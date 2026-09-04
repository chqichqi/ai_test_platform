"""
两步生成法：Step1 提取特征 → Step2 逐一生成用例

2026-09-02 重构（7 根因落地）：
- features 每项带 module/page 归属（允许跨模块），不再只有一个顶层 module 硬压全部用例
- feature.key 改为机器生成（module归一化 :: name归一化），不再让 LLM 自由编 key
  → 同文档同功能两次生成 key 稳定，diff_features（变更检测）/ 落库归并 / 同批去重全部建立在稳定 key 上
- 新增 split_doc_sections / extract_features_chunked：长文档按章节切块多次提取，避免 [:20000] 掐头丢尾部
- Step2 小批生成，编号带全局偏移（不再每批从 TC001 起）
"""
import json as _json
import re as _re
import logging

logger = logging.getLogger(__name__)

# 单块上限：Step1 切块后每块给 LLM 的输入不超过该值（防超长）
_STEP1_CHUNK_MAX = 12000
# 何时启用分块提取
_STEP1_CHUNK_TRIGGER = 15000


def _norm(text) -> str:
    """去除空白与常见分隔符，用于生成稳定 key。"""
    return _re.sub(r"[\s\-_.,，、:：；;·•]+", "", (text or "")).strip()


def clean_module(text) -> str:
    """清理模块/页面名：去掉 markdown 井号与空白。"""
    m = _re.sub(r"^[#*\s]+|[#*\s]+$", "", str(text or ""))
    m = m.strip()
    return m or "通用模块"


def finalize_features(features: list, fallback_module: str = "通用模块") -> list:
    """为每个 feature 补齐 module 并机器生成稳定 key。

    稳定性约定：key = clean_module(module)::norm(name)。
    同一功能点只要 module 与 name 不变，两次生成 key 一致 →
    落库跨次归并、diff_features 变更检测、同批去重都依赖它。
    key 是机器产物（module 取自原文章节名、name 是 LLM 给的简洁名），
    但由本函数统一生成，杜绝 LLM 自己造 key 造成的不稳定。
    """
    out = []
    seen = set()
    dropped = 0
    for f in features or []:
        if not isinstance(f, dict):
            continue
        module = clean_module(f.get("module")) or clean_module(fallback_module) or "通用模块"
        f["module"] = module
        name = (f.get("name") or "").strip()
        detail = (f.get("detail") or "").strip()
        name_norm = _norm(name)
        # ── Step1 功能点质量闸（2026-09-03 审计 P1-3）──
        # 空/过短 name 或缺失 detail = LLM 产出残缺条目，直接剔除并显式记 error，
        # 不再"包装成 featN 放行"（featN 会让下游为一条空功能点生成用例=垃圾用例源头）。
        if not name_norm or len(name_norm) < 2:
            dropped += 1
            logger.error(f"[Step1质量闸] 丢弃残缺功能点: name 缺失或过短 (module={module!r}, name={name!r}, detail={(detail or '')[:40]!r})")
            continue
        if not detail or len(_norm(detail)) < 2:
            dropped += 1
            logger.error(f"[Step1质量闸] 丢弃缺失 detail 的功能点: name={name!r}")
            continue
        if _norm(detail) == _norm(name):
            # detail 与 name 完全相同 = LLM 没展开说明，信息量不足，剔除
            dropped += 1
            logger.error(f"[Step1质量闸] 丢弃 detail 与 name 相同的功能点: name={name!r}")
            continue
        key = f"{_norm(module)}::{name_norm}"
        _k = 2
        while key in seen:
            key = f"{_norm(module)}::{name_norm}__{_k}"
            _k += 1
        seen.add(key)
        f["key"] = key
        out.append(f)
    if dropped:
        logger.error(f"[Step1质量闸] 共剔除 {dropped} 条残缺/低质功能点，保留 {len(out)} 条")
    return out


