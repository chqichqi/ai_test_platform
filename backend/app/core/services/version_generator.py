"""
版本生成服务
用于在创建版本时自动生成测试用例
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.services.llm_service import LLMService
from app.core.models.test_skill import TestSkill, SkillType, SkillStatus
from app.core.models.requirement import RequirementDocument, TestCase as RequirementTestCase, TestCaseStatus, TestCasePriority
from app.core.models.project import Version
from app.core.services.two_step_generator import (
    extract_features, build_step2_prompt, split_doc_sections, clean_module, _STEP1_CHUNK_MAX,
)
from app.core.services.version_generator_utils import clean_module_name
from app.core.services.test_case_auditor import TestCaseAuditor


def _calc_limits(max_tokens: int) -> tuple:
    """根据LLM max_tokens动态计算输入/输出上限，预留安全余量。

    策略：
    - 系统prompt固定预留 ~2000 tokens
    - 输入占40%（中文约2字/token，确保需求内容完整传入）
    - 输出占55%（JSON格式，每条用例约250 token）
    - 剩余5%缓冲
    """
    mt = max_tokens or 8192
    system_overhead = 2000
    available = mt - system_overhead
    input_tokens = int(available * 0.40)
    output_tokens = int(available * 0.55)
    max_input_chars = input_tokens * 2
    safe_cases = max(5, output_tokens // 250)
    return max_input_chars, safe_cases


# ═══════════════════════════════════════════════════════════════
# 中文文本相似度辅助（用于跨 LLM 运行的用例去重匹配）
# ═══════════════════════════════════════════════════════════════

def _chinese_bigram_set(text: str):
    """提取中文二元组集合（用于 Jaccard 相似度计算）。"""
    import re as _re2
    # 只保留中文字符
    chars = _re2.sub(r'[^一-鿿]', '', text)
    if len(chars) < 2:
        return set()
    return {chars[i:i+2] for i in range(len(chars) - 1)}


def _chinese_bigram_similarity(text1: str, text2: str) -> float:
    """中文二元组 Jaccard 相似度。"""
    s1 = _chinese_bigram_set(text1)
    s2 = _chinese_bigram_set(text2)
    if not s1 or not s2:
        return 0.0
    intersection = len(s1 & s2)
    union = len(s1 | s2)
    return intersection / union if union > 0 else 0.0


class VersionGeneratorService:
    """版本生成服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
    
    async def generate_test_assets(
        self,
        version_id: int,
        requirement_doc_content: str,
        project_name: str,
        version_number: str,
        source_type: str = "ai",
    ) -> Dict[str, Any]:
        """
        生成测试资产（测试用例）- 优化版
        
        优化措施：
        1. 分批处理（每批最多6个模块）
        2. 使用LLM配置的max_tokens，上限100000
        3. 需求内容截断到8KB避免输入过长
        """
        try:
            logger.info(f"[{project_name} v{version_number}] 开始生成测试资产")
            logger.info(f"需求文档长度：{len(requirement_doc_content)} 字符")
            
            # 获取LLM配置的max_tokens（上限100000，因为有些模型限制32768）
            llm_config = self.llm_service.get_active_config()
            if not llm_config:
                logger.error("没有活跃的LLM配置，无法生成测试用例")
                return {"success": False, "error": "没有活跃的LLM配置，请在系统设置中配置LLM服务"}
            config_max_tokens = llm_config.max_tokens or 8192
            max_tokens_limit = min(config_max_tokens, 100000)
            logger.info(f"LLM配置: provider={getattr(llm_config, 'provider', 'unknown')}, model={getattr(llm_config, 'model_name', 'unknown')}, max_tokens={config_max_tokens}")
            
            # 1. 获取功能测试 SKILL 模板
            skill = self.db.query(TestSkill).filter(
                TestSkill.skill_type == SkillType.FUNCTIONAL.value,
                TestSkill.is_global == True,
                TestSkill.status == SkillStatus.ACTIVE.value,
            ).first()

            if not skill:
                skill = self.db.query(TestSkill).filter(
                    TestSkill.is_global == True,
                    TestSkill.status == SkillStatus.ACTIVE.value,
                ).first()
                logger.info("未找到功能测试 SKILL，使用通用 SKILL")
            else:
                logger.info(f"找到 SKILL 模板：{skill.name}")
            
            skill_dict = None
            if skill:
                skill_content = skill.content if hasattr(skill, 'content') else None
                skill_dict = skill_content if isinstance(skill_content, dict) else None
                logger.info(f"SKILL模板: name={skill.name}, has_prompt_template={bool(skill_dict.get('prompt_template') if skill_dict else False)}, has_role={bool(skill_dict.get('role') if skill_dict else False)}")
            else:
                skill_dict = None
                logger.info("未找到任何激活的全局SKILL模板")
            
            # 2. Step1: LLM + CoT 分块提取结构化功能点列表
            #   extract_features 已 finalize：每个 feature 带 module 归属 + 机器稳定 key（不再单值 module 全覆盖）
            logger.info("[两步法] Step1: 分块提取功能点...")
            features_result = await extract_features(self.llm_service, requirement_doc_content)
            features = features_result.get("features", []) or []
            self._step1_features = features       # 供 Auditor / 落库归并 / diff 使用
            self._step1_contexts = features_result.get("contexts", {}) or {}   # 规范模型：模块级共享声明 {clean_module(module): ctx}
            module_from_llm = features[0].get("module", "通用模块") if features else "通用模块"
            modules = sorted({f.get("module") or "通用模块" for f in features}) if features else []
            logger.info(f"[两步法] Step1完成: {len(features)}个功能点, 涉及模块={modules}")

            # 需求原文 → 章节索引（供每批注入本批 feature 对应模块的原文段，而非同款头部原文）
            _sections = split_doc_sections(requirement_doc_content)
            _sec_by_normhead = {}
            for _s in _sections:
                _h = clean_module(_s.get("heading", ""))
                if _h:
                    _sec_by_normhead.setdefault(_h, _s)

            def _module_content(_mod: str) -> str:
                """取某 module 对应的原文段；找不到则回退整篇头部。"""
                _c = _sec_by_normhead.get(clean_module(_mod))
                if _c:
                    return _c["content"]
                return requirement_doc_content[:_STEP1_CHUNK_MAX]

            def _ensure_entry_nav(_case: dict, _mod: str):
                """规范模型兜底（2026-09-03）：若该模块在 Step1 声明了入口导航，且该用例首步
                不是导航类动作，则把入口导航前插为 test_steps 第 1 步——因为前置条件不执行、
                导航必须靠步骤，否则用例永远到不了目标页（患者档案类用例即如此）。"""
                import re as _re
                _ctx = (self._step1_contexts or {}).get(clean_module(_mod)) or {}
                _nav = (_ctx.get("entry_navigation") or "").strip()
                if not _nav:
                    return _case
                # ── 入口导航脏声明拦截（2026-09-03）：Step1 的 entry_navigation 若本身是
                # 整条菜单枚举（含换行/多个「」/超长），不能前插——它会把"点整条侧边栏菜单"
                # 固化进每条用例 step1，是"探索乱跑/反复卡工作台"的上游源头。脏则弃用、
                # 交由探索按用例步骤对象自行进入，绝不把整块菜单塞进「」。
                if ("\n" in _nav or "\r" in _nav) or len(_nav) > 60 \
                        or _nav.count("」") > 2 or "「工作台" in _nav:
                    logger.warning(f"  [规范模型] 模块[{_mod}] 入口导航声明含整条菜单/脏文本，弃用不前插: {_nav[:50]}...")
                    return _case
                _steps = _case.get("test_steps") or []
                if not isinstance(_steps, list) or not _steps:
                    return _case
                _f = _steps[0]
                _fa = (_f.get("action") if isinstance(_f, dict) else str(_f)) or ""
                if _re.search(r"进入|导航|goto|跳转|从工作台|打开.+?页面|点击.+?菜单", _fa):
                    return _case   # 首步已是导航，不重复前插
                _seq_key = None
                if isinstance(_steps[0], dict):
                    _seq_key = "step_no" if "step_no" in _steps[0] else ("step" if "step" in _steps[0] else None)
                _pre = {"action": _nav, "expected_result": "成功进入目标页面"}
                if _seq_key:
                    _pre[_seq_key] = 1
                _out = [_pre]
                for _k, _s in enumerate(_steps):
                    _s2 = dict(_s) if isinstance(_s, dict) else {"action": str(_s)}
                    if _seq_key and _seq_key in _s2:
                        try:
                            _s2[_seq_key] = int(_s2[_seq_key]) + 1
                        except Exception:
                            _s2[_seq_key] = _k + 2
                    _out.append(_s2)
                _case["test_steps"] = _out
                logger.info(f"  [规范模型] 模块[{_mod}] 用例首步前插入口导航: {_nav[:40]}...")
                return _case

            # ── Step2: 按 module 分组 → 每 module 内小批生成（1:1 约束）──
            # 小批避免"一次吐巨型 JSON"的结构性截断风险；编号全局连续
            _STEP2_BATCH = 8
            all_test_cases = []
            if features:
                system_prompt = self._build_system_prompt(skill_dict)
                _gno = 1
                _retry = 3                      # 每批最大尝试次数
                # 生成队列：元素 (module, features子批, 剩余尝试)。整批失败 → 拆两半重入队尾降级重试，
                # 直到单条粒度，保证功能点不因单批 LLM 空/坏响应而整批丢失。
                _queue = []
                for _mod in modules:
                    _group = [f for f in features if (f.get("module") or "通用模块") == _mod]
                    for _bi in range(0, len(_group), _STEP2_BATCH):
                        _queue.append((_mod, _group[_bi:_bi + _STEP2_BATCH], _retry))

                _qi = 0
                while _qi < len(_queue):
                    _mod, _batch, _left = _queue[_qi]; _qi += 1
                    _bn = len(_batch)
                    _got = []
                    for _t in range(_left):
                        user_prompt = build_step2_prompt(
                            project_name, version_number, _mod, _batch,
                            _module_content(_mod), start_index=_gno,
                            module_context=(self._step1_contexts or {}).get(clean_module(_mod)),
                        )
                        # 大输出档：每条用例约 600-800 token，小批 + 0.7/100000 防截断
                        dynamic_max_tokens = self.llm_service.get_scaled_max_tokens(0.7, 100000)
                        logger.info(f"[Step2] 模块[{_mod}] 批({_bn}点, 从TC{_gno:03d}) 尝试{_t + 1}/{_left} "
                                    f"max_tokens={dynamic_max_tokens}")
                        _resp = await self.llm_service.async_call_llm(
                            prompt=user_prompt, system_prompt=system_prompt,
                            temperature=0, max_tokens=dynamic_max_tokens, json_mode=False,
                        )
                        if not _resp:
                            logger.warning(f"  [{_mod}]批 LLM 返回空，重试")
                            continue
                        _got = self._parse_got_cases(_resp)
                        if len(_got) >= _bn:      # 整批覆盖到点数才收（避免残缺/垃圾入库）
                            break
                        logger.warning(f"  [{_mod}]批仅恢复 {len(_got)}/{_bn} 条(需整批覆盖)，重试")
                    # 收或降级
                    if len(_got) >= _bn:
                        _kept = []
                        for _c in _got:
                            if not isinstance(_c, dict):
                                _kept.append(_c)
                                continue
                            if not _c.get("module"):
                                _c["module"] = _mod
                            _kept.append(_ensure_entry_nav(_c, _mod))
                        all_test_cases.extend(_kept)
                        _gno += len(_kept)
                    elif _bn > 1:
                        _h = _bn // 2
                        logger.warning(f"  模块[{_mod}] 批({_bn}点)多次仍失败 → 拆为 {_h}/{_bn - _h} 两半重试")
                        _queue.append((_mod, _batch[:_h], _retry))
                        _queue.append((_mod, _batch[_h:], _retry))
                    else:
                        _fn = _batch[0].get("name") if _batch else "?"
                        logger.error(f"  模块[{_mod}] 功能点「{_fn}」多次生成仍失败, 已跳过")

                if not all_test_cases:
                    logger.error("所有批次 LLM 均返回空")
                    return {"success": False, "error": "LLM 未生成任何用例"}

                case_count = len(all_test_cases)
                parsed_result = {
                    "test_cases": all_test_cases,
                    "analysis_summary": {
                        "total_count": case_count,
                        "p0_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P0"),
                        "p1_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P1"),
                        "p2_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P2"),
                        "p3_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P3"),
                    }
                }
                logger.info(f"Step2 完成: 共 {case_count} 条用例 (期望 {len(features)})")
            else:
                # 无 features：不再静默走无约束"按模块自由生成"（该路径曾合并卡片漏用例）
                logger.error("[两步法] 未能从需求文档提取到结构化功能点（features 为空）")
                return {"success": False, "error": "未能从需求文档提取到结构化功能点，请确认文档包含明确的页面/功能描述后重试"}

            # 4.5 Auditor 评审（数量校验 + 补偿生成 + 冗余检测）
            _raw_cases = parsed_result.get("test_cases", [])
            _features = getattr(self, '_step1_features', [])
            if _features and _raw_cases:
                auditor = TestCaseAuditor(self.llm_service)
                _result = await auditor.audit(_features, _raw_cases)
                logger.info(f"[Auditor] 评审结果: {_result.summary}")
                if _result.status != "ok" or len(_result.corrected_cases) != len(_raw_cases):
                    logger.info(f"[Auditor] 使用修正后的用例: {len(_result.corrected_cases)} 条")
                    parsed_result["test_cases"] = _result.corrected_cases  # 同步到 parsed_result
                    parsed_result["analysis_summary"]["total_count"] = len(_result.corrected_cases)
                    _raw_cases = _result.corrected_cases

            # 共享准备/setup 的处理已下移到 _save_test_cases：依据 feature.category=='setup' 标 is_setup、
            # 同 module 卡片自动 depends_on（不再用 preconditions 措辞规则反推——会把"处于展开状态"等静态句误抽）

            # 5. 保存测试用例到数据库
            logger.info(f"开始保存测试用例... ({len(_raw_cases)} 条)")
            test_cases_count = await self._save_test_cases(
                version_id,
                _raw_cases,
                source_type
            )
            logger.info(f"保存测试用例完成：{test_cases_count} 个")
            
            logger.info(
                f"[{project_name} v{version_number}] 测试资产生成完成：{test_cases_count} 个测试用例"
            )

            return {
                "success": True,
                "test_cases_count": test_cases_count,
                "analysis_summary": parsed_result.get("analysis_summary", {})
            }
            
        except Exception as e:
            logger.error(f"[{project_name} v{version_number}] 生成测试资产失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _build_prompts_from_skill(
        self,
        skill_content: Optional[Dict[str, Any]],
        project_name: str,
        version_number: str,
        requirement_content: str,
        modules: List[str] = None,
        estimated_cases_per_module: int = 5
    ) -> tuple:
        """从 SKILL 模板构建系统提示词和用户提示词
        
        Args:
            skill_content: SKILL内容字典
            project_name: 项目名称
            version_number: 版本号
            requirement_content: 需求文档内容
            modules: 已识别的模块列表（避免重复识别）
            estimated_cases_per_module: 每模块预估用例数（统一为5）
        """
        # 如果未提供模块，才识别（但通常应该传入已识别的模块）
        if modules is None:
            modules = self._extract_modules_from_requirement(requirement_content)
        
        # 统一预估数量（每模块5个）
        estimated_cases = len(modules) * estimated_cases_per_module
        
        if skill_content and skill_content.get("prompt_template"):
            prompt_template = skill_content.get("prompt_template")
            
            # 如果是字符串格式（旧版），使用默认方法
            if isinstance(prompt_template, str):
                system_prompt = self._build_system_prompt(skill_content)
                user_prompt = self._build_user_prompt(project_name, version_number, requirement_content, modules)
                return system_prompt, user_prompt
            
            # 如果是对象格式（新版），使用模板变量替换
            if isinstance(prompt_template, dict):
                system_prompt = prompt_template.get("system_prompt", "")
                
                modules_list = self._format_modules_list(modules)
                
                # 大文档优化：截断需求内容（保留关键部分）
                max_doc_length = 20000
                truncated_content = requirement_content
                if len(requirement_content) > max_doc_length:
                    truncated_content = self._extract_key_content(requirement_content, modules, max_doc_length)
                    logger.info(f"需求文档过长({len(requirement_content)}字符)，已截断为{len(truncated_content)}字符")
                
                # 变量替换
                user_prompt_template = prompt_template.get("user_prompt", "")
                user_prompt = user_prompt_template.replace("{{project_name}}", project_name)
                user_prompt = user_prompt.replace("{{version_number}}", version_number)
                user_prompt = user_prompt.replace("{{requirement_content}}", truncated_content)
                user_prompt = user_prompt.replace("{{modules_list}}", modules_list)
                user_prompt = user_prompt.replace("{{estimated_cases}}", str(estimated_cases))
                
                logger.info(f"使用 SKILL 模板提示词，模块数：{len(modules)}，预估用例：{estimated_cases}")
                return system_prompt, user_prompt
        
        # 使用默认方法
        system_prompt = self._build_system_prompt(skill_content)
        user_prompt = self._build_user_prompt(project_name, version_number, requirement_content, modules)
        return system_prompt, user_prompt
    
    def _extract_key_content(self, content: str, modules: List[str], max_length: int) -> str:
        """从大文档中提取关键内容
        
        提取策略：
        1. 保留文档开头（项目信息）
        2. 保留每个模块的标题和功能清单表格
        3. 保留重要的业务规则
        """
        import re
        
        lines = content.split('\n')
        result_lines = []
        current_length = 0
        
        # 1. 保留开头100行（文档信息、目录等）
        for i, line in enumerate(lines[:100]):
            result_lines.append(line)
            current_length += len(line) + 1
        
        # 2. 提取每个模块的关键部分（标题+功能清单表格）
        for module in modules[:20]:  # 最多处理20个模块
            # 找到模块标题位置
            module_pattern = re.escape(module)
            for i, line in enumerate(lines):
                if re.search(module_pattern, line) and i not in result_lines:
                    # 从模块标题开始，保留接下来的50行（功能清单表格）
                    start = max(0, i - 2)  # 包含标题前2行
                    end = min(len(lines), i + 50)
                    for j in range(start, end):
                        if j not in [len(result_lines) + k for k in range(end - start)]:
                            if current_length + len(lines[j]) + 1 < max_length:
                                result_lines.append(lines[j])
                                current_length += len(lines[j]) + 1
                    break
        
        # 3. 如果还有空间，添加业务规则部分
        if current_length < max_length * 0.8:
            for i, line in enumerate(lines):
                if '业务规则' in line or '业务逻辑' in line or '核心业务' in line:
                    start = max(0, i)
                    end = min(len(lines), i + 30)
                    for j in range(start, end):
                        if current_length + len(lines[j]) + 1 < max_length:
                            if lines[j] not in result_lines:
                                result_lines.append(lines[j])
                                current_length += len(lines[j]) + 1
                    break
        
        return '\n'.join(result_lines)
    
    def _extract_batch_content(self, content: str, batch_modules: List[str], max_length: int) -> str:
        """提取批次相关的需求内容
        
        Args:
            content: 需求文档完整内容
            batch_modules: 当前批次的模块列表
            max_length: 最大长度限制
        
        Returns:
            当前批次模块相关的需求内容
        """
        import re
        
        lines = content.split('\n')
        result_lines = []
        current_length = 0
        
        # 保留开头50行（文档信息）
        for i in range(min(50, len(lines))):
            result_lines.append(lines[i])
            current_length += len(lines[i]) + 1
        
        # 提取当前批次模块的内容
        for module in batch_modules:
            module_pattern = re.escape(module)
            for i, line in enumerate(lines):
                if re.search(module_pattern, line):
                    start = max(0, i)
                    end = min(len(lines), i + 100)  # 每个模块保留100行
                    for j in range(start, end):
                        if current_length + len(lines[j]) + 1 < max_length:
                            if lines[j] not in result_lines:
                                result_lines.append(lines[j])
                                current_length += len(lines[j]) + 1
                    break
        
        return '\n'.join(result_lines)
    
    def _build_system_prompt(self, skill_content: Optional[Dict[str, Any]]) -> str:
        """构建系统提示词，充分利用 SKILL 模板的完整内容"""
        if skill_content:
            role = skill_content.get("role", {})
            role_name = role.get("name", "功能测试用例生成专家")
            role_desc = role.get("description", "")
            expertise = role.get("expertise", [])
            behavior_rules = role.get("behavior_rules", [])
            
            methods = skill_content.get("methods", [])
            methods_text = self._format_methods(methods)
            
            domain_rules = skill_content.get("domain_rules", [])
            domain_text = self._format_domain_rules(domain_rules)
            
            quality_checks = skill_content.get("quality_checks", [])
            quality_text = "\n".join(["- " + q for q in quality_checks])
            
            expertise_text = "\n".join(["- " + e for e in expertise])
            behavior_text = "\n".join(["- " + r for r in behavior_rules])
            
            system_prompt = self._build_full_system_prompt(
                role_name, role_desc, expertise_text, behavior_text,
                methods_text, domain_text, quality_text
            )
            
            return system_prompt
        else:
            return self._build_default_system_prompt()
    
    def _format_methods(self, methods: List[Dict]) -> str:
        """格式化测试方法库"""
        lines = []
        for m in methods:
            name = m.get("name", "")
            desc = m.get("description", "")
            scenarios = m.get("applicable_scenarios", [])
            
            line = f"【{name}】{desc}"
            if scenarios:
                line += f"\n适用场景：{', '.join(scenarios)}"
            lines.append(line)
        return "\n".join(lines)
    
    def _format_domain_rules(self, domain_rules: List[Dict]) -> str:
        """格式化领域规则"""
        lines = []
        for rule in domain_rules:
            domain = rule.get("domain", "")
            must_test = rule.get("must_test", [])
            security = rule.get("security_focus", [])
            
            line = f"【{domain}】"
            if must_test:
                line += f"\n必须测试：{', '.join(must_test)}"
            if security:
                line += f"\n安全关注：{', '.join(security)}"
            lines.append(line)
        return "\n".join(lines)
    
    def _build_full_system_prompt(
        self, role_name: str, role_desc: str, expertise: str,
        behavior: str, methods: str, domain: str, quality: str
    ) -> str:
        """构建完整的系统提示词"""
        json_example = '''
{
  "test_cases": [
    {
      "id": "TC001",
      "title": "用例标题",
      "module": "所属模块",
      "sub_module": "子模块",
      "priority": "P0/P1/P2/P3",
      "test_type": "positive/negative/boundary/exception",
      "preconditions": ["前置条件1", "前置条件2"],
      "test_steps": [
        {"step_no": 1, "action": "操作描述", "expected_result": "预期结果"}
      ],
      "test_data": {},
      "tags": ["标签1"],
      "automation_level": "high/medium/low"
    }
  ],
  "test_summary": {
    "total_count": 100,
    "p0_count": 10,
    "p1_count": 30,
    "p2_count": 40,
    "p3_count": 20,
    "coverage_analysis": "覆盖率分析",
    "risk_areas": ["风险点"]
  }
}
'''
        
        return f"""# 角色设定

你是一位资深的【{role_name}】。

{role_desc}

## 专业知识领域
{expertise}

## 行为准则
{behavior}

---

# 测试方法库

请根据需求特点，灵活运用以下测试方法：

{methods}

---

# 领域规则

{domain}

---

# 质量检查规则

生成用例时必须满足以下要求：
{quality}

---

# 输出格式要求

请严格按照 JSON 格式输出：
```json
{json_example}
```

---

# 核心要求

1. **为每个功能模块的每个功能点生成至少1条测试用例，覆盖正常场景、异常场景和边界场景**
2. **每个用例必须包含完整的测试步骤和预期结果**
3. **覆盖所有功能点，确保测试覆盖率**
4. **标注合理的优先级（P0核心功能，P1重要功能，P2一般功能，P3次要功能）**
5. **测试数据必须具体、有效、符合业务逻辑**

---

# UI 元素命名约定（关键！影响后续自动化转化）

测试步骤中的 action 字段必须遵循以下约定，以便后续自动化工具能精确识别页面元素：

## 约定 1：用「」标记真正的 UI 元素名

页面上的按钮、输入框、下拉框、卡片等可交互元素的名字，用「」括起来。
描述 UI 组件类型的词（如"卡片""按钮""输入框""下拉框""链接""菜单""页面"）放在「」外面。

✅ 正确写法：
  - 点击「室早」卡片
  - 点击「新增」按钮
  - 在「患者姓名」输入框中填写
  - 在「状态」下拉框中选择
  - 点击「导出」图标
  - 进入「患者档案」页面

❌ 错误写法（不要把描述词包进「」）：
  - 点击「室早卡片」       ← "卡片"是描述词，不是元素名
  - 点击「新增按钮」       ← "按钮"是描述词
  - 点击「患者姓名输入框」  ← "输入框"是描述词

## 约定 2：用""标记操作值

填入输入框的值、下拉框选中的选项，用半角双引号""括起来。
值和元素名必须分离，不能混在「」里。

✅ 正确写法：
  - 在「患者姓名」输入框中填写"张三"
  - 在「状态」下拉框中选择"已审核"
  - 在「筛选」下拉框中选择"≥30"
  - 在「搜索框」中输入"test"

❌ 错误写法：
  - 在「患者姓名输入框」中填写张三    ← 元素名含描述词，值没标记
  - 选择「筛选≥30」                   ← 值和元素名混在一起
  - 在「筛选'≥30'」下拉框中操作       ← 值应放在 "" 中，不在「」中

## 约定 3：纯验证步骤用"验证："开头

不需要操作页面元素的断言/检查步骤，以"验证："开头。
这类步骤不需要「」标记。

✅ 正确写法：
  - 验证：页面显示所有当天佩戴预警
  - 验证：跳转后的页面 URL 包含 patient-profile
  - 验证：（当卡片总数为0时）页面显示"暂无数据"
  - 验证：接口请求参数中 filter="all"

❌ 错误写法：
  - 点击验证页面显示预警      ← 验证步骤被当成点击操作
  - 检查「页面」显示正确      ← 验证步骤不需要「」标记元素

## 约定 4：每步只做一个 UI 操作

不要把多个操作合并在一步中。

✅ 正确写法：
  - 步骤1：点击「室早」卡片
  - 步骤2：验证：跳转到患者档案页面

❌ 错误写法：
  - 点击室早卡片并验证跳转到患者档案页面

请开始生成测试用例。"""
    
    def _build_default_system_prompt(self) -> str:
        """构建默认系统提示词"""
        return """# 角色设定

你是一位资深的功能测试用例生成专家，拥有10年以上测试经验。擅长从需求文档中提取测试点，设计高覆盖率的测试用例。

## 核心要求

1. **每个功能模块至少生成8-15个测试用例**
2. **每个用例必须包含完整的测试步骤和预期结果**
3. **覆盖正常场景、异常场景、边界场景**
4. **标注合理的优先级（P0核心功能，P1重要功能，P2一般功能，P3次要功能）**
5. **测试数据必须具体、有效、符合业务逻辑**

---

# 测试方法

- 等价类划分法：划分有效和无效输入
- 边界值分析法：测试边界值及附近值
- 场景法：基于业务流程设计测试场景
- 状态迁移法：测试系统状态转换
- 错误推测法：基于经验推测可能缺陷

---

# UI 元素命名约定（关键！影响自动化转化）

## 测试步骤的 action 字段必须遵循以下约定：

1. **用「」标记真正的 UI 元素名**：点击「室早」卡片（不要写"室早卡片"）
2. **用""标记操作值**：在「患者姓名」输入框中填写"张三"
3. **纯验证步骤用"验证："开头**：验证：页面显示所有当天佩戴预警
4. **每步只做1个UI操作**：不要把点击和验证合并在一步
5. **描述词（卡片/按钮/输入框/下拉框）放在「」外面**，不要包进去

## 正确 vs 错误示例：
✅ 点击「室早」卡片 → 元素名="室早"
❌ 点击「室早卡片」 → "卡片"是描述词，不是元素名
✅ 在「筛选」下拉框中选择"≥30" → 元素="筛选", 值="≥30"
❌ 筛选≥30 → 值和元素混在一起
✅ 验证：页面显示"暂无数据" → 纯验证步骤
❌ 检查页面显示暂无数据 → 缺少"验证："前缀

---

# 输出格式

请以JSON格式输出，包含test_cases数组和test_summary对象。"""
    
    def _build_user_prompt(
        self,
        project_name: str,
        version_number: str,
        requirement_content: str,
        modules: Optional[List[str]] = None
    ) -> str:
        """构建用户提示词，包含模块分解和用例数量引导
        
        注意：使用字符串拼接而非 f-string，避免需求文档中的花括号导致格式化错误
        """
        
        if modules is None:
            modules = self._extract_modules_from_requirement(requirement_content) or []
        modules_text = self._format_modules_list(modules)
        estimated_cases = len(modules) * 8  # 每模块约 8 条，LLM 自行调整

        prompt_parts = [
            "# 项目信息\n",
            f"- **项目名称**: {project_name}\n",
            f"- **版本号**: {version_number}\n",
            "\n---\n\n",
            "# 需求文档内容\n\n",
            requirement_content,
            "\n\n---\n\n",
            "# 功能模块列表（已识别）\n\n",
            "根据需求文档分析，识别出以下功能模块：\n\n",
            modules_text,
            "\n\n---\n\n",
            "# 用例生成要求\n\n",
            "## 1. 模块覆盖要求\n\n",
            "请为**每个模块**单独生成测试用例，确保覆盖所有功能点。\n\n",
            f"**用例数量参考**: 建议为此批次生成约 {estimated_cases} 个测试用例"
            f"（每个模块约 8 个，LLM 可根据功能点数量自行调整，不强制固定数量）。\n\n",
            "## 2. 每个模块的用例要求\n\n",
            "对于每个模块，请覆盖以下场景：\n\n",
            "- **正常场景用例**: 验证功能正常运行\n",
            "- **异常场景用例**: 验证错误处理和异常情况\n",
            "- **边界场景用例**: 验证边界值和极限情况\n\n",
            "## 3. 用例字段要求\n\n",
            "每个测试用例必须包含以下字段：\n\n",
            "| 字段 | 说明 | 示例 |\n",
            "|------|------|------|\n",
            "| id | 用例编号 | TC001 |\n",
            "| title | 用例标题（简洁明了） | 验证用户登录-正常登录 |\n",
            "| module | 所属模块 | 用户管理模块 |\n",
            "| priority | 优先级 | P0/P1/P2/P3 |\n",
            "| test_type | 测试类型 | positive/negative/boundary |\n",
            "| preconditions | 前置条件列表 | ['用户已注册', '系统运行正常'] |\n",
            "| test_steps | 测试步骤（每步含action和expected_result） | [{'step_no':1,'action':'点击登录','expected_result':'显示登录页'}] |\n",
            "| expected_result | **整体预期结果**（整个用例完成后的最终结果） | 用户成功登录系统，进入首页 |\n",
            "| tags | 标签 | ['登录', '功能测试'] |\n\n",
            "**重要：expected_result是整体预期结果，与test_steps中每步的expected_result不同！**\n",
            "- test_steps中的expected_result：每个步骤完成后的即时结果\n",
            "- 顶层的expected_result：整个测试用例执行完成后的最终结果\n",
            "- 两者不应重复！\n\n",
            "## 3.1 前置条件要求\n\n",
            "- 前置条件只描述「执行本用例所必需的环境/登录/页面就绪状态」，必须可满足可执行。\n",
            "- **禁止把数据量写成前置条件**（如「今日新增数大于0」「存在至少一条记录」「列表非空」）：无数据（0条/空列表）是合法测试场景，数据量是断言对象，不是执行前提。\n",
            "- 数量类断言必须动态化：先「记录界面显示的数字为 N」，再断言「跳转后/操作后记录总数与 N 一致（0 也正确）」或「记录数≥0」，不要断言写死的具体数字。\n\n",
            "## 4. 优先级分配原则\n\n",
            "- **P0**: 核心功能、关键业务流程\n",
            "- **P1**: 重要功能、主要业务场景\n",
            "- **P2**: 一般功能、常规场景\n",
            "- **P3**: 次要功能、边缘场景\n\n",
            "## 5. 特别关注\n\n",
            "请特别关注以下内容：\n\n",
            "- 业务规则和约束条件\n",
            "- 数据验证规则\n",
            "- 状态流转逻辑\n",
            "- 权限控制\n",
            "- 安全性要求\n",
            "- 异常处理机制\n\n",
            "---\n\n",
            "# 步骤编写示例（Few-Shot）\n\n",
            "以下是符合 UI 元素命名约定的步骤写法示例——请严格遵循「」和\"\"的用法：\n\n",
            "## 示例 1：卡片点击跳转\n",
            "- 步骤1：进入「工作台」页面 | 预期：显示统计卡片区域\n",
            "- 步骤2：记录「今日新增」后面的数字为 N | 预期：成功获取数字\n",
            "- 步骤3：点击「室早」卡片 | 预期：跳转到患者档案页面\n",
            "- 步骤4：验证：页面 URL 包含 patient-profile | 预期：URL 正确\n",
            "- 步骤5：验证：「疾病类型」下拉框显示\"室早\" | 预期：下拉框值为室早\n\n",
            "## 示例 2：表单筛选查询\n",
            "- 步骤1：在「筛选」下拉框中选择\"≥30\" | 预期：下拉选项展开并选中≥30\n",
            "- 步骤2：点击「查询」按钮 | 预期：列表刷新，显示筛选后的数据\n",
            "- 步骤3：验证：列表中的记录数发生变化 | 预期：记录数≥0\n",
            "- 步骤4：验证：（当记录数为0时）页面显示\"暂无数据\" | 预期：显示空状态\n\n",
            "## 示例 3：弹窗新增操作\n",
            "- 步骤1：点击「新增」按钮 | 预期：弹出新增对话框\n",
            "- 步骤2：在弹窗中，在「患者姓名」输入框中填写\"张三\" | 预期：输入成功\n",
            "- 步骤3：在弹窗中，在「性别」下拉框中选择\"男\" | 预期：选中男\n",
            "- 步骤4：在弹窗中，点击「确定」按钮 | 预期：弹窗关闭，列表刷新\n",
            "- 步骤5：验证：列表中出现姓名为\"张三\"的记录 | 预期：新增成功\n\n",
            "## 示例 4：纯验证 / 断言步骤\n",
            "- 验证：页面加载完成，无报错信息 | 预期：页面正常加载\n",
            "- 验证：列表总记录数与卡片统计数字一致 | 预期：数据一致\n",
            "- 验证：接口请求参数中 filter=\"all\" | 预期：API 参数正确\n\n",
            "## 关键规则回顾\n",
            "- 「」内 = 页面真实存在的 UI 元素文本（不含\"卡片\"\"按钮\"等描述词）\n",
            "- \"\" 内 = 填入/选中的值\n",
            "- 验证： = 纯断言步骤（不需要定位 UI 元素）\n",
            "- 每条 action 只做 1 个 UI 操作\n\n",
            "---\n\n",
            "# 输出要求\n\n",
            "请输出 JSON 格式，结构如下（注意 test_steps 中每条 action 都要遵循上述约定）：\n\n",
            '{"test_cases": [{"id": "TC001", "title": "验证室早卡片跳转", "module": "工作台", "priority": "P0", "test_type": "positive", "preconditions": ["已登录系统，进入工作台页面"], "test_steps": [{"step_no": 1, "action": "点击「室早」卡片", "expected_result": "跳转到患者档案页面"}, {"step_no": 2, "action": "验证：页面URL包含patient-profile", "expected_result": "URL正确"}], "expected_result": "成功从工作台跳转到患者档案页面", "tags": ["跳转", "卡片"]}], "test_summary": {"total_count": 100}}\n\n',
            "**请开始生成完整的测试用例列表，确保每个模块都有充分的覆盖。**",
        ]
        
        return "".join(prompt_parts)
    
    def _extract_modules_from_requirement(self, requirement_content: str) -> List[str]:
        """从需求文档中提取一级功能模块（支持多种格式）
        
        支持格式：
        1. Markdown标题（## 开头）
        2. Word/PDF解析后的纯文本标题（中文编号、数字编号）
        3. 功能清单表格
        4. 关键词模式（常见功能名称）
        """
        import re
        
        modules = []
        
        # 过滤关键词列表
        skip_keywords = [
            '概述', '背景', '简介', '附录', '目录', '说明',
            '规则', '字典', '术语', '前言', '文档', '版本',
            '修订', '变更', '范围', '目的', '总体', '引言',
            '编写', '审核', '审批', '发布', '修订记录', '变更记录'
        ]
        
        # 策略1: Markdown二级标题（### 开头）- 优先识别具体功能模块
        # 使用负向先行断言确保###后面不是#（排除####标题）
        md_level2_patterns = [
            r'^(###)(?!\#)\s*\d+[、.]\d+[、.]*\s*([^\n]+)',  # ### 2.1 登录功能（X.Y格式）
            r'^(###)(?!\#)\s*[一二三四五六七八九十]+[、.]\d+[、.]*\s*([^\n]+)',  # ### 一.1 登录功能
        ]
        
        for pattern in md_level2_patterns:
            matches = re.findall(pattern, requirement_content, re.MULTILINE)
            for match in matches:
                # match是元组 (###, 标题内容)，取第二个元素
                module_name = match[1] if isinstance(match, tuple) else match
                module_name = module_name.strip()
                # 排除以#开头的结果（错误匹配）
                if module_name.startswith('#'):
                    continue
                # 清理编号前缀
                module_name = re.sub(r'^\d+[、.]*\d*[、.]*\s*', '', module_name)
                module_name = re.sub(r'^[一二三四五六七八九十]+[、.]*\d*[、.]*\s*', '', module_name)
                module_name = module_name.strip()
                if module_name and len(module_name) > 2:
                    # 只保留包含功能关键词的标题（确保是功能模块而非子节）
                    functional_keywords = ['功能', '模块', '接口', '管理', '系统', '组件', '服务']
                    if any(fk in module_name for fk in functional_keywords):
                        if not any(kw in module_name for kw in skip_keywords):
                            if module_name not in modules:
                                modules.append(module_name)
                                logger.info(f"从###标题识别功能模块: {module_name}")
        
        # 策略2: Markdown一级标题（## 开头）- 仅在未识别到二级模块时使用
        if not modules:
            md_level1_patterns = [
                r'^##\s+[一二三四五六七八九十]+[、.]\s*([^\n]+)',  # ## 一、登录功能
                r'^##\s+\d+[、.]\s*([^\n]+)',  # ## 2. 功能需求
                r'^##\s+([^\n]+)',  # ## 登录功能（确保##后面不是#）
            ]
            
            for pattern in md_level1_patterns:
                matches = re.findall(pattern, requirement_content, re.MULTILINE)
                for match in matches:
                    module_name = match.strip()
                    if module_name and len(module_name) > 3:
                        if not any(kw in module_name for kw in skip_keywords):
                            if module_name not in modules:
                                modules.append(module_name)
        
        # 策略2: 纯文本标题（Word/PDF解析后，无Markdown格式）
        # 中文编号：一、登录功能
        chinese_num_pattern = r'[一二三四五六七八九十百]+[、.]\s*([^\n]{3,30})'
        chinese_matches = re.findall(chinese_num_pattern, requirement_content)
        for match in chinese_matches:
            module_name = match.strip()
            # 过滤非功能标题
            if module_name and len(module_name) > 3:
                if not any(kw in module_name for kw in skip_keywords):
                    # 检查是否包含常见功能关键词
                    functional_keywords = ['功能', '管理', '测试', '接口', '配置', '设置', '查询', '操作', '模块', '页面', '系统']
                    if any(fk in module_name for fk in functional_keywords) or len(module_name) > 5:
                        if module_name not in modules:
                            modules.append(module_name)
        
        # 策略3: 数字编号标题（1. 登录功能）
        digit_pattern = r'\d+[、.]\s*([^\n]{3,30})'
        digit_matches = re.findall(digit_pattern, requirement_content)
        for match in digit_matches:
            module_name = match.strip()
            if module_name and len(module_name) > 3:
                if not any(kw in module_name for kw in skip_keywords):
                    functional_keywords = ['功能', '管理', '测试', '接口', '配置', '设置', '查询', '操作', '模块', '页面', '系统']
                    if any(fk in module_name for fk in functional_keywords) or len(module_name) > 5:
                        if module_name not in modules:
                            modules.append(module_name)
        
        # 策略4: 从表格提取（功能模块列）
        if not modules:
            table_patterns = [
                r'\|\s*功能模块\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*模块名称\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*模块\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*功能\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*功能名称\s*\|\s*([^\|]+)\s*\|',
            ]
            
            for pattern in table_patterns:
                matches = re.findall(pattern, requirement_content)
                for match in matches:
                    module_name = match.strip()
                    if module_name and len(module_name) > 2:
                        if not any(kw in module_name for kw in ['功能模块', '模块名称']):
                            if module_name not in modules:
                                modules.append(module_name)
        
        # 策略5: 关键词模式（常见功能名称）
        if not modules:
            keyword_patterns = [
                r'(RAG知识库管理|SKILL管理|功能测试|API接口测试|WEB UI测试|测试报告管理|测试管理|项目管理|用户管理|权限管理|配置管理|数据管理|登录管理|注册管理)',
                r'(?:功能|模块|管理)[:：]\s*([^\n，。]{3,30})',
            ]
            
            for pattern in keyword_patterns:
                matches = re.findall(pattern, requirement_content)
                for match in matches:
                    module_name = match.strip()
                    if module_name and len(module_name) >= 3:
                        if not any(kw in module_name for kw in skip_keywords):
                            if module_name not in modules:
                                modules.append(module_name)
        
        # 策略6: 如果还是识别不到，尝试识别段落标题（换行后的独立行）
        if not modules:
            lines = requirement_content.split('\n')
            for line in lines[:50]:  # 只检查前50行
                line = line.strip()
                # 检查是否是标题行（不以小写字母开头，长度3-30，不含特殊符号）
                if line and len(line) >= 3 and len(line) <= 30:
                    # 排除包含特殊符号的行
                    if not any(sym in line for sym in ['|', '*', '-', '=', '#', '>', '<', '【', '】', '[', ']']):
                        # 排除纯数字或纯英文单词
                        if not re.match(r'^[\d\s]+$|^[\w\s]+$', line):
                            # 检查是否包含功能关键词
                            functional_keywords = ['功能', '管理', '测试', '接口', '配置', '设置', '查询', '操作', '模块', '页面', '系统']
                            if any(fk in line for fk in functional_keywords):
                                if not any(kw in line for kw in skip_keywords):
                                    if line not in modules:
                                        modules.append(line)
        
        # 策略7: 如果所有策略都失败，返回默认值
        if not modules:
            modules = ["核心功能模块"]
            logger.warning("未能识别功能模块，使用默认值")
        
        # 清理和去重
        cleaned_modules = []
        for m in modules:
            # 去除编号前缀
            clean_name = re.sub(r'^[一二三四五六七八九十百\d]+[、.]\s*', '', m)
            clean_name = re.sub(r'[【\[].*?[】\]]', '', clean_name)
            clean_name = clean_name.strip()
            
            # 去除"功能"、"模块"后缀并去重
            base_name = clean_name.replace('功能', '').replace('模块', '').strip()
            existing_base_names = [
                x.replace('功能', '').replace('模块', '').strip()
                for x in cleaned_modules
            ]
            
            if base_name and base_name not in existing_base_names:
                cleaned_modules.append(clean_name if len(clean_name) > 3 else m)
        
        # 限制模块数量（最多20个）
        if len(cleaned_modules) > 20:
            logger.info(f"模块过多（{len(cleaned_modules)}个），限制为前20个")
            cleaned_modules = cleaned_modules[:20]
        
        logger.info(f"模块识别完成：识别到{len(cleaned_modules)}个一级模块")
        return cleaned_modules
    
    def _format_modules_list(self, modules: Optional[List[str]]) -> str:
        """格式化模块列表"""
        import re
        if not modules:
            return "（未能识别具体模块，请根据需求文档自行分析）"

        lines = []
        for i, module in enumerate(modules, 1):
            # 去掉 emoji 和特殊符号，保留中文和字母
            clean = re.sub(r'[^\w一-鿿\s]', '', module).strip()
            lines.append(f"{i}. **{clean}**")
        
        lines.append("")
        lines.append(f"总计识别到 **{len(modules)}** 个功能模块")
        
        return "\n".join(lines)
    

    def _parse_llm_response(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 响应"""
        try:
            import re
            import json
            
            # 尝试 1: 提取 JSON 代码块
            json_match = None
            pattern = r'```json\s*(.*?)\s*```'
            match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
            
            if match:
                json_str = match.group(1)
                logger.info(f"从 JSON 代码块中提取内容，长度：{len(json_str)}")
            else:
                # 尝试 2: 提取任何花括号包围的内容
                pattern = r'\{.*\}'
                match = re.search(pattern, llm_response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    logger.info(f"从文本中提取 JSON 内容，长度：{len(json_str)}")
                else:
                    # 尝试 3: 直接使用整个响应
                    json_str = llm_response.strip()
                    logger.info(f"使用整个响应作为 JSON，长度：{len(json_str)}")
            
            # 清理 JSON 字符串
            json_str = json_str.strip()
            
            # 尝试解析
            try:
                parsed = json.loads(json_str)
                logger.info("JSON 解析成功")
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败：{e}，尝试修复...")
                
                # 记录响应内容以便调试
                debug_file_path = f"./logs/llm_response_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                try:
                    import os
                    os.makedirs("./logs", exist_ok=True)
                    with open(debug_file_path, 'w', encoding='utf-8') as f:
                        f.write(f"=== LLM Response Debug ===\n")
                        f.write(f"Error: {e}\n")
                        f.write(f"Response Length: {len(llm_response)}\n")
                        f.write(f"JSON String Length: {len(json_str)}\n")
                        # 错误点上下文（2026-09-01 教训：只存首尾看不到错误位置，无法定位幻觉类型）
                        _pos = getattr(e, 'pos', None)
                        if _pos is not None:
                            f.write(f"Error Position: {_pos}\n")
                            f.write(f"\n=== Context around error (char {_pos}) ===\n")
                            f.write(json_str[max(0, _pos - 800):_pos + 800])
                        f.write(f"\n\n=== First 5000 chars of JSON ===\n")
                        f.write(json_str[:5000])
                        f.write(f"\n\n=== Last 500 chars of JSON ===\n")
                        f.write(json_str[-500:])
                    logger.info(f"LLM响应已保存到: {debug_file_path}")
                except Exception as save_err:
                    logger.warning(f"保存LLM响应失败: {save_err}")
                
                # 多种修复策略
                fix_strategies = [
                    # 策略1: 移除末尾逗号
                    lambda s: re.sub(r',(\s*[}\]])', r'\1', s),
                    # 策略2: 替换单引号为双引号
                    lambda s: s.replace("'", '"'),
                    # 策略3: 修复键名引号
                    lambda s: re.sub(r'(["\']?)\s*(\w+)\s*(["\']?)\s*:', r'"\2":', s),
                    # 策略4: 移除控制字符
                    lambda s: re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s),
                    # 策略5: 修复未闭合的数组/对象
                    lambda s: self._fix_unclosed_json(s),
                    # 策略6: 移除注释
                    lambda s: re.sub(r'//.*?\n|/\*.*?\*/', '', s, flags=re.DOTALL),
                    # 策略7: 修复多余的空格和换行
                    lambda s: re.sub(r'\s+', ' ', s),
                ]
                
                for i, fix_func in enumerate(fix_strategies):
                    try:
                        fixed_str = fix_func(json_str)
                        parsed = json.loads(fixed_str)
                        logger.info(f"JSON 修复策略{i+1}成功")
                        return parsed
                    except Exception:
                        continue
                
                logger.error(f"所有JSON修复策略失败")
                
                # 最后尝试：从响应中提取测试用例信息
                logger.info("尝试从文本中提取测试用例...")
                return self._extract_test_cases_from_text(llm_response)
        
        except Exception as e:
            logger.error(f"解析 LLM 响应失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _fix_unclosed_json(self, json_str: str) -> str:
        """修复未闭合的JSON"""
        try:
            # 1. 先修复截断的字符串（未闭合的引号）
            # 检测最后是否是未闭合的字符串
            last_quote_pos = json_str.rfind('"')
            if last_quote_pos > 0:
                # 检查从该位置到末尾是否有闭合引号
                after_last_quote = json_str[last_quote_pos + 1:]
                next_quote_pos = after_last_quote.find('"')
                if next_quote_pos == -1 and len(after_last_quote.strip()) > 0:
                    # 可能是截断的字符串，尝试闭合它
                    # 找到字符串值的开始位置
                    # 简单策略：在截断处添加闭合引号并截断后续内容
                    truncated_pos = json_str.rfind('"expected_result":')
                    if truncated_pos > 0:
                        # 截断到expected_result字段，闭合整个对象
                        json_str = json_str[:truncated_pos]
                        logger.warning(f"JSON截断，已截断到expected_result字段前")
            
            # 2. 修复未闭合的花括号和方括号
            open_braces = json_str.count('{') - json_str.count('}')
            open_brackets = json_str.count('[') - json_str.count(']')
            
            if open_braces > 0:
                json_str += '}' * open_braces
            if open_brackets > 0:
                json_str += ']' * open_brackets
            
            # 3. 确保test_cases数组有闭合
            if 'test_cases' in json_str and not json_str.rstrip().endswith('}'):
                # 添加test_summary对象闭合
                if 'test_summary' not in json_str:
                    json_str += ', "test_summary": {"total_count": 0}'
            
            return json_str
        except Exception as e:
            logger.warning(f"JSON修复失败: {e}")
            return json_str
    
    def _extract_test_cases_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取测试用例信息（备用方案）"""
        try:
            import re
            
            test_cases = []
            
            # 尝试提取类似测试用例的结构
            # 匹配模式：数字。标题 或 数字、标题
            patterns = [
                r'(\d+)[\.、]\s*([^\n]+)',
                r'测试用例 [:-]\s*([^\n]+)',
                r'用例 [:-]\s*([^\n]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        title = match[1]
                    elif isinstance(match, tuple) and len(match) >= 1:
                        title = match[0]
                    elif isinstance(match, str):
                        title = match
                    else:
                        continue
                    
                    if title and len(title.strip()) > 5:
                        test_cases.append({
                            "title": title.strip(),
                            "module": "通用模块",
                            "description": "",
                            "priority": "P2",
                            "preconditions": "",
                            "test_steps": [title.strip()],
                            "expected_results": "操作成功"
                        })
            
            if test_cases:
                logger.info(f"从文本中提取到 {len(test_cases)} 个测试用例")
                return {
                    "test_cases": test_cases[:20],  # 限制最多 20 个
                    "analysis_summary": {
                        "total_count": len(test_cases),
                        "p0_count": 0,
                        "coverage_analysis": "基于文本提取",
                        "risk_points": []
                    }
                }
            
            return None
        except Exception as e:
            logger.error(f"从文本中提取测试用例失败：{e}")
            return None
    
    def _extract_partial_cases_from_response(self, llm_response: str) -> Optional[List[Dict[str, Any]]]:
        """从截断的LLM响应中提取已生成的部分测试用例
        
        当JSON解析失败时，尝试从响应中提取已生成的测试用例（即使JSON不完整）
        
        Args:
            llm_response: LLM返回的原始响应
            
        Returns:
            提取到的测试用例列表，或None
        """
        try:
            import re
            import json
            
            test_cases = []
            
            # 策略1：平衡括号逐条提取顶层用例对象（一条出错只丢一条，不拖垮整批）
            # 2026-09-01 根因：LLM 60KB 大 JSON 中部语法错误（char 38743 缺逗号/未转义引号）
            # → 整体解析失败 → 旧正则 `\{\s*"id":\s*"TC\d+"\s*,.*?\}` 非贪婪匹配到嵌套对象
            # 内部第一个 } → 逐条提取必然失败 → 兜底只保 title（无 test_steps）→
            # 57 条全部「跳过无步骤用例」→ 0 条。改为字符串感知的括号平衡扫描。
            for _idm in re.finditer(r'"id"\s*:\s*"TC\d+"', llm_response):
                _obj_start = llm_response.rfind('{', 0, _idm.start())
                if _obj_start == -1:
                    continue
                _depth = 0
                _in_str = False
                _esc = False
                _obj_end = -1
                for _i in range(_obj_start, len(llm_response)):
                    _ch = llm_response[_i]
                    if _in_str:
                        if _esc:
                            _esc = False
                        elif _ch == '\\':
                            _esc = True
                        elif _ch == '"':
                            _in_str = False
                    else:
                        if _ch == '"':
                            _in_str = True
                        elif _ch == '{':
                            _depth += 1
                        elif _ch == '}':
                            _depth -= 1
                            if _depth == 0:
                                _obj_end = _i
                                break
                if _obj_end == -1:
                    continue
                _case_str = llm_response[_obj_start:_obj_end + 1]
                _case = None
                try:
                    _case = json.loads(_case_str)
                except json.JSONDecodeError:
                    # 单条失败：常见修复（末尾逗号/控制字符）后重试；仍失败只丢此条
                    _fixed = re.sub(r',(\s*})', r'}', _case_str)
                    _fixed = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', _fixed)
                    try:
                        _case = json.loads(_fixed)
                    except Exception:
                        logger.warning(f"单条用例解析失败(仅丢此条): {_case_str[:60]!r}...")
                if _case and _case.get("title"):
                    test_cases.append(_case)
                    logger.info(f"提取到部分用例: {_case.get('title')[:30]}")
            
            # 策略3：如果还是提取不到，使用正则提取关键字段
            if not test_cases:
                logger.info("尝试正则提取关键字段...")
                
                # 提取所有用例ID和标题
                id_title_pattern = r'"id":\s*"TC(\d+)"\s*,\s*"title":\s*"([^"]+)"'
                id_title_matches = re.findall(id_title_pattern, llm_response)
                
                for tc_id, title in id_title_matches:
                    # 提取module字段
                    module_pattern = '"id":\\s*"TC' + str(tc_id) + '"[^}]*"module":\\s*"([^"]+)"'
                    module_match = re.search(module_pattern, llm_response)
                    module = module_match.group(1) if module_match else "通用模块"
                    
                    # 提取priority字段
                    priority_pattern = '"id":\\s*"TC' + str(tc_id) + '"[^}]*"priority":\\s*"([^"]+)"'
                    priority_match = re.search(priority_pattern, llm_response)
                    priority = priority_match.group(1) if priority_match else "P2"
                    
                    # 构造基础测试用例
                    test_cases.append({
                        "id": f"TC{tc_id}",
                        "title": title,
                        "module": module,
                        "priority": priority,
                        "test_type": "positive",
                        "preconditions": [],
                        "test_steps": [],
                        "expected_result": "功能正常运行",
                        "tags": []
                    })
                    logger.info(f"正则提取到用例: {title[:30]}")
            
            if test_cases:
                logger.info(f"共提取到 {len(test_cases)} 条部分测试用例")
                return test_cases
            
            logger.warning("未能提取到任何部分测试用例")
            return None
            
        except Exception as e:
            logger.error(f"提取部分测试用例失败：{e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _llm_semantic_match(
        self, old_cases: list, new_cases: list
    ) -> list:
        """用 LLM 做语义匹配：判断哪些新用例与旧用例测试同一功能。

        不按模块分组——两次 Step1 提取的模块名可能不同，
        导致同功能用例被分到不同模块而无法匹配。
        改为全部新旧用例一起发给 LLM（限制总数避免 token 超限）。

        Returns:
            [{"new_idx": 0, "old_name": "验证室早卡片跳转-正向"}, ...]
        """
        import re as _llm_re

        if not old_cases or not new_cases:
            return []

        llm_config = self.llm_service.get_active_config()
        if not llm_config:
            logger.info("[LLM去重] 无活跃 LLM 配置，跳过语义匹配")
            return []

        # 限制总数（避免 prompt 过长）
        MAX_BATCH = 40
        old_slice = old_cases[:MAX_BATCH]
        # new_cases 中每个元素是 (original_idx, dict)，需要切片
        new_indexed = list(enumerate(new_cases))  # [(original_idx, nc_dict)]
        new_slice = new_indexed[:MAX_BATCH]

        logger.info(f"[LLM去重] 开始语义匹配: {len(old_slice)} 旧 × {len(new_slice)} 新")

        # 构建 prompt
        old_lines = []
        for i, oc in enumerate(old_slice, 1):
            name = getattr(oc, 'name', '')
            mod = getattr(oc, 'module', '') or ''
            steps = getattr(oc, 'test_steps', [])
            first_step = ''
            if isinstance(steps, list) and steps:
                s0 = steps[0]
                first_step = (s0.get('action', '') if isinstance(s0, dict) else str(s0))[:80]
            old_lines.append(f"  [{i}] [{mod}] {name}" + (f" | {first_step}" if first_step else ""))

        new_lines = []
        for i, (orig_idx, nc) in enumerate(new_slice, 1):
            mod = nc.get('module', '')
            ps = nc.get('processed_steps', [])
            first_step = ''
            if isinstance(ps, list) and ps:
                s0 = ps[0]
                first_step = (s0.get('action', '') if isinstance(s0, dict) else str(s0))[:80]
            new_lines.append(f"  [{i}] [{mod}] {nc['name']}" + (f" | {first_step}" if first_step else ""))

        prompt = f"""你是测试用例去重专家。判断新旧两组用例中，哪些测试的是**同一功能**。

判断标准：覆盖相同的 UI 操作或业务规则 → 同一功能。注意不同模块下的用例也可能是同一功能。
- "室早卡片跳转" ≈ "室早统计卡片点击跳转验证" → 匹配（同一功能）
- "筛选≥30" vs "筛选≥30边界值" → 匹配（同一筛选项，不同描述）
- "室早卡片跳转" vs "房颤卡片跳转" → 不匹配（不同功能）
- "验证页面加载" vs "验证筛选功能" → 不匹配（不同功能）

旧用例（已存在）:
{chr(10).join(old_lines) if old_lines else '(无)'}

新用例（本次导入）:
{chr(10).join(new_lines) if new_lines else '(无)'}

输出 JSON 匹配对数组。若不确信则不输出该对。
格式: [{{"new": 1, "old": 3}}]  (数字对应上面列表的编号)
无匹配输出: []
直接输出 JSON，不要 markdown。"""

        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(0.05, 2000), json_mode=False,
            )
            if not response:
                logger.info("[LLM去重] LLM 返回空，无匹配")
                return []

            # 解析 LLM 返回的匹配对
            import json as _json
            json_match = _llm_re.search(r'\[.*?\]', response.strip(), _llm_re.DOTALL)
            if not json_match:
                logger.info(f"[LLM去重] 未找到 JSON 数组: {response[:200]}")
                return []

            pairs = _json.loads(json_match.group(0))
            if not pairs:
                logger.info("[LLM去重] LLM 返回空数组，无匹配")
                return []

            all_matches = []
            for pair in pairs:
                new_num = pair.get('new', 0)
                old_num = pair.get('old', 0)
                if new_num < 1 or old_num < 1:
                    continue
                if new_num > len(new_slice) or old_num > len(old_slice):
                    continue
                orig_idx, nc_data = new_slice[new_num - 1]
                old_case = old_slice[old_num - 1]
                all_matches.append({
                    'new_idx': orig_idx,
                    'old_name': getattr(old_case, 'name', ''),
                })

            logger.info(f"[LLM去重] 匹配完成: {len(pairs)} 对 ({len(all_matches)} 有效)")
            return all_matches

        except Exception as e:
            logger.warning(f"[LLM去重] 语义匹配异常: {e}")
            import traceback; traceback.print_exc()
            return []

    async def _save_test_cases(
        self,
        version_id: int,
        test_cases: List[Dict[str, Any]],
        source_type: str = "ai"
    ) -> int:
        """保存测试用例到数据库"""
        import re as _re
        count = 0
        # setup 占位符 → logical_case_id（生成后处理把共享准备抽成 setup 用例，排在普通用例前先落库，
        # 普通用例的 depends_on 若含 setup_token 字符串，在此解析为其逻辑 id）
        _setup_logical = {}

        from app.core.models.project import Version


        version = self.db.query(Version).filter(Version.id == version_id).first()
        if not version:
            logger.error(f"版本 ID {version_id} 不存在")
            return 0
        
        project_id = version.project_id
        logger.info(f"保存测试用例到项目 {project_id}, 版本 {version_id}")

        # 获取当前版本已有用例的最大 sort_order
        from app.core.models.requirement import TestCase as TC
        max_order = self.db.query(TC).filter(TC.version_id == version_id).count() * 10
        base_order = max_order + 10

        # ── 同模块清理改为"按 feature 逐条 diff"，绝不前置整模块删草稿（2026-09-03）──
        # 用户语义：
        #   * 不同模块的旧用例一律不删（导入新模块=追加）；
        #   * 同模块内：feature 仍存在的旧用例→由下方循环按稳定 key 就地更新（保留 id，不产生双份）；
        #     feature 在本批确实下线(未出现)的 DRAFT 孤例→循环结束后按 feature diff 删除；
        #     已审核/非草稿孤例→保留，待人工/文档明示再处理。
        # 前提假设：同一模块被重新导入 = 该模块"当前权威完整需求"，因此其内缺失的 feature 视为下线移除。
        # 注意：若将来需要"同模块分次追加子功能"(重导只含部分)，须显式区分 追加 与 整模块替换，
        # 否则按缺即删会误删未重发的部分——那是独立增强，非本次范围。
        # 历史缺陷：旧代码按 version+source+DRAFT 不分模块全删 → 导入 B 模块把 A 模块 58 条草稿连根删。
        _new_modules = sorted({clean_module_name((t.get("module") or "通用模块")) for t in test_cases}) if test_cases else []

        # 加载剩余旧用例（已审核/待审核的，做保护性匹配）
        _old_cases = self.db.query(RequirementTestCase).filter(
            RequirementTestCase.version_id == version_id
        ).all()
        _old_by_title = {}
        _old_by_feature = {}  # source_feature(稳定机器 key) → 旧行，用于跨次归并
        for _oc in _old_cases:
            _tn = getattr(_oc, 'name', '') or ''
            if _tn:
                _old_by_title[_tn] = _oc
            _sf_old = getattr(_oc, 'source_feature', '') or ''
            if _sf_old:
                _old_by_feature.setdefault(_sf_old, _oc)

        # 同一批次内的 source_feature 去重（防止多批生成同功能用例）
        _seen_features = set()
        # 本批实际落库(更新/新建)用例的 source_feature 与 name —— 用于"同模块内按 feature diff 删真正下线的 DRAFT 孤例"
        _issued_src: set = set()
        _issued_names: set = set()
        # Step1 features → 用于创建 TestPoint 记录
        _step1_features = getattr(self, '_step1_features', [])
        # 双索引: key → feature, name → feature（source_feature 可能只匹配 name）
        _features_by_key = {}
        _features_by_name = {}
        for f in (_step1_features or []):
            key = f.get('key', '')
            name = (f.get('name', '') or '').strip()
            if key:
                _features_by_key[key] = f
            if name:
                _features_by_name[name] = f

        def _match_feature(tc_name: str):
            """反查某条用例对应的 feature（name 是 tc_name 子串者取最长匹配）。

            用于把用例的稳定机器 key(source_feature) / TestPoint 与 Step1 功能点对齐。
            """
            best = None
            best_len = 0
            for _f in (_step1_features or []):
                _n = (_f.get('name', '') or '').strip()
                if _n and _n in tc_name and len(_n) > best_len:
                    best = _f
                    best_len = len(_n)
            return best

        # ── 共享准备/setup（生成源头识别，2026-09-03）：feature category=='setup' 对应用例标 is_setup=1 并先落库；
        #    同 module 的普通用例自动 depends_on 该 setup（不依赖 preconditions 措辞反推）
        _feat_all_setup = getattr(self, '_step1_features', []) or []
        _setup_mods = {f.get('module') for f in _feat_all_setup if f.get('category') == 'setup'}
        if _setup_mods:
            def _is_setup_title(t):
                _f = _match_feature((t.get('title') or t.get('name') or ''))
                return bool(_f and _f.get('category') == 'setup')
            test_cases = sorted(test_cases, key=lambda t: (0 if _is_setup_title(t) else 1))

        for idx, tc_data in enumerate(test_cases):
            try:
                tc_name = tc_data.get("title") or tc_data.get("name") or "未命名用例"
                # 模块归属直接用 LLM 为每条用例标的 module（不再被 Step1 单值 module 覆盖）
                tc_module = clean_module_name(tc_data.get("module") or "通用模块")
                tc_description = tc_data.get("description") or ""
                # ── 前置依赖 / setup 标记（共享准备机制 2026-09-03）──
                # is_setup 融合两来源：dict 显式标记 OR 该用例反查到 feature.category=='setup'
                _feat_here = _match_feature(tc_name)
                _feat_is_setup = 1 if (_feat_here and _feat_here.get('category') == 'setup') else 0
                tc_is_setup = int(tc_data.get("is_setup") or 0) or _feat_is_setup
                tc_setup_token = tc_data.get("setup_token") or (f"__SETUP__{tc_module}__" if tc_is_setup else "")
                _raw_dep = list(tc_data.get("depends_on") or []) if isinstance(tc_data.get("depends_on"), list) else []
                # 同 module 存在 setup feature → 非 setup 普通用例自动 depends_on 该 module 的 setup
                if not tc_is_setup and tc_module in _setup_mods:
                    _dtok = f"__SETUP__{tc_module}__"
                    if _dtok not in _raw_dep:
                        _raw_dep.append(_dtok)
                _dep_resolved = []
                for _d in _raw_dep:
                    if isinstance(_d, str):
                        if _d in _setup_logical:
                            _dep_resolved.append(_setup_logical[_d])
                        else:
                            logger.warning(f"  忽略未解析依赖占位符 {_d}（setup 尚未落库）")
                    elif isinstance(_d, int):
                        _dep_resolved.append(_d)
                _dep_resolved = _dep_resolved or None
                tc_priority = tc_data.get("priority") or "P2"
                tc_preconditions = tc_data.get("preconditions") or ""
                if isinstance(tc_preconditions, list):
                    tc_preconditions_text = "\n".join([str(p) for p in tc_preconditions if p])
                else:
                    tc_preconditions_text = str(tc_preconditions) if tc_preconditions else ""
                tc_test_steps = tc_data.get("test_steps") or []
                processed_steps = self._process_test_steps(tc_test_steps, module=tc_module)
                tc_expected_result = (tc_data.get("expected_result") or tc_data.get("expected_results") or
                                     tc_data.get("expected") or "")
                if tc_expected_result in ("测试通过", "功能正常", "操作成功", "功能正常运行"):
                    tc_expected_result = ""
                if not tc_expected_result and tc_test_steps:
                    expected_list = []
                    for step in tc_test_steps:
                        if isinstance(step, dict):
                            se = step.get("expected_result") or step.get("expected") or ""
                            if se:
                                expected_list.append(f"{step.get('step_no', step.get('step', len(expected_list)+1))}. {se}")
                    if expected_list:
                        tc_expected_result = "\n".join(expected_list)
                if not tc_preconditions_text or tc_preconditions_text.strip() in ("", "无", "暂无"):
                    tc_preconditions_text = f"已登录系统并进入{tc_module}页面"
                if not tc_expected_result or tc_expected_result.strip() in ("测试通过", "功能正常", "操作成功", "功能正常运行"):
                    if processed_steps:
                        last = processed_steps[-1]
                        tc_expected_result = last.get("expected", "") or last.get("expected_result", "")
                    if not tc_expected_result or tc_expected_result.strip() in ("测试通过", "功能正常", "操作成功", "功能正常运行"):
                        tc_expected_result = f"{tc_name}操作完成，页面正常响应"

                # 跳过 test_steps 为空的残次品（LLM 截断导致）
                if not processed_steps or all(
                    not (s.get('action', '') if isinstance(s, dict) else str(s))
                    for s in processed_steps
                ):
                    logger.warning(f"  跳过无步骤用例: {tc_name[:50]}")
                    continue

                # 本用例对应的 feature（决定稳定机器 key + 关联 TestPoint）
                _match = _match_feature(tc_name)
                _feature_key = (_match.get('key') if _match else '') or ''
                # source_feature 语义：新逻辑存稳定机器 key(feature.key)，供跨次归并/变更检测；
                # 匹配不到 feature 时回退 title 归一化（兼容历史/无 features 调用方）
                _source_feature = _feature_key or _re.sub(r'[\s\-_,，、]+', '', tc_name)[:50]
                auto_sort_order = base_order + (idx * 10)

                # 同一批次内按 (feature_key 或 title归一化) 去重，避免多批/措辞差异双份
                _dedup_key = _feature_key if _feature_key else _source_feature
                _sf_key = (_dedup_key, tc_module)
                if _sf_key in _seen_features:
                    logger.info(f"  跳过同批次重复: {tc_name[:50]} (key={_feature_key or _source_feature})")
                    continue
                _seen_features.add(_sf_key)
                _issued_src.add(_feature_key or _source_feature)
                _issued_names.add(tc_name)

                # 归并目标：优先稳定 feature_key 命中旧行（跨次同功能→更新同一行，避免双份）
                # → 其次 title 精确命中（兼容历史 title 归一化 source_feature 的行）
                _old_match = _old_by_feature.get(_feature_key) if _feature_key else None
                if not _old_match:
                    _old_match = _old_by_title.get(tc_name)
                if _old_match:
                    _ec = _old_match
                    _ec.name = tc_name
                    _ec.module = tc_module
                    _ec.preconditions = tc_preconditions_text
                    _ec.test_steps = processed_steps
                    _ec.expected_result = str(tc_expected_result)
                    _ec.priority = ("P0" if tc_priority == "P0" else "P1" if tc_priority == "P1"
                                   else "P2" if tc_priority == "P2" else "P3")
                    _ec.tags = tc_data.get("tags", [])
                    # 回写稳定机器 key，保证下次跨次归并能按 key 命中同一行（升级历史行）
                    _ec.source_feature = _source_feature
                    _ec.is_setup = tc_is_setup
                    if _dep_resolved is not None:
                        _ec.depends_on = _dep_resolved
                    # 更新命中到 setup 旧行时也登记（跨次保持逻辑 id 稳定，卡片依赖不因重生成变）
                    if tc_is_setup and tc_setup_token:
                        _setup_logical[tc_setup_token] = getattr(_ec, 'logical_case_id', None) or _ec.id
                    _ec.updated_at = datetime.utcnow()
                    # 更新关联 TestPoint
                    _tp_data = _features_by_key.get(_source_feature) or _features_by_name.get(tc_name.split('-')[0] if '-' in tc_name else tc_name[:8])
                    if not _tp_data:
                        for _f in (_step1_features or []):
                            if (_f.get('name', '') or '').strip() in tc_name:
                                _tp_data = _f
                                break
                    if _tp_data:
                        from app.core.models.requirement import TestPoint
                        _tp = self.db.query(TestPoint).filter(TestPoint.test_case_id == _ec.id).first()
                        if _tp:
                            _tp.feature_key = _tp_data.get('key', _source_feature)
                            _tp.name = _tp_data.get('name', tc_name)
                            _tp.category = _tp_data.get('category', '')
                            _tp.detail = _tp_data.get('detail', '')
                            _tp.updated_at = datetime.utcnow()
                        else:
                            _tp = TestPoint(
                                version_id=version_id, feature_key=_tp_data.get('key', _source_feature),
                                name=_tp_data.get('name', tc_name),
                                category=_tp_data.get('category', ''),
                                detail=_tp_data.get('detail', ''),
                                status='active', test_case_id=_ec.id,
                            )
                            self.db.add(_tp)
                    logger.info(f"  匹配已审核用例: {tc_name[:50]} → 更新 id={_ec.id}")
                    _seen_features.add(_sf_key)
                    count += 1
                    continue

                # 新建
                test_case = RequirementTestCase(
                    project_id=project_id, version_id=version_id,
                    name=tc_name, module=tc_module, description=tc_description,
                    priority=("P0" if tc_priority == "P0" else "P1" if tc_priority == "P1"
                             else "P2" if tc_priority == "P2" else "P3"),
                    status=TestCaseStatus.DRAFT.value,
                    preconditions=tc_preconditions_text,
                    test_steps=processed_steps,
                    expected_result=str(tc_expected_result),
                    tags=tc_data.get("tags", []),
                    sort_order=auto_sort_order,
                    generated_by=source_type,
                    source_feature=_source_feature,
                    is_setup=tc_is_setup,
                    depends_on=_dep_resolved,
                    created_by=1,
                )
                self.db.add(test_case)
                self.db.flush()  # 获取 test_case.id

                # 方案B：新建用例逻辑=物理（logical_case_id=自身id，变更派生时新行共享此 id）
                test_case.logical_case_id = test_case.id
                # setup 登记：供其后普通用例的 depends_on 占位符解析为逻辑 id
                if tc_is_setup and tc_setup_token:
                    _setup_logical[tc_setup_token] = test_case.logical_case_id

                # 创建关联 TestPoint（key 优先匹配，name 回退）
                _tp_data = _features_by_key.get(_source_feature) or _features_by_name.get(tc_name.split('-')[0] if '-' in tc_name else tc_name[:8])
                if not _tp_data:
                    for _f in (_step1_features or []):
                        _fn = (_f.get('name', '') or '').strip()
                        if _fn and _fn in tc_name:
                            _tp_data = _f
                            break
                if _tp_data:
                    from app.core.models.requirement import TestPoint
                    _tp = TestPoint(
                        version_id=version_id,
                        feature_key=_tp_data.get('key', _source_feature),  # 用 Step1 的 key，保证和 diff 一致
                        name=_tp_data.get('name', tc_name),
                        category=_tp_data.get('category', ''),
                        detail=_tp_data.get('detail', ''),
                        status='active',
                        test_case_id=test_case.id,
                    )
                    self.db.add(_tp)

                count += 1

            except Exception as e:
                logger.error(f"保存测试用例失败：{str(e)}")
                import traceback; traceback.print_exc()
                continue

        # ── 同模块内按 feature 逐条 diff：只删"确实下线"的 DRAFT 孤例（2026-09-03）──
        # 判定：旧用例 module ∈ 本次生成模块、status=DRAFT、且其 source_feature/name 均未在本批发出
        # (说明它的 feature 从本模块的需求中移除了)。已审核/非草稿孤例一律保留(待人工/文档明示)。
        # 不同模块的旧用例、以及本批被就地更新的用例(其 source_feature 已写入 _issued_src)都不会被删。
        _orphan_ids: list = []
        if _new_modules:
            from app.core.models.requirement import TestPoint as _TP
            for _oc in _old_cases:
                if clean_module_name(getattr(_oc, 'module', '') or '通用模块') not in _new_modules:
                    continue
                if getattr(_oc, 'status', None) != TestCaseStatus.DRAFT.value:
                    continue
                _osf = (getattr(_oc, 'source_feature', '') or '').strip()
                _oname = (getattr(_oc, 'name', '') or '').strip()
                if _osf and _osf in _issued_src:
                    continue
                if _oname and _oname in _issued_names:
                    continue
                _orphan_ids.append(_oc.id)
            if _orphan_ids:
                self.db.query(_TP).filter(_TP.test_case_id.in_(_orphan_ids)).delete(synchronize_session=False)
                self.db.query(RequirementTestCase).filter(
                    RequirementTestCase.id.in_(_orphan_ids)
                ).delete(synchronize_session=False)
                self.db.flush()
                logger.info(f"[去重·feature diff] 删除同模块内确实下线的 DRAFT 孤例 {len(_orphan_ids)} 条(ids={_orphan_ids})")

        self.db.commit()

        # ---- Feature记录已禁用（ChromaDB模型待下载） ----
        return count
    
    def _extract_shared_setup_cases(self, cases: list) -> list:
        """生成后处理：把散落在多条卡片用例 preconditions 里的"共享准备动作句"抽成一条独立 setup 用例。

        触发场景（2026-09-03 业务流"特殊说明"）：测工作台各指标卡片前须先"把所有指标添加到工作台"，
        否则卡片不在台上会找不到元素。Step2 LLM 会把这一准备句复制进每条卡片用例的 preconditions，
        导致"前置条件混入操作步骤"。本方法：
          1. 拆 preconditions 分句，挑含操作动词的"准备动作句"；
          2. 同一句在 >=2 条用例出现 → 视为共享准备；
          3. 抽成一条 setup 用例（is_setup=1，放最前），其 test_steps 以该准备动作作为一步（转 UI 时由探索映射元素）；
          4. 含该句的普通卡片用例：preconditions 移除该句（静态化），depends_on = [该 setup_token]。
        无共享准备时原样返回（完全不影响普通需求）。
        """
        if not cases:
            return cases
        import re as _re
        from collections import Counter
        _ACT = ("点击", "添加", "移除", "保存", "选择", "滚动", "输入", "打开", "勾选", "填写",
                "确认", "预览", "设置", "启用", "关闭", "切换", "上传", "拖动", "展开", "收缩",
                "删除", "清空", "提交", "配置")
        # 以这些开头的分句视为"静态状态"，即使句中带个别动词也不当准备动作
        _STATIC_PREFIX = ("已展示", "已登录", "已存在", "当前", "存在", "进入", "工作台", "患者",
                          "页面展示", "状态", "总数", "下已")

        def split_clauses(pc):
            return [s.strip() for s in _re.split(r"[;；\n。]+", pc or "") if s.strip()]

        def is_prep(cl):
            c = cl.strip()
            if not c:
                return False
            if c.startswith(_STATIC_PREFIX):
                return False
            return any(v in c for v in _ACT)

        def norm(s):
            return _re.sub(r"[\s\-_，,、：:；;·.]+", "", s or "")

        # 1. 收集每条用例的准备句（归一化）
        clauses_map = []        # 原 order 的每条用例分句
        prep_of_case = []       # 每条用例: {norm: orig}
        cnt = Counter()
        owner = {}
        for ci, c in enumerate(cases):
            if not isinstance(c, dict):
                clauses_map.append([]); prep_of_case.append({}); continue
            clauses = split_clauses(c.get("preconditions"))
            prep = {}
            for cl in clauses:
                if is_prep(cl):
                    n = norm(cl)
                    prep.setdefault(n, cl)
            clauses_map.append(clauses)
            prep_of_case.append(prep)
            for n in prep:
                cnt[n] += 1
                owner.setdefault(n, (ci, prep[n]))

        shared = {n for n, k in cnt.items() if k >= 2}
        if not shared:
            return cases

        top = max(shared, key=lambda n: cnt[n])
        owner_ci, owner_orig = owner[top]
        sample = cases[owner_ci] if isinstance(cases[owner_ci], dict) else {}
        module = clean_module_name(sample.get("module") or "通用模块")
        setup_token = "__SETUP_1__"
        clean_orig = _re.sub(r"^(已通过|需先|先|需要|请|然后|若未|必须|并)", "", owner_orig).strip(" ，,。；;")
        setup_name = (f"前置准备：{clean_orig[:40]}" if clean_orig else "前置准备")

        setup = {
            "title": setup_name, "name": setup_name, "module": module,
            "description": "共享前置准备（生成时自动从多张卡片前置抽取）：执行本模块用例前必须先完成此准备，否则指标卡片未上工作台会找不到元素。",
            "priority": "P0",
            "preconditions": f"已登录系统并进入{module}页面",
            "test_steps": [{
                "step": 1, "action": owner_orig,
                "expected": "准备完成，相关指标卡片已在工作台上展示",
            }],
            "expected_result": "相关指标卡片已在工作台上展示",
            "tags": ["前置准备", "setup"],
            "is_setup": 1, "setup_token": setup_token, "depends_on": [],
        }

        out = [setup]
        affected = 0
        for ci, c in enumerate(cases):
            if not isinstance(c, dict):
                out.append(c); continue
            if top not in prep_of_case[ci]:
                out.append(c); continue
            # 命中共享准备 → 静态化前置 + 挂 depends_on
            kept = [cl for cl in clauses_map[ci] if norm(cl) != top]
            new_c = dict(c)
            if kept:
                new_c["preconditions"] = "; ".join(kept)
            else:
                new_c["preconditions"] = f"已登录系统并进入{clean_module_name(c.get('module') or module)}页面"
            dep = list(new_c.get("depends_on") or [])
            if setup_token not in dep:
                dep.append(setup_token)
            new_c["depends_on"] = dep
            out.append(new_c)
            affected += 1

        logger.info(f"[Setup] 识别到共享准备「{clean_orig[:24]}」→ 生成 1 条前置准备用例；"
                    f"{affected} 条卡片用例 depends_on 指向它")
        return out

    def _is_garbage_case(self, tc: Any) -> bool:
        """判该条是否 JSON 解析/截断产生的垃圾（title 非真实功能名）。

        LLM 坏 JSON 经 _fix_unclosed_json 等截断会抠出如 `1.8.0",` 的残片当 title，
        这类必须丢弃，避免污染用例列表。"""
        if not isinstance(tc, dict):
            return True
        import re as _re
        t = (tc.get("title") or tc.get("name") or "").strip()
        if not t:
            return True
        if '"' in t or "," in t:
            return True
        if len(t) < 3:
            return True
        # 纯数字/版本号/标点残片（如 "1.8.0"）
        if _re.fullmatch(r"[\d\s.、,·:：]+", t):
            return True
        return False

    def _parse_got_cases(self, llm_response: str) -> list:
        """解析单批 LLM 输出为"干净"用例列表：过滤 JSON 截断/修复产生的垃圾条目。

        返回可能为空的干净 list（调用方据此决定是否重试/拆半）。"""
        cases = []
        parsed = self._parse_llm_response(llm_response)
        if parsed and parsed.get("test_cases"):
            cases = list(parsed["test_cases"])
        if not cases:
            partial = self._extract_partial_cases_from_response(llm_response)
            if partial:
                cases = list(partial)
        return [c for c in cases if not self._is_garbage_case(c)]

    def _process_test_steps(self, test_steps: List[Any], module: str = "") -> List[Dict[str, Any]]:
        """处理测试步骤，统一为 [{step, action, expected}] 格式

        LLM 返回的格式可能是：
        - [{"step_no": 1, "action": "...", "expected_result": "..."}]
        - [{"step": 1, "action": "...", "expected": "..."}]
        - ["步骤1: 操作...", "步骤2: 操作..."]

        统一输出：每步保留 step/action/expected 三个字段
        落库前对象标记净化（2026-09-03 审计 P1-3）：把 LLM/Step1 塞进「」的整条菜单枚举
        （含换行/超长）裁剪为单对象，杜绝下游 step_parser/探索按整串定位乱跑。
        module：当前用例所属模块名，净化整串菜单时优先取含模块核心词的候选
        （“患者档案模块”的整串 → 裁到「患者档案」而非菜单首项“工作台”）。
        """
        import re as _re_clean

        # 提取模块名的核心词（去“模块/管理/中心/页面/列表/工作台”等通用词缀），用于候选匹配
        _mod_hint = ""
        if module:
            _mz = _re_clean.sub(r"模块|管理|中心|页面|列表|工作台|配置|设置", "", module).strip()
            _mz = _mz.strip(":：- ")
            _mod_hint = _mz[:6]

        def _clean_action_markers(a):
            if not a:
                return a

            def _fix(m):
                inner = m.group(1)
                # 触发裁剪仅限“容器/枚举”信号：含换行（整块多元素）或含多个候选分隔符
                # （顿号/逗号/竖线 = 枚举了多个对象）。纯长的单对象文本（如一句长描述）
                # 不裁，避免误伤合法对象名——净化只针对“把整条菜单/多对象塞进一个「」”。
                if ("\n" in inner or "\r" in inner) or len(_re_clean.findall(r"[、，,|]", inner)) >= 1:
                    flat = inner.replace("\n", " ").replace("\r", " ").strip()
                    parts = [p for p in _re_clean.split(r"[\s、，,|/]+", flat) if p.strip()]
                    cand = ""
                    if _mod_hint and parts:
                        for p in parts:
                            if _mod_hint in p or p in _mod_hint:
                                cand = p
                                break
                    if not cand and parts:
                        cand = parts[0]
                    if not cand:
                        cand = flat
                    return "「" + cand.strip()[:20] + "」"
                return m.group(0)

            try:
                return _re_clean.sub(r"「([^」]*)」", _fix, a)
            except Exception:
                return a

        def _clean_step(s):
            if isinstance(s, dict):
                a = s.get("action", "") or s.get("desc", "")
                ns = dict(s)
                ns["action"] = _clean_action_markers(a)
                return ns
            if isinstance(s, str):
                return _clean_action_markers(s)
            return s

        if not test_steps:
            return []
        test_steps = [_clean_step(s) for s in test_steps]

        processed = []
        for i, step in enumerate(test_steps, 1):
            if isinstance(step, dict):
                action = step.get("action", "") or step.get("desc", "")
                expected = step.get("expected_result") or step.get("expected") or step.get("expect", "")
                processed.append({
                    "step": i,
                    "action": action,
                    "expected": expected,
                })
            elif isinstance(step, str):
                # 纯文本步骤：尝试拆分 "操作 → 预期"
                if "→" in step:
                    parts = step.split("→", 1)
                    processed.append({
                        "step": i,
                        "action": parts[0].strip(),
                        "expected": parts[1].strip(),
                    })
                else:
                    processed.append({
                        "step": i,
                        "action": step,
                        "expected": "",
                    })
            else:
                processed.append(str(step))

        return processed

