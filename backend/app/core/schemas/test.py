"""
测试管理Pydantic模式定义
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, validator, ConfigDict
from app.core.models.test_simple import TestStatus, TestPriority, TestType, ExecutionStatus


# ========== 基础模式 ==========

class TestStep(BaseModel):
    """测试步骤模式"""
    step_number: int = Field(..., ge=1, description="步骤编号")
    action: str = Field(..., min_length=1, description="操作描述")
    expected_result: str = Field(..., min_length=1, description="预期结果")
    data: Optional[Dict[str, Any]] = Field(default=None, description="测试数据")
    
    model_config = ConfigDict(from_attributes=True)


class Attachment(BaseModel):
    """附件模式"""
    name: str = Field(..., description="附件名称")
    url: str = Field(..., description="附件URL")
    type: str = Field(..., description="附件类型")
    size: Optional[int] = Field(default=None, description="附件大小")
    
    model_config = ConfigDict(from_attributes=True)


class Evidence(BaseModel):
    """证据模式"""
    type: str = Field(..., description="证据类型（screenshot, log, video等）")
    url: str = Field(..., description="证据URL")
    description: Optional[str] = Field(default=None, description="证据描述")
    timestamp: Optional[datetime] = Field(default=None, description="时间戳")
    
    model_config = ConfigDict(from_attributes=True)


# ========== 测试用例模式 ==========

class TestCaseBase(BaseModel):
    """测试用例基础模式"""
    title: str = Field(..., min_length=3, max_length=200, description="测试用例标题")
    description: Optional[str] = Field(default=None, description="详细描述")
    summary: Optional[str] = Field(default=None, max_length=500, description="摘要")
    test_type: TestType = Field(default=TestType.FUNCTIONAL, description="测试类型")
    priority: TestPriority = Field(default=TestPriority.MEDIUM, description="优先级")
    status: TestStatus = Field(default=TestStatus.DRAFT, description="状态")
    preconditions: Optional[str] = Field(default=None, description="前置条件")
    test_steps: Optional[List[TestStep]] = Field(default=None, description="测试步骤")
    expected_results: Optional[str] = Field(default=None, description="预期结果")
    postconditions: Optional[str] = Field(default=None, description="后置条件")
    module: Optional[str] = Field(default=None, max_length=100, description="模块")
    component: Optional[str] = Field(default=None, max_length=100, description="组件")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    estimated_time: Optional[int] = Field(default=None, ge=0, description="预估时间（分钟）")
    attachments: Optional[List[Attachment]] = Field(default=None, description="附件")
    custom_fields: Optional[Dict[str, Any]] = Field(default=None, description="自定义字段")
    notes: Optional[str] = Field(default=None, description="备注")
    
    model_config = ConfigDict(from_attributes=True)


class TestCaseCreate(TestCaseBase):
    """创建测试用例模式"""
    project_id: Optional[UUID] = Field(default=None, description="项目ID")
    assigned_to: Optional[UUID] = Field(default=None, description="分配给的用户ID")


class TestCaseUpdate(BaseModel):
    """更新测试用例模式"""
    title: Optional[str] = Field(default=None, min_length=3, max_length=200, description="测试用例标题")
    description: Optional[str] = Field(default=None, description="详细描述")
    summary: Optional[str] = Field(default=None, max_length=500, description="摘要")
    test_type: Optional[TestType] = Field(default=None, description="测试类型")
    priority: Optional[TestPriority] = Field(default=None, description="优先级")
    status: Optional[TestStatus] = Field(default=None, description="状态")
    preconditions: Optional[str] = Field(default=None, description="前置条件")
    test_steps: Optional[List[TestStep]] = Field(default=None, description="测试步骤")
    expected_results: Optional[str] = Field(default=None, description="预期结果")
    postconditions: Optional[str] = Field(default=None, description="后置条件")
    module: Optional[str] = Field(default=None, max_length=100, description="模块")
    component: Optional[str] = Field(default=None, max_length=100, description="组件")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    assigned_to: Optional[UUID] = Field(default=None, description="分配给的用户ID")
    estimated_time: Optional[int] = Field(default=None, ge=0, description="预估时间（分钟）")
    attachments: Optional[List[Attachment]] = Field(default=None, description="附件")
    custom_fields: Optional[Dict[str, Any]] = Field(default=None, description="自定义字段")
    notes: Optional[str] = Field(default=None, description="备注")
    
    model_config = ConfigDict(from_attributes=True)


class TestCaseInDB(TestCaseBase):
    """数据库中的测试用例模式"""
    id: UUID
    project_id: Optional[UUID] = None
    created_by: UUID
    assigned_to: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    execution_count: int = 0
    last_executed_at: Optional[datetime] = None
    actual_time: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class TestCaseResponse(TestCaseInDB):
    """测试用例响应模式"""
    created_by_user: Optional[Dict[str, Any]] = None
    assigned_to_user: Optional[Dict[str, Any]] = None
    execution_stats: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(from_attributes=True)


# ========== 测试执行模式 ==========

class TestExecutionBase(BaseModel):
    """测试执行基础模式"""
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING, description="执行状态")
    actual_results: Optional[str] = Field(default=None, description="实际结果")
    notes: Optional[str] = Field(default=None, description="执行备注")
    evidence: Optional[List[Evidence]] = Field(default=None, description="执行证据")
    failure_reason: Optional[str] = Field(default=None, description="失败原因")
    failure_type: Optional[str] = Field(default=None, description="失败类型")
    stack_trace: Optional[str] = Field(default=None, description="堆栈跟踪")
    environment: Optional[str] = Field(default=None, max_length=100, description="测试环境")
    browser: Optional[str] = Field(default=None, max_length=50, description="浏览器")
    os: Optional[str] = Field(default=None, max_length=50, description="操作系统")
    device: Optional[str] = Field(default=None, max_length=50, description="设备")
    duration: Optional[int] = Field(default=None, ge=0, description="执行时长（秒）")
    execution_type: str = Field(default="scenario", max_length=30, description="执行类型: scenario=执行中心场景测试, ui_verify=UI用例临时验证")

    model_config = ConfigDict(from_attributes=True)


class TestExecutionCreate(TestExecutionBase):
    """创建测试执行模式"""
    test_case_id: UUID = Field(..., description="测试用例ID")
    project_id: Optional[UUID] = Field(default=None, description="项目ID")
    test_run_id: Optional[UUID] = Field(default=None, description="测试运行ID")


class TestExecutionUpdate(BaseModel):
    """更新测试执行模式"""
    status: Optional[ExecutionStatus] = Field(default=None, description="执行状态")
    actual_results: Optional[str] = Field(default=None, description="实际结果")
    notes: Optional[str] = Field(default=None, description="执行备注")
    evidence: Optional[List[Evidence]] = Field(default=None, description="执行证据")
    failure_reason: Optional[str] = Field(default=None, description="失败原因")
    failure_type: Optional[str] = Field(default=None, description="失败类型")
    stack_trace: Optional[str] = Field(default=None, description="堆栈跟踪")
    environment: Optional[str] = Field(default=None, max_length=100, description="测试环境")
    browser: Optional[str] = Field(default=None, max_length=50, description="浏览器")
    os: Optional[str] = Field(default=None, max_length=50, description="操作系统")
    device: Optional[str] = Field(default=None, max_length=50, description="设备")
    duration: Optional[int] = Field(default=None, ge=0, description="执行时长（秒）")
    
    model_config = ConfigDict(from_attributes=True)


class TestExecutionInDB(TestExecutionBase):
    """数据库中的测试执行模式"""
    id: UUID
    test_case_id: UUID
    project_id: Optional[UUID] = None
    test_run_id: Optional[UUID] = None
    executed_by: UUID
    executed_at: datetime
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class TestExecutionResponse(TestExecutionInDB):
    """测试执行响应模式"""
    executed_by_user: Optional[Dict[str, Any]] = None
    test_case: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


# ========== 测试结果模式 ==========

class TestResultBase(BaseModel):
    """测试结果基础模式"""
    step_number: int = Field(..., ge=1, description="步骤编号")
    step_description: str = Field(..., description="步骤描述")
    expected_result: str = Field(..., description="预期结果")
    actual_result: str = Field(..., description="实际结果")
    result_status: ExecutionStatus = Field(default=ExecutionStatus.PENDING, description="结果状态")
    notes: Optional[str] = Field(default=None, description="备注")
    evidence: Optional[List[Evidence]] = Field(default=None, description="证据")
    duration: Optional[int] = Field(default=None, ge=0, description="步骤时长（秒）")
    
    model_config = ConfigDict(from_attributes=True)


class TestResultCreate(TestResultBase):
    """创建测试结果模式"""
    execution_id: UUID = Field(..., description="执行ID")


class TestResultUpdate(BaseModel):
    """更新测试结果模式"""
    step_description: Optional[str] = Field(default=None, description="步骤描述")
    expected_result: Optional[str] = Field(default=None, description="预期结果")
    actual_result: Optional[str] = Field(default=None, description="实际结果")
    result_status: Optional[ExecutionStatus] = Field(default=None, description="结果状态")
    notes: Optional[str] = Field(default=None, description="备注")
    evidence: Optional[List[Evidence]] = Field(default=None, description="证据")
    duration: Optional[int] = Field(default=None, ge=0, description="步骤时长（秒）")
    
    model_config = ConfigDict(from_attributes=True)


class TestResultInDB(TestResultBase):
    """数据库中的测试结果模式"""
    id: UUID
    execution_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# ========== 测试运行模式 ==========

class TestRunBase(BaseModel):
    """测试运行基础模式"""
    name: str = Field(..., min_length=3, max_length=200, description="运行名称")
    description: Optional[str] = Field(default=None, description="描述")
    environment: Optional[str] = Field(default=None, max_length=100, description="测试环境")
    test_plan_id: Optional[UUID] = Field(default=None, description="测试计划ID")
    config: Optional[Dict[str, Any]] = Field(default=None, description="运行配置")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    
    model_config = ConfigDict(from_attributes=True)


class TestRunCreate(TestRunBase):
    """创建测试运行模式"""
    project_id: UUID = Field(..., description="项目ID")


class TestRunUpdate(BaseModel):
    """更新测试运行模式"""
    name: Optional[str] = Field(default=None, min_length=3, max_length=200, description="运行名称")
    description: Optional[str] = Field(default=None, description="描述")
    environment: Optional[str] = Field(default=None, max_length=100, description="测试环境")
    status: Optional[ExecutionStatus] = Field(default=None, description="状态")
    config: Optional[Dict[str, Any]] = Field(default=None, description="运行配置")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    duration: Optional[int] = Field(default=None, ge=0, description="总时长（秒）")
    
    model_config = ConfigDict(from_attributes=True)


class TestRunInDB(TestRunBase):
    """数据库中的测试运行模式"""
    id: UUID
    project_id: UUID
    started_by: UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration: Optional[int] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    total_cases: int = 0
    executed_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    blocked_cases: int = 0
    skipped_cases: int = 0
    error_cases: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class TestRunResponse(TestRunInDB):
    """测试运行响应模式"""
    started_by_user: Optional[Dict[str, Any]] = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0
    error: int = 0
    success_rate: float = 0.0
    
    model_config = ConfigDict(from_attributes=True)


# ========== 测试计划模式 ==========

class TestPlanBase(BaseModel):
    """测试计划基础模式"""
    name: str = Field(..., min_length=3, max_length=200, description="计划名称")
    description: Optional[str] = Field(default=None, description="描述")
    version: str = Field(default="1.0", description="版本")
    start_date: Optional[datetime] = Field(default=None, description="开始日期")
    end_date: Optional[datetime] = Field(default=None, description="结束日期")
    status: TestStatus = Field(default=TestStatus.DRAFT, description="状态")
    objectives: Optional[str] = Field(default=None, description="测试目标")
    scope: Optional[str] = Field(default=None, description="测试范围")
    out_of_scope: Optional[str] = Field(default=None, description="非测试范围")
    assumptions: Optional[str] = Field(default=None, description="假设条件")
    risks: Optional[str] = Field(default=None, description="风险")
    dependencies: Optional[str] = Field(default=None, description="依赖项")
    total_cases: Optional[int] = Field(default=0, ge=0, description="总用例数")
    automated_cases: Optional[int] = Field(default=0, ge=0, description="自动化用例数")
    manual_cases: Optional[int] = Field(default=0, ge=0, description="手动用例数")
    
    model_config = ConfigDict(from_attributes=True)


class TestPlanCreate(TestPlanBase):
    """创建测试计划模式"""
    project_id: UUID = Field(..., description="项目ID")


class TestPlanUpdate(BaseModel):
    """更新测试计划模式"""
    name: Optional[str] = Field(default=None, min_length=3, max_length=200, description="计划名称")
    description: Optional[str] = Field(default=None, description="描述")
    version: Optional[str] = Field(default=None, description="版本")
    start_date: Optional[datetime] = Field(default=None, description="开始日期")
    end_date: Optional[datetime] = Field(default=None, description="结束日期")
    status: Optional[TestStatus] = Field(default=None, description="状态")
    objectives: Optional[str] = Field(default=None, description="测试目标")
    scope: Optional[str] = Field(default=None, description="测试范围")
    out_of_scope: Optional[str] = Field(default=None, description="非测试范围")
    assumptions: Optional[str] = Field(default=None, description="假设条件")
    risks: Optional[str] = Field(default=None, description="风险")
    dependencies: Optional[str] = Field(default=None, description="依赖项")
    total_cases: Optional[int] = Field(default=None, ge=0, description="总用例数")
    automated_cases: Optional[int] = Field(default=None, ge=0, description="自动化用例数")
    manual_cases: Optional[int] = Field(default=None, ge=0, description="手动用例数")
    
    model_config = ConfigDict(from_attributes=True)


class TestPlanInDB(TestPlanBase):
    """数据库中的测试计划模式"""
    id: UUID
    project_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class TestPlanResponse(TestPlanInDB):
    """测试计划响应模式"""
    created_by_user: Optional[Dict[str, Any]] = None
    test_case_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)


# ========== 查询和过滤模式 ==========

class TestCaseFilter(BaseModel):
    """测试用例过滤模式"""
    project_id: Optional[UUID] = Field(default=None, description="项目ID")
    test_type: Optional[TestType] = Field(default=None, description="测试类型")
    priority: Optional[TestPriority] = Field(default=None, description="优先级")
    status: Optional[TestStatus] = Field(default=None, description="状态")
    module: Optional[str] = Field(default=None, description="模块")
    component: Optional[str] = Field(default=None, description="组件")
    created_by: Optional[UUID] = Field(default=None, description="创建者ID")
    assigned_to: Optional[UUID] = Field(default=None, description="分配给的用户ID")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    search: Optional[str] = Field(default=None, description="搜索关键词")
    
    model_config = ConfigDict(from_attributes=True)


class TestExecutionFilter(BaseModel):
    """测试执行过滤模式"""
    test_case_id: Optional[UUID] = Field(default=None, description="测试用例ID")
    project_id: Optional[UUID] = Field(default=None, description="项目ID")
    test_run_id: Optional[UUID] = Field(default=None, description="测试运行ID")
    status: Optional[ExecutionStatus] = Field(default=None, description="执行状态")
    executed_by: Optional[UUID] = Field(default=None, description="执行者ID")
    environment: Optional[str] = Field(default=None, description="测试环境")
    start_date: Optional[datetime] = Field(default=None, description="开始日期")
    end_date: Optional[datetime] = Field(default=None, description="结束日期")
    
    model_config = ConfigDict(from_attributes=True)


class TestRunFilter(BaseModel):
    """测试运行过滤模式"""
    project_id: Optional[UUID] = Field(default=None, description="项目ID")
    test_plan_id: Optional[UUID] = Field(default=None, description="测试计划ID")
    status: Optional[ExecutionStatus] = Field(default=None, description="状态")
    started_by: Optional[UUID] = Field(default=None, description="启动者ID")
    environment: Optional[str] = Field(default=None, description="测试环境")
    start_date: Optional[datetime] = Field(default=None, description="开始日期")
    end_date: Optional[datetime] = Field(default=None, description="结束日期")
    
    model_config = ConfigDict(from_attributes=True)


# ========== 统计和报告模式 ==========

class TestStats(BaseModel):
    """测试统计模式"""
    total: int = Field(..., description="总数")
    passed: int = Field(..., description="通过数")
    failed: int = Field(..., description="失败数")
    blocked: int = Field(..., description="阻塞数")
    skipped: int = Field(..., description="跳过数")
    error: int = Field(..., description="错误数")
    success_rate: float = Field(..., description="成功率")
    avg_duration: Optional[float] = Field(default=None, description="平均执行时长")
    
    model_config = ConfigDict(from_attributes=True)


class TestReport(BaseModel):
    """测试报告模式"""
    period_start: datetime = Field(..., description="报告开始时间")
    period_end: datetime = Field(..., description="报告结束时间")
    total_test_cases: TestStats = Field(..., description="测试用例统计")
    total_executions: TestStats = Field(..., description="测试执行统计")
    total_test_runs: TestStats = Field(..., description="测试运行统计")
    by_test_type: Dict[str, TestStats] = Field(..., description="按测试类型统计")
    by_priority: Dict[str, TestStats] = Field(..., description="按优先级统计")
    by_module: Dict[str, TestStats] = Field(..., description="按模块统计")
    trend_data: List[Dict[str, Any]] = Field(..., description="趋势数据")
    top_failures: List[Dict[str, Any]] = Field(..., description="主要失败原因")
    
    model_config = ConfigDict(from_attributes=True)