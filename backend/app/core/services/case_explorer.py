"""Case-level exploration orchestration.

Contract:
TestCase -> CasePlan -> StateManager -> ActionResolver -> ActionExecutor
         -> EffectValidator -> Evidence -> KG -> UI Case Generator

一个 TestCase 永远是一个独立探索事务。不同 TestCase 不共享“当前页面状态”。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.logger import logger


@dataclass
class CasePlan:
    case_id: str
    case_name: str
    module: str
    preconditions: str = ""
    expected_result: str = ""
    start_url: str = ""
    steps: List[Any] = field(default_factory=list)
    test_case_id: str = ""
    logical_case_id: str = ""
    revision_no: int = 1
    version_id: Optional[int] = None
    project_id: Optional[int] = None
    # Test Data 生命周期：计划与本次运行实例均属于当前 Case，不跨 Case 共享。
    test_data_plan: Dict[str, Any] = field(default_factory=dict)
    runtime_data: Dict[str, Any] = field(default_factory=dict)
    data_set_id: str = ""


class CaseStepBatch(list):
    """兼容旧的 List[GuidedStep] API，同时携带 CasePlan 列表。"""
    def __init__(self, iterable=(), case_plans=None):
        super().__init__(iterable)
        self.case_plans: List[CasePlan] = list(case_plans or [])


class CaseExplorer:
    def __init__(self, agent):
        self.agent = agent

    @staticmethod
    def from_module_steps(module_name: str, guided_steps: List[Any], test_cases: Optional[List[Any]] = None) -> List[CasePlan]:
        """从带 _case_id 的 GuidedStep 构建 CasePlan。"""
        if isinstance(guided_steps, CaseStepBatch) and guided_steps.case_plans:
            return list(guided_steps.case_plans)

        grouped: Dict[str, List[Any]] = {}
        for gs in guided_steps or []:
            cid = str(getattr(gs, '_case_id', '') or '')
            if cid:
                grouped.setdefault(cid, []).append(gs)

        plans: List[CasePlan] = []
        for idx, tc in enumerate(test_cases or []):
            module = getattr(tc, 'module', '') or '通用'
            if module != module_name:
                continue
            cid = str(getattr(tc, 'id', '') or getattr(tc, 'case_id', '') or idx)
            plans.append(CasePlan(
                case_id=cid,
                case_name=getattr(tc, 'name', None) or getattr(tc, 'title', None) or f'用例{idx + 1}',
                module=module_name,
                preconditions=getattr(tc, 'preconditions', '') or '',
                expected_result=getattr(tc, 'expected_result', '') or '',
                steps=grouped.get(cid, []),
                test_case_id=cid,
                logical_case_id=str(getattr(tc, 'logical_case_id', '') or cid),
                revision_no=int(getattr(tc, 'revision_no', 1) or 1),
                version_id=getattr(tc, 'version_id', None),
                project_id=getattr(tc, 'project_id', None),
            ))
        return plans

    def run(self, plans: List[CasePlan], start_url: str, progress_cb=None, cancel_check=None) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        all_pages: List[str] = []
        interrupted = ""
        total_steps = sum(len(p.steps) for p in plans)
        done_steps = 0

        for plan_index, plan in enumerate(plans):
            if cancel_check and cancel_check():
                interrupted = "cancelled"
                break

            plan.start_url = plan.start_url or start_url
            case_t0 = __import__('time').time()
            logger.info(f"[CaseExplorer] START case={plan.case_id} name={plan.case_name!r} steps={len(plan.steps)}")

            # 首个 Case / 上个 Case 改过表单或未回到起始页才硬复位。
            hard_reset = (plan_index == 0) or bool(getattr(self.agent, "_case_needs_hard_reset", True))
            if not self.agent.state_manager.reset_to(plan.start_url, hard_reset=hard_reset):
                ev = self.agent.make_case_error(plan, "case_start_restore_failed")
                evidence.append(ev)
                self.agent.finish_case(plan, "failed", ev.get("error", ""))
                continue

            self.agent.record_case_start(plan, self.agent.state_manager.current_state)
            case_failed = False
            # 一个 TestCase 是一个探索事务：同一 Case 内同一个语义动作只允许真实执行一次。
            # 这是“测试用例 -> 探索对象列表 -> foreach”原则的执行层保证。
            # 注意：这是探索去重，不影响最终 UI 用例执行语义；同一对象即使出现在不同
            # 页面/不同 Case，也允许分别探索。
            case_needs_hard_reset = False
            executed_actions = set()
            _segment_key = 0

            for step_index, gs in enumerate(plan.steps):
                if cancel_check and cancel_check():
                    interrupted = "cancelled"
                    break
                done_steps += 1
                if progress_cb:
                    try:
                        progress_cb({
                            "step_done": done_steps,
                            "step_total": max(total_steps, 1),
                            "case_done": plan_index,
                            "case_total": len(plans),
                            "case_id": plan.case_id,
                            "case_name": plan.case_name,
                        })
                    except Exception:
                        pass

                _seq, _target, _role, _action, _fill, _select, _ctx, _pattern = self.agent._unpack_step(gs)
                _atype = str(_action or "").lower()
                _norm_target = "".join(str(_target or "").split()).lower()
                # 探索去重 key 故意不包含页面段：探索目标列表的语义是“本 Case 中这个对象
                # 只需要真实操作一次”。否则 click -> go_back -> click 会再次触发同一个业务动作。
                # fill/select 保留 value，因此“同一控件选择不同选项”仍可分别探索。
                _action_value = str(_fill or _select or "").strip()
                _action_key = (_atype, _norm_target, str(_role or "").lower(), _action_value)
                _dedup_types = ("click", "navigate", "table_row", "fill", "select",
                                "hover", "tab_switch", "right_click", "key_press")
                if _atype in _dedup_types and _action_key in executed_actions:
                    ev = self.agent.make_skipped_evidence(plan, gs, "duplicate_exploration_target_skipped")
                    logger.info(
                        f"[CaseExplorer] SKIP duplicate exploration target "
                        f"case={plan.case_id} seq={_seq} target={_target!r} action={_atype}"
                    )
                else:
                    ev = self.agent.explore_one_step(plan, step_index, gs)
                    if _atype in _dedup_types:
                        executed_actions.add(_action_key)
                    if _atype in ("fill", "select") and ev.get("status") == "success":
                        case_needs_hard_reset = True
                if _atype in ("go_back", "navigate", "reload") and ev.get("status") in ("success", "skipped"):
                    _segment_key += 1
                if ev.get("status") == "success" and _atype in ("click", "table_row"):
                    if (ev.get("effect") or {}).get("effect") == "navigation":
                        _segment_key += 1
                evidence.append(ev)
                all_pages.extend(ev.get("pages_touched", []) or [])
                if ev.get("status") not in ("success", "skipped"):
                    case_failed = True

            self.agent._case_needs_hard_reset = case_needs_hard_reset or (
                self.agent.state_manager.normalize_url(self.agent.client.get_url()) !=
                self.agent.state_manager.normalize_url(plan.start_url)
            )

            if interrupted:
                self.agent.finish_case(plan, "cancelled", "exploration_cancelled")
                break

            self.agent.finish_case(plan, "failed" if case_failed else "success", "" if not case_failed else "one_or_more_steps_failed")
            logger.info(f"[CaseExplorer] END case={plan.case_id} status={'failed' if case_failed else 'success'} elapsed={__import__('time').time()-case_t0:.2f}s")

        return {
            "case_plans": plans,
            "evidence": evidence,
            "pages_visited": list(dict.fromkeys(x for x in all_pages if x)),
            "interrupted": interrupted,
        }
