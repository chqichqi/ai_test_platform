"""State Manager.

状态是 URL + DOM 结构 + overlay + active tab + form values + 页面文本摘要。
它同时负责 Case 之间的硬复位，避免同 URL 下残留弹窗、Tab、表单值导致串案。
"""
import hashlib
import json
import time
import re
from typing import Any, Dict, Optional

from app.core.logger import logger


class StateManager:
    def __init__(self, client, config=None, module_name: str = ""):
        self.client = client
        self.page = client.page
        self.config = config
        self.module_name = module_name or "module"
        self.states: Dict[str, Dict[str, Any]] = {}
        self.current_state: Optional[Dict[str, Any]] = None

    @staticmethod
    def normalize_url(url: str) -> str:
        if not url:
            return ""
        url = str(url).strip()
        if url == "about:blank":
            return url
        # 保留 hash 路由，忽略 query；query 通常是分页/时间戳等非状态身份信息。
        if "#" in url:
            base, frag = url.split("#", 1)
            frag = frag.split("?", 1)[0].rstrip("/")
            return base.rstrip("/") + "#" + frag
        return url.split("?", 1)[0].rstrip("/")

    @classmethod
    def state_key(cls, snapshot: Dict[str, Any]) -> str:
        data = {
            "url": cls.normalize_url(snapshot.get("url", "")),
            "dom": snapshot.get("dom_fingerprint", ""),
            "overlay": bool(snapshot.get("overlay", False)),
            "active_tab": snapshot.get("active_tab", ""),
            "forms": snapshot.get("form_values", {}),
            "body": snapshot.get("body_text_sample", "")[:600],
        }
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

    def capture(self, label: str = "", include_dom: bool = True) -> Dict[str, Any]:
        url = self.client.get_url() or ""
        try:
            title = self.page.title() or ""
        except Exception:
            title = ""
        try:
            body = self.page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        except Exception:
            body = ""

        dom_fingerprint = ""
        if include_dom:
            try:
                dom_fingerprint = self.page.evaluate(
                    """
                    () => {
                      const norm = s => String(s || '').replace(/\\s+/g, ' ').trim().slice(0, 100);
                      const visible = el => {
                        const r = el.getBoundingClientRect();
                        const st = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
                      };
                      const nodes = document.querySelectorAll(
                        'button,a[href],input,textarea,select,[role="button"],[role="link"],'
                        '[role="tab"],[role="combobox"],[role="option"],[role="dialog"],'
                        '[role="alert"],[role="status"],table,tbody,tr'
                      );
                      const items = [];
                      for (const el of Array.from(nodes).slice(0, 350)) {
                        if (!visible(el)) continue;
                        const tag = el.tagName.toLowerCase();
                        const text = norm(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title'));
                        const role = el.getAttribute('role') || '';
                        const checked = typeof el.checked === 'boolean' ? (el.checked ? '1' : '0') : '';
                        const selected = el.getAttribute('aria-selected') || '';
                        const expanded = el.getAttribute('aria-expanded') || '';
                        const disabled = el.disabled || el.getAttribute('aria-disabled') || '';
                        const value = ['input','textarea','select'].includes(tag) ? String(el.value ?? '').slice(0, 80) : '';
                        if (text || role || value || ['input','textarea','select'].includes(tag)) {
                          items.push([tag, role, text, checked, selected, expanded, disabled, value].join('|'));
                        }
                      }
                      return JSON.stringify(items);
                    }
                    """
                ) or ""
            except Exception:
                dom_fingerprint = ""

        try:
            overlay_raw = self.client.get_overlay_state() or {}
            overlay = bool(overlay_raw.get("overlay", 0)) if isinstance(overlay_raw, dict) else bool(overlay_raw)
        except Exception:
            overlay = False

        try:
            active_tab = self.page.evaluate(
                """() => {
                    const el = document.querySelector('[role="tab"][aria-selected="true"]');
                    return el ? String(el.innerText || el.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim() : '';
                }"""
            ) or ""
        except Exception:
            active_tab = ""

        try:
            form_values = self.page.evaluate(
                """() => {
                    const out = {};
                    document.querySelectorAll('input,textarea,select').forEach((el, i) => {
                      if (i >= 100) return;
                      const key = el.getAttribute('name') || el.getAttribute('aria-label') ||
                                  el.getAttribute('placeholder') || el.id || ('field_' + i);
                      out[key] = String(el.value ?? '').slice(0, 160);
                    });
                    return out;
                }"""
            ) or {}
        except Exception:
            form_values = {}

        snapshot = {
            "label": label,
            "url": url,
            "normalized_url": self.normalize_url(url),
            "title": title,
            "body_text_len": len(body),
            "body_text_sample": re.sub(r"\s+", " ", body).strip()[:1600],
            "dom_fingerprint": hashlib.sha1((dom_fingerprint or "").encode("utf-8")).hexdigest() if dom_fingerprint else "",
            "overlay": overlay,
            "active_tab": active_tab,
            "form_values": form_values,
            "timestamp": time.time(),
        }
        snapshot["state_id"] = self.state_key(snapshot)
        return snapshot

    def record(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        snapshot["state_id"] = snapshot.get("state_id") or self.state_key(snapshot)
        self.states[snapshot["state_id"]] = snapshot
        self.current_state = snapshot
        return snapshot

    def capture_and_record(self, label: str = "") -> Dict[str, Any]:
        return self.record(self.capture(label))

    def diff(self, before: Optional[Dict], after: Optional[Dict]) -> Dict[str, Any]:
        if not before or not after:
            return {"changed": False, "reason": "missing_snapshot", "changes": {}}
        changes = {}
        if self.normalize_url(before.get("url")) != self.normalize_url(after.get("url")):
            changes["url"] = {"before": before.get("url", ""), "after": after.get("url", "")}
        if before.get("dom_fingerprint") != after.get("dom_fingerprint"):
            changes["dom"] = True
        if before.get("overlay") != after.get("overlay"):
            changes["overlay"] = {"before": before.get("overlay"), "after": after.get("overlay")}
        if before.get("active_tab") != after.get("active_tab"):
            changes["active_tab"] = {"before": before.get("active_tab", ""), "after": after.get("active_tab", "")}
        if before.get("form_values") != after.get("form_values"):
            changes["form_values"] = {"before": before.get("form_values", {}), "after": after.get("form_values", {})}
        if before.get("body_text_sample") != after.get("body_text_sample"):
            changes["body_text"] = True
        return {
            "changed": bool(changes),
            "changes": changes,
            "before_state_id": before.get("state_id", ""),
            "after_state_id": after.get("state_id", ""),
        }

    def restore(self, target_url: str, max_wait: Optional[float] = None, hard_reset: bool = False) -> bool:
        if not target_url or target_url == "about:blank":
            return False
        expected = self.normalize_url(target_url)
        current = self.client.get_url()

        # about:blank 不能作为有效状态；优先回退历史页，失败再 goto 目标。
        if self.normalize_url(current) == "about:blank":
            try:
                self.page.go_back(wait_until="domcontentloaded", timeout=getattr(self.config, "page_goto_timeout", 15000))
            except Exception:
                pass
            current = self.client.get_url()

        try:
            if hard_reset:
                if self.normalize_url(current) == expected:
                    # 同 URL 的 SPA 页面，goto 往往复用当前文档/状态；硬复位必须显式 reload。
                    self.page.reload(wait_until="domcontentloaded", timeout=getattr(self.config, "page_goto_timeout", 15000))
                else:
                    self.client.goto(target_url, timeout=getattr(self.config, "page_goto_timeout", 15000))
            elif self.normalize_url(current) != expected:
                self.client.goto(target_url, timeout=getattr(self.config, "page_goto_timeout", 15000))
        except Exception as exc:
            logger.warning(f"[StateManager] restore navigation failed: {exc}")
            try:
                self.page.goto(target_url, wait_until="domcontentloaded", timeout=getattr(self.config, "page_goto_timeout", 15000))
            except Exception:
                return False

        if max_wait is not None:
            timeout = max_wait
        elif hard_reset:
            timeout = getattr(self.config, "case_reset_ready_timeout",
                              getattr(self.config, "page_ready_timeout_fast", 8.0))
        else:
            timeout = getattr(self.config, "page_ready_timeout_fast", 8.0)
        try:
            if hasattr(self.client, "wait_for_page_ready_fast"):
                self.client.wait_for_page_ready_fast(max_wait=timeout)
            else:
                self.client.wait_for_page_ready(max_wait=timeout)
        except Exception:
            pass

        actual = self.normalize_url(self.client.get_url())
        if actual != expected:
            logger.warning(f"[StateManager] restore mismatch expected={expected} actual={actual}")
            return False
        return True

    def reset_to(self, start_url: str, hard_reset: bool = True) -> bool:
        if not start_url or self.normalize_url(start_url) == "about:blank":
            return False
        ok = self.restore(start_url, hard_reset=hard_reset)
        if not ok or self.normalize_url(self.client.get_url()) == "about:blank":
            return False
        # 清理浏览器层面的浮层/焦点；不清理业务数据，避免误伤登录态。
        try:
            self.page.keyboard.press("Escape")
            self.page.evaluate("""() => { window.scrollTo(0,0); const a=document.activeElement; if(a && a.blur) a.blur(); }""")
        except Exception:
            pass
        self.current_state = self.capture_and_record("case_start")
        return True
