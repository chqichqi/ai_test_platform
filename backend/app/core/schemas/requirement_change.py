"""
需求变更管理相关 Schema 定义
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChangeType:
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class ImpactLevel:
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChangeRecordStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChangeAction:
    GENERATE_NEW = "generate_new"
    UPDATE_EXISTING = "update_existing"
    DEPRECATE = "deprecate"
    KEEP_OLD = "keep_old"
    ARCHIVE = "archive"


class ModuleChangeAnalysis(BaseModel):
    """模块变更分析结果"""
    module_name: str = Field(..., description="模块名称")
    change_type: str = Field(..., description="变更类型: added/modified/deleted/unchanged")
    old_description: Optional[str] = Field(None, description="原功能描述")
    new_description: Optional[str] = Field(None, description="新功能描述")
    impact_level: str = Field(default=ImpactLevel.MEDIUM, description="影响级别")
    affected_test_cases: List[int] = Field(default_factory=list, description="受影响的测试用例ID列表")
    suggested_action: str = Field(..., description="建议处理动作")
    suggested_reason: str = Field(..., description="建议原因说明")


class ChangeSummary(BaseModel):
    """变更摘要"""
    added_modules: List[str] = Field(default_factory=list, description="新增的功能模块")
    modified_modules: List[str] = Field(default_factory=list, description="修改的功能模块")
    deleted_modules: List[str] = Field(default_factory=list, description="删除的功能模块")
    unchanged_modules: List[str] = Field(default_factory=list, description="无变化的功能模块")
    added_count: int = Field(default=0, description="新增功能数量")
    modified_count: int = Field(default=0, description="修改功能数量")
    deleted_count: int = Field(default=0, description="删除功能数量")
    unchanged_count: int = Field(default=0, description="无变化功能数量")


class AnalyzeChangeRequest(BaseModel):
    """分析变更请求"""
    version_id: int = Field(..., description="版本ID")
    supplement_requirement: str = Field(..., description="补充需求文档内容")


class AnalyzeChangeResponse(BaseModel):
    """分析变更响应"""
    success: bool = Field(..., description="是否成功")
    change_summary: ChangeSummary = Field(..., description="变更摘要")
    detail_analysis: List[ModuleChangeAnalysis] = Field(default_factory=list, description="详细变更分析")
    total_affected_cases: int = Field(default=0, description="总受影响测试用例数")
    estimated_new_cases: int = Field(default=0, description="预估新生成测试用例数")
    message: str = Field(default="", description="分析结果说明")


class RequirementChangeRecordCreate(BaseModel):
    """创建变更记录请求"""
    version_id: int = Field(..., description="版本ID")
    change_type: str = Field(..., description="变更类型")
    module_name: str = Field(..., description="模块名称")
    old_description: Optional[str] = Field(None, description="原功能描述")
    new_description: Optional[str] = Field(None, description="新功能描述")
    impact_level: str = Field(default=ImpactLevel.MEDIUM, description="影响级别")
    affected_test_cases: List[int] = Field(default_factory=list, description="受影响的测试用例ID")
    suggested_action: str = Field(..., description="建议处理动作")
    suggested_reason: str = Field(..., description="建议原因")


class RequirementChangeRecordResponse(BaseModel):
    """变更记录响应"""
    id: int = Field(..., description="记录ID")
    version_id: int = Field(..., description="版本ID")
    change_type: str = Field(..., description="变更类型")
    module_name: str = Field(..., description="模块名称")
    old_description: Optional[str] = Field(None, description="原功能描述")
    new_description: Optional[str] = Field(None, description="新功能描述")
    impact_level: str = Field(..., description="影响级别")
    affected_test_cases: List[int] = Field(default_factory=list, description="受影响的测试用例ID")
    affected_test_cases_count: int = Field(default=0, description="受影响测试用例数量")
    suggested_action: Optional[str] = Field(None, description="建议处理动作")
    suggested_reason: Optional[str] = Field(None, description="建议原因")
    status: str = Field(..., description="状态")
    action_taken: Optional[str] = Field(None, description="实际执行的动作")
    keep_old_cases: bool = Field(default=False, description="是否保留旧测试用例")
    new_test_cases: List[int] = Field(default_factory=list, description="新生成的测试用例ID")
    new_test_cases_count: int = Field(default=0, description="新生成测试用例数量")
    created_by: Optional[str] = Field(None, description="创建人ID")
    created_at: datetime = Field(..., description="创建时间")
    reviewed_by: Optional[str] = Field(None, description="审核人ID")
    reviewed_at: Optional[datetime] = Field(None, description="审核时间")
    review_comment: Optional[str] = Field(None, description="审核意见")
    processed_by: Optional[str] = Field(None, description="处理人ID")
    processed_at: Optional[datetime] = Field(None, description="处理完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")


class RequirementChangeRecordListResponse(BaseModel):
    """变更记录列表响应"""
    items: List[RequirementChangeRecordResponse] = Field(default_factory=list, description="记录列表")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=10, description="每页数量")
    total_pages: int = Field(default=0, description="总页数")


class ApproveChangeRequest(BaseModel):
    """批准变更请求"""
    action: str = Field(..., description="处理动作: generate_new/update_existing/deprecate/keep_old/archive")
    keep_old_cases: bool = Field(default=False, description="是否保留旧测试用例")
    review_comment: Optional[str] = Field(None, description="审核意见")


class BatchApproveRequest(BaseModel):
    """批量批准变更请求"""
    actions: List[Dict[str, Any]] = Field(default_factory=list, description="批量操作列表")
    approve_all: bool = Field(default=False, description="是否一键批准所有变更")


class UploadSupplementRequest(BaseModel):
    """上传补充需求请求"""
    version_id: int = Field(..., description="版本ID")
    supplement_content: Optional[str] = Field(None, description="补充需求内容")
    supplement_file_path: Optional[str] = Field(None, description="补充需求文件路径")
    supplement_file_type: Optional[str] = Field(None, description="补充需求文件类型")
    batch_name: Optional[str] = Field(None, description="批次名称")
    batch_description: Optional[str] = Field(None, description="批次描述")


class RequirementChangeBatchCreate(BaseModel):
    """创建变更批次请求"""
    version_id: int = Field(..., description="版本ID")
    batch_name: Optional[str] = Field(None, description="批次名称")
    batch_description: Optional[str] = Field(None, description="批次描述")
    original_requirement_doc: Optional[str] = Field(None, description="原需求文档内容")
    supplement_requirement_doc: str = Field(..., description="补充需求文档内容")
    supplement_file_path: Optional[str] = Field(None, description="补充需求文件路径")
    supplement_file_type: Optional[str] = Field(None, description="补充需求文件类型")


class RequirementChangeBatchResponse(BaseModel):
    """变更批次响应"""
    id: int = Field(..., description="批次ID")
    version_id: int = Field(..., description="版本ID")
    batch_name: Optional[str] = Field(None, description="批次名称")
    batch_description: Optional[str] = Field(None, description="批次描述")
    change_summary: Optional[Dict[str, Any]] = Field(None, description="变更摘要")
    added_count: int = Field(default=0, description="新增功能数量")
    modified_count: int = Field(default=0, description="修改功能数量")
    deleted_count: int = Field(default=0, description="删除功能数量")
    unchanged_count: int = Field(default=0, description="无变化功能数量")
    total_affected_cases: int = Field(default=0, description="总受影响测试用例数")
    total_new_cases: int = Field(default=0, description="总新生成测试用例数")
    status: str = Field(..., description="批次状态")
    created_by: Optional[int] = Field(None, description="创建人ID")
    created_at: datetime = Field(..., description="创建时间")
    reviewed_by: Optional[int] = Field(None, description="审核人ID")
    reviewed_at: Optional[datetime] = Field(None, description="审核时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


class RequirementChangeBatchListResponse(BaseModel):
    """变更批次列表响应"""
    items: List[RequirementChangeBatchResponse] = Field(default_factory=list, description="批次列表")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=10, description="每页数量")
    total_pages: int = Field(default=0, description="总页数")


class TestCaseStatusUpdateRequest(BaseModel):
    """测试用例状态更新请求"""
    test_case_ids: List[int] = Field(..., description="测试用例ID列表")
    new_status: str = Field(..., description="新状态")
    reason: Optional[str] = Field(None, description="状态变更原因")


class TestCaseCompareResponse(BaseModel):
    """测试用例对比响应"""
    old_test_case: Optional[Dict[str, Any]] = Field(None, description="旧测试用例详情")
    new_test_case_preview: Optional[Dict[str, Any]] = Field(None, description="新测试用例预览")
    changes: List[str] = Field(default_factory=list, description="变更点列表")
    recommendation: str = Field(..., description="处理建议")