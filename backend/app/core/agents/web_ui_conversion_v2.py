"""
WebUI测试转换 V2 — POM + JSON 数据驱动模式

符合 SKILL spec v2.0:
- POM page classes 从知识图谱生成
- JSON 数据驱动步骤定义
- StepRunner 执行引擎
- 反模式规则检查

Usage:
    result = convert_functional_to_web_ui_v2(db, test_case_id, base_url, ...)
"""

import json
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.models.knowledge_graph import KnowledgeGraph
from app.core.models.web_ui_test import WebUITestCase
from app.core.logger import logger


def convert_functional_to_web_ui_v2(
    db,
    test_case_id: str,
    base_url: str,
    browser: str = "chromium",
    viewport_size: str = "1920x1080",
    headless: bool = True,
    script_type: str = "playwright",
    script_language: str = "python",
    project_id: int = None,
    page_objects: Dict[str, str] = None,   # 预生成的 POM（批量转化时共享，避免重复 LLM 调用）
    kg_data: Dict[str, Any] = None,         # 预加载的 KG 数据（批量转化时共享）
    cancel_check=None,                       # callable → bool, 返回 True 表示客户端已断开
) -> Dict[str, Any]:
    """
    AI驱动的功能→WebUI测试转换 (POM + JSON 数据驱动模式)

    产出格式符合 SKILL spec v2.0:
    - POM page classes (pages/)
    - JSON 数据驱动步骤定义 (tests/)
    - conftest.py + step_runner.py
    """
    from app.core.models.requirement import TestCase as ReqTestCase
    from app.core.models.test_simple import SimpleTestCase
    from app.core.services.llm_service import LLMService
    from app.core.services.pom_generator import generate_pom_classes

    # 1. 获取功能测试用例
    test_case = _load_test_case(db, test_case_id)
    if not test_case:
        return {"success": False, "error": "功能测试用例不存在"}

    # 1.5 检查项目类型
    if project_id:
        from app.core.models.project import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if project and project.project_type == "app":
            return {"success": False, "error": "APP端项目暂不支持转为 WebUI 自动化脚本"}

    # 2. 提取测试步骤
    case_name = getattr(test_case, 'name', None) or getattr(test_case, 'title', '未命名')
    case_desc = test_case.description or ""
    preconditions = getattr(test_case, 'preconditions', '') or ''
    module = getattr(test_case, 'module', '') or '通用'
    steps = _normalize_steps(test_case)

    # 3. 查询知识图谱 + 生成 POM（知识图谱是项目级资产，不按版本过滤——
    #    用例挂任何版本都应命中项目唯一 KG）
    llm_service = LLMService(db)

    if kg_data is None:
        kg_data = _load_knowledge_graph(db, project_id)

    # ── 取消检查：每步昂贵操作前检查 ──
    if cancel_check and cancel_check():
        return {"success": False, "error": "取消: 客户端已断开", "cancelled": True}

    if page_objects is None:
        page_objects = generate_pom_classes(
            exploration_data=kg_data,
            base_url=base_url,
            llm_service=llm_service,
            cancel_check=cancel_check,
        )

    # 4. 构建 LLM prompt — 生成 JSON 数据驱动步骤
    # 页面 URL 映射（prompt 注入 + 落库前补全共用）：goto 数据唯一来源，
    # 历史根因——prompt 无任何页面 URL，LLM 只能编造（goto locator / #/login）
    page_url_map, start_url = _build_page_url_map(kg_data, base_url)
    prompt = _build_generation_prompt(
        case_name, case_desc, preconditions, module,
        steps, page_objects, kg_data, base_url,
        page_url_map=page_url_map, start_url=start_url,
    )

    # ── 取消检查 ──
    if cancel_check and cancel_check():
        return {"success": False, "error": "取消: 客户端已断开", "cancelled": True}

    # 5. 调用 LLM
    try:
        llm_response = llm_service.call_llm(
            prompt=prompt,
            system_prompt="你是WebUI自动化测试专家。根据功能和探索数据生成JSON数据驱动的Pytest测试步骤。只输出JSON，不要markdown。",
            max_tokens=llm_service.get_scaled_max_tokens(),
            cancel_check=cancel_check,
        )
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        return _fallback_to_rules(
            db, test_case_id, case_name, steps,
            base_url, browser, viewport_size, headless,
            script_type, script_language, page_objects,
            project_id=project_id,
        )

    # 6. 解析 JSON 测试定义（preconditions 随用例原文落 test_data——执行器前置条件导航信息来源）
    test_spec = _parse_json_spec(llm_response, case_name, steps, module, preconditions)
    # 将功能用例的数据契约透传到 UI 用例。LLM 只负责步骤，不负责产生运行时数据。
    try:
        from app.core.services.test_data_manager import TestDataManager
        _tdm = TestDataManager(db)
        _td_plan = _tdm.build_plan(test_case)
        test_spec["test_data"] = {"data_plan": _td_plan.to_dict(), "preconditions": preconditions or ""}
    except Exception as _td_e:
        logger.warning(f"[ConvertV2] 测试数据计划透传失败: {_td_e}")
    # F30（2026-08-25）：LLM 响应解析失败 → 回退 spec 是纯等待占位（什么都没测）。
    # 显式上报 warning 而非静默成功，防止用户看到「转化成功」的假象。
    _parse_fallback = bool(test_spec.get("parse_fallback"))
    if _parse_fallback:
        logger.warning(f"[ConvertV2] 用例 '{case_name}' LLM 响应解析失败，回退为等待渲染步骤"
                       f"（未产出实际操作断言），请检查 LLM 返回质量")
    # 6.1 结构化前置条件 + 动态数据语义校验：先编译，再把 guard/动态点击写入 spec。
    precondition_plan = _build_precondition_plan(preconditions, module)
    test_spec = _enrich_and_sanitize_ui_steps(test_spec, precondition_plan, kg_data)

    # 6.2 goto 步骤有效性校验/补全（LLM 不遵守约束时兜底修正，防坏步骤落库）
    test_spec = _sanitize_spec_steps(test_spec, page_url_map=page_url_map, start_url=start_url)

    # 7. 生成完整的 pytest 项目文件
    from app.core.services.step_runner import build_pytest_project
    project_files = build_pytest_project(
        page_objects=page_objects,
        test_specs=[test_spec],
        project_name=re.sub(r'[^a-zA-Z0-9_]', '_', case_name)[:50],
        base_url=base_url,
    )

    # 8. 保存到数据库
    saved = _save_result(
        db, test_case_id, test_spec, page_objects,
        base_url, browser, viewport_size, headless,
        script_type, script_language,
        project_id=project_id,
    )

    return {
        "success": True,
        "test_case_id": str(test_case_id),
        "case_name": case_name,
        "test_spec": test_spec,
        "page_objects": page_objects,
        "project_files": project_files,
        "saved_to_db": saved,
        "script_type": script_type,
        "script_language": script_language,
        # F30（2026-08-25）：LLM 响应解析失败回退标记——调用方据此向上报告 warning，
        # 不再静默产出「纯等待渲染」的空用例（用例显示成功但什么都没测）
        "parse_fallback": _parse_fallback,
    }


