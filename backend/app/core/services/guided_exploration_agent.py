"""Case -> State -> Action -> Effect -> Evidence guided exploration agent.

兼容原 MCPExplorationAgent 的公共返回格式，但内部不再把多个测试用例串成一条流程。
核心链路：
    TestCase
      -> CasePlan
      -> StateManager
      -> ActionResolver
      -> ActionExecutor
      -> EffectValidator
      -> Evidence
      -> KG
      -> UI Case Generator
"""
import json
import os
import re
import time
from typing import Any, Dict, List

from app.core.logger import logger
from app.core.services.mcp_exploration_agent import (
    MCPExplorationAgent, Action, ActionType, ActionResult, StateNode,
)
from app.core.services.element_locator import ElementLocator, LocateResult
from app.core.services.state_manager import StateManager
from app.core.services.action_executor import ActionResolver, ActionExecutor, EffectValidator
from app.core.services.case_explorer import CaseExplorer, CasePlan


class GuidedExplorationAgent(MCPExplorationAgent):
    """按测试用例独立探索，保留原 Agent 的 Phase 1/3/4 能力。"""

    def __init__(self, client, config, llm_service=None, module_name="", platform_type="web"):
        super().__init__(client, config, llm_service, module_name)
        self.platform_type = platform_type
        self._locator = ElementLocator(client.page, config)
        self.state_manager = StateManager(client, config, module_name)
        self.action_resolver = ActionResolver(client.page, self._locator, config)
        self.action_executor = ActionExecutor(client, config)
        self.effect_validator = EffectValidator(client, self.state_manager, config)
        self.case_explorer = CaseExplorer(self)
        self._guided_steps = []
        self._case_plans: List[CasePlan] = []
        self._evidence: List[Dict[str, Any]] = []
        self._case_results: List[Dict[str, Any]] = []
        self._trace = None
        self._cancelled = False
        self._case_contexts = {}

    def set_case_contexts(self, test_cases):
        """注入 TestCase 元数据，供补充探索在没有 CaseStepBatch 时恢复 CasePlan。"""
        self._case_contexts = {}
        for tc in test_cases or []:
            cid = str(getattr(tc, 'id', '') or getattr(tc, 'case_id', '') or '')
            if cid:
                self._case_contexts[cid] = tc

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def explore_guided(self, guided_steps: List, start_url: str = '', trace_logger=None,
                       progress_cb=None, cancel_check=None) -> Dict[str, Any]:
        t0 = time.time()
        self._reset_runtime()
        self._guided_steps = guided_steps or []
        self._trace = trace_logger
        start_url = start_url or self.client.get_url()
        self._set_module_boundary(start_url)
        self.client.inject_console_hook()
        self._setup_dialog_handlers()

        self._prepare_case_plans(start_url)
        logger.info(f"[GuidedAgent] module={self._module}, cases={len(self._case_plans)}, "
                    f"steps={sum(len(p.steps) for p in self._case_plans)}")

        # Phase 1 只扫描模块入口，不把它当作“所有用例已覆盖”。
        try:
            self._site_map = self._phase1_site_map()
            self._nav_names = {self._norm(m.get("name", "")) for m in self._site_map.get("modules", [])
                               if isinstance(m, dict)}
        except Exception as exc:
            logger.warning(f"[GuidedAgent] phase1 site map failed: {exc}")
            self._site_map = {"modules": []}

        try:
            case_run = self.case_explorer.run(
                self._case_plans, start_url,
                progress_cb=progress_cb,
                cancel_check=cancel_check,
            )
            self._evidence = case_run.get("evidence", [])
            self._cancelled = case_run.get("interrupted") == "cancelled"
        except Exception as exc:
            self._error_events.append({"stage": "case_exploration", "error": str(exc), "url": start_url})
            logger.exception("[GuidedAgent] case exploration failed")

        # Phase 3 仅在最后恢复到入口页后做静态组件扫描；不会反过来伪造 guided evidence。
        deep_dive = {}
        try:
            self._restore_first_page(start_url)
            self._scope_element = self.client.get_main_content()
            deep_dive = self._phase3_deep_dive(
                interactive=getattr(self.config, "guided_p3_interactive", False)
            ) or {}
        except Exception as exc:
            logger.warning(f"[GuidedAgent] phase3 failed: {exc}")

        # 引导 SELECT 扫描到的选项合并到 deep_dive。
        dd = deep_dive.setdefault("dropdowns", {}) if isinstance(deep_dive, dict) else {}
        for key, value in getattr(self, "_p3_dropdown_options", {}).items():
            if key not in dd:
                dd[key] = {"options": value, "option_count": len(value)}

        elapsed = time.time() - t0
        successful = [e for e in self._evidence if e.get("status") == "success" and
                      (e.get("effect") or {}).get("valid")]
        stats = {
            "total_elements": len(successful),
            "navigated_elements": sum(1 for e in successful if (e.get("effect") or {}).get("effect") == "navigation"),
            "pages_explored": len(self._visited_urls),
            "visited_states": len(self.state_manager.states),
            "elapsed_seconds": round(elapsed, 1),
            "errors": len(self._error_events) + sum(1 for e in self._evidence if e.get("status") != "success"),
            "guided_steps_total": sum(len(p.steps) for p in self._case_plans),
            "guided_steps_executed": len(successful),
            "guided_steps_successful": len(successful),
            "guided_steps_failed": sum(1 for e in self._evidence if e.get("status") != "success"),
            "cases_total": len(self._case_plans),
            "cases_explored": len([c for c in self._case_results if c.get("status") != "not_started"]),
            "exploration_mode": "case_state_guided",
            "platform_type": self.platform_type,
            "interrupted": "cancelled" if self._cancelled else None,
        }

        # 保留 Phase 4 能力，但只给它真实 evidence。
        phase4 = {}
        if self.llm:
            try:
                phase4 = self._phase4_synthesis(
                    start_url, self._site_map, self._build_element_jumps(), deep_dive
                ) or {}
            except Exception as exc:
                logger.warning(f"[GuidedAgent] phase4 synthesis failed: {exc}")

        self._save_results(start_url)
        state_graph = self._serialize_state_graph()
        pages = [{"url": u} for u in self._visited_urls]
        diagnostics = self._build_step_diagnostics()
        jumps = self._build_element_jumps()

        return {
            "site_map": self._site_map,
            "element_jumps": {"_main": {"url": start_url, "elements": jumps}},
            "deep_dive": deep_dive,
            "stats": stats,
            "pages_visited": list(self._visited_urls),
            "error_events": self._error_events,
            "state_graph": state_graph,
            "module_docs": phase4.get("module_docs", ""),
            "site_map_md": phase4.get("site_map_md", ""),
            "page_object_code": phase4.get("page_object_code", ""),
            "elements": jumps,
            "pages": pages,
            "step_diagnostics": diagnostics,
            "evidence": self._evidence,
            "case_results": self._case_results,
            "case_plans": [self._plan_dict(p) for p in self._case_plans],
        }

    # ------------------------------------------------------------------
    # Case Explorer callbacks
    # ------------------------------------------------------------------
    def explore_one_step(self, plan: CasePlan, step_index: int, gs) -> Dict[str, Any]:
        seq, target, role, action_type, fill_value, select_option, context, ui_pattern = self._unpack_step(gs)
        before = self.state_manager.capture_and_record(f"before_case_{plan.case_id}_step_{seq}")
        before_url = before.get("url", "")
        self._visited_urls.add(before_url)

        if not target and action_type not in ("go_back", "wait_for", "validate"):
            return self._make_evidence(plan, gs, seq, target, action_type, before, before,
                                       None, False, "empty_target")

        if action_type in ("go_back", "GO_BACK"):
            ok = self._go_back_to_case_start(plan, before_url)
            after = self.state_manager.capture_and_record(f"after_case_{plan.case_id}_step_{seq}")
            effect = {"valid": ok, "effect": "go_back", "confidence": 0.95 if ok else 0.0,
                      "diff": self.state_manager.diff(before, after)}
            return self._make_evidence(plan, gs, seq, target, "go_back", before, after,
                                       None, ok, "" if ok else "go_back_failed", effect=effect)

        action = Action(
            type=self._str_to_action_type(action_type),
            label=target,
            target_text=target,
            target_role=role,
            source="guided_step",
            context_hint=context,
            ui_pattern=ui_pattern,
            value=fill_value or select_option or "",
        )

        # ActionResolver 负责 action-aware locator 优先级。
        locate_result = self.action_resolver.resolve(action, context_hint=context)
        if not locate_result.found:
            # SPA 异步渲染：等待目标出现一次再重新定位；仍失败即真实失败。
            self._wait_for_target_text(target)
            locate_result = self.action_resolver.resolve(action, context_hint=context)

        if not locate_result.found:
            after = self.state_manager.capture_and_record(f"failed_case_{plan.case_id}_step_{seq}")
            return self._make_evidence(plan, gs, seq, target, action_type, before, after,
                                       locate_result, False, "element_not_found")

        # 保存 locator 证据后再执行；locator 本身不等于 success。
        result = self.action_executor.execute(
            action, locate_result, fill_value=fill_value, select_option=select_option
        )
        self.client.wait(getattr(self.config, "click_wait", 0.8))
        self._close_extra_pages()
        self._recover_about_blank(before_url)
        current_after_url = self.client.get_url()
        # 模块边界是安全约束：跨模块导航不进入探索图，也不作为成功证据。
        if current_after_url and hasattr(self, "_is_within_module") and not self._is_within_module(current_after_url):
            logger.warning(f"[GuidedAgent] block cross-module navigation: {current_after_url}")
            try:
                self.state_manager.restore(before_url)
            except Exception:
                pass
            result = ActionResult(action=action, success=False, error="cross_module_navigation_blocked")
        after = self.state_manager.capture_and_record(f"after_case_{plan.case_id}_step_{seq}")
        self._visited_urls.add(after.get("url", ""))

        effect = self.effect_validator.validate(action, before, after, result.success)
        final_ok = bool(result.success and effect.get("valid"))
        error = result.error if not result.success else ("effect_not_verified" if not final_ok else "")

        ev = self._make_evidence(
            plan, gs, seq, target, action_type, before, after,
            locate_result, final_ok, error, effect=effect
        )
        self._record_trace(plan, gs, locate_result, result, effect, before, after)
        self._update_state_graph(plan, target, before, after, effect)
        return ev

    def record_case_start(self, plan: CasePlan, state: Dict[str, Any]):
        self._case_results.append({
            "case_id": plan.case_id,
            "case_name": plan.case_name,
            "module": plan.module,
            "test_case_id": plan.test_case_id or plan.case_id,
            "logical_case_id": plan.logical_case_id or plan.case_id,
            "revision_no": plan.revision_no,
            "version_id": plan.version_id,
            "project_id": plan.project_id,
            "preconditions": plan.preconditions,
            "start_url": plan.start_url,
            "start_state_id": state.get("state_id", ""),
            "status": "started",
        })

    def finish_case(self, plan: CasePlan, status: str, error: str = ""):
        for item in reversed(self._case_results):
            if item.get("case_id") == plan.case_id:
                item["status"] = status
                item["error"] = error or ""
                item["finished_at"] = time.time()
                return
        self._case_results.append({
            "case_id": plan.case_id, "case_name": plan.case_name, "module": plan.module,
            "start_url": plan.start_url, "status": status, "error": error or "",
            "finished_at": time.time(),
        })

    def make_case_error(self, plan: CasePlan, error: str) -> Dict[str, Any]:
        return {
            "case_id": plan.case_id, "case_name": plan.case_name, "module": plan.module,
            "seq": 0, "target": "", "action": "case_start", "status": "failed",
            "error": error, "effect": {"valid": False, "effect": "case_start_failed", "confidence": 0.0},
            "pages_touched": [],
        }

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------
    def _make_evidence(self, plan, gs, seq, target, action_type, before, after,
                       locate_result, success, error, effect=None):
        info = locate_result.element_info if locate_result else {}
        evidence = {
            "case_id": plan.case_id,
            "case_name": plan.case_name,
            "module": plan.module,
            "preconditions": plan.preconditions,
            "expected_result": plan.expected_result,
            "seq": seq,
            "target": target,
            "action": action_type,
            "role": self._unpack_step(gs)[2],
            "context": self._unpack_step(gs)[6],
            "ui_pattern": self._unpack_step(gs)[7],
            "status": "success" if success else "failed",
            "error": error or "",
            "before_url": before.get("url", ""),
            "after_url": after.get("url", ""),
            "before_state_id": before.get("state_id", ""),
            "after_state_id": after.get("state_id", ""),
            "locator": {
                "strategy": locate_result.strategy if locate_result else "",
                "actual_text": info.get("text", "") if info else "",
                "role": info.get("role", "") if info else "",
                "tag": info.get("tag", "") if info else "",
                "selector": info.get("selector", "") if info else "",
                "primary_locator": info.get("selector", "") if info else "",
                "id": info.get("id", "") if info else "",
                "name": info.get("name", "") if info else "",
                "placeholder": info.get("placeholder", "") if info else "",
                "href": info.get("href", "") if info else "",
            },
            "effect": effect or {"valid": success, "effect": "executed" if success else "failed", "confidence": 0.0},
            "confidence": (effect or {}).get("confidence", 0.0) if effect else 0.0,
            "pages_touched": list(dict.fromkeys([before.get("url", ""), after.get("url", "")])),
        }
        self._evidence.append(evidence)
        return evidence

    def _build_step_diagnostics(self):
        out = []
        for ev in self._evidence:
            loc = ev.get("locator", {})
            out.append({
                "seq": ev.get("seq", 0),
                "case_id": ev.get("case_id", ""),
                "case_name": ev.get("case_name", ""),
                "target": ev.get("target", ""),
                "action": ev.get("action", ""),
                "status": ev.get("status", "failed"),
                "strategy": loc.get("strategy", ""),
                "actual_text": loc.get("actual_text", ""),
                "locator": loc,
                "effect": ev.get("effect", {}),
                "before_state_id": ev.get("before_state_id", ""),
                "after_state_id": ev.get("after_state_id", ""),
                "error": ev.get("error", ""),
                "confidence": ev.get("confidence", 0.0),
            })
        return out

    def _build_element_jumps(self):
        out = []
        seen = set()
        for ev in self._evidence:
            if ev.get("status") != "success" or not (ev.get("effect") or {}).get("valid"):
                continue
            loc = ev.get("locator", {})
            key = (ev.get("case_id", ""), ev.get("seq", 0), ev.get("target", ""), ev.get("before_state_id", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": ev.get("target", ""),
                "actual_text": loc.get("actual_text", "") or ev.get("target", ""),
                "clicked": True,
                "navigated": (ev.get("effect") or {}).get("effect") == "navigation",
                "jump_url": ev.get("after_url", ""),
                "role": loc.get("role", "") or ev.get("role", ""),
                "action_type": ev.get("action", ""),
                "selector": loc.get("selector", ""),
                "locator_strategy": loc.get("strategy", ""),
                "case_id": ev.get("case_id", ""),
                "state_before": ev.get("before_state_id", ""),
                "state_after": ev.get("after_state_id", ""),
                "confidence": ev.get("confidence", 0.0),
            })
        return out

    # ------------------------------------------------------------------
    # State / case setup
    # ------------------------------------------------------------------
    def _prepare_case_plans(self, start_url: str):
        plans = list(getattr(self._guided_steps, "case_plans", []) or [])
        if not plans:
            grouped = {}
            for gs in self._guided_steps or []:
                cid = str(getattr(gs, '_case_id', '') or '')
                if cid:
                    grouped.setdefault(cid, []).append(gs)
            if grouped:
                for cid, steps in grouped.items():
                    tc = self._case_contexts.get(cid)
                    plans.append(CasePlan(
                        case_id=cid,
                        case_name=(getattr(tc, 'name', None) or getattr(tc, 'title', None) or cid) if tc else cid,
                        module=self._module,
                        preconditions=getattr(tc, 'preconditions', '') or '' if tc else '',
                        expected_result=getattr(tc, 'expected_result', '') or '' if tc else '',
                        start_url=start_url, steps=steps,
                        test_case_id=cid,
                        logical_case_id=str(getattr(tc, 'logical_case_id', '') or cid) if tc else cid,
                        revision_no=int(getattr(tc, 'revision_no', 1) or 1) if tc else 1,
                        version_id=getattr(tc, 'version_id', None) if tc else None,
                        project_id=getattr(tc, 'project_id', None) if tc else None,
                    ))
        if not plans:
            plans = [CasePlan(case_id="legacy-1", case_name="兼容模式", module=self._module, start_url=start_url, steps=list(self._guided_steps))]
        for p in plans:
            p.start_url = p.start_url or start_url
        self._case_plans = plans

    def _reset_runtime(self):
        self._visited_urls = set()
        self._pages_explored = []
        self._all_element_jumps = []
        self._click_log = []
        self._state_counter = 0
        self._error_events = []
        self._site_map = {"modules": []}
        self._state_graph = []
        self._scope_element = None
        self._observer_injected = False
        self._cancelled = False
        self._evidence = []
        self._case_results = []
        self.state_manager.states = {}
        self.state_manager.current_state = None

    def _go_back_to_case_start(self, plan: CasePlan, before_url: str) -> bool:
        try:
            self.client.back()
            self.client.wait_for_page_ready(max_wait=getattr(self.config, "page_ready_timeout_fast", 8.0))
            cur = self.client.get_url()
            if self.state_manager.normalize_url(cur) == self.state_manager.normalize_url(plan.start_url):
                return True
        except Exception:
            pass
        return self.state_manager.restore(plan.start_url, hard_reset=True)

    def _recover_about_blank(self, before_url: str):
        try:
            cur = self.client.get_url()
            if cur == "about:blank" and before_url and before_url != "about:blank":
                self.client.goto(before_url)
                self.client.wait_for_page_ready(max_wait=5.0)
        except Exception:
            pass

    def _wait_for_target_text(self, target: str, max_wait=None) -> bool:
        if not target:
            return True
        max_wait = max_wait if max_wait is not None else getattr(self.config, "target_wait_timeout", 6.0)
        import re as _re
        needle = _re.sub(r"\s+", "", target)
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                found = self.page.evaluate("""(needle) => {
                    const norm=s=>String(s||'').replace(/[ \t\r\n]+/g,'');
                    return Array.from(document.querySelectorAll('button,a,input,textarea,select,[role],[aria-label],[title]'))
                      .some(el => norm(el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder') || el.value).includes(needle));
                }""", needle)
                if found:
                    return True
            except Exception:
                pass
            self.client.wait(0.35)
        return False

    def _update_state_graph(self, plan, target, before, after, effect):
        before_id = before.get("state_id", "")
        after_id = after.get("state_id", "")
        if not before_id:
            return
        node = next((x for x in self._state_graph if x.fingerprint == before_id), None)
        if node is None:
            node = StateNode(
                url=before.get("url", ""), title=before.get("title", ""),
                fingerprint=before_id, actions=[], children=[], deep_dive={"case_id": plan.case_id}
            )
            self._state_graph.append(node)
        if target and target not in node.actions:
            node.actions.append(target)
        if after_id and after_id != before_id and after_id not in node.children:
            node.children.append(after_id)

        if after_id and after_id != before_id and not any(x.fingerprint == after_id for x in self._state_graph):
            self._state_graph.append(StateNode(
                url=after.get("url", ""), title=after.get("title", ""),
                fingerprint=after_id, actions=[], children=[], deep_dive={"case_id": plan.case_id}
            ))

    def _serialize_state_graph(self):
        return [{
            "url": x.url,
            "title": x.title,
            "fingerprint": x.fingerprint,
            "actions": x.actions,
            "children": x.children,
            "deep_dive": x.deep_dive,
        } for x in self._state_graph]

    # ------------------------------------------------------------------
    # Compatibility / infrastructure
    # ------------------------------------------------------------------
    def _setup_dialog_handlers(self):
        """仅禁用浏览器原生弹框；不再安装 MutationObserver 自动点击任意按钮。

        原实现会在 modal 出现后自动点击最后一个按钮，这会把“弹窗打开”直接变成
        “弹窗被错误关闭”，并污染后续步骤。真正的 modal 动作必须由测试步骤驱动。
        """
        try:
            self.page.evaluate("""() => {
                window.print = () => {};
                window.alert = () => {};
                window.confirm = () => false;
                window.prompt = () => null;
            }""")
            self._observer_injected = True
        except Exception:
            pass

    def _close_extra_pages(self):
        try:
            pages = list(self.page.context.pages) if self.page.context else []
            for p in pages:
                if p != self.page:
                    try:
                        p.close()
                    except Exception:
                        pass
        except Exception:
            pass

    def _restore_first_page(self, start_url: str):
        if start_url:
            self.state_manager.restore(start_url)
            try:
                self._scope_element = self.client.get_main_content()
            except Exception:
                self._scope_element = None

    def _set_module_boundary(self, url: str):
        key = self.state_manager.normalize_url(url)
        if key.startswith("/"):
            parts = key.split("/")
            self._module_url_root = parts[1] if len(parts) > 1 else key.strip("/")
        else:
            from urllib.parse import urlparse
            path = urlparse(url).path.strip("/")
            self._module_url_root = path.split("/")[0] if path else key

    def _clean_state_dir(self):
        state_dir = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
            "tests", "exploration", "states", self._module
        ))
        try:
            import shutil
            if os.path.exists(state_dir):
                shutil.rmtree(state_dir)
        except Exception:
            pass

    def _save_results(self, start_url=None):
        """保存最小兼容日志；失败写盘绝不能打断探索。"""
        try:
            log_dir = os.path.abspath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tests", "exploration"
            ))
            os.makedirs(log_dir, exist_ok=True)
            safe = re.sub(r'[\x00-\x1f\x7f\\/:*?"<>| ]', '_', self._module or "module")[:50]
            with open(os.path.join(log_dir, f"{safe}-click-log.json"), "w", encoding="utf-8") as f:
                json.dump({"module": self._module, "evidence": self._evidence,
                           "case_results": self._case_results}, f, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            logger.warning(f"[GuidedAgent] save result failed: {exc}")

    def _record_trace(self, plan, gs, locate_result, result, effect, before, after):
        if not self._trace:
            return
        try:
            seq, target, role, action_type, *_ = self._unpack_step(gs)
            page_len = self.page.evaluate("() => document.body ? document.body.innerText.length : 0")
            self._trace.log_step_attempt(
                seq=seq, target=target, action=action_type, role=role,
                ui_pattern=self._unpack_step(gs)[7],
                found=bool(locate_result and locate_result.found),
                actual_text=(locate_result.element_info.get("text", "") if locate_result else ""),
                strategy=(locate_result.strategy if locate_result else ""),
                clicked=bool(result.success),
                url_changed=(self.state_manager.normalize_url(before.get("url")) !=
                             self.state_manager.normalize_url(after.get("url"))),
                jump_url=after.get("url", ""), page_text_len=page_len,
                current_url=before.get("url", ""),
            )
        except Exception:
            pass

    @staticmethod
    def _plan_dict(plan):
        return {
            "case_id": plan.case_id, "case_name": plan.case_name, "module": plan.module,
            "preconditions": plan.preconditions, "expected_result": plan.expected_result,
            "start_url": plan.start_url, "steps": [GuidedExplorationAgent._step_dict(x) for x in plan.steps]
        }

    @staticmethod
    def _step_dict(gs):
        if isinstance(gs, dict):
            return dict(gs)
        return {
            "seq": getattr(gs, "seq", 0), "action_type": getattr(gs, "action_type", ""),
            "target_text": getattr(gs, "target_text", ""), "role_hint": getattr(gs, "role_hint", ""),
            "fill_value": getattr(gs, "fill_value", ""), "select_option": getattr(gs, "select_option", ""),
            "context_hint": getattr(gs, "context_hint", ""), "ui_pattern": getattr(gs, "ui_pattern", ""),
        }

    @staticmethod
    def _unpack_step(gs):
        if isinstance(gs, dict):
            return (gs.get("seq", 0), gs.get("target_text", ""), gs.get("role_hint", ""),
                    gs.get("action_type", "click"), gs.get("fill_value", ""),
                    gs.get("select_option", ""), gs.get("context_hint", ""), gs.get("ui_pattern", ""))
        return (getattr(gs, "seq", 0), getattr(gs, "target_text", ""), getattr(gs, "role_hint", ""),
                getattr(gs, "action_type", "click"), getattr(gs, "fill_value", ""),
                getattr(gs, "select_option", ""), getattr(gs, "context_hint", ""), getattr(gs, "ui_pattern", ""))

    @staticmethod
    def _str_to_action_type(value: str) -> ActionType:
        mapping = {x.value: x for x in ActionType}
        return mapping.get(str(value).lower(), ActionType.CLICK)

    @staticmethod
    def _norm(text):
        return "".join(str(text or "").split()).lower()
