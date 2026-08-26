"""
CI/CD集成模型
对应需求文档 3.11 CI/CD集成
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class CICDPlatform(str, enum.Enum):
    """CI/CD平台类型"""
    JENKINS = "jenkins"
    GITLAB = "gitlab"
    GITHUB = "github"


class TriggerType(str, enum.Enum):
    """触发类型"""
    ON_COMMIT = "on_commit"
    ON_PR = "on_pr"
    ON_MERGE = "on_merge"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class PipelineStatus(str, enum.Enum):
    """Pipeline状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class CICDConfig(Base):
    """CI/CD配置"""
    __tablename__ = "cicd_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    
    name = Column(String(200), nullable=False, comment="配置名称")
    platform = Column(String(20), nullable=False, comment="平台类型: jenkins/gitlab/github")
    
    platform_url = Column(String(500), comment="平台URL")
    api_token = Column(String(500), comment="API Token(加密存储)")
    username = Column(String(100), comment="用户名")
    
    webhook_url = Column(String(500), comment="Webhook URL")
    webhook_secret = Column(String(200), comment="Webhook密钥")
    
    config_data = Column(JSON, comment="平台特定配置")
    
    enabled = Column(Boolean, default=True, comment="是否启用")
    
    last_sync_at = Column(DateTime, comment="最后同步时间")
    sync_status = Column(String(20), comment="同步状态")
    sync_message = Column(Text, comment="同步消息")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship(
        'Project',
        backref='cicd_configs'
    )
    
    def __repr__(self):
        return f"<CICDConfig(id={self.id}, name={self.name}, platform={self.platform})>"


class PipelineDefinition(Base):
    """Pipeline定义"""
    __tablename__ = "pipeline_definitions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_id = Column(BigInteger, ForeignKey("cicd_configs.id"), nullable=False, comment="CI/CD配置ID")
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    
    name = Column(String(200), nullable=False, comment="Pipeline名称")
    external_id = Column(String(200), comment="外部系统ID(Job ID/Pipeline ID/Workflow ID)")
    
    trigger_type = Column(String(20), default=TriggerType.MANUAL.value, comment="触发类型")
    trigger_config = Column(JSON, comment="触发配置(分支、计划等)")
    
    test_plan_id = Column(BigInteger, comment="关联测试计划ID")
    test_case_ids = Column(JSON, comment="测试用例ID列表")
    test_params = Column(JSON, comment="测试参数")
    
    environment = Column(String(100), comment="执行环境")
    timeout = Column(Integer, default=3600, comment="超时时间(秒)")
    
    notification_config = Column(JSON, comment="通知配置")
    
    enabled = Column(Boolean, default=True, comment="是否启用")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    config = relationship(
        'CICDConfig',
        backref='pipelines'
    )
    project = relationship(
        'Project',
        backref='pipelines'
    )
    
    def __repr__(self):
        return f"<PipelineDefinition(id={self.id}, name={self.name})>"


class PipelineExecution(Base):
    """Pipeline执行记录"""
    __tablename__ = "pipeline_executions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    pipeline_id = Column(BigInteger, ForeignKey("pipeline_definitions.id"), nullable=False, comment="Pipeline ID")
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    
    external_build_id = Column(String(200), comment="外部构建ID")
    build_number = Column(Integer, comment="构建号")
    build_url = Column(String(500), comment="构建URL")
    
    status = Column(String(20), default=PipelineStatus.PENDING.value, comment="执行状态")
    
    trigger_type = Column(String(20), comment="触发类型")
    trigger_by = Column(String(100), comment="触发人")
    trigger_ref = Column(String(200), comment="触发引用(分支/tag/commit)")
    
    started_at = Column(DateTime, comment="开始时间")
    finished_at = Column(DateTime, comment="结束时间")
    duration = Column(Integer, comment="执行时长(秒)")
    
    total_cases = Column(Integer, default=0, comment="总用例数")
    passed_cases = Column(Integer, default=0, comment="通过用例数")
    failed_cases = Column(Integer, default=0, comment="失败用例数")
    skipped_cases = Column(Integer, default=0, comment="跳过用例数")
    
    test_results = Column(JSON, comment="测试结果详情")
    error_message = Column(Text, comment="错误信息")
    
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    pipeline = relationship(
        'PipelineDefinition',
        backref='executions'
    )
    project = relationship(
        'Project',
        backref='pipeline_executions'
    )
    
    def __repr__(self):
        return f"<PipelineExecution(id={self.id}, build_number={self.build_number}, status={self.status})>"
    
    @property
    def pass_rate(self) -> float:
        """计算通过率"""
        if self.total_cases == 0:
            return 0.0
        return round(self.passed_cases / self.total_cases * 100, 2)


class WebhookEvent(Base):
    """Webhook事件记录"""
    __tablename__ = "webhook_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_id = Column(BigInteger, ForeignKey("cicd_configs.id"), comment="CI/CD配置ID")
    
    event_type = Column(String(50), comment="事件类型")
    event_id = Column(String(200), comment="事件ID")
    source = Column(String(50), comment="事件来源: jenkins/gitlab/github")
    
    headers = Column(JSON, comment="请求头")
    payload = Column(JSON, comment="请求体")
    
    processed = Column(Boolean, default=False, comment="是否已处理")
    process_result = Column(Text, comment="处理结果")
    process_error = Column(Text, comment="处理错误")
    
    received_at = Column(DateTime, default=datetime.utcnow, comment="接收时间")
    processed_at = Column(DateTime, comment="处理时间")
    
    config = relationship(
        'CICDConfig',
        backref='webhook_events'
    )
    
    def __repr__(self):
        return f"<WebhookEvent(id={self.id}, event_type={self.event_type}, source={self.source})>"