"""
知识图谱相关Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class KnowledgeGraphGenerateRequest(BaseModel):
    """知识图谱生成请求"""
    version_id: Optional[int] = Field(None, description="版本ID（项目级图谱，可空）")
    project_id: int = Field(..., description="项目ID")
    mode: str = Field(default="existing",
                      description="生成模式：existing=基于已有探索结果合成（默认，零爬取）/ crawl=全站深度爬取")
    base_url: str = Field(default="", description="项目基础URL（crawl 模式必填）")
    login_username: str = Field(default="", description="登录用户名（crawl 模式必填）")
    login_password: str = Field(default="", description="登录密码（crawl 模式必填）")
    exploration_strategy: str = Field(default="normal", description="探索策略：quick/normal/deep")
    skip_tenant: bool = Field(default=True, description="是否跳过租户机构")


class KnowledgeGraphResponse(BaseModel):
    """知识图谱响应"""
    id: int
    project_id: int
    version_id: Optional[int] = None  # 最近更新来源版本（项目唯一，可空）
    graph_name: str
    base_url: str
    exploration_strategy: str
    exploration_status: str
    progress_percentage: int
    current_page: Optional[str]
    page_count: int
    menu_count: int
    element_count: int
    confidence_score: float
    error_message: Optional[str] = None  # 失败原因（failed 状态时前端展示）
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class KnowledgeGraphDetailResponse(BaseModel):
    """知识图谱详细响应（包含所有数据）"""
    id: int
    project_id: int
    version_id: Optional[int] = None  # 最近更新来源版本（项目唯一，可空）
    graph_name: str
    base_url: str
    exploration_strategy: str
    exploration_status: str
    progress_percentage: int
    current_page: Optional[str]
    error_message: Optional[str]
    
    # 爬取数据
    pages: List[Dict[str, Any]]
    menus: List[Dict[str, Any]]
    elements: List[Dict[str, Any]]
    forms: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    flows: List[Dict[str, Any]]
    api_calls: List[Dict[str, Any]]
    dependencies: List[Dict[str, Any]]
    dropdowns: Dict[str, Any] = {}
    modals: List[Dict[str, Any]] = []
    # 逐页快照（可视化下钻：页面 → 元素归属；元素 JSON 列无页面归属信息）
    snapshots: List[Dict[str, Any]] = []
    
    # 统计信息
    page_count: int
    menu_count: int
    element_count: int
    flow_count: int
    api_count: int
    
    # 质量评估
    confidence_score: float
    locator_validation_rate: float
    
    # 时间信息
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class KnowledgeGraphProgressResponse(BaseModel):
    """知识图谱进度响应"""
    graph_id: int
    exploration_status: str
    progress_percentage: int
    current_page: Optional[str]
    error_message: Optional[str]
    page_count: int
    menu_count: int
    element_count: int
    
    class Config:
        from_attributes = True


class PageSnapshotResponse(BaseModel):
    """页面快照响应"""
    id: int
    graph_id: int
    page_url: str
    page_title: str
    page_name: str
    menu_level: int
    parent_menu: Optional[str]
    element_count: int
    visited_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ElementLocatorResponse(BaseModel):
    """元素定位器响应"""
    id: int
    element_name: str
    element_type: str
    element_text: Optional[str]
    locators: Dict[str, Optional[str]]
    primary_locator: Dict[str, str]
    is_validated: bool
    validation_success: bool
    
    class Config:
        from_attributes = True


class KnowledgeGraphStatsResponse(BaseModel):
    """知识图谱统计响应"""
    total_graphs: int
    completed_graphs: int
    running_graphs: int
    failed_graphs: int
    total_pages: int
    total_elements: int
    total_apis: int