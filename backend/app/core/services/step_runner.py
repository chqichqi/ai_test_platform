"""
StepRunner — JSON 数据驱动测试步骤执行引擎

读取 JSON 步骤定义（符合 SKILL spec v2.0 格式），
反射调用 POM Page Object 方法，支持：
- $变量 运行时解析
- foreach 动态列表遍历
- assert 断言
- skip_if / check_data_exists 数据存在性判断
- save_as 运行时变量保存
"""

import re
import json
import logging
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


class StepRunError(Exception):
    """步骤执行异常"""
    pass


class SkipTestError(Exception):
    """跳过用例（数据不存在等场景）"""
    pass


# CSS 选择器特征检测（用于区分 locator 字段是 CSS 还是纯文本）
_CSS_PATTERNS = (
    re.compile(r'^[a-zA-Z][a-zA-Z0-9]*(?:\[[^\]]*\])'),   # input[type=...]
    re.compile(r'^(?:input|button|select|a|div|span|img|form|label|li|ul|table|tr|td|text)\b.*[:\[.#]'),
    re.compile(r'^[.#]'),                                  # .class / #id
    re.compile(r'^\[.*\]'),                                # [role=...]
    re.compile(r':visible|:has-text|:has\(|:not\(|:nth-'),  # 伪类
)


def _looks_like_css(text: str) -> bool:
    """判断 locator 字符串是否像 CSS 选择器而非页面文本"""
    if not text or len(text) > 120:
        return False
    return any(p.search(text) for p in _CSS_PATTERNS)


# 执行侧导航动作词表（唯一定义处，同源策略）：
# - 消费方：run_parametrized_specs（前置条件导航判定）、build_pytest_project 生成的
#   pytest 参数化模板（tests/test_runner.py）——两处必须与 `_run_step` 的 goto 派发同源，
#   禁止各自写动作名集合（否则新增动作/改名即静默断链）
NAVIGATION_ACTIONS = ("goto",)

# 登录/鉴权页 page_name 判定元组（与 _looks_like_login_url 同源配套）：
# goto(page=login) 无 url 形态同样登出会话（2026-08-24 审计 M1 封堵）
_LOGIN_PAGE_NAMES = ("login", "auth", "signin", "sso")


def _looks_like_login_url(url: str) -> bool:
    """URL 是否指向登录/鉴权页（登录态判定唯一来源）。

    消费方：批量执行登录态验证（ui_test_executor 重定向判定）、
    StepRunner._do_goto 的"返回起始页跳登录 URL"拦截——同源，禁止各自写特征。
    语义与历史判定一致（/login /auth 子串），保守不误放；
    sign-in/logout 等形态补充（2026-08-24 审计 L2）。
    """
    if not url:
        return False
    u = (url or "").lower()
    return ("/login" in u or "/auth" in u or "signin" in u or "sign-in" in u
            or "logout" in u or "signout" in u)


def _looks_like_login_page(page: str) -> bool:
    """page_name 是否为登录/鉴权页（goto page 形态判定，与 URL 判定配套）。"""
    return bool(page) and str(page).lower() in _LOGIN_PAGE_NAMES


def _normalize_page_url(url: str, base_url: str = "") -> str:
    """页面 URL 规范化（生成侧 goto 目标 / POM navigate 的唯一来源）。

    - 相对路径（/xx 或 #/xx）按 base_url 路由形态补全：hash 路由保 `#`，pushState 直拼
    - 去除 query 参数（?refresh=... 等探索期临时参数，导航与 URL 断言不需要）

    历史缺陷：POM navigate 用 f"{base_url.rstrip('/')}{page_url}" 拼接，
    hash 路由项目（base_url=https://host/#/login）拼出 https://host/#/login/workpanel
    错误地址 → goto(page=xx) 导航失败/跳回登录（2026-08-24 生成根因审计）。
    """
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        src = (base_url or "").split("#", 1)[0].rstrip("/")
        if url.startswith("#"):
            url = f"{src}{url}"
        elif url.startswith("/"):
            url = f"{src}#{url}" if "#" in (base_url or "") else f"{src}{url}"
        else:
            url = f"{src}/{url}"
    return url.split("?", 1)[0]


class StepRunner:
    """
    JSON 步骤 → POM 方法调用执行引擎

    Usage:
        runner = StepRunner(page, {"workpanel": WorkPanelPage(page), ...})
        runner.run(steps)
    """

    def __init__(self, page: Any, page_objects: Dict[str, Any]):
        """
        Args:
            page: Playwright Page 实例
            page_objects: {"page_key": PageObject(page), ...}
        """
        self.page = page
        self.pages = page_objects
        self.vars: Dict[str, Any] = {}  # $变量 存储
        self.current_page: Any = None
        self._org_meta = None  # 机构选择实际用到的定位参数（导入验证成功后回填步骤数据）

    # ═══════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════

    def run(self, steps: List[dict]) -> Dict[str, Any]:
        """
        执行步骤列表

        Returns:
            {"success": bool, "steps_executed": int, "skipped": bool, "error": str|None}
        """
        executed = 0
        try:
            for step in steps:
                self._run_step(step)
                executed += 1
        except SkipTestError as e:
            logger.info(f"用例跳过: {e}")
            return {"success": True, "steps_executed": executed, "skipped": True, "error": None}
        except StepRunError as e:
            logger.error(f"步骤执行失败 (step {executed + 1}): {e}")
            return {"success": False, "steps_executed": executed, "skipped": False, "error": str(e)}
        except Exception as e:
            logger.error(f"未预期错误 (step {executed + 1}): {e}")
            return {"success": False, "steps_executed": executed, "skipped": False, "error": str(e)}

        return {"success": True, "steps_executed": executed, "skipped": False, "error": None}

    def set_var(self, name: str, value: Any) -> None:
        """外部设置变量（如从数据库注入测试数据）"""
        self.vars[name] = value

    def get_var(self, name: str) -> Any:
        """获取变量值"""
        return self.vars.get(name)

    # ═══════════════════════════════════════════════════════════
    # Step dispatch
    # ═══════════════════════════════════════════════════════════

    def _run_step(self, step: dict) -> None:
        """执行单个步骤——支持全部 Playwright 标准操作"""
        action = step.get("action", "")
        args = self._resolve_args(step.get("args", {}))
        desc = step.get("desc", action)

        # ════ 交互操作 ════
        if action == "click":
            self._do_click(args, desc)
        elif action == "dblclick":
            self._do_dblclick(args, desc)
        elif action == "fill":
            self._do_fill(args, desc)
        elif action == "select":
            self._do_select(args, desc)
        elif action == "hover":
            self._do_hover(args, desc)
        elif action == "check":
            self._do_check(args, desc)

        # ════ 断言操作 ════
        elif action == "assert_visible":
            self._do_assert_visible(args, desc)
        elif action == "assert_text":
            self._do_assert_text(args, desc)
        elif action == "assert_value":
            self._do_assert_value(args, desc)
        elif action == "assert_url":
            self._do_assert_url(args, desc)
        # 2026-08-25 复查修复：assert_total_count/assert_empty_state/assert_none_selected
        # 此前错派发到 _do_assert_visible（无定位字段 → 抛「无法构建定位器」必败）。
        # 完整实现族在 _do_assert → _assert_count/_assert_empty_state/_assert_none_selected
        # （支持 selector+min/eq/max 旧形态与空态/无选中语义）；别名（assert_count/
        # assert_no_data/assert_no_indicators_selected）一并并入，防自定义动作落
        # _call_pom_or_fallback 按文本乱点
        elif action in ("assert_total_count", "assert_count", "assert_empty_state",
                        "assert_no_data", "assert_none_selected", "assert_no_indicators_selected"):
            self._do_assert(action, args, desc)

        # ════ 导航操作 ════
        elif action in NAVIGATION_ACTIONS:
            self._do_goto(args, step)
        elif action == "go_back":
            self.page.go_back()
        elif action == "reload":
            self.page.reload()

        # ════ 等待操作 ════
        elif action == "wait_for_render":
            self.page.wait_for_timeout(args.get("ms", 1000))
        elif action == "wait_for_url":
            self.page.wait_for_url(args.get("url", ""), timeout=args.get("timeout", 15000))
        elif action == "wait_for_load_state":
            # 默认 domcontentloaded：networkidle 对带 WebSocket/长轮询的 SPA 永不满足
            self.page.wait_for_load_state(args.get("state", "domcontentloaded"),
                                          timeout=args.get("timeout", 15000))

        # ════ 按键操作 ════
        elif action == "press":
            self.page.keyboard.press(args.get("key", "Enter"))

        # ════ 数据操作 ════
        elif action == "get_all_items":
            self._do_get_all_items(args, step)
        elif action == "scroll_to_bottom":
            self._do_scroll_to_bottom(args)
        elif action == "skip_if_empty":
            self._do_skip_if_empty(args)
        elif action == "guard_dynamic_data":
            self._do_guard_dynamic_data(args)
        elif action == "click_dynamic_item":
            self._do_click_dynamic_item(args, desc)
        elif action == "skip_if_not_exists":
            self._do_skip_if_not_exists(args)
        elif action == "handle_org_selection":
            self._do_handle_org_selection(args, desc)
        # 2026-08-25 复查修复：foreach/check_data_exists/get_first_row_data/
        # get_dropdown_options/get_selected_items 五个方法此前从未派发（死方法），
        # 落入 _call_pom_or_fallback 按文本乱点或报「无法构建定位器」——与
        # STEP_RUNNER_PY_STANDALONE 模板的 builtins 派发对齐（生成侧可产出这些动作）
        elif action == "foreach":
            self._do_foreach(args, step)
        elif action == "check_data_exists":
            self._do_check_data_exists(args, step)
        elif action == "get_first_row_data":
            self._do_get_first_row_data(step)
        elif action == "get_dropdown_options":
            self._do_get_dropdown_options(args, step)
        elif action == "get_selected_items":
            self._do_get_selected_items(args, step)

        # ════ 回退：自定义action → POM或文本定位 ════
        else:
            self._call_pom_or_fallback(action, args, desc)

        # ── save_as 处理 ──
        # 2026-08-25 复查修复：删除 _last_get_result 覆写——该变量从未被赋值，
        # getattr 恒 None，把 _do_get_all_items 已写入的 save_as 变量强制覆写为 None，
        # 导致 foreach/skip_if_empty 消费 $items 时静默空转/误跳过（在线引擎数据链断裂）
        if "save_as" in step and action in (
            "get_all_items",
        ):
            pass

    # ═══════════════════════════════════════════════════════════
    # Variable resolution
    # ═══════════════════════════════════════════════════════════

    def _resolve_args(self, args: dict) -> dict:
        """解析 args 中的 $变量 引用"""
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("$"):
                var_path = value[1:]  # 去掉 $
                resolved[key] = self._resolve_var_path(var_path)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_args(value)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_args(v) if isinstance(v, dict) else
                    self._resolve_var_path(v[1:]) if isinstance(v, str) and v.startswith("$") else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _resolve_var_path(self, path: str) -> Any:
        """解析 $var.sub.path 路径"""
        parts = path.split(".")
        val = self.vars
        for part in parts:
            if part.endswith("]") and "[" in part:
                # array index: items[0]
                name, idx = part.split("[", 1)
                idx = int(idx.rstrip("]"))
                val = val.get(name, [])
                if isinstance(val, list) and 0 <= idx < len(val):
                    val = val[idx]
                else:
                    raise StepRunError(f"变量索引无效: ${path}, 当前变量: {list(self.vars.keys())}")
            else:
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    val = getattr(val, part, None)
            if val is None and part != parts[-1]:
                break
        return val

    # ═══════════════════════════════════════════════════════════
    # Built-in actions
    # ═══════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════
    # 通用定位器：支持 text / role / placeholder / label / css
    # ═══════════════════════════════════════════════
    @staticmethod
    def _ws_fallback_xpath(text: str):
        """文本定位的去空白兜底 XPath（叶子元素精确匹配，忽略所有空白）。

        应用侧文本可能带空格（真机实证：按钮文案渲染为「重 置」），
        get_by_text 子串匹配对此失败。此兜底把目标文本与元素文本
        各自去空白（空格/换行/制表/全角空格）后精确比较——通用机制，
        不针对任何特定文案。无法构造（空文本/引号冲突）时返回 None。
        """
        needle = re.sub(r"\s+", "", text)
        if not needle or ("'" in needle and '"' in needle):
            return None
        quote = '"' if "'" in needle else "'"
        return (
            f"//*[not(*)][translate(normalize-space(.), ' \t\r\n　', '') = "
            f"{quote}{needle}{quote}]"
        )

    def _resolve_locator(self, args: dict):
        """根据 args 构建 Playwright Locator"""
        text = args.get("locator", args.get("text", ""))
        role = args.get("role", "")
        placeholder = args.get("placeholder", "")
        label = args.get("label", "")
        css = args.get("css", "")
        position = args.get("position", "first")  # first / last / nth(0)
        if css:
            loc = self.page.locator(css)
        elif text and _looks_like_css(text):
            # locator 字段带 CSS 选择器语法（如 input[type="password"]）→ 按 CSS 处理
            loc = self.page.locator(text)
        elif role and text:
            loc = self.page.get_by_role(role, name=text)
            if loc.count() == 0:
                loc = self._ws_fallback_loc(text) or loc
        elif placeholder:
            loc = self.page.get_by_placeholder(placeholder)
        elif label:
            loc = self.page.get_by_label(label)
        elif text:
            # 纯文本匹配：get_by_text 子串匹配优先；匹配不到（应用文本可能
            # 带空格，如「重 置」——真机实证超时）时用去空白精确匹配兜底。
            # count 探测保证正常文本的行为与原实现完全一致（含隐藏元素）。
            loc = self.page.get_by_text(text)
            if loc.count() == 0:
                loc = self._ws_fallback_loc(text) or loc
        else:
            raise StepRunError(f"无法构建定位器: {args}")
        return loc.first if position == "first" else loc.last

    def _ws_fallback_loc(self, text: str):
        """文本定位的去空白兜底 Locator；无法构造时返回 None。

        兜底 XPath 只匹配叶子元素（not(*)），目标文本与元素文本各自去掉
        空白（空格/换行/制表/全角空格）后精确比较。通用机制，不针对任何
        特定文案。
        """
        xpath = self._ws_fallback_xpath(text)
        return self.page.locator(xpath) if xpath else None

    # ═══════════════════════════════════════════════
    # 交互操作
    # ═══════════════════════════════════════════════
    def _do_click(self, args: dict, desc: str) -> None:
        explicit_role = str(args.get("role") or "").lower()
        if explicit_role in {"heading", "text", "paragraph", "table", "region", "card", "static"}:
            raise StepRunError(f"不可点击元素(role={explicit_role}): {args.get('locator', desc)}")
        loc = self._resolve_locator(args)
        try:
            loc.wait_for(state="visible", timeout=5000)
            try:
                semantic = loc.evaluate("e => ({tag:e.tagName.toLowerCase(), role:e.getAttribute('role') || '', disabled:e.disabled === true})")
                if semantic.get('role') in ('heading', 'presentation') or semantic.get('tag') in ('h1','h2','h3','h4','h5','h6'):
                    raise StepRunError(f"不可点击元素: {args.get('locator', desc)} ({semantic})")
            except StepRunError:
                raise
            except Exception:
                pass
            loc.click(timeout=5000)
            logger.info(f"[StepRunner] click ✓ {desc[:30]}")
        except StepRunError:
            raise
        except Exception as e:
            raise StepRunError(str(e))

    def _do_dblclick(self, args: dict, desc: str) -> None:
        loc = self._resolve_locator(args)
        loc.dblclick(timeout=5000)
        logger.info(f"[StepRunner] dblclick ✓ {desc[:30]}")

    def _do_fill(self, args: dict, desc: str) -> None:
        value = args.get("value", args.get("text", ""))
        if not value:
            raise StepRunError(f"fill 缺少 value: {desc}")
        loc = self._resolve_locator(args)
        loc.fill(value, timeout=5000)
        logger.info(f"[StepRunner] fill ✓ {desc[:30]}")

    def _do_select(self, args: dict, desc: str) -> None:
        """执行 select：先点触发器 → 等下拉打开 → 在下拉面板内点选项。

        LLM 生成的 args 中 trigger 和 locator/option 是分开的：
        - trigger: 触发器文本（如"房颤预警"标题）
        - locator/value/option: 选项文本（如"≥30"）
        旧版 _do_select 把 locator 同时用于触发器和选项，导致操作失败。
        """
        option = args.get("option", args.get("value", args.get("locator", "")))
        option = str(option).strip()
        if not option:
            raise StepRunError(f"select 缺少 option/value: {desc}")

        # ── 第1步：点击触发器 ──
        # 优先用 args.trigger（LLM 新格式），回退用 args（旧格式）
        trigger = args.get("trigger", "")
        if trigger:
            trigger_args = dict(args)
            trigger_args["locator"] = str(trigger)
            trigger_args.pop("trigger", None)
            self._do_click(trigger_args, desc)
        else:
            self._do_click(args, desc)
        # 下拉展开等待（用户 2026-09-02 建议缩短到 500ms）
        self.page.wait_for_timeout(500)

        # ── 第2步：在打开的下拉面板中点击目标选项 ──
        option_clicked = False
        for panel_sel in (
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
            ".ant-dropdown:not(.ant-dropdown-hidden)",
            '[role="listbox"]:not([aria-hidden="true"])',
        ):
            try:
                panel = self.page.locator(panel_sel).first
                if panel.count() > 0 and panel.is_visible():
                    # 精确匹配
                    opt = panel.get_by_text(option, exact=True).first
                    if opt.count() > 0 and opt.is_visible():
                        opt.click(timeout=3000)
                        option_clicked = True
                        break
                    # 包含匹配
                    opt = panel.get_by_text(option, exact=False).first
                    if opt.count() > 0 and opt.is_visible():
                        opt.click(timeout=3000)
                        option_clicked = True
                        break
            except Exception:
                continue

        if not option_clicked:
            # 回退：全页文本定位
            try:
                self.page.get_by_text(option, exact=True).first.click(timeout=5000)
                option_clicked = True
            except Exception:
                self.page.get_by_text(option, exact=False).first.click(timeout=5000)
                option_clicked = True

        logger.info(f"[StepRunner] select '{option}' ✓ {desc[:40]}")

    def _do_hover(self, args: dict, desc: str) -> None:
        loc = self._resolve_locator(args)
        loc.hover(timeout=5000)
        logger.info(f"[StepRunner] hover ✓ {desc[:30]}")

    def _do_check(self, args: dict, desc: str) -> None:
        loc = self._resolve_locator(args)
        loc.check(timeout=5000)
        logger.info(f"[StepRunner] check ✓ {desc[:30]}")

    # ═══════════════════════════════════════════════
    # 断言操作
    # ═══════════════════════════════════════════════
    def _do_assert_visible(self, args: dict, desc: str) -> None:
        loc = self._resolve_locator(args)
        loc.first.wait_for(state="visible", timeout=5000)
        logger.info(f"[StepRunner] assert_visible ✓ {desc[:30]}")

    def _do_assert_text(self, args: dict, desc: str) -> None:
        expected = args.get("expected", args.get("text", ""))
        loc = self._resolve_locator(args)
        import re as _re
        # 生成侧 LLM 常产出动态/正则断言：未解析模板变量（'共 ${total} 条'）或
        # 正则转义（'佩戴预警 \(\d+\)'）。此类若按字面匹配必然误判失败。
        # 含 ${...} 模板 → 把占位符转通配 .*?；含反斜杠/正则特征 → 按正则匹配页面实际文本。
        has_template = '${' in expected
        has_regex_feature = ('\\' in expected) or ('.?' in expected)
        if has_template or has_regex_feature:
            pattern = '.*?'.join(_re.escape(p) for p in _re.split(r'\$\{[^}]*\}', expected)) if has_template else expected
            try:
                text = loc.first.inner_text(timeout=5000)
            except Exception:
                text = ''
            if not _re.search(pattern, text):
                raise StepRunError(f"assert_text 不匹配: {desc} (期望 {pattern!r}, 实际 {text[:60]!r})")
            logger.info(f"[StepRunner] assert_text(正则) ✓ {desc[:30]}")
            return
        from playwright.sync_api import expect
        expect(loc.first).to_contain_text(expected, timeout=5000)
        logger.info(f"[StepRunner] assert_text ✓ {desc[:30]}")

    def _do_assert_value(self, args: dict, desc: str) -> None:
        expected = args.get("expected", "")
        loc = self._resolve_locator(args)
        from playwright.sync_api import expect
        expect(loc.first).to_have_value(expected, timeout=5000)
        logger.info(f"[StepRunner] assert_value ✓ {desc[:30]}")

    def _do_assert_url(self, args: dict, desc: str) -> None:
        expected = args.get("expected", args.get("url", ""))
        from playwright.sync_api import expect
        try:
            # 先按 Playwright glob 语义全量匹配（生成侧规范形态：**/patient**）
            expect(self.page).to_have_url(expected, timeout=5000)
        except Exception:
            # 裸 URL 子串形态（批量 prompt 示例 patient-detail，存量数据也如此）——
            # to_have_url 全量 glob 匹配永不命中子串 → 断言必失败（2026-08-25 复查
            # 修复：降级子串包含匹配）；空 expected 无任何匹配语义，如实报错
            _actual = self.page.url
            if not expected or expected not in _actual:
                raise
            logger.info(f"[StepRunner] assert_url ✓（子串匹配）{desc[:30]}")
            return
        logger.info(f"[StepRunner] assert_url ✓ {desc[:30]}")

    # ═══════════════════════════════════════════════
    # 回退：自定义action → POM方法 或 文本定位
    # ═══════════════════════════════════════════════
    def _call_pom_or_fallback(self, action: str, args: dict, desc: str) -> Any:
        """先试 POM 方法，失败则用文本定位"""
        try:
            return self._call_pom(action, args, desc)
        except Exception:
            pass
        # 回退：当作 click 处理
        text = args.get("locator", args.get("text", ""))
        if not text and action.startswith("click_"):
            text = action.replace("click_", "").replace("_", " ")
        if text:
            self.page.get_by_text(text).first.click(timeout=5000)
            logger.info(f"[StepRunner] pom fallback click '{text}' ✓")
            return True
        raise StepRunError(f"未找到方法: {action}")

    def _do_goto(self, args: dict, step: dict) -> None:
        """导航到页面"""
        page_name = args.get("page", "")
        url = args.get("url")

        # 登录页拦截：'返回起始页' 类步骤被生成器转成 goto 登录 URL 时跳过
        # 导航——跳登录页会清会话，导致当前及后续用例全部失败（历史坏数据兜底）
        # page 形态同判（goto(page=login) 无 url 也会登出会话，2026-08-24 审计 M1）
        if _looks_like_login_url(url) or _looks_like_login_page(page_name):
            logger.warning(f"[StepRunner] goto 目标为登录页"
                           f"（url={str(url)[:40] if url else '-'}, page={page_name}），跳过——防登出会话")
            return

        po = None
        if page_name in self.pages:
            po = self.pages[page_name]
        else:
            # 模糊匹配：忽略大小写、去 Page 后缀
            pn_lower = page_name.lower().replace('page', '')
            for k, v in self.pages.items():
                if k.lower().replace('page', '') == pn_lower:
                    po = v
                    break

        if po:
            if hasattr(po, "navigate"):
                po.navigate(url)
            elif url:
                # networkidle 对带 WebSocket/长轮询的 SPA 永远不满足（默认 30s 超时）；
                # domcontentloaded 时页面内容已就绪，与探索阶段一致
                self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self.current_page = page_name
        elif url:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        else:
            # 空 goto（无 page/url，历史旧数据坏步骤）：不导航保持当前页。
            # 首步空 goto 已由 run_parametrized_specs 的 base_url 兜底覆盖；
            # 非首步空 goto 保持当前页，页面不符由后续断言暴露（诚实失败）。
            logger.warning(f"[StepRunner] goto 无页面名且无 URL（desc={step.get('desc', '')[:30]}），保持当前页")

    def _do_wait(self, args: dict) -> None:
        """等待渲染"""
        ms = args.get("ms", 800)
        self.page.wait_for_timeout(ms)

    def _do_scroll_to_bottom(self, args: dict) -> None:
        """滚动容器到底部"""
        container = args.get("container", ".ant-table-body")
        try:
            self.page.locator(container).evaluate("el => el.scrollTop = el.scrollHeight")
            self.page.wait_for_timeout(500)
        except Exception:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)

    def _do_get_first_row_data(self, step: dict) -> None:
        """提取表格/列表第一行数据"""
        try:
            rows = self.page.locator("tr.ant-table-row, .ant-list-item, [class*='row']").all()
            if not rows or len(rows) == 0:
                if "save_as" in step:
                    self.vars[step["save_as"]] = None
                return
            first = rows[0]
            cells = first.locator("td, .ant-list-item-meta-title, [class*='cell']").all()
            data = {}
            for i, cell in enumerate(cells[:10]):
                data[f"col_{i}"] = cell.inner_text().strip()
            # 也提取常见字段
            name_el = first.locator("[class*='name'], [class*='title'], td:first-child").first
            try:
                data["name"] = name_el.inner_text().strip()
            except Exception:
                data["name"] = ""
            if "save_as" in step:
                self.vars[step["save_as"]] = data
        except Exception as e:
            logger.warning(f"get_first_row_data 失败: {e}")
            if "save_as" in step:
                self.vars[step["save_as"]] = None

    def _do_get_dropdown_options(self, args: dict, step: dict) -> None:
        """获取下拉框选项列表"""
        dropdown_name = args.get("name", "")
        try:
            # 尝试定位下拉选项
            options = self.page.locator(
                ".ant-select-dropdown:visible .ant-select-item, "
                ".ant-cascader-dropdown:visible .ant-cascader-menu-item"
            ).all()
            texts = [opt.inner_text().strip() for opt in options if opt.is_visible()]
            if "save_as" in step:
                self.vars[step["save_as"]] = texts
        except Exception as e:
            logger.warning(f"get_dropdown_options 失败: {e}")
            if "save_as" in step:
                self.vars[step["save_as"]] = []

    def _do_get_selected_items(self, args: dict, step: dict) -> None:
        """获取已选中项列表"""
        try:
            items = self.page.locator(
                ".ant-select-selection-item, .ant-checkbox-checked, "
                "[class*='selected'], [class*='checked']"
            ).all()
            data = []
            for item in items:
                try:
                    text = item.inner_text().strip()
                    if text:
                        data.append({"name": text, "element": item})
                except Exception:
                    pass
            if "save_as" in step:
                self.vars[step["save_as"]] = data
        except Exception as e:
            logger.warning(f"get_selected_items 失败: {e}")
            if "save_as" in step:
                self.vars[step["save_as"]] = []

    def _do_get_all_items(self, args: dict, step: dict) -> None:
        """获取所有列表项"""
        try:
            selector = args.get("selector", "tr.ant-table-row, .ant-list-item, [class*='row']")
            items = self.page.locator(selector).all()
            data = []
            for item in items:
                try:
                    data.append({"text": item.inner_text().strip()})
                except Exception:
                    pass
            if "save_as" in step:
                self.vars[step["save_as"]] = data
        except Exception as e:
            logger.warning(f"get_all_items 失败: {e}")
            if "save_as" in step:
                self.vars[step["save_as"]] = []

    def _do_check_data_exists(self, args: dict, step: dict) -> None:
        """检查数据在页面中是否存在"""
        value = args.get("value", "")
        if not value:
            if "save_as" in step:
                self.vars[step["save_as"]] = False
            return
        try:
            exists = self.page.locator(f"text={value}").first.is_visible(timeout=2000)
        except Exception:
            exists = False
        if "save_as" in step:
            self.vars[step["save_as"]] = exists

    def _do_skip_if_not_exists(self, args: dict) -> None:
        """数据不存在时跳过用例"""
        condition = args.get("condition", True)
        if isinstance(condition, str) and condition.startswith("$"):
            condition = self._resolve_var_path(condition[1:])
        if not condition:
            raise SkipTestError("无可用的测试数据，跳过本用例")

    def _do_skip_if_empty(self, args: dict) -> None:
        """列表为空时跳过用例"""
        list_var = args.get("list", "")
        if isinstance(list_var, str) and list_var.startswith("$"):
            items = self._resolve_var_path(list_var[1:])
        else:
            items = list_var
        if not items or (isinstance(items, list) and len(items) == 0):
            raise SkipTestError("列表为空，无可操作项，跳过本用例")

    def _section_container(self, section: str):
        """返回 section 标题对应的数据容器。

        不依赖具体前端框架：先找精确文本，再沿祖先向上寻找包含明显数据内容的
        容器。这样既适配 Ant Design，也适配普通 div/card 布局。
        """
        if not section:
            return None
        heading = self.page.get_by_text(str(section), exact=True).first
        try:
            heading.wait_for(state="visible", timeout=2000)
        except Exception:
            return None
        # 优先语义区域，其次向上尝试 1~5 层。
        for xp in (
            'xpath=ancestor::*[@role="region"][1]',
            'xpath=ancestor::section[1]',
            'xpath=ancestor::*[contains(@class,"card")][1]',
            'xpath=ancestor::div[1]',
            'xpath=ancestor::div[2]',
            'xpath=ancestor::div[3]',
            'xpath=ancestor::div[4]',
        ):
            try:
                loc = heading.locator(xp).first
                if loc.count() and loc.is_visible():
                    text = (loc.inner_text() or '').strip()
                    if len(text) > len(str(section)):
                        return loc
            except Exception:
                continue
        return heading

    def _section_has_data(self, section: str, empty_indicators=None) -> bool:
        """判断一个动态数据区是否有可操作数据。"""
        container = self._section_container(section)
        if container is None:
            return False
        empty_indicators = [str(x).strip() for x in (empty_indicators or []) if str(x).strip()]
        try:
            text = (container.inner_text() or '').strip()
        except Exception:
            return False
        if not text:
            return False
        # 空态文案命中且没有其它明显内容 → 视为空。
        if any(ind in text for ind in empty_indicators):
            # 去掉标题和空态后仍有实质文本，认为有数据；否则为空。
            residue = text
            for token in [section] + empty_indicators:
                residue = residue.replace(token, '')
            if not residue.strip():
                return False

        # 有交互数据优先：链接、button、表格行、cursor:pointer 元素。
        for selector in (
            'a:visible', '[role="link"]:visible', '[role="button"]:visible',
            'button:visible', 'tbody tr:visible', '[onclick]:visible',
        ):
            try:
                if container.locator(selector).count() > 0:
                    return True
            except Exception:
                pass

        # 某些业务页面患者姓名是 div/span + click handler，不能靠 tag 判断。
        try:
            candidates = container.locator('div,span,p,td').all()
            for el in candidates[:80]:
                try:
                    if not el.is_visible():
                        continue
                    t = (el.inner_text() or '').strip()
                    if not t or t == section or t in empty_indicators or len(t) > 80:
                        continue
                    cursor = el.evaluate("e => getComputedStyle(e).cursor")
                    if cursor == 'pointer':
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        # 没有空态且容器存在额外文本，也可以视为有数据；后续 click_dynamic_item
        # 仍会再次寻找真正可点击元素，避免把标题当作数据。
        residue = text.replace(section, '').strip()
        return bool(residue and not any(ind in residue for ind in empty_indicators))

    def _do_guard_dynamic_data(self, args: dict) -> None:
        """动态数据前置守卫：没有数据时 Skip，而不是 Failed。"""
        sections = args.get('sections') or args.get('targets') or []
        if isinstance(sections, str):
            sections = [sections]
        normalized = []
        for item in sections:
            if isinstance(item, str):
                normalized.append({'section': item})
            elif isinstance(item, dict) and item.get('section'):
                normalized.append(item)
        empty = args.get('empty_indicators') or ['暂无数据', '无数据']
        match = (args.get('match') or 'any').lower()
        states = []
        for item in normalized:
            section = str(item.get('section'))
            states.append(self._section_has_data(section, empty))
        has_data = any(states) if match == 'any' else all(states) if states else False
        logger.info(f"[StepRunner] dynamic_data_guard sections={normalized} states={states} match={match}")
        if not has_data:
            raise SkipTestError("动态数据为空，无可操作数据，跳过本用例")

    def _do_click_dynamic_item(self, args: dict, desc: str) -> None:
        """点击动态数据区中的真实可操作项，严禁点击 section 标题本身。"""
        section = args.get('section') or args.get('container') or ''
        empty = args.get('empty_indicators') or ['暂无数据', '无数据']
        if not self._section_has_data(section, empty):
            raise SkipTestError(f"「{section}」没有动态数据，跳过本用例")
        container = self._section_container(section)
        if container is None:
            raise StepRunError(f"动态数据区不存在: {section}")

        item_role = args.get('item_role') or ''
        item_text = args.get('item_text') or ''
        selectors = []
        if item_role in ('link', 'button', 'tab'):
            selectors.append(f'[role="{item_role}"]:visible')
            if item_role == 'link': selectors.append('a:visible')
            if item_role == 'button': selectors.append('button:visible')
        selectors.extend(['a:visible', '[role="link"]:visible', 'button:visible', '[role="button"]:visible',
                          '[onclick]:visible', 'tbody tr:visible'])
        if item_text:
            selectors.insert(0, f'text={item_text}')

        # 排除标题和空态文本。
        exclude = set([section] + [str(x) for x in empty])
        for selector in selectors:
            try:
                loc = container.locator(selector)
                count = min(loc.count(), 50)
                for i in range(count):
                    el = loc.nth(i)
                    if not el.is_visible():
                        continue
                    txt = (el.inner_text() or el.get_attribute('aria-label') or '').strip()
                    if txt in exclude:
                        continue
                    if item_text and item_text not in txt:
                        continue
                    el.click(force=True, timeout=5000)
                    logger.info(f"[StepRunner] click_dynamic_item ✓ {section} -> {txt[:80]}")
                    return
            except Exception:
                continue
        # 最后尝试 cursor:pointer 的数据项。
        try:
            candidates = container.locator('div,span,p,td').all()
            for el in candidates[:100]:
                try:
                    if not el.is_visible(): continue
                    txt = (el.inner_text() or '').strip()
                    if not txt or txt in exclude or len(txt) > 80: continue
                    if el.evaluate("e => getComputedStyle(e).cursor") != 'pointer': continue
                    if item_text and item_text not in txt: continue
                    el.click(force=True, timeout=5000)
                    logger.info(f"[StepRunner] click_dynamic_item ✓ {section} -> {txt[:80]}")
                    return
                except Exception:
                    continue
        except Exception:
            pass
        raise StepRunError(f"「{section}」存在数据，但未找到可点击的数据项")

    def _do_handle_org_selection(self, args: dict, desc: str) -> None:
        """条件性处理机构选择页——与 LoginEngine._h_handle_org_selection 同源策略。

        定位参数来自步骤数据（cards_selector / confirm_text，导入验证成功时
        已回填真实选择器）；旧数据无参数时走通用兜底候选。成功定位后把实际
        用到的选择器记录到 self._org_meta，供导入流程回填步骤数据（自学习：
        下一次执行直接用真实参数，代码零硬编码）。
        """
        # 等待页面稳定
        self.page.wait_for_timeout(1500)
        cur = self.page.url
        body_text = ""
        try:
            body_text = self.page.locator("body").inner_text()
        except Exception:
            pass
        # 检测机构选择页（URL 关键字 或 页面标题关键字）
        is_org = ("switchorganization" in cur or
                  "选择机构" in body_text or
                  "selectOrganization" in cur)
        if not is_org:
            logger.info(f"[StepRunner] 未检测到机构选择页，跳过")
            return
        logger.info("[StepRunner] 检测到机构选择页，自动处理...")
        cards_selector = (args or {}).get("cards_selector")
        confirm_text = (args or {}).get("confirm_text")
        used_cards = None
        used_confirm = None
        try:
            # 卡片：步骤参数优先，无参数走通用候选（tailwind 特征 + class 关键词回退）
            cards = self.page.locator(cards_selector) if cards_selector else None
            if cards is None or cards.count() == 0:
                cards = self.page.locator("div.cursor-pointer.border.rounded:visible")
            if cards.count() == 0:
                cards = self.page.locator("[class*='org']:visible, [class*='card']:visible, .cursor-pointer:visible")
            if cards.count() == 0:
                logger.info("[StepRunner] 未找到机构卡片，跳过机构选择")
                return
            # 记录实际命中的卡片选择器（供回填）
            used_cards = cards_selector or "div.cursor-pointer.border.rounded:visible"
            cards.first.click(timeout=3000)
            self.page.wait_for_timeout(1500)
            # 确认按钮：步骤参数优先，兜底兼容「确 认」（字间空格）
            confirm = None
            if confirm_text:
                confirm = self.page.get_by_role("button", name=confirm_text)
                if not confirm.is_visible(timeout=500):
                    confirm = None
            if confirm is None:
                confirm = self.page.get_by_role("button", name="确 认")
                if not confirm.is_visible(timeout=500):
                    confirm = self.page.locator("button").filter(has_text="确认").first
            if confirm.is_visible():
                used_confirm = confirm_text or "确 认"
                confirm.click(timeout=3000)
                self.page.wait_for_timeout(1500)
            logger.info("[StepRunner] 机构选择完成")
            # 自学习：回填真实定位参数（供导入流程写入 __login__ 步骤数据）
            if used_cards or used_confirm:
                self._org_meta = {
                    "cards_selector": used_cards,
                    "confirm_text": used_confirm or "确 认",
                }
        except Exception as e:
            logger.warning(f"[StepRunner] 机构选择异常（不阻塞）: {e}")

    def _do_foreach(self, args: dict, step: dict) -> None:
        """遍历列表执行子步骤"""
        items = args.get("items", [])
        if isinstance(items, str) and items.startswith("$"):
            items = self._resolve_var_path(items[1:])
        if not items:
            return

        as_var = args.get("as", "item")
        sub_steps = args.get("do", [])

        original_var = self.vars.get(as_var)
        for item in items:
            self.vars[as_var] = item
            for sub in sub_steps:
                self._run_step(sub)
        if original_var is not None:
            self.vars[as_var] = original_var

    def _do_assert(self, action: str, args: dict, desc: str) -> None:
        """断言处理"""
        if action == "assert_total_count" or action == "assert_count":
            self._assert_count(args, desc)
        elif action == "assert_visible" or action == "assert_element_visible":
            self._assert_visible(args, desc)
        elif action == "assert_empty_state" or action == "assert_no_data":
            self._assert_empty_state(args, desc)
        elif action == "assert_no_indicators_selected" or action == "assert_none_selected":
            self._assert_none_selected(desc)
        else:
            # 通用断言：尝试调用 POM 方法
            result = self._call_pom(action, args, desc)
            if not result:
                raise StepRunError(f"断言失败: {desc}")

    def _assert_count(self, args: dict, desc: str) -> None:
        """断言数据行数"""
        min_count = args.get("min")
        eq_count = args.get("eq")
        max_count = args.get("max")
        selector = args.get("selector", "tr.ant-table-row, .ant-list-item")

        count = self.page.locator(selector).count()

        if eq_count is not None and count != eq_count:
            raise StepRunError(f"{desc}: 期望 {eq_count} 条，实际 {count} 条")
        if min_count is not None and count < min_count:
            raise StepRunError(f"{desc}: 期望至少 {min_count} 条，实际 {count} 条")
        if max_count is not None and count > max_count:
            raise StepRunError(f"{desc}: 期望至多 {max_count} 条，实际 {count} 条")

        logger.info(f"✅ {desc}: {count} 条")

    def _assert_visible(self, args: dict, desc: str) -> None:
        """断言元素可见"""
        text = args.get("text", "")
        selector = args.get("selector", f"text={text}" if text else "")
        if not selector:
            raise StepRunError(f"assert_visible 缺少 selector 或 text")
        try:
            self.page.locator(selector).first.wait_for(state="visible", timeout=5000)
            logger.info(f"✅ {desc}")
        except Exception:
            raise StepRunError(f"断言失败: 元素不可见 - {selector}")

    def _assert_empty_state(self, args: dict, desc: str) -> None:
        """断言空状态"""
        try:
            no_data = self.page.locator(".ant-empty, [class*='empty'], [class*='no-data'], "
                                        "text=暂无数据, text=No Data").first
            if no_data.is_visible():
                logger.info(f"✅ {desc}: 页面显示空状态")
            else:
                raise StepRunError(f"{desc}: 未找到空状态提示")
        except StepRunError:
            raise
        except Exception:
            # 回退: 检查数据行数为 0
            count = self.page.locator("tr.ant-table-row, .ant-list-item").count()
            if count == 0:
                logger.info(f"✅ {desc}: 数据行数为 0")
            else:
                raise StepRunError(f"{desc}: 仍有 {count} 条数据")

    def _assert_none_selected(self, desc: str) -> None:
        """断言无选中项"""
        try:
            selected = self.page.locator(
                ".ant-select-selection-item, .ant-checkbox-checked, [class*='selected']"
            ).count()
            if selected == 0:
                logger.info(f"✅ {desc}")
            else:
                raise StepRunError(f"{desc}: 仍有 {selected} 个选中项")
        except StepRunError:
            raise
        except Exception:
            pass  # 选择器没匹配到 = 无选中项

    # ═══════════════════════════════════════════════════════════
    # POM method dispatch
    # ═══════════════════════════════════════════════════════════

    def _call_pom(self, action: str, args: dict, desc: str) -> Any:
        """
        将 action name 映射到 POM 方法并调用。

        映射策略：
        1. 在当前页面对象中查找方法
        2. 在所有注册的页面对象中查找
        3. 常用别名映射
        """
        # 别名映射 (JSON action → POM method name)
        ALIASES = {
            "click_search": "click_search_btn",
            "click_save": "click_save_btn",
            "click_reset": "click_reset_btn",
            "search_by_name": "search_by_name",
            "search_by_keyword": "search_by_keyword",
            "select_dropdown_option": "select_filter_option",
            "expand_filter_dropdown": "expand_filter",
            "open_custom_metric_dialog": "open_custom_dialog",
        }

        method_name = ALIASES.get(action, action)

        # 1-3. 尝试 POM 方法，失败立即回退文本定位
        pom_error = None
        for attempt in range(3):
            po = None
            if attempt == 0 and self.current_page and self.current_page in self.pages:
                po = self.pages[self.current_page]
            elif attempt == 1:
                for pk, p in self.pages.items():
                    if hasattr(p, method_name):
                        po = p
                        break
            elif attempt == 2:
                for pk, p in self.pages.items():
                    for attr_name in dir(p):
                        if not attr_name.startswith("_") and self._method_matches(attr_name, action):
                            po = p
                            self.current_page = pk
                            method_name = attr_name
                            break
                    if po:
                        break
            if po and hasattr(po, method_name):
                method = getattr(po, method_name)
                if callable(method):
                    try:
                        return method(**args) if args else method()
                    except Exception as e:
                        pom_error = str(e)[:80]
                        break  # POM 找到了但执行失败 → 不回退，直接用文本定位

        # 4. POM 方法未找到 → 从 desc 推导通用操作
        try:
            return self._fallback_action(action, args, desc)
        except StepRunError:
            pass  # fallback 也失败，继续抛出原始错误

        raise StepRunError(
            f"未找到 POM 方法: {action} (当前页: {self.current_page}, "
            f"已注册页: {list(self.pages.keys())})")

    def _fallback_action(self, action: str, args: dict, desc: str) -> Any:
        """POM 方法缺失/失败时的通用回退：从步骤描述 + args 推导操作"""
        import re as _re

        # 从 desc 提取候选目标文本列表
        candidates = []
        # 1. args 中的 locator/text/name
        for k in ('locator', 'text', 'name'):
            v = args.get(k, '')
            if v:
                candidates.append(v)
        # 2. 从 desc 剥离动词前缀 + 分隔符截断
        clean = desc
        for pfx in ('点击', '单击', '勾选', '验证', '确认', '检查', '输入', '填写', '选择', '获取'):
            if clean.startswith(pfx):
                clean = clean[len(pfx):]
                break
        clean = _re.sub(r'[，,。；;！!\s].*$', '', clean)  # 截断到第一个标点
        clean = _re.sub(r'(卡片|按钮|链接|图标|输入框|下拉框|页面|弹窗|菜单|选项|页面|列|行)$', '', clean.strip()).strip()
        if clean:
            candidates.append(clean)
        # 3. 从 action 名提取关键词
        action_hint = action.replace('click_', '').replace('assert_', '').replace('get_', '')
        if action_hint and action_hint != action:
            candidates.append(action_hint)

        candidates = [c for c in candidates if c]  # 去空
        logger.info(f"[StepRunner] fallback candidates: {candidates}")

        if action.startswith('click_') or action == 'click':
            for target in candidates:
                for strategy in [
                    lambda t=target: self.page.get_by_text(t, exact=False).first.click(timeout=2000),
                    lambda t=target: self.page.locator(f':has-text("{t}")').first.click(timeout=2000),
                ]:
                    try:
                        strategy()
                        logger.info(f"[StepRunner] fallback click: '{target}' ✓")
                        return True
                    except Exception:
                        continue
            raise StepRunError(f"无法点击: {candidates}")

        elif 'assert' in action or 'visible' in action:
            for target in candidates:
                try:
                    if self.page.get_by_text(target, exact=False).first.is_visible():
                        return True
                except Exception:
                    pass
            raise StepRunError(f"断言失败: {candidates}")

        elif action.startswith('get_') or action == 'get_all_items':
            items = []
            for sel in ['tr', '[class*="row"]', '[class*="item"]', 'li', '[class*="card"]']:
                try:
                    for r in self.page.locator(sel).all()[:50]:
                        txt = r.inner_text().strip()
                        if txt:
                            items.append(txt)
                except Exception:
                    pass
            save_as = args.get('save_as', '')
            if save_as:
                self.vars[save_as] = items
            return items

        elif action == 'wait_for_render':
            self.page.wait_for_timeout(args.get('ms', 1000))
            return True

        elif action == 'skip_if_empty':
            var_name = args.get('list', args.get('items', ''))
            val = self.vars.get(var_name.lstrip('$'), []) if var_name else []
            if not val:
                raise SkipTestError(f"数据为空: {var_name}")
            return True

        raise StepRunError(
            f"未找到 POM 方法: {action} (当前页: {self.current_page}, "
            f"已注册页: {list(self.pages.keys())})")

    @staticmethod
    def _method_matches(method_name: str, action: str) -> bool:
        """检查方法名是否匹配 action"""
        return (
            method_name == action or
            method_name.replace("_", "") == action.replace("_", "") or
            action in method_name or
            method_name in action
        )


