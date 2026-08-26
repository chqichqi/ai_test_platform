# -*- coding: utf-8 -*-
"""
项目与版本管理模型 - MySQL版本
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, ForeignKey,
    Index, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.config import settings


class ProjectStatus(str, Enum):
    """项目状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionStatus(str, Enum):
    """版本状态"""
    PLANNING = "planning"
    DEVELOPING = "developing"
    TESTING = "testing"
    FROZEN = "frozen"      # 新增：已冻结（测试完成，准备发布）
    RELEASED = "released"
    ARCHIVED = "archived"


class Project(Base):
    """项目模型 - 对应需求文档 3.1.1"""
    
    __tablename__ = 'projects'
    
    id = Column(
        BigInteger, 
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    name = Column(
        String(100), 
        nullable=False,
        comment='项目名称'
    )
    code = Column(
        String(50), 
        unique=True, 
        nullable=False,
        comment='项目编码'
    )
    description = Column(
        Text,
        comment='项目描述'
    )
    # 项目类型字段
    project_type = Column(
        String(20),
        default='web',
        comment='项目类型: web/app'
    )
    app_platform = Column(
        String(20),
        nullable=True,
        comment='APP平台: android/ios'
    )
    app_package_name = Column(
        String(200),
        nullable=True,
        comment='Android: APP包名 (appPackage)'
    )
    app_launch_activity = Column(
        String(500),
        nullable=True,
        comment='Android: 启动Activity (appActivity)'
    )
    app_bundle_id = Column(
        String(200),
        nullable=True,
        comment='iOS: Bundle ID'
    )
    app_device_type = Column(
        String(20),
        nullable=True,
        comment='iOS: 设备类型 simulator/real'
    )
    app_device_udid = Column(
        String(100),
        nullable=True,
        comment='iOS: 真机UDID'
    )
    app_simulator_name = Column(
        String(100),
        nullable=True,
        comment='iOS: 模拟器名称'
    )
    app_automation_name = Column(
        String(50),
        nullable=True,
        comment='自动化引擎: UiAutomator2/XCUITest/Espresso'
    )
    owner_id = Column(
        String(36),
        ForeignKey('user.id', ondelete='SET NULL'),
        comment='负责人ID'
    )
    status = Column(
        String(20),
        default=ProjectStatus.ACTIVE.value,
        comment='状态: active/archived'
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
    deleted_at = Column(
        DateTime,
        nullable=True,
        comment='软删除时间'
    )
    
    owner = relationship(
        'User',
        back_populates='owned_projects',
        foreign_keys=[owner_id],
        lazy='selectin'
    )
    
    versions = relationship(
        'Version',
        back_populates='project',
        lazy='dynamic',
        order_by='Version.created_at.desc()'
    )
    
    git_repositories = relationship(
        'GitRepository',
        back_populates='project',
        lazy='dynamic'
    )
    
    test_cases = relationship(
        'TestCase',
        back_populates='project',
        lazy='dynamic'
    )
    
    # 新增关联关系
    members = relationship(
        'ProjectMember',
        back_populates='project',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    environments = relationship(
        'ProjectEnvironment',
        back_populates='project',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    settings = relationship(
        'ProjectSetting',
        back_populates='project',
        lazy='selectin',
        uselist=False,
        cascade='all, delete-orphan'
    )
    
    knowledge_graphs = relationship(
        'KnowledgeGraph',
        back_populates='project',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_projects_code', 'code'),
        Index('idx_projects_owner_id', 'owner_id'),
        Index('idx_projects_status', 'status'),
        Index('idx_projects_deleted_at', 'deleted_at'),
        {'comment': '项目表'}
    )
    
    def soft_delete(self):
        """软删除项目"""
        self.deleted_at = datetime.utcnow()
        self.status = ProjectStatus.ARCHIVED.value
    
    def restore(self):
        """恢复已删除的项目"""
        self.deleted_at = None
        self.status = ProjectStatus.ACTIVE.value
    
    def is_deleted(self) -> bool:
        """检查是否已删除"""
        return self.deleted_at is not None
    
    def to_dict(self, exclude: Optional[List[str]] = None):
        """转换为字典"""
        exclude = exclude or []
        result = {}
        
        for column in self.__table__.columns:
            col_name = column.name
            if col_name in exclude:
                continue
            value = getattr(self, col_name)
            if isinstance(value, datetime):
                value = value.isoformat() if value else None
            result[col_name] = value
        
        if 'owner' not in exclude and self.owner:
            result['owner'] = {
                'id': str(self.owner.id),
                'username': self.owner.username,
                'full_name': self.owner.full_name,
                'email': self.owner.email
            }
        
        return result


class Version(Base):
    """版本模型 - 对应需求文档 3.1.2"""
    
    __tablename__ = 'versions'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    project_id = Column(
        BigInteger,
        ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False,
        comment='项目ID'
    )
    version_number = Column(
        String(50),
        nullable=False,
        comment='版本号'
    )
    version_name = Column(
        String(100),
        comment='版本名称'
    )
    description = Column(
        Text,
        comment='版本描述'
    )
    requirement_doc = Column(
        Text,
        comment='需求文档内容'
    )
    requirement_doc_url = Column(
        String(500),
        comment='需求文档URL'
    )
    requirement_doc_file = Column(
        String(500),
        comment='需求文档文件路径'
    )
    requirement_doc_file_type = Column(
        String(20),
        comment='需求文档文件类型(docx/pdf/md/txt)'
    )
    status = Column(
        String(20),
        default=VersionStatus.PLANNING.value,
        comment='状态: planning/developing/testing/released/archived'
    )
    plan_start_date = Column(
        DateTime,
        comment='计划开始日期'
    )
    plan_end_date = Column(
        DateTime,
        comment='计划结束日期'
    )
    actual_start_date = Column(
        DateTime,
        comment='实际开始日期'
    )
    actual_end_date = Column(
        DateTime,
        comment='实际结束日期'
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
    
    project = relationship(
        'Project',
        back_populates='versions',
        lazy='selectin'
    )
    
    requirement_documents = relationship(
        'RequirementDocument',
        back_populates='version',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    test_cases = relationship(
        'TestCase',
        back_populates='version',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    test_points = relationship(
        'TestPoint',
        back_populates='version',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    # 新增关联关系
    doc_history = relationship(
        'VersionDocHistory',
        back_populates='version',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    knowledge_graphs = relationship(
        'KnowledgeGraph',
        back_populates='version',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        Index('idx_versions_project_id', 'project_id'),
        Index('idx_versions_status', 'status'),
        Index('idx_versions_version_number', 'version_number'),
        {'comment': '版本表'}
    )
    
    VALID_STATUS_TRANSITIONS = {
        VersionStatus.PLANNING: [VersionStatus.DEVELOPING, VersionStatus.ARCHIVED],
        VersionStatus.DEVELOPING: [VersionStatus.TESTING, VersionStatus.PLANNING],
        VersionStatus.TESTING: [VersionStatus.FROZEN, VersionStatus.DEVELOPING],
        VersionStatus.FROZEN: [VersionStatus.RELEASED, VersionStatus.TESTING],
        VersionStatus.RELEASED: [VersionStatus.ARCHIVED],
        VersionStatus.ARCHIVED: [],
    }
    
    def can_transition_to(self, new_status: VersionStatus) -> bool:
        """检查是否可以转换到新状态"""
        current = VersionStatus(self.status)
        return new_status in self.VALID_STATUS_TRANSITIONS.get(current, [])
    
    def transition_to(self, new_status: VersionStatus) -> bool:
        """转换状态"""
        if self.can_transition_to(new_status):
            self.status = new_status.value
            
            if new_status == VersionStatus.DEVELOPING and not self.actual_start_date:
                self.actual_start_date = datetime.utcnow()
            elif new_status == VersionStatus.FROZEN:
                # 冻结时设置冻结时间
                pass
            elif new_status == VersionStatus.RELEASED and not self.actual_end_date:
                self.actual_end_date = datetime.utcnow()
            
            return True
        return False
    
    def get_status_display(self) -> str:
        """获取状态显示名称"""
        status_names = {
            VersionStatus.PLANNING: '规划中',
            VersionStatus.DEVELOPING: '开发中',
            VersionStatus.TESTING: '测试中',
            VersionStatus.FROZEN: '已冻结',
            VersionStatus.RELEASED: '已发布',
            VersionStatus.ARCHIVED: '已归档',
        }
        try:
            # 尝试匹配枚举值
            for enum_val, display in status_names.items():
                if enum_val.value == self.status:
                    return display
            return self.status
        except Exception:
            return self.status
    
    def to_dict(self, exclude: Optional[List[str]] = None):
        """转换为字典"""
        exclude = exclude or []
        result = {}
        
        for column in self.__table__.columns:
            col_name = column.name
            if col_name in exclude:
                continue
            value = getattr(self, col_name)
            if isinstance(value, datetime):
                value = value.isoformat() if value else None
            result[col_name] = value
        
        if 'project' not in exclude and self.project:
            result['project'] = {
                'id': self.project.id,
                'name': self.project.name,
                'code': self.project.code
            }
        
        result['status_display'] = self.get_status_display()
        
        return result