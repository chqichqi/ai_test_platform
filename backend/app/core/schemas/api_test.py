"""
API接口测试相关Schema
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class ImportSwaggerRequest(BaseModel):
    project_id: int = Field(..., description="项目ID")
    source_type: str = Field(..., description="来源类型: url/file")
    source_url: Optional[str] = Field(None, description="Swagger文档URL")
    name: Optional[str] = Field(None, description="文档名称")


class ApiDefinitionResponse(BaseModel):
    id: int
    project_id: int
    name: Optional[str]
    source_type: Optional[str]
    source_url: Optional[str]
    version: Optional[str]
    base_url: Optional[str]
    description: Optional[str]
    imported_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ApiEndpointResponse(BaseModel):
    id: int
    definition_id: int
    path: str
    method: str
    tag: Optional[str]
    summary: Optional[str]
    description: Optional[str]
    parameters: Optional[List[dict]]
    request_body: Optional[dict]
    responses: Optional[dict]
    deprecated: bool

    class Config:
        from_attributes = True


class ApiEndpointListResponse(BaseModel):
    items: List[ApiEndpointResponse]
    total: int
    page: int
    page_size: int


class AssertRule(BaseModel):
    type: str = Field(..., description="断言类型: eq/neq/contains/regex/jsonpath")
    field: str = Field(..., description="字段路径")
    value: Any = Field(..., description="期望值")


class VariableExtraction(BaseModel):
    name: str = Field(..., description="变量名")
    source: str = Field(..., description="来源: body/header/cookie")
    json_path: Optional[str] = Field(None, description="JSONPath表达式")
    regex: Optional[str] = Field(None, description="正则表达式")


class ApiTestCaseCreate(BaseModel):
    project_id: int = Field(..., description="项目ID")
    endpoint_id: Optional[int] = Field(None, description="接口ID")
    version_id: Optional[int] = Field(None)
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    query_params: Optional[Dict[str, Any]] = None
    path_params: Optional[Dict[str, str]] = None
    request_body: Optional[Dict[str, Any]] = None
    expected_status: Optional[int] = None
    expected_headers: Optional[Dict[str, str]] = None
    expected_body: Optional[Dict[str, Any]] = None
    assert_rules: Optional[List[AssertRule]] = None
    case_type: str = Field(default="normal")
    priority: str = Field(default="P2")
    tags: Optional[List[str]] = None
    depends_on: Optional[List[int]] = None
    variable_extractions: Optional[List[VariableExtraction]] = None


class ApiTestCaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    query_params: Optional[Dict[str, Any]] = None
    path_params: Optional[Dict[str, str]] = None
    request_body: Optional[Dict[str, Any]] = None
    expected_status: Optional[int] = None
    expected_headers: Optional[Dict[str, str]] = None
    expected_body: Optional[Dict[str, Any]] = None
    assert_rules: Optional[List[AssertRule]] = None
    case_type: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None
    depends_on: Optional[List[int]] = None
    variable_extractions: Optional[List[VariableExtraction]] = None
    status: Optional[str] = None


class ApiTestCaseResponse(BaseModel):
    id: int
    project_id: int
    endpoint_id: Optional[int]
    version_id: Optional[int]
    name: str
    description: Optional[str]
    method: Optional[str]
    path: Optional[str]
    base_url: Optional[str]
    headers: Optional[Dict[str, str]]
    query_params: Optional[Dict[str, Any]]
    path_params: Optional[Dict[str, str]]
    request_body: Optional[Dict[str, Any]]
    expected_status: Optional[int]
    expected_headers: Optional[Dict[str, str]]
    expected_body: Optional[Dict[str, Any]]
    assert_rules: Optional[List[dict]]
    preconditions: Optional[str]
    test_steps: Optional[List[Dict[str, Any]]]
    expected_result: Optional[str]
    case_type: str
    priority: str
    status: str
    tags: Optional[List[str]]
    depends_on: Optional[List[int]]
    variable_extractions: Optional[List[dict]]
    generated_by: str
    created_by: Optional[str] = None
    reviewer_id: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApiTestCaseListResponse(BaseModel):
    items: List[ApiTestCaseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExecuteApiTestRequest(BaseModel):
    case_id: int = Field(..., description="用例ID")
    environment: Optional[str] = Field(None, description="环境名称")
    base_url: Optional[str] = Field(None, description="覆盖基础URL")


class ApiTestExecutionResponse(BaseModel):
    id: int
    case_id: int
    project_id: int
    environment: Optional[str]
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration: Optional[int]
    actual_status: Optional[int]
    actual_headers: Optional[Dict[str, str]]
    actual_body: Optional[Dict[str, Any]]
    error_message: Optional[str]
    assert_results: Optional[List[dict]]
    created_at: datetime

    class Config:
        from_attributes = True


class GenerateApiTestCasesRequest(BaseModel):
    endpoint_id: int = Field(..., description="接口ID")
    include_normal: bool = Field(default=True, description="生成正常场景")
    include_error: bool = Field(default=True, description="生成异常场景")
    include_boundary: bool = Field(default=True, description="生成边界值")
    include_auth: bool = Field(default=False, description="生成权限场景")


class GenerateApiTestCasesResponse(BaseModel):
    generated_count: int
    test_cases: List[ApiTestCaseResponse]


class ApiEnvironmentCreate(BaseModel):
    project_id: int = Field(..., description="项目ID")
    name: str = Field(..., max_length=100)
    base_url: Optional[str] = None
    variables: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None
    auth_config: Optional[Dict[str, Any]] = None
    is_default: bool = Field(default=False)


class ApiEnvironmentResponse(BaseModel):
    id: int
    project_id: int
    name: str
    base_url: Optional[str]
    variables: Optional[Dict[str, str]]
    headers: Optional[Dict[str, str]]
    auth_config: Optional[Dict[str, Any]]
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 鉴权配置 Schemas =====

class TokenExtractionSchema(BaseModel):
    """Token提取配置"""
    source: str = Field(default="body", description="提取来源: body/header/cookie")
    json_path: Optional[str] = Field(default="data.token", description="JSON路径")
    header_name: Optional[str] = Field(default=None, description="响应头名称")
    cookie_name: Optional[str] = Field(default=None, description="Cookie名称")


class TokenInjectionSchema(BaseModel):
    """Token注入配置"""
    location: str = Field(default="header", description="注入位置: header/query/cookie")
    header_name: str = Field(default="Authorization", description="请求头名称")
    prefix: str = Field(default="Bearer ", description="Token前缀")


class AuthConfigSchema(BaseModel):
    """环境鉴权配置"""
    enabled: bool = Field(default=False, description="是否启用鉴权")
    auth_type: str = Field(default="bearer_token", description="鉴权类型: bearer_token/basic_auth/api_key/oauth2/cookie")
    # 登录方式鉴权
    login_url: Optional[str] = Field(default=None, description="登录接口URL")
    login_method: str = Field(default="POST", description="登录请求方法")
    login_headers: Optional[Dict[str, str]] = Field(default=None, description="登录请求头")
    login_body: Optional[Dict[str, Any]] = Field(default=None, description="登录请求体")
    content_type: str = Field(default="application/json", description="登录请求Content-Type")
    # 凭证
    credentials: Optional[Dict[str, str]] = Field(default=None, description="凭证(username/password/client_id/client_secret)")
    # Token处理
    token_extraction: Optional[TokenExtractionSchema] = Field(default=None, description="Token提取配置")
    token_injection: Optional[TokenInjectionSchema] = Field(default=None, description="Token注入配置")
    # OAuth2
    token_url: Optional[str] = Field(default=None, description="OAuth2 Token URL")
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[str] = Field(default=None)
    grant_type: Optional[str] = Field(default="password", description="OAuth2 grant类型")
    # 缓存
    token_cache_duration: int = Field(default=3600, description="Token缓存时间(秒)")


class TestAuthRequest(BaseModel):
    """测试鉴权配置请求"""
    environment_id: int = Field(..., description="环境ID")
    base_url: Optional[str] = Field(default=None, description="基础URL")


class TestAuthResponse(BaseModel):
    """测试鉴权配置响应"""
    success: bool
    message: str
    token_preview: Optional[str] = Field(default=None, description="Token预览(脱敏)")
    token_type: Optional[str] = Field(default=None)


# ===== 文件Hash Schemas =====

class FileHashResponse(BaseModel):
    """文件Hash响应"""
    file_name: str
    file_size: int
    md5: Optional[str] = None
    sha1: Optional[str] = None
    sha256: Optional[str] = None
    mime_type: Optional[str] = None


class SwaggerAutoGenerateRequest(BaseModel):
    """Swagger自动生成测试用例请求"""
    project_id: int = Field(..., description="项目ID")
    version_id: Optional[int] = Field(None, description="版本ID")
    swagger_url: str = Field(..., description="Swagger文档URL")
    base_url: Optional[str] = Field(None, description="API基础URL（可覆盖Swagger中的）")
    include_normal: bool = Field(default=True, description="生成正常场景")
    include_error: bool = Field(default=True, description="生成异常场景")
    include_boundary: bool = Field(default=True, description="生成边界值场景")
    include_auth: bool = Field(default=True, description="生成权限/认证场景")
    max_cases_per_endpoint: int = Field(default=5, ge=1, le=10, description="每个接口最多生成用例数")


class GeneratedApiTestCase(BaseModel):
    """生成的API测试用例详情"""
    id: int
    name: str
    endpoint_path: str
    method: str
    case_type: str
    priority: str
    description: Optional[str]
    preconditions: Optional[str]
    test_steps: Optional[List[Dict[str, Any]]]
    expected_result: Optional[str]
    headers: Optional[Dict[str, str]]
    query_params: Optional[Dict[str, Any]]
    request_body: Optional[Dict[str, Any]]
    expected_status: Optional[int]
    assert_rules: Optional[List[Dict[str, Any]]]


class SwaggerAutoGenerateResponse(BaseModel):
    """Swagger自动生成测试用例响应"""
    success: bool
    message: str
    definition_id: Optional[int]
    endpoints_count: int
    generated_count: int
    test_cases: List[GeneratedApiTestCase]
    generation_summary: Optional[Dict[str, Any]]
    raw_spec: Optional[Dict[str, Any]] = None


class ApiTestVersionCreate(BaseModel):
    """创建API测试版本"""
    project_id: int = Field(..., description="项目ID")
    version_id: Optional[int] = Field(None, description="关联的项目版本ID")
    name: str = Field(..., max_length=100, description="版本名称")
    version_number: Optional[str] = Field(None, max_length=50, description="版本号")
    description: Optional[str] = Field(None, description="版本描述")
    is_api_test_only: bool = Field(default=True, description="是否为API测试专用版本")


class ApiTestVersionResponse(BaseModel):
    """API测试版本响应"""
    id: int
    project_id: int
    version_id: Optional[int]
    name: str
    version_number: Optional[str]
    description: Optional[str]
    is_api_test_only: bool
    query_version_id: int = Field(..., description="用于查询用例的版本ID（项目同步版本用version_id，API专用版本用ApiTestVersion.id）")
    test_cases_count: int = Field(default=0, description="测试用例数量")
    created_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ApiTestVersionListResponse(BaseModel):
    """API测试版本列表响应"""
    items: List[ApiTestVersionResponse]
    total: int


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    case_ids: List[int] = Field(..., description="要删除的用例ID列表")


class BatchExecuteRequest(BaseModel):
    """批量执行请求"""
    case_ids: List[int] = Field(..., description="要执行的用例ID列表")
    base_url: Optional[str] = Field(None, description="覆盖基础URL")
    environment: Optional[str] = Field(None, description="测试环境")


class BatchExecuteResponse(BaseModel):
    """批量执行响应"""
    total: int = Field(..., description="总用例数")
    passed: int = Field(..., description="通过数")
    failed: int = Field(..., description="失败数")
    error: int = Field(..., description="错误数")
    results: List[Dict[str, Any]] = Field(default=[], description="执行结果详情")


# ---- 审批相关 Schema ----

class SubmitReviewRequest(BaseModel):
    """提交审批请求"""
    comment: Optional[str] = Field(None, description="提交说明")


class ReviewActionRequest(BaseModel):
    """审批操作请求"""
    action: str = Field(..., pattern="^(approve|reject)$", description="审批动作: approve/reject")
    comment: Optional[str] = Field(None, description="审批意见")


class ReviewStatisticsResponse(BaseModel):
    """审批统计响应"""
    project_id: int
    total: int = Field(default=0)
    draft: int = Field(default=0)
    pending_review: int = Field(default=0)
    approved: int = Field(default=0)
    rejected: int = Field(default=0)


# ---- 导出相关 Schema ----

class ExportQueryParams(BaseModel):
    """导出查询参数"""
    version_id: Optional[int] = Field(None, description="版本ID")
    project_id: Optional[int] = Field(None, description="项目ID")
    case_type: Optional[str] = Field(None, description="用例类型")
    priority: Optional[str] = Field(None, description="优先级")
    search: Optional[str] = Field(None, description="搜索关键词")
    format: str = Field(default="csv", pattern="^(csv|xlsx)$", description="导出格式")


# ---- 报告相关 Schema ----

class ReportRequest(BaseModel):
    """生成测试报告请求"""
    project_id: int = Field(..., description="项目ID")
    version_id: Optional[int] = Field(None, description="版本ID")
    execution_ids: Optional[List[int]] = Field(None, description="指定执行记录ID列表")


class DurationStats(BaseModel):
    """耗时统计"""
    avg_ms: float = Field(default=0)
    max_ms: int = Field(default=0)
    min_ms: int = Field(default=0)
    total_ms: int = Field(default=0)


class CaseTypeStats(BaseModel):
    """用例类型统计"""
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    total: int = Field(default=0)


class AssertionSummary(BaseModel):
    """断言统计"""
    total_asserts: int = Field(default=0)
    passed_asserts: int = Field(default=0)
    failed_asserts: int = Field(default=0)


class ReportResponse(BaseModel):
    """测试报告响应"""
    project_id: int
    version_id: Optional[int] = None
    report_time: datetime = Field(default_factory=datetime.utcnow)
    total: int = Field(default=0)
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    error: int = Field(default=0)
    pass_rate: float = Field(default=0.0)
    duration_stats: Dict[str, Any] = Field(default_factory=dict)
    case_type_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    results: List[Dict[str, Any]] = Field(default_factory=list)
    assertion_summary: Dict[str, int] = Field(default_factory=dict)
    slowest_cases: List[Dict[str, Any]] = Field(default_factory=list)
    most_failed_assertions: List[Dict[str, Any]] = Field(default_factory=list)