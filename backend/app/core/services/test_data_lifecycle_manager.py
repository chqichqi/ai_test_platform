"""测试数据生命周期管理：消费型数据默认 recreate，不做危险的数据库 DELETE。"""
from datetime import datetime
from typing import Any, Dict


class TestDataLifecycleManager:
    def __init__(self):
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.cleanup_handlers: Dict[str, Any] = {}

    def register_cleanup_handler(self, policy: str, handler):
        self.cleanup_handlers[policy] = handler

    def register_run(self, dataset):
        self.runs[dataset.run_id] = dataset.to_dict()

    def mark_consumed(self, dataset, key: str, metadata=None):
        for lease in dataset.leases:
            if lease.get("key") == key:
                lease["consumed"] = True
                lease["consumed_at"] = datetime.utcnow().isoformat()
                if metadata:
                    lease.update(metadata)
                break
        else:
            dataset.leases.append({"key": key, "consumed": True, "consumed_at": datetime.utcnow().isoformat(), **(metadata or {})})
        dataset.status = "consumed"
        self.runs[dataset.run_id] = dataset.to_dict()

    def complete(self, dataset, plan, manager):
        actions = []
        for req in plan.requirements:
            policy = req.cleanup_policy
            if req.data_type == "consumable" and policy == "none":
                policy = "recreate"
            if policy in ("none", "keep"):
                actions.append({"key": req.key, "policy": policy, "status": "kept"})
                continue
            handler = self.cleanup_handlers.get(policy)
            if handler:
                try:
                    handler(req, dataset.get(req.key), dataset, manager)
                    actions.append({"key": req.key, "policy": policy, "status": "handled"})
                except Exception as exc:
                    actions.append({"key": req.key, "policy": policy, "status": "failed", "error": str(exc)})
            else:
                # recreate/release/expire 没有业务 handler 时只记录策略，不碰 DB。
                actions.append({"key": req.key, "policy": policy, "status": "deferred", "reason": "no_cleanup_handler"})
        dataset.status = "completed"
        self.runs[dataset.run_id] = dataset.to_dict()
        return actions
