"""
简化版测试管理模型定义（避免外键依赖）
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, 
    ForeignKey, Enum, JSON, Index
)
from sqlalchemy.orm import relationship, validates

from app.core.models.base import BaseModel
from app.core.config import settings


class TestStatus(PyEnum):
    """测试状态枚举"""
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class TestPriority(PyEnum):
    """测试优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TestType(PyEnum):
    """测试类型枚举"""
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    SECURITY = "security"
    INTEGRATION = "integration"
    UNIT = "unit"
    REGRESSION = "regression"
    SMOKE = "smoke"
    ACCEPTANCE = "acceptance"
    WEB_UI = "web_ui"


class ExecutionStatus(PyEnum):
    """执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    ERROR = "error"


class SimpleTestCase(BaseModel):
    """简化版测试用例模型（用于统计展示）"""
    
    __tablename__ = 'test_case'
    
    # 基本信息
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    summary = Column(String(500))
    
    # 测试信息
    test_type = Column(
        Enum(TestType, name='test_type_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TestType.FUNCTIONAL.value
    )
    priority = Column(
        Enum(TestPriority, name='test_priority_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TestPriority.MEDIUM.value
    )
    status = Column(
        Enum(TestStatus, name='test_status_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TestStatus.DRAFT.value
    )
    
    # 测试步骤
    preconditions = Column(Text)
    test_steps = Column(JSON)
    expected_results = Column(Text)
    postconditions = Column(Text)
    
    # 关联信息
    project_id = Column(String(36), nullable=True, index=True)
    module = Column(String(100), index=True)
    component = Column(String(100), index=True)
    tags = Column(JSON, default=list)
    
    # 创建和执行信息
    created_by = Column(String(36), nullable=False, index=True)
    assigned_to = Column(String(36), nullable=True, index=True)
    
    # 统计信息
    estimated_time = Column(Integer)
    actual_time = Column(Integer)
    execution_count = Column(Integer, default=0)
    last_executed_at = Column(DateTime)
    
    # 扩展信息
    attachments = Column(JSON, default=list)
    custom_fields = Column(JSON, default=dict)
    notes = Column(Text)
    
    # 关系（暂时注释，避免外键问题）
    # executions = relationship(
    #     'TestExecution',
    #     back_populates='test_case',
    #     lazy='dynamic',
    #     cascade='all, delete-orphan'
    # )
    
    @validates('title')
    def validate_title(self, key, title):
        """验证标题"""
        if not title or len(title.strip()) < 3:
            raise ValueError('Test case title must be at least 3 characters')
        return title.strip()
    
    def get_execution_stats(self):
        """获取执行统计信息"""
        stats = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'blocked': 0,
            'skipped': 0,
            'error': 0,
            'success_rate': 0.0
        }
        
        for execution in self.executions:
            stats['total'] += 1
            if execution.status == ExecutionStatus.PASSED.value:
                stats['passed'] += 1
            elif execution.status == ExecutionStatus.FAILED.value:
                stats['failed'] += 1
            elif execution.status == ExecutionStatus.BLOCKED.value:
                stats['blocked'] += 1
            elif execution.status == ExecutionStatus.SKIPPED.value:
                stats['skipped'] += 1
            elif execution.status == ExecutionStatus.ERROR.value:
                stats['error'] += 1
        
        if stats['total'] > 0:
            stats['success_rate'] = round(stats['passed'] / stats['total'] * 100, 2)
        
        return stats


class TestExecution(BaseModel):
    """测试执行记录模型"""
    
    __tablename__ = 'test_execution'
    
    # 关联信息
    test_case_id = Column(String(36), nullable=False, index=True)
    project_id = Column(String(36), nullable=True, index=True)
    
    # 执行信息
    status = Column(
        Enum(ExecutionStatus, name='execution_status_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExecutionStatus.PENDING.value
    )
    executed_by = Column(String(36), nullable=False, index=True)
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration = Column(Integer)
    # 执行类型（用户 2026-09-02）：区分「UI用例临时验证」与「执行中心场景测试」。
    # scenario=执行中心场景测试（默认）；ui_verify=UI用例页临时执行（仅验证转化用例是否正确，对结果无过多要求）
    execution_type = Column(
        String(30), nullable=False, default='scenario', server_default='scenario',
        comment="执行类型: scenario=执行中心场景测试, ui_verify=UI用例临时验证"
    )
    
    # 执行详情
    actual_results = Column(Text)
    notes = Column(Text)
    evidence = Column(JSON, default=list)
    
    # 失败信息
    failure_reason = Column(Text)
    failure_type = Column(String(100))
    stack_trace = Column(Text)
    
    # 环境信息
    environment = Column(String(100))
    browser = Column(String(50))
    os = Column(String(50))
    device = Column(String(50))
    
    # 关联执行
    test_run_id = Column(String(36), nullable=True, index=True)
    
    # 关系（暂时注释，避免外键问题）
    # test_case = relationship(
    #     'TestCase',
    #     back_populates='executions',
    #     lazy='selectin'
    # )
    # results = relationship(
    #     'TestResult',
    #     back_populates='execution',
    #     lazy='dynamic',
    #     cascade='all, delete-orphan'
    # )
    
    @validates('status')
    def validate_status(self, key, status):
        """验证执行状态"""
        # 接受枚举成员或字符串值
        if hasattr(status, 'value'):
            status_value = status.value
        else:
            status_value = status
            
        if status_value not in [s.value for s in ExecutionStatus]:
            raise ValueError(f'Invalid execution status: {status}')
        return status_value


class TestResult(BaseModel):
    """测试结果详情模型"""
    
    __tablename__ = 'test_result'
    
    # 关联信息
    execution_id = Column(String(36), nullable=False, index=True)
    
    # 结果信息
    step_number = Column(Integer, nullable=False)
    step_description = Column(Text)
    expected_result = Column(Text)
    actual_result = Column(Text)
    result_status = Column(
        Enum(ExecutionStatus, name='result_status_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExecutionStatus.PENDING.value
    )
    
    # 详细信息
    notes = Column(Text)
    evidence = Column(JSON, default=list)
    duration = Column(Integer)
    
    # 关系（暂时注释，避免外键问题）
    # execution = relationship(
    #     'TestExecution',
    #     back_populates='results',
    #     lazy='selectin'
    # )
    
    @validates('step_number')
    def validate_step_number(self, key, step_number):
        """验证步骤编号"""
        if step_number < 1:
            raise ValueError('Step number must be positive')
        return step_number


class TestRun(BaseModel):
    """测试运行批次模型"""
    
    __tablename__ = 'test_run'
    
    # 基本信息
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    
    # 运行信息
    project_id = Column(String(36), nullable=False, index=True)
    environment = Column(String(100))
    test_plan_id = Column(String(36), nullable=True, index=True)
    
    # 执行信息
    started_by = Column(String(36), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    duration = Column(Integer)
    
    # 统计信息
    total_cases = Column(Integer, default=0)
    executed_cases = Column(Integer, default=0)
    passed_cases = Column(Integer, default=0)
    failed_cases = Column(Integer, default=0)
    blocked_cases = Column(Integer, default=0)
    skipped_cases = Column(Integer, default=0)
    error_cases = Column(Integer, default=0)
    
    # 状态信息
    status = Column(
        Enum(ExecutionStatus, name='test_run_status_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExecutionStatus.PENDING.value
    )
    
    # 配置信息
    config = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    
    # 关系（暂时注释，避免外键问题）
    # executions = relationship(
    #     'TestExecution',
    #     lazy='dynamic',
    #     cascade='all, delete-orphan'
    # )
    
    @validates('name')
    def validate_name(self, key, name):
        """验证名称"""
        if not name or len(name.strip()) < 3:
            raise ValueError('Test run name must be at least 3 characters')
        return name.strip()
    
    def calculate_stats(self):
        """计算统计信息"""
        stats = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'blocked': 0,
            'skipped': 0,
            'error': 0,
            'success_rate': 0.0
        }
        
        for execution in self.executions:
            stats['total'] += 1
            if execution.status == ExecutionStatus.PASSED.value:
                stats['passed'] += 1
            elif execution.status == ExecutionStatus.FAILED.value:
                stats['failed'] += 1
            elif execution.status == ExecutionStatus.BLOCKED.value:
                stats['blocked'] += 1
            elif execution.status == ExecutionStatus.SKIPPED.value:
                stats['skipped'] += 1
            elif execution.status == ExecutionStatus.ERROR.value:
                stats['error'] += 1
        
        if stats['total'] > 0:
            stats['success_rate'] = round(stats['passed'] / stats['total'] * 100, 2)
        
        # 更新字段
        self.total_cases = stats['total']
        self.passed_cases = stats['passed']
        self.failed_cases = stats['failed']
        self.blocked_cases = stats['blocked']
        self.skipped_cases = stats['skipped']
        self.error_cases = stats['error']
        self.executed_cases = stats['total']
        
        return stats


class TestPlan(BaseModel):
    """测试计划模型"""
    
    __tablename__ = 'test_plan'
    
    # 基本信息
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    version = Column(String(50), default='1.0')
    
    # 关联信息
    project_id = Column(String(36), nullable=False, index=True)
    
    # 计划信息
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    status = Column(
        Enum(TestStatus, name='test_plan_status_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TestStatus.DRAFT.value
    )
    
    # 创建信息
    created_by = Column(String(36), nullable=False, index=True)
    
    # 配置信息
    objectives = Column(Text)
    scope = Column(Text)
    out_of_scope = Column(Text)
    assumptions = Column(Text)
    risks = Column(Text)
    dependencies = Column(Text)
    
    # 统计信息
    total_cases = Column(Integer, default=0)
    automated_cases = Column(Integer, default=0)
    manual_cases = Column(Integer, default=0)
    
    @validates('name')
    def validate_name(self, key, name):
        """验证名称"""
        if not name or len(name.strip()) < 3:
            raise ValueError('Test plan name must be at least 3 characters')
        return name.strip()