# -*- coding: utf-8 -*-
"""
生成任务模型 - 用于异步生成测试用例
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, ForeignKey,
    Enum as SQLEnum, JSON, Integer, Float
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"      # 待处理
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


class TaskType(str, Enum):
    """任务类型"""
    TEST_CASE_GENERATION = "test_case_generation"  # 测试用例生成
    XMIND_GENERATION = "xmind_generation"          # XMind生成
    API_TEST_GENERATION = "api_test_generation"    # API测试生成


class GenerationTask(Base):
    """生成任务模型"""
    
    __tablename__ = 'generation_tasks'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='任务ID'
    )
    task_type = Column(
        SQLEnum(TaskType),
        nullable=False,
        default=TaskType.TEST_CASE_GENERATION,
        comment='任务类型'
    )
    status = Column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        comment='任务状态'
    )
    
    project_id = Column(
        BigInteger,
        ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False,
        comment='项目ID'
    )
    version_id = Column(
        BigInteger,
        ForeignKey('versions.id', ondelete='CASCADE'),
        nullable=False,
        comment='版本ID'
    )
    
    progress = Column(
        Integer,
        default=0,
        comment='进度百分比(0-100)'
    )
    current_step = Column(
        String(200),
        nullable=True,
        comment='当前步骤描述'
    )
    total_batches = Column(
        Integer,
        default=0,
        comment='总批次数'
    )
    current_batch = Column(
        Integer,
        default=0,
        comment='当前批次数'
    )
    
    input_data = Column(
        JSON,
        nullable=True,
        comment='输入参数(JSON格式)'
    )
    result_data = Column(
        JSON,
        nullable=True,
        comment='生成结果(JSON格式)'
    )
    error_message = Column(
        Text,
        nullable=True,
        comment='错误信息'
    )
    
    started_at = Column(
        DateTime,
        nullable=True,
        comment='开始时间'
    )
    completed_at = Column(
        DateTime,
        nullable=True,
        comment='完成时间'
    )
    duration_seconds = Column(
        Float,
        nullable=True,
        comment='执行时长(秒)'
    )
    
    generated_count = Column(
        Integer,
        default=0,
        comment='已生成数量'
    )
    
    created_by = Column(
        String(36),
        ForeignKey('user.id', ondelete='SET NULL'),
        nullable=True,
        comment='创建人ID'
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        comment='创建时间'
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment='更新时间'
    )
    
    project = relationship("Project", backref="generation_tasks")
    version = relationship("Version", backref="generation_tasks")
    creator = relationship("User", backref="generation_tasks")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        # 生成显示ID：时间戳(YYMMDDHHMMSS) + ID
        display_id = self.id
        if self.created_at:
            timestamp = self.created_at.strftime("%y%m%d%H%M%S")
            display_id = f"{timestamp}{self.id}"
        
        return {
            "id": self.id,
            "display_id": display_id,
            "task_type": self.task_type.value if self.task_type else None,
            "status": self.status.value if self.status else None,
            "project_id": self.project_id,
            "version_id": self.version_id,
            "progress": self.progress,
            "current_step": self.current_step,
            "total_batches": self.total_batches,
            "current_batch": self.current_batch,
            "generated_count": self.generated_count,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }