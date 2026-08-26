"""
测试测试管理功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.core.database import Base, get_db
from app.core.models.test_simple import (
    TestCase, TestExecution, TestResult, TestRun, TestPlan,
    TestStatus, TestPriority, TestType, ExecutionStatus
)
from app.core.models.user import User
from app.core.schemas.test import (
    TestCaseCreate, TestExecutionCreate, TestRunCreate, TestPlanCreate,
    TestStep, Attachment, Evidence
)

# 创建内存数据库
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)

# 创建会话
db = Session(engine)

def test_test_case_creation():
    """测试测试用例创建"""
    print("测试测试用例创建...")
    
    # 创建测试用例数据
    test_case_data = TestCaseCreate(
        title="用户登录功能测试",
        description="测试用户登录功能的正确性",
        summary="验证用户可以使用正确的凭据登录系统",
        test_type=TestType.FUNCTIONAL,
        priority=TestPriority.HIGH,
        status=TestStatus.ACTIVE,
        preconditions="1. 系统已启动\n2. 测试用户已注册",
        test_steps=[
            TestStep(
                step_number=1,
                action="访问登录页面",
                expected_result="显示登录表单"
            ),
            TestStep(
                step_number=2,
                action="输入正确的用户名和密码",
                expected_result="成功登录并跳转到主页"
            ),
            TestStep(
                step_number=3,
                action="输入错误的密码",
                expected_result="显示错误消息"
            )
        ],
        expected_results="用户可以使用正确的凭据成功登录，错误的凭据会被拒绝",
        postconditions="用户已登录或保持在登录页面",
        module="认证模块",
        component="登录组件",
        tags=["登录", "认证", "功能测试"],
        estimated_time=15,
        attachments=[
            Attachment(
                name="登录页面截图",
                url="/attachments/login_screenshot.png",
                type="image/png",
                size=102400
            )
        ],
        custom_fields={
            "browser_compatibility": ["Chrome", "Firefox", "Edge"],
            "mobile_support": True
        },
        notes="需要测试多种浏览器兼容性"
    )
    
    # 创建测试用例对象
    test_case = TestCase(
        **test_case_data.model_dump(exclude={"project_id", "assigned_to"}),
        id=str(uuid4()),
        created_by=str(uuid4()),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    # 保存到数据库
    db.add(test_case)
    db.commit()
    db.refresh(test_case)
    
    print(f"✓ 测试用例创建成功: {test_case.title}")
    print(f"  ID: {test_case.id}")
    print(f"  类型: {test_case.test_type}")
    print(f"  优先级: {test_case.priority}")
    print(f"  状态: {test_case.status}")
    print(f"  标签: {test_case.tags}")
    
    return test_case

def test_test_execution_creation(test_case):
    """测试测试执行记录创建"""
    print("\n测试测试执行记录创建...")
    
    # 创建测试执行数据
    execution_data = TestExecutionCreate(
        test_case_id=test_case.id,
        status=ExecutionStatus.PASSED,
        actual_results="所有测试步骤都通过，功能正常",
        notes="在Chrome浏览器中测试通过",
        evidence=[
            Evidence(
                type="screenshot",
                url="/evidence/login_success.png",
                description="登录成功页面截图"
            )
        ],
        environment="测试环境",
        browser="Chrome 120",
        os="Windows 11",
        device="Desktop",
        duration=120  # 2分钟
    )
    
    # 创建测试执行对象
    execution = TestExecution(
        **execution_data.model_dump(exclude={"test_case_id", "project_id", "test_run_id"}),
        id=str(uuid4()),
        test_case_id=test_case.id,
        executed_by=str(uuid4()),
        executed_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    # 保存到数据库
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    print(f"✓ 测试执行记录创建成功")
    print(f"  测试用例: {test_case.title}")
    print(f"  执行状态: {execution.status}")
    print(f"  执行时间: {execution.executed_at}")
    print(f"  执行时长: {execution.duration}秒")
    
    return execution

def test_test_run_creation():
    """测试测试运行创建"""
    print("\n测试测试运行创建...")
    
    # 创建测试运行数据
    test_run_data = TestRunCreate(
        name="登录功能回归测试",
        description="登录功能的回归测试运行",
        project_id=str(uuid4()),
        environment="预发布环境",
        config={
            "browser": "Chrome",
            "parallel_execution": True,
            "timeout": 300
        },
        tags=["回归测试", "登录", "v2.0"]
    )
    
    # 创建测试运行对象
    test_run = TestRun(
        **test_run_data.model_dump(exclude={"project_id"}),
        id=str(uuid4()),
        project_id=test_run_data.project_id,
        started_by=str(uuid4()),
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    # 保存到数据库
    db.add(test_run)
    db.commit()
    db.refresh(test_run)
    
    print(f"✓ 测试运行创建成功: {test_run.name}")
    print(f"  环境: {test_run.environment}")
    print(f"  状态: {test_run.status}")
    print(f"  开始时间: {test_run.started_at}")
    
    return test_run

def test_test_plan_creation():
    """测试测试计划创建"""
    print("\n测试测试计划创建...")
    
    # 创建测试计划数据
    test_plan_data = TestPlanCreate(
        name="v2.0发布测试计划",
        description="v2.0版本发布的完整测试计划",
        version="2.0",
        project_id=str(uuid4()),
        start_date=datetime(2024, 1, 15),
        end_date=datetime(2024, 1, 30),
        status=TestStatus.ACTIVE,
        objectives="确保v2.0版本的质量和稳定性",
        scope="所有核心功能模块",
        out_of_scope="第三方集成和性能测试",
        assumptions="测试环境已准备就绪",
        risks="时间紧迫，测试覆盖率可能不足",
        dependencies="开发团队按时交付功能",
        total_cases=150,
        automated_cases=100,
        manual_cases=50
    )
    
    # 创建测试计划对象
    test_plan = TestPlan(
        **test_plan_data.model_dump(exclude={"project_id"}),
        id=str(uuid4()),
        project_id=test_plan_data.project_id,
        created_by=str(uuid4()),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    # 保存到数据库
    db.add(test_plan)
    db.commit()
    db.refresh(test_plan)
    
    print(f"✓ 测试计划创建成功: {test_plan.name}")
    print(f"  版本: {test_plan.version}")
    print(f"  状态: {test_plan.status}")
    print(f"  开始日期: {test_plan.start_date}")
    print(f"  结束日期: {test_plan.end_date}")
    print(f"  总用例数: {test_plan.total_cases}")
    
    return test_plan

def test_query_operations():
    """测试查询操作"""
    print("\n测试查询操作...")
    
    # 查询所有测试用例
    test_cases = db.query(TestCase).all()
    print(f"✓ 查询到 {len(test_cases)} 个测试用例")
    
    # 查询所有测试执行
    executions = db.query(TestExecution).all()
    print(f"✓ 查询到 {len(executions)} 个测试执行记录")
    
    # 查询所有测试运行
    test_runs = db.query(TestRun).all()
    print(f"✓ 查询到 {len(test_runs)} 个测试运行")
    
    # 查询所有测试计划
    test_plans = db.query(TestPlan).all()
    print(f"✓ 查询到 {len(test_plans)} 个测试计划")
    
    return test_cases, executions, test_runs, test_plans

def test_statistics_calculation(test_case):
    """测试统计计算"""
    print("\n测试统计计算...")
    
    # 创建多个测试执行记录
    statuses = [
        ExecutionStatus.PASSED,
        ExecutionStatus.FAILED,
        ExecutionStatus.PASSED,
        ExecutionStatus.BLOCKED,
        ExecutionStatus.SKIPPED
    ]
    
    for i, status in enumerate(statuses):
        execution = TestExecution(
            id=str(uuid4()),
            test_case_id=test_case.id,
            status=status.value,
            executed_by=str(uuid4()),
            executed_at=datetime.utcnow(),
            duration=60 + i * 10,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(execution)
    
    db.commit()
    
    # 重新加载测试用例以获取关联的执行记录
    db.refresh(test_case)
    
    # 计算统计信息
    stats = test_case.get_execution_stats()
    
    print(f"✓ 测试用例统计计算成功")
    print(f"  总执行次数: {stats['total']}")
    print(f"  通过: {stats['passed']}")
    print(f"  失败: {stats['failed']}")
    print(f"  阻塞: {stats['blocked']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  错误: {stats['error']}")
    print(f"  成功率: {stats['success_rate']}%")
    
    return stats

def main():
    """主测试函数"""
    print("=" * 60)
    print("测试管理功能测试")
    print("=" * 60)
    
    try:
        # 测试各个功能
        test_case = test_test_case_creation()
        execution = test_test_execution_creation(test_case)
        test_run = test_test_run_creation()
        test_plan = test_test_plan_creation()
        
        # 测试查询操作
        test_cases, executions, test_runs, test_plans = test_query_operations()
        
        # 测试统计计算
        stats = test_statistics_calculation(test_case)
        
        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)
        print(f"总结:")
        print(f"  • 创建了 {len(test_cases)} 个测试用例")
        print(f"  • 创建了 {len(executions)} 个测试执行记录")
        print(f"  • 创建了 {len(test_runs)} 个测试运行")
        print(f"  • 创建了 {len(test_plans)} 个测试计划")
        print(f"  • 测试用例执行统计: {stats['passed']}/{stats['total']} 通过")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)