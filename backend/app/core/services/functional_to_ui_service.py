"""
功能用例 → UI 用例 转化编排服务

实现「先探索、再转化」逻辑：
1. 检查目标项目/模块是否已有 KnowledgeGraph 探索结果
2. 如果没有或覆盖不足 → 触发 BFS 探索 → 实时保存结果
3. 探索完成后 → 自动调用 LLM 逐条转化功能用例为 UI 用例

与 BusinessFlowUIService 的区别：
- BusinessFlowUIService: 从业务流文本出发 → CoT 提取用例 → MCP 探索 → 生成 UI 用例
- FunctionalToUIService: 从已有的功能测试用例出发 → 检查/补充 KG → V2/V1 转化

复用 BusinessFlowUIService 的探索基础设施（KG 查询、覆盖度检查、BFS 探索）。
"""

import asyncio
import inspect
import json
import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.models.knowledge_graph import KnowledgeGraph, ExplorationPageSnapshot
from app.core.models.project_ext import ProjectSetting
from app.core.services.text_normalize import normalize_ws


def _generate_login_steps_via_llm(login_content: str, llm_service) -> list:
    """复用业务流→功能用例的 LLM 能力：将自然语言登录描述生成为标准化操作步骤。

    与 VersionGeneratorService._extract_features 使用同一个 LLMService，
    确保 target 指向页面真实元素名（如"手机号"而非"登录手机号"）。

    Returns:
        [{"action":"fill","target":"手机号","value":"","role":"textbox","desc":"输入手机号"}, ...]
    """
    import json as _json
    import re
    prompt = f"""将以下自然语言登录描述转为标准化操作步骤。

规则：
1. 每条步骤输出 action（navigate/fill/click/select/validate）和 target
2. target 必须是页面上真实 UI 元素（≤6字），不包含"按钮/输入框/卡片"等描述词
   - "输入登录手机号" → target="手机号"
   - "点击登录按钮" → target="登录"
   - "选择第一个机构" → target="机构", value="第一个"
3. 条件句（"若...则..."）提取"则"后面的动作，忽略否定句（"不能选择"→跳过）
4. role: textbox/button/combobox/link/tab
5. value: fill 时可为空（凭证外部注入），select 时填选项

登录描述：
{login_content}

输出 JSON 数组：[{{"action":"...","target":"...","value":"...","role":"...","desc":"原文"}}]"""

    try:
        response = None
        for attempt in range(2):  # 空响应重试一次（DeepSeek 偶发空响应）
            response = llm_service.call_llm(
                prompt=prompt,
                system_prompt="你是UI自动化测试专家。将登录流程转为标准化步骤。只输出JSON。",
                max_tokens=llm_service.get_scaled_max_tokens(),
            )
            if response and response.strip():
                break
            logger.warning(f"[LoginImport] LLM 响应为空（第{attempt+1}次），准备重试" if attempt == 0 else "[LoginImport] LLM 两次响应均为空")
        json_match = re.search(r'\[.*?\]', response or '', re.DOTALL)
        if not json_match:
            logger.warning(f"[LoginImport] LLM 响应无 JSON: {(response or '')[:200]}")
            return []
        result = _json.loads(json_match.group(0))
        if not isinstance(result, list):
            return []
        _map = {'navigate': 'navigate', 'goto': 'navigate', 'fill': 'fill', '输入': 'fill', '填写': 'fill',
                'click': 'click', '点击': 'click', 'select': 'select', '选择': 'select',
                'validate': 'validate', '验证': 'validate'}
        for r in result:
            if isinstance(r, dict):
                r['action'] = _map.get(str(r.get('action', '')).lower(), r.get('action', ''))
        return [r for r in result if isinstance(r, dict) and r.get('action')]
    except Exception as e:
        logger.warning(f"[LoginImport] LLM 生成步骤失败: {e}")
        return []


def _dump_login_import_stage(project_id: int, version_id: Optional[int], stage: str, payload: dict):
    """将登录模块导入的分阶段结果写入临时文件，便于分别查看三个阶段的数据处理结果。

    stage: stage1_功能用例 / stage2_探索结果 / stage3_UI用例
    文件写入 logs/login_import/（与 app.log 同目录，路径由 settings.LOG_FILE 驱动）
    version_id 可空（项目无版本时先行导入，登录模块是项目级资产）
    """
    import json as _json
    from pathlib import Path
    from app.core.config import settings
    try:
        _dir = Path(settings.LOG_FILE).parent / "login_import"
        _dir.mkdir(parents=True, exist_ok=True)
        _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _fp = _dir / f"{stage}_v{version_id or 0}_{_ts}.json"
        _fp.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[LoginImport] {stage} 结果已保存: {_fp}")
    except Exception as _e:
        logger.warning(f"[LoginImport] {stage} 结果保存失败（不影响导入）: {_e}")


def _collect_login_elements(page, cfg) -> list:
    """LoginAgent 模式：用 Playwright Locator API 收集登录页可见表单元素——不用 page.evaluate 扫描。

    返回 [{group: 'input'|'button', index: 组内匹配序号, type, name, id, placeholder,
           aria-label, text, value, title}]
    index 与组选择器的匹配序号一致——解析时用同一选择器 + nth(index) 还原 Locator。
    """
    elements = []
    for _grp, _sel in (('input', cfg.login_element_inputs),
                       ('button', cfg.login_element_buttons)):
        loc = page.locator(_sel)
        _n = loc.count()
        for _i in range(_n):
            el = loc.nth(_i)
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue
            _info = {'group': _grp, 'index': _i}
            for _attr in ('type', 'name', 'id', 'placeholder', 'aria-label', 'role', 'value', 'title'):
                try:
                    _info[_attr] = el.get_attribute(_attr) or ''
                except Exception:
                    _info[_attr] = ''
            try:
                _info['text'] = (el.inner_text() or '').strip()[:50]
            except Exception:
                _info['text'] = ''
            elements.append(_info)
    return elements


def _llm_pick_login_elements(elements: list, llm, cfg) -> dict:
    """LLM 只回答"元素是什么"：username/password/login_button 各对应哪个 (group, index)。

    Playwright 负责定位，绝不让 LLM 生成 JS/CSS。失败返回 None → 规则兜底。
    """
    import json as _json
    import re as _re
    # 业务词零硬编码：关键词来自配置（项目可在 exploration_config.explore 段覆盖）
    _u_kws = [k.strip() for k in (cfg.login_username_keywords or '').split(',') if k.strip()]
    _p_kws = [k.strip() for k in (cfg.login_password_keywords or '').split(',') if k.strip()]
    _b_kws = [k.strip() for k in (cfg.login_button_keywords or '').split(',') if k.strip()]
    _compact = [{k: (v or '') for k, v in el.items()
                 if k in ('group', 'index', 'type', 'name', 'id', 'placeholder', 'aria-label', 'text', 'value')}
                for el in elements]
    prompt = f"""你是 Web UI 自动登录专家。分析登录页元素列表，找出三个核心元素并返回其 group 和 index：
1. username：用户名输入框（placeholder/name/aria-label 含以下任一关键词：{'/'.join(_u_kws)}）
2. password：密码输入框（type=password 几乎一定是，或含关键词：{'/'.join(_p_kws)}）
3. login_button：登录按钮（文本/aria-label 含以下任一关键词：{'/'.join(_b_kws)}）
规则：不要按出现顺序猜，综合 type/name/id/placeholder/aria-label/text 判断；
找不到的 index 返回 -1；只输出 JSON，不要 markdown，不要解释。
元素列表（JSON）：
{_json.dumps(_compact, ensure_ascii=False)}"""
    try:
        resp = llm.call_llm(
            prompt=prompt,
            system_prompt="你是UI自动化测试专家。只输出JSON。",
            max_tokens=llm.get_scaled_max_tokens(),
        )
        _m = _re.search(r'\{.*\}', resp or '', _re.DOTALL)
        if not _m:
            return None
        _data = _json.loads(_m.group(0))
        _out = {}
        for _k in ('username', 'password', 'login_button'):
            _v = _data.get(_k) or {}
            if not isinstance(_v, dict):
                continue
            try:
                _idx = int(_v.get('index', -1))
            except Exception:
                _idx = -1
            if _idx < 0:
                continue
            _grp = str(_v.get('group', 'input' if _k != 'login_button' else 'button'))
            _out[_k] = {'group': _grp, 'index': _idx}
        return _out if len(_out) == 3 else None
    except Exception as e:
        logger.warning(f"[LoginImport] LLM 登录元素识别失败: {e}")
        return None


def _rule_pick_login_elements(elements: list, cfg) -> dict:
    """规则兜底（LLM 失败时）：type=password → 密码；placeholder 关键词 → 用户名；按钮文本关键词 → 登录按钮。

    文本匹配统一去空白归一化（normalize_ws）——应用侧按钮文案可能带空格（真机实证
    「登 录」/「重 置」），子串匹配会因空格失配（2026-09-02 在登录元素识别侧的同类漏网：
    「登录」not in「登 录」→ 按钮识别为 None → 登录步骤退化为文本定位 → 无法点击登录）。
    关键词与元素文本各自 normalize_ws 后再比较，与探索侧/执行侧同源。
    """
    _user_kws = [normalize_ws(k).lower() for k in cfg.login_username_keywords.split(',') if k.strip()]
    _pwd_kws = [normalize_ws(k).lower() for k in cfg.login_password_keywords.split(',') if k.strip()]
    _btn_kws = [normalize_ws(k).lower() for k in cfg.login_button_keywords.split(',') if k.strip()]

    _password = None
    for _el in elements:
        if _el['group'] != 'input':
            continue
        _blob = normalize_ws(f"{_el.get('type','')} {_el.get('placeholder','')} {_el.get('name','')}").lower()
        if _el.get('type', '').lower() == 'password' or any(k in _blob for k in _pwd_kws):
            _password = _el
            break
    _username = None
    for _el in elements:
        if _el['group'] != 'input' or _el is _password:
            continue
        _blob = normalize_ws(f"{_el.get('placeholder','')} {_el.get('name','')} {_el.get('id','')} {_el.get('aria-label','')}").lower()
        if any(k in _blob for k in _user_kws):
            _username = _el
            break
    if not _username:
        for _el in elements:
            if _el['group'] == 'input' and _el is not _password and _el.get('type', '').lower() in ('', 'text', 'tel', 'email'):
                _username = _el
                break
    _button = None
    for _el in elements:
        if _el['group'] != 'button':
            continue
        _blob = normalize_ws(f"{_el.get('text','')} {_el.get('value','')} {_el.get('aria-label','')} {_el.get('title','')}").lower()
        if any(k in _blob for k in _btn_kws):
            _button = _el
            break
    if not (_username and _password and _button):
        return None
    return {'username': {'group': 'input', 'index': _username['index']},
            'password': {'group': 'input', 'index': _password['index']},
            'login_button': {'group': 'button', 'index': _button['index']}}


def _find_el_by_pick(elements: list, pick: dict):
    """按 (group, index) 从收集列表中还原元素描述。"""
    if not pick:
        return None
    return next((el for el in elements
                 if el['group'] == pick.get('group') and el['index'] == pick.get('index')), None)


def _build_login_step_args(el: dict, kind: str, cfg, value: str = '') -> dict:
    """由收集到的真实元素属性构建语义化步骤 args（无 JS、无 CSS nth）：
    fill → {"placeholder": 真实placeholder}；click → {"locator": 按钮真实文本}。
    无 placeholder/文本时按 id > name 属性构建，最后才回退组选择器 nth。
    """
    if kind == 'fill':
        if el.get('placeholder'):
            return {"placeholder": el['placeholder'], "value": value}
        if el.get('id'):
            return {"locator": f"#{el['id']}", "value": value}
        if el.get('name'):
            return {"locator": f"[name=\"{el['name']}\"]", "value": value}
        _sel = cfg.login_element_inputs
        return {"locator": f"{_sel} >> nth={el['index']}", "value": value}
    if kind == 'click':
        if el.get('text'):
            return {"locator": el['text']}
        if el.get('value'):
            return {"locator": el['value']}
        if el.get('id'):
            return {"locator": f"#{el['id']}"}
        _sel = cfg.login_element_buttons
        return {"locator": f"{_sel} >> nth={el['index']}"}


def _find_token_path_in_obj(obj, prefix: str = '', kws: tuple = ('token', 'jwt', 'access')) -> list:
    """递归扫描 JSON 找 token 字段的完整路径（叶子必须是较长的字符串，过滤权限/布尔标记）。

    阈值说明（启发式，非业务值）：len >= 8 过滤短值（权限标记 hasAccess 等布尔/标志位不会误判为 token）；
    list 递归深度限 5 层防止嵌套爆炸。
    """
    _paths = []
    if isinstance(obj, dict):
        for _k, _v in obj.items():
            _cur = f"{prefix}.{_k}" if prefix else str(_k)
            if isinstance(_v, dict):
                _paths.extend(_find_token_path_in_obj(_v, _cur, kws))
            elif isinstance(_v, list):
                for _i, _it in enumerate(_v[:5]):
                    _paths.extend(_find_token_path_in_obj(_it, f"{_cur}[{_i}]", kws))
            elif isinstance(_v, str) and len(_v) >= 8 and any(_kw in str(_k).lower() for _kw in kws):
                _paths.append(_cur)
    return _paths


def _pick_best_token_path(paths: list, prefer_kws: tuple = ('access', 'jwt')) -> str:
    """多候选 token 路径择优：含 access/jwt 的字段优先（如 access_token 优于 refresh_token），
    同优先级取路径最短（嵌套最浅、最通用）。"""
    def _key(p):
        _pl = str(p).lower()
        _seg = _pl.rsplit('.', 1)[-1]
        return (0 if any(_kw in _seg for _kw in prefer_kws) else 1, len(p))
    return sorted(paths, key=_key)[0]


def _analyze_login_api_from_capture(capture: dict, base_url: str, cfg) -> dict:
    """从浏览器网络捕获中识别登录接口与 Token 路径（真实请求，比 Swagger 推断更可靠）。

    capture: {"requests": [{"method","url","resource_type","post_data"}],
              "responses": [{"url","status","body","token_headers"}]}
    返回候选 dict 或 None：{"url","method","body_params","token_path","token_source","score"}
    token_source: 'body'（JSON 响应体）| 'header'（响应头，如 X-Auth-Token）
    """
    import json as _json
    from urllib.parse import urlparse as _up

    _token_kws = tuple(k.strip().lower() for k in (cfg.login_token_keywords or '').split(',') if k.strip()) \
        or ('token', 'jwt', 'access')
    _api_kws = tuple(k.strip().lower() for k in (cfg.login_api_keywords or '').split(',') if k.strip()) \
        or ('login', 'auth', 'signin')

    # 响应按 URL 分组：url -> [{"path","source","status"}]（body 路径与 header 路径都收进来）
    _resp_tokens = {}
    for _r in (capture.get('responses') or []):
        _url = _r.get('url', '')
        _status = _r.get('status')
        _body = _r.get('body')
        if isinstance(_body, dict):
            for _p in _find_token_path_in_obj(_body, kws=_token_kws):
                _resp_tokens.setdefault(_url, []).append({"path": _p, "source": "body", "status": _status})
        for _hname in (_r.get('token_headers') or {}):
            # 防御性再过滤：仅接收名称含 token 关键词的响应头（Date/Cache-Control 等无关头不入候选）
            if not any(_kw in str(_hname).lower() for _kw in _token_kws):
                continue
            _resp_tokens.setdefault(_url, []).append({"path": _hname, "source": "header", "status": _status})

    if not _resp_tokens:
        return None

    _cands = []
    for _req in (capture.get('requests') or []):
        # 过滤页面导航（document）：登录接口是 xhr/fetch，避免把页面跳转误判为登录接口
        if (_req.get('resource_type') or '') == 'document':
            continue
        _url = _req.get('url', '')
        _tk = _resp_tokens.get(_url)
        if not _tk:
            continue
        _post = _req.get('post_data') or ''
        _body_params = {}
        try:
            _pd = _json.loads(_post) if _post.strip() else {}
            if isinstance(_pd, dict):
                for _k, _v in _pd.items():
                    _body_params[_k] = _v if isinstance(_v, str) else _json.dumps(_v, ensure_ascii=False)
        except Exception:
            pass
        _score = 0
        _ul = _url.lower()
        for _kw in _api_kws:
            if _kw in _ul:
                _score += 1
        _score += 2  # 响应含 token → 强候选
        # body 路径优先（结构化、可注入）；仅 header 时用 header 名
        _body_paths = [t for t in _tk if t['source'] == 'body']
        _picked = _pick_best_token_path([t['path'] for t in _body_paths]) if _body_paths \
            else _pick_best_token_path([t['path'] for t in _tk])
        _cands.append({
            "url": _url, "method": (_req.get('method') or 'POST').upper(),
            "body_params": _body_params,
            "token_path": _picked,
            "token_source": 'body' if _body_paths else 'header',
            "score": _score,
        })

    _cands.sort(key=lambda c: c['score'], reverse=True)
    return _cands[0] if _cands else None




