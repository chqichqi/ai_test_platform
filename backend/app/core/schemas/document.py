"""
文档相关Pydantic模式
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# 文档模式
class DocumentBase(BaseModel):
    """文档基础模式"""
    title: str = Field(..., min_length=1, max_length=255, description="文档标题")
    description: Optional[str] = Field(None, description="文档描述")
    file_name: str = Field(..., description="原始文件名")
    file_size: int = Field(..., ge=0, description="文件大小（字节）")
    file_type: str = Field(..., description="文件类型")
    status: str = Field(default="uploaded", description="处理状态")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文档元数据")


class DocumentCreate(DocumentBase):
    """文档创建模式"""
    file_path: str = Field(..., description="文件存储路径")


class DocumentUpdate(BaseModel):
    """文档更新模式"""
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="文档标题")
    description: Optional[str] = Field(None, description="文档描述")
    status: Optional[str] = Field(None, description="处理状态")
    processing_progress: Optional[int] = Field(None, ge=0, le=100, description="处理进度")
    error_message: Optional[str] = Field(None, description="错误信息")
    is_vectorized: Optional[bool] = Field(None, description="是否已向量化")
    metadata: Optional[Dict[str, Any]] = Field(None, description="文档元数据")


class DocumentInDB(DocumentBase):
    """数据库中的文档模式"""
    id: str = Field(..., description="文档ID")
    file_path: str = Field(..., description="文件存储路径")
    user_id: str = Field(..., description="上传用户ID")
    processing_progress: int = Field(default=0, ge=0, le=100, description="处理进度")
    error_message: Optional[str] = Field(None, description="错误信息")
    is_vectorized: bool = Field(default=False, description="是否已向量化")
    vectorized_at: Optional[datetime] = Field(None, description="向量化时间")
    embedding_model: Optional[str] = Field(None, description="使用的嵌入模型")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    
    @classmethod
    def from_orm(cls, obj):
        """自定义from_orm方法处理metadata字段名冲突"""
        data = {
            "id": obj.id,
            "title": obj.title,
            "description": obj.description,
            "file_path": obj.file_path,
            "file_name": obj.file_name,
            "file_size": obj.file_size,
            "file_type": obj.file_type,
            "status": obj.status,
            "metadata": obj.doc_metadata if hasattr(obj, 'doc_metadata') else {},
            "user_id": obj.user_id,
            "processing_progress": obj.processing_progress,
            "error_message": obj.error_message,
            "is_vectorized": obj.is_vectorized,
            "vectorized_at": obj.vectorized_at,
            "embedding_model": obj.embedding_model,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "deleted_at": obj.deleted_at,
        }
        return cls(**data)


class DocumentResponse(DocumentInDB):
    """文档响应模式"""
    pass


# 文档分块模式
class DocumentChunkBase(BaseModel):
    """文档分块基础模式"""
    chunk_index: int = Field(..., ge=0, description="分块索引")
    chunk_text: str = Field(..., description="分块文本内容")
    chunk_size: int = Field(..., ge=0, description="分块大小（字符数）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="分块元数据")


class DocumentChunkCreate(DocumentChunkBase):
    """文档分块创建模式"""
    pass


class DocumentChunkInDB(DocumentChunkBase):
    """数据库中的文档分块模式"""
    id: str = Field(..., description="分块ID")
    document_id: str = Field(..., description="文档ID")
    embedding: Optional[List[float]] = Field(None, description="向量嵌入")
    is_embedded: bool = Field(default=False, description="是否已生成嵌入")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    
    @classmethod
    def from_orm(cls, obj):
        """自定义from_orm方法处理metadata字段名冲突"""
        data = {
            "id": obj.id,
            "document_id": obj.document_id,
            "chunk_index": obj.chunk_index,
            "chunk_text": obj.chunk_text,
            "chunk_size": obj.chunk_size,
            "metadata": obj.chunk_metadata if hasattr(obj, 'chunk_metadata') else {},
            "embedding": obj.embedding,
            "is_embedded": obj.is_embedded,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "deleted_at": obj.deleted_at,
        }
        return cls(**data)


class DocumentChunkResponse(DocumentChunkInDB):
    """文档分块响应模式"""
    pass


# 文档列表响应
class DocumentListResponse(BaseModel):
    """文档列表响应模式"""
    success: bool = Field(default=True, description="是否成功")
    data: List[DocumentResponse] = Field(..., description="文档列表")
    total: int = Field(..., description="总文档数")
    skip: int = Field(..., description="跳过的记录数")
    limit: int = Field(..., description="返回的最大记录数")


# 文档上传请求
class DocumentUploadRequest(BaseModel):
    """文档上传请求模式"""
    title: str = Field(..., min_length=1, max_length=255, description="文档标题")
    description: Optional[str] = Field(None, description="文档描述")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文档元数据")


# 文档处理请求
class DocumentProcessRequest(BaseModel):
    """文档处理请求模式"""
    document_id: str = Field(..., description="文档ID")


# 文档搜索请求
class DocumentSearchRequest(BaseModel):
    """文档搜索请求模式"""
    query: str = Field(..., min_length=1, description="搜索查询")
    document_id: Optional[str] = Field(None, description="文档ID（可选，用于限制搜索范围）")
    top_k: int = Field(default=5, ge=1, le=50, description="返回的最相似结果数量")


# 文档搜索结果
class DocumentSearchResult(BaseModel):
    """文档搜索结果模式"""
    id: str = Field(..., description="结果ID")
    document_id: str = Field(..., description="文档ID")
    chunk_index: int = Field(..., description="分块索引")
    content: str = Field(..., description="内容")
    score: float = Field(..., ge=0, le=1, description="相似度分数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


# 文档搜索响应
class DocumentSearchResponse(BaseModel):
    """文档搜索响应模式"""
    query: str = Field(..., description="搜索查询")
    results: List[DocumentSearchResult] = Field(default_factory=list, description="搜索结果")
    total_results: int = Field(..., description="总结果数")