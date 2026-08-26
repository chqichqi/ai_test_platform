"""
需求变更记录模型
用于追踪需求变更、分析影响、管理审核流程
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, JSON, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship, backref
import enum

from app.core.database import Base


class ChangeType(str, enum.Enum):
    """变更类型"""
    ADDED = "added"           # 新增功能
    MODIFIED = "modified"     # 修改功能
    DELETED = "deleted"       # 删除功能
    UNCHANGED = "unchanged"   # 无变化


class ChangeImpactLevel(str, enum.Enum):
    """变更影响级别"""
    HIGH = "high"       # 高影响：核心功能变更，需全面重新测试
    MEDIUM = "medium"   # 中影响：部分功能变更，需局部重新测试
    LOW = "low"         # 低影响：边缘功能变更，可选择性测试


class ChangeRecordStatus(str, enum.Enum):
    """变更记录状态"""
    PENDING = "pending"         # 待审核
    APPROVED = "approved"       # 已批准
    REJECTED = "rejected"       # 已拒绝
    PROCESSING = "processing"   # 正在处理
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 处理失败


class ChangeAction(str, enum.Enum):
    """变更处理动作"""
    GENERATE_NEW = "generate_new"       # 生成新测试用例
    UPDATE_EXISTING = "update_existing" # 更新现有用例
    DEPRECATE = "deprecate"             # 废弃现有用例
    KEEP_OLD = "keep_old"               # 保留旧用例（不处理）
    ARCHIVE = "archive"                 # 归档旧用例


class RequirementChangeRecord(Base):
    """需求变更记录"""
    __tablename__ = "requirement_change_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    version_id = Column(BigInteger, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False, comment="版本ID")
    requirement_document_id = Column(BigInteger, ForeignKey("requirement_documents.id", ondelete="SET NULL"), comment="原需求文档ID")
    
    change_type = Column(String(20), nullable=False, comment="变更类型: added/modified/deleted/unchanged")
    
    module_name = Column(String(100), nullable=False, comment="模块名称")
    old_description = Column(Text, comment="原功能描述")
    new_description = Column(Text, comment="新功能描述")
    
    impact_level = Column(String(10), default=ChangeImpactLevel.MEDIUM.value, comment="影响级别: high/medium/low")
    
    affected_test_cases = Column(JSON, comment="受影响的测试用例ID列表")
    affected_test_cases_count = Column(Integer, default=0, comment="受影响测试用例数量")
    
    suggested_action = Column(String(20), comment="建议处理动作")
    suggested_reason = Column(Text, comment="建议原因说明")
    
    status = Column(String(20), default=ChangeRecordStatus.PENDING.value, comment="状态: pending/approved/rejected/...")
    
    action_taken = Column(String(20), comment="实际执行的动作")
    keep_old_cases = Column(Boolean, default=False, comment="是否保留旧测试用例")
    
    new_test_cases = Column(JSON, comment="新生成的测试用例ID列表")
    new_test_cases_count = Column(Integer, default=0, comment="新生成测试用例数量")
    
    created_by = Column(String(36), ForeignKey("user.id"), comment="创建人ID（上传补充需求的人）")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    reviewed_by = Column(String(36), ForeignKey("user.id"), comment="审核人ID")
    reviewed_at = Column(DateTime, comment="审核时间")
    review_comment = Column(Text, comment="审核意见")
    
    processed_by = Column(String(36), ForeignKey("user.id"), comment="处理人ID")
    processed_at = Column(DateTime, comment="处理完成时间")
    
    error_message = Column(Text, comment="错误信息")
    
    version = relationship(
        'Version',
        backref=backref('requirement_change_records', cascade='all, delete-orphan')
    )
    
    requirement_document = relationship(
        'RequirementDocument',
        backref='change_records'
    )
    
    creator = relationship(
        'User',
        foreign_keys=[created_by],
        backref='created_change_records'
    )
    
    reviewer = relationship(
        'User',
        foreign_keys=[reviewed_by],
        backref='reviewed_change_records'
    )
    
    processor = relationship(
        'User',
        foreign_keys=[processed_by],
        backref='processed_change_records'
    )
    
    def __repr__(self):
        return f"<RequirementChangeRecord(id={self.id}, module={self.module_name}, type={self.change_type})>"


class RequirementChangeBatch(Base):
    """需求变更批次（一次补充需求上传对应一个批次）"""
    __tablename__ = "requirement_change_batches"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    version_id = Column(BigInteger, ForeignKey("versions.id", ondelete="CASCADE"), nullable=False, comment="版本ID")
    
    batch_name = Column(String(200), comment="批次名称")
    batch_description = Column(Text, comment="批次描述")
    
    original_requirement_doc = Column(Text, comment="原需求文档内容")
    supplement_requirement_doc = Column(Text, comment="补充需求文档内容")
    supplement_file_path = Column(String(500), comment="补充需求文件路径")
    supplement_file_type = Column(String(20), comment="补充需求文件类型")
    
    change_summary = Column(JSON, comment="变更摘要")
    added_count = Column(Integer, default=0, comment="新增功能数量")
    modified_count = Column(Integer, default=0, comment="修改功能数量")
    deleted_count = Column(Integer, default=0, comment="删除功能数量")
    unchanged_count = Column(Integer, default=0, comment="无变化功能数量")
    
    total_affected_cases = Column(Integer, default=0, comment="总受影响测试用例数")
    total_new_cases = Column(Integer, default=0, comment="总新生成测试用例数")
    
    status = Column(String(20), default=ChangeRecordStatus.PENDING.value, comment="批次状态")
    
    created_by = Column(String(36), ForeignKey("user.id"), comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    
    reviewed_by = Column(String(36), ForeignKey("user.id"), comment="审核人ID")
    reviewed_at = Column(DateTime, comment="审核时间")
    
    completed_at = Column(DateTime, comment="完成时间")
    
    version = relationship(
        'Version',
        backref=backref('requirement_change_batches', cascade='all, delete-orphan')
    )
    
    creator = relationship(
        'User',
        foreign_keys=[created_by],
        backref='created_change_batches'
    )
    
    reviewer = relationship(
        'User',
        foreign_keys=[reviewed_by],
        backref='reviewed_change_batches'
    )
    
    change_records = relationship(
        'RequirementChangeRecord',
        backref='change_batch',
        foreign_keys='RequirementChangeRecord.version_id',
        primaryjoin='RequirementChangeBatch.version_id == RequirementChangeRecord.version_id',
        lazy='dynamic'
    )
    
    def __repr__(self):
        return f"<RequirementChangeBatch(id={self.id}, version_id={self.version_id})>"