class FunctionalToUIService:
    """功能用例 → UI 用例 转化编排服务"""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # 登录模块导入（专用——有头探索 + 三件套生成）
    # ========================================================================

    async def import_login_module(
        self, version_id: Optional[int], login_content: str, project_id: int,
        force_headless: bool = False,
    ) -> dict:
        """
        导入登录模块（项目级资产，跨版本共享）：

        步骤一：LLM 生成标准化功能用例（复用业务流→功能用例管线）
        步骤二：有头浏览器探索 + ElementLocator 定位真实元素 → UI 用例（复用已有定位器）
        步骤三：StepRunner 验证 → 成功则保存三件套

        version_id 可空：项目尚无版本时允许先行导入（登录模块项目级资产不依赖版本，
        与「创建版本前必须先配置登录鉴权」门控配套）；有版本时传入最新版本 id 用于
        功能用例（test_cases 表）关联，便于版本内可见。

        换项目只需修改业务流文本，无需改代码。
        """
        import json as _json

        # ════════ 读项目配置 ════════
        from app.core.models.project_ext import ProjectSetting
        from app.core.models.project import Project
        psetting = self.db.query(ProjectSetting).filter(
            ProjectSetting.project_id == project_id
        ).first()
        _ec = (psetting.exploration_config or {}) if psetting else {}
        _proj = self.db.query(Project).filter(Project.id == project_id).first()
        _pt = (_proj.project_type or 'web').lower() if _proj else 'web'

        if _pt == 'app':
            _cfg = _ec.get('app', {})
            if not _cfg.get('apk_package'):
                return {"success": False, "error": "请先在项目卡片的「项目配置」中上传 APK 安装包后再导入登录模块"}
            if not _cfg.get('username'):
                return {"success": False, "error": "请先在项目卡片的「项目配置」中配置登录用户名后再导入登录模块"}
            if not _cfg.get('password'):
                return {"success": False, "error": "请先在项目卡片的「项目配置」中配置登录密码后再导入登录模块"}
            base_url = ''
        else:
            _cfg = _ec.get('web', {})
            base_url = _cfg.get('base_url', '') or ''
            if not base_url:
                _envs = _cfg.get('environments') or []
                _active_env = _cfg.get('active_environment') or ''
                if isinstance(_envs, list) and _active_env:
                    _matched = [e for e in _envs if isinstance(e, dict) and e.get('name') == _active_env]
                    if _matched:
                        base_url = _matched[0].get('url', '') or ''
            if not base_url:
                return {"success": False, "error": "请先在项目卡片的「项目配置」中配置目标系统 URL（base_url）后再导入登录模块"}
            if not _cfg.get('username'):
                return {"success": False, "error": "请先在项目卡片的「项目配置」中配置登录用户名（username）后再导入登录模块"}
            if not _cfg.get('password'):
                return {"success": False, "error": "请先在项目卡片的「项目配置」中配置登录密码（password）后再导入登录模块"}

        _uname = _cfg.get('username', '')
        _pwd = _cfg.get('password', '')

        # 零硬编码：登录字段/按钮/成功标志等业务词全部来自 WebExplorationConfig
        # （项目可在 exploration_config.explore 段覆盖定制，换项目不改代码）
        from app.core.services.exploration_config import build_web_exploration_config
        explore_cfg = build_web_exploration_config(_ec)

        # ════════ 步骤一：LLM 生成标准化功能用例步骤（失败回退正则解析） ════════
        llm = self._get_llm()
        actionable_steps = _generate_login_steps_via_llm(login_content, llm) if llm else []
        _steps_source = 'llm' if actionable_steps else ''
        if not actionable_steps:
            # 回退：LLM 失败/空响应 → StepParser 正则解析（处理带序号、副词的规范文本）
            from app.core.services.step_parser import parse_steps
            logger.warning("[LoginImport] LLM 未产出步骤，回退到 StepParser 正则解析")
            _steps_source = 'regex'
            raw_steps = [{"action": line.strip()} for line in login_content.strip().split('\n') if line.strip()]
            guided_steps = parse_steps(raw_steps, llm_service=llm)
            actionable_steps = []
            for gs in guided_steps:
                _at = getattr(gs, 'action_type', '')
                if _at not in ('click', 'fill', 'select', 'navigate', 'goto'):
                    continue
                _tgt = getattr(gs, 'target_text', '') or ''
                _val = getattr(gs, 'fill_value', '') or getattr(gs, 'select_option', '') or ''
                # 登录语义修正：target 为空而 value 是登录字段名（账号/密码/手机号等）时，
                # 说明用户写的是"输入：账号"——账号是字段名（target），凭证从配置注入
                _login_fields = tuple(
                    f.strip() for f in (explore_cfg.login_username_keywords + ',' + explore_cfg.login_password_keywords).split(',') if f.strip()
                )
                if _at == 'fill' and not _tgt and any(f in (_val or '') for f in _login_fields):
                    _tgt = _val
                    _val = ''
                actionable_steps.append({
                    "action": _at,
                    "target": _tgt,
                    "value": _val,
                    "role": getattr(gs, 'role_hint', '') or ('textbox' if _at == 'fill' else 'button'),
                    "desc": getattr(gs, 'raw_action', '') or f"{_at} {_tgt}",
                })
        if not actionable_steps:
            return {"success": False, "error": "登录业务流中未找到可执行步骤——请包含至少一个点击/填写/选择操作"}
        logger.info(f"[LoginImport] 生成 {len(actionable_steps)} 个可执行步骤: "
                    f"{[(s.get('action',''), s.get('target','')[:20]) for s in actionable_steps]}")

        # 阶段一落盘：登录模块功能用例（LLM 或正则解析的标准化步骤）
        _dump_login_import_stage(project_id, version_id, "stage1_功能用例", {
            "version_id": version_id,
            "project_id": project_id,
            "source": _steps_source,
            "login_content": login_content,
            "actionable_steps": actionable_steps,
        })

        # ════════ 步骤二：有头浏览器探索（LoginAgent 模式：LLM 识别 + Playwright 定位） ════════
        from app.core.services.step_runner import StepRunner
        from playwright.sync_api import sync_playwright

        ui_steps = []
        exploration_success = False
        step_diagnostics = []  # 探索结果：target → 页面实际文本（供 KG 保存）
        # 探索与验证共用同一浏览器会话（不再开第二个窗口——
        # 旧流程里探索窗口填完账号密码却不点登录就关闭，用户会误以为"第一次登录失败"）
        exec_result = {"status": "skipped", "error": "未执行"}

        _api_capture = {"requests": [], "responses": []}  # 浏览器网络捕获（联动 API 鉴权用）
        _auth_state = None  # 登录后的浏览器 storage_state（写入 KG 供后续复用）

        def _do_explore():
            nonlocal ui_steps, exploration_success, step_diagnostics, exec_result, _api_capture, _auth_state
            _deferred_validates = []  # validate 类步骤延后到机构选择处理之后执行
            _pw = sync_playwright().start()
            _browser = None
            try:
                _browser = _pw.chromium.launch(headless=False)
                _ctx = _browser.new_context(viewport={"width": explore_cfg.viewport_width,
                                                      "height": explore_cfg.viewport_height})
                _page = _ctx.new_page()

                # ── 网络捕获：监听登录时的真实 API 请求/响应（联动 API 鉴权用，无需 Swagger 文档）──
                _cap_token_kws = tuple(
                    k.strip().lower() for k in (explore_cfg.login_token_keywords or '').split(',') if k.strip()
                ) or ('token', 'jwt', 'access')

                def _on_req(_req):
                    try:
                        if _req.resource_type not in ('document', 'xhr', 'fetch'):
                            return
                        # 记录资源类型：document=页面导航（登录接口一般是 xhr/fetch），
                        # 分析阶段过滤 document 避免把页面请求误判为登录接口
                        _api_capture['requests'].append({
                            "method": (_req.method or '').upper(),
                            "url": _req.url,
                            "resource_type": _req.resource_type or '',
                            # 截断超大请求体（魔法数字 30000≈30KB，防内存膨胀，正常登录请求远小于此）
                            "post_data": (_req.post_data or '')[:30000],
                        })
                    except Exception:
                        pass

                def _on_resp(_resp):
                    try:
                        _ct = (_resp.headers.get('content-type', '') or '').lower()
                        # 部分系统把 token 放在响应头（如 X-Auth-Token / Authorization），
                        # 故即使非 JSON 响应也要检查响应头（登录接口也可能返回空 body）
                        _token_headers = {}
                        for _hname, _hval in (_resp.headers or {}).items():
                            _hl = str(_hname).lower()
                            if any(_kw in _hl for _kw in _cap_token_kws) and isinstance(_hval, str) and len(_hval) >= 8:
                                _token_headers[_hname] = _hval
                        _body = None
                        if 'json' in _ct:
                            try:
                                _body = _resp.json()
                            except Exception:
                                _body = None
                        # body 有 JSON 内容或响应头含 token → 记录（两条信息都需要的场景各自完整保留）
                        if isinstance(_body, dict) or _token_headers:
                            _api_capture['responses'].append({
                                "url": _resp.url, "status": _resp.status,
                                "body": _body if isinstance(_body, dict) else None,
                                "token_headers": _token_headers or None,
                            })
                    except Exception:
                        pass

                _page.on('request', _on_req)
                _page.on('response', _on_resp)

                _page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
                _page.wait_for_timeout(2000)
                logger.info(f"[LoginImport] 探索登录页: {_page.url[:80]}")
                step_diagnostics.append({"target": "__page__", "actual_text": "",
                                         "url": _page.url, "title": _page.title() or ''})

                # ── LoginAgent 模式：Playwright 收集元素 → LLM 识别三要素（规则兜底）──
                _login_els = _collect_login_elements(_page, explore_cfg)
                logger.info(f"[LoginImport] 登录页收集到 {len(_login_els)} 个可见表单元素")
                _pick_info = _llm_pick_login_elements(_login_els, llm, explore_cfg) if llm else None
                _pick_src = 'llm' if _pick_info else ''
                if not _pick_info:
                    _pick_info = _rule_pick_login_elements(_login_els, explore_cfg)
                    _pick_src = 'rule' if _pick_info else 'none'
                logger.info(f"[LoginImport] 登录元素识别({_pick_src}): {_pick_info}")

                for _s in actionable_steps:
                    _act = _s.get('action', '')
                    _target = _s.get('target', '')
                    _val = _s.get('value', '')

                    if _act in ('navigate', 'goto'):
                        ui_steps.append({"seq": len(ui_steps)+1, "action": "goto",
                                         "desc": _s.get('desc', '导航'), "args": {"url": base_url}})
                        continue

                    if _act == 'validate':
                        # 验证类步骤延后：登录后可能先出现机构选择页，
                        # "待机构选择页面消失→进入工作台"的验证必须在 handle_org_selection 之后
                        # StepRunner 无 validate 处理器，统一转为 assert_visible（等可见而非点击）
                        _deferred_validates.append({"action": "assert_visible",
                                                    "desc": _s.get('desc', f'验证 {_target}'),
                                                    "args": {"locator": _target or explore_cfg.login_success_marker}})
                        continue

                    step_args = {}
                    if _act == 'fill':
                        # 用户名/密码输入框识别：关键词来自 WebExplorationConfig（账号/手机号/username/邮箱等）
                        _is_cred = any(
                            _kw in _target for _kw in
                            (explore_cfg.login_username_keywords or '').split(',')
                            if _kw.strip()
                        )
                        _pick_key = 'username' if _is_cred else 'password'
                        _picked = _find_el_by_pick(_login_els, (_pick_info or {}).get(_pick_key))
                        _cred_val = "$username" if _is_cred else "$password"
                        if _picked:
                            # LLM/规则识别的输入框 → 真实 placeholder 语义定位（无 JS、无 CSS nth）
                            # 探索阶段只定位不执行——填写/点击由随后的同窗口验证（StepRunner）完成
                            step_args = _build_login_step_args(_picked, 'fill', explore_cfg, _cred_val)
                            step_diagnostics.append({"target": _target,
                                                     "actual_text": _picked.get('placeholder') or _target,
                                                     "role": "textbox", "action": "fill"})
                        else:
                            logger.warning(f"[LoginImport] 未识别到 {_pick_key} 输入框，用目标文本做 placeholder")
                            step_args = {"placeholder": _target, "value": _cred_val}
                    elif _act == 'click':
                        _picked = None
                        if _target and any(
                            _kw in _target for _kw in
                            (explore_cfg.login_button_keywords or '').split(',')
                            if _kw.strip()
                        ):
                            _picked = _find_el_by_pick(_login_els, (_pick_info or {}).get('login_button'))
                        if _picked:
                            step_args = _build_login_step_args(_picked, 'click', explore_cfg)
                            step_diagnostics.append({"target": _target,
                                                     "actual_text": _picked.get('text') or _target,
                                                     "role": "button", "action": "click"})
                        elif _target in tuple(
                            k.strip() for k in (explore_cfg.login_org_confirm_keywords or '').split(',') if k.strip()
                        ) and any(
                            k.strip() and k.strip() in login_content
                            for k in (explore_cfg.login_org_marker_keywords or '').split(',')
                        ):
                            # 机构选择页的"确定"按钮在登录页探索时不存在（页面还没跳转过去），
                            # 由 handle_org_selection 兜底选择机构并确认 → 跳过该步，避免错配成"登 录"
                            logger.warning(f"[LoginImport] CLICK '{_target}' 登录页上未定位（机构选择页按钮），跳过，由 handle_org_selection 兜底")
                            continue
                        else:
                            # 保留原始目标文本，按钮可能出现在登录后的页面，验证阶段再解析
                            step_args = {"locator": _target}
                    elif _act == 'select':
                        # 登录页上没有机构下拉控件 → 该步骤来自条件句（"若多个身份→选择机构"），
                        # 由 handle_org_selection 兜底处理机构选择
                        logger.warning(f"[LoginImport] SELECT '{_target}' 登录页无下拉控件，跳过（机构选择由 handle_org_selection 兜底）")
                        continue
                    else:
                        step_args = {"locator": _target}

                    ui_steps.append({"seq": len(ui_steps)+1, "action": _act,
                                     "desc": _s.get('desc', f'{_act} {_target}'), "args": step_args})
                    logger.info(f"[LoginImport] {_act.upper()} '{_target}' → {step_args}")

                # 收尾步骤
                ui_steps.append({"seq": len(ui_steps)+1, "action": "wait_for_render",
                                 "desc": "等待页面跳转", "args": {"ms": 3000}})
                if any(
                    k.strip() and k.strip() in login_content
                    for k in (explore_cfg.login_org_marker_keywords or '').split(',')
                ):
                    ui_steps.append({"seq": len(ui_steps)+1, "action": "handle_org_selection",
                                     "desc": "若出现「选择机构」页则选第一个机构并确认", "args": {}})
                    ui_steps.append({"seq": len(ui_steps)+1, "action": "wait_for_render",
                                     "desc": f"等待进入{explore_cfg.login_success_marker}", "args": {"ms": 2000}})
                # 延后的验证类步骤（机构选择处理之后执行）
                for _v in _deferred_validates:
                    _v["seq"] = len(ui_steps) + 1
                    ui_steps.append(_v)
                ui_steps.append({"seq": len(ui_steps)+1, "action": "assert_visible",
                                 "desc": f"验证已进入{explore_cfg.login_success_marker}",
                                 "args": {"locator": explore_cfg.login_success_marker}})

                # ═══ 同一浏览器窗口直接执行验证（不再开第二个窗口）═══
                # 跳过 goto 步骤——当前页面就是登录页（探索时已加载），无需重载
                _runner = StepRunner(_page, {})
                _runner.set_var('username', _uname)
                _runner.set_var('password', _pwd)
                _verify_steps = [s for s in ui_steps if s.get('action') != 'goto']
                _result = _runner.run(_verify_steps)
                _wb_url = _page.url if _result.get('success') else ''
                exec_result = {
                    "status": "completed" if _result.get("success") else "failed",
                    "error": _result.get("error"),
                    "steps_executed": _result.get("steps_executed", 0),
                    "workbench_url": _wb_url,
                }
                logger.info(f"[LoginImport] 同窗口验证完成: status={exec_result['status']}, "
                            f"steps={exec_result['steps_executed']}, error={exec_result['error']}")
                # 捕获登录后的 storage_state（写入 KG auth_data，后续执行/探索直接复用登录态）
                try:
                    if exec_result.get('status') == 'completed':
                        _auth_state = _ctx.storage_state()
                except Exception as _ae:
                    logger.warning(f"[LoginImport] 捕获 storage_state 失败: {_ae}")
                # 自学习回填：验证真实跑通机构页后，把实际用到的定位参数写入
                # handle_org_selection 步骤 args——步骤数据自包含，后续转化/执行
                # 直接读参数，执行器不硬编码具体系统的选择器（换项目零代码改动）
                _org_meta = getattr(_runner, '_org_meta', None)
                if _org_meta:
                    for _s in ui_steps:
                        if _s.get('action') == 'handle_org_selection':
                            _s['args'] = {**_s.get('args', {}), **_org_meta}
                            break
                    logger.info(f"[LoginImport] 机构选择参数已回填步骤数据: {_org_meta}")
                exploration_success = True
                _ctx.close()
            finally:
                if _browser:
                    try: _browser.close()
                    except Exception: pass
                if _pw:
                    try: _pw.stop()
                    except Exception: pass

        import asyncio as _aio
        await _aio.get_event_loop().run_in_executor(None, _do_explore)
        if not exploration_success:
            return {"success": False, "error": "探索登录页失败"}
        logger.info(f"[LoginImport] 探索完成，生成 {len(ui_steps)} 个 UI 步骤")

        # 阶段二落盘：登录页探索结果（页面诊断 + 探索生成的 UI 步骤）
        _dump_login_import_stage(project_id, version_id, "stage2_探索结果", {
            "version_id": version_id,
            "project_id": project_id,
            "base_url": base_url,
            "pages_visited": [d.get('url') for d in step_diagnostics if d.get('target') == '__page__'],
            "step_diagnostics": [d for d in step_diagnostics if d.get('target') != '__page__'],
            "ui_steps": ui_steps,
        })

        # ════════ 步骤三：StepRunner 验证执行（已在探索窗口内完成） ════════

        # 阶段三落盘：最终 UI 用例 + 验证执行结果（验证失败时同样落盘，便于排查）
        _dump_login_import_stage(project_id, version_id, "stage3_UI用例", {
            "version_id": version_id,
            "project_id": project_id,
            "case_id": "__login__",
            "title": "系统登录",
            "success": exec_result.get("status") in ("completed", "skipped"),
            "ui_steps": ui_steps,
            "execution_result": exec_result,
        })

        if exec_result.get("status") not in ("completed", "skipped"):
            return {
                "success": False,
                "error": f"登录验证失败（第{exec_result.get('steps_executed', 0)+1}步）: {exec_result.get('error', '未知错误')}——请修改业务流描述后重新导入",
                "ui_steps": ui_steps,
                "execution_result": exec_result,
            }

        # ════════ 保存登录页探索结果到 KG ════════
        try:
            from app.core.services.kg_populator import KGPopulator
            _page_url = base_url
            for _d in step_diagnostics:
                if _d.get('target') == '__page__' and _d.get('url'):
                    _page_url = _d['url']
                    break
            _exploration_result = {
                'pages_visited': [_page_url],
                'step_diagnostics': [d for d in step_diagnostics if d.get('target') != '__page__'],
                'deep_dive': {
                    'forms': [{
                        'name': '登录表单',
                        'fields': [{'name': d['target'], 'type': 'textbox' if d.get('role') == 'textbox' else 'combobox'}
                                   for d in step_diagnostics if d.get('action') == 'fill' and d.get('target') != '__page__'],
                        'submit': next((d.get('actual_text', '') for d in step_diagnostics
                                        if d.get('action') == 'click' and d.get('target') != '__page__'), ''),
                    }],
                },
            }
            _guided_steps_for_kg = [{'action_type': s.get('action', ''),
                                     'target_text': s.get('target', ''),
                                     'role_hint': s.get('role', '')} for s in actionable_steps]
            _kg_pop = KGPopulator(self.db)
            _kg_pop.populate(
                project_id=project_id,
                version_id=version_id,
                module_name='登录模块',
                exploration_result=_exploration_result,
                guided_steps=_guided_steps_for_kg,
                base_url=base_url,
                username=_uname,
                auth_data=_auth_state,  # 登录后的 storage_state，后续执行/探索直接复用登录态
                replace_mode='merge',
                explored_modules=['登录模块'],
            )
            logger.info(f"[LoginImport] 登录页探索结果已保存到 KG（{len(step_diagnostics)} 条诊断）")
        except Exception as _kg_e:
            logger.warning(f"[LoginImport] KG 保存失败（不影响导入结果）: {_kg_e}")

        # ════════ 保存三件套 ════════
        from app.core.models.web_ui_test import WebUITestCase
        from app.core.models.test_simple import SimpleTestCase, TestExecution, TestPriority

        # SimpleTestCase 无 test_case_id 字段（id 为 UUID 主键），
        # 按 标题 + 模块 + 项目 定位登录功能用例；priority 是 TestPriority 枚举（无 'P0'，用 critical 对应）
        _existing_func = self.db.query(SimpleTestCase).filter(
            SimpleTestCase.title == '系统登录',
            SimpleTestCase.module == '登录模块',
            SimpleTestCase.project_id == str(project_id),
            SimpleTestCase.deleted_at.is_(None),
        ).first()
        if _existing_func:
            _existing_func.title = '系统登录'
            _existing_func.module = '登录模块'
            _existing_func.priority = TestPriority.CRITICAL.value
            _existing_func.test_steps = login_content
            _existing_func.status = 'active'
        else:
            self.db.add(SimpleTestCase(
                title='系统登录', module='登录模块',
                priority=TestPriority.CRITICAL.value,
                test_steps=login_content, status='active',
                project_id=str(project_id),
                created_by='system',
            ))
        self.db.flush()

        # 功能用例列表（test_cases 表）同步一条「系统登录」：自动审核通过 + 已发布。
        # 与文件导入用例一致（导入后 status=published 已评审通过）；
        # 前端「转化为UI」仅对 approved 状态可用 → published 的登录用例按钮天然禁用（符合预期，无需再转化）。
        #
        # 功能用例与 UI 用例的内容必须不同：
        # - 功能用例（业务视角，人看）= 纯业务行为描述 + 预期结果，不带任何元素对象
        # - UI 用例（定位器视角，机器执行）= placeholder/locator 元素定位步骤
        from app.core.models.requirement import TestCase as ReqTestCase
        # 业务措辞模板与关键词全部来自 WebExplorationConfig（零硬编码）
        import json as _json_tpl
        try:
            _tpl = _json_tpl.loads(explore_cfg.login_func_step_templates or '{}')
        except Exception:
            _tpl = {}
        _user_kws = [k.strip().lower() for k in (explore_cfg.login_username_keywords or '').split(',') if k.strip()]
        _btn_kws = [k.strip().lower() for k in (explore_cfg.login_button_keywords or '').split(',') if k.strip()]
        _org_kws = [k.strip() for k in (explore_cfg.login_org_confirm_keywords or '').split(',') if k.strip()]

        _login_steps_structured = []
        for _i, _s in enumerate(actionable_steps):
            _act = _s.get('action', '')
            _tgt = (_s.get('target', '') or '').lower()
            if _act in ('navigate', 'goto'):
                _key = 'navigate'
            elif _act == 'fill':
                _key = 'username_fill' if any(k in _tgt for k in _user_kws) else 'password_fill'
            elif _act == 'click':
                if any(k in _tgt for k in _btn_kws):
                    _key = 'login_click'
                elif any(_tgt == k for k in _org_kws):
                    _key = 'org_confirm'
                else:
                    _key = ''
            elif _act == 'select':
                _key = 'org_select'
            elif _act == 'validate':
                _key = 'validate'
            else:
                _key = ''
            _pair = _tpl.get(_key) if _key else None
            if not (isinstance(_pair, list) and len(_pair) >= 2):
                _pair = _tpl.get('default')
            if isinstance(_pair, list) and len(_pair) >= 2:
                _biz, _exp = _pair[0], _pair[1]
            else:
                _biz, _exp = (_s.get('desc') or f'{_act} {_s.get("target", "")}').strip(), '执行成功'
            _login_steps_structured.append({"step": _i + 1, "action": _biz, "expected": _exp})
        _existing_req = self.db.query(ReqTestCase).filter(
            ReqTestCase.project_id == project_id,
            ReqTestCase.name == '系统登录',
        ).first()
        if _existing_req:
            _existing_req.module = '登录模块'
            _existing_req.status = 'published'
            _existing_req.priority = 'P0'
            _existing_req.test_steps = _login_steps_structured
            _existing_req.generated_by = 'ai'
        else:
            _new_login_case = ReqTestCase(
                project_id=project_id, version_id=version_id,
                module='登录模块', name='系统登录',
                priority='P0', case_type='functional',
                status='published',  # 已评审通过 + 已发布
                test_steps=_login_steps_structured,
                generated_by='ai',
                description='登录模块业务流自动生成的系统登录用例',
            )
            self.db.add(_new_login_case)
        self.db.flush()
        if not _existing_req:
            # 方案B：新建用例逻辑=物理（logical_case_id=自身id）
            _new_login_case.logical_case_id = _new_login_case.id

        _test_data = {"title": "系统登录", "module": "登录模块", "priority": "P0",
                      "case_id": "__login__", "preconditions": "", "steps": ui_steps}
        _test_script = _json.dumps(_test_data, ensure_ascii=False)
        _existing = self.db.query(WebUITestCase).filter(
            WebUITestCase.test_case_id == '__login__',
            WebUITestCase.project_id == str(project_id),
        ).first()
        if _existing:
            _existing.test_script = _test_script
            _existing.test_data = _test_data
            _existing.base_url = base_url
            _existing.headless = False
            _existing.project_id = str(project_id)
        else:
            self.db.add(WebUITestCase(
                test_case_id='__login__', base_url=base_url, project_id=str(project_id),
                browser='chromium', viewport_width=1920, viewport_height=1080,
                headless=False, timeout=30000, test_script=_test_script, test_data=_test_data,
                generation_mode='pom_data_driven',
            ))
        self.db.flush()

        if not self.db.query(TestExecution).filter(
            TestExecution.test_case_id == '__login__',
            TestExecution.project_id == str(project_id),
        ).first():
            self.db.add(TestExecution(test_case_id='__login__', project_id=str(project_id),
                                       executed_by='system', status='pending'))
        self.db.commit()

        # ════════ 步骤四：登录模块导入成功后自动联动 API 鉴权 ════════
        # 主路径：从刚才同窗口登录的浏览器网络捕获中提取真实登录接口与 Token（无需 Swagger）；
        # 回退：Swagger 候选扫描；均失败 → 保持待验证（不影响登录模块导入结果）
        _api_auth_auto = self._auto_config_api_auth(project_id, base_url, capture=_api_capture)
        logger.info(f"[LoginImport] API鉴权自动联动: {_api_auth_auto.get('status')} - {_api_auth_auto.get('reason', _api_auth_auto.get('token_path', ''))}")

        return {
            "success": True,
            "functional_case": {"name": "系统登录", "module": "登录模块", "priority": "P0", "steps": login_content},
            "ui_case": {"test_case_id": "__login__", "title": "系统登录", "steps": ui_steps},
            "execution_result": exec_result,
            "api_auth_auto": _api_auth_auto,
        }

    def _auto_config_api_auth(self, project_id: int, base_url: str, capture: dict = None) -> dict:
        """
        登录模块导入成功后自动联动 API 鉴权（失败不阻塞，保持待验证可手动重试）。

        主路径（capture）：浏览器登录时已真实发出登录请求——从网络捕获中提取
        登录 URL/方法/请求体/Token 路径，Token 已真实获取 → verified=True。
        无需 Swagger 文档（UI 能登录，API 信息就是真实的）。

        回退路径（无捕获）：扫描项目 Swagger 文档候选登录接口，调用验证 Token。
        """
        from datetime import datetime
        import requests as _req

        try:
            from app.core.models.project_ext import ProjectSetting
            from app.core.services.exploration_config import WebExplorationConfig

            psetting = self.db.query(ProjectSetting).filter(
                ProjectSetting.project_id == project_id
            ).first()
            if not psetting:
                return {"status": "skipped", "reason": "项目无配置"}
            _ec = dict(psetting.exploration_config or {})
            _web = _ec.get('web', {})
            if not (_web.get('username') and _web.get('password')):
                return {"status": "skipped", "reason": "未配置登录凭证"}
            _real_username = str(_web.get('username', '') or '')
            _real_password = str(_web.get('password', '') or '')
            explore_cfg = WebExplorationConfig()

            def _save_auth(auth: dict, reason_extra: str = ''):
                _ec['api_auth'] = auth
                psetting.exploration_config = _ec
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(psetting, "exploration_config")
                self.db.commit()
                return {"status": "success", "login_url": auth.get('login_url', ''),
                        "method": auth.get('login_method', ''), "token_path": auth.get('token_path', '')}

            # ════════ 主路径：浏览器网络捕获（真实登录请求，无需 Swagger）════════
            if capture:
                cand = _analyze_login_api_from_capture(capture, base_url, explore_cfg)
                if cand:
                    # 请求体：真实凭证值替换回占位符（避免明文凭证入库，供前端展示）
                    body = {}
                    for _k, _v in (cand.get('body_params') or {}).items():
                        if _v == _real_username:
                            body[_k] = '{username}'
                        elif _v == _real_password:
                            body[_k] = '{password}'
                        else:
                            body[_k] = _v
                    # URL 相对化：去掉 base_url 前缀；跨域/不同端口时保留完整 path+query
                    _rel = cand['url'].replace(base_url.rstrip('/'), '')
                    if not _rel.startswith('/'):
                        try:
                            from urllib.parse import urlparse as _up
                            _p = _up(cand['url'])
                            _rel = _p.path + (f"?{_p.query}" if _p.query else '')
                        except Exception:
                            _rel = cand['url']
                    auth = {
                        "login_url": _rel or cand['url'],
                        "login_method": cand['method'],
                        "request_body": body or {"username": "{username}", "password": "{password}"},
                        # token 来源：body=响应体 JSONPath；header=响应头字段名（如 X-Auth-Token）
                        "token_path": cand['token_path'],
                        "token_source": cand.get('token_source', 'body'),
                        "token_inject_location": "header",
                        "token_inject_name": "Authorization",
                        "token_inject_template": "Bearer {token}",
                        "verified": True,  # Token 在浏览器真实登录时已拿到
                        "verified_at": datetime.utcnow().isoformat(),
                        "capture_source": "browser_login",
                    }
                    logger.info(f"[LoginImport] 捕获到真实登录接口 {cand['method']} {cand['url']} "
                                f"→ token_path={cand['token_path']}（score={cand['score']}）")
                    return _save_auth(auth)

            # ════════ 回退路径：Swagger 候选扫描（无捕获时使用）════════
            try:
                from app.api.api_v1.endpoints.project_settings import _scan_login_candidates
                candidates = _scan_login_candidates(self.db, project_id)
            except Exception:
                candidates = []
            if not candidates:
                return {"status": "skipped",
                        "reason": "未捕获到登录接口请求且未导入 Swagger 文档（可到 Swagger Tab 手动配置）"}

            cand = candidates[0]
            # 凭证字段识别复用登录模块关键词配置（零硬编码）
            _user_kws = [k.strip().lower() for k in (explore_cfg.login_username_keywords or '').split(',') if k.strip()]
            _pass_kws = [k.strip().lower() for k in (explore_cfg.login_password_keywords or '').split(',') if k.strip()]

            # 构造请求体模板：与凭证相关的字段替换为 {username}/{password} 占位符
            body = {}
            for pname in (cand.get('request_body_params') or {}):
                _pl = str(pname).lower()
                if any(_k in _pl for _k in _pass_kws):
                    body[pname] = '{password}'
                elif any(_k in _pl for _k in _user_kws):
                    body[pname] = '{username}'

            full_url = cand['path'] if cand['path'].startswith('http') \
                else base_url.rstrip('/') + '/' + cand['path'].lstrip('/')

            token_paths = cand.get('token_path_candidates') or ['access_token', 'token', 'data.access_token', 'data.token']
            _last_err = ''
            _verified_path = None
            # 验证请求必须用真实凭证（保存的 api_auth 配置里保留 {username}/{password} 占位符供前端展示）
            for tp in token_paths:
                try:
                    _req_body = {
                        k: v.replace('{username}', _real_username).replace('{password}', _real_password)
                        if isinstance(v, str) else v
                        for k, v in body.items()
                    }
                    if cand['method'].upper() == 'GET':
                        resp = _req.get(full_url, params=_req_body, timeout=15, verify=False)
                    else:
                        resp = _req.request(cand['method'].upper(), full_url, json=_req_body, timeout=15, verify=False)
                except Exception as e:
                    _last_err = f'登录请求失败: {e}'
                    continue
                if resp.status_code >= 500:
                    _last_err = f'登录接口返回服务器错误 {resp.status_code}'
                    continue
                token = None
                try:
                    data = resp.json() if resp.text else {}
                    parts = str(tp).split('.')
                    _d = data
                    for part in parts:
                        if isinstance(_d, dict):
                            _d = _d.get(part)
                        elif isinstance(_d, list) and part.isdigit():
                            _d = _d[int(part)] if int(part) < len(_d) else None
                        else:
                            _d = None
                            break
                    token = _d
                except Exception:
                    token = None
                if token:
                    _verified_path = tp
                    break
                _last_err = f"Token 提取失败（{tp}）"

            auth = {
                "login_url": cand['path'],
                "login_method": cand['method'].upper(),
                "request_body": body,
                "token_path": _verified_path or (token_paths[0] if token_paths else ''),
                "token_source": "body",
                "token_inject_location": "header",
                "token_inject_name": "Authorization",
                "token_inject_template": "Bearer {token}",
                "verified": bool(_verified_path),
                "verified_at": datetime.utcnow().isoformat() if _verified_path else None,
                "capture_source": "swagger",
            }
            if not _verified_path:
                auth["auto_error"] = _last_err
            _save_auth(auth)
            if _verified_path:
                return {"status": "success", "login_url": cand['path'],
                        "method": cand['method'].upper(), "token_path": _verified_path}
            return {"status": "partial", "login_url": cand['path'],
                    "reason": _last_err or '未提取到 Token'}
        except Exception as e:
            logger.warning(f"[LoginImport] API 鉴权自动联动异常（不影响登录模块导入结果）: {e}")
            return {"status": "failed", "reason": str(e)}

    async def convert_cases_with_exploration(
        self,
        test_case_ids: List[str],
        base_url: str,
        browser: str = "chromium",
        viewport_size: str = "1920x1080",
        headless: bool = True,
        script_type: str = "playwright",
        script_language: str = "python",
        project_id: int = None,
        force_explore: bool = False,
        cancel_check=None,
        progress_callback=None,  # callable(dict) → 每完成一条用例回调
        phase_cb=None,           # callable(dict) → 阶段进度事件 {phase, phase_detail, explored_*}
    ) -> Dict[str, Any]:
        """
        主入口：确保探索就绪 → 逐条转化功能用例为 UI 用例

        Args:
            test_case_ids: 功能测试用例 ID 列表
            base_url: 目标系统 URL
            browser: 浏览器类型
            viewport_size: 视口尺寸
            headless: 是否无头模式
            force_explore: 是否强制重新探索（忽略缓存）。用于需求版本迭代场景，
                          用户确认 UI 已变更 → 跳过 KG 缓存 → 重新全量探索。
            script_type: 脚本类型
            script_language: 脚本语言
            project_id: 项目 ID

        Returns:
            {
                "success": bool,
                "results": [{test_case_id, case_name, success, error?, ...}],
                "explored_modules": [...],
                "cached_modules": [...],
                "exploration_method": "cached" | "bfs" | "mcp",
            }
        """
        from app.core.models.requirement import TestCase as ReqTestCase
        from app.core.models.test_simple import SimpleTestCase

        # 1. 加载所有功能测试用例
        test_cases = []
        for tid in test_case_ids:
            tc = self._load_test_case(tid)
            if tc:
                test_cases.append(tc)

        if not test_cases:
            return {"success": False, "error": "没有找到有效的功能测试用例", "results": []}

        # 2. 提取 project_id 和 version_id
        if not project_id:
            project_id = self._extract_project_id(test_cases[0])
        version_id = self._extract_version_id(test_cases[0])
        if version_id is None:
            # SimpleTestCase 等简单模型没有 version_id，尝试从项目获取最新版本
            version_id = self._infer_version_id(project_id)
            logger.info(f"[FunctionalToUI] 用例无 version_id，推断为 {version_id}")

        if not project_id:
            return {"success": False, "error": "无法确定项目ID", "results": []}

        # 2.5 同项目一致性：批量转化共享一套探索配置与保存归属（取首条用例的项目），
        # 混入跨项目用例会把 UI 用例存到错误项目——有项目归属的用例之间必须一致
        _pids = {str(tc.project_id) for tc in test_cases if getattr(tc, 'project_id', None)}
        if len(_pids) > 1:
            return {
                "success": False,
                "error": f"所选功能用例分属多个项目（{', '.join(sorted(_pids))}），批量转化仅支持同一项目内的用例",
                "results": [],
            }

        # 3. 读取探索配置（base_url / username / password）
        explore_cfg = self._load_exploration_config(project_id)
        explore_base_url = base_url or explore_cfg.get("base_url", "")
        username = explore_cfg.get("username", "")
        password = explore_cfg.get("password", "")

        if not explore_base_url:
            return {"success": False, "error": "未配置目标系统 URL，请先在项目卡片的「项目配置」中配置目标环境 URL", "results": []}

        # 4. 确定平台类型（Web / APP）
        from app.core.models.project import Project
        project = self.db.query(Project).filter(Project.id == project_id).first()
        platform_type = project.project_type if project else "web"

        # APP 端：自动探索暂未实现（需 Appium MCP Client）
        # 平台类型已通过管线传递，后续扩展时取消此检查即可
        if platform_type not in ("web", ""):
            return {
                "success": False,
                "error": f"「{platform_type}」平台暂不支持自动探索。当前仅支持 Web 端（Playwright）。APP 端探索功能开发中。",
                "results": [],
            }

        # 5. 解析测试步骤 → GuidedStep[]（按模块分组）
        # 正则解析失败的自然语言步骤会走 LLM 回退（同步 call_llm）——线程化避免占死事件循环
        # （2026-08-25 转化 timeout 根因：POM/解析 LLM 占死循环 → 前端轮询 120s 超时 → 弹窗自动消失）
        module_steps = await asyncio.to_thread(self._parse_and_group_steps, test_cases)

        # 回退：如果所有用例步骤都解析失败，至少用用例的 module 字段做缓存检查
        if not module_steps:
            module_steps = self._extract_modules_from_cases(test_cases)
            # _extract_modules_from_cases 返回 {模块名: [关键词]}，转为空步骤列表
            module_steps = {m: [] for m in module_steps}
            logger.info(f"[FunctionalToUI] 步骤解析为空，回退到模块名缓存检查: {list(module_steps.keys())}")

        logger.info(f"[FunctionalToUI] 用例涉及 {len(module_steps)} 个模块: {list(module_steps.keys())}")

        # 6. 检查现有 KG 覆盖度,确定需要探索的模块
        cached_modules = {}
        modules_to_explore = []

        if force_explore:
            # 强制探索模式：跳过所有缓存检查，全部重新探索
            modules_to_explore = list(module_steps.keys())
            logger.info(f"[FunctionalToUI] 强制探索模式：{len(modules_to_explore)} 个模块将全部重新探索")
        else:
            for module_name, steps in module_steps.items():
                kg_data = self._query_existing_kg(project_id, version_id, module_name)
                # 覆盖度检查：KG 有数据且至少有一个快照
                if kg_data and self._coverage_sufficient(kg_data, steps):
                    cached_modules[module_name] = kg_data
                    logger.info(f"[FunctionalToUI] 模块 '{module_name}' 缓存命中，覆盖度足够")
                else:
                    modules_to_explore.append(module_name)
                    logger.info(f"[FunctionalToUI] 模块 '{module_name}' 需要探索 (缓存={kg_data is not None})")

        # 7. 对缺失模块执行步骤驱动探索
        explored_results = {}
        exploration_failures = {}
        if modules_to_explore:
            logger.info(f"[FunctionalToUI] 开始步骤驱动探索 {len(modules_to_explore)} 个模块: {modules_to_explore}")
            if phase_cb:
                try:
                    phase_cb({"phase": "exploring",
                              "phase_detail": f"正在打开浏览器登录目标系统，探索 {len(modules_to_explore)} 个模块"})
                except Exception:
                    pass
            try:
                explored_results, explored_guided = await self._explore_by_steps(
                    module_steps={m: module_steps[m] for m in modules_to_explore},
                    base_url=explore_base_url,
                    username=username,
                    password=password,
                    project_id=project_id,
                    version_id=version_id,
                    headless=headless,
                    browser=browser,
                    viewport_size=viewport_size,
                    test_cases=test_cases,
                    platform_type=platform_type,
                    phase_cb=phase_cb,
                    cancel_check=cancel_check,
                )
                logger.info(f"[FunctionalToUI] 步骤驱动探索完成: {list(explored_results.keys())}")
            except Exception as e:
                logger.error(f"[FunctionalToUI] 步骤驱动探索异常: {e}")
                for m in modules_to_explore:
                    exploration_failures[m] = f"探索异常: {str(e)}"

            # 检查探索结果有效性
            for m in modules_to_explore:
                if m in explored_results:
                    result = explored_results[m]
                    if isinstance(result, dict) and result.get("error"):
                        exploration_failures[m] = result["error"]
                        del explored_results[m]
                    elif not self._exploration_has_usable_data(result):
                        exploration_failures[m] = "探索完成但未获取到可用元素"
                        explored_results[m] = {"module": m, "elements": [], "pages": [],
                                                "insufficient": True,
                                                "reason": "探索完成但元素数据为空"}

            if not explored_results and not cached_modules:
                return {
                    "success": False,
                    "error": f"探索失败且无缓存数据",
                    "results": [],
                    "summary": {"total": len(test_cases), "success": 0,
                                "exploration_failed": len(test_cases)},
                    "explored_modules": modules_to_explore,
                    "cached_modules": [],
                    "exploration_failures": exploration_failures,
                }

        # 8. 合并探索结果（缓存 + 新探索的）
        all_exploration = {**cached_modules, **explored_results}
        # 探索侧解析结果（含 LLM 指代推断）——预检/补充探索复用，与探索侧解析断链修复（H4）
        all_guided_steps = locals().get('explored_guided') or {}

        # 8.5. 批量级别预生成 POM（避免每条用例重复 LLM 调用）
        # POM 只依赖 KG 数据 + base_url，同批次所有用例完全相同
        shared_page_objects = None
        if cancel_check:
            _c = cancel_check()
            if inspect.isawaitable(_c):
                _c = await _c
            if _c:
                logger.info("[FunctionalToUI] ⛔ 客户端已断开，跳过 POM 预生成")
        else:
            _c = False
        # POM 是可选优化，不是 Guided Evidence -> UI Case 的必要环节。
        # 默认关闭，避免每次转化前额外触发一次大 Prompt LLM；项目可显式配置 generate_shared_pom=true。
        _generate_shared_pom = bool(explore_cfg.get("generate_shared_pom", False))
        if not _c and _generate_shared_pom:
            try:
                for _mod_name, _mod_kg in all_exploration.items():
                    if isinstance(_mod_kg, dict) and _mod_kg.get("elements"):
                        from app.core.services.llm_service import LLMService
                        from app.core.services.pom_generator import generate_pom_classes
                        if phase_cb:
                            try:
                                phase_cb({"phase": "pom",
                                          "phase_detail": "正在生成页面对象模型（POM），AI 生成中请稍候..."})
                            except Exception:
                                pass
                        _llm = LLMService(self.db)
                        # generate_pom_classes 内部同步 call_llm（POM prompt 大、耗时长）——
                        # 直接调用会占死事件循环 → 前端轮询超时 → 转化弹窗自动消失（2026-08-25 用户反馈）
                        # 线程化与 _convert_batch_v2 同模式
                        shared_page_objects = await asyncio.to_thread(
                            generate_pom_classes,
                            exploration_data=_mod_kg,
                            base_url=explore_base_url,
                            llm_service=_llm,
                            cancel_check=cancel_check,
                        )
                        logger.info(f"[FunctionalToUI] 批量 POM 生成完成: {len(shared_page_objects)} 个页面类 "
                                   f"(共 {len(test_cases)} 条用例共享)")
                        break
            except Exception as _pom_err:
                logger.warning(f"[FunctionalToUI] 批量 POM 生成失败，每条各自生成: {_pom_err}")

        # 7.5 ── 补充探索：预检发现步骤元素缺失 → 强制补充探索补齐后再转化（2026-08-17）──
        # 目标：KG 探索结果缺元素时先补齐再转化，而不是带缺元素转化（steps_missing 仅保留给
        #       「用例本身问题」——补充探索一轮后仍无法定位的步骤，如实标注）。
        # 策略：仅对缺失步骤所在模块补充探索（复用步骤驱动探索管线，探索器已 populate 落库，
        #       复查时重查 KG 刷新该模块数据）；force_explore 已全量重探索，跳过；
        #       补充探索异常不阻塞主流程。
        _supplemented_cases: set = set()  # 经历过补充探索的用例 id（用于失败信息标注）
        # 默认禁止第二轮真实点击。第一轮探索已经是 TestCase -> CasePlan 的完整事务；
        # 自动补充探索会重新打开浏览器并再次执行同一目标，是重复点击和长耗时的主要来源。
        # 通用平台仍保留能力，但必须由项目配置显式开启。
        _enable_supplement = bool(explore_cfg.get("enable_supplement_exploration", False))
        if not force_explore and _enable_supplement:
            try:
                _missing_by_module: Dict[str, list] = {}
                _case_missing: Dict[str, list] = {}
                for tc in test_cases:
                    tc_id = str(tc.id) if hasattr(tc, 'id') else str(getattr(tc, 'id', ''))
                    module = getattr(tc, 'module', '') or '通用'
                    module_kg = self._match_module_kg(all_exploration, module)
                    if not module_kg:
                        continue
                    _diags = self._check_case_steps(tc, module_kg,
                                                    guided_steps=all_guided_steps.get(module))
                    _miss = [d for d in _diags if d.get("status") == "not_found"]
                    if _miss:
                        _missing_by_module.setdefault(module, []).extend(_miss)
                        _case_missing.setdefault(tc_id, []).extend(_miss)

                if _missing_by_module:
                    # 从用例原始步骤中挑出缺失步骤，重新解析为引导步骤（按模块聚合、去重）
                    from app.core.services.step_parser import parse_single_step as _pss
                    _supple_steps: Dict[str, list] = {}
                    for tc in test_cases:
                        tc_id = str(tc.id) if hasattr(tc, 'id') else str(getattr(tc, 'id', ''))
                        module = getattr(tc, 'module', '') or '通用'
                        _case_miss = _case_missing.get(tc_id) or []
                        if not _case_miss:
                            continue
                        _supplemented_cases.add(tc_id)
                        _raw = self._extract_raw_steps(tc)
                        for _d in _case_miss:
                            _idx = int(_d.get("seq") or 1) - 1
                            if 0 <= _idx < len(_raw):
                                _gs = _pss(_raw[_idx], _idx + 1)
                                _tgt = getattr(_gs, 'target_text', '')
                                if not _tgt:
                                    continue
                                try:
                                    setattr(_gs, '_case_id', str(tc_id))
                                    setattr(_gs, '_case_index', 0)
                                except Exception:
                                    pass
                                _slist = _supple_steps.setdefault(module, [])
                                _k = (getattr(_gs, 'action_type', ''), _tgt)
                                if not any(
                                    (getattr(s, 'action_type', ''), getattr(s, 'target_text', '')) == _k
                                    for s in _slist
                                ):
                                    _slist.append(_gs)

                    if _supple_steps:
                        _mods = list(_supple_steps.keys())
                        _miss_cnt = sum(len(v) for v in _missing_by_module.values())
                        logger.info(f"[FunctionalToUI] ⬆ 补充探索 {len(_mods)} 个模块"
                                    f"（预检缺失 {_miss_cnt} 个步骤）: {_mods}")
                        if phase_cb:
                            try:
                                phase_cb({"phase": "exploring",
                                          "phase_detail": f"补充探索缺失步骤 {_miss_cnt} 个（模块：{'、'.join(_mods)}）"})
                            except Exception:
                                pass
                        # 将补充步骤保持为 Case-aware batch，避免补充探索退化成 legacy-1。
                        try:
                            from app.core.services.case_explorer import CaseStepBatch, CasePlan
                            for _sm, _steps in list(_supple_steps.items()):
                                _plans = []
                                _by_case = {}
                                for _gs in _steps:
                                    _cid = str(getattr(_gs, '_case_id', '') or '')
                                    if _cid:
                                        _by_case.setdefault(_cid, []).append(_gs)
                                for _cid, _csteps in _by_case.items():
                                    _tc = next((x for x in test_cases if str(getattr(x, 'id', '')) == _cid), None)
                                    if _tc:
                                        _plans.append(CasePlan(
                                            case_id=_cid, case_name=getattr(_tc, 'name', None) or getattr(_tc, 'title', None) or _cid,
                                            module=_sm, preconditions=getattr(_tc, 'preconditions', '') or '',
                                            expected_result=getattr(_tc, 'expected_result', '') or '', steps=_csteps,
                                            test_case_id=_cid, logical_case_id=str(getattr(_tc, 'logical_case_id', '') or _cid),
                                            revision_no=int(getattr(_tc, 'revision_no', 1) or 1), version_id=getattr(_tc, 'version_id', None),
                                            project_id=getattr(_tc, 'project_id', None),
                                        ))
                                _supple_steps[_sm] = CaseStepBatch(_steps, case_plans=_plans)
                        except Exception as _batch_e:
                            logger.warning(f"[FunctionalToUI] 补充探索 CasePlan 构建失败，继续兼容模式: {_batch_e}")
                        _supple_results, _ = await self._explore_by_steps(
                            module_steps=_supple_steps,
                            base_url=explore_base_url,
                            username=username,
                            password=password,
                            project_id=project_id,
                            version_id=version_id,
                            headless=headless,
                            browser=browser,
                            viewport_size=viewport_size,
                            test_cases=test_cases,
                            platform_type=platform_type,
                            phase_cb=phase_cb,
                            cancel_check=cancel_check,
                        )
                        for _m in _mods:
                            _sr = _supple_results.get(_m)
                            if _sr and isinstance(_sr, dict) and not _sr.get("error"):
                                # 探索器已 populate 落库——重查 KG 刷新该模块数据
                                _fresh = self._query_existing_kg(project_id, version_id, _m)
                                if _fresh and _fresh.get("step_diagnostics"):
                                    all_exploration[_m] = _fresh
                                    logger.info(f"[FunctionalToUI] 模块 '{_m}' 补充探索完成，KG 已刷新")
                                else:
                                    logger.warning(f"[FunctionalToUI] 模块 '{_m}' 补充探索后无新诊断数据")
                            else:
                                _err = _sr.get("error", "补充探索失败") if isinstance(_sr, dict) else "补充探索异常"
                                exploration_failures[_m] = _err
                                logger.warning(f"[FunctionalToUI] 模块 '{_m}' 补充探索失败: {_err}")
            except Exception as _se:
                logger.warning(f"[FunctionalToUI] 补充探索阶段异常（不影响主流程）: {_se}")

        # 9. 逐用例转化——带步骤级诊断
        from app.core.services.trace_logger import TraceLogger as _TraceLogger
        _conv_trace = _TraceLogger(module_name="-".join(module_steps.keys()) if module_steps else "conversion")
        # 如果探索产生了 trace，记录其路径
        _explore_trace_path = ""
        for _er in explored_results.values():
            if isinstance(_er, dict) and _er.get("_trace_path"):
                _explore_trace_path = _er["_trace_path"]
                break

        # 探索期 API 用例生成统计（探索自动生成 API 用例：normal + error 变体，聚合主/补充探索）
        # 注意：api_cases_generated 是 _explore_by_steps 返回 dict 的顶层键（results["api_cases_generated"]），
        # 不是模块级键——必须对顶层 dict 取 .get()，遍历 .values() 拿不到该统计（断链曾致恒为 0）
        api_cases_generated = {"generated": 0, "skipped": 0, "errors": 0}
        for _er in (explored_results, locals().get("_supple_results")):
            if isinstance(_er, dict) and isinstance(_er.get("api_cases_generated"), dict):
                _stats = _er["api_cases_generated"]
                for _k in api_cases_generated:
                    api_cases_generated[_k] += _stats.get(_k, 0)
        if api_cases_generated.get("generated"):
            logger.info(f"[FunctionalToUI] 本次转化探索共生成 API 用例 "
                        f"{api_cases_generated['generated']} 条（去重跳过 {api_cases_generated['skipped']}）")

        results = []
        status_counts = {"success": 0, "exploration_insufficient": 0,
                         "exploration_failed": 0, "conversion_failed": 0,
                         "steps_missing": 0}

        # ── 预检：收集可转化的用例 ──
        _pending = []  # (tc, module_kg, case_name, module, case_diagnostics, found_steps, missing_steps)
        for tc in test_cases:
            if cancel_check:
                _c = cancel_check()
                if inspect.isawaitable(_c): _c = await _c
                if _c: break

            tc_id = str(tc.id) if hasattr(tc, 'id') else str(getattr(tc, 'id', ''))
            module = getattr(tc, 'module', '') or '通用'
            case_name = getattr(tc, 'name', None) or getattr(tc, 'title', '未命名')

            module_kg = self._match_module_kg(all_exploration, module)

            if not module_kg:
                results.append({"test_case_id": tc_id, "case_name": case_name, "module": module,
                               "status": "exploration_failed", "error": "该模块未探索或无缓存数据",
                               "diagnostics": None, "script": None})
                status_counts["exploration_failed"] += 1
                continue
            if module_kg.get("insufficient"):
                results.append({"test_case_id": tc_id, "case_name": case_name, "module": module,
                               "status": "exploration_insufficient",
                               "error": module_kg.get("reason", "探索数据不足"), "diagnostics": None, "script": None})
                status_counts["exploration_insufficient"] += 1
                continue

            case_diagnostics = self._check_case_steps(tc, module_kg,
                                                      guided_steps=all_guided_steps.get(module))
            # 探索校正：以探索实际命中的页面文本为准回写用例步骤（落库后再转化，
            # 转化 prompt 读取的是校正后的 test_steps——用户定性 2026-08-23）
            try:
                self._correct_case_steps(self.db, tc, case_diagnostics)
            except Exception as _ce:
                logger.warning(f"[FunctionalToUI] 探索校正异常（不影响转化）: {_ce}")
            if case_diagnostics and tc_id in _supplemented_cases:
                # 经历过补充探索仍缺失 → 属用例本身问题（元素不存在/描述不符），如实标注
                for _d in case_diagnostics:
                    if _d.get("status") == "not_found":
                        _d["message"] = (f"✗ 未找到「{_d.get('target', '')}」— 补充探索后仍无法定位，"
                                         f"请检查用例描述或页面元素")
            missing_steps = [d for d in case_diagnostics if d.get("status") == "not_found"]
            found_steps = [d for d in case_diagnostics if d.get("status") == "success"]

            # 纯断言用例（全部步骤 skipped：无「」元素或「验证：」断言步骤）不拒绝转化——
            # 断言目标不需要探索依据（D3 复查修复 2026-08-25：此前只看 found==0，
            # 全部 skipped 的用例被误拒为「所有步骤元素均未找到」）
            if case_diagnostics and len(found_steps) == 0 and missing_steps:
                results.append({"test_case_id": tc_id, "case_name": case_name, "module": module,
                               "status": "steps_missing", "error": "所有步骤元素均未在页面上找到",
                               "diagnostics": {"total_steps": len(case_diagnostics), "found_steps": 0,
                                               "missing_steps": missing_steps, "step_details": case_diagnostics},
                               "script": None})
                status_counts["steps_missing"] += 1
                continue

            _pending.append((tc, module_kg, case_name, module, case_diagnostics, found_steps, missing_steps))

        # ── 批量转化：每 N 条一组共用一个 LLM 调用 ──
        # N 由项目探索配置 exploration_config.convert_batch_size 控制（默认 15）。
        # 批量越大单批输出越长，漏条/截断风险越高；可用项目配置按项目调节。
        try:
            _batch_size = int(explore_cfg.get("convert_batch_size") or 15)
            if _batch_size < 1:
                _batch_size = 15
        except (TypeError, ValueError):
            _batch_size = 15
        if phase_cb:
            try:
                phase_cb({"phase": "converting",
                          "phase_detail": f"AI 转化 {len(_pending)} 条用例（每批 {_batch_size} 条）"})
            except Exception:
                pass
        # 按模块分组切批（H1 复查修复 2026-08-25）：批量 prompt 的元素摘要/URL 映射
        # 来自 batch[0] 的 KG——跨模块混批会让非首模块用例拿错元素上下文（错页 URL、
        # 错 locator 清单）；同批同模块后每批上下文自洽。同模块内仍按 batch_size 分片。
        _pending_by_mod: Dict[str, list] = {}
        _mod_order: list = []
        for _t in _pending:
            _tm = _t[3]
            if _tm not in _pending_by_mod:
                _pending_by_mod[_tm] = []
                _mod_order.append(_tm)
            _pending_by_mod[_tm].append(_t)
        for _m in _mod_order:
            _mlist = _pending_by_mod[_m]
            for _bi in range(0, len(_mlist), _batch_size):
                _batch = _mlist[_bi:_bi + _batch_size]
                _batch_results = await self._convert_batch_v2(
                    _batch, explore_base_url, browser, viewport_size, headless,
                    script_type, script_language, project_id, shared_page_objects, cancel_check
                )
                for _br in _batch_results:
                    results.append(_br["result"])
                    status_counts[_br["status_key"]] += 1
                    if progress_callback:
                        try: progress_callback(_br["result"])
                        except Exception: pass
                    if _conv_trace:
                        try:
                            _conv_trace.log_conversion(
                                test_case_id=_br["result"]["test_case_id"],
                                case_name=_br["result"]["case_name"],
                                module=_br["result"]["module"],
                                before_steps=self._extract_raw_steps(_br.get("tc")),
                                after_spec=_br["result"].get("script", {}),
                                mode=_br.get("method", "v2"),
                                status=_br["result"]["status"],
                                diagnostics=_br["result"].get("diagnostics", {}),
                                error=_br["result"].get("error"),
                            )
                        except Exception:
                            pass

        # 口径：steps_missing（部分步骤未定位）不算成功——用例步骤不完整，仅报「部分未定位」
        success_count = status_counts.get("success", 0)
        logger.info(f"[FunctionalToUI] 转化完成: {status_counts}")

        # ── 转化后同步登录用例（仅校验不覆盖：导入时探索出的真实步骤是权威来源）──
        # 转化入口已由 _require_login_module 拦截（无登录模块文档的项目无法进入转化），
        # 故 __login__ 必然存在（import_login_module 成功路径三件套同存）——此分支仅防御性校验。
        # 不再创建硬编码模板（零硬编码规则：业务词/元素不得写死在代码里）。
        if success_count > 0:
            try:
                from app.core.models.web_ui_test import WebUITestCase as _WUI
                _login = self.db.query(_WUI).filter(
                    _WUI.test_case_id == '__login__',
                    _WUI.project_id == str(project_id),
                ).first()
                if _login:
                    logger.info("[FunctionalToUI] 已存在登录用例（保留导入时的真实步骤），跳过模板覆盖")
                else:
                    logger.warning("[FunctionalToUI] 未找到 __login__ 用例（异常状态：转化入口应已拦截），"
                                   "请重新导入登录模块后再转化")
                self.db.commit()
            except Exception:
                self.db.rollback()

        # ── 保存转化追踪日志 ──
        _ctp = ""
        try:
            _conv_trace.log_summary(status_counts)
            _ctp = _conv_trace.save()
            logger.info(f"[FunctionalToUI] ✓ 转化追踪日志已保存: {_ctp} ({len(_conv_trace._data.get('conversions',[]))} 条)")
        except Exception as _te:
            logger.warning(f"[FunctionalToUI] 转化追踪保存失败: {_te}")

        return {
            "success": success_count > 0,
            "results": results,
            "summary": status_counts,
            "success_count": success_count,
            "total_count": len(test_cases),
            "explored_modules": modules_to_explore,
            "cached_modules": list(cached_modules.keys()),
            "exploration_method": "step_driven" if modules_to_explore else "cached",
            "exploration_failures": exploration_failures if exploration_failures else None,
            "exploration_trace": _explore_trace_path or "",
            "conversion_trace": _ctp or "",
            "api_cases_generated": api_cases_generated,
        }

    # ========================================================================
    # 辅助方法
    # ========================================================================

    @staticmethod
    def _extract_raw_steps(test_case) -> List[Dict]:
        """从用例中提取原始步骤（JSON 格式）。"""
        import json as _j
        steps = getattr(test_case, 'test_steps', None)
        if not steps:
            return []
        if isinstance(steps, str):
            try:
                steps = _j.loads(steps)
            except _j.JSONDecodeError:
                return [{"raw": steps}]
        if isinstance(steps, list):
            return steps
        return []

    def _load_test_case(self, test_case_id: str):
        """加载功能测试用例（兼容两种模型；ReqTestCase 按【生效行】解析——方案B 逻辑 id 绑定）"""
        from app.core.models.requirement import TestCase as ReqTestCase
        from app.core.models.test_simple import SimpleTestCase
        from app.core.services.case_versioning import load_effective_case

        try:
            int(test_case_id)
        except ValueError:
            return self.db.query(SimpleTestCase).filter(SimpleTestCase.id == test_case_id).first()
        return load_effective_case(self.db, test_case_id)

    @staticmethod
    def _extract_project_id(test_case) -> Optional[int]:
        """从测试用例提取 project_id"""
        if hasattr(test_case, 'project_id'):
            return test_case.project_id
        return None

    @staticmethod
    def _extract_version_id(test_case) -> Optional[int]:
        """从测试用例提取 version_id"""
        if hasattr(test_case, 'version_id'):
            return test_case.version_id
        return None

    def _infer_version_id(self, project_id: int) -> Optional[int]:
        """当用例无 version_id 时，推断一个可用的版本ID"""
        if not project_id:
            return None
        from app.core.models.requirement import Version
        v = self.db.query(Version).filter(
            Version.project_id == project_id
        ).order_by(Version.created_at.desc()).first()
        return v.id if v else None

    def _get_llm(self):
        """懒加载 LLM 服务（用于步骤语义解析）。"""
        if not hasattr(self, '_llm_service'):
            try:
                from app.core.services.llm_service import LLMService
                self._llm_service = LLMService(self.db)
            except Exception:
                self._llm_service = None
        return self._llm_service

    def _load_exploration_config(self, project_id: int) -> Dict[str, Any]:
        """从 ProjectSetting 加载项目配置。支持多环境。"""
        psetting = self.db.query(ProjectSetting).filter(
            ProjectSetting.project_id == project_id
        ).first()
        if psetting and psetting.exploration_config:
            cfg = psetting.exploration_config
            if isinstance(cfg, dict):
                web_cfg = dict(cfg.get("web", {}) or {})
                if isinstance(web_cfg, dict):
                    # 多环境支持：用 active_environment 的 URL
                    if not web_cfg.get("base_url") and web_cfg.get("environments"):
                        active = web_cfg.get("active_environment", "")
                        envs = web_cfg.get("environments", [])
                        env = next((e for e in envs if e.get("name") == active), envs[0] if envs else None)
                        if env:
                            web_cfg["base_url"] = env.get("url", "")
                    return web_cfg
                return cfg
        return {}

    @staticmethod
    def _match_module_kg(all_exploration: Dict, module: str) -> Dict:
        """按模块名解析 KG 数据（精确优先，模糊回退；补充探索与预检共用）"""
        module_kg = all_exploration.get(module)
        if not module_kg:
            for m_name, m_data in all_exploration.items():
                if module in m_name or m_name in module:
                    module_kg = m_data
                    break
        return module_kg or {}

    def _extract_modules_from_cases(self, test_cases: list) -> Dict[str, List[str]]:
        """
        从测试用例中提取模块名及其涉及的元素名。
        从 test_steps 中提取操作目标作为 required_elements。

        Returns:
            {"模块名": ["元素1", "元素2", ...], ...}
        """
        import json as _json

        modules = {}
        for tc in test_cases:
            module = getattr(tc, 'module', '') or '通用'
            if module not in modules:
                modules[module] = []

            # 从测试步骤中提取操作目标
            steps = getattr(tc, 'test_steps', None)
            if not steps:
                continue

            if isinstance(steps, str):
                try:
                    steps = _json.loads(steps)
                except _json.JSONDecodeError:
                    continue

            if not isinstance(steps, list):
                continue

            for step in steps:
                if isinstance(step, dict):
                    action = step.get("action", "")
                    target = step.get("target", "")
                    desc = step.get("desc", step.get("description", ""))
                    expected = step.get("expected", step.get("expected_result", ""))

                    # 从 action/desc 中提取关键词作为元素名
                    for text in [target, action, desc, expected]:
                        if text and isinstance(text, str) and len(text) >= 2:
                            modules[module].append(text.strip())

            # 也加入用例名称和描述的词汇
            name = getattr(tc, 'name', None) or getattr(tc, 'title', '')
            desc = getattr(tc, 'description', '') or ''
            if name:
                modules[module].append(name)
            if desc:
                modules[module].append(desc)

        # 去重 + 清理
        for module in modules:
            modules[module] = list(set(modules[module]))[:30]  # 限制数量

        return modules

    # ========================================================================
    # 步骤驱动探索（新）
    # ========================================================================

    def _parse_and_group_steps(self, test_cases: list) -> Dict[str, List]:
        """解析步骤并按模块分组，同时保留“用例 -> 步骤”的一一对应关系。

        旧实现先把同模块所有用例步骤 flatten，再做全局去重，导致：
        1. Case A 的“搜索”把 Case B 的“搜索”吃掉；
        2. 不同页面状态的同名元素被错误合并；
        3. GuidedExplorationAgent 无法知道某一步属于哪个 TestCase。

        新实现仍返回 dict[str, list]，保持所有旧调用方兼容；每个 list 是
        CaseStepBatch，并额外携带 case_plans。CasePlan 才是探索的执行边界。
        """
        from app.core.services.step_parser import parse_steps
        from app.core.services.case_explorer import CasePlan, CaseStepBatch

        module_steps: Dict[str, CaseStepBatch] = {}
        llm = self._get_llm()

        for tc_index, tc in enumerate(test_cases or []):
            module = getattr(tc, 'module', '') or '通用'
            if module not in module_steps:
                module_steps[module] = CaseStepBatch()
            batch = module_steps[module]

            raw_steps = getattr(tc, 'test_steps', None)
            if isinstance(raw_steps, str):
                try:
                    raw_steps = json.loads(raw_steps)
                except Exception:
                    raw_steps = [raw_steps]
            if not isinstance(raw_steps, list):
                raw_steps = []

            guided = parse_steps(raw_steps, llm_service=llm)
            case_id = str(getattr(tc, 'id', '') or getattr(tc, 'case_id', '') or tc_index)
            case_steps = []
            for gs in guided:
                # GuidedStep 本身保持兼容；附加私有归属信息，不改变 dataclass 契约。
                try:
                    setattr(gs, '_case_id', case_id)
                    setattr(gs, '_case_index', tc_index)
                except Exception:
                    pass
                case_steps.append(gs)
                batch.append(gs)

            plan = CasePlan(
                case_id=case_id,
                case_name=getattr(tc, 'name', None) or getattr(tc, 'title', None) or f'用例{tc_index + 1}',
                module=module,
                preconditions=getattr(tc, 'preconditions', '') or '',
                expected_result=getattr(tc, 'expected_result', '') or '',
                start_url='',
                steps=case_steps,
                test_case_id=case_id,
                logical_case_id=str(getattr(tc, 'logical_case_id', '') or case_id),
                revision_no=int(getattr(tc, 'revision_no', 1) or 1),
                version_id=getattr(tc, 'version_id', None),
                project_id=getattr(tc, 'project_id', None),
            )
            batch.case_plans.append(plan)

        # 只在“同一个 Case、同一个页面段”内去重。
        # 页面边界由 navigate/go_back/reload 标记；不同 Case 永不互相去重。
        boundary = {'navigate', 'go_back', 'reload'}
        for module, batch in module_steps.items():
            case_plans = list(batch.case_plans)
            rebuilt = CaseStepBatch(case_plans=case_plans)
            for plan in case_plans:
                seen = set()
                unique_steps = []
                for gs in plan.steps:
                    at = str(getattr(gs, 'action_type', '') or '').lower()
                    target = str(getattr(gs, 'target_text', '') or '').strip()
                    if at in boundary:
                        seen.clear()
                        unique_steps.append(gs)
                        rebuilt.append(gs)
                        continue
                    if at in ('fill', 'select'):
                        value = (getattr(gs, 'fill_value', '') or getattr(gs, 'select_option', '') or '').strip()
                        key = (at, target, value)
                    else:
                        key = (at, target)
                    if key not in seen:
                        seen.add(key)
                        unique_steps.append(gs)
                        rebuilt.append(gs)
                plan.steps = unique_steps
            module_steps[module] = rebuilt
            logger.info(
                f"[FunctionalToUI] Case-aware步骤解析: 模块={module}, "
                f"cases={len(case_plans)}, raw={len(batch)}, unique={len(rebuilt)}"
            )

        return module_steps

    @staticmethod
    def _parse_viewport(viewport_size: str, fallback_w: int, fallback_h: int) -> tuple:
        """解析 "1920x1080" → (width, height)；无效/空时回退默认。"""
        try:
            w, h = str(viewport_size or "").lower().split("x")
            w, h = int(w), int(h)
            if w > 0 and h > 0:
                return w, h
        except (ValueError, AttributeError):
            pass
        return fallback_w, fallback_h

    @staticmethod
    def _resolve_browser_factory(pw_module, browser_name: str):
        """按浏览器名解析 launch 工厂（白名单校验，非法回退 chromium）。"""
        _name = str(browser_name or "").lower()
        _factory = getattr(pw_module, _name, None) if _name in ("chromium", "firefox", "webkit") else None
        if _factory is None:
            _factory = pw_module.chromium
            if _name and _name != "chromium":
                logger.warning(f"[FunctionalToUI] 未知浏览器 '{browser_name}'，回退 chromium")
        return _factory

    async def _explore_by_steps(
        self,
        module_steps: Dict[str, List],
        base_url: str,
        username: str,
        password: str,
        project_id: int,
        version_id: int,
        headless: bool = False,
        browser: str = "chromium",
        viewport_size: str = "",
        test_cases: list = None,
        platform_type: str = "web",
        phase_cb=None,        # callable(dict) → 阶段进度事件（模块/步骤级，探索线程内调用）
        cancel_check=None,    # callable → bool, True=用户取消转化，探索立即停止（透传 explore_guided）
    ) -> Dict[str, Dict]:
        """步骤驱动探索：登录 → 每个模块按步骤逐条探索 → 填充 KG。

        遵循与 BusinessFlowUIService._explore_async 相同的登录引导模式，
        但用 GuidedExplorationAgent 替代 BFSExplorer。
        browser/viewport_size：前端弹窗选择的探索浏览器与视口（默认 chromium + 项目配置视口）。
        """
        import concurrent.futures
        import asyncio as _aio

        def _do_explore():
            _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
            loop = _aio.new_event_loop()
            _aio.set_event_loop(loop)
            return loop.run_until_complete(
                self._explore_by_steps_async(
                    module_steps, base_url, username, password,
                    project_id, version_id, headless, browser, viewport_size,
                    test_cases, platform_type, phase_cb, cancel_check,
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await _aio.get_event_loop().run_in_executor(pool, _do_explore)

    async def _explore_by_steps_async(
        self,
        module_steps: Dict[str, List],
        base_url: str,
        username: str,
        password: str,
        project_id: int,
        version_id: int,
        headless: bool,
        browser: str = "chromium",
        viewport_size: str = "",
        test_cases: list = None,
        platform_type: str = "web",
        phase_cb=None,        # callable(dict) → 阶段进度事件（透传给 _run_sync_exploration）
        cancel_check=None,    # callable → bool, True=用户取消转化，探索立即停止
    ) -> Dict[str, Dict]:
        """Async 步骤驱动探索。"""
        results = {}

        # 非 Web 平台暂不支持自动探索
        if platform_type not in ("web", ""):
            logger.warning(f"[FunctionalToUI] Platform '{platform_type}' not supported for auto-exploration")
            for m in module_steps:
                results[m] = {"error": f"平台「{platform_type}」暂不支持自动探索", "module": m}
            return results, {}

        from playwright.async_api import async_playwright
        from app.core.services.login_engine import login_with_ui_case
        from app.core.services.exploration_config import WebExplorationConfig
        from app.core.services.guided_exploration_agent import GuidedExplorationAgent
        from app.core.services.mcp_client import MCPClient
        from app.core.services.kg_populator import KGPopulator
        from app.core.models.knowledge_graph import KnowledgeGraph
        from app.core.models.project_ext import ProjectSetting
        from app.core.database import SessionLocal
        from datetime import datetime as dt

        db = SessionLocal()

        # 提前创建 config（用于 viewport 等参数）——零硬编码：
        # web 段 5 键白名单合并（向后兼容）+ explore 段全量覆盖（任意配置字段可定制，换项目不改代码）
        config = WebExplorationConfig()
        web_cfg = {}
        try:
            psetting = db.query(ProjectSetting).filter(
                ProjectSetting.project_id == project_id
            ).first()
            web_cfg = (psetting.exploration_config or {}).get("web", {}) if psetting else {}
            for key in ('noise_keywords', 'danger_keywords', 'modal_trigger_keywords',
                        'search_button_keywords', 'form_fill_values'):
                if key in web_cfg and web_cfg[key]:
                    existing = getattr(config, key, []) or []
                    merged = list(existing)
                    for v in (web_cfg[key] or []):
                        if v not in merged:
                            merged.append(v)
                    setattr(config, key, merged)
            if 'element_synonyms' in web_cfg and web_cfg['element_synonyms']:
                existing_syn = getattr(config, 'element_synonyms', {}) or {}
                for k, v in (web_cfg['element_synonyms'] or {}).items():
                    if k in existing_syn:
                        existing_syn[k] = list(set(existing_syn[k] + v))
                    else:
                        existing_syn[k] = v
                setattr(config, 'element_synonyms', existing_syn)
            config.apply_overrides((psetting.exploration_config or {}).get("explore") or {})
        except Exception:
            pass

        try:
            async with async_playwright() as pw:
                _vw, _vh = self._parse_viewport(viewport_size, config.viewport_width, config.viewport_height)
                _browser_factory = self._resolve_browser_factory(pw, browser)
                browser = await _browser_factory.launch(
                    headless=headless,
                    args=["--start-maximized"] if not headless else [],
                )
                ctx = await browser.new_context(
                    viewport={"width": _vw, "height": _vh},
                )
                page = await ctx.new_page()

                # 用 __login__ UI 用例步骤执行登录（项目隔离）
                login_ok, workbench_url = await login_with_ui_case(
                    page, base_url, username, password, project_id=project_id
                )
                if not login_ok or not workbench_url:
                    logger.error("[FunctionalToUI] Login failed for step-driven exploration")
                    for m in module_steps:
                        results[m] = {"error": "登录失败——请先导入登录模块", "module": m}
                    return results, {}

                # 导出登录态供 sync 浏览器复用
                state = await page.context.storage_state()
                import json as _json
                storage_state_str = _json.dumps(state, ensure_ascii=False)
                state_dict = _json.loads(storage_state_str) if storage_state_str else None
                await browser.close()

            # ── Sync Playwright 必须在独立线程中运行（不能直接在 async 上下文中）──
            import concurrent.futures as _cf
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                _cf.ThreadPoolExecutor(max_workers=1),
                lambda: self._run_sync_exploration(
                    workbench_url, state_dict, module_steps, config,
                    project_id, version_id, base_url, username, password,
                    platform_type, test_cases, db, headless, browser, viewport_size,
                    phase_cb, cancel_check,
                )
            )

        except Exception as e:
            import traceback as _tb
            logger.error(f"[FunctionalToUI] Step-driven exploration error: {type(e).__name__}: {e}\n{_tb.format_exc()}")
            return results, {}
        finally:
            db.close()

    @staticmethod
    def _run_sync_exploration(workbench_url, state_dict, module_steps, config,
                              project_id, version_id, base_url, username, password,
                              platform_type, test_cases, db, headless,
                              browser="chromium", viewport_size="",
                              phase_cb=None, cancel_check=None):
        """在独立线程中运行 sync Playwright 探索（脱离 asyncio 事件循环）。

        browser/viewport_size：前端弹窗选择的探索浏览器与视口（默认 chromium + 项目配置视口）。
        phase_cb：阶段进度回调（探索线程内调用，dict 写入线程安全；前端进度条在长探索期间保持移动）。
        cancel_check：取消回调——用户点击「取消转化」→ True → 探索立即停止，
            取消后跳过 KG 写入与 API 用例落库，finally 关浏览器结束整个生成流程。
        """
        from playwright.sync_api import sync_playwright
        from app.core.services.guided_exploration_agent import GuidedExplorationAgent
        from app.core.services.mcp_client import MCPClient
        from app.core.services.evidence_kg_writer import EvidenceKGWriter
        from app.core.services.api_flow_capture import ApiFlowCapture
        from app.core.models.knowledge_graph import KnowledgeGraph

        results = {}
        pw_sync = None
        browser_sync = None
        try:
            pw_sync = sync_playwright().start()
            _vw, _vh = FunctionalToUIService._parse_viewport(viewport_size, config.viewport_width, config.viewport_height)
            _browser_factory = FunctionalToUIService._resolve_browser_factory(pw_sync, browser)
            browser_sync = _browser_factory.launch(
                headless=headless,
                args=["--start-maximized"] if not headless else [],
            )
            ctx_sync = browser_sync.new_context(
                viewport={"width": _vw, "height": _vh},
                storage_state=state_dict,
            )
            page_sync = ctx_sync.new_page()

            # 首屏 workbench 加载会立即触发组织/用户等 XHR。先绑定首个实际模块，
            # 避免这些接口被错误命名为“探索”。
            _initial_module = next((str(m) for m, steps in module_steps.items() if steps and str(m).strip()), "")
            capture = ApiFlowCapture(ctx_sync, config, project_id, base_url, db)
            capture.set_module(_initial_module)
            page_sync.goto(workbench_url, wait_until="domcontentloaded", timeout=config.page_goto_timeout)

            # 等待 SPA 渲染
            FunctionalToUIService._wait_spa_render_sync(
                page_sync, min_len=config.spa_render_min_len,
                max_rounds=config.spa_render_max_rounds,
                interval=config.spa_render_interval)

            populator = EvidenceKGWriter(db)
            all_exploration_results = {}
            all_guided_steps = {}

            _mod_total = sum(1 for _s in module_steps.values() if _s)
            _mi = 0
            for module_name, guided_steps in module_steps.items():
                # 取消检查：用户点击「取消转化」→ 停止后续模块探索（当前模块由
                # explore_guided 内部 cancel_check 在步骤间停止；浏览器 finally 关闭）
                if cancel_check:
                    try:
                        if cancel_check():
                            logger.warning(f"[FunctionalToUI] 收到取消信号，停止探索模块循环")
                            break
                    except Exception:
                        pass
                if not guided_steps:
                    logger.warning(f"[FunctionalToUI] 模块 '{module_name}' 无有效步骤，跳过")
                    continue
                _mi += 1

                # 阶段进度：模块开始/完成/步骤级三档事件（前端进度条据此移动）
                if phase_cb:
                    try:
                        phase_cb({
                            "phase": "exploring",
                            "phase_detail": f"探索模块 {_mi}/{_mod_total}：{module_name}（{len(guided_steps)} 步）",
                            "explored_done": _mi - 1, "explored_total": _mod_total,
                            "step_done": 0, "step_total": len(guided_steps),
                        })
                    except Exception:
                        pass

                capture.set_module(module_name)
                logger.info(f"[FunctionalToUI] 步骤驱动探索: '{module_name}' ({len(guided_steps)} steps)")
                from app.core.services.trace_logger import TraceLogger
                trace = TraceLogger(module_name=module_name)
                trace.log_exploration_start(module_name, len(guided_steps), workbench_url)
                start_url = workbench_url
                if module_name not in config.home_module_names:
                    try:
                        # sync 版 evaluate 只接受单个参数——参数必须合并成 dict
                        # （此前分传 2 个位置参数必抛 TypeError，模块导航一直静默失败降级）
                        nav_clicked = page_sync.evaluate("""\
                            (params) => {
                                const name = (params.name || '').replace(/\\s+/g, '');
                                if (!name) return false;  // 空模块名不导航，避免乱点
                                const maxChildren = params.maxChildren;
                                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                                let best = null, bestLen = Infinity;
                                while (walker.nextNode()) {
                                    const el = walker.currentNode;
                                    if (el.offsetParent === null || el.children.length > maxChildren) continue;
                                    const t = (el.textContent || '').replace(/\\s+/g, '');
                                    if (!t) continue;
                                    // 归一化后模糊匹配：模块名可能带“模块/管理”等通用后缀而菜单文本不带
                                    // （“患者档案模块” vs 菜单“患者档案”），或反向带前缀。用“互相包含”判定。
                                    const hit = (t === name) || (name && name.includes(t)) || (t && t.includes(name));
                                    if (hit && t.length < bestLen && t.length >= Math.min(2, name.length)) { best = el; bestLen = t.length; }
                                }
                                if (best) { (best.closest('li') || best.closest('[onclick]') || best).click(); return true; }
                                return false;
                            }
                        """, {"name": module_name, "maxChildren": config.nav_max_children})
                        if nav_clicked:
                            # SPA 渲染等待（替代固定 3s 硬等——快慢页面都稳）+ URL 变化校验
                            FunctionalToUIService._wait_spa_render_sync(
                                page_sync, min_len=config.spa_render_min_len,
                                max_rounds=config.spa_render_max_rounds,
                                interval=config.spa_render_interval)
                            _nav_url = page_sync.url
                            if _nav_url and _nav_url != workbench_url:
                                start_url = _nav_url
                                logger.info(f"[FunctionalToUI] 已导航到模块 '{module_name}': {_nav_url[-60:]}")
                            else:
                                logger.warning(f"[FunctionalToUI] 导航 '{module_name}' 后 URL 未变化"
                                               f"（仍为 {workbench_url}），继续在当前页探索")
                        else:
                            # 精确/模糊匹配均未命中：显式告警（此前静默降级停 workpanel，
                            # 是“反复卡工作台、元素大量 not_found”的直接诱因之一）
                            logger.warning(f"[FunctionalToUI] 预导航未找到模块 '{module_name}' 菜单项，"
                                           f"将从工作台起步（靠用例入口导航步骤进入）")
                    except Exception as e:
                        logger.warning(f"[FunctionalToUI] Navigate to module '{module_name}' failed: {e}")

                # E2 复查修复 2026-08-25：模块间显式页面复位——导航失败/不导航时
                # 浏览器仍停在前一模块的最后页面（start_url 只是记录值，explore_guided
                # 从不 goto 回去），第一步定位会直接跑在错误页面上、诊断却归入本模块。
                # 当前 URL 与目标不一致则显式拉回（导航成功时二者一致，goto 空转可忽略）
                try:
                    if page_sync.url != start_url:
                        page_sync.goto(start_url, wait_until="domcontentloaded",
                                       timeout=config.page_goto_timeout)
                except Exception as _nav_e:
                    logger.warning(f"[FunctionalToUI] 模块 '{module_name}' 页面复位失败: {_nav_e}")

                try:
                    client = MCPClient(page_sync, config)
                    agent = GuidedExplorationAgent(client, config, llm_service=None,
                                                   module_name=module_name, platform_type=platform_type, db=db)
                    agent.set_case_contexts(test_cases or [])

                    def _step_cb(ev: dict):
                        if phase_cb:
                            try:
                                phase_cb({
                                    "phase": "exploring",
                                    "phase_detail": f"探索模块 {_mi}/{_mod_total}：{module_name}"
                                                    f"（步骤 {ev.get('step_done', 0)}/{ev.get('step_total', 0)}）",
                                    "explored_done": _mi - 1, "explored_total": _mod_total,
                                    "step_done": ev.get("step_done", 0),
                                    "step_total": ev.get("step_total", 0),
                                })
                            except Exception:
                                pass

                    exploration_result = agent.explore_guided(
                        guided_steps=guided_steps, start_url=start_url, trace_logger=trace,
                        progress_cb=_step_cb if phase_cb else None,
                        cancel_check=cancel_check)
                    results[module_name] = exploration_result
                    all_exploration_results[module_name] = exploration_result
                    all_guided_steps[module_name] = guided_steps
                    trace.log_exploration_done(exploration_result.get("stats", {}))
                    logger.info(f"[FunctionalToUI] Module '{module_name}' explored: "
                               f"{exploration_result.get('stats', {}).get('total_elements', 0)} elements")
                except Exception as e:
                    import traceback as _tb
                    logger.error(f"[FunctionalToUI] Step-driven exploration failed for '{module_name}': {e}\n{_tb.format_exc()}")
                    results[module_name] = {"error": str(e), "module": module_name}

                # 模块完成事件（步骤内异常也照报，避免进度条停在模块中间）
                if phase_cb:
                    try:
                        phase_cb({
                            "phase": "exploring",
                            "phase_detail": f"模块 {_mi}/{_mod_total}「{module_name}」探索完成",
                            "explored_done": _mi, "explored_total": _mod_total,
                        })
                    except Exception:
                        pass

            # 取消后不再落库（KG/API 用例/登录态均跳过——用户已取消，不产生半成品数据）
            if cancel_check:
                try:
                    _cancelled_now = bool(cancel_check())
                except Exception:
                    _cancelled_now = False
            else:
                _cancelled_now = False

            # 合并写入 KG（H3 复查修复 2026-08-25：逐模块 populate——此前合并全部模块
            # 后一次性 populate，module_name 是「模块A, 模块B」逗号串 → 快照模块字段
            # 变成逗号串 → _query_existing_kg 按 module_name 模糊匹配时每个模块都命中
            # 全部快照 → 元素/URL 映射跨模块污染，转化 prompt 拿到别模块的 locator）
            if all_exploration_results and not _cancelled_now:
                for _m_name, _m_result in all_exploration_results.items():
                    try:
                        populator.populate(
                            project_id=project_id, version_id=version_id,
                            module_name=_m_name,
                            exploration_result=_m_result,
                            guided_steps=all_guided_steps.get(_m_name) or [],
                            test_cases=test_cases, base_url=base_url, username=username,
                            platform_type=platform_type, auth_data=None,
                            replace_mode='auto',
                            explored_modules=list(all_exploration_results.keys()),
                        )
                    except Exception as e:
                        import traceback as _tb
                        logger.error(f"[FunctionalToUI] KG population failed for '{_m_name}': {e}\n{_tb.format_exc()}")
                logger.info(f"[FunctionalToUI] KG populated with {len(all_exploration_results)} modules")

            # 探索完成：捕获的 API 接口生成用例落库（normal + 主动构造 error 变体）
            # 结果写入 results["api_cases_generated"]（独立 key，不参与模块结果合并）
            # 取消后跳过（用户已取消，不落半成品 API 用例）
            if _cancelled_now:
                logger.info("[FunctionalToUI] 已取消，跳过探索期 API 用例落库")
            else:
                try:
                    api_stats = capture.flush_to_db(db, project_id, base_url, version_id=version_id)
                    if api_stats.get("generated") or api_stats.get("skipped"):
                        logger.info(
                            f"[FunctionalToUI] 探索生成 API 用例: 生成 {api_stats.get('generated', 0)} 条, "
                            f"去重跳过 {api_stats.get('skipped', 0)} 条"
                        )
                    results["api_cases_generated"] = api_stats
                except Exception as e:
                    import traceback as _tb
                    logger.error(f"[FunctionalToUI] 探索生成 API 用例失败: {e}\n{_tb.format_exc()}")
                    results["api_cases_generated"] = {"generated": 0, "skipped": 0, "errors": 1}

            # 更新 auth_data（项目唯一行，按 project_id 查；
            # 取最近完成的 KG——running 中的行由其他探索管线持有，不应写入；
            # 取消后跳过——用户已取消整个生成流程，不写登录态）
            try:
                if state_dict and not _cancelled_now:
                    kg = db.query(KnowledgeGraph).filter(
                        KnowledgeGraph.project_id == project_id,
                        KnowledgeGraph.exploration_status == "completed",
                    ).order_by(KnowledgeGraph.completed_at.desc()).first()
                    if kg:
                        kg.auth_data = state_dict
                        db.commit()
            except Exception:
                pass

        except Exception as e:
            import traceback as _tb
            logger.error(f"[FunctionalToUI] Sync exploration error: {type(e).__name__}: {e}\n{_tb.format_exc()}")
        finally:
            if browser_sync:
                try: browser_sync.close()
                except Exception: pass
            if pw_sync:
                try: pw_sync.stop()
                except Exception: pass
            # 保存探索追踪日志
            try:
                if 'trace' in locals():
                    _tp = trace.save()
                    logger.info(f"[FunctionalToUI] 探索追踪日志: {_tp}")
                    results["_trace_path"] = _tp
            except Exception:
                pass

        # 返回探索侧解析结果（含 LLM 指代推断）供预检复用（H4 修复 2026-08-25：
        # 预检 _check_case_steps 若重新 parse_single_step 会丢失指代推断，永远匹配不到）
        return results, (locals().get('all_guided_steps') or {})

    @staticmethod
    def _wait_spa_render_sync(page, min_len=200, max_rounds=15, interval=1000):
        """等待 SPA 渲染完成（同步版）。"""
        last_len = 0
        for _ in range(max_rounds):
            page.wait_for_timeout(interval)
            try:
                cur_len = page.evaluate("() => document.body ? document.body.innerText.length : 0")
            except Exception:
                cur_len = 0
            if cur_len >= min_len and cur_len == last_len:
                return True
            last_len = cur_len
        return True  # 即使不完美也继续

    @staticmethod
    def _merge_exploration_results(all_results: Dict[str, Dict]) -> Dict:
        """合并多个模块的探索结果为统一格式。

        将各模块的 site_map、element_jumps、deep_dive、state_graph 等合并到一起。
        """
        merged = {
            "site_map": {"modules": []},
            "element_jumps": {},
            "deep_dive": {
                "dropdowns": {},
                "modals": [],
                "tables": [],
                "pagination": [],
                "forms": [],
                "api_endpoints": [],
            },
            "stats": {
                "total_elements": 0,
                "navigated_elements": 0,
                "pages_explored": 0,
                "visited_states": 0,
                "elapsed_seconds": 0,
                "errors": 0,
                "guided_steps_total": 0,
                "guided_steps_executed": 0,
                "exploration_mode": "guided",
                # F2 修复 2026-08-25：探索中断原因透传（任一模块中断即整体标中断——
                # 静默中断事故：99 步只执行 35 步，中断必须可观测到落库告警）
                "interrupted": "",
            },
            "pages_visited": [],
            "error_events": [],
            "state_graph": [],
            "step_diagnostics": [],
        }

        seen_urls = set()
        for module_name, result in all_results.items():
            if not isinstance(result, dict):
                continue

            # site_map
            sm = result.get("site_map", {})
            for m in sm.get("modules", []):
                if isinstance(m, dict):
                    merged["site_map"]["modules"].append({
                        **m, "source_module": module_name,
                    })

            # element_jumps
            merged["element_jumps"][module_name] = result.get("element_jumps", {}).get(
                "_main", {"url": "", "elements": []}
            )

            # deep_dive
            dd = result.get("deep_dive", {})
            if isinstance(dd.get("dropdowns"), dict):
                merged["deep_dive"]["dropdowns"].update(dd["dropdowns"])
            for key in ("modals", "tables", "pagination", "forms", "api_endpoints"):
                items = dd.get(key, [])
                merged["deep_dive"][key].extend([i for i in items if isinstance(i, dict)])

            # stats
            s = result.get("stats", {})
            for key in ("total_elements", "navigated_elements", "pages_explored", "errors",
                       "guided_steps_total", "guided_steps_executed"):
                merged["stats"][key] += s.get(key, 0)
            merged["stats"]["elapsed_seconds"] += s.get("elapsed_seconds", 0)
            # F2 修复 2026-08-25：interrupted 保留首个非空原因（模块间不叠加）
            if s.get("interrupted") and not merged["stats"].get("interrupted"):
                merged["stats"]["interrupted"] = s["interrupted"]

            # pages_visited
            for url in result.get("pages_visited", []):
                if url not in seen_urls:
                    seen_urls.add(url)
                    merged["pages_visited"].append(url)

            # error_events
            merged["error_events"].extend(result.get("error_events", []))

            # step_diagnostics (标记来源模块)
            for diag in result.get("step_diagnostics", []):
                merged["step_diagnostics"].append({**diag, "_module": module_name})

            # state_graph
            for sn in result.get("state_graph", []):
                merged["state_graph"].append({**sn, "_module": module_name})

        merged["stats"]["pages_explored"] = len(merged["pages_visited"])
        merged["stats"]["visited_states"] = len(merged["state_graph"])
        return merged

    # ========================================================================
    # KG 查询 + 覆盖度检查
    # ========================================================================

    def _query_existing_kg(
        self, project_id: int, version_id: int,
        module_name: str, config_snapshot: dict = None
    ) -> Optional[Dict]:
        """
        查询该项目下的已完成探索结果（知识图谱是项目级资产，UNIQUE(project_id)）。

        version_id 保留仅为兼容调用签名（已不再参与过滤）。
        关键改进：按模块名匹配 ExplorationPageSnapshot，只返回该模块的专属数据。
        这样版本迭代新增的模块不会误命中旧模块的探索数据。
        """
        kg = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
            KnowledgeGraph.exploration_status == "completed",
        ).order_by(KnowledgeGraph.completed_at.desc()).first()

        if not kg:
            return None

        # 配置变更检测：URL 或用户名变了 → 缓存失效
        if config_snapshot:
            if (kg.base_url != config_snapshot.get("base_url") or
                    kg.login_username != config_snapshot.get("username")):
                logger.info(f"[FunctionalToUI] 模块 '{module_name}' 配置已变更，缓存失效")
                return None

        # === 按模块名筛选 ExplorationPageSnapshot ===
        all_snapshots = (
            self.db.query(ExplorationPageSnapshot)
            .filter(ExplorationPageSnapshot.graph_id == kg.id)
            .all()
        )

        # 筛选与模块名匹配的 snapshot
        module_snapshots = []
        for snap in all_snapshots:
            snap_module = (snap.page_name or snap.page_title or "").strip()
            if not snap_module:
                # 也尝试从 snapshot_data JSON 中提取 module 字段
                snap_data = getattr(snap, 'snapshot_data', None)
                if isinstance(snap_data, dict):
                    snap_module = snap_data.get("module", "").strip()
            if not snap_module:
                continue
            # 模糊匹配：模块名互相包含
            if module_name in snap_module or snap_module in module_name:
                module_snapshots.append(snap)

        if not module_snapshots:
            # 没有该模块的专属探索数据
            logger.info(f"[FunctionalToUI] 模块 '{module_name}' 在 KG 中无匹配的探索数据 "
                        f"(共 {len(all_snapshots)} 个 snapshot)")
            return {
                "module": module_name,
                "elements": [],
                "pages": [],
                "modals": [],
                "filter_options": {},
                "kg_id": kg.id,
                "snapshot_count": 0,
            }

        # 收集该模块的元素和页面
        elements = []
        pages = []
        for snap in module_snapshots:
            if snap.elements and isinstance(snap.elements, list):
                elements.extend(snap.elements)
            if snap.buttons and isinstance(snap.buttons, list):
                elements.append({"buttons": snap.buttons})
            if snap.links and isinstance(snap.links, list):
                elements.append({"links": snap.links})
            if snap.page_url:
                pages.append(snap.page_url)

        # 不再回退到项目级 kg.elements：该列表可能包含其他模块元素，
        # 一旦回退会造成跨模块 locator 污染。缺元素应触发补充探索。
        if not pages:
            pages = [kg.base_url] if kg.base_url else []

        # 提取持久化的步骤诊断（储存在 KG flows 中，按模块分 flow：
        # __step_diagnostics__:{module}，F1 修复 2026-08-25——单一 flow 跨批次覆盖
        # 导致其他模块诊断丢失、转化误判「探索未覆盖此步骤」震荡）
        # 旧格式 __step_diagnostics__（无后缀）仅存量库回退：写入侧合并时已剔除，
        # 新格式 flow 出现时旧格式必然不存在，无新旧并存污染
        step_diagnostics = []
        if kg.flows and isinstance(kg.flows, list):
            from app.core.services.kg_populator import STEP_DIAG_FLOW_PREFIX
            _flow_mod = f"{STEP_DIAG_FLOW_PREFIX}{module_name}"
            for flow in kg.flows:
                if isinstance(flow, dict) and flow.get("flow_name") == _flow_mod:
                    step_diagnostics = flow.get("steps", [])
                    break
            else:
                for flow in kg.flows:
                    if isinstance(flow, dict) and flow.get("flow_name") == "__step_diagnostics__":
                        step_diagnostics = flow.get("steps", [])
                        break

        logger.info(f"[FunctionalToUI] 模块 '{module_name}' 命中 {len(module_snapshots)} 个 snapshot, "
                    f"{len(elements)} 组元素, {len(pages)} 个页面, {len(step_diagnostics)} 条步骤诊断")

        return {
            "module": module_name,
            "elements": elements,
            "filter_options": {},
            "pages": pages,
            "modals": [],
            "kg_id": kg.id,
            "snapshot_count": len(module_snapshots),
            "step_diagnostics": step_diagnostics,
        }

    @staticmethod
    def _coverage_sufficient(kg_result: Dict, required_elements: List[str]) -> bool:
        """严格按“步骤可验证覆盖”判断缓存是否可复用。

        仅有 page/snapshot 不能代表某个 TestCase 的元素已经探索过；否则版本新增
        用例会误命中旧模块缓存，最终 UI 转化得到 locator 但执行时找不到。
        """
        if not kg_result:
            return False
        elements = kg_result.get("elements", []) if isinstance(kg_result, dict) else []
        diagnostics = kg_result.get("step_diagnostics", []) if isinstance(kg_result, dict) else []
        if not isinstance(elements, list): elements = []
        if not isinstance(diagnostics, list): diagnostics = []

        targets = []
        for step in required_elements or []:
            if isinstance(step, str):
                t = step.strip()
            else:
                t = str(getattr(step, "target_text", "") or "").strip()
            if t and t not in targets:
                targets.append(t)
        # 纯验证/空步骤没有 locator 要求；只要模块有真实 snapshot 即可。
        if not targets:
            return bool(kg_result.get("snapshot_count", 0) or kg_result.get("pages"))

        def norm(v):
            return "".join(str(v or "").split()).lower()
        element_texts = []
        for e in elements:
            if not isinstance(e, dict): continue
            for k in ("name", "element_name", "text", "locator_text", "actual_text"):
                if e.get(k): element_texts.append(norm(e.get(k)))
        success_targets = {norm(d.get("target")) for d in diagnostics if isinstance(d, dict) and d.get("status") == "success"}
        success_actual = {norm(d.get("actual_text")) for d in diagnostics if isinstance(d, dict) and d.get("status") == "success" and d.get("actual_text")}

        missing = []
        for target in targets:
            nt = norm(target)
            covered = nt in success_targets or nt in success_actual
            if not covered:
                covered = any(nt == x or nt in x or x in nt for x in element_texts if x)
            if not covered:
                missing.append(target)
        if missing:
            logger.info(f"[FunctionalToUI] 模块 '{kg_result.get('module','')}' 缓存缺失步骤元素: {missing[:10]}")
            return False
        return True

    @staticmethod
    def _exploration_has_usable_data(exploration_result) -> bool:
        """
        检查探索结果是否包含可用的元素/页面数据。

        兼容两种探索结果格式:
        - BFS (旧): {"elements": [...], "pages": [...]}
        - 步骤驱动 (新): {"element_jumps": {...}, "pages_visited": [...], "stats": {...}}
        """
        if not exploration_result or not isinstance(exploration_result, dict):
            return False
        if exploration_result.get("error"):
            return False

        # 步骤驱动探索结果
        jumps = exploration_result.get("element_jumps", {})
        if isinstance(jumps, dict):
            for mod_data in jumps.values():
                if isinstance(mod_data, dict) and mod_data.get("elements"):
                    return True

        pages = exploration_result.get("pages_visited", [])
        if isinstance(pages, list) and len(pages) > 0:
            return True

        # 旧 BFS 格式兼容
        elements = exploration_result.get("elements", [])
        if isinstance(elements, list) and len(elements) > 0:
            return True
        old_pages = exploration_result.get("pages", [])
        if isinstance(old_pages, list) and len(old_pages) > 0:
            return True

        # 有统计数据且有成功执行的步骤
        stats = exploration_result.get("stats", {})
        if stats.get("total_elements", 0) > 0 or stats.get("guided_steps_executed", 0) > 0:
            return True

        return False

    # ========================================================================
    # 步骤诊断映射
    # ========================================================================

    @staticmethod
    def _check_case_steps(tc, module_kg: Dict, guided_steps: Optional[list] = None) -> List[Dict]:
        """将探索的步骤诊断映射回单个测试用例。

        解析用例的 test_steps，对每一步检查在探索中是否成功定位。
        匹配时同时检查 target_text 和 actual_text（页面真实文本）。
        guided_steps: 探索侧已解析的引导步骤（含 LLM 指代推断）——指代步骤
            （「点击该条预警」）在探索侧被推断为具体元素（「佩戴预警」），预检
            若用 parse_single_step 重解析只会得到原始指代文本，永远匹配不到诊断
            （H4 复查修复 2026-08-25：与探索侧解析断链，指代用例被误标 steps_missing）。
            探索侧解析结果按 seq 覆盖预检解析；多步骤共用同一 seq 时以预检为准。
        """
        from app.core.services.step_parser import parse_single_step

        diagnostics = []
        # (target_text, action_type) → 诊断列表（同 key 多条全保留——跨页面段同名
        # 元素是页面段去重的有意保留，dict 后写覆盖会把 success/not_found 吞成一条，
        # 误判已定位或未定位；E3 复查修复 2026-08-25）
        step_diag_map = {}
        actual_text_map = {}

        def _best_diag(candidates):
            """同 key 多条诊断取「任一 success」，无 success 取首条（not_found/failed 可辨识）。"""
            if not candidates:
                return None
            for d in candidates:
                if d.get("status") == "success":
                    return d
            return candidates[0]

        # 构建探索诊断查找表（双重索引，值均为列表）
        for diag in module_kg.get("step_diagnostics", []):
            key = (diag.get("target", ""), diag.get("action", ""))
            step_diag_map.setdefault(key, []).append(diag)
            # 也按页面上实际找到的文本索引
            actual = diag.get("actual_text", "")
            if actual and actual != diag.get("target", ""):
                actual_text_map.setdefault((actual, diag.get("action", "")), []).append(diag)

        # 探索侧解析结果按 seq 建立索引（LLM 指代推断后的真实目标）
        _guided_by_seq = {}
        if guided_steps:
            for _gs in guided_steps:
                _s = getattr(_gs, 'seq', None)
                if _s is not None:
                    _guided_by_seq[_s] = _gs

        # 解析用例步骤
        steps_raw = getattr(tc, 'test_steps', None)
        if not steps_raw:
            return diagnostics

        import json as _json
        if isinstance(steps_raw, str):
            try:
                steps_raw = _json.loads(steps_raw)
            except _json.JSONDecodeError:
                return diagnostics

        if not isinstance(steps_raw, list):
            return diagnostics

        for i, step in enumerate(steps_raw):
            gs = parse_single_step(step, i + 1)
            target = gs.target_text
            action = gs.action_type

            # 探索侧 LLM 推断优先（指代步骤：parse_single_step 得「该条预警」，
            # 探索侧经 LLM 推断为「佩戴预警」——以推断后的真实元素为准匹配诊断）
            _g = _guided_by_seq.get(i + 1)
            if _g is not None:
                _gt = getattr(_g, 'target_text', '')
                if _gt:
                    target = _gt
                    action = getattr(_g, 'action_type', action)

            if not target:
                diagnostics.append({
                    "seq": i + 1,
                    "step_raw": str(step)[:100],
                    "target": "",
                    "status": "skipped",
                    "message": "步骤描述无法解析",
                })
                continue

            # 纯断言步骤（「验证：「患者姓名」」带「」元素名）：探索不探索断言步骤，
            # 四层匹配必然 miss——元素已由其他交互步骤定位过则算已覆盖；未定位过
            # 不算缺失（不缺探索依据，断言目标由交互步骤的元素名覆盖）
            if action == "validate":
                _diag = _best_diag(step_diag_map.get((target, "click"))) \
                    or _best_diag(step_diag_map.get((target, "fill")))
                if _diag:
                    diagnostics.append({
                        "seq": i + 1,
                        "target": target,
                        "action": action,
                        "actual_text": _diag.get("actual_text", ""),
                        "status": "success",
                        "strategy": _diag.get("strategy", ""),
                        "message": f"✓ 已定位「{target}」（断言目标由交互步骤覆盖）",
                    })
                else:
                    diagnostics.append({
                        "seq": i + 1,
                        "target": target,
                        "action": action,
                        "status": "skipped",
                        "strategy": "",
                        "message": f"「{target}」为纯断言目标，探索不探索断言步骤（不计缺失）",
                    })
                continue

            # 查找匹配的探索结果（四层回退）
            diag = _best_diag(step_diag_map.get((target, action)))
            if not diag:
                # 按实际页面文本匹配（评分引擎找到的相似文本）
                diag = _best_diag(actual_text_map.get((target, action)))
            if not diag:
                # 仅按 target 匹配（忽略 action，合并同 target 全部候选）
                _cands = []
                for key, vals in step_diag_map.items():
                    if key[0] == target:
                        _cands.extend(vals)
                diag = _best_diag(_cands)
            if not diag:
                # 按 actual_text 前缀包含匹配
                _cands = []
                for (at, act), vals in actual_text_map.items():
                    if target in at or at in target:
                        _cands.extend(vals)
                diag = _best_diag(_cands)

            if diag:
                # actual_text = 探索实际命中的页面真实文本（校正数据源：
                # 与用例 target 不同时，以探索结果为准回写用例——用户定性 2026-08-23）
                _actual = diag.get("actual_text", "")
                diagnostics.append({
                    "seq": i + 1,
                    "target": target,
                    "action": action,
                    "actual_text": _actual,
                    "status": diag.get("status", "unknown"),
                    "strategy": diag.get("strategy", ""),
                    "message": (
                        f"✓ 已定位「{target}」({diag.get('strategy', '')})"
                        if diag.get("status") == "success"
                        else f"✗ 未找到「{target}」— {diag.get('error', '未知错误')}"
                    ),
                })
            else:
                diagnostics.append({
                    "seq": i + 1,
                    "target": target,
                    "action": action,
                    "status": "not_found",
                    "strategy": "",
                    "message": f"✗ 未找到「{target}」— 探索未覆盖此步骤，请检查用例描述是否正确",
                })

        return diagnostics

    @staticmethod
    def _correct_case_steps(db, tc, case_diagnostics: List[Dict]) -> int:
        """探索结果校正：以探索实际命中的页面文本为准，回写功能用例步骤并落库。

        用户定性（2026-08-23）：探索实际结果与用户输入/需求有出入时，以探索
        结果为准，反过来把用例中不正确的文本修改正确，再转化为 UI 用例。
        校正按步骤进行：同一 target 在不同步骤可能命中不同元素（真机实证：
        工作台卡片叫「待审核报告」，点击跳转后目标页 tab 叫「报告审核」）——
        只替换探索成功命中且实际文本 ≠ 用例文本的步骤，且只替换 action 中
        「{target}」标记内的文本，不跨元素瞎替换。

        安全阀：actual_text 必须与 target 在文本层面合理关联才校正——归一化后
        相等（渲染差异：「重 置」vs「重置」）、target 是 actual 子串（加前后缀）、
        或最长公共连续子串 ≥ 2（同物异名：「待审核报告」vs「报告审核」共享
        「报告」）。零关联的命中是探索误命中（旧评分引擎容器污染实证：
        「重置」→「自定义」LCS=0），不校正。

        幂等：已校正过的步骤再跑（actual == target）自动跳过。
        返回校正的步骤数（0 = 未改动）。
        """
        if not case_diagnostics or tc is None:
            return 0

        steps = FunctionalToUIService._extract_raw_steps(tc)
        if not isinstance(steps, list) or not steps:
            return 0

        # 拷贝一份再修改：JSON 列原地 mutate 不触发 SQLAlchemy 变更检测（雷区）
        new_steps = list(steps)
        changed = 0
        for d in case_diagnostics:
            if d.get("status") != "success":
                continue
            target = (d.get("target") or "").strip()
            actual = (d.get("actual_text") or "").strip()
            if not target or not actual or actual == target:
                continue
            # 关联性安全阀（见 docstring）——防旧评分引擎容器污染数据
            n_target = normalize_ws(target)
            n_actual = normalize_ws(actual)
            # ── 硬化护栏（2026-09-03 修复“探索乱跑到账号管理/角色管理”）──
            # (a) actual 是多行/含换行的“容器整块文本”（如侧边栏整条菜单被当成命中文本）
            #     绝不写回——它不是单个可操作元素的真实文本，写回会把整条菜单固化进步骤。
            if "\n" in actual or "\r" in actual:
                logger.info(f"[FunctionalToUI] 探索校正跳过: 用例{getattr(tc, 'id', '?')} "
                            f"step{int(d.get('seq') or 0)} actual 含换行(容器整块文本)，不固化")
                continue
            # (b) actual 过长（> 40 归一化字符，明显是容器拼接文本而非单元素文案）不写回
            if len(n_actual) > 40:
                logger.info(f"[FunctionalToUI] 探索校正跳过: 用例{getattr(tc, 'id', '?')} "
                            f"step{int(d.get('seq') or 0)} actual 过长({len(n_actual)} 字符)，不固化")
                continue
            # (c) 关联强度收紧：仅“相等”或“target 是 actual 子串”才认校正；
            #     LCS≥2 的同前缀不同物（新增收发→新增角色）不再作为关联依据，
            #     它会把语义不同的对象（跨模块误命中）错误固化。
            _m = SequenceMatcher(None, n_target, n_actual).find_longest_match(
                0, len(n_target), 0, len(n_actual))
            _allow = (n_actual == n_target
                      or (n_target and n_target in n_actual))
            if not _allow:
                logger.info(f"[FunctionalToUI] 探索校正跳过: 用例{getattr(tc, 'id', '?')} "
                            f"step{int(d.get('seq') or 0)}「{target}」→「{actual}」仅弱关联(LCS={_m.size})，不固化")
                continue
            try:
                idx = int(d.get("seq") or 0) - 1
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < len(new_steps)):
                continue
            step = new_steps[idx]
            if not isinstance(step, dict):
                continue
            action = step.get("action", "")
            marked = f"「{target}」"
            if marked not in action:
                continue
            new_action = action.replace(marked, f"「{actual}」")
            if new_action == action:
                continue
            new_step = dict(step)
            new_step["action"] = new_action
            new_steps[idx] = new_step
            changed += 1
            logger.info(f"[FunctionalToUI] 探索校正: 用例{getattr(tc, 'id', '?')} "
                        f"step{idx + 1}「{target}」→「{actual}」")

        if changed:
            tc.test_steps = new_steps  # 新对象赋回（触发 JSON 变更检测）
            try:
                db.commit()
            except Exception as _e:
                db.rollback()
                logger.warning(f"[FunctionalToUI] 探索校正落库失败（不影响转化）: {_e}")
                return 0
        return changed

    # ========================================================================
    # 批量转化（每批共用一个 LLM 调用）
    # ========================================================================

    async def _convert_batch_v2(
        self, batch, base_url, browser, viewport_size, headless,
        script_type, script_language, project_id, shared_page_objects, cancel_check
    ) -> List[Dict]:
        """将一批用例合并为一个 LLM 调用，返回各用例结果"""
        if not batch:
            return []

        from app.core.services.llm_service import LLMService
        llm = LLMService(self.db)

        # 构建组合 prompt
        cases_text = []
        for tc, kg, case_name, module, diag, found, missing in batch:
            steps = self._extract_raw_steps(tc)
            steps_str = "\n".join([
                f"  {s.get('step', s.get('seq', i+1))}. {s.get('action', s.get('desc', ''))}"
                + (f" → {s.get('expected', '')}" if s.get('expected') else '')
                for i, s in enumerate(steps)
            ]) if steps else "（无步骤）"
            # 前置条件注入（2026-08-25 修复：历史批量 prompt 无前置条件段 → LLM 输出
            # 的 test_data 无 preconditions 键 → 28 条批量转化全部前置条件丢失，执行时
            # 无法按前置条件导航。与单条链路 _build_generation_prompt 同源）
            _pre = getattr(tc, 'preconditions', '') or ''
            _td = getattr(tc, 'test_data', None)
            if isinstance(_td, str):
                try: _td = json.loads(_td)
                except Exception: _td = {}
            _data_plan = _td.get('data_plan', {}) if isinstance(_td, dict) else {}
            _data_requirements = _data_plan.get('requirements', []) if isinstance(_data_plan, dict) else []
            _data_text = json.dumps(_data_requirements, ensure_ascii=False) if _data_requirements else '（未定义；生成脚本时不得擅自编造固定测试值，输入步骤可保留 ${key} 占位符）'
            cases_text.append(
                f"### 用例 {tc.id if hasattr(tc, 'id') else '?'}: {case_name}\n"
                f"模块: {module}\n"
                f"前置条件: {_pre or '无'}\n"
                f"测试数据计划: {_data_text}\n"
                f"步骤:\n{steps_str}\n"
            )

        # 从第一个用例取 KG 数据
        _first_kg = batch[0][1] if batch else {}
        _elements_summary = _summarize_elements_v2(_first_kg)
        _dropdowns_summary = _summarize_dropdowns_v2(_first_kg)

        # 页面 URL 映射/起始页/POM key 段——与单条链路同源（2026-08-24 审计 H1：
        # 批量 prompt 曾无 URL 注入 → LLM 编造 goto(locator=工作台)/goto(#/login)）
        from app.core.agents.web_ui_conversion_v2 import (
            _build_page_url_map, _build_url_prompt_sections, _sanitize_spec_steps,
        )
        page_url_map, start_url = _build_page_url_map(_first_kg, base_url)
        _pom_keys = "、".join(shared_page_objects.keys()) if shared_page_objects else "（无）"
        _url_sections = _build_url_prompt_sections(page_url_map, start_url, _pom_keys)

        prompt = f"""你是WebUI自动化测试专家。为以下 {len(batch)} 条功能用例生成 JSON 数据驱动测试步骤。

{_url_sections}

## 页面元素（来自探索，LOCATOR=页面上真实存在的文本）
{_elements_summary}

## 下拉筛选控件
{_dropdowns_summary}

## 用例列表
{"".join(cases_text)}

## 测试数据规则
- TestDataPlan 是功能用例的正式数据契约；UI 脚本不要把一次运行的随机值固化进脚本。
- 对 generated/consumable 数据，脚本参数保留为 ${{key}} 占位符，由执行阶段 TestDataManager 提供本次运行实例。
- consumable 每次 Case Run 必须使用新的实例；不要依赖上一次运行的值。
- static/shared 可以直接使用其 value；seeded/factory 只引用工厂产生的数据，不允许 LLM 猜数据库 ID。

## 每条用例输出一个 JSON（不含 markdown）:
{{
  "test_case_id": "用例ID",
  "title": "用例标题",
  "module": "模块名",
  "preconditions": "前置条件原文（原样透传上方用例的「前置条件」内容，没有则填空字符串）",
  "steps": [
    {{"seq": 1, "action": "click", "desc": "点击XX", "args": {{"locator": "页面真实文本"}}}},
    {{"seq": 2, "action": "assert_visible", "desc": "验证XX可见", "args": {{"locator": "页面真实文本"}}}}
  ]
}}

## 硬约束（违反会导致执行失败）:
- action 只用以下标准值（与单条链路同源）：
  导航: goto, go_back, reload
  交互: click, dblclick, fill, select, hover, check, press
  断言: assert_visible, assert_text, assert_value, assert_url
  等待: wait_for_render, wait_for_url, wait_for_load_state
  数据: get_all_items, scroll_to_bottom, skip_if_empty
- **「进入/打开/跳转/点击进入 XX 页面」类步骤必须输出为 goto（不是 click 文本）**——
  按步骤中页面名在「页面 URL 映射」匹配 URL（F34 修复 2026-08-25，与单条链路
  web_ui_conversion_v2 的 goto 规则同源）；「验证：页面URL包含」必须输出 assert_url
- goto 步骤：args.url 必须从「页面 URL 映射」中取（禁止编造 URL！）；绝不使用登录页 URL（跳登录页=登出会话）
- **「返回工作台/返回起始页/回到原页面」等返回语义步骤一律输出 {{"action": "go_back", "desc": "返回...", "args": {{}}}}，禁止用 goto 起始 URL 代替浏览器历史返回、禁止 goto 登录页**——SPA 项目 goto 起始 URL（尤其 base 根地址）会整页重载并丢失会话、落到登录页；返回只能走浏览器历史 go_back
- args.page 仅允许「可用的 POM 页面 key」中的值，且仅在映射无匹配时使用
- locator 来源：①「页面元素」列表的 LOCATOR 值 ②「下拉筛选控件」的选项文本 ③ 功能用例原文中「」标记的 UI 元素名
- select 操作的 locator 用下拉选项文本（如 "男"、"全部"），trigger 用「页面元素」中对应的控件名
- 缺 locator 时不要编造步骤，但可以从用例描述原文提取 UI 元素名作为 locator
- **URL 校验步骤（原步骤以「验证：页面URL包含」开头）必须输出 assert_url（args.expected=URL 子串），
  禁止改成 assert_visible(locator=URL 文本)！** 示例正确: {{"action":"assert_url","desc":"验证跳转","args":{{"expected":"patient-detail"}}}}
- **「验证：」开头的纯断言步骤原样保留为断言动作；「记录/获取/捕获XX」是读取语义，
  禁止臆造 assert_visible 步骤——页面有对应字段文本时输出 assert_visible 验证该字段，
  否则不输出该步骤**
- **动态计数文本（含 (数字) 的计数，如「佩戴预警 (0)」）定位时去掉计数部分**：
  locator 用「佩戴预警」（get_by_text 子串匹配可命中任意计数），禁止把「(0)」固进 locator
- 输出 JSON 数组 [{...}, {...}]，一条用例一个对象
- **每条用例输出的 test_case_id 必须原样等于输入用例标题「用例 N:」中的 N，不得修改、不得乱序、不得漏条**
- **preconditions 原样透传上方「前置条件:」行的内容，不得改写**
"""
        logger.info(f"[FunctionalToUI] 批量转化 {len(batch)} 条...")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: llm.call_llm(prompt, max_tokens=llm.get_scaled_max_tokens(), cancel_check=cancel_check)
        )
        if not response:
            return [{"result": {"test_case_id": str(tc.id) if hasattr(tc, 'id') else '',
                                "case_name": cn, "module": mod, "status": "conversion_failed",
                                "error": "LLM 无响应", "script": None},
                     "status_key": "conversion_failed", "tc": tc}
                    for tc, kg, cn, mod, diag, fnd, mis in batch]

        # 解析 JSON 数组
        import re as _re
        # 先尝试 ```json ... ``` 包裹的（LLM 常见行为），再回退裸 []
        _json_match = _re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, _re.DOTALL)
        if not _json_match:
            _json_match = _re.search(r'\[.*\]', response, _re.DOTALL)
        specs = []
        _parse_error = ""
        try:
            specs = json.loads(_json_match.group(1) if _json_match and _json_match.lastindex else _json_match.group(0)) if _json_match else []
        except json.JSONDecodeError as _je:
            _parse_error = str(_je)

        if not specs:
            # 解析失败，记录原始响应片段方便排查
            _resp_preview = response[:600] if response else "(空)"
            logger.error(
                f"[FunctionalToUI] 批量转化 JSON 解析失败: "
                f"batch_size={len(batch)} json_found={bool(_json_match)} "
                f"error={_parse_error} response_preview={_resp_preview}"
            )
            return [{"result": {"test_case_id": str(tc.id) if hasattr(tc, 'id') else '',
                                "case_name": cn, "module": mod, "status": "conversion_failed",
                                "error": f"LLM 响应解析失败{': ' + _parse_error if _parse_error else ''}", "script": None},
                     "status_key": "conversion_failed", "tc": tc}
                    for tc, kg, cn, mod, diag, fnd, mis in batch]

        # 逐条保存——按 test_case_id 精确匹配，不依赖 LLM 数组顺序（LLM 可能乱序/漏条，
        # 按索引对应会把内容静默错配到其他用例；匹配不到显式报 conversion_failed，不静默）
        def _norm_sid(_v):
            if _v is None:
                return ''
            try:
                return str(int(float(str(_v).strip())))
            except (ValueError, TypeError):
                return str(_v).strip()

        _spec_by_id = {}
        for _sp in specs:
            if isinstance(_sp, dict):
                _sid = _norm_sid(_sp.get("test_case_id"))
                if _sid and _sid not in _spec_by_id:
                    _spec_by_id[_sid] = _sp

        output = []
        for (tc, kg, case_name, module, diag, found, missing) in batch:
            tc_id = str(tc.id) if hasattr(tc, 'id') else str(getattr(tc, 'id', ''))
            spec = _spec_by_id.get(tc_id)
            if not spec or not isinstance(spec, dict):
                output.append({"result": {"test_case_id": tc_id, "case_name": case_name,
                                          "module": module, "status": "conversion_failed",
                                          "error": "LLM 未生成此用例（test_case_id 不匹配或漏条）", "script": None},
                               "status_key": "conversion_failed", "tc": tc})
                continue

            # ── 自动补尾：最后一步不是 goto/go_back 时追加 go_back ──
            # 所有“卡片/链接点击后返回”统一使用浏览器历史返回，避免 SPA 项目
            # 通过 goto 起始 URL 丢失 organization 等运行态参数。
            steps = spec.get("steps", [])
            if steps and isinstance(steps, list):
                last_action = steps[-1].get("action", "") if steps else ""
                if last_action not in ("goto", "go_back"):
                    steps.append({
                        "seq": len(steps) + 1,
                        "action": "go_back",
                        "desc": "返回起始页",
                        "args": {},
                    })
                    spec["steps"] = steps

            # 前置条件兜底（2026-08-25：LLM 漏输出 preconditions 时用功能用例原文补齐，
            # 与单条链路 _parse_json_spec 的 setdefault 同源——preconditions 丢失即
            # 执行器无法按前置条件导航，历史 28 条批量转化全部丢失）
            if not spec.get("preconditions"):
                spec["preconditions"] = getattr(tc, 'preconditions', '') or ''

            # 落库前把功能用例的 TestDataPlan 作为 UI 用例正式数据契约透传。
            # 不能只把计划写进 prompt：LLM 输出格式没有强制返回 test_data，若不在代码层补齐，
            # 执行阶段 TestDataManager 看不到原始计划，${key} 会原样留在页面上。
            try:
                from app.core.services.test_data_manager import TestDataManager as _TDM
                _tdm = _TDM(self.db)
                _td_plan = _tdm.build_plan(tc)
                spec["test_data"] = {
                    "data_plan": _td_plan.to_dict(),
                    "preconditions": spec.get("preconditions") or getattr(tc, "preconditions", "") or "",
                }
            except Exception as _td_e:
                logger.warning(f"[FunctionalToUI] TestDataPlan 透传失败 case={tc_id}: {_td_e}")

            # 落库前 goto 步骤有效性校验/补全（与单条链路同源——LLM 编造的 goto
            # 坏形态在此兜底修正，防止坏数据落库；2026-08-24 审计 H1）
            spec = _sanitize_spec_steps(spec, page_url_map=page_url_map, start_url=start_url)

            # 保存到 DB（project_id 透传：WebUITestCase 项目隔离）
            _saved_ok = True
            try:
                from app.core.agents.web_ui_conversion_v2 import _save_result
                _saved_ok = _save_result(self.db, tc_id, spec, shared_page_objects or {},
                           base_url, browser, viewport_size, headless, script_type, script_language,
                           project_id=project_id)
            except Exception as e:
                logger.warning(f"[FunctionalToUI] 保存失败 {tc_id}: {e}")
                _saved_ok = False
            if not _saved_ok:
                # E5 复查修复 2026-08-25：落库失败必须如实上报 conversion_failed——
                # 此前忽略 _save_result 返回值，前端显示转化成功但脚本为 None，
                # 后续执行「用例不存在」，用户无从感知
                output.append({"result": {
                    "test_case_id": tc_id, "case_name": case_name, "module": module,
                    "status": "conversion_failed", "error": "转化结果保存到数据库失败",
                    "script": None,
                    "diagnostics": {"total_steps": len(diag), "found_steps": len(found),
                                    "missing_steps": missing, "step_details": diag,
                                    "warning": f"{len(found)}/{len(diag)} 步已定位" if missing else None},
                }, "status_key": "conversion_failed", "method": "v2", "tc": tc})
                continue

            status_label = "success" if not missing else "steps_missing"
            output.append({"result": {
                "test_case_id": tc_id, "case_name": case_name, "module": module,
                "status": status_label, "error": None,
                "script": spec,
                "diagnostics": {"total_steps": len(diag), "found_steps": len(found),
                                "missing_steps": missing, "step_details": diag,
                                "warning": f"{len(found)}/{len(diag)} 步已定位" if missing else None},
            }, "status_key": status_label, "method": "v2", "tc": tc})

        logger.info(f"[FunctionalToUI] 批量完成: {len(output)} 条")
        return output


