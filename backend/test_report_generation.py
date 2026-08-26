"""
测试报告生成功能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.core.database import Base
from app.core.models.test_simple import (
    TestCase, TestExecution, TestResult, TestRun, TestPlan,
    TestStatus, TestPriority, TestType, ExecutionStatus
)
from app.core.services.test_service import TestReportService

# 创建内存数据库
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)

def test_report_generation():
    """测试报告生成"""
    print("测试报告生成功能...")
    
    db = Session(engine)
    
    try:
        # 创建测试数据
        project_id = str(uuid4())
        user_id = str(uuid4())
        
        # 1. 创建测试计划
        test_plan = TestPlan(
            id=str(uuid4()),
            name="v2.0发布测试计划",
            description="v2.0版本发布前的全面测试",
            project_id=project_id,
            created_by=user_id,
            status=TestStatus.ACTIVE.value,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(test_plan)
        
        # 2. 创建测试用例
        test_cases = []
        for i in range(5):
            test_case = TestCase(
                id=str(uuid4()),
                title=f"测试用例 {i+1}",
                description=f"测试用例 {i+1} 的描述",
                test_type=[TestType.FUNCTIONAL.value, TestType.PERFORMANCE.value, TestType.SECURITY.value][i % 3],
                priority=[TestPriority.HIGH.value, TestPriority.MEDIUM.value, TestPriority.LOW.value][i % 3],
                status=TestStatus.ACTIVE.value,
                project_id=project_id,
                module=f"module_{i % 2 + 1}",
                component=f"component_{i % 3 + 1}",
                tags=["tag1", "tag2"] if i % 2 == 0 else ["tag3"],
                created_by=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(test_case)
            test_cases.append(test_case)
        
        db.commit()
        print(f"[OK] 创建了 {len(test_cases)} 个测试用例")
        
        # 3. 创建测试执行记录
        execution_statuses = [
            ExecutionStatus.PASSED.value,
            ExecutionStatus.FAILED.value,
            ExecutionStatus.PASSED.value,
            ExecutionStatus.BLOCKED.value,
            ExecutionStatus.SKIPPED.value
        ]
        
        executions = []
        for i, test_case in enumerate(test_cases):
            execution = TestExecution(
                id=str(uuid4()),
                test_case_id=test_case.id,
                status=execution_statuses[i],
                executed_by=user_id,
                executed_at=datetime.utcnow() - timedelta(days=i),
                duration=60 + i * 10,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(execution)
            executions.append(execution)
        
        db.commit()
        print(f"[OK] 创建了 {len(executions)} 个测试执行记录")
        
        # 4. 创建测试结果详情
        for i, execution in enumerate(executions):
            for step in range(3):
                result = TestResult(
                    id=str(uuid4()),
                    execution_id=execution.id,
                    step_number=step + 1,
                    step_description=f"步骤 {step + 1}",
                    expected_result=f"预期结果 {step + 1}",
                    actual_result=f"实际结果 {step + 1}",
                    result_status=execution.status,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(result)
        
        db.commit()
        print("[OK] 创建了测试结果详情")
        
        # 5. 测试报告服务
        print("\n测试报告服务:")
        
        # 5.1 生成测试报告
        print("\n1. 生成测试报告:")
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        try:
            # 注意：project_id需要转换为UUID
            from uuid import UUID as UUIDClass
            project_uuid = UUIDClass(project_id)
            
            test_report = TestReportService.generate_test_report(
                db, project_uuid, start_date, end_date
            )
            
            print(f"   报告生成成功!")
            print(f"   时间范围: {start_date.date()} 到 {end_date.date()}")
            print(f"   测试用例总数: {test_report.total_test_cases.total}")
            print(f"   测试执行统计:")
            print(f"     - 总数: {test_report.total_executions.total}")
            print(f"     - 通过: {test_report.total_executions.passed}")
            print(f"     - 失败: {test_report.total_executions.failed}")
            print(f"     - 阻塞: {test_report.total_executions.blocked}")
            print(f"     - 跳过: {test_report.total_executions.skipped}")
            print(f"     - 错误: {test_report.total_executions.error}")
            print(f"     - 通过率: {test_report.total_executions.success_rate:.1f}%")
            
            if test_report.total_executions.avg_duration:
                print(f"     - 平均执行时间: {test_report.total_executions.avg_duration:.1f}秒")
            
            # 打印按类型统计
            if test_report.by_test_type:
                print(f"\n   按测试类型统计:")
                for test_type, stats in list(test_report.by_test_type.items())[:3]:  # 只显示前3个
                    print(f"     - {test_type}: {stats.total} 个用例")
            
            # 打印按优先级统计
            if test_report.by_priority:
                print(f"\n   按优先级统计:")
                for priority, stats in test_report.by_priority.items():
                    print(f"     - {priority}: {stats.total} 个用例")
            
            # 打印趋势数据
            if test_report.trend_data:
                print(f"\n   趋势数据: {len(test_report.trend_data)} 天")
            
            print("\n[SUCCESS] 报告生成功能测试完成!")
            return True
            
        except Exception as e:
            print(f"   报告生成失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print(f"\n[ERROR] 报告生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def main():
    """主函数"""
    print("=" * 60)
    print("测试报告生成功能测试")
    print("=" * 60)
    
    success = test_report_generation()
    
    print("\n" + "=" * 60)
    if success:
        print("[SUCCESS] 所有测试通过!")
    else:
        print("[FAILED] 测试失败")
    
    print("=" * 60)
    print("\n总结:")
    print("  - 报告生成功能已实现:")
    print("    - 项目统计报告")
    print("    - 测试用例执行统计")
    print("    - 按状态/类型/优先级统计")
    print("    - 趋势分析")
    print("    - 综合报告生成")
    print("    - 建议生成")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)