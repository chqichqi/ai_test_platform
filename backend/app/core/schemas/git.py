"""
Git版本管理相关的Pydantic Schemas
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class AuthType(str, Enum):
    SSH = "ssh"
    TOKEN = "token"
    PASSWORD = "password"
    NONE = "none"


class RepositoryStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class WebhookEventType(str, Enum):
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    MERGE_REQUEST = "merge_request"
    RELEASE = "release"


class RepositoryCreate(BaseModel):
    """创建仓库请求"""
    project_id: int = Field(..., description="项目ID")
    name: str = Field(..., min_length=1, max_length=100, description="仓库名称")
    url: str = Field(..., min_length=1, max_length=500, description="仓库URL")
    auth_type: AuthType = Field(default=AuthType.NONE, description="认证类型")
    auth_token: Optional[str] = Field(None, description="认证Token")
    ssh_key: Optional[str] = Field(None, description="SSH私钥")
    username: Optional[str] = Field(None, max_length=100, description="用户名")
    password: Optional[str] = Field(None, max_length=255, description="密码")
    default_branch: str = Field(default="main", max_length=50, description="默认分支")


class RepositoryUpdate(BaseModel):
    """更新仓库请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="仓库名称")
    auth_type: Optional[AuthType] = Field(None, description="认证类型")
    auth_token: Optional[str] = Field(None, description="认证Token")
    ssh_key: Optional[str] = Field(None, description="SSH私钥")
    username: Optional[str] = Field(None, max_length=100, description="用户名")
    password: Optional[str] = Field(None, max_length=255, description="密码")
    default_branch: Optional[str] = Field(None, max_length=50, description="默认分支")
    status: Optional[RepositoryStatus] = Field(None, description="状态")


class RepositoryResponse(BaseModel):
    """仓库响应"""
    id: int
    project_id: int
    name: str
    url: str
    auth_type: str
    default_branch: str
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class RepositoryListResponse(BaseModel):
    """仓库列表响应"""
    items: List[RepositoryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RepositoryTestConnection(BaseModel):
    """连接测试请求"""
    pass


class RepositoryTestResult(BaseModel):
    """连接测试结果"""
    success: bool
    message: str
    branch_count: Optional[int] = None
    last_commit: Optional[dict] = None


class BranchResponse(BaseModel):
    """分支响应"""
    id: int
    repository_id: int
    name: str
    last_commit_hash: Optional[str] = None
    last_commit_message: Optional[str] = None
    last_commit_author: Optional[str] = None
    last_commit_at: Optional[datetime] = None
    is_default: int = 0
    is_protected: int = 0
    ahead_count: int = 0
    behind_count: int = 0
    status: str
    
    model_config = {"from_attributes": True}


class BranchListResponse(BaseModel):
    """分支列表响应"""
    items: List[BranchResponse]
    total: int


class CommitResponse(BaseModel):
    """提交响应"""
    id: int
    repository_id: int
    commit_hash: str
    short_hash: Optional[str] = None
    branch: Optional[str] = None
    author: Optional[str] = None
    author_email: Optional[str] = None
    message: Optional[str] = None
    committed_at: Optional[datetime] = None
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    created_at: datetime
    
    model_config = {"from_attributes": True}


class CommitDetailResponse(CommitResponse):
    """提交详情响应"""
    files: Optional[List[dict]] = None
    parent_hashes: Optional[str] = None


class CommitListResponse(BaseModel):
    """提交列表响应"""
    items: List[CommitResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WebhookCreate(BaseModel):
    """创建Webhook请求"""
    repository_id: int = Field(..., description="仓库ID")
    name: Optional[str] = Field(None, max_length=100, description="Webhook名称")
    trigger_events: List[str] = Field(..., description="触发事件列表")
    trigger_branches: Optional[List[str]] = Field(None, description="触发分支列表")
    trigger_paths: Optional[List[str]] = Field(None, description="触发路径规则")
    test_plan_id: Optional[int] = Field(None, description="关联的测试计划ID")
    execution_config: Optional[dict] = Field(None, description="执行配置")


class WebhookUpdate(BaseModel):
    """更新Webhook请求"""
    name: Optional[str] = Field(None, max_length=100, description="Webhook名称")
    trigger_events: Optional[List[str]] = Field(None, description="触发事件列表")
    trigger_branches: Optional[List[str]] = Field(None, description="触发分支列表")
    trigger_paths: Optional[List[str]] = Field(None, description="触发路径规则")
    test_plan_id: Optional[int] = Field(None, description="关联的测试计划ID")
    execution_config: Optional[dict] = Field(None, description="执行配置")
    enabled: Optional[bool] = Field(None, description="是否启用")


class WebhookResponse(BaseModel):
    """Webhook响应"""
    id: int
    repository_id: int
    name: Optional[str] = None
    webhook_url: Optional[str] = None
    trigger_events: Optional[List[str]] = None
    trigger_branches: Optional[List[str]] = None
    trigger_paths: Optional[List[str]] = None
    test_plan_id: Optional[int] = None
    execution_config: Optional[dict] = None
    enabled: int = 1
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class WebhookListResponse(BaseModel):
    """Webhook列表响应"""
    items: List[WebhookResponse]
    total: int


class WebhookLogResponse(BaseModel):
    """Webhook日志响应"""
    id: int
    webhook_id: int
    event_type: Optional[str] = None
    triggered: int = 0
    trigger_reason: Optional[str] = None
    execution_id: Optional[int] = None
    error_message: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}


class WebhookLogListResponse(BaseModel):
    """Webhook日志列表响应"""
    items: List[WebhookLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BranchCompareRequest(BaseModel):
    """分支对比请求"""
    base_branch: str = Field(..., description="基础分支")
    target_branch: str = Field(..., description="目标分支")


class BranchCompareResponse(BaseModel):
    """分支对比响应"""
    base_branch: str
    target_branch: str
    ahead_count: int
    behind_count: int
    commits: List[CommitResponse]
    files_changed: List[dict]


class CommitLinkRequest(BaseModel):
    """提交关联用例请求"""
    test_case_id: int = Field(..., description="测试用例ID")
    link_type: str = Field(default="reference", description="关联类型")


class SyncRepositoryRequest(BaseModel):
    """同步仓库请求"""
    force: bool = Field(default=False, description="是否强制同步")