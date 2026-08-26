"""
Git版本管理模型 - MySQL版本
对应需求文档 3.2 Git版本管理
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column, BigInteger, String, Text, DateTime, ForeignKey,
    Index, Integer, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AuthType(str, Enum):
    """认证类型"""
    SSH = "ssh"
    TOKEN = "token"
    PASSWORD = "password"
    NONE = "none"


class RepositoryStatus(str, Enum):
    """仓库状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class WebhookEventType(str, Enum):
    """Webhook事件类型"""
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    MERGE_REQUEST = "merge_request"
    RELEASE = "release"


class GitRepository(Base):
    """Git仓库模型 - 对应需求文档 3.2.1"""
    
    __tablename__ = 'git_repositories'
    
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
        comment='仓库名称'
    )
    url = Column(
        String(500),
        nullable=False,
        comment='仓库URL'
    )
    auth_type = Column(
        String(20),
        default=AuthType.NONE.value,
        comment='认证类型: ssh/token/password/none'
    )
    auth_token = Column(
        Text,
        comment='认证Token(加密存储)'
    )
    ssh_key = Column(
        Text,
        comment='SSH私钥(加密存储)'
    )
    username = Column(
        String(100),
        comment='用户名(用于密码认证)'
    )
    password = Column(
        String(255),
        comment='密码(加密存储)'
    )
    default_branch = Column(
        String(50),
        default='main',
        comment='默认分支'
    )
    last_sync_at = Column(
        DateTime,
        comment='最后同步时间'
    )
    last_sync_status = Column(
        String(20),
        comment='最后同步状态'
    )
    last_sync_error = Column(
        Text,
        comment='最后同步错误信息'
    )
    status = Column(
        String(20),
        default=RepositoryStatus.ACTIVE.value,
        comment='状态: active/inactive/error'
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
        back_populates='git_repositories',
        lazy='selectin'
    )
    
    commits = relationship(
        'GitCommit',
        back_populates='repository',
        lazy='dynamic'
    )
    
    branches = relationship(
        'GitBranch',
        back_populates='repository',
        lazy='dynamic'
    )
    
    webhooks = relationship(
        'GitWebhook',
        back_populates='repository',
        lazy='dynamic'
    )
    
    __table_args__ = (
        Index('idx_git_repositories_project_id', 'project_id'),
        Index('idx_git_repositories_status', 'status'),
        Index('idx_git_repositories_url', 'url'),
        {'comment': 'Git仓库表'}
    )
    
    def to_dict(self, exclude: Optional[List[str]] = None):
        """转换为字典（排除敏感信息）"""
        exclude = exclude or []
        exclude.extend(['auth_token', 'ssh_key', 'password'])
        
        result = {}
        for column in self.__table__.columns:
            col_name = column.name
            if col_name in exclude:
                continue
            value = getattr(self, col_name)
            if isinstance(value, datetime):
                value = value.isoformat() if value else None
            result[col_name] = value
        
        return result


