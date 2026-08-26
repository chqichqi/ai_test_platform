"""
项目管理扩展Schemas
对应需求文档 3.1.3 项目成员管理、环境配置等
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==================== 项目成员管理 ====================

class ProjectRoleInfo(BaseModel):
    """项目角色信息"""
    code: str
    name: str
    description: str
    permissions: List[str]


class ProjectMemberCreate(BaseModel):
    """添加项目成员请求"""
    user_id: str = Field(..., description="用户ID")
    role: str = Field(default="viewer", description="角色: owner/test_lead/tester/developer/viewer")
    permissions: Optional[Dict[str, Any]] = Field(None, description="自定义权限")


class ProjectMemberUpdate(BaseModel):
    """更新项目成员请求"""
    role: Optional[str] = Field(None, description="角色")
    permissions: Optional[Dict[str, Any]] = Field(None, description="自定义权限")


class UserBrief(BaseModel):
    """用户简要信息"""
    id: str
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar: Optional[str] = None


class ProjectMemberResponse(BaseModel):
    """项目成员响应"""
    id: int
    project_id: int
    user_id: str
    user: UserBrief
    role: str
    permissions: Optional[Dict[str, Any]] = None
    joined_at: datetime
    joined_by: Optional[str] = None
    inviter: Optional[UserBrief] = None
    is_active: bool
    
    model_config = {"from_attributes": True}


class ProjectMemberList(BaseModel):
    """项目成员列表响应"""
    items: List[ProjectMemberResponse]
    total: int
    page: int
    page_size: int


# ==================== 项目环境配置 ====================

class ProjectEnvironmentCreate(BaseModel):
    """创建环境配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="环境名称")
    code: str = Field(..., min_length=1, max_length=50, description="环境编码")
    base_url: Optional[str] = Field(None, description="基础URL")
    headers: Optional[Dict[str, str]] = Field(None, description="请求头配置")
    variables: Optional[Dict[str, str]] = Field(None, description="环境变量")
    db_config: Optional[Dict[str, Any]] = Field(None, description="数据库配置")
    is_default: bool = Field(default=False, description="是否默认环境")
    description: Optional[str] = Field(None, description="环境描述")


class ProjectEnvironmentUpdate(BaseModel):
    """更新环境配置请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    variables: Optional[Dict[str, str]] = None
    db_config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class ProjectEnvironmentResponse(BaseModel):
    """环境配置响应"""
    id: int
    project_id: int
    name: str
    code: str
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    variables: Optional[Dict[str, str]] = None
    db_config: Optional[Dict[str, Any]] = None
    is_default: bool
    is_active: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class ProjectEnvironmentList(BaseModel):
    """环境配置列表响应"""
    items: List[ProjectEnvironmentResponse]
    total: int


# ==================== 项目设置 ====================

class NotificationConfig(BaseModel):
    """通知配置"""
    execution_completed: bool = True
    execution_failed: bool = True
    issue_created: bool = True
    channels: List[str] = ["email"]


class ExecutionDefaults(BaseModel):
    """执行默认配置"""
    parallel: int = 4
    retry: int = 1
    timeout: int = 3600


class TestDefaults(BaseModel):
    """测试默认配置"""
    browser: str = "chromium"
    viewport: Dict[str, int] = {"width": 1920, "height": 1080}
    headless: bool = True


class LoginRulesSchema(BaseModel):
    """登录规则配置（存储于 exploration_config.web.login_rules）"""
    username_selector: Optional[str] = None
    password_selector: Optional[str] = None
    submit_text: Optional[str] = None
    submit_fallback: Optional[str] = None
    logged_in_url_patterns: Optional[List[str]] = None
    auth_param_names: Optional[List[str]] = None
    org_url_keyword: Optional[str] = None
    org_title_keyword: Optional[str] = None
    org_card_selector: Optional[str] = None
    org_confirm_text: Optional[str] = None
    org_select_name: Optional[str] = None
    render_wait: Optional[float] = None
    login_poll_interval: Optional[float] = None
    login_max_wait: Optional[int] = None
    page_timeout: Optional[int] = None


class WebExplorationConfigSchema(BaseModel):
    """WEB 端探索配置"""
    base_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    login_rules: Optional[LoginRulesSchema] = None
    convert_batch_size: Optional[int] = None  # 批量转化每批用例数（默认 15）


class AppExplorationConfigSchema(BaseModel):
    """APP 端探索配置"""
    appium_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    auto_launch: Optional[bool] = True


class ExplorationConfigSchema(BaseModel):
    """项目探索完整配置"""
    web: Optional[WebExplorationConfigSchema] = None
    app: Optional[AppExplorationConfigSchema] = None


class ProjectSettingUpdate(BaseModel):
    """更新项目设置请求"""
    notification_config: Optional[NotificationConfig] = None
    execution_defaults: Optional[ExecutionDefaults] = None
    test_defaults: Optional[TestDefaults] = None
    exploration_config: Optional[ExplorationConfigSchema] = None
    custom_settings: Optional[Dict[str, Any]] = None


class ProjectSettingResponse(BaseModel):
    """项目设置响应"""
    id: int
    project_id: int
    notification_config: Optional[Dict[str, Any]] = None
    execution_defaults: Optional[Dict[str, Any]] = None
    test_defaults: Optional[Dict[str, Any]] = None
    exploration_config: Optional[Dict[str, Any]] = None
    custom_settings: Optional[Dict[str, Any]] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== 版本文档历史 ====================

class VersionDocHistoryResponse(BaseModel):
    """版本文档历史响应"""
    id: int
    version_id: int
    doc_type: Optional[str] = None
    doc_url: Optional[str] = None
    doc_content: Optional[Dict[str, Any]] = None
    change_summary: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploader: Optional[UserBrief] = None
    uploaded_at: datetime
    
    model_config = {"from_attributes": True}


class VersionDocHistoryList(BaseModel):
    """版本文档历史列表"""
    items: List[VersionDocHistoryResponse]
    total: int
