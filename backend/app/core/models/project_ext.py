"""
项目成员管理模型
对应需求文档 3.1.3 项目成员管理
"""

from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    Column, BigInteger, String, DateTime, ForeignKey,
    Index, JSON, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ProjectRole(str, Enum):
    """项目角色定义"""
    OWNER = "owner"           # 项目负责人 - 全部权限
    TEST_LEAD = "test_lead"   # 测试负责人 - 测试管理权限
    TESTER = "tester"         # 测试工程师 - 测试执行权限
    DEVELOPER = "developer"   # 开发工程师 - 查看和修复权限
    VIEWER = "viewer"         # 观察员 - 只读权限


class ProjectMember(Base):
    """项目成员模型"""
    
    __tablename__ = 'project_members'
    
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
    
    user_id = Column(
        String(36),
        ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
        comment='用户ID'
    )
    
    role = Column(
        String(50),
        nullable=False,
        default=ProjectRole.VIEWER.value,
        comment='角色: owner/test_lead/tester/developer/viewer'
    )
    
    # 自定义权限（覆盖默认角色权限）
    permissions = Column(
        JSON,
        comment='自定义权限: {"can_edit_case": true, "can_execute": true}'
    )
    
    joined_at = Column(
        DateTime,
        server_default=func.now(),
        comment='加入时间'
    )
    
    joined_by = Column(
        String(36),
        ForeignKey('user.id', ondelete='SET NULL'),
        comment='邀请人ID'
    )
    
    is_active = Column(
        Boolean,
        default=True,
        comment='是否有效'
    )
    
    # 关联关系
    project = relationship(
        'Project',
        back_populates='members',
        lazy='selectin'
    )
    
    user = relationship(
        'User',
        foreign_keys=[user_id],
        back_populates='project_memberships',
        lazy='selectin'
    )
    
    inviter = relationship(
        'User',
        foreign_keys=[joined_by],
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_project_members_project', 'project_id'),
        Index('idx_project_members_user', 'user_id'),
        Index('idx_project_members_role', 'role'),
        {'comment': '项目成员表'}
    )
    
    def has_permission(self, permission: str) -> bool:
        """检查是否有特定权限"""
        # 如果有自定义权限，优先使用
        if self.permissions and permission in self.permissions:
            return self.permissions[permission]
        
        # 否则使用角色默认权限
        role_permissions = {
            ProjectRole.OWNER: [
                'project:view', 'project:edit', 'project:delete',
                'member:manage', 'version:manage', 'case:manage',
                'execution:manage', 'issue:manage', 'setting:manage'
            ],
            ProjectRole.TEST_LEAD: [
                'project:view', 'member:view',
                'version:view', 'version:create',
                'case:manage', 'execution:manage', 'issue:manage'
            ],
            ProjectRole.TESTER: [
                'project:view',
                'version:view', 'case:view', 'case:create', 'case:edit',
                'execution:execute', 'issue:view', 'issue:create'
            ],
            ProjectRole.DEVELOPER: [
                'project:view', 'version:view', 'case:view',
                'issue:view', 'issue:edit'
            ],
            ProjectRole.VIEWER: [
                'project:view', 'version:view', 'case:view',
                'execution:view', 'issue:view'
            ]
        }
        
        return permission in role_permissions.get(ProjectRole(self.role), [])


class ProjectEnvironment(Base):
    """项目环境配置模型"""
    
    __tablename__ = 'project_environments'
    
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
    
    name = Column(
        String(100),
        nullable=False,
        comment='环境名称（如：开发环境、测试环境）'
    )
    
    code = Column(
        String(50),
        nullable=False,
        comment='环境编码（如：dev、test、prod）'
    )
    
    base_url = Column(
        String(500),
        comment='基础URL'
    )
    
    # 请求头配置
    headers = Column(
        JSON,
        comment='请求头: {"Authorization": "Bearer xxx"}'
    )
    
    # 环境变量
    variables = Column(
        JSON,
        comment='环境变量: {"db_host": "localhost", "timeout": "30"}'
    )
    
    # 数据库配置（可选）
    db_config = Column(
        JSON,
        comment='数据库配置: {"host": "", "port": 3306, "database": ""}'
    )
    
    is_default = Column(
        Boolean,
        default=False,
        comment='是否默认环境'
    )
    
    is_active = Column(
        Boolean,
        default=True,
        comment='是否启用'
    )
    
    description = Column(
        String(500),
        comment='环境描述'
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
    
    # 关联关系
    project = relationship(
        'Project',
        back_populates='environments',
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_env_project', 'project_id'),
        Index('idx_env_code', 'project_id', 'code', unique=True),
        {'comment': '项目环境配置表'}
    )


class VersionDocHistory(Base):
    """版本文档历史模型"""
    
    __tablename__ = 'version_doc_history'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    
    version_id = Column(
        BigInteger,
        ForeignKey('versions.id', ondelete='CASCADE'),
        nullable=False,
        comment='版本ID'
    )
    
    doc_type = Column(
        String(20),
        comment='文档类型: word/pdf/markdown/url'
    )
    
    doc_url = Column(
        String(500),
        comment='文档URL'
    )
    
    doc_content = Column(
        JSON,
        comment='文档内容（解析后的结构化内容）'
    )
    
    change_summary = Column(
        String(1000),
        comment='变更摘要（AI生成）'
    )
    
    uploaded_by = Column(
        String(36),
        ForeignKey('user.id', ondelete='SET NULL'),
        comment='上传人ID'
    )
    
    uploaded_at = Column(
        DateTime,
        server_default=func.now(),
        comment='上传时间'
    )
    
    # 关联关系
    version = relationship(
        'Version',
        back_populates='doc_history',
        lazy='selectin'
    )
    
    uploader = relationship(
        'User',
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_doc_history_version', 'version_id'),
        Index('idx_doc_history_uploaded', 'uploaded_at'),
        {'comment': '版本文档历史表'}
    )


class ProjectSetting(Base):
    """项目设置模型"""
    
    __tablename__ = 'project_settings'
    
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
        unique=True,
        comment='项目ID'
    )
    
    # 通知配置
    notification_config = Column(
        JSON,
        comment='通知配置: {"execution_completed": true, "channels": ["email"]}'
    )
    
    # 执行默认配置
    execution_defaults = Column(
        JSON,
        comment='执行默认配置: {"parallel": 4, "retry": 1, "timeout": 3600}'
    )
    
    # 测试默认配置
    test_defaults = Column(
        JSON,
        comment='测试默认配置: {"browser": "chromium", "viewport": {"width": 1920}}'
    )
    
    # 探索配置 — WEB/APP 端探索所需的连接信息
    exploration_config = Column(
        JSON,
        default=dict,
        comment='探索配置: {"web":{"base_url":"","username":"","password":""},"app":{"appium_url":"","username":"","password":"","auto_launch":true}}'
    )

    # 其他自定义设置
    custom_settings = Column(
        JSON,
        comment='其他自定义设置'
    )
    
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment='更新时间'
    )
    
    # 关联关系
    project = relationship(
        'Project',
        back_populates='settings',
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_setting_project', 'project_id'),
        {'comment': '项目设置表'}
    )