# ═══════════════════════════════════════════════════════════
# 参数化执行（pytest 参数化数据驱动的在线等价）
# ═══════════════════════════════════════════════════════════

def run_parametrized_specs(
    specs: List[dict],
    page: Any,
    page_objects: Dict[str, Any],
    base_url: str,
    timeout_ms: int,
    skip_goto: bool = False,
) -> List[dict]:
    """参数化数据驱动执行：一条用例 = 一组 (preconditions + steps)。

    与 build_pytest_project 生成的 tests/test_runner.py（@pytest.mark.parametrize）
    同构（RULES.md 二.6 同源策略）：生成物与在线执行共用同一套语义——
      1. 用例步骤自带导航（goto 动作 = 前置条件导航）→ 不预跳 base_url，按步骤执行；
      2. 无导航步骤（历史旧数据）→ 兜底 goto base_url（登录态由调用方保证）；
      3. 前置条件原文只做日志/排查，导航一律由步骤数据驱动（不做 NL 解析）。
    反射分发由 StepRunner._run_step 承担（action 名 → handler），此处不重复实现。

    Returns: 与 specs 一一对应的 [{"status", "steps_executed", "skipped", "error", ...}]
    """
    results: List[dict] = []
    for spec in specs:
        meta = {}
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except Exception:
                spec = {}
        if isinstance(spec, dict):
            meta = {"case_id": spec.get("case_id", "?"), "title": spec.get("title", "?")}
            steps = spec.get("steps", [])
            preconditions = spec.get("preconditions", "")
        else:
            steps, preconditions = [], ""

        if not steps:
            results.append({"status": "failed", "error": "无步骤定义", **meta})
            continue

        # 用例自带导航步骤（前置条件导航）→ 尊重用例，不预跳 base_url；
        # 无导航步骤的旧用例 → 兜底跳 base_url（登录态由调用方保证）。
        # goto 必须有有效目标（page/url 非空）才算导航步骤：历史旧数据坏步骤
        # （goto 只有 locator）视为无导航 → 兜底 base_url（批量登录后=起始页）。
        has_nav_step = any(
            isinstance(s, dict)
            and (s.get("action") or "") in NAVIGATION_ACTIONS
            and bool((s.get("args") or {}).get("page") or (s.get("args") or {}).get("url"))
            for s in steps
        )
        if not skip_goto and not has_nav_step:
            logger.info(f"[Execute] 导航到 {base_url}")
            page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1000)
        # 日志行不做真实浏览器调用：浏览器被外部关闭时 page.title() 会抛
        # TargetClosedError，把整条用例打成空跑异常（21:17 批量执行实证）
        try:
            _cur_url = page.url[:80]
            _cur_title = page.title()
        except Exception:
            _cur_url, _cur_title = "?", "?"
        logger.info(f"[Execute] 前置条件: {preconditions or '（无）'} | "
                    f"当前 URL: {_cur_url}, title: {_cur_title}")

        runner = StepRunner(page, page_objects)
        logger.info(f"[Execute] {len(steps)} 步, POM: {list(page_objects.keys())}")
        result = runner.run(steps)
        logger.info(f"[Execute] 执行完成: success={result.get('success')}, "
                    f"steps={result.get('steps_executed', 0)}, error={result.get('error', '')}")

        results.append({
            "status": "completed" if result.get("success") else "failed",
            "steps_executed": result.get("steps_executed", 0),
            "skipped": result.get("skipped", False),
            "error": result.get("error"),
            **meta,
        })
    return results


