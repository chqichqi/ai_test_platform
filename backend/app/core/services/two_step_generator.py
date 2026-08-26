"""
两步生成法：Step1 提取特征 → Step2 逐一生成用例
"""
import json as _json
import logging

logger = logging.getLogger(__name__)

STEP1_SYSTEM_PROMPT = """你是需求分析专家。请仔细阅读以下业务需求文档，用Chain-of-Thought方法逐步分析：

第一步：全局分析，确定测试策略：
- 文档描述的功能点默认都需要测试。区分：
  - 确定性功能（文档明确列出）→ 生成测试用例
  - 条件性功能（权限/数据决定是否可见）→ 先生成存在性判断步骤，存在则测试，不存在则标记
  - 数据为空场景 → 是有效边界测试，不是skip。筛选后显示"暂无数据"是PASS
- 测试顺序：先确保被测数据存在（添加/准备）→ 再逐个测试 → 最后恢复（清理）

第二步：列出文档中提到的所有功能点。包括：
- 每个卡片（表格中「包含卡片」列的每一项——用"/"分隔的每个值都是独立卡片）
- 每个筛选规则（下拉选项的每个具体值）
- 每个BIZ/MUST规则（编号+描述）
- 每个自定义操作（添加/移除/保存）
- 每个边界场景

第二步：将以上功能点整理为结构化JSON。

输出格式（纯JSON）：
{"module": "从文档标题提取的模块名", "features": [
  {"key": "功能点标识(模块-名称, 无空格, 用于去重)", "name": "功能点名称(简洁)", "category": "指标跳转|筛选|规则|预警|自定义|边界", "detail": "具体描述"}
]}

每个功能点=独立feature。不要合并、不要省略。直接输出JSON。"""


async def extract_features(llm_service, requirement_text: str) -> dict:
    """Step1: LLM + CoT 提取结构化特征列表"""
    llm_config = llm_service.get_active_config()
    if not llm_config:
        logger.warning("[Step1] 无LLM配置，回退到空特征")
        return {"module": "通用模块", "features": []}

    user_prompt = f"请分析以下业务需求文档，提取所有功能点：\n\n{requirement_text[:20000]}"

    try:
        response = await llm_service.async_call_llm(
            prompt=user_prompt,
            system_prompt=STEP1_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=min(llm_config.max_tokens or 8192, 16000),
            json_mode=True,   # Step1 需要结构化JSON输出
        )
        if not response:
            raise ValueError("LLM返回空")

        # 解析JSON
        content = response.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
        result = _json.loads(content)
        features = result.get("features", [])
        module = result.get("module", "通用模块")

        logger.info(f"[Step1] 提取到 {len(features)} 个功能点, 模块: {module}")
        return {"module": module, "features": features}

    except Exception as e:
        logger.warning(f"[Step1] 特征提取失败(回退正则): {e}")
        return {"module": "通用模块", "features": []}


def build_step2_prompt(project_name: str, version_number: str,
                       module: str, features: list, content: str) -> str:
    """构建Step2的user_prompt，将特征列表注入（严格 1:1 约束）。"""
    if features:
        n = len(features)
        feature_lines = [f"共 {n} 个功能点（必须恰好生成 {n} 条用例，编号 TC001 到 TC{n:03d}）："]
        for i, f in enumerate(features, 1):
            name = f.get("name", f"功能{i}")
            cat = f.get("category", "")
            detail = f.get("detail", "")
            feature_lines.append(f"  {i}. [{cat}] {name}: {detail}")
        feature_text = "\n".join(feature_lines)
        return (
            f"项目：{project_name}，版本：{version_number}\n\n"
            f"模块：{module}\n\n"
            f"{feature_text}\n\n"
            f"需求原文参考：\n{content[:10000]}\n\n"
            f"重要约束：\n"
            f"  1. 共 {n} 个功能点 → 必须恰好输出 {n} 条用例（不允许多，不允许少）\n"
            f"  2. 每条用例聚焦该功能点的核心操作场景\n"
            f"  3. 编号从 TC001 到 TC{n:03d}\n"
            f"  4. test_steps 中每条 action 必须遵循 UI 元素命名约定（「」标记元素，\"\" 标记值，验证：开头）\n\n"
            f"输出格式（严格按照以下 JSON 结构，直接输出，不要 markdown 代码块）：\n"
            f'{{"test_cases": [\n'
            f'  {{"id": "TC001", "title": "验证室早卡片点击跳转-正常", "module": "{module}",\n'
            f'    "priority": "P1", "test_type": "positive",\n'
            f'    "preconditions": ["已登录系统, 进入{module}页面"],\n'
            f'    "test_steps": [\n'
            f'      {{"step_no": 1, "action": "点击「室早」卡片", "expected_result": "跳转到患者档案页面"}},\n'
            f'      {{"step_no": 2, "action": "验证：页面URL包含patient-profile", "expected_result": "URL正确"}}\n'
            f'    ],\n'
            f'    "expected_result": "成功跳转并验证页面",\n'
            f'    "tags": ["跳转", "卡片"]\n'
            f'  }},\n'
            f'  ...(共{n}条, 编号 TC001 到 TC{n:03d})\n'
            f']}}'
        )
    else:
        return (
            f"项目：{project_name}，版本：{version_number}\n\n"
            f"需求文档：\n{content}\n\n"
            f"模块：{module}\n\n"
            f"为每个功能点生成1条用例。输出纯JSON。"
        )


def diff_features(old_features: list, new_features: list) -> dict:
    """结构化 diff：按 feature.key 比较新旧功能点（机器驱动, 不依赖 LLM）。

    Returns:
        {"added": [...], "removed": [...], "unchanged": [...], "stats": {...}}
    """
    old_by_key = {f.get('key', ''): f for f in old_features if f.get('key')}
    new_by_key = {f.get('key', ''): f for f in new_features if f.get('key')}
    old_keys, new_keys = set(old_by_key), set(new_by_key)
    return {
        "added": [new_by_key[k] for k in (new_keys - old_keys)],
        "removed": [old_by_key[k] for k in (old_keys - new_keys)],
        "unchanged": [{"old": old_by_key[k], "new": new_by_key[k]} for k in (old_keys & new_keys)],
        "unchanged_keys": list(old_keys & new_keys),
        "stats": {
            "old_total": len(old_features), "new_total": len(new_features),
            "added": len(new_keys - old_keys), "removed": len(old_keys - new_keys),
            "unchanged": len(old_keys & new_keys),
        }
    }
