"""
测试管理服务
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
from fastapi import HTTPException
from starlette import status

from app.core.models.test_simple import (
    SimpleTestCase, TestExecution, TestResult, TestRun, TestPlan,
    TestStatus, TestPriority, TestType, ExecutionStatus
)
from app.core.schemas.test import (
    TestCaseCreate, TestCaseUpdate, TestCaseFilter,
    TestExecutionCreate, TestExecutionUpdate, TestExecutionFilter,
    TestRunCreate, TestRunUpdate, TestRunFilter,
    TestPlanCreate, TestPlanUpdate,
    TestStats, TestReport
)
from app.core.models.user import User
from app.core.responses import ErrorResponse


class TestCaseService:
    """测试用例服务"""
    
    @staticmethod
    def create_test_case(
        db: Session, 
        test_case_data: TestCaseCreate, 
        current_user: User
    ) -> SimpleTestCase:
        """创建测试用例"""
        # 检查项目是否存在（如果提供了project_id）
        if test_case_data.project_id:
            # TODO: 检查项目是否存在
            pass
        
        # 检查分配给的用户是否存在（如果提供了assigned_to）
        if test_case_data.assigned_to:
            assigned_user = db.query(User).filter(
                User.id == test_case_data.assigned_to,
                User.is_active == True
            ).first()
            if not assigned_user:
                raise HTTPException(
                    status_code=404,
                    detail="指定的分配用户不存在"
                )
        
        # 创建测试用例
        test_case = SimpleTestCase(
            **test_case_data.model_dump(exclude={"project_id", "assigned_to"}),
            created_by=current_user.id,
            project_id=test_case_data.project_id,
            assigned_to=test_case_data.assigned_to
        )
        
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        
        return test_case
    
    @staticmethod
    def get_test_case(db: Session, test_case_id: UUID) -> Optional[SimpleTestCase]:
        """获取测试用例"""
        return db.query(SimpleTestCase).filter(
            SimpleTestCase.id == test_case_id,
            SimpleTestCase.deleted_at.is_(None)
        ).first()
    
    @staticmethod
    def get_test_cases(
        db: Session, 
        filter_data: TestCaseFilter,
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[List[SimpleTestCase], int]:
        """获取测试用例列表"""
        query = db.query(SimpleTestCase).filter(SimpleTestCase.deleted_at.is_(None))
        
        # 应用过滤器
        if filter_data.project_id:
            query = query.filter(SimpleTestCase.project_id == filter_data.project_id)
        
        if filter_data.test_type:
            query = query.filter(SimpleTestCase.test_type == filter_data.test_type.value)
        
        if filter_data.priority:
            query = query.filter(SimpleTestCase.priority == filter_data.priority.value)
        
        if filter_data.status:
            query = query.filter(SimpleTestCase.status == filter_data.status.value)
        
        if filter_data.module:
            query = query.filter(SimpleTestCase.module == filter_data.module)
        
        if filter_data.component:
            query = query.filter(SimpleTestCase.component == filter_data.component)
        
        if filter_data.created_by:
            query = query.filter(SimpleTestCase.created_by == filter_data.created_by)
        
        if filter_data.assigned_to:
            query = query.filter(SimpleTestCase.assigned_to == filter_data.assigned_to)
        
        if filter_data.tags:
            # 使用JSON包含查询
            for tag in filter_data.tags:
                query = query.filter(SimpleTestCase.tags.contains([tag]))
        
        if filter_data.search:
            search_pattern = f"%{filter_data.search}%"
            query = query.filter(
                or_(
                    SimpleTestCase.title.ilike(search_pattern),
                    SimpleTestCase.description.ilike(search_pattern),
                    SimpleTestCase.summary.ilike(search_pattern)
                )
            )
        
        # 获取总数
        total = query.count()
        
        # 应用分页和排序
        test_cases = query.order_by(
            desc(SimpleTestCase.created_at)
        ).offset(skip).limit(limit).all()
        
        return test_cases, total
    
    @staticmethod
    def update_test_case(
        db: Session, 
        test_case_id: UUID, 
        update_data: TestCaseUpdate
    ) -> Optional[SimpleTestCase]:
        """更新测试用例"""
        test_case = SimpleTestCaseService.get_test_case(db, test_case_id)
        if not test_case:
            return None
        
        # 检查分配给的用户是否存在（如果提供了assigned_to）
        if update_data.assigned_to:
            assigned_user = db.query(User).filter(
                User.id == update_data.assigned_to,
                User.is_active == True
            ).first()
            if not assigned_user:
                raise HTTPException(
                    status_code=404,
                    detail="指定的分配用户不存在"
                )
        
        # 更新字段
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(test_case, field, value)
        
        db.commit()
        db.refresh(test_case)
        
        return test_case
    
    @staticmethod
    def delete_test_case(db: Session, test_case_id: UUID) -> bool:
        """删除测试用例（软删除）"""
        test_case = SimpleTestCaseService.get_test_case(db, test_case_id)
        if not test_case:
            return False
        
        test_case.soft_delete()
        db.commit()
        
        return True
    
    @staticmethod
    def get_test_case_stats(db: Session, test_case_id: UUID) -> Optional[Dict[str, Any]]:
        """获取测试用例统计信息"""
        test_case = SimpleTestCaseService.get_test_case(db, test_case_id)
        if not test_case:
            return None
        
        return test_case.get_execution_stats()


class TestExecutionService:
    """测试执行服务"""
    
    @staticmethod
    def create_test_execution(
        db: Session, 
        execution_data: TestExecutionCreate, 
        current_user: User
    ) -> TestExecution:
        """创建测试执行记录"""
        # 检查测试用例是否存在
        test_case = SimpleTestCaseService.get_test_case(db, execution_data.test_case_id)
        if not test_case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="指定的分配用户不存在"
                )
        
        # 检查项目是否存在（如果提供了project_id）
        if execution_data.project_id:
            # TODO: 检查项目是否存在
            pass
        
        # 检查测试运行是否存在（如果提供了test_run_id）
        if execution_data.test_run_id:
            test_run = db.query(TestRun).filter(
                TestRun.id == execution_data.test_run_id,
                TestRun.deleted_at.is_(None)
            ).first()
            if not test_run:
                raise HTTPException(
                    status_code=404,
                    detail="测试运行不存在"
                )
        
        # 创建测试执行记录
        execution = TestExecution(
            **execution_data.model_dump(exclude={"test_case_id", "project_id", "test_run_id"}),
            test_case_id=execution_data.test_case_id,
            project_id=execution_data.project_id or test_case.project_id,
            test_run_id=execution_data.test_run_id,
            executed_by=current_user.id
        )
        
        # 更新测试用例的执行统计
        test_case.execution_count += 1
        test_case.last_executed_at = datetime.utcnow()
        
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        return execution
    
    @staticmethod
    def get_test_execution(db: Session, execution_id: UUID) -> Optional[TestExecution]:
        """获取测试执行记录"""
        return db.query(TestExecution).filter(
            TestExecution.id == execution_id,
            TestExecution.deleted_at.is_(None)
        ).first()
    
    @staticmethod
    def get_test_executions(
        db: Session, 
        filter_data: TestExecutionFilter,
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[List[TestExecution], int]:
        """获取测试执行记录列表"""
        query = db.query(TestExecution).filter(TestExecution.deleted_at.is_(None))
        
        # 应用过滤器
        if filter_data.test_case_id:
            query = query.filter(TestExecution.test_case_id == filter_data.test_case_id)
        
        if filter_data.project_id:
            query = query.filter(TestExecution.project_id == filter_data.project_id)
        
        if filter_data.test_run_id:
            query = query.filter(TestExecution.test_run_id == filter_data.test_run_id)
        
        if filter_data.status:
            query = query.filter(TestExecution.status == filter_data.status.value)
        
        if filter_data.executed_by:
            query = query.filter(TestExecution.executed_by == filter_data.executed_by)
        
        if filter_data.environment:
            query = query.filter(TestExecution.environment == filter_data.environment)
        
        if filter_data.start_date:
            query = query.filter(TestExecution.executed_at >= filter_data.start_date)
        
        if filter_data.end_date:
            query = query.filter(TestExecution.executed_at <= filter_data.end_date)
        
        # 获取总数
        total = query.count()
        
        # 应用分页和排序
        executions = query.order_by(
            desc(TestExecution.executed_at)
        ).offset(skip).limit(limit).all()
        
        return executions, total
    
    @staticmethod
    def update_test_execution(
        db: Session, 
        execution_id: UUID, 
        update_data: TestExecutionUpdate
    ) -> Optional[TestExecution]:
        """更新测试执行记录"""
        execution = TestExecutionService.get_test_execution(db, execution_id)
        if not execution:
            return None
        
        # 更新字段
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(execution, field, value)
        
        db.commit()
        db.refresh(execution)
        
        return execution
    
    @staticmethod
    def delete_test_execution(db: Session, execution_id: UUID) -> bool:
        """删除测试执行记录（软删除）"""
        execution = TestExecutionService.get_test_execution(db, execution_id)
        if not execution:
            return False
        
        execution.soft_delete()
        db.commit()
        
        return True


class TestRunService:
    """测试运行服务"""
    
    @staticmethod
    def create_test_run(
        db: Session, 
        test_run_data: TestRunCreate, 
        current_user: User
    ) -> TestRun:
        """创建测试运行"""
        # 检查项目是否存在
        # TODO: 检查项目是否存在
        
        # 检查测试计划是否存在（如果提供了test_plan_id）
        if test_run_data.test_plan_id:
            test_plan = db.query(TestPlan).filter(
                TestPlan.id == test_run_data.test_plan_id,
                TestPlan.deleted_at.is_(None)
            ).first()
            if not test_plan:
                raise HTTPException(
                    status_code=404,
                    detail="测试计划不存在"
                )
        
        # 创建测试运行
        test_run = TestRun(
            **test_run_data.model_dump(exclude={"project_id"}),
            project_id=test_run_data.project_id,
            started_by=current_user.id
        )
        
        db.add(test_run)
        db.commit()
        db.refresh(test_run)
        
        return test_run
    
    @staticmethod
    def get_test_run(db: Session, test_run_id: UUID) -> Optional[TestRun]:
        """获取测试运行"""
        return db.query(TestRun).filter(
            TestRun.id == test_run_id,
            TestRun.deleted_at.is_(None)
        ).first()
    
    @staticmethod
    def get_test_runs(
        db: Session, 
        filter_data: TestRunFilter,
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[List[TestRun], int]:
        """获取测试运行列表"""
        query = db.query(TestRun).filter(TestRun.deleted_at.is_(None))
        
        # 应用过滤器
        if filter_data.project_id:
            query = query.filter(TestRun.project_id == filter_data.project_id)
        
        if filter_data.test_plan_id:
            query = query.filter(TestRun.test_plan_id == filter_data.test_plan_id)
        
        if filter_data.status:
            query = query.filter(TestRun.status == filter_data.status.value)
        
        if filter_data.started_by:
            query = query.filter(TestRun.started_by == filter_data.started_by)
        
        if filter_data.environment:
            query = query.filter(TestRun.environment == filter_data.environment)
        
        if filter_data.start_date:
            query = query.filter(TestRun.started_at >= filter_data.start_date)
        
        if filter_data.end_date:
            query = query.filter(TestRun.started_at <= filter_data.end_date)
        
        # 获取总数
        total = query.count()
        
        # 应用分页和排序
        test_runs = query.order_by(
            desc(TestRun.started_at)
        ).offset(skip).limit(limit).all()
        
        return test_runs, total
    
    @staticmethod
    def update_test_run(
        db: Session, 
        test_run_id: UUID, 
        update_data: TestRunUpdate
    ) -> Optional[TestRun]:
        """更新测试运行"""
        test_run = TestRunService.get_test_run(db, test_run_id)
        if not test_run:
            return None
        
        # 更新字段
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(test_run, field, value)
        
        # 如果状态变为完成，设置完成时间
        if update_data.status == ExecutionStatus.PASSED or update_data.status == ExecutionStatus.FAILED:
            if not test_run.completed_at:
                test_run.completed_at = datetime.utcnow()
        
        db.commit()
        db.refresh(test_run)
        
        return test_run
    
    @staticmethod
    def delete_test_run(db: Session, test_run_id: UUID) -> bool:
        """删除测试运行（软删除）"""
        test_run = TestRunService.get_test_run(db, test_run_id)
        if not test_run:
            return False
        
        test_run.soft_delete()
        db.commit()
        
        return True
    
    @staticmethod
    def add_test_case_to_run(
        db: Session, 
        test_run_id: UUID, 
        test_case_id: UUID
    ) -> bool:
        """添加测试用例到测试运行"""
        test_run = TestRunService.get_test_run(db, test_run_id)
        test_case = SimpleTestCaseService.get_test_case(db, test_case_id)
        
        if not test_run or not test_case:
            return False
        
        # 创建测试执行记录（执行中心场景测试类型）
        execution = TestExecution(
            test_case_id=test_case_id,
            project_id=test_case.project_id,
            test_run_id=test_run_id,
            executed_by=test_run.started_by,
            status=ExecutionStatus.PENDING,
            execution_type='scenario',
        )
        
        db.add(execution)
        
        # 更新测试运行统计
        test_run.total_cases += 1
        
        db.commit()
        
        return True
    
    @staticmethod
    def get_test_run_stats(db: Session, test_run_id: UUID) -> Optional[Dict[str, Any]]:
        """获取测试运行统计信息"""
        test_run = TestRunService.get_test_run(db, test_run_id)
        if not test_run:
            return None
        
        return test_run.calculate_stats()


class TestPlanService:
    """测试计划服务"""
    
    @staticmethod
    def create_test_plan(
        db: Session, 
        test_plan_data: TestPlanCreate, 
        current_user: User
    ) -> TestPlan:
        """创建测试计划"""
        # 检查项目是否存在
        # TODO: 检查项目是否存在
        
        # 创建测试计划
        test_plan = TestPlan(
            **test_plan_data.model_dump(exclude={"project_id"}),
            project_id=test_plan_data.project_id,
            created_by=current_user.id
        )
        
        db.add(test_plan)
        db.commit()
        db.refresh(test_plan)
        
        return test_plan
    
    @staticmethod
    def get_test_plan(db: Session, test_plan_id: UUID) -> Optional[TestPlan]:
        """获取测试计划"""
        return db.query(TestPlan).filter(
            TestPlan.id == test_plan_id,
            TestPlan.deleted_at.is_(None)
        ).first()
    
    @staticmethod
    def get_test_plans(
        db: Session, 
        project_id: Optional[UUID] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[List[TestPlan], int]:
        """获取测试计划列表"""
        query = db.query(TestPlan).filter(TestPlan.deleted_at.is_(None))
        
        if project_id:
            query = query.filter(TestPlan.project_id == project_id)
        
        # 获取总数
        total = query.count()
        
        # 应用分页和排序
        test_plans = query.order_by(
            desc(TestPlan.created_at)
        ).offset(skip).limit(limit).all()
        
        return test_plans, total
    
    @staticmethod
    def update_test_plan(
        db: Session, 
        test_plan_id: UUID, 
        update_data: TestPlanUpdate
    ) -> Optional[TestPlan]:
        """更新测试计划"""
        test_plan = TestPlanService.get_test_plan(db, test_plan_id)
        if not test_plan:
            return None
        
        # 更新字段
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(test_plan, field, value)
        
        db.commit()
        db.refresh(test_plan)
        
        return test_plan
    
    @staticmethod
    def delete_test_plan(db: Session, test_plan_id: UUID) -> bool:
        """删除测试计划（软删除）"""
        test_plan = TestPlanService.get_test_plan(db, test_plan_id)
        if not test_plan:
            return False
        
        test_plan.soft_delete()
        db.commit()
        
        return True
    
    @staticmethod
    def add_test_case_to_plan(
        db: Session, 
        test_plan_id: UUID, 
        test_case_id: UUID,
        current_user: User
    ) -> bool:
        """添加测试用例到测试计划"""
        test_plan = TestPlanService.get_test_plan(db, test_plan_id)
        test_case = SimpleTestCaseService.get_test_case(db, test_case_id)
        
        if not test_plan or not test_case:
            return False
        
        # 检查是否已经存在
        existing = db.execute(
            test_plan_case.select().where(
                and_(
                    test_plan_case.c.test_plan_id == test_plan_id,
                    test_plan_case.c.test_case_id == test_case_id
                )
            )
        ).first()
        
        if existing:
            return True  # 已经存在
        
        # 添加到关联表
        db.execute(
            test_plan_case.insert().values(
                test_plan_id=test_plan_id,
                test_case_id=test_case_id,
                added_by=current_user.id
            )
        )
        
        # 更新测试计划统计
        test_plan.total_cases += 1
        
        db.commit()
        
        return True
    
    @staticmethod
    def remove_test_case_from_plan(
        db: Session, 
        test_plan_id: UUID, 
        test_case_id: UUID
    ) -> bool:
        """从测试计划中移除测试用例"""
        test_plan = TestPlanService.get_test_plan(db, test_plan_id)
        
        if not test_plan:
            return False
        
        # 从关联表中移除
        result = db.execute(
            test_plan_case.delete().where(
                and_(
                    test_plan_case.c.test_plan_id == test_plan_id,
                    test_plan_case.c.test_case_id == test_case_id
                )
            )
        )
        
        if result.rowcount > 0:
            # 更新测试计划统计
            test_plan.total_cases = max(0, test_plan.total_cases - 1)
            db.commit()
            return True
        
        return False


class TestReportService:
    """测试报告服务"""
    
    @staticmethod
    def generate_test_report(
        db: Session,
        project_id: Optional[UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> TestReport:
        """生成测试报告"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # 基础查询
        base_query = db.query(SimpleTestCase).filter(SimpleTestCase.deleted_at.is_(None))
        execution_query = db.query(TestExecution).filter(TestExecution.deleted_at.is_(None))
        run_query = db.query(TestRun).filter(TestRun.deleted_at.is_(None))
        
        if project_id:
            base_query = base_query.filter(SimpleTestCase.project_id == project_id)
            execution_query = execution_query.filter(TestExecution.project_id == project_id)
            run_query = run_query.filter(TestRun.project_id == project_id)
        
        # 测试用例统计
        total_test_cases = base_query.count()
        
        # 测试执行统计
        execution_stats = TestReportService._calculate_execution_stats(
            db, execution_query, start_date, end_date
        )
        
        # 测试运行统计
        run_stats = TestReportService._calculate_run_stats(
            db, run_query, start_date, end_date
        )
        
        # 按测试类型统计
        by_test_type = TestReportService._calculate_stats_by_test_type(
            db, base_query, execution_query
        )
        
        # 按优先级统计
        by_priority = TestReportService._calculate_stats_by_priority(
            db, base_query, execution_query
        )
        
        # 按模块统计
        by_module = TestReportService._calculate_stats_by_module(
            db, base_query, execution_query
        )
        
        # 趋势数据
        trend_data = TestReportService._calculate_trend_data(
            db, execution_query, start_date, end_date
        )
        
        # 主要失败原因
        top_failures = TestReportService._get_top_failures(
            db, execution_query, start_date, end_date
        )
        
        return TestReport(
            period_start=start_date,
            period_end=end_date,
            total_test_cases=TestStats(
                total=total_test_cases,
                passed=0,  # 测试用例没有通过状态
                failed=0,
                blocked=0,
                skipped=0,
                error=0,
                success_rate=0.0
            ),
            total_executions=execution_stats,
            total_test_runs=run_stats,
            by_test_type=by_test_type,
            by_priority=by_priority,
            by_module=by_module,
            trend_data=trend_data,
            top_failures=top_failures
        )
    
    @staticmethod
    def _calculate_execution_stats(
        db: Session, 
        query, 
        start_date: datetime, 
        end_date: datetime
    ) -> TestStats:
        """计算执行统计"""
        executions = query.filter(
            TestExecution.executed_at.between(start_date, end_date)
        ).all()
        
        stats = {
            'total': len(executions),
            'passed': 0,
            'failed': 0,
            'blocked': 0,
            'skipped': 0,
            'error': 0,
            'success_rate': 0.0,
            'avg_duration': 0.0
        }
        
        total_duration = 0
        duration_count = 0
        
        for execution in executions:
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
            
            if execution.duration:
                total_duration += execution.duration
                duration_count += 1
        
        if stats['total'] > 0:
            stats['success_rate'] = round(stats['passed'] / stats['total'] * 100, 2)
        
        if duration_count > 0:
            stats['avg_duration'] = round(total_duration / duration_count, 2)
        
        return TestStats(**stats)
    
    @staticmethod
    def _calculate_run_stats(
        db: Session, 
        query, 
        start_date: datetime, 
        end_date: datetime
    ) -> TestStats:
        """计算运行统计"""
        runs = query.filter(
            TestRun.started_at.between(start_date, end_date)
        ).all()
        
        stats = {
            'total': len(runs),
            'passed': 0,
            'failed': 0,
            'blocked': 0,
            'skipped': 0,
            'error': 0,
            'success_rate': 0.0,
            'avg_duration': 0.0
        }
        
        total_duration = 0
        duration_count = 0
        
        for run in runs:
            if run.status == ExecutionStatus.PASSED.value:
                stats['passed'] += 1
            elif run.status == ExecutionStatus.FAILED.value:
                stats['failed'] += 1
            elif run.status == ExecutionStatus.BLOCKED.value:
                stats['blocked'] += 1
            elif run.status == ExecutionStatus.SKIPPED.value:
                stats['skipped'] += 1
            elif run.status == ExecutionStatus.ERROR.value:
                stats['error'] += 1
            
            if run.duration:
                total_duration += run.duration
                duration_count += 1
        
        if stats['total'] > 0:
            stats['success_rate'] = round(stats['passed'] / stats['total'] * 100, 2)
        
        if duration_count > 0:
            stats['avg_duration'] = round(total_duration / duration_count, 2)
        
        return TestStats(**stats)
    
    @staticmethod
    def _calculate_stats_by_test_type(db: Session, base_query, execution_query) -> Dict[str, TestStats]:
        """按测试类型统计"""
        stats_by_type = {}
        
        # 获取所有测试类型
        test_types = db.query(SimpleTestCase.test_type).distinct().all()
        
        for test_type_tuple in test_types:
            test_type = test_type_tuple[0]
            if not test_type:
                continue
            
            # 该类型的测试用例
            type_cases = base_query.filter(SimpleTestCase.test_type == test_type).all()
            
            # 该类型的执行记录
            type_executions = []
            for test_case in type_cases:
                executions = execution_query.filter(
                    TestExecution.test_case_id == test_case.id
                ).all()
                type_executions.extend(executions)
            
            # 计算统计
            stats = TestReportService._calculate_stats_from_executions(type_executions)
            stats_by_type[test_type] = stats
        
        return stats_by_type
    
    @staticmethod
    def _calculate_stats_by_priority(db: Session, base_query, execution_query) -> Dict[str, TestStats]:
        """按优先级统计"""
        stats_by_priority = {}
        
        # 获取所有优先级
        priorities = db.query(SimpleTestCase.priority).distinct().all()
        
        for priority_tuple in priorities:
            priority = priority_tuple[0]
            if not priority:
                continue
            
            # 该优先级的测试用例
            priority_cases = base_query.filter(SimpleTestCase.priority == priority).all()
            
            # 该优先级的执行记录
            priority_executions = []
            for test_case in priority_cases:
                executions = execution_query.filter(
                    TestExecution.test_case_id == test_case.id
                ).all()
                priority_executions.extend(executions)
            
            # 计算统计
            stats = TestReportService._calculate_stats_from_executions(priority_executions)
            stats_by_priority[priority] = stats
        
        return stats_by_priority
    
    @staticmethod
    def _calculate_stats_by_module(db: Session, base_query, execution_query) -> Dict[str, TestStats]:
        """按模块统计"""
        stats_by_module = {}
        
        # 获取所有模块
        modules = db.query(SimpleTestCase.module).distinct().all()
        
        for module_tuple in modules:
            module = module_tuple[0]
            if not module:
                continue
            
            # 该模块的测试用例
            module_cases = base_query.filter(SimpleTestCase.module == module).all()
            
            # 该模块的执行记录
            module_executions = []
            for test_case in module_cases:
                executions = execution_query.filter(
                    TestExecution.test_case_id == test_case.id
                ).all()
                module_executions.extend(executions)
            
            # 计算统计
            stats = TestReportService._calculate_stats_from_executions(module_executions)
            stats_by_module[module] = stats
        
        return stats_by_module
    
    @staticmethod
    def _calculate_stats_from_executions(executions: List[TestExecution]) -> TestStats:
        """从执行记录计算统计"""
        stats = {
            'total': len(executions),
            'passed': 0,
            'failed': 0,
            'blocked': 0,
            'skipped': 0,
            'error': 0,
            'success_rate': 0.0,
            'avg_duration': 0.0
        }
        
        total_duration = 0
        duration_count = 0
        
        for execution in executions:
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
            
            if execution.duration:
                total_duration += execution.duration
                duration_count += 1
        
        if stats['total'] > 0:
            stats['success_rate'] = round(stats['passed'] / stats['total'] * 100, 2)
        
        if duration_count > 0:
            stats['avg_duration'] = round(total_duration / duration_count, 2)
        
        return TestStats(**stats)
    
    @staticmethod
    def _calculate_trend_data(
        db: Session, 
        query, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """计算趋势数据"""
        trend_data = []
        
        # 按天分组
        current_date = start_date
        while current_date <= end_date:
            next_date = current_date + timedelta(days=1)
            
            day_executions = query.filter(
                TestExecution.executed_at.between(current_date, next_date)
            ).all()
            
            day_stats = TestReportService._calculate_stats_from_executions(day_executions)
            
            trend_data.append({
                'date': current_date.date().isoformat(),
                'total': day_stats.total,
                'passed': day_stats.passed,
                'failed': day_stats.failed,
                'success_rate': day_stats.success_rate
            })
            
            current_date = next_date
        
        return trend_data
    
    @staticmethod
    def _get_top_failures(
        db: Session, 
        query, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取主要失败原因"""
        failed_executions = query.filter(
            TestExecution.executed_at.between(start_date, end_date),
            TestExecution.status == ExecutionStatus.FAILED.value
        ).all()
        
        # 按失败原因分组
        failure_reasons = {}
        for execution in failed_executions:
            reason = execution.failure_reason or "未知原因"
            if reason not in failure_reasons:
                failure_reasons[reason] = {
                    'reason': reason,
                    'count': 0,
                    'test_cases': set()
                }
            
            failure_reasons[reason]['count'] += 1
            if execution.test_case:
                failure_reasons[reason]['test_cases'].add(execution.test_case.title)
        
        # 转换为列表并排序
        top_failures = []
        for reason_data in failure_reasons.values():
            top_failures.append({
                'reason': reason_data['reason'],
                'count': reason_data['count'],
                'test_cases': list(reason_data['test_cases'])[:5]  # 最多显示5个测试用例
            })
        
        # 按数量降序排序
        top_failures.sort(key=lambda x: x['count'], reverse=True)
        
        return top_failures[:10]  # 返回前10个失败原因