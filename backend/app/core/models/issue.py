"""
问题跟踪和AI失败分析模型
对应需求文档 3.10 结果与问题管理
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Integer
import enum

from app.core.database import Base


class IssueSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class IssuePriority(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class FailureType(str, enum.Enum):
    ELEMENT_NOT_FOUND = "element_not_found"
    ASSERTION_FAILED = "assertion_failed"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    ENVIRONMENT_ERROR = "environment_error"
    DATA_ERROR = "data_error"
    BUSINESS_BUG = "business_bug"
    SCRIPT_ERROR = "script_error"
    UNKNOWN = "unknown"


class RootCauseCategory(str, enum.Enum):
    UI_CHANGED = "ui_changed"
    ENVIRONMENT = "environment"
    BUSINESS_LOGIC = "business_logic"
    DATA_ISSUE = "data_issue"
    TEST_SCRIPT = "test_script"
    INFRASTRUCTURE = "infrastructure"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class Issue(Base):
    __tablename__ = "issues"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    version_id = Column(BigInteger, ForeignKey("versions.id"), comment="版本ID")
    execution_id = Column(BigInteger, comment="执行ID")
    case_id = Column(BigInteger, comment="用例ID")
    
    title = Column(String(200), nullable=False, comment="问题标题")
    description = Column(Text, comment="问题描述")
    
    severity = Column(String(20), default=IssueSeverity.MEDIUM.value, comment="严重程度")
    priority = Column(String(10), default=IssuePriority.P2.value, comment="优先级")
    status = Column(String(20), default=IssueStatus.OPEN.value, comment="状态")
    
    failure_type = Column(String(30), comment="失败类型")
    root_cause = Column(String(30), comment="根本原因分类")
    
    ai_analysis = Column(Text, comment="AI分析结果")
    ai_suggestion = Column(Text, comment="AI建议")
    ai_confidence = Column(Integer, comment="AI分析置信度(0-100)")
    
    assignee_id = Column(BigInteger, comment="处理人ID")
    reporter_id = Column(BigInteger, comment="报告人ID")
    
    resolved_at = Column(DateTime, comment="解决时间")
    resolved_by = Column(BigInteger, comment="解决人ID")
    resolution_note = Column(Text, comment="解决方案说明")
    
    tags = Column(JSON, comment="标签列表")
    attachments = Column(JSON, comment="附件信息")
    
    affected_cases = Column(JSON, comment="影响的用例ID列表")
    similar_issues = Column(JSON, comment="相似问题ID列表")
    
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<Issue(id={self.id}, title={self.title})>"


class FailureAnalysis(Base):
    __tablename__ = "failure_analyses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    execution_id = Column(BigInteger, nullable=False, comment="执行ID")
    case_id = Column(BigInteger, comment="用例ID")
    project_id = Column(BigInteger, nullable=False, comment="项目ID")
    
    failure_type = Column(String(30), comment="失败类型")
    failure_message = Column(Text, comment="失败消息")
    stack_trace = Column(Text, comment="堆栈跟踪")
    
    screenshot_url = Column(String(500), comment="截图URL")
    dom_snapshot = Column(Text, comment="DOM快照")
    console_logs = Column(JSON, comment="控制台日志")
    network_logs = Column(JSON, comment="网络日志")
    
    ai_analysis = Column(Text, comment="AI分析结果")
    root_cause = Column(String(30), comment="根本原因")
    confidence = Column(Integer, comment="置信度")
    
    suggested_fix = Column(Text, comment="建议修复方案")
    auto_fix_available = Column(Integer, default=0, comment="是否可自动修复")
    auto_fix_applied = Column(Integer, default=0, comment="是否已应用自动修复")
    
    affected_locators = Column(JSON, comment="受影响的定位器")
    affected_cases = Column(JSON, comment="受影响的用例")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FailureAnalysis(id={self.id}, type={self.failure_type})>"


class IssueComment(Base):
    __tablename__ = "issue_comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    issue_id = Column(BigInteger, ForeignKey("issues.id"), nullable=False, comment="问题ID")
    
    content = Column(Text, nullable=False, comment="评论内容")
    author_id = Column(BigInteger, comment="作者ID")
    
    is_internal = Column(Integer, default=0, comment="是否内部评论")
    parent_id = Column(BigInteger, comment="父评论ID")
    
    attachments = Column(JSON, comment="附件")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<IssueComment(id={self.id})>"


class IssueHistory(Base):
    __tablename__ = "issue_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    issue_id = Column(BigInteger, ForeignKey("issues.id"), nullable=False, comment="问题ID")
    
    field_name = Column(String(50), comment="变更字段")
    old_value = Column(Text, comment="旧值")
    new_value = Column(Text, comment="新值")
    
    changed_by = Column(BigInteger, comment="变更人ID")
    changed_at = Column(DateTime, default=datetime.utcnow, comment="变更时间")
    change_reason = Column(Text, comment="变更原因")

    def __repr__(self):
        return f"<IssueHistory(id={self.id})>"