# ═══════════════════════════════════════════════════════════
# Step 1-2: Data loading
# ═══════════════════════════════════════════════════════════

def _load_test_case(db, test_case_id: str):
    """加载功能测试用例（兼容两种模型；ReqTestCase 按【生效行】解析——方案B 逻辑 id 绑定）"""
    from app.core.models.requirement import TestCase as ReqTestCase
    from app.core.models.test_simple import SimpleTestCase
    from app.core.services.case_versioning import load_effective_case

    try:
        int(test_case_id)
    except ValueError:
        return db.query(SimpleTestCase).filter(SimpleTestCase.id == test_case_id).first()
    return load_effective_case(db, test_case_id)


def _load_knowledge_graph(db, project_id: int, version_id: int = None) -> Dict[str, Any]:
    """加载知识图谱数据。知识图谱是项目级资产（UNIQUE(project_id)），
    version_id 参数保留仅为兼容旧调用，不再参与过滤。"""
    if not project_id:
        return {}

    from app.core.models.knowledge_graph import ExplorationPageSnapshot

    query = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.project_id == project_id,
        KnowledgeGraph.exploration_status == "completed"
    )
    kg = query.order_by(KnowledgeGraph.completed_at.desc()).first()
    if not kg:
        return {}

    pages = kg.pages if isinstance(kg.pages, list) else []
    elements = kg.elements if isinstance(kg.elements, list) else []
    tables = kg.tables if isinstance(kg.tables, list) else []
    dropdowns = getattr(kg, 'dropdowns', {}) or {}
    modals = getattr(kg, 'modals', []) or []

    # 兜底：如果 KG 主表为空，从 ExplorationPageSnapshot 合并
    if not elements and not pages:
        snapshots = db.query(ExplorationPageSnapshot).filter(
            ExplorationPageSnapshot.graph_id == kg.id
        ).all()
        for snap in snapshots:
            if snap.elements and isinstance(snap.elements, list):
                elements.extend(snap.elements)
            if snap.page_url:
                pages.append(snap.page_url)
            if snap.operations and isinstance(snap.operations, list):
                modals.extend(snap.operations)
            # 从 dom_snapshot 恢复完整数据
            dom = getattr(snap, 'dom_snapshot', None)
            if isinstance(dom, str):
                try:
                    full = json.loads(dom)
                    if isinstance(full.get("filter_options"), dict):
                        dropdowns.update(full["filter_options"])
                    if isinstance(full.get("tables"), list):
                        tables.extend(full["tables"])
                except json.JSONDecodeError:
                    pass

    return {
        "pages": pages,
        "menus": kg.menus or [],
        "flows": kg.flows or [],
        "elements": elements,
        "dropdowns": dropdowns,
        "tables": tables,
        "modals": modals,
    }


def _normalize_steps(test_case) -> List[dict]:
    """标准化测试步骤为 [{seq, action, expected}]"""
    raw = test_case.test_steps
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [{"seq": 1, "action": raw, "expected": ""}]
    if not isinstance(raw, list):
        return []

    result = []
    for i, s in enumerate(raw):
        if isinstance(s, dict):
            result.append({
                "seq": s.get("seq", s.get("step", i + 1)),
                "action": s.get("action", s.get("desc", s.get("description", ""))),
                "expected": s.get("expected", s.get("expected_result", "")),
            })
        elif isinstance(s, str):
            result.append({"seq": i + 1, "action": s, "expected": ""})
    return result


# ═══════════════════════════════════════════════════════════
# Step 4: Prompt building
# ═══════════════════════════════════════════════════════════

def _build_url_prompt_sections(page_url_map: Optional[Dict[str, str]], start_url: str, pom_keys: str) -> str:
    """页面 URL 映射/起始页/POM key 三段 prompt 文本——单条与批量转化共用（同源防漂移）。

    批量路径（_convert_batch_v2）注入同一段，避免批量 LLM 再次编造 goto
    （2026-08-24 审计 H1：批量 prompt 无 URL 注入 → 根因在批量路径原样存在）。
    """
    page_urls_summary = "\n".join(
        f"- {k}: {v}" for k, v in (page_url_map or {}).items()
    ) or "（无可用页面 URL 数据，goto 用 args.page）"
    return f"""## 页面 URL 映射（goto args.url 的唯一取值来源）
{page_urls_summary}

## 起始页（登录后落地页，「返回起始页」步骤的固定目标）
{start_url or '（无——禁止编造 URL，此时「返回起始页」步骤不要输出 goto）'}

## 可用的 POM 页面 key（goto args.page 仅允许这些值）
{pom_keys}"""


def _build_precondition_plan(preconditions: str, module: str = "") -> Dict[str, Any]:
    """统一编译功能用例前置条件；不让 LLM 独自决定动态数据 Skip 语义。"""
    from app.core.services.ui_precondition_plan import compile_precondition_plan
    return compile_precondition_plan(preconditions or "", module=module)


def _dynamic_section_names(precondition_plan: Dict[str, Any]) -> List[str]:
    names = []
    for cond in (precondition_plan or {}).get("conditions", []):
        if not isinstance(cond, dict) or cond.get("type") != "dynamic_data":
            continue
        for target in cond.get("targets", []):
            if isinstance(target, str): name = target
            elif isinstance(target, dict): name = target.get("section", "")
            else: name = ""
            if name and name not in names: names.append(name)
    return names


def _is_same_ui_text(a: str, b: str) -> bool:
    def n(x):
        return re.sub(r"[\s「」『』【】\\[\\]（）()\"'“”‘’]", "", str(x or "")).lower()
    return bool(n(a) and n(a) == n(b))


def _enrich_and_sanitize_ui_steps(spec: Dict[str, Any], precondition_plan: Dict[str, Any], kg_data: Dict[str, Any]) -> Dict[str, Any]:
    """把结构化动态前置条件编译成执行步骤，并阻止标题/静态元素被点击。

    规则：
    1. dynamic_data 必须在第一个业务操作前执行 guard；
    2. click 的目标如果恰好是动态 section 标题，改成 click_dynamic_item；
    3. KG 明确 clickable=false/role=heading 的目标禁止生成普通 click；
    4. guard 失败由 StepRunner 返回 skipped，不计为 failed。
    """
    steps = spec.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    sections = _dynamic_section_names(precondition_plan)
    conditions = [c for c in (precondition_plan or {}).get("conditions", []) if isinstance(c, dict)]
    dyn = next((c for c in conditions if c.get("type") == "dynamic_data"), None)
    fixed = []

    if dyn and dyn.get("skip_when_empty") and sections:
        guard = {
            "seq": 0,
            "action": "guard_dynamic_data",
            "desc": "动态数据前置检查：无数据时跳过本用例",
            "args": {
                "sections": sections,
                "match": dyn.get("match", "any"),
                "empty_indicators": dyn.get("empty_indicators") or ["暂无数据", "无数据"],
            },
        }
        # 避免重复插入
        if not any((s.get("action") == "guard_dynamic_data") for s in steps if isinstance(s, dict)):
            fixed.append(guard)

    # 建立 KG 目标索引：同名目标优先使用可信 evidence 元素。
    elem_index = {}
    all_elements = []
    if isinstance(kg_data, dict):
        all_elements.extend(kg_data.get("elements", []) or [])
        for page in kg_data.get("pages", []) or []:
            if isinstance(page, dict): all_elements.extend(page.get("elements", []) or [])
    for e in all_elements:
        if not isinstance(e, dict): continue
        name = e.get("name") or e.get("element_name") or e.get("text") or ""
        if name:
            elem_index.setdefault(str(name), []).append(e)

    for s in steps:
        if not isinstance(s, dict): continue
        action = s.get("action") or ""
        args = s.get("args") if isinstance(s.get("args"), dict) else {}
        locator = args.get("locator") or args.get("text") or args.get("label") or ""
        if action == "click":
            # 动态 section 标题不可点击：点击 section 内真实数据项。
            section = next((sec for sec in sections if _is_same_ui_text(locator, sec) or _is_same_ui_text(s.get("desc", ""), sec)), None)
            if section:
                s["action"] = "click_dynamic_item"
                s["desc"] = f"点击「{section}」数据中的可操作患者/数据项"
                s["args"] = {
                    "section": section,
                    "item_role": "link",
                    "empty_indicators": (dyn or {}).get("empty_indicators") or ["暂无数据", "无数据"],
                }
                fixed.append(s)
                continue

            # 如果 KG 明确知道该文本是 heading/static，则不要生成 click。
            matches = elem_index.get(str(locator), [])
            bad = any((e.get("clickable") is False or e.get("role") in ("heading", "static", "paragraph", "table")) for e in matches)
            good = any(e.get("clickable") is True or e.get("role") in ("button", "link", "tab", "menuitem") for e in matches)
            if bad and not good:
                s["action"] = "assert_visible"
                s["desc"] = f"验证「{locator}」可见（该元素为静态标题，不执行点击）"
                s["args"] = {"locator": locator}
                fixed.append(s)
                continue
        fixed.append(s)

    for i, s in enumerate(fixed, 1):
        if isinstance(s, dict): s["seq"] = i
    spec["steps"] = fixed
    spec["precondition_plan"] = precondition_plan
    spec.setdefault("metadata", {})["precondition_compiler"] = "ui_precondition_plan_v1"
    if dyn:
        spec["metadata"]["dynamic_data_policy"] = "skip_when_empty"
    return spec