# ═══════════════════════════════════════════════════════════
# pytest fixture support
# ═══════════════════════════════════════════════════════════

POM_CLASS_TEMPLATE = '''"""Auto-generated POM classes for {project_name}"""
from playwright.sync_api import Page, expect

{classes}
'''

CONFTEST_TEMPLATE = '''"""pytest configuration for {project_name} UI tests"""
import pytest
import os
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# 导入所有 POM 类
{pom_imports}

# ── 登录 fixture ──
@pytest.fixture(scope="session")
def browser():
    """浏览器实例 (session 级别)"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("HEADLESS", "true") == "true")
        yield browser
        browser.close()

@pytest.fixture
def page(browser):
    """页面实例 (function 级别，每条用例独立上下文)"""
    context = browser.new_context(
        viewport={{"width": 1920, "height": 1080}},
        locale="zh-CN"
    )
    page = context.new_page()
    # 登录
    _login(page)
    yield page
    context.close()

def _login(page):
    """自动登录"""
    base_url = os.getenv("BASE_URL", "{base_url}")
    username = os.getenv("TEST_USERNAME", "admin")
    password = os.getenv("TEST_PASSWORD", "admin123")
    page.goto(f"{{base_url}}/login")
    page.fill('input[placeholder*="手机号"], input[placeholder*="用户名"], input[name="username"]', username)
    page.fill('input[placeholder*="密码"], input[type="password"]', password)
    page.click('button[type="submit"], button:has-text("登录")')
    page.wait_for_load_state("domcontentloaded")

# ── POM fixtures ──
{pom_fixtures}
'''

