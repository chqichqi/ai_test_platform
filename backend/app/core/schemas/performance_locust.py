"""
Locust性能测试相关Schema
"""
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class LocustScriptCreate(BaseModel):
    project_id: int = Field(..., description="项目ID")
    name: str = Field(..., max_length=200, description="脚本名称")
    description: Optional[str] = Field(None, description="描述")
    host: str = Field(..., description="目标Host")
    case_ids: List[int] = Field(..., description="已审批API用例ID列表")


class LocustScriptResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str]
    file_content: Optional[str]
    file_size: int = 0
    host: Optional[str]
    version: int = 1
    status: str
    source_case_ids: Optional[List[int]]
    created_by: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class LocustScriptListResponse(BaseModel):
    items: List[LocustScriptResponse]
    total: int


class StepConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用梯度")
    step_count: int = Field(default=5, ge=1, le=20, description="步数")
    step_duration: int = Field(default=60, ge=10, le=600, description="每步时长(秒)")
    step_thread_increment: int = Field(default=10, ge=1, le=100, description="每步增加线程数")
    max_users: Optional[int] = Field(None, description="最大用户数")


class LocustExecutionStart(BaseModel):
    script_id: Optional[int] = Field(None, description="脚本ID")
    project_id: Optional[int] = Field(None, description="项目ID")
    name: Optional[str] = Field(None, description="执行名称")
    host: Optional[str] = Field(None, description="目标Host（覆盖脚本中的）")
    num_users: int = Field(default=100, ge=1, le=10000, description="并发用户数")
    spawn_rate: int = Field(default=10, ge=1, le=500, description="孵化率(用户/秒)")
    run_time: int = Field(default=60, ge=10, le=3600, description="运行时长(秒)")
    step_config: Optional[StepConfig] = Field(None, description="梯度配置")


class LocustExecutionResponse(BaseModel):
    id: int
    project_id: int
    script_id: Optional[int]
    scenario_id: Optional[int]
    name: Optional[str]
    status: str
    host: Optional[str]
    num_users: int
    spawn_rate: int
    run_time: int
    step_enabled: bool = False
    step_count: int = 5
    step_duration: int = 60
    step_thread_increment: int = 10
    locust_process_id: Optional[int]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    actual_duration: Optional[int]
    avg_tps: Optional[float]
    max_tps: Optional[float]
    avg_rt: Optional[float]
    p50_rt: Optional[float]
    p90_rt: Optional[float]
    p95_rt: Optional[float]
    p99_rt: Optional[float]
    error_rate: Optional[float]
    total_samples: Optional[int]
    success_samples: Optional[int]
    error_samples: Optional[int]
    created_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class LocustExecutionListResponse(BaseModel):
    items: List[LocustExecutionResponse]
    total: int


class LocustMetricResponse(BaseModel):
    timestamp: str
    elapsed: Optional[int]
    user_count: int
    tps: float
    avg_rt: float
    min_rt: Optional[float]
    max_rt: Optional[float]
    fail_ratio: float
    samples_count: int
    error_count: int = 0


class LocustMetricsResponse(BaseModel):
    status: str
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    progress: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None


class ApprovedApiCaseResponse(BaseModel):
    id: int
    name: str
    method: Optional[str]
    path: Optional[str]
    priority: str
    case_type: str
    description: Optional[str]
    tags: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovedApiCaseListResponse(BaseModel):
    items: List[ApprovedApiCaseResponse]
    total: int
    page: int
    page_size: int