def _build_generation_prompt(
    case_name, case_desc, preconditions, module,
    steps, page_objects, kg_data, base_url,
    page_url_map: Optional[Dict[str, str]] = None,
    start_url: str = "",
) -> str:
    """构建 JSON 数据驱动生成 prompt

    2026-08-24 生成根因修复：历史 prompt 从不注入页面 URL（base_url/KG pages 的
    page_url 均未进 prompt）→ LLM 无法生成有效 goto，输出 goto(locator=XX) 或
    编造 goto(#/login)（批量执行 21:16 实证）。现在注入：
    - 页面 URL 映射（中文模块名+英文路由名 → 规范化 URL，goto args.url 唯一来源）
    - 起始页 URL（登录后落地页，「返回起始页」步骤固定目标）
    - POM 页面 key 列表（goto args.page 白名单）
    """

    steps_text = "\n".join([
        f"步骤 {s['seq']}: {s['action']} → 预期: {s['expected']}"
        for s in steps
    ]) if steps else "（无具体步骤）"

    pom_signatures = _summarize_pom_methods(page_objects)
    elements_summary = _summarize_elements(kg_data)
    dropdowns_summary = _summarize_dropdowns(kg_data)
    modals_summary = _summarize_modals(kg_data)
    anti_rules = _get_anti_pattern_rules()
    pom_keys = "、".join(page_objects.keys()) if page_objects else "（无）"
    url_sections = _build_url_prompt_sections(page_url_map, start_url, pom_keys)
    precondition_plan = _build_precondition_plan(preconditions, module)
    precondition_plan_text = json.dumps(precondition_plan, ensure_ascii=False, indent=2)

    return f"""你是WebUI自动化测试专家。将功能测试用例转换为 JSON 数据驱动测试步骤。

## 功能测试用例
- 名称: {case_name}
- 描述: {case_desc}
- 前置条件: {preconditions or '无'}
- 模块: {module}

## 结构化前置条件（系统编译结果，优先级高于自然语言）
{precondition_plan_text}

动态数据规则：若 dynamic_data.skip_when_empty=true，必须把动态数据检查放在所有业务操作之前；检查不到数据时必须返回 skipped，禁止继续点击标题。

## 测试步骤
{steps_text}

## 可用的 POM 方法（按页面）
{pom_signatures}

{url_sections}

## 目标系统页面元素
{elements_summary}

## 可用的下拉筛选控件及选项
{dropdowns_summary}

## 已发现的弹窗
{modals_summary}

## 硬约束 — 必须遵守
{anti_rules}

## 输出格式（只输出 JSON，不要 markdown 标记）

每个步骤必须包含 action、desc、args（含 locator 用于定位元素）。

{{
  "case_id": "TC-{module}-N",
  "title": "用例标题",
  "module": "{module}",
  "preconditions": "前置条件原文（原样透传上方「前置条件」内容，没有则填空字符串）",
  "steps": [
    {{"seq": 1, "action": "click", "desc": "点击「新增」按钮", "args": {{"locator": "新增"}}}},
    {{"seq": 2, "action": "assert_visible", "desc": "确认弹窗可见", "args": {{"locator": "新增患者"}}}},
    {{"seq": 3, "action": "click", "desc": "点击确定", "args": {{"locator": "确定"}}}}
  ]
}}

## 硬约束（违反会导致执行失败）

### 1. action 只能用以下标准值：
交互: click, dblclick, fill, select, hover, check, press
断言: assert_visible, assert_text, assert_value, assert_url
导航: goto, go_back, reload
等待: wait_for_render, wait_for_url, wait_for_load_state
数据: get_all_items, scroll_to_bottom, skip_if_empty, guard_dynamic_data, click_dynamic_item

### 2. args 定位器（必须提供至少一种）：
  - locator: 从页面元素列表的"页面真实文本(LOCATOR)"取值 → get_by_text
  - role + locator: 按钮用 role="button", 输入框用 role="textbox", 下拉用 role="combobox"
  - placeholder: 输入框占位文本 → get_by_placeholder
  - label: 表单标签文本 → get_by_label
  - css: CSS选择器（最后手段）

### 3. locator 必须来自页面元素列表
  优先取"页面真实文本(LOCATOR)"的值（评分引擎在页面上找到的实际文本）
  示例正确: {{"action":"click","desc":"点击室早卡片","args":{{"locator":"室性早搏"}}}}
  示例正确: {{"action":"fill","desc":"输入姓名","args":{{"label":"姓名","value":"张三"}}}}
  示例正确: {{"action":"assert_url","desc":"验证跳转","args":{{"expected":"**/patient**"}}}}
  示例错误: {{"action":"click","desc":"点击室早卡片","args":{{}}}}  ← 缺locator！
  示例错误: {{"action":"click_ventricular"...}}  ← 自创action名！

### 4. select 下拉选择：
  args.locator = 下拉触发器文本, args.option = 选项文本
  示例: {{"action":"select","desc":"选择科室","args":{{"locator":"科室","option":"内科"}}}}

### 5. fill 输入填充：
  args.value = 要填入的值, args.locator/label/placeholder = 定位输入框
  示例: {{"action":"fill","desc":"输入姓名","args":{{"placeholder":"姓名","value":"张三"}}}}

### 6. goto 页面导航（前置条件导航的载体）：
  args.url **必须**从上方「页面 URL 映射」中取（禁止自己编造 URL！）
  args.page 仅允许「可用的 POM 页面 key」中的值，且只在映射无匹配时使用
  示例正确: {{"action":"goto","desc":"进入工作台","args":{{"url":"{start_url or '（映射中取，如 https://host/#/workpanel）'}"}}}}
  示例错误: {{"action":"goto","desc":"进入工作台","args":{{"locator":"工作台"}}}}  ← locator 不能导航！
  示例错误: {{"action":"goto","desc":"进入工作台","args":{{"url":"https://任意网址/#/login"}}}}  ← 登录页=登出会话！
  示例错误: {{"action":"goto","desc":"进入工作台","args":{{"url":"https://编造的地址/xx"}}}}  ← URL 不在映射里！
  「进入/打开/跳转 XX 页面」类步骤**必须**输出为 goto（不是 click 文本），
  按步骤中的页面名称（如「工作台」「指标总览-审核任务」，也支持对应英文名）在「页面 URL 映射」匹配 URL
  **若「前置条件」描述了起始页面位置（如「已登录并进入工作台」「用户位于XX页」），
  步骤序列第一条必须是 goto 步骤**（导航到该起始页，URL 从映射取）——
  执行器按用例自带导航步骤执行，不做文本解析

### 其他
  - 不要包含登录步骤
  - 不要描述"循环点击"、"逐个移除" — 当前不支持循环
  - 负向场景拆为独立用例
  - press 用 args.key = "Enter"/"Escape"/"Tab"

### 7. 动态数据/不可点击元素硬约束：
  - 「佩戴预警」「测量预警」等数据区标题不是数据项；若探索 role=heading 或 clickable=false，禁止 click。
  - 当动态数据区有数据时，点击区内真正可操作的数据项（优先 link/button/真实 click handler），不要点击 section 标题。
  - 当动态数据区为空（如「暂无数据」）时，必须由 guard_dynamic_data 直接 SKIP，不能产生定位超时。
  - 不得因为“点击卡片”字样就假定标题可点击；以探索 Evidence 的 role/clickable 为准。

### 8. 每条用例最后一步必须返回起始页：
  优先输出 {{"seq": 99, "action": "go_back", "desc": "返回起始页", "args": {{}}}}。
  禁止用 goto 起始页代替浏览器历史返回；禁止 goto 登录页。
  URL **固定取上方「起始页」的值，禁止编造、绝不使用登录页 URL（跳登录页=登出会话）**

### 其他
  - 不要包含登录步骤
  - 不要描述"循环点击"、"逐个移除"
  - 负向场景拆为独立用例
"""