class GitBranch(Base):
    """Git分支模型"""
    
    __tablename__ = 'git_branches'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    repository_id = Column(
        BigInteger,
        ForeignKey('git_repositories.id', ondelete='CASCADE'),
        nullable=False,
        comment='仓库ID'
    )
    name = Column(
        String(200),
        nullable=False,
        comment='分支名称'
    )
    last_commit_hash = Column(
        String(40),
        comment='最后提交哈希'
    )
    last_commit_message = Column(
        Text,
        comment='最后提交信息'
    )
    last_commit_author = Column(
        String(100),
        comment='最后提交者'
    )
    last_commit_at = Column(
        DateTime,
        comment='最后提交时间'
    )
    is_default = Column(
        Integer,
        default=0,
        comment='是否默认分支: 0否 1是'
    )
    is_protected = Column(
        Integer,
        default=0,
        comment='是否保护分支: 0否 1是'
    )
    ahead_count = Column(
        Integer,
        default=0,
        comment='领先默认分支的提交数'
    )
    behind_count = Column(
        Integer,
        default=0,
        comment='落后默认分支的提交数'
    )
    status = Column(
        String(20),
        default='active',
        comment='状态: active/deleted'
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
    
    repository = relationship(
        'GitRepository',
        back_populates='branches',
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_git_branches_repository_id', 'repository_id'),
        Index('idx_git_branches_name', 'name'),
        Index('idx_git_branches_status', 'status'),
        {'comment': 'Git分支表'}
    )
    
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
        return result


class GitCommit(Base):
    """Git提交记录模型 - 对应需求文档 3.2.3"""
    
    __tablename__ = 'git_commits'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    repository_id = Column(
        BigInteger,
        ForeignKey('git_repositories.id', ondelete='CASCADE'),
        nullable=False,
        comment='仓库ID'
    )
    commit_hash = Column(
        String(40),
        nullable=False,
        comment='提交哈希'
    )
    short_hash = Column(
        String(7),
        comment='短哈希'
    )
    branch = Column(
        String(200),
        comment='分支名称'
    )
    author = Column(
        String(100),
        comment='提交者'
    )
    author_email = Column(
        String(100),
        comment='提交者邮箱'
    )
    committer = Column(
        String(100),
        comment='提交人'
    )
    committer_email = Column(
        String(100),
        comment='提交人邮箱'
    )
    message = Column(
        Text,
        comment='提交信息'
    )
    committed_at = Column(
        DateTime,
        comment='提交时间'
    )
    files_changed = Column(
        Integer,
        default=0,
        comment='变更文件数'
    )
    additions = Column(
        Integer,
        default=0,
        comment='新增行数'
    )
    deletions = Column(
        Integer,
        default=0,
        comment='删除行数'
    )
    parent_hashes = Column(
        Text,
        comment='父提交哈希列表(JSON)'
    )
    files = Column(
        JSON,
        comment='变更文件列表'
    )
    created_at = Column(
        DateTime,
        server_default=func.now(),
        comment='创建时间'
    )
    
    repository = relationship(
        'GitRepository',
        back_populates='commits',
        lazy='selectin'
    )
    
    test_case_links = relationship(
        'GitCommitTestCase',
        back_populates='commit',
        lazy='dynamic'
    )
    
    __table_args__ = (
        Index('idx_git_commits_repository_id', 'repository_id'),
        Index('idx_git_commits_commit_hash', 'commit_hash'),
        Index('idx_git_commits_branch', 'branch'),
        Index('idx_git_commits_author', 'author'),
        Index('idx_git_commits_committed_at', 'committed_at'),
        {'comment': 'Git提交记录表'}
    )
    
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
        return result


class GitWebhook(Base):
    """Git Webhook配置模型 - 对应需求文档 3.2.4"""
    
    __tablename__ = 'git_webhooks'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    repository_id = Column(
        BigInteger,
        ForeignKey('git_repositories.id', ondelete='CASCADE'),
        nullable=False,
        comment='仓库ID'
    )
    name = Column(
        String(100),
        comment='Webhook名称'
    )
    webhook_url = Column(
        String(500),
        comment='外部Webhook URL(用于接收方)'
    )
    secret = Column(
        String(100),
        comment='Webhook密钥/签名'
    )
    trigger_events = Column(
        JSON,
        comment='触发事件列表: ["push", "pull_request"]'
    )
    trigger_branches = Column(
        JSON,
        comment='触发分支列表(空为全部)'
    )
    trigger_paths = Column(
        JSON,
        comment='触发路径规则(空为全部)'
    )
    test_plan_id = Column(
        BigInteger,
        comment='关联的测试计划ID'
    )
    execution_config = Column(
        JSON,
        comment='执行配置'
    )
    enabled = Column(
        Integer,
        default=1,
        comment='是否启用: 0否 1是'
    )
    last_triggered_at = Column(
        DateTime,
        comment='最后触发时间'
    )
    trigger_count = Column(
        Integer,
        default=0,
        comment='触发次数'
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
    
    repository = relationship(
        'GitRepository',
        back_populates='webhooks',
        lazy='selectin'
    )
    
    logs = relationship(
        'GitWebhookLog',
        back_populates='webhook',
        lazy='dynamic'
    )
    
    __table_args__ = (
        Index('idx_git_webhooks_repository_id', 'repository_id'),
        Index('idx_git_webhooks_enabled', 'enabled'),
        {'comment': 'Git Webhook配置表'}
    )
    
    def to_dict(self, exclude: Optional[List[str]] = None):
        """转换为字典"""
        exclude = exclude or []
        exclude.append('secret')
        result = {}
        for column in self.__table__.columns:
            col_name = column.name
            if col_name in exclude:
                continue
            value = getattr(self, col_name)
            if isinstance(value, datetime):
                value = value.isoformat() if value else None
            result[col_name] = value
        return result


class GitWebhookLog(Base):
    """Git Webhook日志模型"""
    
    __tablename__ = 'git_webhook_logs'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    webhook_id = Column(
        BigInteger,
        ForeignKey('git_webhooks.id', ondelete='CASCADE'),
        nullable=False,
        comment='Webhook ID'
    )
    event_type = Column(
        String(50),
        comment='事件类型: push/pull_request/merge_request'
    )
    payload = Column(
        JSON,
        comment='请求内容'
    )
    headers = Column(
        JSON,
        comment='请求头'
    )
    signature_valid = Column(
        Integer,
        comment='签名验证: 0失败 1成功'
    )
    triggered = Column(
        Integer,
        default=0,
        comment='是否触发测试: 0否 1是'
    )
    trigger_reason = Column(
        Text,
        comment='触发/未触发原因'
    )
    execution_id = Column(
        BigInteger,
        comment='执行记录ID'
    )
    error_message = Column(
        Text,
        comment='错误信息'
    )
    ip_address = Column(
        String(50),
        comment='请求IP'
    )
    user_agent = Column(
        String(255),
        comment='User-Agent'
    )
    created_at = Column(
        DateTime,
        server_default=func.now(),
        comment='创建时间'
    )
    
    webhook = relationship(
        'GitWebhook',
        back_populates='logs',
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_git_webhook_logs_webhook_id', 'webhook_id'),
        Index('idx_git_webhook_logs_event_type', 'event_type'),
        Index('idx_git_webhook_logs_created_at', 'created_at'),
        {'comment': 'Git Webhook日志表'}
    )
    
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
        return result


class GitCommitTestCase(Base):
    """Git提交与测试用例关联表"""
    
    __tablename__ = 'git_commit_test_cases'
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )
    commit_id = Column(
        BigInteger,
        ForeignKey('git_commits.id', ondelete='CASCADE'),
        nullable=False,
        comment='提交ID'
    )
    test_case_id = Column(
        BigInteger,
        comment='测试用例ID'
    )
    link_type = Column(
        String(20),
        default='reference',
        comment='关联类型: reference/fix/feature'
    )
    linked_by = Column(
        BigInteger,
        comment='关联用户ID'
    )
    created_at = Column(
        DateTime,
        server_default=func.now(),
        comment='创建时间'
    )
    
    commit = relationship(
        'GitCommit',
        back_populates='test_case_links',
        lazy='selectin'
    )
    
    __table_args__ = (
        Index('idx_git_commit_test_cases_commit_id', 'commit_id'),
        Index('idx_git_commit_test_cases_test_case_id', 'test_case_id'),
        {'comment': 'Git提交与测试用例关联表'}
    )