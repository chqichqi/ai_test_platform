"""UI 功能用例前置条件编译器。

把功能用例中的自然语言前置条件编译成稳定的 JSON 数据契约。
重点支持：
- 已登录/页面位置
- 动态数据存在性：A 或 B 有数据、且不是“暂无数据”
- 空数据时跳过用例

该模块不负责执行，只负责把业务语义变成可执行的 plan；执行由 StepRunner 完成。
"""
import re
from typing import Any, Dict, List

_EMPTY_RE = re.compile(r"(?:无|暂无|没有|不存在|未找到|未发现|为空|空白|空列表)[^，。；;|\n]*数据|暂无数据|无数据|没有数据|数据为空")

# 只用于识别中文业务短语，不绑定具体项目页面。
_DYNAMIC_PATTERNS = [
    re.compile(r"存在(?:任一|任意一个|至少一个)?(.+?)(?:且|，|,|$)"),
    re.compile(r"有(?:任一|任意一个|至少一个)?(.+?)(?:且|，|,|$)"),
    re.compile(r"包含(?:任一|任意一个|至少一个)?(.+?)(?:且|，|,|$)"),
]

_STOP = {
    "卡片", "页面", "数据", "记录", "内容", "项目", "信息",
    "且", "并且", "同时", "时", "后", "才能", "可以", "可",
}


def _clean_target(text: str) -> str:
    text = re.sub(r"[「」『』【】\[\]]", "", text or "").strip()
    text = re.sub(r"^(存在|有|包含)\s*", "", text)
    text = re.sub(r"^(任一|任意一个|至少一个|一个|任意)\s*", "", text)
    text = re.sub(r"(卡片|数据项|项目)$", "", text).strip()
    return text


def _extract_targets(text: str) -> List[str]:
    """提取动态数据目标，优先识别带「」的 UI 标题。"""
    quoted = re.findall(r"[「『【]([^」』】]+)[」』】]", text or "")
    targets: List[str] = []
    for q in quoted:
        q = _clean_target(q)
        # 「暂无数据」属于空态指示词，不是动态数据区目标。
        if any(x in q for x in ("暂无数据", "无数据", "数据为空", "空列表")):
            continue
        if q and q not in targets and q not in _STOP:
            targets.append(q)

    # “佩戴或测量预警卡片”这种未加引号的业务表达。
    m = re.search(r"([\u4e00-\u9fffA-Za-z0-9_-]+?)\s*(?:或|或者)\s*([\u4e00-\u9fffA-Za-z0-9_-]+?)(?:卡片|数据|项|标题)?(?:且|，|,|$)", text or "")
    if m:
        parts = [_clean_target(x) for x in m.groups()]
        # 中文业务表达常省略第二个对象的共同后缀：
        # “佩戴或测量预警卡片”实际表示“佩戴预警/测量预警”。
        suffixes = ("预警", "告警", "异常", "消息", "任务", "记录")
        for suffix in suffixes:
            if len(parts) == 2 and parts[1].endswith(suffix) and not parts[0].endswith(suffix):
                parts[0] += suffix
                break
        for t in parts:
            if t and t not in targets and t not in _STOP:
                targets.append(t)

    if targets:
        return targets

    for p in _DYNAMIC_PATTERNS:
        m = p.search(text or "")
        if not m:
            continue
        raw = m.group(1)
        # 如果是“佩戴预警或测量预警”，拆成两个 section。
        parts = re.split(r"\s*(?:或|或者)\s*", raw)
        for part in parts:
            t = _clean_target(part)
            if t and t not in targets and t not in _STOP:
                targets.append(t)
        if targets:
            break
    return targets


def compile_precondition_plan(preconditions: str, module: str = "") -> Dict[str, Any]:
    raw = (preconditions or "").strip()
    plan: Dict[str, Any] = {
        "schema_version": 1,
        "raw_text": raw,
        "conditions": [],
        "skip_policy": "never",
    }
    if not raw:
        return plan

    low = raw.lower()
    if any(x in raw for x in ("已登录", "登录系统", "登录成功", "有效登录")):
        plan["conditions"].append({"type": "auth", "required": True, "description": "需要有效登录态"})

    # 页面位置只是结构化信息，不在这里自动执行导航；导航仍由 UI steps 负责。
    page_terms = re.findall(r"(?:进入|位于|在|回到|返回)([^，。；;\s]+?)(?:页面|页)(?=[，。；;\s]|$)", raw)
    for p in page_terms:
        p = p.strip()
        if p:
            plan["conditions"].append({"type": "page", "page": p, "required": True})

    # “有数据/存在数据/且无暂无数据”是动态数据守卫。
    dynamic_hint = any(k in raw for k in ("有数据", "存在", "数据", "暂无数据", "无数据", "才能点击", "才可点击"))
    if dynamic_hint:
        targets = _extract_targets(raw)
        empty_indicators = re.findall(r"[「『【]([^」』】]*(?:暂无数据|无数据|为空|空列表)[^」』】]*)[」』】]", raw)
        if not empty_indicators:
            if "暂无数据" in raw:
                empty_indicators.append("暂无数据")
            if "无数据" in raw:
                empty_indicators.append("无数据")
        if targets:
            cond = {
                "type": "dynamic_data",
                "match": "any" if len(targets) > 1 else "single",
                "targets": [{"section": t} for t in targets],
                "empty_indicators": list(dict.fromkeys(empty_indicators or ["暂无数据", "无数据"])),
                "skip_when_empty": True,
                "required": True,
                "description": "至少一个目标数据区存在可操作数据",
            }
            plan["conditions"].append(cond)
            plan["skip_policy"] = "dynamic_data_empty"

    plan["metadata"] = {"module": module or "", "compiler": "ui_precondition_plan_v1"}
    return plan


def get_dynamic_conditions(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in (plan or {}).get("conditions", []) if isinstance(c, dict) and c.get("type") == "dynamic_data"]
