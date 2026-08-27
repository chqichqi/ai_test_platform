"""ActionResolver / ActionExecutor / EffectValidator.

三者严格分工：
- Resolver：只回答“应该操作哪个真实元素”；
- Executor：只回答“浏览器是否实际执行了动作”；
- Validator：只回答“执行后是否产生了与动作一致的可观察效果”。
"""
import time
from typing import Any, Dict, Optional

from app.core.logger import logger
from app.core.services.mcp_exploration_agent import Action, ActionType, ActionResult
from app.core.services.element_locator import LocateResult


_ROLE_MAP = {
    "button": "button", "link": "link", "tab": "tab", "menuitem": "menuitem",
    "checkbox": "checkbox", "radio": "radio", "switch": "switch", "row": "row",
    "table_row": "row", "combobox": "combobox", "listbox": "listbox",
    "textbox": "textbox", "searchbox": "searchbox",
}


class ActionResolver:
    def __init__(self, page, locator, config=None):
        self.page = page
        self.locator = locator
        self.config = config

    def resolve(self, action: Action, context_hint: str = "") -> LocateResult:
        target = (action.target_text or "").strip()
        role = (action.target_role or "").strip().lower()
        if not target:
            return LocateResult(False, strategy="empty_target")
        typ = action.type.value if isinstance(action.type, ActionType) else str(action.type).lower()

        # 表单控件：先找真正的 input/select，再允许通用文本回退。
        if typ == "fill":
            for fn in (
                lambda: self.locator._try_get_by_label(target, self._scope(context_hint)),
                lambda: self.locator._try_get_by_placeholder(target, self._scope(context_hint)),
                lambda: self.locator._try_get_by_role(target, "textbox", self._scope(context_hint)),
                lambda: self.locator._try_get_by_role(target, "searchbox", self._scope(context_hint)),
            ):
                try:
                    r = fn()
                    if r.found and r.locator:
                        return r
                except Exception:
                    pass

        if typ == "select":
            for rname in ("combobox", "listbox"):
                try:
                    r = self.locator._try_get_by_role(target, rname, self._scope(context_hint))
                    if r.found and r.locator:
                        return r
                except Exception:
                    pass
            try:
                r = self.locator._try_get_by_label(target, self._scope(context_hint))
                if r.found and r.locator:
                    return r
            except Exception:
                pass

        # Click / navigate / tab：角色优先，避免 get_by_text 命中祖先容器或 label。
        mapped = _ROLE_MAP.get(role)
        if mapped:
            try:
                r = self.locator._try_get_by_role(target, mapped, self._scope(context_hint))
                if r.found and r.locator:
                    return r
            except Exception:
                pass

        return self.locator.locate(
            target=target,
            role=role,
            context_hint=context_hint,
            ui_pattern=getattr(action, "ui_pattern", "") or "",
            scope_element=self._scope(context_hint),
        )

    def _scope(self, context_hint):
        # ElementLocator 返回 Locator scope；它在页面导航后重新解析，避免 stale handle。
        try:
            return self.locator._resolve_scope(context_hint or '', None)
        except Exception:
            return None