def _summarize_pom_methods(page_objects: Dict[str, str]) -> str:
    """从 POM 代码中提取方法签名摘要"""
    lines = []
    for class_name, code in page_objects.items():
        methods = re.findall(r'def (\w+)\(self(?:,\s*(.+?))?\)', code)
        if methods:
            lines.append(f"\n### {class_name}")
            for method_name, params in methods:
                if method_name == "__init__":
                    continue
                lines.append(f"  - {method_name}({params or ''})")
    return "\n".join(lines) if lines else "（无可用的 POM 方法）"


def _summarize_elements(kg_data: Dict[str, Any]) -> str:
    """摘要元素列表。处理 BFS 探索的嵌套结构 [{role: [items]}, ...]

    关键约定（影响 LLM 生成准确性）：
    - locator_text 是页面上的真实文本（探索引擎通过评分找到的实际文本）
    - name/element_name 是功能用例中描述的文本（可能有「」标记残留或自然语言包装）
    - 当两者不同时（评分找到了相似匹配），LOCATOR 必须使用 locator_text
    - LLM 看到此提示后会生成正确的 get_by_text("实际文本") 调用
    """
    elements = kg_data.get("elements", [])
    for p in kg_data.get("pages", []):
        if isinstance(p, dict):
            elements.extend(p.get("elements", []))

    if not elements:
        return "（无知识图谱数据）"

    lines = []
    count = 0
    for item in elements:
        if count >= 30:
            break
        if isinstance(item, dict):
            # 步骤驱动探索格式: {"element_name": "...", "name": "...", "role": "button", ...}
            name = item.get("name", item.get("element_name", item.get("text", "")))
            role = item.get("role", item.get("type", ""))
            locator_text = item.get("locator_text", "")
            if name and role:
                role_label = {"button": "按钮", "link": "链接", "textbox": "输入框",
                              "combobox": "下拉框", "tab": "标签页", "table": "表格",
                              "heading": "标题", "static": "静态文本", "table-row": "表格行"}.get(role, role)
                clickable = item.get("clickable")
                click_label = "可点击" if clickable is True else ("不可点击" if clickable is False else "可点击性未知")
                # 当探索找到了不同的实际文本时，显式标注 LOCATOR
                if locator_text and locator_text != name:
                    lines.append(f"- [{role_label}/{click_label}] 描述名={name} | 页面真实文本(LOCATOR)={locator_text}")
                else:
                    lines.append(f"- [{role_label}/{click_label}] {name}")
                count += 1
                continue

            # BFS 探索格式: {"buttons": [...], "links": [...], ...}
            for role, items_list in item.items():
                if isinstance(items_list, list):
                    role_label = {"buttons": "按钮", "links": "链接", "inputs": "输入框",
                                  "tabs": "标签页", "cards": "卡片", "dropdowns": "下拉框"}.get(role, role)
                    for elem in items_list[:5]:
                        if count >= 30:
                            break
                        if isinstance(elem, dict):
                            name = elem.get("name", elem.get("element_name", elem.get("text", "?")))
                            selector = elem.get("selector", elem.get("css", elem.get("primary_locator", "")))
                            lt = elem.get("locator_text", "")
                            clickable = elem.get("clickable") if isinstance(elem, dict) else None
                            click_label = "可点击" if clickable is True else ("不可点击" if clickable is False else "可点击性未知")
                            if lt and lt != name:
                                lines.append(f"- [{role_label}/{click_label}] 描述名={name} | LOCATOR={lt}" + (f" ({selector})" if selector else ""))
                            else:
                                lines.append(f"- [{role_label}/{click_label}] {name}" + (f" ({selector})" if selector else ""))
                            count += 1
                        elif isinstance(elem, str):
                            lines.append(f"- [{role_label}] {elem}")
                            count += 1
        elif isinstance(item, str):
            lines.append(f"- {item}")
            count += 1

    if not lines:
        return "（知识图谱元素格式无法解析）"
    return "\n".join(lines)


