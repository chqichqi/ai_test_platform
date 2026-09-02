"""测试数据领域模型：不依赖数据库表，兼容现有 TestCase.test_data JSON 字段。"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import re


DATA_TYPES = {"static", "shared", "generated", "seeded", "consumable", "dependent", "persistent", "mutation"}
CLEANUP_POLICIES = {"none", "keep", "reset", "delete", "archive", "release", "expire", "recreate"}


@dataclass
class TestDataRequirement:
    key: str
    data_type: str = "generated"
    provider: str = "generator"
    generator: str = "auto"
    factory: str = ""
    value: Any = None
    required: bool = True
    unique: bool = True
    reuse_scope: str = "case_run"
    cleanup_policy: str = "none"
    state: str = ""
    depends_on: List[str] = field(default_factory=list)
    description: str = ""
    format: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    # API 数据契约字段：location/query|path|header|body，parameter_name 为真实请求字段名。
    location: str = ""
    parameter_name: str = ""
    mutation: str = ""
    target_type: str = ""
    source_value: Any = None
    observed: bool = False
    nullable: bool = False

    def __post_init__(self):
        self.data_type = (self.data_type or "generated").lower()
        if self.data_type not in DATA_TYPES:
            self.data_type = "generated"
        self.cleanup_policy = (self.cleanup_policy or "none").lower()
        if self.cleanup_policy not in CLEANUP_POLICIES:
            self.cleanup_policy = "none"
        self.depends_on = list(self.depends_on or [])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestDataSet:
    run_id: str
    case_id: str
    logical_case_id: str = ""
    revision_no: int = 1
    values: Dict[str, Any] = field(default_factory=dict)
    leases: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "prepared"

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestDataPlan:
    case_id: str
    logical_case_id: str = ""
    revision_no: int = 1
    version_id: Optional[int] = None
    project_id: Optional[int] = None
    requirements: List[TestDataRequirement] = field(default_factory=list)
    setup: List[Dict[str, Any]] = field(default_factory=list)
    cleanup: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, requirement: TestDataRequirement):
        existing = {r.key: r for r in self.requirements}
        existing[requirement.key] = requirement
        self.requirements = list(existing.values())
        return requirement

    def get(self, key: str) -> Optional[TestDataRequirement]:
        for item in self.requirements:
            if item.key == key:
                return item
        return None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["requirements"] = [r.to_dict() for r in self.requirements]
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]], defaults: Optional[Dict[str, Any]] = None):
        data = dict(data or {})
        defaults = defaults or {}
        reqs = []
        raw_reqs = data.get("requirements", [])
        if isinstance(raw_reqs, dict):
            raw_reqs = [dict(v, key=k) if isinstance(v, dict) else {"key": k, "value": v} for k, v in raw_reqs.items()]
        for raw in raw_reqs or []:
            if isinstance(raw, TestDataRequirement):
                reqs.append(raw)
            elif isinstance(raw, dict) and raw.get("key"):
                reqs.append(TestDataRequirement(**{k: v for k, v in raw.items() if k in TestDataRequirement.__dataclass_fields__}))
        return cls(
            case_id=str(data.get("case_id") or defaults.get("case_id") or ""),
            logical_case_id=str(data.get("logical_case_id") or defaults.get("logical_case_id") or data.get("case_id") or ""),
            revision_no=int(data.get("revision_no") or defaults.get("revision_no") or 1),
            version_id=data.get("version_id", defaults.get("version_id")),
            project_id=data.get("project_id", defaults.get("project_id")),
            requirements=reqs,
            setup=list(data.get("setup") or []),
            cleanup=list(data.get("cleanup") or []),
            metadata=dict(data.get("metadata") or {}),
        )


def build_api_test_data_plan(query_params=None, path_params=None, request_body=None, headers=None,
                             mutation_key: str = "", mutation: str = "", observed: bool = True,
                             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """从 API 请求模板构造统一数据计划。用于探索捕获与 Swagger/手工 API 用例。"""
    requirements = []
    query_params = query_params or {}
    path_params = path_params or {}
    headers = headers or {}
    request_body = request_body if isinstance(request_body, dict) else {}

    def add(location, name, value):
        key = f"{location}.{name}"
        is_mut = key == mutation_key
        requirements.append({
            "key": key, "location": location, "parameter_name": name,
            "data_type": "mutation" if is_mut else "static",
            "provider": "mutation" if is_mut else "static",
            "value": value, "source_value": value,
            "mutation": mutation if is_mut else "",
            "target_type": infer_api_parameter_type(name, value),
            "observed": observed, "unique": False, "cleanup_policy": "none"
        })

    for k, v in query_params.items(): add("query", str(k), v)
    for k, v in path_params.items(): add("path", str(k), v)
    for k, v in headers.items():
        if not str(k).lower() in ("authorization", "cookie"):
            add("header", str(k), v)

    def walk(node, prefix=""):
        if not isinstance(node, dict): return
        for k, v in node.items():
            name = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict): yield from walk(v, name)
            else: yield name, v
    for name, v in walk(request_body): add("body", name, v)

    return {"schema_version": 2, "kind": "api", "requirements": requirements,
            "metadata": metadata or {}}


def infer_api_parameter_type(name: str, value: Any) -> str:
    """HTTP 查询参数在 wire 上都是字符串，因此优先结合字段名推断业务类型。"""
    n = str(name or "").lower()
    if isinstance(value, bool): return "boolean"
    if any(x in n for x in ("page", "size", "limit", "offset", "count", "status", "type", "id", "index")):
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value or ""):
            return "integer"
    if isinstance(value, int): return "integer"
    if isinstance(value, float): return "number"
    if isinstance(value, list): return "array"
    if isinstance(value, dict): return "object"
    return "string"


def _infer_type_for_plan(value: Any) -> str:
    if isinstance(value, bool): return "boolean"
    if isinstance(value, int): return "integer"
    if isinstance(value, float): return "number"
    if isinstance(value, list): return "array"
    if isinstance(value, dict): return "object"
    return "string"