def split_doc_sections(text: str) -> list:
    """按 markdown 标题把文档切成若干块，供分块提取与按模块取原文段。

    返回: [{"heading": str, "content": str, "start": int}]（start 为起始行号，仅调试用）
    未识别出任何标题时返回整篇单块（heading=""）。
    """
    if not text:
        return []
    lines = (text or "").split("\n")
    # 标题起始行（# 开头且后有非空内容）
    head_idx = []
    for i, ln in enumerate(lines):
        m = _re.match(r"^\s{0,3}#{1,6}\s+(.*)$", ln)
        if m and m.group(1).strip():
            head_idx.append((i, m.group(1).strip()))

    if not head_idx:
        return [{"heading": "", "content": text, "start": 0}]

    sections = []
    for n, (i, heading) in enumerate(head_idx):
        end = head_idx[n + 1][0] if n + 1 < len(head_idx) else len(lines)
        # 标题行本身并入本块内容
        chunk = "\n".join(lines[i:end]).strip()
        if chunk:
            sections.append({"heading": heading, "content": chunk, "start": i})
    # 标题之前的前言（项目信息/说明）单独一块，若非空则前置
    if head_idx[0][0] > 0:
        pre = "\n".join(lines[: head_idx[0][0]]).strip()
        if pre:
            sections.insert(0, {"heading": "", "content": pre, "start": 0})
    return sections


def _build_step1_prompt(content: str) -> str:
    return f"请分析以下业务需求文档（章节内容），提取该章节内所有功能点：\n\n{content}"


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
- 共享前置准备（Setup）：若文档/某模块明确要求"执行本模块用例前须先完成某个共享准备动作"（如"测工作台卡片前须先把所有指标添加到工作台""先创建/准备好某数据"），把该准备动作**单独列为一条 feature**（category=setup，name=该准备动作，如"把所有指标添加到工作台"），并**不要**把这段准备动作写进其它卡片/功能点里（它们会被系统自动关联为该 setup 的前置）。若文档无此类"全局/模块级先准备"要求，则不要编造 setup。

第三步：将以上功能点整理为结构化JSON。

重要——不要把下面这些"写给测试自动化作者的工程/编写规范"当成功能点或用例（它们不是被测系统的业务行为，无法针对被测系统执行验证，会生成无意义的伪用例）：
- 测试框架/断言库的实现写法（pytest、pytest.skip、spec/spec文件、expect(...)、to_have_count、for 循环写脚本、Playwright/Selenium 等自动化调用细节）；
- 关于"测试代码本身应具备什么"的自检/元要求（例如"某 spec 文件至少出现一次 pytest.skip 分支""不得硬编码指标名""不得假设指标/数据一定存在""动态数据处理""关键断言矩阵""操作返回规范"这类整节标题与条目）——这些是约束 UI 自动化实现层的规范，不作为功能点生成用例；
- 仅描述"如何用自动化脚本实现跳转/登录/返回"的过程性提示（goto URL、storage_state/登录态、机构ID参数、测试后恢复清理等）——只有当该内容是**被测系统的一个真实业务操作**（如"点击某卡片会跳转到某页"）才提取为功能点，纯实现提示一律不提取。

输出格式（纯JSON，不要 markdown 代码块，不要多余文字）：
{"features": [
  {"name": "功能点名称(简洁,体现页面对象+操作)", "module": "该功能点所属模块/页面名(取原文最近的章节/页面标题, 如实填写, 不要合并成单个)", "category": "指标跳转|筛选|规则|预警|自定义|边界|setup", "detail": "具体描述"}
],
 "module_contexts": [
  {"module": "模块/页面名(与上面 features 的 module 同名)", "entry_navigation": "如何到达本模块页面/需先导航到哪(如『从工作台点击「患者档案」进入患者列表页面』；若该模块即登录后默认落地页则填空)", "shared_preconditions": ["本模块所有用例共有的静态前提(如『已登录系统』)"], "shared_setup": "执行本模块用例前须先完成的共享准备动作(文档明确要求才写, 如『先把所有指标添加到工作台』; 无则填空字符串)", "assertions": ["本模块通用断言要求(如『卡片总数=列表总记录数』『筛选后数据一致』)"], "return_rule": "本模块用例断言完成后是否需返回某页(如『返回工作台』; 无则空)"}
 ]}