def _summarize_dropdowns(kg_data: Dict[str, Any]) -> str:
    """摘要下拉筛选控件及选项"""
    dropdowns = kg_data.get("dropdowns", {})
    if not dropdowns:
        return "（无下拉筛选数据）"
    lines = []
    for name, info in dropdowns.items():
        if isinstance(info, dict):
            opts = info.get("options", [])
            if opts:
                lines.append(f"- {name}: {', '.join(str(o) for o in opts[:15])}")
            else:
                lines.append(f"- {name}（选项未知）")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines) if lines else "（无下拉筛选数据）"


def _summarize_modals(kg_data: Dict[str, Any]) -> str:
    """摘要弹窗信息"""
    modals = kg_data.get("modals", [])
    if not modals:
        return "（无弹窗数据）"
    lines = []
    for m in modals[:10]:
        if isinstance(m, dict):
            trigger = m.get("trigger", m.get("name", "?"))
            mtype = m.get("type", "?")
            lines.append(f"- {trigger} → {mtype}")
        elif isinstance(m, str):
            lines.append(f"- {m}")
    return "\n".join(lines) if lines else "（无弹窗数据）"


def _get_anti_pattern_rules() -> str:
    """获取反模式规则"""
    import os
    rules_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..",
        ".opencode", "skills", "webui-test-generation", "anti_patterns.json"
    )
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rules = data.get("generation_anti_patterns", [])
        return "\n".join([
            f"- {r['id']}: {r['pattern']}" +
            (" (禁止)" if r.get("severity") == "block" else " (警告)") +
            (f" — {r.get('reason', '')}" if r.get("reason") else "")
            for r in rules
        ])
    except Exception:
        pass
    return """- GEN001: time.sleep/wait_for_timeout (禁止)
- GEN002: CSS/XPath选择器写在步骤中 (禁止)
- GEN003: 登录步骤写在spec中 (禁止)
- GEN004: 测试无assert (禁止)
- GEN005: 硬编码测试数据值 (禁止) — 必须从页面运行时提取
- GEN006: 凭空编造元素名/选项值 (禁止)
- GEN007: 下拉选项值不在filter_options中 (禁止)
- GEN010: 过滤前不判断数据是否存在 (禁止)
- GEN011: 正负向场景未拆分 (禁止)
- GEN012: 用固定循环替代foreach (禁止)
- GEN013: foreach内使用save_as/assert (禁止)
- GEN016: 动态列表无空值判断 (禁止)"""


# ═══════════════════════════════════════════════════════════
# Step 6: Response parsing
# ═══════════════════════════════════════════════════════════

def _parse_json_spec(
    llm_response: str, case_name: str, steps: List[dict], module: str,
    preconditions: str = '',
) -> Dict[str, Any]:
    """解析 LLM 返回的 JSON 测试定义。

    preconditions：功能用例前置条件原文，写入 test_data 顶层——执行器按用例
    自身前置条件导航（通用执行语义），此字段是导航起点信息来源。
    """
    # 尝试提取 ```json ... ``` 或纯 JSON
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', llm_response, re.DOTALL)
    json_str = json_match.group(1) if json_match else llm_response.strip()

    # 去掉可能的注释/说明文本
    if json_str.startswith("{"):
        try:
            spec = json.loads(json_str)
            if "case_id" in spec and "steps" in spec:
                # LLM 未输出 preconditions 或输出空串 → 从功能用例前置条件原文补齐
                # （F31 修复 2026-08-25：setdefault 对 key 存在但值为空串不生效——
                # 与批量路径 `if not spec.get("preconditions")` 语义同源）
                if not spec.get("preconditions"):
                    spec["preconditions"] = preconditions
                return spec
        except json.JSONDecodeError:
            pass

    # 回退：构建最小化 JSON spec（LLM 解析失败的最后手段）
    # 历史缺陷：回退步骤是 goto 且无 args（page/url 皆空）→ 执行必然
    # "goto: 未知页面 '' 且无 URL"（21:17 批量执行实证）。
    # 修复：回退步骤统一转 wait_for_render（无定位依赖，保持当前页），
    # 起始导航由执行器 base_url 兜底（批量登录后=起始页）。
    logger.warning("LLM 返回格式无法解析为 JSON，使用回退格式")
    # F30 修复（2026-08-25）：回退 spec 打 parse_fallback 标记——回退步骤是纯
    # wait_for_render 无操作占位（防坏 goto 落库），若静默落库，用例显示成功但
    # 什么都没测。消费方（_convert_single）检测此标记 → 返回 warning 上报前端。
    return {
        "case_id": re.sub(r'[^a-zA-Z0-9_]', '_', case_name)[:30],
        "title": case_name,
        "module": module,
        "preconditions": preconditions,
        "parse_fallback": True,
        "steps": [
            {"seq": i + 1, "action": "wait_for_render", "args": {"ms": 500},
             "desc": (s.get("desc") if isinstance(s, dict) else "") or "等待页面渲染"}
            for i, s in enumerate(steps)
        ],
    }


