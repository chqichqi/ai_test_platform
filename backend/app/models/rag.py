"""
RAG知识库管理模块 - 数据库模型
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RAGKnowledgeBase(Base):
    """
    RAG知识库表
    存储上传的需求文档和对应的向量化信息
    """
    __tablename__ = "rag_knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True, comment="知识库名称")
    description = Column(Text, nullable=True, comment="知识库描述")
    project_name = Column(String(255), nullable=False, index=True, comment="项目名称")
    version = Column(String(50), nullable=False, comment="项目版本")
    
    # 文件信息
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_path = Column(String(500), nullable=False, comment="文件存储路径")
    file_size = Column(Integer, nullable=False, comment="文件大小（字节）")
    file_type = Column(String(50), nullable=False, comment="文件类型")
    
    # 处理状态
    status = Column(String(50), nullable=False, default="pending", comment="处理状态: pending, processing, completed, failed")
    processing_progress = Column(Float, nullable=False, default=0.0, comment="处理进度 0-100")
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    # 向量化信息
    vector_store_path = Column(String(500), nullable=True, comment="向量存储路径")
    embedding_model = Column(String(100), nullable=True, comment="使用的嵌入模型")
    chunk_size = Column(Integer, nullable=True, comment="分块大小")
    chunk_overlap = Column(Integer, nullable=True, comment="分块重叠大小")
    total_chunks = Column(Integer, nullable=True, comment="总块数")
    
    # 元数据
    extra_metadata = Column("metadata", JSON, nullable=True, comment="额外元数据")
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True, comment="软删除时间")
    
    # 关系
    documents = relationship("RAGDocument", back_populates="knowledge_base", cascade="all, delete-orphan")
    created_by_id = Column(String(36), ForeignKey("user.id"), nullable=True, comment="创建用户ID")
    created_by = relationship("User", foreign_keys=[created_by_id])


class RAGDocument(Base):
    """
    RAG文档分块表
    存储文档分块和对应的向量信息
    """
    __tablename__ = "rag_documents"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("rag_knowledge_bases.id"), nullable=False, index=True)
    
    # 分块信息
    chunk_index = Column(Integer, nullable=False, comment="分块索引")
    chunk_text = Column(Text, nullable=False, comment="分块文本内容")
    chunk_hash = Column(String(64), nullable=False, index=True, comment="分块内容哈希")
    
    # 元数据
    extra_metadata = Column("metadata", JSON, nullable=True, comment="分块元数据")
    page_number = Column(Integer, nullable=True, comment="页码（如果适用）")
    section_title = Column(String(500), nullable=True, comment="章节标题")
    
    # 向量信息
    embedding = Column(JSON, nullable=True, comment="向量嵌入（JSON格式）")
    embedding_model = Column(String(100), nullable=True, comment="嵌入模型")
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # 关系
    knowledge_base = relationship("RAGKnowledgeBase", back_populates="documents")


class RAGQueryHistory(Base):
    """
    RAG查询历史表
    记录用户对知识库的查询历史
    """
    __tablename__ = "rag_query_history"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("rag_knowledge_bases.id"), nullable=False, index=True)
    
    # 查询信息
    query_text = Column(Text, nullable=False, comment="查询文本")
    query_type = Column(String(50), nullable=False, default="general", comment="查询类型: general, test_case, mind_map")
    response_text = Column(Text, nullable=True, comment="响应文本")
    
    # 检索信息
    retrieved_chunks = Column(JSON, nullable=True, comment="检索到的分块ID列表")
    similarity_scores = Column(JSON, nullable=True, comment="相似度分数")
    
    # 生成信息
    generated_content = Column(Text, nullable=True, comment="生成的内容（测试用例、思维导图等）")
    generation_model = Column(String(100), nullable=True, comment="生成模型")
    
    # 性能指标
    retrieval_time_ms = Column(Float, nullable=True, comment="检索时间（毫秒）")
    generation_time_ms = Column(Float, nullable=True, comment="生成时间（毫秒）")
    total_time_ms = Column(Float, nullable=True, comment="总时间（毫秒）")
    
    # 用户信息
    user_id = Column(String(36), ForeignKey("user.id"), nullable=True, comment="用户ID")
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # 关系
    knowledge_base = relationship("RAGKnowledgeBase")
    user = relationship("User")


class TestCaseFromRAG(Base):
    """
    从RAG生成的测试用例表
    """
    __tablename__ = "test_cases_from_rag"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("rag_knowledge_bases.id"), nullable=False, index=True)
    query_history_id = Column(Integer, ForeignKey("rag_query_history.id"), nullable=True, index=True)
    
    # 测试用例信息
    test_case_id = Column(String(100), nullable=False, unique=True, index=True, comment="测试用例ID")
    title = Column(String(500), nullable=False, comment="测试用例标题")
    description = Column(Text, nullable=True, comment="测试用例描述")
    priority = Column(String(20), nullable=False, default="medium", comment="优先级: low, medium, high, critical")
    category = Column(String(100), nullable=False, comment="测试类别")
    
    # 测试步骤
    preconditions = Column(Text, nullable=True, comment="前置条件")
    test_steps = Column(JSON, nullable=False, comment="测试步骤（JSON数组）")
    expected_results = Column(Text, nullable=False, comment="预期结果")
    
    # 状态
    status = Column(String(50), nullable=False, default="draft", comment="状态: draft, reviewed, approved, implemented")
    
    # 元数据
    tags = Column(JSON, nullable=True, comment="标签")
    requirements = Column(JSON, nullable=True, comment="关联的需求ID列表")
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # 关系
    knowledge_base = relationship("RAGKnowledgeBase")
    query_history = relationship("RAGQueryHistory")


class MindMapFromRAG(Base):
    """
    从RAG生成的思维导图表
    """
    __tablename__ = "mind_maps_from_rag"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("rag_knowledge_bases.id"), nullable=False, index=True)
    query_history_id = Column(Integer, ForeignKey("rag_query_history.id"), nullable=True, index=True)
    
    # 思维导图信息
    title = Column(String(500), nullable=False, comment="思维导图标题")
    description = Column(Text, nullable=True, comment="描述")
    
    # 导图数据
    mind_map_data = Column(JSON, nullable=False, comment="思维导图数据（JSON格式）")
    format = Column(String(50), nullable=False, default="xmind", comment="格式: xmind, freemind, markmap")
    
    # 导出文件
    export_path = Column(String(500), nullable=True, comment="导出文件路径")
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # 关系
    knowledge_base = relationship("RAGKnowledgeBase")
    query_history = relationship("RAGQueryHistory")