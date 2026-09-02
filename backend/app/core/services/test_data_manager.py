"""Test Data Manager：TestCase -> DataPlan -> RuntimeData，并把运行数据注入 CasePlan。"""
import copy
import json
import re
import uuid
from typing import Any, Dict, Optional

from app.core.services.test_data_plan import TestDataPlan, TestDataRequirement, TestDataSet
from app.core.services.test_data_generator import TestDataGenerator
from app.core.services.test_data_provider import TestDataProviderRegistry
from app.core.services.test_data_factory import TestDataFactory
from app.core.services.test_data_lifecycle_manager import TestDataLifecycleManager

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}|\{\{([A-Za-z0-9_.-]+)\}\}")


class TestDataManager:
    """单次 Case Run 的数据边界管理器。"""
    def __init__(self, db=None):
        self.db = db
        self.generator = TestDataGenerator()
        self.providers = TestDataProviderRegistry()
        self.factory_registry = TestDataFactory()
        self.factories = self.factory_registry._factories
        self.lifecycle = TestDataLifecycleManager()
        self.shared_cache: Dict[str, Any] = {}

    def register_generator(self, name, func):
        self.generator.register(name, func)

    def register_factory(self, name, func):
        self.factory_registry.register(name, func)

    def register_provider(self, provider):
        self.providers.register(provider)

    def build_plan(self, test_case) -> TestDataPlan:
        raw = getattr(test_case, "test_data", None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {"legacy_value": raw}
        raw = raw if isinstance(raw, dict) else {}
        defaults = {
            "case_id": str(getattr(test_case, "id", "")),
            "logical_case_id": str(getattr(test_case, "logical_case_id", "") or getattr(test_case, "id", "")),
            "revision_no": int(getattr(test_case, "revision_no", 1) or 1),
            "version_id": getattr(test_case, "version_id", None),
            "project_id": getattr(test_case, "project_id", None),
        }
        plan_raw = raw.get("data_plan") if isinstance(raw.get("data_plan"), dict) else None
        if plan_raw:
            return TestDataPlan.from_dict(plan_raw, defaults)

        # 兼容旧 test_data：把普通键推断为数据需求；保留 title/module 等元字段不作为运行数据。
        plan = TestDataPlan(**defaults)
        reserved = {"title", "name", "module", "priority", "preconditions", "description", "expected_result", "data_plan", "metadata"}
        for key, value in raw.items():
            if key in reserved:
                continue
            if isinstance(value, dict) and any(k in value for k in ("type", "data_type", "provider", "generator", "value", "factory")):
                req = self._requirement_from_legacy(key, value)
            else:
                req = TestDataRequirement(key=key, data_type="static", provider="static", value=value, unique=False, cleanup_policy="none")
            plan.add(req)

        # 兼容早期功能用例：即使 test_data 没有 DataPlan，也从步骤发现“需要数据”的字段。
        # 这里只补“没有明确值”的输入，不覆盖用户已经给出的 test_data。
        for key, desc in self._infer_step_requirements(test_case):
            if plan.get(key) is None:
                plan.add(TestDataRequirement(key=key, data_type="generated", provider="generator", generator="auto", unique=True, description=desc))
        return plan

    def _infer_step_requirements(self, test_case):
        steps = getattr(test_case, "test_steps", None)
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except Exception:
                return []
        result = []
        if not isinstance(steps, list):
            return result
        for step in steps:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or step.get("desc") or step.get("description") or "")
            if not re.match(r"^(填写|输入|填入|录入|键入|设置|选择|下拉选择|选中)", action.strip()):
                continue
            target = str(step.get("target") or "").strip()
            if not target:
                m = re.search(r"[「\"](.+?)[」\"]", action)
                target = m.group(1).strip() if m else ""
            # 去掉角色后缀和常见动词，得到稳定 key。
            target = re.sub(r"(按钮|输入框|文本框|搜索框|下拉框|下拉列表|下拉菜单|选择框)$", "", target).strip()
            if not target:
                continue
            key = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", target).strip("_").lower()
            if key:
                result.append((key, target))
        return result

    def _requirement_from_legacy(self, key, value):
        d = dict(value)
        data_type = d.pop("type", d.pop("data_type", "generated"))
        provider = d.pop("provider", "generator")
        allowed = TestDataRequirement.__dataclass_fields__
        d = {k: v for k, v in d.items() if k in allowed}
        return TestDataRequirement(key=key, data_type=data_type, provider=provider, **d)

    def materialize(self, plan: TestDataPlan) -> TestDataSet:
        run_id = str(uuid.uuid4())
        dataset = TestDataSet(run_id=run_id, case_id=plan.case_id, logical_case_id=plan.logical_case_id, revision_no=plan.revision_no)
        context = {"run_id": run_id, "case_id": plan.case_id, "logical_case_id": plan.logical_case_id, "revision_no": plan.revision_no}
        pending = list(plan.requirements)
        resolved = set()
        # 简单拓扑排序：依赖已经解析的 requirement 优先。
        for _ in range(len(pending) + 1):
            progressed = False
            for req in list(pending):
                if any(dep not in resolved for dep in req.depends_on):
                    continue
                provider_name = req.provider or self._provider_for_type(req.data_type)
                provider = self.providers.get(provider_name)
                value, lease = provider.acquire(req, context, self)
                if req.unique and req.data_type in ("generated", "consumable"):
                    value = self._ensure_unique(req, value, dataset.values)
                    lease["resource"] = value
                dataset.values[req.key] = value
                lease.update({"key": req.key, "data_type": req.data_type, "cleanup_policy": req.cleanup_policy})
                dataset.leases.append(lease)
                resolved.add(req.key)
                pending.remove(req)
                progressed = True
            if not pending or not progressed:
                break
        for req in pending:
            if req.required:
                raise ValueError(f"测试数据依赖无法解析: {req.key}, depends_on={req.depends_on}")
        self.lifecycle.register_run(dataset)
        return dataset

    def materialize_api_case(self, test_case):
        """把 API TestCase 的 test_data(TestDataPlan)实例化成真正请求数据。

        API 与 UI 共用 TestDataManager：
        - normal 用例通常保留探索时 observed value；
        - error/boundary 用例通过 mutation requirement 在运行时生成错误值；
        - 不把一次运行的随机值写回用例。
        """
        raw = getattr(test_case, "test_data", None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        raw = raw if isinstance(raw, dict) else {}
        plan = TestDataPlan.from_dict(raw, {
            "case_id": str(getattr(test_case, "id", "")),
            "logical_case_id": str(getattr(test_case, "id", "")),
            "revision_no": 1,
            "project_id": getattr(test_case, "project_id", None),
            "version_id": getattr(test_case, "version_id", None),
        })
        dataset = self.materialize(plan)
        query, path, headers, body = {}, {}, {}, {}
        for req in plan.requirements:
            loc = (req.location or "").lower()
            name = req.parameter_name or req.key
            value = dataset.values.get(req.key)
            if loc == "query":
                if value is not None and not (req.mutation == "missing"):
                    query[name] = value
            elif loc == "path":
                if value is not None and req.mutation != "missing":
                    path[name] = value
            elif loc == "header":
                if value is not None and req.mutation != "missing":
                    headers[name] = value
            elif loc == "body":
                self._set_nested(body, name, value, remove=(req.mutation == "missing"))
        # 兼容老用例：没有 API plan 时沿用原请求值并渲染变量。
        if not plan.requirements:
            query = self._render_structure(getattr(test_case, "query_params", None) or {}, dataset.values)
            path = self._render_structure(getattr(test_case, "path_params", None) or {}, dataset.values)
            headers = self._render_structure(getattr(test_case, "headers", None) or {}, dataset.values)
            raw_body = getattr(test_case, "request_body", None)
            body = self._render_structure(raw_body, dataset.values) if isinstance(raw_body, (dict, list, str)) else {}
        else:
            # headers 中的鉴权占位符仍由 API 执行器统一处理。
            stored_headers = getattr(test_case, "headers", None) or {}
            headers = {**self._render_structure(stored_headers, dataset.values), **headers}
            raw_body = getattr(test_case, "request_body", None)
            if not body and isinstance(raw_body, dict):
                body = self._render_structure(raw_body, dataset.values)
            elif isinstance(raw_body, str):
                body = self.render(raw_body, dataset.values)
        return {"query_params": query, "path_params": path, "headers": headers, "request_body": body,
                "dataset": dataset, "plan": plan}

    @staticmethod
    def _set_nested(target, dotted, value, remove=False):
        parts = str(dotted).split(".") if dotted else []
        if not parts:
            return
        cur = target
        for part in parts[:-1]:
            if not isinstance(cur.get(part), dict):
                cur[part] = {}
            cur = cur[part]
        if remove:
            cur.pop(parts[-1], None)
        else:
            cur[parts[-1]] = value

    def _render_structure(self, obj, values):
        if isinstance(obj, dict):
            return {k: self._render_structure(v, values) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._render_structure(v, values) for v in obj]
        return self.render(obj, values) if isinstance(obj, str) else obj

    def mutate_value(self, requirement, source):
        """标准参数变异：确定性按 schema 类型生成，不依赖 LLM 临场发挥。"""
        mutation = (getattr(requirement, "mutation", "") or "type_mismatch").lower()
        target_type = (getattr(requirement, "target_type", "") or "").lower()
        if mutation == "missing":
            return None
        if mutation == "null":
            return None
        if mutation == "not_found":
            # “不存在资源”必须根据真实参数类型构造，而不是一律写死 999999999。
            # UUID/string ID 用唯一不存在值；integer 用远离业务常见范围的正整数。
            if target_type in ("integer", "number") or isinstance(source, (int, float)):
                return 999999999
            if target_type == "string" or isinstance(source, str):
                return f"__not_found_{uuid.uuid4().hex}__"
            if target_type == "array":
                return ["__not_found__"]
            if target_type == "object":
                return {"__not_found__": True}
            return f"__not_found_{uuid.uuid4().hex}__"
        if mutation == "type_mismatch":
            if target_type:
                return self._coerce_invalid_type(target_type)
            if isinstance(source, bool): return "not_bool"
            if isinstance(source, int): return "not_an_integer"
            if isinstance(source, float): return "not_number"
            if isinstance(source, str): return [source, "extra"]
            if isinstance(source, list): return {"unexpected": True}
            if isinstance(source, dict): return ["unexpected"]
            return "invalid"
        if mutation == "boundary":
            if isinstance(source, bool): return not source
            if isinstance(source, int):
                lo = getattr(requirement, "min_value", None)
                return (lo - 1) if lo is not None else -1
            if isinstance(source, float):
                return -0.000001
            if isinstance(source, str):
                max_len = getattr(requirement, "max_value", None) or 256
                return "X" * min(max_len + 1, 2000)
            if isinstance(source, list): return []
            return source
        if mutation == "special":
            return "<script>alert(1)</script>\' OR \'1\'=\'1"
        if mutation == "invalid_format":
            return "not-a-valid-format"
        return source

    @staticmethod
    def _coerce_invalid_type(target_type):
        # 返回“与原类型不同”的值。对 HTTP query 参数而言最终会被编码成字符串，
        # 因此 integer/number/bool 的错误值刻意使用无法被正常解析的字符串。
        return {
            "string": 123456,
            "integer": "not_integer",
            "number": "not_number",
            "boolean": "not_boolean",
            "array": "not_array",
            "object": ["not_object"],
        }.get(target_type, "__INVALID_TYPE__")

    @staticmethod
    def _provider_for_type(data_type):
        return {"static": "static", "shared": "shared", "generated": "generator", "consumable": "consumable", "seeded": "seeded", "dependent": "dependent", "mutation": "mutation"}.get(data_type, "generator")

    @staticmethod
    def _ensure_unique(req, value, current):
        if value not in current.values():
            return value
        if isinstance(value, str):
            return f"{value}_{uuid.uuid4().hex[:8]}"
        return uuid.uuid4().hex

    def apply_to_case_plan(self, plan, dataset: TestDataSet):
        plan.runtime_data = copy.deepcopy(dataset.values)
        plan.data_set_id = dataset.run_id
        if hasattr(plan, "preconditions"):
            plan.preconditions = self.render(plan.preconditions, dataset.values)
        if hasattr(plan, "expected_result"):
            plan.expected_result = self.render(plan.expected_result, dataset.values)
        plan.test_data_plan = getattr(plan, "test_data_plan", None) or {}
        plan.test_data_plan["runtime_data"] = copy.deepcopy(dataset.values)
        plan.test_data_plan["run_id"] = dataset.run_id
        for step in plan.steps:
            self._render_object(step, dataset.values)
        return plan

    def render(self, text: Any, values: Dict[str, Any]):
        if not isinstance(text, str):
            return text
        def repl(match):
            key = match.group(1) or match.group(2)
            if key in values:
                return str(values[key])
            # 支持 patient.id 形式
            cur = values
            for part in key.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return match.group(0)
                cur = cur[part]
            return str(cur)
        return _PLACEHOLDER.sub(repl, text)

    def _render_object(self, obj, values):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                obj[k] = self._render_object(v, values)
            return obj
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = self._render_object(v, values)
            return obj
        if isinstance(obj, str):
            return self.render(obj, values)
        if hasattr(obj, "__dict__"):
            for k, v in list(vars(obj).items()):
                if k.startswith("_"):
                    continue
                try:
                    setattr(obj, k, self._render_object(v, values))
                except Exception:
                    pass
        return obj

    def mark_consumed(self, dataset, key, metadata=None):
        self.lifecycle.mark_consumed(dataset, key, metadata)

    def complete(self, dataset, plan):
        return self.lifecycle.complete(dataset, plan, self)

    def to_plan_json(self, plan):
        return plan.to_json()
