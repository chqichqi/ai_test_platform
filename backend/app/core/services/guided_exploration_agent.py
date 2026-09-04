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
from app.core.services.test_data_manager import TestDataManager


class GuidedExplorationAgent(MCPExplorationAgent):
    """按测试用例独立探索，保留原 Agent 的 Phase 1/3/4 能力。"""

    def __init__(self, client, config, llm_service=None, module_name="", platform_type="web", db=None):
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
        # 引导探索的“已允许导航根”集合：初始含起点页根，后续用例步骤发生真实站内导航
        # 时并入新页根（如从工作台点「患者档案」菜单抵达 patientarchieve）。模块边界由此
        # 动态扩张——只放行用例真实导航到达的站内页，非同站/危险跳转仍被边界拦截。
        self._allowed_roots: set = set()
        self.test_data_manager = TestDataManager(db)
        self._runtime_datasets = {}
        # 跨 Case 的“真实导航转移”缓存：只复用已验证的导航结果，不复用表单/弹窗动作。
        self._transition_cache = {}

    def set_case_contexts(self, test_cases):
        """注入 TestCase 元数据，供补充探索在没有 CaseStepBatch 时恢复 CasePlan。"""
        self._case_contexts = {}
        self.test_data_manager = TestDataManager(self.test_data_manager.db)
        self._runtime_datasets = {}
        self._transition_cache = {}
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
        # 基准站点（origin）：引导探索只在本站内导航；跨站/登出跳转仍被边界拦截。
        self._base_origin = self._extract_origin(start_url)
        if start_url:
            self._allowed_roots.add(self._url_root_key(start_url) or "")
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
            # Guided 探索已经严格按 TestCase/CasePlan 执行动作。Phase 3 只能做静态扫描，
            # 绝不能再点击下拉、分页、弹窗触发器，否则会把同一对象第二次真实操作，
            # 甚至把动态空数据组件带到 about:blank。即使项目配置误设为 true，
            # Guided 模式也必须保持非交互。
            deep_dive = self._phase3_deep_dive(interactive=False) or {}
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
            "errors": len(self._error_events) + sum(1 for e in self._evidence if e.get("status") == "failed"),
            "guided_steps_total": sum(len(p.steps) for p in self._case_plans),
            "guided_steps_executed": len(successful),
            "guided_steps_successful": len(successful),
            "guided_steps_failed": sum(1 for e in self._evidence if e.get("status") == "failed"),
            "cases_total": len(self._case_plans),
            "cases_explored": len([c for c in self._case_results if c.get("status") != "not_started"]),
            "exploration_mode": "case_state_guided",
            "platform_type": self.platform_type,
            "interrupted": "cancelled" if self._cancelled else None,
        }

        # Guided → UI Case 的主链路不依赖 Phase-4 LLM 文档综合。
        # 旧逻辑这里连续调用 3 次 LLM（文档/站点图/POM），会让一次 3 用例转化额外耗时数分钟。
        # 默认关闭；确需生成文档时可在 exploration_config.explore.guided_phase4_synthesis=true 开启。
        phase4 = {}
        if self.llm and getattr(self.config, "guided_phase4_synthesis", False):
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
        # 轻量等待：先给 click/fill 一个极短的事件循环窗口；真正的页面就绪由状态变化决定。
        post_wait = float(getattr(self.config, "action_post_wait",
                                  getattr(self.config, "click_wait", 0.25)) or 0)
        if post_wait > 0 and action_type not in ("validate", "wait_for"):
            self.client.wait(post_wait)
        self._close_extra_pages()
        # about:blank 是探索中的非法中间状态：一旦出现，立即恢复到动作前页面，
        # 不允许它继续进入 Evidence/KG，也不让下一条 Case 从空白页开始。
        blank_recovered = self._recover_about_blank(before_url)
        current_after_url = self.client.get_url()
        if current_after_url == "about:blank":
            try:
                self.state_manager.restore(before_url, hard_reset=False,
                                           max_wait=getattr(self.config, "case_reset_ready_timeout", 3.0))
            except Exception:
                pass
            current_after_url = self.client.get_url()
            result = ActionResult(action=action, success=False,
                                  error="about_blank_after_action")
        elif blank_recovered:
            # 已经从 about:blank 恢复；这次动作不能被当成成功导航。
            result = ActionResult(action=action, success=False,
                                  error="about_blank_recovered")
        # 模块边界是安全约束：跨模块导航不进入探索图，也不作为成功证据。
        # 边界=白名单(见 _is_within_module)：起点根 ∪ 本模块入口导航真实抵达的页根。
        # 首步(step_index==0)发生真实站内导航 → 视为用例入口导航，目标页并入白名单(模块主根)；
        # 后续步骤跳出白名单(如误点到角色管理 /role) → 拦截并拉回。
        if current_after_url and hasattr(self, "_is_within_module"):
            if not self._is_within_module(current_after_url):
                # 尝试把“入口导航目标”并入白名单：仅当这是本用例第 1 步且产生了真实站内导航。
                if self._try_admit_entry_navigation(before_url, current_after_url, step_index):
                    logger.info(f"[GuidedAgent] 入口导航并入白名单: {current_after_url}")
                else:
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
        if final_ok:
            self._mark_consumable_step(plan, gs)
        return ev

    def _mark_consumable_step(self, plan: CasePlan, gs):
        dataset = self._runtime_datasets.get(str(plan.case_id))
        if dataset is None:
            return
        seq, target, role, action_type, fill_value, select_option, context, ui_pattern = self._unpack_step(gs)
        candidates = {str(target or ""), str(fill_value or ""), str(select_option or "")}
        try:
            data_plan = self._plan_data_object(plan)
            for req in data_plan.requirements:
                if req.data_type != "consumable":
                    continue
                if str(dataset.get(req.key, "")) in candidates:
                    self.test_data_manager.mark_consumed(dataset, req.key, {"step": seq, "action": action_type})
        except Exception as exc:
            logger.warning(f"[GuidedAgent] mark consumable failed case={plan.case_id}: {exc}")

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
            "data_set_id": getattr(plan, "data_set_id", ""),
            "runtime_data": getattr(plan, "runtime_data", {}),
            "status": "started",
        })

    def finish_case(self, plan: CasePlan, status: str, error: str = ""):
        dataset = self._runtime_datasets.get(str(plan.case_id))
        cleanup = []
        if dataset is not None:
            try:
                cleanup = self.test_data_manager.complete(dataset, self._plan_data_object(plan))
            except Exception as exc:
                cleanup = [{"status": "failed", "error": str(exc)}]
        for item in reversed(self._case_results):
            if item.get("case_id") == plan.case_id:
                item.update({
                    "status": status, "error": error or "", "finished_at": time.time(),
                    "data_set_id": getattr(plan, "data_set_id", ""),
                    "runtime_data": getattr(plan, "runtime_data", {}),
                    "data_cleanup": cleanup,
                })
                return
        self._case_results.append({
            "case_id": plan.case_id, "case_name": plan.case_name, "module": plan.module,
            "start_url": plan.start_url, "status": status, "error": error or "",
            "data_set_id": getattr(plan, "data_set_id", ""),
            "runtime_data": getattr(plan, "runtime_data", {}),
            "data_cleanup": cleanup, "finished_at": time.time(),
        })

    def _plan_data_object(self, plan):
        from app.core.services.test_data_plan import TestDataPlan
        return TestDataPlan.from_dict(getattr(plan, "test_data_plan", {}) or {}, {
            "case_id": plan.case_id, "logical_case_id": plan.logical_case_id,
            "revision_no": plan.revision_no, "version_id": plan.version_id, "project_id": plan.project_id,
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
    def make_replayed_evidence(self, plan, gs, before_state, after_state, cache) -> Dict[str, Any]:
        """为跨 Case 复用的已验证导航生成证据。

        replay 不再次点击浏览器，而是恢复到此前已经验证过的目标 URL。
        只有“发生导航”的 click/navigate/table_row 才允许走这里，因此不会把
        modal、toggle、表单等具有局部状态的动作错误地缓存。
        """
        seq, target, role, action_type, fill_value, select_option, context, ui_pattern = self._unpack_step(gs)
        loc = cache.get("locator") or {}
        effect = {
            "valid": True,
            "effect": "navigation",
            "replayed": True,
            "confidence": min(0.98, max(0.80, float(cache.get("confidence", 0.90) or 0.90))),
            "diff": self.state_manager.diff(before_state or {}, after_state or {}),
        }
        evidence = {
            "case_id": plan.case_id, "case_name": plan.case_name, "module": plan.module,
            "preconditions": plan.preconditions, "expected_result": plan.expected_result,
            "seq": seq, "target": target, "action": action_type, "role": role,
            "context": context, "ui_pattern": ui_pattern, "status": "success",
            "error": "", "before_url": (before_state or {}).get("url", ""),
            "after_url": (after_state or {}).get("url", ""),
            "before_state_id": (before_state or {}).get("state_id", ""),
            "after_state_id": (after_state or {}).get("state_id", ""),
            "locator": dict(loc), "effect": effect,
            "confidence": effect["confidence"],
            "execution_mode": "cached_transition_replay",
            "pages_touched": list(dict.fromkeys([(before_state or {}).get("url", ""), (after_state or {}).get("url", "")])),
        }
        self._evidence.append(evidence)
        return evidence

    def make_skipped_evidence(self, plan, gs, reason: str) -> Dict[str, Any]:
        seq, target, role, action_type, fill_value, select_option, context, ui_pattern = self._unpack_step(gs)
        state = self.state_manager.current_state or self.state_manager.capture_and_record(f"skipped_case_{plan.case_id}_step_{seq}")
        return self._make_evidence(plan, gs, seq, target, action_type, state, state, None, False, reason,
                                   effect={"valid": False, "effect": "skipped", "confidence": 1.0, "reason": reason})

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
            "status": ("success" if success else ("skipped" if str(error or "").startswith(("skipped_", "duplicate_action_skipped")) else "failed")),
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
            tc = self._case_contexts.get(str(p.case_id))
            try:
                data_plan = self.test_data_manager.build_plan(tc) if tc is not None else None
                if data_plan is not None:
                    p.test_data_plan = data_plan.to_dict()
                    dataset = self.test_data_manager.materialize(data_plan)
                    self.test_data_manager.apply_to_case_plan(p, dataset)
                    self._runtime_datasets[p.case_id] = dataset
                    logger.info(f"[GuidedAgent] TestData prepared case={p.case_id} run={dataset.run_id} keys={list(dataset.values.keys())}")
            except Exception as exc:
                # 数据需求无法满足时，不静默改成随机值；让该 Case 产生明确 evidence。
                logger.error(f"[GuidedAgent] TestData prepare failed case={p.case_id}: {exc}")
                p.test_data_plan = p.test_data_plan or {"error": str(exc)}
                p.runtime_data = {}
        self._case_plans = plans

    def _plan_data_object(self, plan):
        from app.core.services.test_data_plan import TestDataPlan
        return TestDataPlan.from_dict(getattr(plan, "test_data_plan", {}) or {}, {
            "case_id": plan.case_id, "logical_case_id": plan.logical_case_id,
            "revision_no": plan.revision_no, "version_id": plan.version_id, "project_id": plan.project_id,
        })

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
        self._allowed_roots = set()
        self._base_origin = ""

    def _go_back_to_case_start(self, plan: CasePlan, before_url: str) -> bool:
        try:
            self.client.back(wait=0.15)
            if hasattr(self.client, "wait_for_page_ready_fast"):
                self.client.wait_for_page_ready_fast(max_wait=getattr(self.config, "case_reset_ready_timeout", 3.0))
            else:
                self.client.wait_for_page_ready(max_wait=getattr(self.config, "case_reset_ready_timeout", 3.0))
            cur = self.client.get_url()
            if self.state_manager.normalize_url(cur) == self.state_manager.normalize_url(plan.start_url):
                return True
        except Exception:
            pass
        return self.state_manager.restore(plan.start_url, hard_reset=True)

    def _recover_about_blank(self, before_url: str):
        """发现动作把主页面送到 about:blank 时立即恢复。

        不能只依赖 goto(before_url)：某些站点的点击会先创建/切换空白文档，
        此时浏览器历史记录里的上一页反而是最可靠的恢复路径；历史失败才使用
        StateManager 的目标 URL 复位。整个过程禁止把 about:blank 写入有效 Evidence。
        """
        try:
            cur = self.client.get_url()
            if self.state_manager.normalize_url(cur) != "about:blank":
                return False
            if not before_url or self.state_manager.normalize_url(before_url) == "about:blank":
                return False

            logger.warning(f"[GuidedAgent] about:blank detected; recovering -> {before_url[-100:]}")
            recovered = False
            try:
                self.page.go_back()
                if hasattr(self.client, "wait_for_page_ready_fast"):
                    self.client.wait_for_page_ready_fast(max_wait=getattr(self.config, "case_reset_ready_timeout", 3.0))
                recovered = self.state_manager.normalize_url(self.client.get_url()) != "about:blank"
            except Exception:
                recovered = False

            if not recovered or self.state_manager.normalize_url(self.client.get_url()) != self.state_manager.normalize_url(before_url):
                recovered = self.state_manager.restore(
                    before_url, hard_reset=False,
                    max_wait=getattr(self.config, "case_reset_ready_timeout", 3.0)
                )
            return bool(recovered and self.state_manager.normalize_url(self.client.get_url()) != "about:blank")
        except Exception as exc:
            logger.warning(f"[GuidedAgent] about:blank recovery failed: {exc}")
            return False

    def _wait_for_target_text(self, target: str, max_wait=None) -> bool:
        if not target:
            return True
        max_wait = max_wait if max_wait is not None else min(
            float(getattr(self.config, "target_wait_timeout", 0.6) or 0.6), 0.8
        )
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
            self.client.wait(0.15)
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
            # 某些业务卡片/链接通过 window.open('', ...) 或 target=_blank 先创建
            # about:blank popup。探索不需要新窗口：空白 popup 立即关闭，主页面继续保持。
            try:
                self.page.on("popup", lambda popup: self._handle_popup(popup))
            except Exception:
                pass
            self._observer_injected = True
        except Exception:
            pass

    def _handle_popup(self, popup):
        try:
            url = self.state_manager.normalize_url(popup.url or "")
            if url in ("", "about:blank"):
                popup.close()
                logger.info("[GuidedAgent] closed blank popup created by exploratory action")
        except Exception as exc:
            logger.debug(f"[GuidedAgent] popup handler ignored: {exc}")

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

    @staticmethod
    def _extract_origin(url: str) -> str:
        """提取站点 origin（scheme://netloc），无则空串。用于引导探索的同源边界判定。"""
        if not url:
            return ""
        from urllib.parse import urlparse
        try:
            p = urlparse(url)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"
        except Exception:
            pass
        return ""

    def _url_root_key(self, url: str) -> str:
        """提取 hash 路由的首页面根（如 #/patientarchieve 的根 patientarchieve），
        无 hash 则取 pathname 首段。用于 allowed 边界集记录。"""
        if not url:
            return ""
        norm = self._norm_url_key(url)  # 纯 hash 路径或纯 path
        if norm.startswith("/"):
            parts = norm.strip("/").split("/")
            return parts[0] if parts else norm
        return norm

    def _is_within_module(self, url):
        """引导探索的模块边界（白名单版，2026-09-03 修复"探索乱跑/进不到目标页"两难）。

        早期父类把边界锁死为起点页(workpanel) → 用例入口导航进 patientarchieve 被误拦；
        一度放开为"同源全放行" → 又让误点(角色管理 /role)也乱跑。最终取"白名单"：
        _allowed_roots 初始含起点根，仅当用例首步入口导航真实抵达某站内页时并入该页根，
        此后只允许在 起点根 ∪ 已并入页根 内导航；其它站内页(误点 /role)与跨站都拦截。
        """
        if not url or url == "about:blank":
            return False
        root = self._url_root_key(url)
        # 无 hash 的路径取不到根的(如纯站首页) —— 退回父类保守判定
        if not root:
            return super()._is_within_module(url)
        return root in getattr(self, "_allowed_roots", set())

    def _try_admit_entry_navigation(self, before_url: str, after_url: str, step_index: int) -> bool:
        """把"用例真实导航到达的同源站内页"并入白名单。

        判据（通用、非硬编码，2026-09-03 放宽原"仅 step0"限制）：
        模块入口导航不总是首步——很多用例先在中转/列表页操作，中后步才经业务跳转
        （卡片/菜单）进入本模块主操作页。若仅放行 step0，会把这些合法跨模块业务跳转
        误判越界、反复拉回起点（工作台/卡片点进去→被拦→重来），正是用户看到的
        "反复卡在工作台 / 探索进不到模块真实页"的另一半根因。

        因此凡满足以下条件的真实站内导航都并入 _allowed_roots（白名单持续扩张）：
        1. after 是真实站内页（非 about:blank / 非同源登出跳转）；
        2. after 与 before 不同根（确实换了页面）。
        误点其它模块(如 /role)的兜底由两条上游防线承担：①生成规则#10 禁止步骤对象
        写它模块名词；②探索校正 _correct_case_steps 不再把跨模块/容器命中固化成步骤。
        """
        try:
            if not after_url or after_url == "about:blank":
                return False
            after_origin = self._extract_origin(after_url)
            base = getattr(self, "_base_origin", "") or ""
            if base and after_origin and after_origin != base:
                return False  # 跨站/登出，绝不并入
            after_root = self._url_root_key(after_url)
            before_root = self._url_root_key(before_url or "")
            if not after_root or after_root == before_root:
                return False  # 无根或未真正换页
            self._allowed_roots.add(after_root)
            return True
        except Exception:
            return False

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
            "case_id": plan.case_id, "test_case_id": plan.test_case_id,
            "logical_case_id": plan.logical_case_id, "revision_no": plan.revision_no,
            "version_id": plan.version_id, "project_id": plan.project_id,
            "case_name": plan.case_name, "module": plan.module,
            "preconditions": plan.preconditions, "expected_result": plan.expected_result,
            "start_url": plan.start_url,
            "test_data_plan": getattr(plan, "test_data_plan", {}),
            "runtime_data": getattr(plan, "runtime_data", {}),
            "data_set_id": getattr(plan, "data_set_id", ""),
            "steps": [GuidedExplorationAgent._step_dict(x) for x in plan.steps]
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