class ActionExecutor:
    def __init__(self, client, config=None):
        self.client = client
        self.page = client.page
        self.config = config

    def execute(self, action: Action, locate_result: LocateResult, fill_value: str = "", select_option: str = "") -> ActionResult:
        typ = action.type.value if isinstance(action.type, ActionType) else str(action.type).lower()
        loc = locate_result.locator if locate_result else None
        if typ in ("wait_for", "validate", "go_back"):
            return self._execute_non_element(action, typ, fill_value, select_option)
        if not locate_result or not locate_result.found:
            return ActionResult(action=action, success=False, error="locator_not_found")
        if loc is None:
            return ActionResult(action=action, success=False, error="locator_not_available")

        try:
            if not loc.is_visible(timeout=1000):
                return ActionResult(action=action, success=False, error="locator_not_visible")
        except Exception:
            pass

        try:
            if typ == "fill":
                if fill_value is None or str(fill_value) == "":
                    return ActionResult(action=action, success=False, error="fill_value_missing")
                loc.fill(str(fill_value), timeout=4000)
                return ActionResult(action=action, success=True)

            if typ == "select":
                return self._select(action, loc, select_option)

            if typ == "hover":
                loc.hover(timeout=4000)
                return ActionResult(action=action, success=True)

            if typ == "right_click":
                loc.click(button="right", timeout=4000)
                return ActionResult(action=action, success=True)

            if typ == "tab_switch":
                loc.click(timeout=4000)
                return ActionResult(action=action, success=True)

            if typ == "key_press":
                key = str(fill_value or select_option or action.target_text or "").strip()
                if not key:
                    return ActionResult(action=action, success=False, error="key_missing")
                self.page.keyboard.press(key)
                return ActionResult(action=action, success=True)

            if typ in ("click", "navigate", "table_row"):
                try:
                    loc.click(timeout=4000)
                except Exception as first:
                    # force 仅作为明确的第二尝试，仍然需要后续 EffectValidator 验证。
                    try:
                        loc.click(force=True, timeout=2500)
                    except Exception:
                        return ActionResult(action=action, success=False, error=f"click_failed:{first}")
                return ActionResult(action=action, success=True)

            return ActionResult(action=action, success=False, error=f"unsupported_action:{typ}")
        except Exception as exc:
            logger.warning(f"[ActionExecutor] {typ} failed: {exc}")
            return ActionResult(action=action, success=False, error=f"{type(exc).__name__}:{exc}")

    def _execute_non_element(self, action, typ, fill_value, select_option):
        try:
            if typ == "wait_for":
                seconds = float(getattr(self.config, "click_wait", 0.8) or 0.8)
                self.client.wait(seconds)
                return ActionResult(action=action, success=True)
            if typ == "validate":
                return ActionResult(action=action, success=True)
            if typ == "go_back":
                self.page.go_back()
                self.client.wait_for_page_ready(max_wait=getattr(self.config, "page_ready_timeout_fast", 8.0))
                return ActionResult(action=action, success=True)
        except Exception as exc:
            return ActionResult(action=action, success=False, error=f"{typ}_failed:{exc}")
        return ActionResult(action=action, success=False, error=f"unsupported_non_element:{typ}")

    def _select(self, action, loc, option):
        if not option:
            loc.click(timeout=4000)
            return ActionResult(action=action, success=True)
        try:
            tag = loc.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            tag = ""
        if tag == "select":
            try:
                loc.select_option(label=option)
                return ActionResult(action=action, success=True)
            except Exception:
                try:
                    loc.select_option(value=option)
                    return ActionResult(action=action, success=True)
                except Exception as exc:
                    return ActionResult(action=action, success=False, error=f"native_select_failed:{exc}")

        # 自定义下拉：先打开，再只在可见 option/listbox 中找目标。
        loc.click(timeout=4000)
        self.client.wait(float(getattr(self.config, "dropdown_wait", 0.8) or 0.8))
        option_loc = self._find_visible_option(option)
        if option_loc is None:
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            return ActionResult(action=action, success=False, error=f"select_option_not_found:{option}")
        try:
            option_loc.click(timeout=4000)
            return ActionResult(action=action, success=True)
        except Exception as exc:
            return ActionResult(action=action, success=False, error=f"select_option_click_failed:{exc}")

    def _find_visible_option(self, target):
        candidates = []
        try:
            candidates.extend([
                self.page.get_by_role("option", name=target, exact=True),
                self.page.get_by_role("option", name=target, exact=False),
            ])
        except Exception:
            pass
        try:
            candidates.extend([
                self.page.locator('[role="listbox"]:visible').get_by_text(target, exact=True),
                self.page.locator('[role="listbox"]:visible').get_by_text(target, exact=False),
            ])
        except Exception:
            pass
        for c in candidates:
            try:
                if c.count() and c.first.is_visible():
                    return c.first
            except Exception:
                continue
        return None


