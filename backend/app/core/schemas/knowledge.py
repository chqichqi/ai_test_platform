"""
知识管理模块 - Pydantic Schemas
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class RagKnowledgeBaseCreate(BaseModel):
    """创建RAG知识库请求"""
    name: str = Field(..., min_length=1, max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, description="知识库描述")
    chunk_size: Optional[int] = Field(500, ge=100, le=2000, description="分块大小")
    chunk_method: Optional[str] = Field("auto", description="分块方式")
    embedding_model: Optional[str] = Field("text-embedding-3-small", description="Embedding模型")


class RagKnowledgeBaseUpdate(BaseModel):
    """更新RAG知识库请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None


class RagDocumentCreate(BaseModel):
    """创建文档请求"""
    name: str
    type: str
    size: str
    content: Optional[str] = None
    file_path: Optional[str] = None


class RagKnowledgeBaseResponse(BaseModel):
    """RAG知识库响应"""
    id: int
    name: str
    description: Optional[str]
    project: str
    version: str
    document_count: int
    chunk_count: int
    status: str
    has_graph: bool
    chunk_size: Optional[int]
    chunk_method: Optional[str]
    embedding_model: Optional[str]
    created_at: datetime
    updated_at: datetime
    documents: Optional[List['RagDocumentResponse']] = None

    class Config:
        from_attributes = True


class RagDocumentResponse(BaseModel):
    """文档响应"""
    id: int
    name: str
    type: str
    size: str
    content: Optional[str]
    status: str
    chunk_count: int
    file_path: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeGraphCreate(BaseModel):
    """创建知识图谱请求"""
    name: str = Field(..., min_length=1, max_length=255)
    knowledge_base_id: int


class KnowledgeGraphResponse(BaseModel):
    """知识图谱响应"""
    id: int
    name: str
    source_rag: str
    entity_count: int
    relation_count: int
    triple_count: int
    status: str
    progress: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GraphEntityResponse(BaseModel):
    """图谱实体响应"""
    id: int
    name: str
    type: str
    description: Optional[str]
    color: Optional[str]

    class Config:
        from_attributes = True


class GraphRelationResponse(BaseModel):
    """图谱关系响应"""
    id: int
    source_id: int
    target_id: int
    relation: str
    weight: Optional[float]

    class Config:
        from_attributes = True


class KnowledgeGraphDetailResponse(BaseModel):
    """知识图谱详情响应（包含实体和关系）"""
    id: int
    name: str
    source_rag: str
    entity_count: int
    relation_count: int
    triple_count: int
    status: str
    progress: int
    created_at: datetime
    updated_at: datetime
    nodes: List[GraphEntityResponse]
    edges: List[Dict[str, Any]]

    class Config:
        from_attributes = True


class KnowledgeStatisticsResponse(BaseModel):
    """知识库统计响应"""
    total_knowledge_bases: int
    total_documents: int
    total_chunks: int
    graph_coverage_rate: float


RagKnowledgeBaseResponse.model_rebuild()