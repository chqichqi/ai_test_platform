"""
API接口测试相关模型
对应需求文档 3.5 API接口测试
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Integer, Boolean
import enum

from app.core.database import Base


class ApiDefinition(Base):
    __tablename__ = "api_definitions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    name = Column(String(200), comment="API文档名称")
    source_type = Column(String(20), comment="来源类型: url/file")
    source_url = Column(String(500), comment="来源URL")
    content = Column(JSON, comment="API定义内容(OpenAPI JSON)")
    version = Column(String(50), comment="OpenAPI版本")
    base_url = Column(String(500), comment="基础URL")
    description = Column(Text, comment="描述")
    imported_at = Column(DateTime, comment="导入时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<ApiDefinition(id={self.id}, name={self.name})>"


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    definition_id = Column(BigInteger, ForeignKey("api_definitions.id"), nullable=False, comment="API定义ID")
    path = Column(String(500), nullable=False, comment="接口路径")
    method = Column(String(10), nullable=False, comment="请求方法: GET/POST/PUT/DELETE/PATCH")
    tag = Column(String(100), comment="标签/模块")
    summary = Column(String(500), comment="接口描述")
    description = Column(Text, comment="详细描述")
    parameters = Column(JSON, comment="请求参数")
    request_body = Column(JSON, comment="请求体")
    responses = Column(JSON, comment="响应定义")
    security = Column(JSON, comment="安全配置")
    deprecated = Column(Boolean, default=False, comment="是否废弃")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def __repr__(self):
        return f"<ApiEndpoint(id={self.id}, {self.method} {self.path})>"


class ApiTestCase(Base):
    __tablename__ = "api_test_cases"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    endpoint_id = Column(BigInteger, ForeignKey("api_endpoints.id"), comment="接口ID")
    version_id = Column(BigInteger, ForeignKey("versions.id"), comment="版本ID")
    name = Column(String(200), nullable=False, comment="用例名称")
    description = Column(Text, comment="用例描述")
    
    method = Column(String(10), comment="请求方法")
    path = Column(String(500), comment="请求路径")
    base_url = Column(String(500), comment="基础URL")
    
    headers = Column(JSON, comment="请求头")
    query_params = Column(JSON, comment="查询参数")
    path_params = Column(JSON, comment="路径参数")
    request_body = Column(JSON, comment="请求体")
    
    expected_status = Column(Integer, comment="预期状态码")
    expected_headers = Column(JSON, comment="预期响应头")
    expected_body = Column(JSON, comment="预期响应体")
    assert_rules = Column(JSON, comment="断言规则")
    
    preconditions = Column(Text, comment="前置条件")
    test_steps = Column(JSON, comment="测试步骤")
    expected_result = Column(Text, comment="预期结果描述")
    
    case_type = Column(String(20), default="normal", comment="用例类型: normal/error/boundary/auth")
    priority = Column(String(10), default="P2", comment="优先级")
    status = Column(String(20), default="draft", comment="状态")
    tags = Column(JSON, comment="标签")
    
    depends_on = Column(JSON, comment="依赖的用例ID列表")
    variable_extractions = Column(JSON, comment="变量提取配置")
    
    generated_by = Column(String(20), default="manual", comment="生成方式: ai/manual")
    created_by = Column(String(36), comment="创建人ID")
    reviewer_id = Column(String(36), nullable=True, comment="审批人ID")
    review_comment = Column(Text, nullable=True, comment="审批意见")
    reviewed_at = Column(DateTime, nullable=True, comment="审批时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<ApiTestCase(id={self.id}, name={self.name}, status={self.status})>"


class ApiTestExecution(Base):
    __tablename__ = "api_test_executions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    case_id = Column(BigInteger, ForeignKey("api_test_cases.id"), nullable=False, comment="用例ID")
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    environment = Column(String(50), comment="测试环境")
    trigger_type = Column(String(20), default="manual", comment="触发类型")
    trigger_user_id = Column(String(36), comment="触发用户ID")
    
    status = Column(String(20), default="pending", comment="状态: pending/running/passed/failed/error")
    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    duration = Column(Integer, comment="执行时长(毫秒)")
    
    actual_status = Column(Integer, comment="实际状态码")
    actual_headers = Column(JSON, comment="实际响应头")
    actual_body = Column(JSON, comment="实际响应体")
    
    request_log = Column(Text, comment="请求日志")
    response_log = Column(Text, comment="响应日志")
    
    error_message = Column(Text, comment="错误信息")
    assert_results = Column(JSON, comment="断言结果")
    
    extracted_variables = Column(JSON, comment="提取的变量")
    
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def __repr__(self):
        return f"<ApiTestExecution(id={self.id}, status={self.status})>"


class ApiEnvironment(Base):
    __tablename__ = "api_environments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    name = Column(String(100), nullable=False, comment="环境名称")
    base_url = Column(String(500), comment="基础URL")
    variables = Column(JSON, comment="环境变量")
    headers = Column(JSON, comment="默认请求头")
    auth_config = Column(JSON, comment="认证配置")
    is_default = Column(Boolean, default=False, comment="是否默认环境")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<ApiEnvironment(id={self.id}, name={self.name})>"


class ApiTestVersion(Base):
    """API测试专用版本 - 不与项目管理版本同步"""
    __tablename__ = "api_test_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    version_id = Column(BigInteger, ForeignKey("versions.id"), comment="关联的项目版本ID(可为空)")
    name = Column(String(100), nullable=False, comment="版本名称")
    version_number = Column(String(50), comment="版本号")
    description = Column(Text, comment="版本描述")
    is_api_test_only = Column(Boolean, default=True, comment="是否为API测试专用版本")
    created_by = Column(String(36), comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<ApiTestVersion(id={self.id}, name={self.name})>"