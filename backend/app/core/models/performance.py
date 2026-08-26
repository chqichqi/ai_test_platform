"""
性能测试模型
对应需求文档 3.14 性能测试
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Boolean, Integer, Float
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class PerformanceTestStatus(str, enum.Enum):
    """性能测试状态"""
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ScriptStatus(str, enum.Enum):
    """脚本状态"""
    DRAFT = "draft"
    VALIDATED = "validated"
    ERROR = "error"


class JMeterScript(Base):
    """JMeter脚本"""
    __tablename__ = "jmeter_scripts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    
    name = Column(String(200), nullable=False, comment="脚本名称")
    description = Column(Text, comment="脚本描述")
    
    file_path = Column(String(500), comment="JMX文件路径")
    file_content = Column(Text, comment="JMX文件内容(XML)")
    file_size = Column(Integer, comment="文件大小(KB)")
    
    version = Column(Integer, default=1, comment="版本号")
    version_note = Column(String(500), comment="版本说明")
    
    status = Column(String(20), default="draft", comment="状态: draft/validated/error")
    validation_message = Column(Text, comment="验证信息")
    
    test_plan_name = Column(String(200), comment="TestPlan名称")
    thread_groups = Column(JSON, comment="线程组配置列表")
    samplers = Column(JSON, comment="采样器列表")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship('Project', backref='jmeter_scripts')
    
    def __repr__(self):
        return f"<JMeterScript(id={self.id}, name={self.name}, version={self.version})>"


class ScriptVersion(Base):
    """脚本版本历史"""
    __tablename__ = "script_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    script_id = Column(BigInteger, ForeignKey("jmeter_scripts.id"), nullable=False)
    
    version = Column(Integer, nullable=False, comment="版本号")
    file_content = Column(Text, comment="JMX文件内容")
    version_note = Column(String(500), comment="版本说明")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    script = relationship('JMeterScript', backref='versions')
    
    def __repr__(self):
        return f"<ScriptVersion(id={self.id}, script_id={self.script_id}, version={self.version})>"


class PerformanceScenario(Base):
    """性能测试场景"""
    __tablename__ = "performance_scenarios"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    script_id = Column(BigInteger, ForeignKey("jmeter_scripts.id"), nullable=False)
    
    name = Column(String(200), nullable=False, comment="场景名称")
    description = Column(Text, comment="场景描述")
    
    concurrent_users = Column(Integer, default=100, comment="并发用户数")
    ramp_up_period = Column(Integer, default=60, comment="启动时间(秒)")
    duration = Column(Integer, default=300, comment="持续时间(秒)")
    
    target_tps = Column(Float, comment="目标TPS")
    target_rt = Column(Float, comment="目标响应时间(ms)")
    error_rate_threshold = Column(Float, default=1.0, comment="错误率阈值(%)")
    
    thread_group_config = Column(JSON, comment="线程组详细配置")
    variables = Column(JSON, comment="JMeter变量配置")
    
    jmeter_properties = Column(JSON, comment="JMeter属性")
    jmeter_args = Column(String(500), comment="JMeter命令行参数")
    
    slave_count = Column(Integer, default=1, comment="压测机数量")
    slave_hosts = Column(JSON, comment="压测机地址列表")
    
    enabled = Column(Boolean, default=True, comment="是否启用")

    # 梯度线程配置
    step_enabled = Column(Boolean, default=False, comment="是否启用梯度线程")
    step_count = Column(Integer, default=5, comment="梯度步数")
    step_duration = Column(Integer, default=60, comment="每步持续时间(秒)")
    step_thread_increment = Column(Integer, default=10, comment="每步增加线程数")

    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    project = relationship('Project', backref='performance_scenarios')
    script = relationship('JMeterScript', backref='scenarios')
    api_sources = relationship('PerformanceTestSource', backref='scenario')
    
    def __repr__(self):
        return f"<PerformanceScenario(id={self.id}, name={self.name})>"


class PerformanceTestExecution(Base):
    """性能测试执行记录"""
    __tablename__ = "performance_executions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    scenario_id = Column(BigInteger, ForeignKey("performance_scenarios.id"), nullable=False)
    script_id = Column(BigInteger, ForeignKey("jmeter_scripts.id"), nullable=False)
    
    name = Column(String(200), comment="执行名称")
    status = Column(String(20), default="draft", comment="状态")
    
    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    actual_duration = Column(Integer, comment="实际持续时间(秒)")
    
    jmeter_process_id = Column(String(50), comment="JMeter进程ID")
    jmeter_log_path = Column(String(500), comment="JMeter日志路径")
    
    result_file_path = Column(String(500), comment="结果文件路径(JTL)")
    report_path = Column(String(500), comment="HTML报告路径")
    
    summary_metrics = Column(JSON, comment="汇总指标")
    detailed_metrics = Column(JSON, comment="详细指标")
    
    avg_tps = Column(Float, comment="平均TPS")
    max_tps = Column(Float, comment="最大TPS")
    avg_rt = Column(Float, comment="平均响应时间(ms)")
    max_rt = Column(Float, comment="最大响应时间(ms)")
    min_rt = Column(Float, comment="最小响应时间(ms)")
    p90_rt = Column(Float, comment="90%响应时间(ms)")
    p95_rt = Column(Float, comment="95%响应时间(ms)")
    p99_rt = Column(Float, comment="99%响应时间(ms)")
    
    total_samples = Column(Integer, comment="总样本数")
    success_samples = Column(Integer, comment="成功样本数")
    error_samples = Column(Integer, comment="失败样本数")
    error_rate = Column(Float, comment="错误率(%)")
    
    throughput_kb = Column(Float, comment="吞吐量(KB/sec)")
    received_kb = Column(Float, comment="接收数据量(KB)")
    sent_kb = Column(Float, comment="发送数据量(KB)")
    
    grafana_dashboard_url = Column(String(500), comment="Grafana仪表盘URL")
    
    passed = Column(Boolean, comment="是否达标")
    pass_reason = Column(Text, comment="达标/未达标原因")
    
    triggered_by = Column(String(50), comment="触发方式: manual/schedule/cicd")
    trigger_data = Column(JSON, comment="触发数据")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    project = relationship('Project', backref='performance_executions')
    scenario = relationship('PerformanceScenario', backref='executions')
    script = relationship('JMeterScript', backref='executions')
    
    def __repr__(self):
        return f"<PerformanceTestExecution(id={self.id}, status={self.status})>"


class PerformanceMetric(Base):
    """性能指标明细"""
    __tablename__ = "performance_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    execution_id = Column(BigInteger, ForeignKey("performance_executions.id"), nullable=False)
    
    timestamp = Column(DateTime, nullable=False, comment="时间戳")
    elapsed_seconds = Column(Integer, comment="运行时长(秒)")
    
    sampler_name = Column(String(200), comment="采样器名称")
    sampler_type = Column(String(50), comment="采样器类型")
    
    tps = Column(Float, comment="当前TPS")
    avg_rt = Column(Float, comment="平均响应时间(ms)")
    min_rt = Column(Float, comment="最小响应时间(ms)")
    max_rt = Column(Float, comment="最大响应时间(ms)")
    
    active_threads = Column(Integer, comment="活跃线程数")
    total_threads = Column(Integer, comment="总线程数")
    
    samples_count = Column(Integer, comment="样本数")
    error_count = Column(Integer, comment="错误数")
    error_rate = Column(Float, comment="错误率(%)")
    
    throughput_kb = Column(Float, comment="吞吐量(KB/sec)")
    
    latency = Column(Float, comment="延迟(ms)")
    connect_time = Column(Float, comment="连接时间(ms)")
    
    response_code = Column(String(10), comment="响应码")
    response_message = Column(String(200), comment="响应消息")
    
    execution = relationship('PerformanceTestExecution', backref='metrics')
    
    def __repr__(self):
        return f"<PerformanceMetric(id={self.id}, execution_id={self.execution_id})>"


class GrafanaDashboard(Base):
    """Grafana仪表盘配置"""
    __tablename__ = "grafana_dashboards"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    
    name = Column(String(200), nullable=False, comment="仪表盘名称")
    dashboard_uid = Column(String(100), comment="Grafana Dashboard UID")
    dashboard_url = Column(String(500), comment="仪表盘URL")
    
    grafana_host = Column(String(200), comment="Grafana服务器地址")
    api_key = Column(String(200), comment="Grafana API Key")
    
    datasource_config = Column(JSON, comment="数据源配置")
    panels_config = Column(JSON, comment="面板配置")
    
    is_embedded = Column(Boolean, default=True, comment="是否嵌入显示")
    embed_mode = Column(String(20), default="iframe", comment="嵌入模式")
    
    enabled = Column(Boolean, default=True, comment="是否启用")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship('Project', backref='grafana_dashboards')
    
    def __repr__(self):
        return f"<GrafanaDashboard(id={self.id}, name={self.name})>"


class PerformanceReport(Base):
    """性能测试报告"""
    __tablename__ = "performance_reports"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    execution_id = Column(BigInteger, ForeignKey("performance_executions.id"), nullable=False)
    
    title = Column(String(200), nullable=False, comment="报告标题")
    summary = Column(Text, comment="报告摘要")
    
    conclusion = Column(Text, comment="测试结论")
    recommendations = Column(JSON, comment="优化建议")
    
    metrics_summary = Column(JSON, comment="指标汇总")
    charts_data = Column(JSON, comment="图表数据")
    
    report_format = Column(String(20), default="html", comment="报告格式: html/pdf")
    report_path = Column(String(500), comment="报告文件路径")
    
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    project = relationship('Project', backref='performance_reports')
    execution = relationship('PerformanceTestExecution', backref='reports')
    
    def __repr__(self):
        return f"<PerformanceReport(id={self.id}, title={self.title})>"


class PerformanceTestSource(Base):
    """API测试用例与性能测试场景的关联桥接表"""
    __tablename__ = "performance_test_sources"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scenario_id = Column(BigInteger, ForeignKey("performance_scenarios.id"), nullable=False, comment="场景ID")
    case_id = Column(BigInteger, ForeignKey("api_test_cases.id"), nullable=False, comment="API测试用例ID")
    source_type = Column(String(20), default="api_test", comment="来源类型: api_test/locust_script/jmeter_script")
    weight = Column(Integer, default=1, comment="执行权重/比例")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    def __repr__(self):
        return f"<PerformanceTestSource(id={self.id}, scenario={self.scenario_id}, case={self.case_id})>"