class EffectValidator:
    def __init__(self, client, state_manager, config=None):
        self.client = client
        self.page = client.page
        self.state_manager = state_manager
        self.config = config

    def validate(self, action: Action, before: Dict[str, Any], after: Dict[str, Any], execution_ok: bool,
                 fill_value: str = "", select_option: str = "") -> Dict[str, Any]:
        diff = self.state_manager.diff(before, after)
        changes = diff.get("changes", {})
        typ = action.type.value if isinstance(action.type, ActionType) else str(action.type).lower()
        url_changed = "url" in changes
        dom_changed = "dom" in changes
        overlay_changed = "overlay" in changes
        form_changed = "form_values" in changes
        tab_changed = "active_tab" in changes
        body_changed = "body_text" in changes

        if not execution_ok:
            return {"valid": False, "effect": "execution_failed", "confidence": 0.0, "diff": diff}
        if typ in ("wait_for", "validate"):
            return {"valid": True, "effect": typ, "confidence": 1.0, "diff": diff}
        if typ == "go_back":
            return {"valid": bool(url_changed or dom_changed), "effect": "go_back", "confidence": .95 if url_changed else .75, "diff": diff}
        if typ == "fill":
            # React controlled input 有时 DOM fingerprint 不变；直接核对目标字段值。
            desired = str(fill_value or "")
            matched = self._input_contains_value(action.target_text, desired)
            valid = bool(form_changed or matched)
            return {"valid": valid, "effect": "form_changed" if valid else "no_observable_form_change",
                    "confidence": .97 if matched else .90 if form_changed else .35, "diff": diff}
        if typ == "select":
            selected = self._selected_option_is(select_option)
            valid = bool(form_changed or dom_changed or selected)
            return {"valid": valid, "effect": "selection_changed" if valid else "no_observable_selection_change",
                    "confidence": .97 if selected else .90 if (form_changed or dom_changed) else .35, "diff": diff}
        if typ == "tab_switch":
            valid = bool(tab_changed or dom_changed)
            return {"valid": valid, "effect": "tab_changed" if tab_changed else "tab_dom_changed",
                    "confidence": .96 if tab_changed else .80 if dom_changed else .30, "diff": diff}
        if typ in ("click", "navigate", "table_row"):
            valid = bool(url_changed or dom_changed or overlay_changed or body_changed)
            effect = "navigation" if url_changed else "overlay" if overlay_changed else "dom_changed" if dom_changed else "body_changed" if body_changed else "static"
            return {"valid": valid, "effect": effect, "confidence": .98 if url_changed else .92 if valid else .25, "diff": diff}
        if typ in ("hover", "right_click"):
            valid = bool(dom_changed or overlay_changed or body_changed)
            return {"valid": valid, "effect": "interaction" if valid else "static", "confidence": .85 if valid else .25, "diff": diff}
        return {"valid": False, "effect": "unsupported", "confidence": 0.0, "diff": diff}

    def _input_contains_value(self, target, desired):
        if desired == "":
            return False
        try:
            return bool(self.page.evaluate(
                """(p) => Array.from(document.querySelectorAll('input,textarea')).some(el => {
                    const t=(el.getAttribute('name')||el.getAttribute('aria-label')||el.getAttribute('placeholder')||el.id||'');
                    return t.includes(p.target) && String(el.value ?? '') === p.value;
                })""", {"target": target or "", "value": desired}))
        except Exception:
            return False

    def _selected_option_is(self, option):
        if not option:
            return False
        try:
            return bool(self.page.evaluate(
                """(opt) => Array.from(document.querySelectorAll('[role="option"][aria-selected="true"],option:checked'))
                    .some(el => String(el.innerText || el.textContent || el.value || '').trim() === opt)""", option))
        except Exception:
            return False
