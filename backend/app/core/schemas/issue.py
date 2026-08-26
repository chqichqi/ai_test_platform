"""
问题跟踪和AI失败分析Schema
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class IssueCreate(BaseModel):
    project_id: int = Field(..., description="项目ID")
    version_id: Optional[int] = None
    execution_id: Optional[int] = None
    case_id: Optional[int] = None
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    severity: str = Field(default="medium")
    priority: str = Field(default="P2")
    failure_type: Optional[str] = None
    tags: Optional[List[str]] = None
    assignee_id: Optional[int] = None


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    tags: Optional[List[str]] = None
    resolution_note: Optional[str] = None


class IssueResponse(BaseModel):
    id: int
    project_id: int
    version_id: Optional[int]
    execution_id: Optional[int]
    case_id: Optional[int]
    title: str
    description: Optional[str]
    severity: str
    priority: str
    status: str
    failure_type: Optional[str]
    root_cause: Optional[str]
    ai_analysis: Optional[str]
    ai_suggestion: Optional[str]
    ai_confidence: Optional[int]
    assignee_id: Optional[int]
    reporter_id: Optional[int]
    resolved_at: Optional[datetime]
    resolved_by: Optional[int]
    resolution_note: Optional[str]
    tags: Optional[List[str]]
    affected_cases: Optional[List[int]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IssueListResponse(BaseModel):
    items: List[IssueResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AnalyzeFailureRequest(BaseModel):
    execution_id: int = Field(..., description="执行ID")
    case_id: Optional[int] = None
    project_id: int = Field(..., description="项目ID")
    failure_message: Optional[str] = None
    stack_trace: Optional[str] = None
    screenshot_base64: Optional[str] = None
    dom_snapshot: Optional[str] = None
    console_logs: Optional[List[dict]] = None
    network_logs: Optional[List[dict]] = None


class FailureAnalysisResponse(BaseModel):
    id: int
    execution_id: int
    case_id: Optional[int]
    failure_type: Optional[str]
    failure_message: Optional[str]
    root_cause: Optional[str]
    ai_analysis: Optional[str]
    confidence: Optional[int]
    suggested_fix: Optional[str]
    auto_fix_available: bool
    affected_locators: Optional[List[dict]]
    affected_cases: Optional[List[dict]]
    created_at: datetime
    similar_issues: Optional[List[Dict[str, Any]]] = None
    severity_recommendation: Optional[str] = None
    priority_recommendation: Optional[str] = None

    class Config:
        from_attributes = True


class CreateIssueFromAnalysisRequest(BaseModel):
    analysis_id: int = Field(..., description="分析记录ID")
    additional_description: Optional[str] = None


class IssueCommentCreate(BaseModel):
    issue_id: int
    content: str
    is_internal: bool = False
    parent_id: Optional[int] = None


class IssueCommentResponse(BaseModel):
    id: int
    issue_id: int
    content: str
    author_id: Optional[int]
    is_internal: bool
    parent_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class IssueStatsResponse(BaseModel):
    total: int
    open: int
    in_progress: int
    resolved: int
    closed: int
    by_severity: Dict[str, int]
    by_priority: Dict[str, int]
    by_failure_type: Dict[str, int]


class SimilarIssuesResponse(BaseModel):
    issues: List[IssueResponse]
    similarity_scores: List[float]


class BatchUpdateStatusRequest(BaseModel):
    issue_ids: List[int]
    status: str
    resolution_note: Optional[str] = None


class AssignIssuesRequest(BaseModel):
    issue_ids: List[int]
    assignee_id: int