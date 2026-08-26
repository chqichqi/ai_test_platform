"""
项目管理相关的Pydantic Schemas
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict, computed_field, model_validator
from enum import Enum


class UserBrief(BaseModel):
    """用户简要信息"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionStatus(str, Enum):
    PLANNING = "planning"
    DEVELOPING = "developing"
    TESTING = "testing"
    RELEASED = "released"
    ARCHIVED = "archived"


class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str = Field(..., min_length=1, max_length=100, description="项目名称")
    code: str = Field(..., min_length=1, max_length=50, description="项目编码")
    description: Optional[str] = Field(None, description="项目描述")
    owner_id: Optional[str] = Field(None, description="负责人ID(UUID)")
    # 项目类型字段
    project_type: Optional[str] = Field('web', description="项目类型: web/app")
    app_platform: Optional[str] = Field(None, description="APP平台: android/ios")
    # Android 配置
    app_package_name: Optional[str] = Field(None, description="Android: APP包名")
    app_launch_activity: Optional[str] = Field(None, description="Android: 启动Activity")
    # iOS 配置
    app_bundle_id: Optional[str] = Field(None, description="iOS: Bundle ID")
    app_device_type: Optional[str] = Field(None, description="iOS: 设备类型 simulator/real")
    app_device_udid: Optional[str] = Field(None, description="iOS: 真机UDID")
    app_simulator_name: Optional[str] = Field(None, description="iOS: 模拟器名称")
    # 通用自动化配置
    app_automation_name: Optional[str] = Field(None, description="自动化引擎: UiAutomator2/XCUITest/Espresso")
    
    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        if not v:
            raise ValueError('项目编码不能为空')
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', v):
            raise ValueError('项目编码必须以字母开头，只能包含字母、数字、下划线和中划线')
        return v.lower()


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    owner_id: Optional[str] = Field(None, description="负责人ID(UUID)")
    status: Optional[ProjectStatus] = Field(None, description="项目状态")
    # 项目类型字段
    project_type: Optional[str] = Field(None, description="项目类型: web/app")
    app_platform: Optional[str] = Field(None, description="APP平台: android/ios")
    # Android 配置
    app_package_name: Optional[str] = Field(None, description="Android: APP包名")
    app_launch_activity: Optional[str] = Field(None, description="Android: 启动Activity")
    # iOS 配置
    app_bundle_id: Optional[str] = Field(None, description="iOS: Bundle ID")
    app_device_type: Optional[str] = Field(None, description="iOS: 设备类型")
    app_device_udid: Optional[str] = Field(None, description="iOS: 真机UDID")
    app_simulator_name: Optional[str] = Field(None, description="iOS: 模拟器名称")
    # 通用自动化配置
    app_automation_name: Optional[str] = Field(None, description="自动化引擎")


class ProjectResponse(BaseModel):
    """项目响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    owner: Optional[UserBrief] = None
    status: str
    # 项目类型字段
    project_type: Optional[str] = 'web'
    app_platform: Optional[str] = None
    app_package_name: Optional[str] = None
    app_launch_activity: Optional[str] = None
    app_bundle_id: Optional[str] = None
    app_device_type: Optional[str] = None
    app_device_udid: Optional[str] = None
    app_simulator_name: Optional[str] = None
    app_automation_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProjectDetailResponse(ProjectResponse):
    """项目详情响应"""
    versions_count: int = 0
    test_cases_count: int = 0
    latest_version: Optional[dict] = None


class VersionCreate(BaseModel):
    """创建版本请求"""
    project_id: int = Field(..., description="项目 ID")
    version_number: str = Field(..., min_length=1, max_length=50, description="版本号")
    version_name: Optional[str] = Field(None, max_length=100, description="版本名称")
    description: Optional[str] = Field(None, description="版本描述")
    requirement_doc: Optional[str] = Field(None, description="需求文档内容（文本格式）")
    requirement_doc_file: Optional[str] = Field(None, description="需求文档文件路径")
    requirement_doc_file_type: Optional[str] = Field(None, description="需求文档文件类型")
    plan_start_date: Optional[datetime] = Field(None, description="计划开始日期")
    plan_end_date: Optional[datetime] = Field(None, description="计划结束日期")
    
    @field_validator('version_number')
    @classmethod
    def validate_version_number(cls, v):
        if not v or not v.strip():
            raise ValueError('版本号不能为空')
        v = v.strip()
        if len(v) > 50:
            raise ValueError('版本号不能超过50个字符')
        return v
    
    # 注：需求文档可在创建版本后再补充，不再强制要求
    # @model_validator(mode='after')
    # def validate_requirement(self):
    #     if not self.requirement_doc and not self.requirement_doc_file:
    #         raise ValueError('需求文档内容或文件路径必须提供一项')
    #     return self


class VersionReuseCases(BaseModel):
    """跨版本复用用例请求：从任意历史版本复制用例到目标版本（两种模式，至少给一项）"""
    source_version_id: int = Field(..., description="来源版本 ID")
    case_ids: Optional[List[int]] = Field(None, description="勾选模式：勾选的用例 id（源版本视角生效行）")
    module: Optional[str] = Field(None, description="全模块模式：模块名（源版本视角该模块全部生效用例一起复制）")


class VersionUpdate(BaseModel):
    """更新版本请求"""
    version_name: Optional[str] = Field(None, max_length=100, description="版本名称")
    description: Optional[str] = Field(None, description="版本描述")
    requirement_doc: Optional[str] = Field(None, description="需求文档内容（业务流/需求文本）")
    plan_start_date: Optional[datetime] = Field(None, description="计划开始日期")
    plan_end_date: Optional[datetime] = Field(None, description="计划结束日期")
    actual_start_date: Optional[datetime] = Field(None, description="实际开始日期")
    actual_end_date: Optional[datetime] = Field(None, description="实际结束日期")


class VersionStatusUpdate(BaseModel):
    """更新版本状态请求"""
    status: VersionStatus = Field(..., description="目标状态")
    comment: Optional[str] = Field(None, max_length=500, description="状态变更备注")


class VersionResponse(BaseModel):
    """版本响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    project_id: int
    version_number: str
    version_name: Optional[str] = None
    description: Optional[str] = None
    requirement_doc: Optional[str] = None
    requirement_doc_file: Optional[str] = None
    requirement_doc_file_type: Optional[str] = None
    test_cases_count: int = 0
    generation_task_id: Optional[int] = None
    generation_task_display_id: Optional[str] = None
    status: str
    plan_start_date: Optional[datetime] = None
    plan_end_date: Optional[datetime] = None
    actual_start_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    @computed_field
    @property
    def status_display(self) -> str:
        """计算状态显示名称"""
        status_names = {
            'planning': '规划中',
            'developing': '开发中',
            'testing': '测试中',
            'frozen': '已冻结',
            'released': '已发布',
            'archived': '已归档',
        }
        return status_names.get(self.status, self.status)


class VersionListResponse(BaseModel):
    """版本列表响应"""
    items: List[VersionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class VersionDetailResponse(VersionResponse):
    """版本详情响应"""
    requirement_doc: Optional[str] = None
    requirement_doc_url: Optional[str] = None
    test_cases_count: int = 0
    test_plans_count: int = 0


class ProjectStats(BaseModel):
    """项目统计信息"""
    total_versions: int = 0
    total_test_cases: int = 0
    passed_test_cases: int = 0
    failed_test_cases: int = 0
    pending_test_cases: int = 0
    total_executions: int = 0
    latest_execution_time: Optional[datetime] = None