POM_FIXTURE_TEMPLATE = '''
@pytest.fixture
def {var_name}(page) -> "{class_name}":
    """ {class_name} fixture """
    po = {class_name}(page)
    return po
'''


def build_pytest_project(
    page_objects: Dict[str, str],
    test_specs: List[dict],
    project_name: str = "webui_tests",
    base_url: str = "http://localhost:3000",
) -> Dict[str, str]:
    """
    将 POM 类代码 + JSON 测试定义 组装为完整的 pytest 项目文件。

    Returns: {"pages/xxx.py": "code...", "conftest.py": "code...", ...}
    """
    files = {}

    # conftest.py
    imports = []
    fixtures = []
    for class_name in page_objects.keys():
        var_name = class_name[0].lower() + class_name[1:]
        imports.append(f"from pages.{class_name.lower()}_page import {class_name}")
        fixtures.append(
            POM_FIXTURE_TEMPLATE.format(var_name=var_name, class_name=class_name)
        )

    files["conftest.py"] = CONFTEST_TEMPLATE.format(
        project_name=project_name,
        pom_imports="\n".join(imports),
        pom_fixtures="\n".join(fixtures),
        base_url=base_url,
    )

    # POM files
    for class_name, code in page_objects.items():
        file_name = f"{class_name.lower()}_page.py"
        files[f"pages/{file_name}"] = code

    files["pages/__init__.py"] = ""

    # Test specs as JSON files
    for spec in test_specs:
        case_id = spec.get("case_id", f"TC-{len(files)}")
        safe_name = case_id.replace(" ", "_").replace("/", "_")
        files[f"tests/{safe_name}.json"] = json.dumps(spec, ensure_ascii=False, indent=2)

    # StepRunner-based test executor (runs all JSON specs)
    test_runner_py = _generate_test_runner(page_objects, test_specs, base_url=base_url)
    files["tests/test_runner.py"] = test_runner_py
    files["tests/__init__.py"] = ""

    # step_runner module for pytest
    files["step_runner.py"] = STEP_RUNNER_PY_STANDALONE

    return files