def _build_page_url_map(kg_data: Dict[str, Any], base_url: str) -> Tuple[Dict[str, str], str]:
    """页面 URL 映射 + 起始页推导——生成侧 goto 数据唯一来源（prompt 注入与落库前补全共用）。

    - 映射键：page_name（英文路由名，唯一）+ module（中文模块名——功能用例步骤措辞来源，
      「进入工作台」→ 键「工作台」）。**module 键仅在模块下唯一页时绑定**：
      KG 里 module 是探索分组名，一模块常含多路由页（实测「工作台」下 8 页），
      绑定第一页=错误导航（「进入工作台」→ patientarchieve）；歧义时不猜——
      prompt 引导 LLM 用 args.page=POM key，sanitize 匹配不到则安全兜底（执行侧 base_url）
    - 排除：登录/鉴权页（goto 登录页=登出会话）、逗号分隔 module（探索叠加污染的
      「模块A, 模块B, ...」脏值）
    - 起始页：base_url 本身非登录页 → 直接用（规范化）；否则取 KG 首个非登录页面 URL
      （SPA 常见 base_url 指向 #/login，登录后落地页只能从 KG 推导）
    """
    from app.core.services.step_runner import (
        _LOGIN_PAGE_NAMES, _looks_like_login_url, _normalize_page_url,
    )

    mapping: Dict[str, str] = {}
    module_names: Dict[str, set] = {}  # module -> 名下 page_name 集合（歧义检测）
    start_url = ""
    if base_url and not _looks_like_login_url(base_url):
        start_url = _normalize_page_url(base_url, base_url)
    for p in kg_data.get("pages", []) or []:
        if not isinstance(p, dict):
            continue
        name = (p.get("page_name") or "").strip()
        url = _normalize_page_url(p.get("page_url") or "", base_url)
        if not name or not url:
            continue
        if name.lower() in _LOGIN_PAGE_NAMES or _looks_like_login_url(url):
            continue
        if name not in mapping:
            mapping[name] = url
        module = (p.get("module") or "").strip()
        if module and module != name and "," not in module:
            module_names.setdefault(module, set()).add(name)
        if not start_url:
            start_url = url
    # 模块键仅绑定「模块下唯一页」；多页歧义不猜（宁可走 args.page/POM key）
    for module, names in module_names.items():
        if len(names) == 1:
            only = next(iter(names))
            mapping.setdefault(module, mapping.get(only, ""))
    return mapping, start_url


def _match_page_url(desc: str, args, page_url_map: Optional[Dict[str, str]]) -> str:
    """按步骤描述/定位器文本匹配页面 URL 映射（中文模块名/英文路由名）。
    长键优先，防「工作台」误中「工作台-XX」类前缀。返回匹配 URL 或空串。"""
    if not page_url_map:
        return ""
    text = f"{desc} {json.dumps(args, ensure_ascii=False)}" if args else desc
    for key in sorted(page_url_map, key=len, reverse=True):
        if key and key in text:
            return page_url_map[key]
    return ""


