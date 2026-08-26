"""
通知与告警模型
对应需求文档 3.13 告警与通知
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class NotificationType(str, enum.Enum):
    """通知渠道类型"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECHAT = "wechat"
    EMAIL = "email"


class AlertConditionType(str, enum.Enum):
    """告警条件类型"""
    EXECUTION_FAILED = "execution_failed"
    PASS_RATE_LOW = "pass_rate_low"
    PERFORMANCE_ABNORMAL = "performance_abnormal"
    CI_FAILED = "ci_failed"
    ISSUE_CREATED = "issue_created"
    ISSUE_UNRESOLVED = "issue_unresolved"


class NotificationChannel(Base):
    """通知渠道配置"""
    __tablename__ = "notification_channels"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), comment="项目ID(空则为全局)")
    
    name = Column(String(100), nullable=False, comment="渠道名称")
    type = Column(String(20), nullable=False, comment="渠道类型: feishu/dingtalk/wechat/email")
    
    webhook_url = Column(String(500), comment="Webhook URL")
    secret = Column(String(200), comment="密钥/签名")
    
    email_config = Column(JSON, comment="邮件配置(smtp_server, smtp_port, username, password, from_addr)")
    
    enabled = Column(Boolean, default=True, comment="是否启用")
    
    test_status = Column(String(20), comment="测试状态: success/failed")
    test_message = Column(Text, comment="测试消息")
    last_test_at = Column(DateTime, comment="最后测试时间")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship(
        'Project',
        backref='notification_channels'
    )
    
    def __repr__(self):
        return f"<NotificationChannel(id={self.id}, name={self.name}, type={self.type})>"


class AlertRule(Base):
    """告警规则"""
    __tablename__ = "alert_rules"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), comment="项目ID")
    
    name = Column(String(100), nullable=False, comment="规则名称")
    description = Column(Text, comment="规则描述")
    
    condition_type = Column(String(50), nullable=False, comment="条件类型")
    condition_config = Column(JSON, comment="条件配置(阈值、次数等)")
    
    channel_ids = Column(JSON, comment="通知渠道ID列表")
    receivers = Column(JSON, comment="接收人列表(邮箱、手机号等)")
    
    template_id = Column(BigInteger, comment="消息模板ID")
    custom_template = Column(Text, comment="自定义消息模板")
    
    enabled = Column(Boolean, default=True, comment="是否启用")
    
    last_triggered_at = Column(DateTime, comment="最后触发时间")
    trigger_count = Column(Integer, default=0, comment="触发次数")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship(
        'Project',
        backref='alert_rules'
    )
    
    def __repr__(self):
        return f"<AlertRule(id={self.id}, name={self.name})>"


class MessageTemplate(Base):
    """消息模板"""
    __tablename__ = "message_templates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), comment="项目ID")
    
    name = Column(String(100), nullable=False, comment="模板名称")
    type = Column(String(20), comment="模板类型: feishu/dingtalk/wechat/email")
    
    title_template = Column(String(500), comment="标题模板")
    content_template = Column(Text, comment="内容模板(支持变量替换)")
    
    variables = Column(JSON, comment="支持的变量列表")
    
    is_default = Column(Boolean, default=False, comment="是否默认模板")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship(
        'Project',
        backref='message_templates'
    )
    
    def __repr__(self):
        return f"<MessageTemplate(id={self.id}, name={self.name})>"


class NotificationHistory(Base):
    """通知发送历史"""
    __tablename__ = "notification_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"))
    
    channel_id = Column(BigInteger, ForeignKey("notification_channels.id"), comment="渠道ID")
    rule_id = Column(BigInteger, ForeignKey("alert_rules.id"), comment="规则ID")
    
    recipient = Column(String(200), comment="接收人")
    subject = Column(String(500), comment="通知主题")
    content = Column(Text, comment="通知内容")
    
    status = Column(String(20), default="pending", comment="发送状态: pending/success/failed")
    error_message = Column(Text, comment="错误信息")
    
    triggered_by = Column(String(200), comment="触发来源")
    trigger_data = Column(JSON, comment="触发数据")
    
    sent_at = Column(DateTime, comment="发送时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    project = relationship(
        'Project',
        backref='notification_history'
    )
    channel = relationship(
        'NotificationChannel',
        backref='history'
    )
    rule = relationship(
        'AlertRule',
        backref='history'
    )
    
    def __repr__(self):
        return f"<NotificationHistory(id={self.id}, status={self.status})>"