def _summarize_elements_v2(kg_data: Dict) -> str:
    """摘要元素列表（供批量 prompt 使用）"""
    elements = kg_data.get("elements", []) if isinstance(kg_data, dict) else []
    if not elements:
        return "（无）"
    lines = []
    for e in elements[:40]:
        if isinstance(e, dict):
            name = e.get("name", "")
            lt = e.get("locator_text", "")
            role = e.get("role", e.get("type", ""))
            if lt and lt != name:
                lines.append(f"- {role}: 描述名={name} | LOCATOR={lt}")
            elif name:
                lines.append(f"- {role}: {name}")
    return "\n".join(lines) if lines else "（无）"


def _summarize_dropdowns_v2(kg_data: Dict) -> str:
    """摘要下拉框（供批量 prompt 使用）—— 选项文本也是合法的 locator"""
    dd = kg_data.get("dropdowns", {}) if isinstance(kg_data, dict) else {}
    if not dd:
        return "（无）"
    lines = []
    for name, info in dd.items():
        if isinstance(info, dict):
            opts = info.get("options", [])
            if opts:
                # 每个选项单独列出为可用 locator
                opt_strs = [f'"{o}"' for o in opts[:15]]
                lines.append(f"- {name}: 选项=[{', '.join(opt_strs)}]  ← 这些选项文本均可作为 select 操作的 locator")
    return "\n".join(lines) if lines else "（无）"


    async def _debug_score_elements(
        self, test_case_ids: list, all_targets: dict, base_url: str, headless: bool = True,
    ) -> Dict[str, Any]:
        """调试模式：复用 _explore_by_steps 的登录流程，仅扫描评分不探索。"""
        import concurrent.futures, asyncio as _aio, json

        _first_tc = self._load_test_case(test_case_ids[0]) if test_case_ids else None
        project_id = self._extract_project_id(_first_tc) if _first_tc else None
        if not project_id:
            return {"login_ok": False, "error": "无法确定项目ID"}
        explore_cfg = self._load_exploration_config(project_id)
        _base_url = base_url or explore_cfg.get("base_url", "")
        username = explore_cfg.get("username", "")
        password = explore_cfg.get("password", "")
        if not _base_url:
            return {"login_ok": False, "error": "未配置目标URL"}

        def _do_score():
            from playwright.sync_api import sync_playwright
            from app.core.services.login_engine import login_with_ui_case
            from app.core.models.knowledge_graph import KnowledgeGraph
            from app.core.database import SessionLocal

            _db = SessionLocal()
            result = {"login_ok": False, "page_url": "", "scores": {}, "error": ""}
            pw = None; browser = None
            try:
                # Step 1: async 登录（使用 __login__ UI 用例步骤）
                _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
                _login_loop = _aio.new_event_loop()

                async def _login():
                    from playwright.async_api import async_playwright
                    async with async_playwright() as apw:
                        b = await apw.chromium.launch(headless=headless)
                        c = await b.new_context(viewport={"width": 1280, "height": 900})
                        p = await c.new_page()
                        ok, wb_url = await login_with_ui_case(p, _base_url, username, password,
                                                              project_id=project_id)
                        state = await p.context.storage_state() if ok else None
                        await b.close()
                        return ok, json.dumps(state, ensure_ascii=False) if state else None, wb_url

                login_ok, storage_json, workbench_url = _login_loop.run_until_complete(_login())
                _login_loop.close()
                result["login_ok"] = login_ok
                if not login_ok:
                    result["error"] = "登录失败"
                    return result
                result["page_url"] = workbench_url
                state = json.loads(storage_json)

                # Step 2: sync Playwright 加载登录态 → 扫描评分
                pw = sync_playwright().start()
                browser = pw.chromium.launch(headless=headless)
                ctx = browser.new_context(viewport={"width": 1280, "height": 900}, storage_state=state)
                page = ctx.new_page()
                page.goto(workbench_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(4000)

                from app.core.services.element_locator import ElementLocator
                from app.core.services.exploration_config import WebExplorationConfig
                locator = ElementLocator(page, WebExplorationConfig())

                scores = {}
                for target, info in all_targets.items():
                    r = locator.locate(target=target, role=info.get('role', ''), ui_pattern=info.get('ui_pattern', ''))
                    scores[target] = {
                        'action': info.get('action', ''), 'role': info.get('role', ''),
                        'ui_pattern': info.get('ui_pattern', ''),
                        'found': r.found, 'strategy': r.strategy,
                        'element_info': r.element_info if r.found else None,
                    }
                result["scores"] = scores
            except Exception as e:
                result["error"] = str(e)
            finally:
                if browser: browser.close()
                if pw:
                    try: pw.stop()
                    except Exception: pass
                _db.close()
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await _aio.get_event_loop().run_in_executor(pool, _do_score)

# ========================================================================
# 便捷函数 — 供端点直接调用
# ========================================================================

async def convert_with_exploration_fallback(
    db: Session,
    test_case_ids: List[str],
    base_url: str = "http://localhost:3000",
    browser: str = "chromium",
    viewport_size: str = "1920x1080",
    headless: bool = True,
    script_type: str = "playwright",
    script_language: str = "python",
    project_id: int = None,
    force_explore: bool = False,
    cancel_check=None,
    progress_callback=None,  # callable(dict) → 每完成一条用例回调
    phase_cb=None,           # callable(dict) → 阶段进度事件（探索/POM/转化）
) -> Dict[str, Any]:
    """转换功能用例为 UI 用例。progress_callback 每完成一条被调用。"""
    service = FunctionalToUIService(db)
    return await service.convert_cases_with_exploration(
        test_case_ids=test_case_ids,
        base_url=base_url,
        browser=browser,
        viewport_size=viewport_size,
        headless=headless,
        script_type=script_type,
        script_language=script_language,
        project_id=project_id,
        force_explore=force_explore,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
        phase_cb=phase_cb,
    )
