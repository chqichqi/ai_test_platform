"""
TestCase Auditor — 测试用例数量评审 Agent

职责：
1. 校验 Step2 生成的用例数量是否与 Step1 features 数量一致
2. 数量不足 → 识别缺失 feature → 触发补偿生成
3. 数量超出 → 识别冗余 case → 裁剪
"""

import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    """评审结果"""
    expected_count: int            # features 数量
    actual_count: int              # 实际生成数量
    status: str = "ok"             # "ok" | "under" | "over"
    missing_features: list = field(default_factory=list)   # 缺失 feature 的描述
    redundant_indices: list = field(default_factory=list)  # 冗余用例的索引
    corrected_cases: list = field(default_factory=list)    # 修正后的完整用例列表
    summary: str = ""
    marker_stats: dict = field(default_factory=dict)  # 「」标记覆盖率诊断（仅观测，不拦截）


class TestCaseAuditor:
    """测试用例数量评审 Agent。

    在 Step2 生成后、保存前运行，确保生成数量与 Step1 features 一致。
    使用 LLM 进行语义层面的缺失/冗余分析。
    """

    def __init__(self, llm_service):
        """
        Args:
            llm_service: LLMService 实例（用于补偿生成和冗余分析）
        """
        self.llm_service = llm_service

    async def audit(self, features: list, test_cases: list) -> AuditResult:
        """主入口：评审并返回修正后的用例列表。

        Args:
            features: Step1 提取的功能点列表 [{"key": "...", "name": "...", ...}]
            test_cases: Step2 生成的用例列表 (dict 格式, 含 title/test_steps 等)

        Returns:
            AuditResult 含 status + corrected_cases
        """
        expected = len(features)
        actual = len(test_cases)

        logger.info(f"[Auditor] 开始评审: 期望 {expected} 条, 实际 {actual} 条")

        # 「」标记覆盖率诊断（不拦截，仅观测 LLM 是否遵守标记约定）
        marker_stats = self._check_marker_coverage(test_cases)
        if marker_stats["total_steps"] > 0 and marker_stats["unmarked_steps"] > 0:
            logger.warning(
                f"[Auditor] ⚠️ 「」标记缺失 {marker_stats['unmarked_steps']}/"
                f"{marker_stats['total_steps']} 步 ({marker_stats['unmarked_ratio']:.0%}), "
                f"涉及 {marker_stats['unmarked_case_count']} 条用例——"
                f"这些步骤将退化为正则/LLM 猜测解析，探索定位可能不准"
            )
            for _s in marker_stats["samples"]:
                logger.warning(f"[Auditor]   → {_s}")

        if actual == expected:
            logger.info(f"[Auditor] ✅ 数量一致, 通过")
            return AuditResult(
                expected_count=expected, actual_count=actual,
                status="ok", corrected_cases=test_cases,
                summary=f"数量一致: {actual}/{expected}",
                marker_stats=marker_stats,
            )

        if actual < expected:
            logger.warning(f"[Auditor] ⚠️ 数量不足: {actual}/{expected}, 触发补偿生成")
            return await self._handle_under_generation(features, test_cases, expected, actual, marker_stats)

        # actual > expected
        logger.warning(f"[Auditor] ⚠️ 数量超出: {actual}/{expected}, 触发冗余检测")
        return await self._handle_over_generation(features, test_cases, expected, actual, marker_stats)

    @staticmethod
    def _check_marker_coverage(test_cases: list) -> dict:
        """「」标记覆盖率诊断：统计可交互步骤中缺失「」标记的比例。

        约定（与 step_parser 消费同源）：
        - 可交互步骤用「」标记 UI 元素名、"" 标记操作值
        - 纯验证/断言类步骤（验证/断言/检查/确认 开头）豁免，不需要标记
        仅观测记录，不拦截生成（软约束 + 诊断，暴露 LLM 遵守率）。
        """
        total_steps = 0
        unmarked_steps = 0
        unmarked_cases = set()
        samples = []
        # 与 step_parser 的 validate 动词同源的豁免前缀（约定 3）
        _exempt_prefixes = ("验证", "断言", "检查", "确认")
        for tc in test_cases:
            steps = tc.get("test_steps") or tc.get("steps") or []
            if not isinstance(steps, list):
                continue
            for st in steps:
                action = ""
                if isinstance(st, dict):
                    action = str(st.get("action", "") or "")
                elif isinstance(st, str):
                    action = st
                action = action.strip()
                if not action:
                    continue
                total_steps += 1
                if action.startswith(_exempt_prefixes):
                    continue
                if "「" not in action:
                    unmarked_steps += 1
                    _title = (tc.get("title") or tc.get("name") or "(无标题)")[:40]
                    unmarked_cases.add(_title)
                    if len(samples) < 5:
                        samples.append(f"{_title}: {action[:60]}")
        return {
            "total_steps": total_steps,
            "unmarked_steps": unmarked_steps,
            "unmarked_ratio": (unmarked_steps / total_steps) if total_steps else 0.0,
            "unmarked_case_count": len(unmarked_cases),
            "samples": samples,
        }

    # ═══════════════════════════════════════════════════════════
    # 补偿生成（数量不足）
    # ═══════════════════════════════════════════════════════════

    async def _handle_under_generation(
        self, features: list, test_cases: list, expected: int, actual: int,
        marker_stats: dict = None,
    ) -> AuditResult:
        """数量不足时：用 LLM 识别缺失 feature → 补偿生成。"""
        llm_config = self.llm_service.get_active_config()
        if not llm_config:
            logger.warning("[Auditor] 无 LLM 配置, 无法补偿生成, 返回原始数据")
            return AuditResult(
                expected_count=expected, actual_count=actual,
                status="under", missing_features=[],
                corrected_cases=test_cases,
                summary="无 LLM 配置, 未补偿",
                marker_stats=marker_stats or {},
            )

        # Step 1: 识别哪些 feature 缺失用例
        missing = await self._identify_missing_features(features, test_cases)
        if not missing:
            # LLM 无法识别 → 保守返回
            return AuditResult(
                expected_count=expected, actual_count=actual,
                status="under", missing_features=[],
                corrected_cases=test_cases,
                summary="无法识别缺失项, 保持原始数据",
                marker_stats=marker_stats or {},
            )

        # Step 2: 补偿生成
        logger.info(f"[Auditor] 识别到 {len(missing)} 个缺失功能点, 开始补偿生成...")
        compensated = await self._generate_missing_cases(missing)
        if compensated:
            test_cases = list(test_cases) + compensated
            logger.info(f"[Auditor] 补偿生成完成: +{len(compensated)} 条, "
                       f"总计 {len(test_cases)} 条")

        return AuditResult(
            expected_count=expected, actual_count=len(test_cases),
            status="ok" if len(test_cases) >= expected else "under",
            missing_features=missing,
            corrected_cases=test_cases,
            summary=f"补偿 {len(compensated)} 条, 最终 {len(test_cases)}/{expected}",
            marker_stats=marker_stats or {},
        )

    async def _identify_missing_features(
        self, features: list, test_cases: list
    ) -> list:
        """用 LLM 分析哪些 feature 没有被覆盖。

        Returns: 缺失的 feature 列表（原始 dict 格式）
        """
        # 构建 case title 列表
        case_titles = []
        for tc in test_cases:
            title = tc.get("title") or tc.get("name", "")
            case_titles.append(title[:80])

        # 构建 feature 列表
        feature_lines = []
        for i, f in enumerate(features, 1):
            key = f.get("key", "")
            name = f.get("name", "")
            cat = f.get("category", "")
            detail = f.get("detail", "")[:60]
            feature_lines.append(f"  [{i}] [{cat}] {name} ({key}): {detail}")

        # 问问 LLM 哪些 feature 没被覆盖
        prompt = f"""你是测试用例覆盖度分析专家。

功能点列表 (共 {len(features)} 个):
{chr(10).join(feature_lines)}

已有测试用例 (共 {len(case_titles)} 条):
{chr(10).join(f'  [{i+1}] {t}' for i, t in enumerate(case_titles))}

请找出**完全没有被任何用例覆盖**的功能点编号。
返回 JSON: {{"missing_indices": [3, 7, 12]}}
若无缺失，返回: {{"missing_indices": []}}
直接输出 JSON，不要 markdown。"""

        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(0.05, 2000), json_mode=False,
            )
            if not response:
                return []

            import re
            json_match = re.search(r'\{.*?\}', response.strip(), re.DOTALL)
            if not json_match:
                return []

            result = json.loads(json_match.group(0))
            indices = result.get("missing_indices", [])
            if not indices:
                return []

            # 收集缺失的 feature
            missing = []
            for idx in indices:
                if isinstance(idx, int) and 1 <= idx <= len(features):
                    missing.append(features[idx - 1])
            return missing

        except Exception as e:
            logger.warning(f"[Auditor] 识别缺失功能点失败: {e}")
            return []

    async def _generate_missing_cases(self, missing_features: list) -> list:
        """为缺失的功能点补偿生成用例。"""
        if not missing_features:
            return []

        lines = []
        for i, f in enumerate(missing_features, 1):
            name = f.get("name", "")
            cat = f.get("category", "")
            detail = f.get("detail", "")[:80]
            lines.append(f"  {i}. [{cat}] {name}: {detail}")

        prompt = f"""你是功能测试用例生成专家。请为以下功能点生成测试用例。

缺失的功能点（共 {len(missing_features)} 个）:
{chr(10).join(lines)}

要求:
1. 为每个功能点生成**恰好 1 条**用例
2. 聚焦该功能点的核心操作场景
3. test_steps 中 action 遵循 UI 命名约定（「」标记元素, "" 标记值, 验证：开头）
4. 输出纯 JSON: {{"test_cases": [{{"title": "...", "module": "...", "priority": "P1", "test_type": "positive", "preconditions": [], "test_steps": [{{"step_no": 1, "action": "点击「元素」按钮", "expected_result": "..."}}], "expected_result": "...", "tags": []}}]}}

"""

        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(), json_mode=False,
            )
            if not response:
                return []

            import re as _audit_re
            # 提取最外层 JSON 对象（贪婪匹配，处理嵌套 {} 和 []）
            _start = response.find('{')
            if _start < 0:
                return []
            # 括号平衡提取
            _depth = 0
            _end = -1
            for _i in range(_start, len(response)):
                if response[_i] == '{':
                    _depth += 1
                elif response[_i] == '}':
                    _depth -= 1
                    if _depth == 0:
                        _end = _i + 1
                        break
            if _end < 0:
                return []
            result = json.loads(response[_start:_end])
            cases = result.get("test_cases", [])
            logger.info(f"[Auditor] 补偿生成 {len(cases)} 条用例")
            return cases

        except Exception as e:
            logger.warning(f"[Auditor] 补偿生成失败: {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # 冗余检测（数量超出）
    # ═══════════════════════════════════════════════════════════

    async def _handle_over_generation(
        self, features: list, test_cases: list, expected: int, actual: int,
        marker_stats: dict = None,
    ) -> AuditResult:
        """数量超出时：用 LLM 识别冗余 case → 裁剪。"""
        llm_config = self.llm_service.get_active_config()
        if not llm_config:
            logger.warning("[Auditor] 无 LLM 配置, 无法裁剪, 返回原始数据")
            return AuditResult(
                expected_count=expected, actual_count=actual,
                status="over", redundant_indices=[],
                corrected_cases=test_cases,
                summary="无 LLM 配置, 未裁剪",
                marker_stats=marker_stats or {},
            )

        redundant = await self._identify_redundant_cases(features, test_cases, expected)
        if not redundant:
            return AuditResult(
                expected_count=expected, actual_count=actual,
                status="over", redundant_indices=[],
                corrected_cases=test_cases,
                summary="无法识别冗余, 保持原始数据",
                marker_stats=marker_stats or {},
            )

        # 裁剪：去掉冗余的，保留前 expected 条
        redundant_set = set(redundant)
        kept = [tc for i, tc in enumerate(test_cases) if i not in redundant_set]
        # 如果裁剪后仍超出，截断
        if len(kept) > expected:
            kept = kept[:expected]
        elif len(kept) < expected:
            # 裁剪过多，补回一些
            for i, tc in enumerate(test_cases):
                if len(kept) >= expected:
                    break
                if i not in redundant_set and tc not in kept:
                    kept.append(tc)

        logger.info(f"[Auditor] 裁剪 {len(redundant)} 条冗余, "
                   f"最终 {len(kept)}/{expected}")

        return AuditResult(
            expected_count=expected, actual_count=len(kept),
            status="ok" if len(kept) == expected else "over",
            redundant_indices=redundant,
            corrected_cases=kept,
            summary=f"裁剪 {len(redundant)} 条, 最终 {len(kept)}/{expected}",
            marker_stats=marker_stats or {},
        )

    async def _identify_redundant_cases(
        self, features: list, test_cases: list, expected: int
    ) -> list:
        """用 LLM 识别冗余/重复的用例。

        Returns: 冗余用例的索引列表
        """
        excess = len(test_cases) - expected
        if excess <= 0:
            return []

        case_lines = []
        for i, tc in enumerate(test_cases, 1):
            title = (tc.get("title") or tc.get("name", ""))[:80]
            case_lines.append(f"  [{i}] {title}")

        prompt = f"""你是测试用例质量评审专家。

期望生成 {expected} 条用例，但实际生成了 {len(test_cases)} 条（超出 {excess} 条）。

请找出哪些用例是**功能重复或冗余**的（覆盖同一功能点的多条用例）。
返回 JSON: {{"redundant_indices": [3, 7]}}  (编号是上面列表中的数字)

规则:
- 只标记明确重复的，保留有独立测试价值的
- 每个功能点最多保留 1 条
- 如果无法确定，则不返回

用例列表:
{chr(10).join(case_lines)}

直接输出 JSON，不要 markdown。"""

        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(0.05, 2000), json_mode=False,
            )
            if not response:
                return []

            import re
            json_match = re.search(r'\{.*?\}', response.strip(), re.DOTALL)
            if not json_match:
                return []

            result = json.loads(json_match.group(0))
            indices = result.get("redundant_indices", [])
            # 转 0-based 索引
            return [i - 1 for i in indices if isinstance(i, int) and 1 <= i <= len(test_cases)]

        except Exception as e:
            logger.warning(f"[Auditor] 识别冗余失败: {e}")
            return []
