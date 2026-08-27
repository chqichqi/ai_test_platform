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
            logger.info(f"[CaseExplorer] START case={plan.case_id} name={plan.case_name!r} steps={len(plan.steps)}")

            # 每个 Case 都强制恢复到干净起始页，而不是仅检查 URL。
            if not self.agent.state_manager.reset_to(plan.start_url, hard_reset=True):
                ev = self.agent.make_case_error(plan, "case_start_restore_failed")
                evidence.append(ev)
                self.agent.finish_case(plan, "failed", ev.get("error", ""))
                continue

            self.agent.record_case_start(plan, self.agent.state_manager.current_state)
            case_failed = False

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

                ev = self.agent.explore_one_step(plan, step_index, gs)
                evidence.append(ev)
                all_pages.extend(ev.get("pages_touched", []) or [])
                if ev.get("status") != "success":
                    case_failed = True

            if interrupted:
                self.agent.finish_case(plan, "cancelled", "exploration_cancelled")
                break

            self.agent.finish_case(plan, "failed" if case_failed else "success", "" if not case_failed else "one_or_more_steps_failed")

        return {
            "case_plans": plans,
            "evidence": evidence,
            "pages_visited": list(dict.fromkeys(x for x in all_pages if x)),
            "interrupted": interrupted,
        }