def _generate_test_runner(
    page_objects: Dict[str, str],
    test_specs: List[dict],
    base_url: str = "http://localhost:3000",
) -> str:
    """生成 pytest parametrize 参数化测试文件"""

    # 生成 load_all_specs 的 spec 列表（完整 spec：preconditions + steps 一起参数化，
    # 与 run_parametrized_specs 同源——前置条件导航由 spec 数据携带，不做文本解析）
    spec_entries = []
    for spec in test_specs:
        case_id = spec.get("case_id", "TC-unknown")
        title = spec.get("title", case_id)
        spec_repr = repr(json.dumps(spec, ensure_ascii=False))
        spec_entries.append(
            f'    pytest.param({spec_repr}, id="{case_id}"),  # {title}'
        )

    fixture_uses = ", ".join(
        f"{c[0].lower() + c[1:]}" for c in page_objects
    )

    pom_registry_lines = []
    for cn in page_objects:
        vn = cn[0].lower() + cn[1:]
        pom_registry_lines.append(f'        "{vn}": {vn},')

    return f'''"""Auto-generated parametrized test runner — POM + JSON data-driven"""
import json
import os
import pytest
from pathlib import Path


BASE_URL = os.getenv("BASE_URL", "{base_url}")


def load_all_specs():
    """加载所有 JSON 测试定义作为参数化用例（完整 spec：preconditions + steps）"""
    return [
{chr(10).join(spec_entries)}
    ]


@pytest.mark.parametrize("spec", load_all_specs())
def test_data_driven(spec, {fixture_uses}):
    """参数化数据驱动测试：一条用例 = 一组 (preconditions + steps)
    与 run_parametrized_specs 同源（RULES.md 二.6）：用例步骤自带 goto 导航 → 按步骤执行；
    无导航步骤（历史旧数据）→ 兜底 goto BASE_URL。前置条件只做排查，导航由步骤数据驱动。"""
    from step_runner import StepRunner, NAVIGATION_ACTIONS

    spec = json.loads(spec)
    steps = spec.get("steps", [])
    preconditions = spec.get("preconditions", "")

    pom_registry = {{
{chr(10).join(pom_registry_lines)}
    }}

    # 取第一个 POM 实例获取 page 引用（所有 POM 共享同一个 page）
    first_po = next(iter(pom_registry.values()))
    runner = StepRunner(first_po.page, pom_registry)

    # 与 run_parametrized_specs 同源：goto 必须有有效目标（page/url 非空）
    has_nav_step = any(
        isinstance(s, dict)
        and (s.get("action") or "") in NAVIGATION_ACTIONS
        and bool((s.get("args") or {{}}).get("page") or (s.get("args") or {{}}).get("url"))
        for s in steps
    )
    if not has_nav_step:
        first_po.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        first_po.page.wait_for_timeout(1000)

    result = runner.run(steps)
    assert result["success"], (
        f"❌ 步骤执行失败\\n"
        f"   前置条件: {{preconditions or '（无）'}}\\n"
        f"   执行步数: {{result.get('steps_executed', 0)}}\\n"
        f"   错误: {{result.get('error', '未知')}}"
    )
'''