def _sanitize_spec_steps(spec: Dict[str, Any], page_url_map: Optional[Dict[str, str]] = None,
                         start_url: str = "") -> Dict[str, Any]:
    """落库前 goto 步骤有效性校验/补全——LLM 不遵守 prompt 约束时的兜底，
    防止再产生不可执行的坏步骤（历史坏数据形态见执行侧兜底）。

    处理（与执行侧 step_runner 同源语义）：
    1. goto 无 page/url（「进入XX」→ goto(locator=XX)）→ 按 desc/locator 文本匹配
       page_url_map（中文模块名/英文路由名）补全 args.url；匹配不到 → 转 wait_for_render
    2. goto 只有 page 无 url → 映射中存在该页 → 补 args.url
       （POM navigate 内嵌 full_url 对 hash 路由项目拼接错误，显式 URL 最稳）
    3. goto 目标为登录页：返回/起始语义 → 转 go_back；其他 → 转 wait_for_render。
    """
    from app.core.services.step_runner import _looks_like_login_page, _looks_like_login_url

    steps = spec.get("steps") or []
    if not isinstance(steps, list):
        return spec
    fixed = 0
    for s in steps:
        if not isinstance(s, dict) or (s.get("action") or "") != "goto":
            continue
        args = s.get("args") or {}
        page_name = args.get("page") if isinstance(args, dict) else None
        url = args.get("url") if isinstance(args, dict) else None
        desc = str(s.get("desc") or "")

        # 1. 空导航 → 按步骤文本匹配映射补全
        if not page_name and not url:
            matched = _match_page_url(desc, args, page_url_map)
            if matched:
                s.setdefault("args", {})["url"] = matched
                logger.warning(f"[Conversion] 步骤修正: goto 补全 URL"
                               f"（desc={desc[:30]}）→ {matched[:60]}")
                fixed += 1
                continue
            s["action"] = "wait_for_render"
            s.setdefault("args", {})["ms"] = 500
            logger.warning(f"[Conversion] 步骤修正: goto 无页面名/URL（空导航）"
                           f"（desc={desc[:30]}）→ wait_for_render")
            fixed += 1
            continue

        # 2. 只有 page 无 url → 映射命中则补显式 URL（hash 路由项目 POM navigate 不可靠）
        if page_name and not url and page_url_map:
            mapped = page_url_map.get(page_name) or page_url_map.get(str(page_name).lower())
            if mapped:
                s.setdefault("args", {})["url"] = mapped
                logger.warning(f"[Conversion] 步骤修正: goto 补全 URL"
                               f"（page={page_name}）→ {mapped[:60]}")
                fixed += 1
            continue

        # 3. 登录页目标（url 与 page 双形态判定——goto(page=login) 无 url 同样登出会话，
        #    2026-08-24 审计 M1 封堵，与执行侧 _do_goto 同源）
        _page = (s.get("args") or {}).get("page") or (s.get("args") or {}).get("page_name")
        if _looks_like_login_url(url) or _looks_like_login_page(_page):
            if "返回" in desc or "起始" in desc:
                s["action"] = "go_back"
                s["args"] = {}
                logger.warning("[Conversion] 步骤修正: 返回起始页禁止 goto，改为 go_back")
            else:
                s["action"] = "wait_for_render"
                s.setdefault("args", {})["ms"] = 500
                logger.warning(f"[Conversion] 步骤修正: goto 目标为登录页（desc={desc[:30]}）→ wait_for_render")
            fixed += 1
            continue
    if fixed:
        logger.warning(f"[Conversion] goto 步骤校验修正 {fixed} 处")
    return spec


# ═══════════════════════════════════════════════════════════
# Step 8: Save to database
# ═══════════════════════════════════════════════════════════

def _save_result(
    db, test_case_id, test_spec, page_objects,
    base_url, browser, viewport_size, headless,
    script_type, script_language,
    project_id: int = None,
) -> bool:
    """保存转换结果到 WebUITestCase（project_id 存在时按项目隔离查询，防跨项目覆盖同名 ID）

    方案B：WUI.test_case_id 绑定逻辑 id；existing 按逻辑 id 兼容历史物理 id 绑定查找。
    """
    try:
        from app.core.services.case_versioning import find_existing_wui, wui_binding_id
        existing, _binding_id = find_existing_wui(db, project_id, test_case_id)
        test_case_id = wui_binding_id(db, test_case_id)

        # 兼容旧格式: test_script 存摘要 + test_data 存 JSON spec
        compat_script = f'''"""
POM + 数据驱动测试: {test_spec.get("title", "WebUI Test")}
模式: JSON data-driven with StepRunner v2
POM Pages: {list(page_objects.keys())}
模块: {test_spec.get("module", "")}
步骤数: {len(test_spec.get("steps", []))}
"""
# 此测试通过 StepRunner + POM 执行
# 测试定义见 test_data 字段
'''

        data = {
            "project_id": str(project_id) if project_id else None,
            "base_url": base_url,
            "browser": browser,
            "viewport_size": viewport_size,
            "headless": headless,
            "test_script": compat_script,
            "script_type": script_type,
            "script_language": script_language,
            "element_selectors": {},  # 选择器在 POM 中，不在此处
            "test_data": test_spec,   # JSON 测试定义
            "generation_mode": "pom_data_driven",
            "page_objects": page_objects,
        }

        if existing:
            # 复用已绑定行：(project_id, test_case_id) 唯一约束下重转化不新增行。
            # 派生时软删的旧行 → 续命为当前版本；历史物理 id 绑定改写为逻辑 id，统一语义。
            existing.is_deleted = False
            existing.deleted_at = None
            existing.test_case_id = str(test_case_id)
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            wui = WebUITestCase(
                test_case_id=str(test_case_id),
                timeout=30000,
                **data,
            )
            db.add(wui)

        db.commit()
        return True
    except Exception as e:
        logger.error(f"保存失败: {e}")
        db.rollback()
        return False


def _fallback_to_rules(
    db, test_case_id, case_name, steps,
    base_url, browser, viewport_size, headless,
    script_type, script_language, page_objects,
    project_id: int = None,
) -> Dict[str, Any]:
    """V2 主提示词链路失败时的兜底：改用 V1 提示词（AI 直转）再试一次"""
    logger.info(f"V2 LLM 异常，回退 V1 兜底: {case_name}")
    from app.core.agents.web_ui_conversion_agent import convert_functional_to_web_ui_ai
    result = convert_functional_to_web_ui_ai(
        db=db,
        test_case_id=test_case_id,
        base_url=base_url,
        browser=browser,
        viewport_size=viewport_size,
        headless=headless,
        script_type=script_type,
        script_language=script_language,
        project_id=project_id,
    )
    if isinstance(result, dict):
        result["fallback"] = True
        result["page_objects"] = page_objects
    return result
