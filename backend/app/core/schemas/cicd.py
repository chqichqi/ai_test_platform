"""
CI/CD集成 Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CICDPlatformEnum:
    JENKINS = "jenkins"
    GITLAB = "gitlab"
    GITHUB = "github"


class TriggerTypeEnum:
    ON_COMMIT = "on_commit"
    ON_PR = "on_pr"
    ON_MERGE = "on_merge"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class PipelineStatusEnum:
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class CICDConfigCreate(BaseModel):
    project_id: int
    name: str = Field(..., max_length=200)
    platform: str = Field(..., pattern="^(jenkins|gitlab|github)$")
    platform_url: Optional[str] = Field(None, max_length=500)
    api_token: Optional[str] = Field(None, max_length=500)
    username: Optional[str] = Field(None, max_length=100)
    webhook_secret: Optional[str] = Field(None, max_length=200)
    config_data: Optional[Dict[str, Any]] = None
    enabled: bool = True


class CICDConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    platform_url: Optional[str] = Field(None, max_length=500)
    api_token: Optional[str] = Field(None, max_length=500)
    username: Optional[str] = Field(None, max_length=100)
    webhook_secret: Optional[str] = Field(None, max_length=200)
    config_data: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class CICDConfigResponse(BaseModel):
    id: int
    project_id: int
    name: str
    platform: str
    platform_url: Optional[str]
    username: Optional[str]
    webhook_url: Optional[str]
    enabled: bool
    last_sync_at: Optional[datetime]
    sync_status: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PipelineDefinitionCreate(BaseModel):
    config_id: int
    project_id: int
    name: str = Field(..., max_length=200)
    external_id: Optional[str] = Field(None, max_length=200)
    trigger_type: str = Field(default="manual", pattern="^(on_commit|on_pr|on_merge|scheduled|manual)$")
    trigger_config: Optional[Dict[str, Any]] = None
    test_plan_id: Optional[int] = None
    test_case_ids: Optional[List[int]] = None
    test_params: Optional[Dict[str, Any]] = None
    environment: Optional[str] = Field(None, max_length=100)
    timeout: int = Field(default=3600, ge=60, le=86400)
    notification_config: Optional[Dict[str, Any]] = None
    enabled: bool = True


class PipelineDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    external_id: Optional[str] = Field(None, max_length=200)
    trigger_type: Optional[str] = None
    trigger_config: Optional[Dict[str, Any]] = None
    test_plan_id: Optional[int] = None
    test_case_ids: Optional[List[int]] = None
    test_params: Optional[Dict[str, Any]] = None
    environment: Optional[str] = Field(None, max_length=100)
    timeout: Optional[int] = Field(None, ge=60, le=86400)
    notification_config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class PipelineDefinitionResponse(BaseModel):
    id: int
    config_id: int
    project_id: int
    name: str
    external_id: Optional[str]
    trigger_type: str
    trigger_config: Optional[Dict[str, Any]]
    test_plan_id: Optional[int]
    test_case_ids: Optional[List[int]]
    test_params: Optional[Dict[str, Any]]
    environment: Optional[str]
    timeout: int
    notification_config: Optional[Dict[str, Any]]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PipelineExecutionResponse(BaseModel):
    id: int
    pipeline_id: int
    project_id: int
    external_build_id: Optional[str]
    build_number: Optional[int]
    build_url: Optional[str]
    status: str
    trigger_type: Optional[str]
    trigger_by: Optional[str]
    trigger_ref: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration: Optional[int]
    total_cases: int
    passed_cases: int
    failed_cases: int
    skipped_cases: int
    pass_rate: float
    test_results: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerPipelineRequest(BaseModel):
    pipeline_id: int
    branch: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    environment: Optional[str] = None


class TriggerPipelineResponse(BaseModel):
    success: bool
    message: str
    execution_id: Optional[int] = None
    build_number: Optional[int] = None
    build_url: Optional[str] = None


class WebhookEventResponse(BaseModel):
    id: int
    config_id: Optional[int]
    event_type: Optional[str]
    event_id: Optional[str]
    source: Optional[str]
    processed: bool
    process_result: Optional[str]
    received_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class JenkinsJobInfo(BaseModel):
    name: str
    url: str
    color: str
    last_build: Optional[Dict[str, Any]] = None


class JenkinsBuildInfo(BaseModel):
    number: int
    url: str
    result: Optional[str]
    building: bool
    duration: Optional[int]
    timestamp: Optional[int]


class GitLabPipelineInfo(BaseModel):
    id: int
    status: str
    ref: str
    sha: str
    web_url: str
    created_at: str
    updated_at: Optional[str]


class GitHubWorkflowRun(BaseModel):
    id: int
    name: str
    status: str
    conclusion: Optional[str]
    html_url: str
    created_at: str
    updated_at: Optional[str]
    head_branch: str
    head_sha: str


class CICDConfigListResponse(BaseModel):
    items: List[CICDConfigResponse]
    total: int
    page: int
    page_size: int


class PipelineListResponse(BaseModel):
    items: List[PipelineDefinitionResponse]
    total: int
    page: int
    page_size: int


class ExecutionListResponse(BaseModel):
    items: List[PipelineExecutionResponse]
    total: int
    page: int
    page_size: int


class CICDDashboardStats(BaseModel):
    total_configs: int
    active_configs: int
    total_pipelines: int
    active_pipelines: int
    total_executions: int
    success_rate: float
    recent_executions: List[PipelineExecutionResponse]


PLATFORM_OPTIONS = [
    {"value": "jenkins", "label": "Jenkins"},
    {"value": "gitlab", "label": "GitLab CI"},
    {"value": "github", "label": "GitHub Actions"}
]

TRIGGER_OPTIONS = [
    {"value": "manual", "label": "手动触发"},
    {"value": "on_commit", "label": "提交触发"},
    {"value": "on_pr", "label": "PR触发"},
    {"value": "on_merge", "label": "合并触发"},
    {"value": "scheduled", "label": "定时触发"}
]

STATUS_OPTIONS = [
    {"value": "pending", "label": "等待中", "color": "#faad14"},
    {"value": "running", "label": "执行中", "color": "#1890ff"},
    {"value": "success", "label": "成功", "color": "#52c41a"},
    {"value": "failed", "label": "失败", "color": "#f5222d"},
    {"value": "cancelled", "label": "已取消", "color": "#8c8c8c"},
    {"value": "timeout", "label": "超时", "color": "#fa8c16"}
]