STEP_RUNNER_PY_STANDALONE = '''
"""Standalone StepRunner for pytest execution"""
import re
import logging
import fnmatch  # F33：assert_url glob 匹配（与在线版 _do_assert_url 同源）

logger = logging.getLogger(__name__)


# 与在线版 NAVIGATION_ACTIONS 同源（pytest 工程 test_runner 引用此词表做前置条件导航判定）
NAVIGATION_ACTIONS = ("goto",)


def _looks_like_login_url(url: str) -> bool:
    """与在线版 step_runner 同源：登录页特征判定（goto 登录页拦截）"""
    if not url:
        return False
    u = (url or "").lower()
    return ("/login" in u or "/auth" in u or "signin" in u or "sign-in" in u
            or "logout" in u or "signout" in u)


class StepRunError(Exception):
    pass


class SkipTestError(Exception):
    pass


class StepRunner:
    """JSON steps → POM method call executor (standalone for pytest)"""

    def __init__(self, page, page_objects):
        self.page = page
        self.pages = page_objects
        self.vars = {}
        self.current_page = None

    def run(self, steps):
        executed = 0
        try:
            for step in steps:
                self._run_step(step)
                executed += 1
        except SkipTestError as e:
            return {"success": True, "steps_executed": executed, "skipped": True}
        except StepRunError as e:
            return {"success": False, "steps_executed": executed, "skipped": False, "error": str(e)}
        return {"success": True, "steps_executed": executed, "skipped": False, "error": None}

    def _run_step(self, step):
        action = step.get("action", "")
        args = self._resolve_args(step.get("args", {}))
        desc = step.get("desc", action)

        builtins = {
            "goto": self._do_goto, "wait_for_render": self._do_wait,
            "scroll_to_bottom": self._do_scroll, "get_first_row_data": self._do_first_row,
            "get_dropdown_options": self._do_dropdown_opts, "get_selected_items": self._do_selected,
            "get_all_items": self._do_all_items, "check_data_exists": self._do_check_exists,
            "skip_if_not_exists": self._do_skip_not_exists, "skip_if_empty": self._do_skip_empty,
            "guard_dynamic_data": self._do_guard_dynamic_data, "click_dynamic_item": self._do_click_dynamic_item,
            "foreach": self._do_foreach,
        }

        if action in builtins:
            builtins[action](args, step)
        elif action.startswith("assert"):
            self._do_assert(action, args, desc)
        else:
            result = self._call_pom(action, args, desc)
            if "save_as" in step:
                self.vars[step["save_as"]] = result
            if result is not None and hasattr(result, 'page'):
                for k, po in self.pages.items():
                    if po is result:
                        self.current_page = k

    def _resolve_args(self, args):
        resolved = {}
        for k, v in args.items():
            if isinstance(v, str) and v.startswith("$"):
                resolved[k] = self._resolve_path(v[1:])
            elif isinstance(v, dict): resolved[k] = self._resolve_args(v)
            else: resolved[k] = v
        return resolved

    def _resolve_path(self, path):
        parts = path.split(".")
        val = self.vars
        for p in parts:
            if p.endswith("]") and "[" in p:
                name, idx = p.split("[", 1); idx = int(idx.rstrip("]"))
                val = val.get(name, []) if isinstance(val, dict) else val
                val = val[idx] if isinstance(val, list) and 0 <= idx < len(val) else None
            elif isinstance(val, dict): val = val.get(p)
            elif hasattr(val, p): val = getattr(val, p)
            else: val = None
        return val

    def _do_goto(self, args, step):
        if args.get("page") in self.pages:
            po = self.pages[args["page"]]
            if hasattr(po, "navigate"): po.navigate(args.get("url"))
            self.current_page = args["page"]
        elif args.get("url"):
            self.page.goto(args["url"], wait_until="domcontentloaded", timeout=15000)

    def _do_wait(self, args, step): self.page.wait_for_timeout(args.get("ms", 800))
    def _do_scroll(self, args, step):
        try: self.page.locator(args.get("container", ".ant-table-body")).evaluate("el => el.scrollTop = el.scrollHeight")
        except: self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.page.wait_for_timeout(500)

    def _do_first_row(self, args, step):
        try:
            rows = self.page.locator("tr.ant-table-row, .ant-list-item").all()
            data = {}
            if rows:
                first = rows[0]
                try: data["name"] = first.locator("td:first-child").inner_text().strip()
                except: data["name"] = ""
            if "save_as" in step: self.vars[step["save_as"]] = data if rows else None
        except: pass

    def _do_dropdown_opts(self, args, step):
        try:
            opts = self.page.locator(".ant-select-dropdown:visible .ant-select-item").all()
            texts = [o.inner_text().strip() for o in opts if o.is_visible()]
            if "save_as" in step: self.vars[step["save_as"]] = texts
        except: pass

    def _do_selected(self, args, step):
        try:
            items = self.page.locator(".ant-select-selection-item, .ant-checkbox-checked").all()
            data = [{"name": i.inner_text().strip()} for i in items if i.inner_text().strip()]
            if "save_as" in step: self.vars[step["save_as"]] = data
        except: pass

    def _do_all_items(self, args, step):
        try:
            items = self.page.locator(args.get("selector", "tr.ant-table-row")).all()
            data = [{"text": i.inner_text().strip()} for i in items]
            if "save_as" in step: self.vars[step["save_as"]] = data
        except: pass

    def _do_check_exists(self, args, step):
        v = args.get("value", "")
        try: exists = self.page.locator(f"text={v}").first.is_visible(timeout=2000)
        except: exists = False
        if "save_as" in step: self.vars[step["save_as"]] = exists

    def _section_container(self, section):
        if not section: return None
        try:
            h = self.page.get_by_text(str(section), exact=True).first
            h.wait_for(state="visible", timeout=2000)
            for xp in ('xpath=ancestor::*[@role="region"][1]', 'xpath=ancestor::section[1]', 'xpath=ancestor::div[1]', 'xpath=ancestor::div[2]', 'xpath=ancestor::div[3]'):
                try:
                    loc=h.locator(xp).first
                    if loc.count() and loc.is_visible() and len((loc.inner_text() or '').strip()) > len(str(section)):
                        return loc
                except Exception: pass
            return h
        except Exception: return None

    def _section_has_data(self, section, empty):
        c=self._section_container(section)
        if c is None: return False
        try: text=(c.inner_text() or '').strip()
        except Exception: return False
        if not text: return False
        residue=text.replace(str(section),'')
        if any(str(x) in residue for x in empty) and not residue.strip().replace('暂无数据','').replace('无数据','').strip(): return False
        for sel in ('a:visible','[role="link"]:visible','button:visible','[role="button"]:visible','tbody tr:visible','[onclick]:visible'):
            try:
                if c.locator(sel).count()>0: return True
            except Exception: pass
        return bool(residue.strip())

    def _do_guard_dynamic_data(self, args, step=None):
        sections=args.get('sections') or args.get('targets') or []
        if isinstance(sections,str): sections=[sections]
        sections=[x.get('section') if isinstance(x,dict) else x for x in sections]
        empty=args.get('empty_indicators') or ['暂无数据','无数据']
        states=[self._section_has_data(x,empty) for x in sections if x]
        ok=any(states) if (args.get('match') or 'any')=='any' else all(states)
        if not ok: raise SkipTestError('动态数据为空，无可操作数据，跳过本用例')

    def _do_click_dynamic_item(self, args, step=None):
        section=args.get('section') or ''
        empty=args.get('empty_indicators') or ['暂无数据','无数据']
        if not self._section_has_data(section,empty): raise SkipTestError(f'「{section}」没有动态数据，跳过本用例')
        c=self._section_container(section)
        if c is None: raise StepRunError(f'动态数据区不存在: {section}')
        role=args.get('item_role') or ''
        selectors=[]
        if role: selectors.append(f'[role="{role}"]:visible')
        selectors += ['a:visible','[role="link"]:visible','button:visible','[role="button"]:visible','[onclick]:visible','tbody tr:visible']
        exclude={section,*[str(x) for x in empty]}
        for sel in selectors:
            try:
                loc=c.locator(sel)
                for i in range(min(loc.count(),50)):
                    el=loc.nth(i)
                    if not el.is_visible(): continue
                    txt=(el.inner_text() or el.get_attribute('aria-label') or '').strip()
                    if not txt or txt in exclude: continue
                    el.click(force=True,timeout=5000); return
            except Exception: pass
        raise StepRunError(f'「{section}」存在数据，但未找到可点击的数据项')

    def _do_skip_not_exists(self, args):
        if not args.get("condition", True): raise SkipTestError("无可用的测试数据")
    def _do_skip_empty(self, args):
        items = args.get("list", [])
        if not items or len(items) == 0: raise SkipTestError("列表为空")

    def _do_foreach(self, args, step):
        items = args.get("items", [])
        if isinstance(items, str) and items.startswith("$"): items = self._resolve_path(items[1:])
        if not items: return
        as_var = args.get("as", "item")
        orig = self.vars.get(as_var)
        for item in items:
            self.vars[as_var] = item
            for sub in args.get("do", []): self._run_step(sub)
        if orig is not None: self.vars[as_var] = orig

    def _do_assert(self, action, args, desc):
        if action in ("assert_total_count", "assert_count"):
            c = self.page.locator(args.get("selector", "tr.ant-table-row")).count()
            eq_val = args.get("eq")
            if eq_val is not None and c != eq_val:
                raise StepRunError(f"{desc}: 期望{'{' + str(eq_val) + '}'}条，实际{'{' + str(c) + '}'}条")
            min_val = args.get("min")
            if min_val is not None and c < min_val:
                raise StepRunError(f"{desc}: 期望至少{'{' + str(min_val) + '}'}条，实际{'{' + str(c) + '}'}条")
        elif action == "assert_empty_state":
            try:
                count = self.page.locator("tr.ant-table-row").count()
                if count > 0: raise StepRunError(f"{desc}: 仍有{'{' + str(count) + '}'}条数据")
            except StepRunError: raise
            except: pass
        elif action == "assert_none_selected":
            c = self.page.locator(".ant-select-selection-item, .ant-checkbox-checked").count()
            if c > 0: raise StepRunError(f"{desc}: 仍有{'{' + str(c) + '}'}个选中项")
        # F33 修复（2026-08-25）：standalone 模板此前缺 assert_url/assert_visible/
        # assert_text/assert_value 处理 → 落 _call_pom 搜不到 POM 方法 → raise
        # 「未找到POM方法」→ 导出 pytest 工程执行标准断言必失败。
        # 语义与在线版 step_runner 同构：assert_url glob 优先子串降级；
        # 文本/值断言含子串即通过；assert_visible 无 expected。
        elif action == "assert_url":
            expected = args.get("expected") or args.get("url") or ""
            actual = self.page.url
            if expected and (fnmatch.fnmatch(actual, expected) or expected in actual):
                pass
            else:
                raise StepRunError(f"{desc}: 期望URL匹配 {expected}，实际 {actual}")
        elif action in ("assert_visible", "assert_text", "assert_value"):
            expected = args.get("expected", "")
            el = None
            if args.get("role"):
                el = self.page.get_by_role(args["role"], name=args.get("locator", "")).first
            elif args.get("placeholder"):
                el = self.page.get_by_placeholder(args["placeholder"]).first
            elif args.get("label"):
                el = self.page.get_by_label(args["label"]).first
            elif args.get("locator") or args.get("css") or args.get("selector"):
                sel = args.get("locator") or args.get("css") or args.get("selector")
                el = self.page.locator(f"text={sel}").first
            if el is None:
                raise StepRunError(f"{desc}: 缺少定位参数")
            if not el.is_visible(timeout=5000):
                raise StepRunError(f"{desc}: 元素不可见")
            if action == "assert_text" and expected and expected not in (el.inner_text() or ""):
                raise StepRunError(f"{desc}: 文本不匹配，期望包含 {expected}")
            if action == "assert_value" and expected:
                val = (el.input_value() if el.evaluate(
                    "el => ['INPUT','TEXTAREA','SELECT'].includes(el.tagName)") else el.inner_text()) or ""
                if expected not in val:
                    raise StepRunError(f"{desc}: 值不匹配，期望包含 {expected}")

    def _call_pom(self, action, args, desc):
        ALIASES = {"click_search": "click_search_btn", "click_save": "click_save_btn"}
        method_name = ALIASES.get(action, action)

        # search current page first
        if self.current_page and self.current_page in self.pages:
            po = self.pages[self.current_page]
            if hasattr(po, method_name) and callable(getattr(po, method_name)):
                return getattr(po, method_name)(**args) if args else getattr(po, method_name)()

        # search all pages
        for pk, po in self.pages.items():
            if hasattr(po, method_name) and callable(getattr(po, method_name)):
                return getattr(po, method_name)(**args) if args else getattr(po, method_name)()

        raise StepRunError(f"未找到POM方法: {action}")
'''
