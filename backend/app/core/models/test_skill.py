"""
SKILL管理模块 - 数据库模型
对应需求文档 3.16 SKILL管理模块
"""

from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, 
    ForeignKey, Integer, Enum, JSON, Boolean, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SkillType(str, enum.Enum):
    """SKILL类型"""
    FUNCTIONAL = "functional"      # 功能测试
    API = "api"                    # API测试
    UI = "ui"                      # UI测试
    PERFORMANCE = "performance"    # 性能测试
    SECURITY = "security"          # 安全测试


class SkillStatus(str, enum.Enum):
    """SKILL状态"""
    ACTIVE = "active"              # 已启用
    DRAFT = "draft"                # 草稿
    DEPRECATED = "deprecated"      # 已弃用


class TestSkill(Base):
    """SKILL模板表"""
    __tablename__ = 'test_skills'
    
    id = Column(
        BigInteger, 
        primary_key=True, 
        autoincrement=True,
        comment='主键ID'
    )
    
    # 基本信息
    name = Column(
        String(100), 
        nullable=False, 
        comment='SKILL名称'
    )
    code = Column(
        String(50), 
        nullable=False, 
        unique=True,
        comment='SKILL编码'
    )
    description = Column(
        Text,
        comment='SKILL描述'
    )
    skill_type = Column(
        Enum(SkillType), 
        nullable=False,
        comment='SKILL类型: functional/api/ui/performance/security'
    )
    tags = Column(
        JSON,
        comment='标签列表'
    )
    
    # 版本控制
    version = Column(
        String(20), 
        nullable=False, 
        default='1.0.0',
        comment='SKILL版本号'
    )
    is_latest = Column(
        Boolean, 
        default=True,
        comment='是否最新版本'
    )
    parent_skill_id = Column(
        BigInteger, 
        ForeignKey('test_skills.id', ondelete='SET NULL'),
        nullable=True,
        comment='父SKILL ID（用于版本继承）'
    )
    
    # 归属信息
    project_id = Column(
        BigInteger, 
        ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=True,
        comment='所属项目（NULL表示全局SKILL）'
    )
    is_global = Column(
        Boolean, 
        default=False,
        comment='是否全局SKILL'
    )
    is_default = Column(
        Boolean, 
        default=False,
        comment='是否为项目默认SKILL'
    )
    
    # SKILL内容（JSON格式）
    content = Column(
        JSON, 
        nullable=False,
        comment='SKILL完整内容，包含role/input/output/methods/examples等'
    )
    
    # 统计信息
    usage_count = Column(
        Integer, 
        default=0,
        comment='使用次数'
    )
    generation_count = Column(
        Integer, 
        default=0,
        comment='生成次数'
    )
    avg_quality_score = Column(
        Integer,
        comment='平均质量评分(1-100)'
    )
    
    # 状态
    status = Column(
        Enum(SkillStatus), 
        default=SkillStatus.ACTIVE,
        comment='状态: active/draft/deprecated'
    )
    
    # 创建信息
    created_by = Column(
        String(36),
        comment='创建人ID'
    )
    created_at = Column(
        DateTime,
        server_default=func.now(),
        comment='创建时间'
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment='更新时间'
    )
    
    # 关系
    project = relationship(
        'Project',
        backref='skills'
    )
    parent_skill = relationship(
        'TestSkill',
        remote_side=[id],
        backref='child_skills'
    )
    examples = relationship(
        'SkillExample',
        back_populates='skill',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_skill_code', 'code'),
        Index('idx_skill_type', 'skill_type'),
        Index('idx_skill_project', 'project_id'),
        Index('idx_skill_status', 'status'),
        Index('idx_skill_is_global', 'is_global'),
        Index('idx_skill_is_default', 'is_default'),
        {'comment': 'SKILL模板表'}
    )


class SkillExample(Base):
    """SKILL示例库表"""
    __tablename__ = 'skill_examples'
    
    id = Column(
        BigInteger, 
        primary_key=True, 
        autoincrement=True,
        comment='主键ID'
    )
    
    skill_id = Column(
        BigInteger, 
        ForeignKey('test_skills.id', ondelete='CASCADE'),
        nullable=False,
        comment='所属SKILL ID'
    )
    
    name = Column(
        String(200),
        comment='示例名称'
    )
    description = Column(
        Text,
        comment='示例描述'
    )
    
    # 输入输出示例
    input_example = Column(
        Text, 
        nullable=False,
        comment='输入示例'
    )
    output_example = Column(
        JSON, 
        nullable=False,
        comment='输出示例（JSON格式）'
    )
    
    # 状态
    is_active = Column(
        Boolean, 
        default=True,
        comment='是否启用'
    )
    sort_order = Column(
        Integer, 
        default=0,
        comment='排序'
    )
    
    # 创建信息
    created_by = Column(
        String(36),
        comment='创建人ID'
    )
    created_at = Column(
        DateTime,
        server_default=func.now(),
        comment='创建时间'
    )
    
    # 关系
    skill = relationship(
        'TestSkill',
        back_populates='examples'
    )
    
    __table_args__ = (
        Index('idx_example_skill', 'skill_id'),
        Index('idx_example_is_active', 'is_active'),
        {'comment': 'SKILL示例库表'}
    )


class SkillUsageLog(Base):
    """SKILL使用记录表"""
    __tablename__ = 'skill_usage_logs'
    
    id = Column(
        BigInteger, 
        primary_key=True, 
        autoincrement=True,
        comment='主键ID'
    )
    
    skill_id = Column(
        BigInteger, 
        ForeignKey('test_skills.id', ondelete='CASCADE'),
        nullable=False,
        comment='使用的SKILL ID'
    )
    version_id = Column(
        BigInteger, 
        ForeignKey('versions.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的版本ID'
    )
    project_id = Column(
        BigInteger, 
        ForeignKey('projects.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的项目ID'
    )
    
    # 生成信息
    input_tokens = Column(
        Integer,
        comment='输入Token数'
    )
    output_tokens = Column(
        Integer,
        comment='输出Token数'
    )
    generation_time_ms = Column(
        Integer,
        comment='生成耗时(毫秒)'
    )
    generated_count = Column(
        Integer,
        comment='生成用例数'
    )
    
    # 质量评估
    quality_score = Column(
        Integer,
        comment='质量评分(1-100)'
    )
    completeness_score = Column(
        Integer,
        comment='完整性评分(1-100)'
    )
    accuracy_score = Column(
        Integer,
        comment='准确性评分(1-100)'
    )
    readability_score = Column(
        Integer,
        comment='可读性评分(1-100)'
    )
    
    # 用户反馈
    user_feedback = Column(
        Text,
        comment='用户反馈'
    )
    user_rating = Column(
        Integer,
        comment='用户评分(1-5)'
    )
    
    # 创建信息
    created_by = Column(
        BigInteger,
        comment='使用人ID'
    )
    created_at = Column(
        DateTime,
        server_default=func.now(),
        comment='使用时间'
    )
    
    # 关系
    skill = relationship(
        'TestSkill',
        backref='usage_logs'
    )
    
    __table_args__ = (
        Index('idx_usage_skill', 'skill_id'),
        Index('idx_usage_version', 'version_id'),
        Index('idx_usage_project', 'project_id'),
        Index('idx_usage_created', 'created_at'),
        {'comment': 'SKILL使用记录表'}
    )
