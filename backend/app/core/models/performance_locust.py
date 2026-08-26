"""
Locust性能测试相关模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Integer, Float, Boolean, Enum as SAEnum
import enum

from app.core.database import Base


class LocustScriptStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class LocustExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class LocustScript(Base):
    """Locust压测脚本"""
    __tablename__ = "locust_scripts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    name = Column(String(200), nullable=False, comment="脚本名称")
    description = Column(Text, comment="描述")
    file_content = Column(Text, comment="locustfile.py 内容")
    file_size = Column(Integer, default=0, comment="文件大小(字节)")
    version = Column(Integer, default=1, comment="版本号")
    status = Column(String(20), default=LocustScriptStatus.DRAFT.value, comment="状态")
    host = Column(String(500), comment="目标Host")
    source_case_ids = Column(JSON, comment="来源API用例ID列表")
    created_by = Column(String(36), comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __repr__(self):
        return f"<LocustScript(id={self.id}, name={self.name})>"


class LocustExecution(Base):
    """Locust执行记录"""
    __tablename__ = "locust_executions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    script_id = Column(BigInteger, ForeignKey("locust_scripts.id"), comment="脚本ID")
    scenario_id = Column(BigInteger, ForeignKey("performance_scenarios.id"), comment="场景ID")
    name = Column(String(200), comment="执行名称")

    status = Column(String(20), default=LocustExecutionStatus.PENDING.value, comment="状态")
    host = Column(String(500), comment="目标Host")
    num_users = Column(Integer, default=100, comment="并发用户数")
    spawn_rate = Column(Integer, default=10, comment="孵化率(用户/秒)")
    run_time = Column(Integer, default=60, comment="运行时长(秒)")

    # 梯度配置
    step_enabled = Column(Boolean, default=False, comment="是否启用梯度")
    step_count = Column(Integer, default=5, comment="梯度步数")
    step_duration = Column(Integer, default=60, comment="每步持续时间(秒)")
    step_thread_increment = Column(Integer, default=10, comment="每步增加线程数")

    locust_process_id = Column(Integer, comment="Locust进程ID")
    result_dir = Column(String(500), comment="结果文件目录")

    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    actual_duration = Column(Integer, comment="实际执行时长(秒)")

    # 汇总指标
    avg_tps = Column(Float, comment="平均TPS")
    max_tps = Column(Float, comment="最大TPS")
    avg_rt = Column(Float, comment="平均响应时间(ms)")
    max_rt = Column(Float, comment="最大响应时间(ms)")
    p50_rt = Column(Float, comment="P50响应时间(ms)")
    p90_rt = Column(Float, comment="P90响应时间(ms)")
    p95_rt = Column(Float, comment="P95响应时间(ms)")
    p99_rt = Column(Float, comment="P99响应时间(ms)")
    total_samples = Column(Integer, comment="总请求数")
    success_samples = Column(Integer, comment="成功请求数")
    error_samples = Column(Integer, comment="错误请求数")
    error_rate = Column(Float, comment="错误率(%)")

    summary_metrics = Column(JSON, comment="汇总指标详细")
    detailed_metrics = Column(JSON, comment="详细指标")

    triggered_by = Column(String(36), comment="触发用户ID")
    created_by = Column(String(36), comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def __repr__(self):
        return f"<LocustExecution(id={self.id}, status={self.status})>"


class LocustMetric(Base):
    """Locust运行时序指标"""
    __tablename__ = "locust_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    execution_id = Column(BigInteger, ForeignKey("locust_executions.id"), nullable=False, comment="执行ID")
    timestamp = Column(DateTime, nullable=False, comment="时间戳")
    elapsed_seconds = Column(Integer, comment="已运行秒数")

    user_count = Column(Integer, comment="当前用户数")
    tps = Column(Float, comment="当前TPS")
    avg_rt = Column(Float, comment="平均响应时间(ms)")
    min_rt = Column(Float, comment="最小响应时间(ms)")
    max_rt = Column(Float, comment="最大响应时间(ms)")
    fail_ratio = Column(Float, comment="失败率")
    samples_count = Column(Integer, comment="当前请求数")
    error_count = Column(Integer, comment="当前错误数")

    throughput_kb = Column(Float, comment="吞吐量(KB/s)")
    latency = Column(Float, comment="延迟(ms)")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def __repr__(self):
        return f"<LocustMetric(execution_id={self.execution_id}, t={self.elapsed_seconds}s, tps={self.tps})>"