每个功能点=独立feature。不要合并、不要省略。
关键（规范模型·2026-09-03）：把"整个模块/整节开头/整段"里的**横切共享声明**——如何到达本模块页面的入口导航、本模块共有的前置、须先做的共享准备、本模块通用断言、断言后返回规则——统一收进 module_contexts（每模块一条），**不要**再把它们逐条重复埋进各 feature 的 detail；feature 的 detail 只写各自具体的业务操作点与验证点。若模块间没有共享声明，module_contexts 可为空数组。
直接输出JSON，不要输出 key 字段（key 由系统生成）。"""


def _dump_step1_response(response, tag: str = ""):
    """Step1 解析失败时把 LLM 原始响应落盘，便于排查（logs/step1_response_debug_*.txt）。"""
    try:
        from datetime import datetime as _dt
        import os
        os.makedirs("logs", exist_ok=True)
        _p = f"logs/step1_response_debug_{_dt.now().strftime('%Y%m%d_%H%M%S')}_{tag}.txt"
        with open(_p, "w", encoding="utf-8") as f:
            f.write((response or "" )[:8000])
        logger.warning(f"[Step1] 原始响应已落盘: {_p}")
    except Exception as e:
        logger.warning(f"[Step1] dump 失败: {e}")


def _list_of(v):
    """把 context 里的字符串/分号串/列表统一成去空行列表。"""
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.replace("；", ";").split(";") if x.strip()]
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _normalize_contexts(raw_contexts, fallback_module: str = "") -> list:
    """把 LLM 输出的 module_contexts 归一为 [{module, entry_navigation, shared_preconditions,
    shared_setup, assertions, return_rule}]（缺失字段补默认，空句剔除）。"""
    out = []
    for c in (raw_contexts or []):
        if not isinstance(c, dict):
            continue
        module = (str(c.get("module") or fallback_module or "")).strip()
        if not module:
            continue
        out.append({
            "module": module,
            "entry_navigation": (str(c.get("entry_navigation") or "")).strip(),
            "shared_preconditions": _list_of(c.get("shared_preconditions")),
            "shared_setup": (str(c.get("shared_setup") or "")).strip(),
            "assertions": _list_of(c.get("assertions")),
            "return_rule": (str(c.get("return_rule") or "")).strip(),
        })
    return out


def _context_map(ctx_list: list, fallback_module: str = "") -> dict:
    """{clean_module(module): ctx}（重复模块后覆盖）。无 module 的 ctx 用 fallback_module 兜底。"""
    _map = {}
    for c in _normalize_contexts(ctx_list, fallback_module):
        _mod = clean_module(c["module"])
        if _mod:
            _map[_mod] = c
    return _map


async def extract_features_once(llm_service, section_text: str) -> dict:
    """单次 LLM 提取某段文本：返回 {"features":[...], "contexts":[...]}。

    其中 features 为 raw（未 finalize）；contexts 为该段解析出的模块级共享声明
    （已归一为 {module, entry_navigation, shared_preconditions, shared_setup, assertions, return_rule}）。
    带失败重试；空/坏响应自动重试至多 3 次，仍失败则 dump + error（不静默当整篇无功能点）。
    """
    llm_config = llm_service.get_active_config()
    if not llm_config:
        logger.warning("[Step1] 无LLM配置，返回空特征")
        return {"features": [], "contexts": []}

    # Step1 单次提取可能输出较多功能点（大模块/功能点密集需求），cap 过低会把 JSON
    # 截断成未闭合 → 解析失败重试（每次 120s 超时）→ 前端长时间"处理中"无结果。
    # 给足预算（同 Step2 铁律 get_scaled_max_tokens 0.7/100000），避免截断。
    max_tokens = llm_service.get_scaled_max_tokens(0.7, 100000)
    for _attempt in range(1, 4):
        user_prompt = _build_step1_prompt(section_text)
        response = None
        try:
            response = await llm_service.async_call_llm(
                prompt=user_prompt,
                system_prompt=STEP1_SYSTEM_PROMPT,
                temperature=0,
                json_mode=False,
                max_tokens=max_tokens,
            )
            if not response:
                logger.warning(f"[Step1] 第{_attempt}次 LLM 返回空，重试")
                continue
            result = _robust_loads(response)
            feats = result.get("features", []) or []
            ctxs = _normalize_contexts(result.get("module_contexts"))
            if feats:
                logger.info(f"[Step1] 第{_attempt}次提取成功: {len(feats)} 个功能点, {len(ctxs)} 条模块共享声明")
                return {"features": feats, "contexts": ctxs}
            logger.warning(f"[Step1] 第{_attempt}次返回 0 个功能点，重试")
        except Exception as e:
            logger.warning(f"[Step1] 第{_attempt}次解析失败: {e}，重试")
            try:
                _dump_step1_response(response, f"attempt{_attempt}")
            except Exception:
                pass
    logger.error("[Step1] 3 次提取仍失败（features 为空）")
    return {"features": [], "contexts": []}


async def extract_features_chunked(llm_service, requirement_text: str) -> dict:
    """分块提取：长文档按标题切块逐块调用 LLM，合并后机器生成 key/module。

    返回: {"features": [finalize后的feature], "contexts": {clean_module(module): ctx}}
    ctx = {module, entry_navigation, shared_preconditions, shared_setup, assertions, return_rule}
    """
    if not requirement_text:
        return {"features": [], "contexts": {}}

    if len(requirement_text) <= _STEP1_CHUNK_TRIGGER:
        # 短文档单次
        res = await extract_features_once(llm_service, requirement_text)
        features = finalize_features(res.get("features", []))
        contexts = _context_map(res.get("contexts", []))
        logger.info(f"[Step1] 单次提取到 {len(features)} 个功能点, {len(contexts)} 条模块共享声明")
        return {"features": features, "contexts": contexts}

    sections = split_doc_sections(requirement_text)
    merged_raw = []
    merged_ctx = []
    for sec in sections:
        content = sec["content"]
        if len(content) > _STEP1_CHUNK_MAX:
            content = content[:_STEP1_CHUNK_MAX]
        res = await extract_features_once(llm_service, content)
        # 给本块 feature / context 打上所属 module（用章节标题，除非 LLM 已标更细 module）
        for f in res.get("features", []):
            if isinstance(f, dict) and not f.get("module"):
                f["module"] = sec.get("heading", "") or "通用模块"
            merged_raw.append(f)
        for c in res.get("contexts", []):
            if isinstance(c, dict) and not c.get("module"):
                c["module"] = sec.get("heading", "") or "通用模块"
            merged_ctx.append(c)
        logger.info(f"[Step1] 章节「{sec.get('heading','(前言)')}」提取 {len(res.get('features',[]))} 个功能点, 累计 {len(merged_raw)}")

    features = finalize_features(merged_raw)
    contexts = _context_map(merged_ctx)
    logger.info(f"[Step1] 分块提取合并后共 {len(features)} 个功能点, {len(contexts)} 条模块共享声明")
    return {"features": features, "contexts": contexts}


async def extract_features(llm_service, requirement_text: str) -> dict:
    """Step1 提取特征列表（分块提取入口，返回已 finalize 的 features + 模块共享声明）。

    兼容旧调用方（version_generator / requirement_change_service）：
    返回 {"features": [...], "contexts": {module: ctx}}。features 每项带 module + 稳定 key；
    contexts 为该需求各模块/页面的共享声明（入口导航/共享前置/共享准备/通用断言/返回规范），
    供 Step2 生成时按模块注入，保证"先理解成规范模型、再生成"。
    """
    return await extract_features_chunked(llm_service, requirement_text)


def _robust_loads(text: str) -> dict:
    """把 LLM 输出稳健地解析为 JSON 对象（对齐 version_generator._parse_llm_response）。

    依次尝试：```json 代码块 → 最大花括号包裹内容 → 整个字符串；
    只要解析出 dict 即返回。全部失败则抛 ValueError，交由调用方明确记录，
    而不是静默把解析失败当成"无功能点"（那样上层会降级自由生成、漏掉卡片）。
    """
    content = (text or "").strip()
    candidates = []

    m = _re.search(r"```(?:json)?\s*(.*?)\s*```", content, _re.DOTALL | _re.IGNORECASE)
    if m:
        candidates.append(m.group(1).strip())

    if not candidates:
        m = _re.search(r"\{.*\}", content, _re.DOTALL)
        if m:
            candidates.append(m.group(0))

    candidates.append(content)

    for cand in candidates:
        if not cand:
            continue
        try:
            obj = _json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    raise ValueError("无法将 Step1 LLM 输出解析为 JSON 对象")


def build_step2_prompt(project_name: str, version_number: str,
                       module: str, features: list, content: str,
                       start_index: int = 1, module_context: dict = None) -> str:
    """构建 Step2 的 user_prompt，将特征列表注入（严格 1:1 约束）。

    module: 本批功能点所属模块/页面
    features: 本批功能点（已 finalize，含 key/name/category/detail）
    content: 本批 feature 对应模块的原文段（由调用方用 split_doc_sections 定位后传入）
    start_index: 全局用例编号起点（1-based），使多批用例编号连续不重复
    module_context: 可选，该模块在 Step1 中解析出的共享声明（规范模型）：
        {entry_navigation, shared_preconditions, shared_setup, assertions, return_rule}
        注入后强制应用到本模块每一条用例，避免模块级共享前提漏进单条用例。
    """
    n = len(features)
    if n == 0:
        return _build_step2_empty(project_name, version_number, module, content)

    # ── 模块共享声明（规范模型注入）──
    _ctx_block = ""
    if module_context:
        _lines = ["", "## 本模块共享声明（Step1 规范模型，必须逐条应用到此模块每一条用例，不得遗漏）"]
        _en = (module_context.get("entry_navigation") or "").strip()
        if _en:
            _lines.append(f"- 入口导航：{_en}")
            _lines.append(f"  → 本模块每条用例的 test_steps 第 1 步都必须是这段入口导航（禁止用『已处于…页面』前置代替）")
        _sp = module_context.get("shared_preconditions") or []
        if _sp:
            _lines.append(f"- 共享前置（写入每条用例 preconditions）：{'；'.join(_sp)}")
        _ss = (module_context.get("shared_setup") or "").strip()
        if _ss:
            _lines.append(f"- 共享准备（须先完成的动作）：{_ss}")
            _lines.append(f"  → 把它作为本模块 setup（本模块需要先准备的用例 depends_on 它），不要逐条复制进每条的 preconditions/步骤")
        _as_ = module_context.get("assertions") or []
        if _as_:
            _lines.append(f"- 通用断言（相关用例必须含这些断言）：{'；'.join(_as_)}")
        _rr = (module_context.get("return_rule") or "").strip()
        if _rr:
            _lines.append(f"- 返回规则（跳转/操作断言完成后须执行）：{_rr}")
        _lines.append("")
        _ctx_block = "\n".join(_lines)

    end_no = start_index + n - 1
    feature_lines = [f"共 {n} 个功能点（必须恰好生成 {n} 条用例，编号 TC{start_index:03d} 到 TC{end_no:03d}）："]
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
        f"需求原文参考：\n{content}\n\n"
        f"{_ctx_block}"
        f"重要约束：\n"
        f"  1. 共 {n} 个功能点 → 必须恰好输出 {n} 条用例（不允许多，不允许少）\n"
        f"  2. 每条用例聚焦该功能点的核心操作场景\n"
        f"  3. 编号从 TC{start_index:03d} 到 TC{end_no:03d}（全局连续，不得重复）\n"
        f"  4. test_steps 中每条 action 必须遵循 UI 元素命名约定（「」标记元素，\"\" 标记值，验证：开头）\n"
        f"  5. 所有字符串值内禁止出现裸 ASCII 双引号（步骤文本中的引号一律用中文「」或转义 \\\"），"
        f"字段间必须用英文逗号分隔，JSON 必须整体合法可被 json.loads 直接解析\n"
        f"  6. preconditions 只写『执行本用例前必须已就绪的导航/入口状态』，每句一条、用分号分隔，且：\n"
        f"     (a) 导航状态必须指向真实可进入的页面级位置（如『已登录系统并处于工作台页面』）；页面内部的『分类/分区/卡片区』（如 审核任务、患者概览、物流看板）"
        f"不是独立可进入的页面，禁止把分类写成『进入…审核任务页面』这类虚假导航词，用例实际停留/断言所在的真实页面才是前置的导航目标；\n"
        f"     (b) 禁止把『某指标卡片/某条数据/某列表记录必然存在且正在展示』写成必须就绪的硬前提——这些对象是否出现由被测系统动态决定，"
        f"应表述为『若该卡片/该数据出现则继续执行本用例，未出现则该用例跳过』，由执行阶段的动态跳过机制处理，而不是在前置里断言其一定存在、也不得臆造其数值；\n"
        f"     (c) 禁止出现任何操作动词/动作指令（不得出现 点击/添加/移除/保存/选择/滚动/输入/打开/后退 等），需要执行的动作只能放进 test_steps；\n"
        f"     (d) 禁止在前置里写具体统计数/预置数据条数\n"
        f"  7. 禁止臆造需求中未给出的具体数字。对『总数/今日新增/合计/条数』等统计展示类功能点，只能断言其『结构』（如：卡片展示总数与今日新增两项数值，"
        f"且均为有效数字/数值格式正确），不得编造『总数 N/今日新增 M/总数为 N 条/可见 N 条』这类凭空绝对值写进 action、expected_result 或 preconditions；"
        f"仅当需求原文明确给出了确切数字、且该数字确属断言目标时，才允许在期望中原样引用，否则一律不得写死任何数字\n"
        f"  8. 禁止臆造跳转目标 URL/路由。需求未给出明确目标页时，不要凭空编造具体路径（如 /xxx），动作与期望一律写成语义化目标"
        f"（如『点击后跳转至该卡片对应的详情/列表页面』、『跳转到患者档案并携带对应疾病筛选』）；具体 URL/路由交由 UI 转化阶段的真实探索去解析绑定，"
        f"严禁把凭空猜的路径固化成断言\n"
        f"  9. 页面入口导航必须是 test_steps 的第 1 步，禁止用『已处于/已进入 XX 页面』这类静态前置代替导航。"
        f"当用例的操作页面需经导航到达（模块/文档开头明确写了『从工作台点击「患者档案」进入患者列表页面』这类入口说明，"
        f"或该页不是登录后的默认落地页）时，该『从…进入…』动作必须作为本用例 test_steps 的第 1 条输出"
        f"（如『从工作台点击「患者档案」菜单进入患者列表页面』），使每条用例独立可跑、能真正到达目标页后再操作；"
        f"只有登录后即停在该页的默认落地页才允许在 test_steps 不写入口导航。不得把『如何到达本页』只写进 preconditions 而让步骤直接从页内操作开始\n"
        f"  10. 每条步骤的『操作对象/目标元素』必须来自本模块需求原文，只写本模块页面真实存在的对象名；"
        f"严禁凭空引入本模块之外其它模块/菜单的项（如操作『患者档案』模块的用例，步骤对象不得写成『新增角色』『角色管理』『账号管理』"
        f"『随访管理』等它模块菜单/页面名词）——UI 探索按步骤对象定位，跨模块名词会把探索带到错误页面。若需求原文动作对象不明确，"
        f"用最贴近本页面的通用对象名（如该按钮/区域在需求里的原始称呼），不得借用别的模块同名按钮\n\n"
        f"输出格式（严格按照以下 JSON 结构，直接输出，不要 markdown 代码块）：\n"
        f'{{"test_cases": [\n'
        f'  {{"id": "TC{start_index:03d}", "title": "验证某卡片点击跳转-正常", "module": "{module}",\n'
        f'    "priority": "P1", "test_type": "positive",\n'
        f'    "preconditions": ["已登录系统, 进入{module}页面"],\n'
        f'    "test_steps": [\n'
        f'      {{"step_no": 1, "action": "点击「某卡片」", "expected_result": "跳转到对应页面"}},\n'
        f'      {{"step_no": 2, "action": "验证：页面URL包含xxx", "expected_result": "URL正确"}}\n'
        f'    ],\n'
        f'    "expected_result": "成功跳转并验证页面",\n'
        f'    "tags": ["跳转", "卡片"]\n'
        f'  }},\n'
        f'  ...(共{n}条, 编号 TC{start_index:03d} 到 TC{end_no:03d})\n'
        f']}}'
    )


def _build_step2_empty(project_name: str, version_number: str, module: str, content: str) -> str:
    return (
        f"项目：{project_name}，版本：{version_number}\n\n"
        f"需求文档：\n{content}\n\n"
        f"模块：{module}\n\n"
        f"为每个功能点生成1条用例。输出纯JSON。"
    )


def diff_features(old_features: list, new_features: list) -> dict:
    """结构化 diff：按 feature.key 比较新旧功能点（机器驱动, 不依赖 LLM）。

    key 现为机器生成的 module::name（finalize_features），两次生成同功能 key 稳定，
    变更检测基于它更可靠。

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
