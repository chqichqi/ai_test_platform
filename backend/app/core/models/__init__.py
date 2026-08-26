"""
数据库模型定义
"""

from .base import BaseModel, TimestampMixin
from .user import User, Role, Permission
from .requirement import TestCase  # 先导入 TestCase
from .project import Project, Version, ProjectStatus, VersionStatus
from .project_ext import ProjectMember, ProjectEnvironment, ProjectSetting, VersionDocHistory
from .generation_task import GenerationTask, TaskStatus, TaskType
from .git import (
    GitRepository, GitBranch, GitCommit, GitWebhook, GitWebhookLog,
    GitCommitTestCase, AuthType, RepositoryStatus, WebhookEventType
)
from .test_simple import (
    SimpleTestCase, TestExecution, TestResult, TestRun, TestPlan,
    TestStatus, TestPriority, TestType, ExecutionStatus
)

__all__ = [
    "BaseModel",
    "TimestampMixin",
    
    "User",
    "Role", 
    "Permission",
    
    "TestCase",  # 添加 TestCase
    "Project",
    "Version",
    "ProjectStatus",
    "VersionStatus",
    
    "GenerationTask",
    "TaskStatus",
    "TaskType",
    
    "ProjectMember",
    "ProjectEnvironment",
    "ProjectSetting",
    "VersionDocHistory",
    
    "GitRepository",
    "GitBranch",
    "GitCommit",
    "GitWebhook",
    "GitWebhookLog",
    "GitCommitTestCase",
    "AuthType",
    "RepositoryStatus",
    "WebhookEventType",
    
    "SimpleTestCase",
    "TestExecution", 
    "TestResult",
    "TestRun",
    "TestPlan",
    "TestStatus",
    "TestPriority",
    "TestType",
    "ExecutionStatus",
]