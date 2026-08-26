"""
知识管理模块 - 数据库模型
包含RAG知识库和知识图谱
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class KnowledgeBaseStatus(str, enum.Enum):
    """知识库状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROCESSING = "processing"


class GraphStatus(str, enum.Enum):
    """知识图谱状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentStatus(str, enum.Enum):
    """文档状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class RagKnowledgeBaseModel(Base):
    """
    RAG知识库表
    """
    __tablename__ = "rag_knowledge_bases_new"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True, comment="知识库名称")
    description = Column(Text, nullable=True, comment="知识库描述")
    project = Column(String(255), nullable=False, default="", comment="项目标识")
    version = Column(String(50), nullable=False, default="v1.0.0", comment="版本")
    
    document_count = Column(Integer, nullable=False, default=0, comment="文档数量")
    chunk_count = Column(Integer, nullable=False, default=0, comment="分块数量")
    
    status = Column(String(50), nullable=False, default="inactive", comment="状态: active, inactive, processing")
    has_graph = Column(Boolean, nullable=False, default=False, comment="是否已生成图谱")
    
    chunk_size = Column(Integer, nullable=True, default=500, comment="分块大小")
    chunk_method = Column(String(50), nullable=True, default="auto", comment="分块方式")
    embedding_model = Column(String(100), nullable=True, default="text-embedding-3-small", comment="Embedding模型")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True, comment="软删除时间")
    
    created_by_id = Column(String(36), ForeignKey("user.id"), nullable=True, comment="创建用户ID")
    created_by = relationship("User", foreign_keys=[created_by_id])
    
    documents = relationship("RagDocumentModel", back_populates="knowledge_base", cascade="all, delete-orphan")
    graph = relationship("KnowledgeGraphModel", back_populates="knowledge_base", uselist=False, cascade="all, delete-orphan")


class RagDocumentModel(Base):
    """
    RAG文档表
    """
    __tablename__ = "rag_documents_new"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("rag_knowledge_bases_new.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False, comment="文档名称")
    type = Column(String(50), nullable=False, comment="文档类型: PDF, DOC, DOCX, TXT, MD")
    size = Column(String(50), nullable=False, comment="文档大小")
    content = Column(Text, nullable=True, comment="文档内容")
    
    status = Column(String(50), nullable=False, default="pending", comment="状态: pending, processing, processed, failed")
    chunk_count = Column(Integer, nullable=False, default=0, comment="分块数量")
    
    file_path = Column(String(500), nullable=True, comment="文件存储路径")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    knowledge_base = relationship("RagKnowledgeBaseModel", back_populates="documents")
    chunks = relationship("RagChunkModel", back_populates="document", cascade="all, delete-orphan")


class RagChunkModel(Base):
    """
    文档分块表
    """
    __tablename__ = "rag_chunks_new"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("rag_documents_new.id", ondelete="CASCADE"), nullable=False, index=True)
    
    chunk_index = Column(Integer, nullable=False, comment="分块索引")
    content = Column(Text, nullable=False, comment="分块内容")
    
    embedding = Column(JSON, nullable=True, comment="向量嵌入")
    embedding_model = Column(String(100), nullable=True, comment="嵌入模型")
    
    chunk_metadata = Column(JSON, nullable=True, comment="元数据")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    document = relationship("RagDocumentModel", back_populates="chunks")


class KnowledgeGraphModel(Base):
    """
    知识图谱表
    """
    __tablename__ = "knowledge_graphs"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("rag_knowledge_bases_new.id", ondelete="CASCADE"), nullable=True, index=True)
    
    name = Column(String(255), nullable=False, index=True, comment="图谱名称")
    source_rag = Column(String(255), nullable=False, comment="来源RAG库名称")
    
    entity_count = Column(Integer, nullable=False, default=0, comment="实体数量")
    relation_count = Column(Integer, nullable=False, default=0, comment="关系数量")
    triple_count = Column(Integer, nullable=False, default=0, comment="三元组数量")
    
    status = Column(String(50), nullable=False, default="pending", comment="状态: pending, processing, completed, failed")
    progress = Column(Integer, nullable=False, default=0, comment="生成进度 0-100")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    knowledge_base = relationship("RagKnowledgeBaseModel", back_populates="graph")
    entities = relationship("GraphEntityModel", back_populates="graph", cascade="all, delete-orphan")
    relations = relationship("GraphRelationModel", back_populates="graph", cascade="all, delete-orphan")


class GraphEntityModel(Base):
    """
    图谱实体表
    """
    __tablename__ = "graph_entities"

    id = Column(Integer, primary_key=True, index=True)
    graph_id = Column(Integer, ForeignKey("knowledge_graphs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False, comment="实体名称")
    type = Column(String(100), nullable=False, comment="实体类型")
    description = Column(Text, nullable=True, comment="实体描述")
    color = Column(String(50), nullable=True, comment="显示颜色")
    
    properties = Column(JSON, nullable=True, comment="实体属性")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    graph = relationship("KnowledgeGraphModel", back_populates="entities")


class GraphRelationModel(Base):
    """
    图谱关系表
    """
    __tablename__ = "graph_relations"

    id = Column(Integer, primary_key=True, index=True)
    graph_id = Column(Integer, ForeignKey("knowledge_graphs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    source_id = Column(Integer, ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    relation = Column(String(255), nullable=False, comment="关系名称")
    properties = Column(JSON, nullable=True, comment="关系属性")
    
    weight = Column(Float, nullable=True, default=1.0, comment="关系权重")
    
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    graph = relationship("KnowledgeGraphModel", back_populates="relations")
    source = relationship("GraphEntityModel", foreign_keys=[source_id])
    target = relationship("GraphEntityModel", foreign_keys=[target_id])