"""
文档相关数据模型
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.models.base import BaseModel


class Document(BaseModel):
    """文档模型"""
    __tablename__ = "document"
    
    # 基本信息
    title = Column(String(255), nullable=False, comment="文档标题")
    description = Column(Text, nullable=True, comment="文档描述")
    file_path = Column(String(500), nullable=False, comment="文件存储路径")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_size = Column(Integer, nullable=False, comment="文件大小（字节）")
    file_type = Column(String(50), nullable=False, comment="文件类型")
    
    # 处理状态
    status = Column(String(50), default="uploaded", comment="处理状态：uploaded, processing, processed, error")
    processing_progress = Column(Integer, default=0, comment="处理进度（0-100）")
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    # 向量化信息
    is_vectorized = Column(Boolean, default=False, comment="是否已向量化")
    vectorized_at = Column(DateTime, nullable=True, comment="向量化时间")
    embedding_model = Column(String(100), nullable=True, comment="使用的嵌入模型")
    processed_chunks = Column(Integer, default=0, comment="已处理的块数量")
    
    # 元数据
    doc_metadata = Column("metadata", JSON, default=dict, comment="文档元数据")
    
    # 关联关系
    user_id = Column(String(36), ForeignKey("user.id"), nullable=False, comment="上传用户ID")
    # user = relationship("User", back_populates="documents")
    
    # 分块
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Document(id={self.id}, title='{self.title}', status='{self.status}')>"


class DocumentChunk(BaseModel):
    """文档分块模型"""
    __tablename__ = "document_chunk"
    
    # 分块信息
    document_id = Column(String(36), ForeignKey("document.id"), nullable=False, comment="文档ID")
    chunk_index = Column(Integer, nullable=False, comment="分块索引")
    chunk_text = Column(Text, nullable=False, comment="分块文本内容")
    chunk_size = Column(Integer, nullable=False, comment="分块大小（字符数）")
    
    # 向量化信息
    embedding = Column(JSON, nullable=True, comment="向量嵌入")
    is_embedded = Column(Boolean, default=False, comment="是否已生成嵌入")
    
    # 元数据
    chunk_metadata = Column("metadata", JSON, default=dict, comment="分块元数据")
    
    # 关联关系
    document = relationship("Document", back_populates="chunks")
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index})>"