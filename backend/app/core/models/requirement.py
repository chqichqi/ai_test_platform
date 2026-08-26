"""
需求分析与测试用例生成相关模型
对应需求文档 3.3 需求分析与用例生成
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Integer, Enum
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, enum.Enum):
    WORD = "word"
    PDF = "pdf"
    MARKDOWN = "markdown"
    URL = "url"
    TEXT = "text"


class RequirementDocument(Base):
    __tablename__ = "requirement_documents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    version_id = Column(BigInteger, ForeignKey("versions.id"), nullable=False, comment="版本ID")
    name = Column(String(200), comment="文档名称")
    type = Column(String(20), default=DocumentType.TEXT.value, comment="文档类型")
    content = Column(Text, comment="文档内容")
    file_url = Column(String(500), comment="文件URL")
    file_size = Column(Integer, comment="文件大小(字节)")
    parsed_content = Column(JSON, comment="解析后的结构化内容")
    status = Column(String(20), default=DocumentStatus.PENDING.value, comment="状态")
    error_message = Column(Text, comment="错误信息")
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    version = relationship(
        'Version',
        back_populates='requirement_documents'
    )

    def __repr__(self):
        return f"<RequirementDocument(id={self.id}, name={self.name})>"


class TestPoint(Base):
    """测试点 — Step1 提取的可独立测试的功能点（1:1 对应 TestCase）。"""
    __tablename__ = "test_points"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    version_id = Column(BigInteger, ForeignKey("versions.id"), nullable=False, comment="版本ID")
    feature_key = Column(String(200), nullable=False, comment="功能点标识(无空格, 用于去重和diff)")
    name = Column(String(200), comment="功能点名称")
    category = Column(String(50), comment="分类: 指标跳转|筛选|规则|预警|自定义|边界")
    detail = Column(Text, comment="具体描述")
    status = Column(String(20), default="active", comment="active | modified | deprecated")
    test_case_id = Column(BigInteger, ForeignKey("test_cases.id"), comment="关联的测试用例ID")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    version = relationship('Version', back_populates='test_points')
    test_case = relationship('TestCase', back_populates='test_point', foreign_keys=[test_case_id])

    def __repr__(self):
        return f"<TestPoint(id={self.id}, key={self.feature_key})>"


class TestCaseStatus(str, enum.Enum):
    DRAFT = "draft"                     # 待审核（新生成/派生新修订）
    PENDING_REVIEW = "pending_review"   # 待评审
    APPROVED = "approved"               # 已激活（审核通过）
    REJECTED = "rejected"               # 已拒绝
    DEPRECATED = "deprecated"           # 已废弃（功能删除）
    ARCHIVED = "archived"               # 已归档（变更派生时旧行冻结）


class TestCasePriority(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TestCaseType(str, enum.Enum):
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPATIBILITY = "compatibility"
    UI = "ui"
    API = "api"


class ExecutionType(str, enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    version_id = Column(BigInteger, ForeignKey("versions.id"), comment="版本ID")
    module = Column(String(100), comment="所属模块")
    name = Column(String(200), nullable=False, comment="用例名称")
    description = Column(Text, comment="用例描述")
    preconditions = Column(Text, comment="前置条件")
    test_steps = Column(JSON, comment="测试步骤")
    expected_result = Column(Text, comment="预期结果")
    test_data = Column(JSON, comment="测试数据")
    priority = Column(String(10), default=TestCasePriority.P2.value, comment="优先级")
    case_type = Column(String(20), default=TestCaseType.FUNCTIONAL.value, comment="用例类型")
    execution_type = Column(String(20), default=ExecutionType.MANUAL.value, comment="执行方式")
    sort_order = Column(Integer, default=0, comment="执行顺序(10间隔递增)")
    status = Column(String(20), default=TestCaseStatus.DRAFT.value, comment="状态")
    tags = Column(JSON, comment="标签列表")
    auto_script = Column(Text, comment="自动化脚本")
    generated_by = Column(String(20), default="manual", comment="生成方式: ai/manual")
    source_feature = Column(String(200), comment="Step1特征名, 用于变更去重")
    reviewer_id = Column(String(36), comment="审核人ID")
    reviewed_at = Column(DateTime, comment="审核时间")
    review_comment = Column(Text, comment="审核意见")
    # ── 方案B 版本化：逻辑用例维度（同逻辑用例=同 logical_case_id，按 (version_id, revision_no) 演进）──
    logical_case_id = Column(BigInteger, index=True, comment="逻辑用例ID（首次创建=自身id；变更派生时新行共享同一逻辑id）")
    revision_no = Column(Integer, default=1, comment="修订号（逻辑用例第N版，从1递增）")
    derived_from_id = Column(BigInteger, index=True, comment="派生来源行ID（变更即派生时旧行id；无FK，历史只增不改）")
    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    project = relationship(
        'Project',
        back_populates='test_cases'
    )
    version = relationship(
        'Version',
        back_populates='test_cases'
    )
    test_point = relationship(
        'TestPoint',
        back_populates='test_case',
        foreign_keys='TestPoint.test_case_id',
        uselist=False,
    )

    def __repr__(self):
        return f"<TestCase(id={self.id}, name={self.name})>"