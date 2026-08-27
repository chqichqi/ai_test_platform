"""Evidence -> KnowledgeGraph writer.

Evidence 是探索事实，KG 是项目级知识资产。写入原则：
1. 未定位、未执行、效果未验证的步骤不能进入可信 elements；
2. 失败 Evidence 仍保存到 step_diagnostics，便于影响分析/补充探索；
3. Case identity（test_case_id/logical_case_id/revision_no/version_id）跟随 flow/evidence；
4. 页面元素按真实 before/after URL 归属，避免把入口页元素挂到所有页面；
5. 可用时同步写入 ElementLocator / NavigationFlow 结构化表，JSON 列继续保留以兼容旧消费者。
"""
from datetime import datetime
from typing import Any, Dict, List

from app.core.logger import logger
from app.core.services.kg_populator import KGPopulator, STEP_DIAG_FLOW_PREFIX
from app.core.models.knowledge_graph import KnowledgeGraph, ExplorationPageSnapshot, ElementLocator, NavigationFlow


class EvidenceKGWriter(KGPopulator):
    def populate(self, *args, **kwargs):
        result = kwargs.get("exploration_result")
        if isinstance(result, dict):
            kwargs["exploration_result"] = self._normalize_evidence(result)
        try:
            kg = super().populate(*args, **kwargs)
            result = kwargs.get("exploration_result") or {}
            self._write_structured_evidence(kg, result)
            return kg
        except Exception:
            raise

    def _normalize_evidence(self, result: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(result)
        evidence = result.get("evidence", [])
        diagnostics, jumps = [], []
        for ev in evidence if isinstance(evidence, list) else []:
            if not isinstance(ev, dict):
                continue
            loc = ev.get("locator") or {}
            effect = ev.get("effect") or {}
            diagnostics.append({
                "seq": ev.get("seq", 0), "case_id": ev.get("case_id", ""),
                "test_case_id": ev.get("test_case_id", ev.get("case_id", "")),
                "logical_case_id": ev.get("logical_case_id", ""),
                "revision_no": ev.get("revision_no", 1), "version_id": ev.get("version_id"),
                "case_name": ev.get("case_name", ""), "target": ev.get("target", ""),
                "action": ev.get("action", ""), "status": ev.get("status", "failed"),
                "strategy": loc.get("strategy", ""), "actual_text": loc.get("actual_text", ""),
                "locator": loc, "effect": effect,
                "before_state_id": ev.get("before_state_id", ""),
                "after_state_id": ev.get("after_state_id", ""),
                "before_url": ev.get("before_url", ""), "after_url": ev.get("after_url", ""),
                "error": ev.get("error", ""), "confidence": ev.get("confidence", 0.0),
            })
            if ev.get("status") == "success" and effect.get("valid"):
                jumps.append({
                    "name": ev.get("target", ""), "actual_text": loc.get("actual_text", "") or ev.get("target", ""),
                    "clicked": True, "navigated": effect.get("effect") == "navigation",
                    "jump_url": ev.get("after_url", ""), "role": loc.get("role", ""),
                    "action_type": ev.get("action", ""), "selector": loc.get("selector", ""),
                    "primary_locator": loc.get("primary_locator", ""),
                    "locator_strategy": loc.get("strategy", ""), "case_id": ev.get("case_id", ""),
                    "logical_case_id": ev.get("logical_case_id", ""),
                    "revision_no": ev.get("revision_no", 1),
                    "state_before": ev.get("before_state_id", ""), "state_after": ev.get("after_state_id", ""),
                    "confidence": ev.get("confidence", 0.0),
                })
        out["step_diagnostics"] = diagnostics
        first_url = next((e.get("before_url") for e in evidence if isinstance(e, dict) and e.get("before_url")), "")
        out["element_jumps"] = {"_main": {"url": first_url, "elements": jumps}}
        out["elements"] = jumps
        out["evidence"] = evidence
        return out

    def _extract_flows(self, result: Dict, guided_steps=None, test_cases=None) -> List[Dict]:
        groups: Dict[str, Dict[str, Any]] = {}
        for ev in result.get("evidence", []) if isinstance(result.get("evidence"), list) else []:
            if not isinstance(ev, dict):
                continue
            cid = str(ev.get("case_id") or ev.get("test_case_id") or "legacy")
            if cid not in groups:
                groups[cid] = {
                    "flow_name": ev.get("case_name", "") or cid,
                    "flow_type": "guided", "module": ev.get("module", ""),
                    "start_page": ev.get("before_url", ""), "end_page": ev.get("after_url", ""),
                    "test_case_id": ev.get("test_case_id", cid),
                    "logical_case_id": ev.get("logical_case_id", ""),
                    "revision_no": ev.get("revision_no", 1), "version_id": ev.get("version_id"),
                    "steps": [],
                }
            g = groups[cid]
            g["end_page"] = ev.get("after_url", "") or g["end_page"]
            loc = ev.get("locator") or {}
            g["steps"].append({
                "seq": ev.get("seq", 0), "action": ev.get("action", ""), "target": ev.get("target", ""),
                "locator_role": loc.get("role", ""), "locator_text": loc.get("actual_text", "") or ev.get("target", ""),
                "status": ev.get("status", "failed"), "effect": ev.get("effect", {}),
                "locator": loc, "error": ev.get("error", ""),
                "state_before": ev.get("before_state_id", ""), "state_after": ev.get("after_state_id", ""),
            })
        return list(groups.values())

    def _extract_elements(self, result: Dict, guided_steps=None) -> List[Dict]:
        # 可信元素完全由 Evidence 驱动。
        elements, seen = [], set()
        for ev in result.get("evidence", []) if isinstance(result.get("evidence"), list) else []:
            if not isinstance(ev, dict) or ev.get("status") != "success":
                continue
            effect = ev.get("effect") or {}
            if not effect.get("valid"):
                continue
            loc = ev.get("locator") or {}
            name = (ev.get("target") or "").strip()
            if not name:
                continue
            role = (loc.get("role") or ev.get("role") or "button").strip()
            key = (name, role, ev.get("before_state_id", ""), loc.get("selector", ""))
            if key in seen:
                continue
            seen.add(key)
            elements.append({
                "element_name": name, "name": name, "type": role, "role": role,
                "text": loc.get("actual_text", "") or name,
                "locator_text": loc.get("actual_text", "") or name,
                "locator_role": role, "selector": loc.get("selector", ""),
                "primary_locator": loc.get("primary_locator", ""),
                "locator_strategy": loc.get("strategy", ""), "located": True,
                "validated": True, "source": "evidence", "case_id": ev.get("case_id", ""),
                "logical_case_id": ev.get("logical_case_id", ""), "revision_no": ev.get("revision_no", 1),
                "version_id": ev.get("version_id"), "state_id": ev.get("before_state_id", ""),
                "confidence": ev.get("confidence", 0.0), "navigated": effect.get("effect") == "navigation",
                "page_url": ev.get("before_url", ""),
            })
        return elements

    def _get_page_elements(self, url: str, result: Dict) -> List[Dict]:
        return [
            {
                "name": ev.get("target", ""),
                "role": (ev.get("locator") or {}).get("role", "") or ev.get("role", ""),
                "tag": (ev.get("locator") or {}).get("tag", ""),
                "text": (ev.get("locator") or {}).get("actual_text", "") or ev.get("target", ""),
                "selector": (ev.get("locator") or {}).get("selector", ""),
                "primary_locator": (ev.get("locator") or {}).get("primary_locator", ""),
                "locator_strategy": (ev.get("locator") or {}).get("strategy", ""),
                "located": True, "validated": True, "case_id": ev.get("case_id", ""),
                "logical_case_id": ev.get("logical_case_id", ""), "revision_no": ev.get("revision_no", 1),
                "state_id": ev.get("before_state_id", ""), "confidence": ev.get("confidence", 0.0),
            }
            for ev in (result.get("evidence", []) or [])
            if isinstance(ev, dict) and ev.get("status") == "success" and (ev.get("effect") or {}).get("valid")
            and url in (ev.get("before_url", ""), ev.get("after_url", "")) and ev.get("target")
        ]

    def _write_structured_evidence(self, kg: KnowledgeGraph, result: Dict[str, Any]):
        """同步写结构化 ElementLocator / NavigationFlow；失败不影响 JSON KG。"""
        try:
            snapshots = self.db.query(ExplorationPageSnapshot).filter(
                ExplorationPageSnapshot.graph_id == kg.id
            ).all()
            snap_by_url = {s.page_url: s.id for s in snapshots if s.page_url}

            for ev in result.get("evidence", []) or []:
                if not isinstance(ev, dict) or ev.get("status") != "success":
                    continue
                if not (ev.get("effect") or {}).get("valid"):
                    continue
                loc = ev.get("locator") or {}
                url = ev.get("before_url", "")
                page_id = snap_by_url.get(url)
                if not page_id:
                    continue
                selector = loc.get("selector", "") or loc.get("primary_locator", "")
                if not selector:
                    continue
                exists = self.db.query(ElementLocator).filter(
                    ElementLocator.graph_id == kg.id,
                    ElementLocator.page_id == page_id,
                    ElementLocator.element_name == ev.get("target", ""),
                    ElementLocator.primary_locator_value == selector,
                ).first()
                if exists:
                    exists.is_validated = True
                    exists.validation_success = True
                    exists.validation_attempts = (exists.validation_attempts or 0) + 1
                    exists.last_validated_at = datetime.utcnow()
                    continue
                self.db.add(ElementLocator(
                    graph_id=kg.id, page_id=page_id,
                    element_name=ev.get("target", ""),
                    element_type=loc.get("role", "") or ev.get("action", ""),
                    element_text=loc.get("actual_text", "") or ev.get("target", ""),
                    locator_css=selector if selector.startswith(".") or "[" in selector else "",
                    locator_text=loc.get("actual_text", "") or ev.get("target", ""),
                    primary_locator=loc.get("strategy", "text")[:20],
                    primary_locator_value=selector,
                    is_validated=True, validation_attempts=1, validation_success=True,
                    last_validated_at=datetime.utcnow(),
                ))

            # 每个 case 一条结构化 NavigationFlow，和 JSON flow 同源。
            for flow in self._extract_flows(result):
                if not flow.get("steps"):
                    continue
                cid = str(flow.get("test_case_id") or flow.get("flow_name"))
                exists = self.db.query(NavigationFlow).filter(
                    NavigationFlow.graph_id == kg.id,
                    NavigationFlow.flow_name == cid,
                ).first()
                if not exists:
                    self.db.add(NavigationFlow(
                        graph_id=kg.id,
                        flow_name=cid,
                        flow_type=flow.get("flow_type", "guided"),
                        start_page=flow.get("start_page", ""),
                        end_page=flow.get("end_page", ""),
                        steps=flow.get("steps", []),
                        dependencies=[], required_data={},
                    ))
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning(f"[EvidenceKGWriter] structured KG write skipped: {exc}")
