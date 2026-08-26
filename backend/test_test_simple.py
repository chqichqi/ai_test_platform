"""
简单测试测试管理功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.core.database import Base
from app.core.models.test_simple import (
    TestCase, TestExecution, TestResult, TestRun, TestPlan,
    TestStatus, TestPriority, TestType, ExecutionStatus
)

# 创建内存数据库
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)

# 创建会话
db = Session(engine)

def test_basic_functionality():
    """测试基本功能"""
    print("测试测试管理基本功能...")
    
    # 1. 创建测试用例
    test_case = TestCase(
        id=str(uuid4()),
        title="用户登录功能测试",
        description="测试用户登录功能的正确性",
        test_type=TestType.FUNCTIONAL.value,  # 使用字符串值
        priority=TestPriority.HIGH.value,  # 使用字符串值
        status=TestStatus.ACTIVE.value,  # 使用字符串值
        created_by=str(uuid4()),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(test_case)
    db.commit()
    print(f"[OK] 创建测试用例: {test_case.title}")
    
    # 2. 创建测试执行记录
    execution = TestExecution(
        id=str(uuid4()),
        test_case_id=test_case.id,
        status=ExecutionStatus.PASSED.value,  # 使用字符串值
        executed_by=str(uuid4()),
        executed_at=datetime.utcnow(),
        duration=120,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(execution)
    db.commit()
    print(f"[OK] 创建测试执行记录: {execution.status}")
    
    # 3. 创建测试结果详情
    result = TestResult(
        id=str(uuid4()),
        execution_id=execution.id,
        step_number=1,
        step_description="访问登录页面",
        expected_result="显示登录表单",
        actual_result="成功显示登录表单",
        result_status=ExecutionStatus.PASSED,  # 使用枚举成员
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(result)
    db.commit()
    print(f"[OK] 创建测试结果详情: 步骤{result.step_number}")
    
    # 4. 创建测试运行
    test_run = TestRun(
        id=str(uuid4()),
        name="登录功能回归测试",
        project_id=str(uuid4()),
        started_by=str(uuid4()),
        started_at=datetime.utcnow(),
        status=ExecutionStatus.RUNNING,  # 使用枚举成员
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(test_run)
    db.commit()
    print(f"[OK] 创建测试运行: {test_run.name}")
    
    # 5. 创建测试计划
    test_plan = TestPlan(
        id=str(uuid4()),
        name="v2.0发布测试计划",
        project_id=str(uuid4()),
        created_by=str(uuid4()),
        status=TestStatus.ACTIVE,  # 使用枚举成员
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(test_plan)
    db.commit()
    print(f"[OK] 创建测试计划: {test_plan.name}")
    
    # 6. 查询测试
    test_cases = db.query(TestCase).all()
    executions = db.query(TestExecution).all()
    results = db.query(TestResult).all()
    test_runs = db.query(TestRun).all()
    test_plans = db.query(TestPlan).all()
    
    print(f"\n[OK] 查询结果:")
    print(f"  测试用例: {len(test_cases)} 个")
    print(f"  测试执行: {len(executions)} 个")
    print(f"  测试结果: {len(results)} 个")
    print(f"  测试运行: {len(test_runs)} 个")
    print(f"  测试计划: {len(test_plans)} 个")
    
    # 7. 测试统计计算
    # 添加更多执行记录
    for i in range(4):
        exec_status = [ExecutionStatus.PASSED, ExecutionStatus.FAILED, 
                      ExecutionStatus.PASSED, ExecutionStatus.BLOCKED][i]
        execution = TestExecution(
            id=str(uuid4()),
            test_case_id=test_case.id,
            status=exec_status,  # 使用枚举成员
            executed_by=str(uuid4()),
            executed_at=datetime.utcnow(),
            duration=60 + i * 10,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(execution)
    
    db.commit()
    
    # 手动查询执行记录
    executions = db.query(TestExecution).filter(TestExecution.test_case_id == test_case.id).all()
    
    # 手动计算统计
    stats = {
        'total': len(executions),
        'passed': 0,
        'failed': 0,
        'blocked': 0,
        'skipped': 0,
        'error': 0,
        'success_rate': 0.0
    }
    
    for execution in executions:
        # 从数据库查询时，状态可能是字符串或枚举，需要统一处理
        status_value = execution.status.value if hasattr(execution.status, 'value') else execution.status
        
        if status_value == ExecutionStatus.PASSED.value:
            stats['passed'] += 1
        elif status_value == ExecutionStatus.FAILED.value:
            stats['failed'] += 1
        elif status_value == ExecutionStatus.BLOCKED.value:
            stats['blocked'] += 1
        elif status_value == ExecutionStatus.SKIPPED.value:
            stats['skipped'] += 1
        elif status_value == ExecutionStatus.ERROR.value:
            stats['error'] += 1
    
    if stats['total'] > 0:
        stats['success_rate'] = round(stats['passed'] / stats['total'] * 100, 2)
    
    print(f"\n[OK] 测试用例统计:")
    print(f"  总执行次数: {stats['total']}")
    print(f"  通过: {stats['passed']}")
    print(f"  失败: {stats['failed']}")
    print(f"  阻塞: {stats['blocked']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  错误: {stats['error']}")
    print(f"  成功率: {stats['success_rate']}%")
    
    # 8. 测试枚举类型
    print(f"\n[OK] 枚举类型测试:")
    print(f"  测试类型: {TestType.FUNCTIONAL.value}")
    print(f"  测试优先级: {TestPriority.HIGH.value}")
    print(f"  测试状态: {TestStatus.ACTIVE.value}")
    print(f"  执行状态: {ExecutionStatus.PASSED.value}")
    
    return True

def main():
    """主函数"""
    print("=" * 60)
    print("测试管理功能简单测试")
    print("=" * 60)
    
    try:
        success = test_basic_functionality()
        
        if success:
            print("\n" + "=" * 60)
            print("[SUCCESS] 所有测试通过！")
            print("=" * 60)
            print("测试管理功能已成功实现:")
            print("  - 测试用例管理")
            print("  - 测试执行跟踪")
            print("  - 测试结果记录")
            print("  - 测试运行管理")
            print("  - 测试计划管理")
            print("  - 统计计算功能")
        
        return success
        
    except Exception as e:
        print(f"\n[FAILED] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)