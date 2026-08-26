"""
测试管理API端点
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.user import User
from app.core.services.auth_service import AuthService, oauth2_scheme
from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import PaginatedResponse, ErrorResponse, success_response, error_response
from app.core.schemas.test import (
    TestCaseCreate, TestCaseUpdate, TestCaseResponse, TestCaseFilter,
    TestExecutionCreate, TestExecutionUpdate, TestExecutionResponse, TestExecutionFilter,
    TestRunCreate, TestRunUpdate, TestRunResponse, TestRunFilter,
    TestPlanCreate, TestPlanUpdate, TestPlanResponse,
    TestReport
)
from app.core.services.test_service import (
    TestCaseService, TestExecutionService, TestRunService, 
    TestPlanService, TestReportService
)

router = APIRouter()


# 认证依赖函数 - 返回User模型
async def get_current_user_model(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """获取当前用户（返回User模型）"""
    # 先获取用户字典
    user_dict = AuthService.get_current_user(token=token, db=db)
    
    # 从数据库获取完整的User模型
    user = db.query(User).filter(
        User.id == user_dict["id"],
        User.deleted_at.is_(None)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user_model(
    current_user: User = Depends(get_current_user_model),
) -> User:
    """获取当前活跃用户（返回User模型）"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


# ========== 测试用例API ==========

@router.get("/test-cases", response_model=PaginatedResponse[List[TestCaseResponse]])
async def get_test_cases(
    project_id: Optional[UUID] = Query(None, description="项目ID"),
    test_type: Optional[str] = Query(None, description="测试类型"),
    priority: Optional[str] = Query(None, description="优先级"),
    status: Optional[str] = Query(None, description="状态"),
    module: Optional[str] = Query(None, description="模块"),
    component: Optional[str] = Query(None, description="组件"),
    created_by: Optional[UUID] = Query(None, description="创建者ID"),
    assigned_to: Optional[UUID] = Query(None, description="分配给的用户ID"),
    tags: Optional[str] = Query(None, description="标签（逗号分隔）"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="每页记录数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试用例列表"""
    # 解析标签
    tag_list = tags.split(",") if tags else None
    
    # 验证枚举参数
    try:
        # 构建过滤器
        filter_data = TestCaseFilter(
            project_id=project_id,
            test_type=test_type,
            priority=priority,
            status=status,
            module=module,
            component=component,
            created_by=created_by,
            assigned_to=assigned_to,
            tags=tag_list,
            search=search
        )
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filter parameter: {str(e)}"
        )
    
    # 获取测试用例
    test_cases, total = TestCaseService.get_test_cases(
        db, filter_data, skip, limit
    )
    
    # 转换为响应模型
    test_case_responses = []
    for test_case in test_cases:
        response = TestCaseResponse.model_validate(test_case.to_dict())
        test_case_responses.append(response)
    
    return PaginatedResponse.create(
        data=test_case_responses,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/test-cases/{test_case_id}", response_model=TestCaseResponse)
async def get_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试用例详情"""
    test_case = TestCaseService.get_test_case(db, test_case_id)
    if not test_case:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试用例不存在"
        )
    
    return TestCaseResponse.model_validate(test_case.to_dict())


@router.post("/test-cases", response_model=TestCaseResponse, status_code=http_status.HTTP_201_CREATED)
async def create_test_case(
    test_case_data: TestCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """创建测试用例"""
    try:
        test_case = TestCaseService.create_test_case(db, test_case_data, current_user)
        return TestCaseResponse.model_validate(test_case.to_dict())
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.put("/test-cases/{test_case_id}", response_model=TestCaseResponse)
async def update_test_case(
    test_case_id: UUID,
    update_data: TestCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """更新测试用例"""
    test_case = TestCaseService.update_test_case(db, test_case_id, update_data)
    if not test_case:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试用例不存在"
        )
    
    return TestCaseResponse.model_validate(test_case.to_dict())


@router.delete("/test-cases/{test_case_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """删除测试用例"""
    success = TestCaseService.delete_test_case(db, test_case_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试用例不存在"
        )


@router.get("/test-cases/{test_case_id}/stats")
async def get_test_case_stats(
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试用例统计信息"""
    stats = TestCaseService.get_test_case_stats(db, test_case_id)
    if not stats:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试用例不存在"
        )
    
    return stats


# ========== 测试执行API ==========

@router.get("/executions", response_model=PaginatedResponse[List[TestExecutionResponse]])
async def get_test_executions(
    test_case_id: Optional[UUID] = Query(None, description="测试用例ID"),
    project_id: Optional[UUID] = Query(None, description="项目ID"),
    test_run_id: Optional[UUID] = Query(None, description="测试运行ID"),
    status: Optional[str] = Query(None, description="执行状态"),
    executed_by: Optional[UUID] = Query(None, description="执行者ID"),
    environment: Optional[str] = Query(None, description="测试环境"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="每页记录数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试执行记录列表"""
    # 构建过滤器
    try:
        filter_data = TestExecutionFilter(
            test_case_id=test_case_id,
            project_id=project_id,
            test_run_id=test_run_id,
            status=status,
            executed_by=executed_by,
            environment=environment,
            start_date=start_date,
            end_date=end_date
        )
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filter parameter: {str(e)}"
        )
    
    # 获取执行记录
    executions, total = TestExecutionService.get_test_executions(
        db, filter_data, skip, limit
    )
    
    # 转换为响应模型
    execution_responses = []
    for execution in executions:
        response = TestExecutionResponse.model_validate(execution.to_dict())
        execution_responses.append(response)
    
    return PaginatedResponse.create(
        data=execution_responses,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/executions/{execution_id}", response_model=TestExecutionResponse)
async def get_test_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试执行记录详情"""
    execution = TestExecutionService.get_test_execution(db, execution_id)
    if not execution:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试执行记录不存在"
        )
    
    return TestExecutionResponse.model_validate(execution.to_dict())


@router.post("/executions", response_model=TestExecutionResponse, status_code=http_status.HTTP_201_CREATED)
async def create_test_execution(
    execution_data: TestExecutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """创建测试执行记录"""
    try:
        execution = TestExecutionService.create_test_execution(db, execution_data, current_user)
        return TestExecutionResponse.model_validate(execution.to_dict())
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.put("/executions/{execution_id}", response_model=TestExecutionResponse)
async def update_test_execution(
    execution_id: UUID,
    update_data: TestExecutionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """更新测试执行记录"""
    execution = TestExecutionService.update_test_execution(db, execution_id, update_data)
    if not execution:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试执行记录不存在"
        )
    
    return TestExecutionResponse.model_validate(execution.to_dict())


@router.delete("/executions/{execution_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_test_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """删除测试执行记录"""
    success = TestExecutionService.delete_test_execution(db, execution_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试执行记录不存在"
        )


# ========== 测试运行API ==========

@router.get("/test-runs", response_model=PaginatedResponse[List[TestRunResponse]])
async def get_test_runs(
    project_id: Optional[UUID] = Query(None, description="项目ID"),
    test_plan_id: Optional[UUID] = Query(None, description="测试计划ID"),
    status: Optional[str] = Query(None, description="状态"),
    started_by: Optional[UUID] = Query(None, description="启动者ID"),
    environment: Optional[str] = Query(None, description="测试环境"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="每页记录数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试运行列表"""
    # 构建过滤器
    try:
        filter_data = TestRunFilter(
            project_id=project_id,
            test_plan_id=test_plan_id,
            status=status,
            started_by=started_by,
            environment=environment,
            start_date=start_date,
            end_date=end_date
        )
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filter parameter: {str(e)}"
        )
    
    # 获取测试运行
    test_runs, total = TestRunService.get_test_runs(
        db, filter_data, skip, limit
    )
    
    # 转换为响应模型
    test_run_responses = []
    for test_run in test_runs:
        response = TestRunResponse.model_validate(test_run.to_dict())
        test_run_responses.append(response)
    
    return PaginatedResponse.create(
        data=test_run_responses,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/test-runs/{test_run_id}", response_model=TestRunResponse)
async def get_test_run(
    test_run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试运行详情"""
    test_run = TestRunService.get_test_run(db, test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试运行不存在"
        )
    
    return TestRunResponse.model_validate(test_run.to_dict())


@router.post("/test-runs", response_model=TestRunResponse, status_code=http_status.HTTP_201_CREATED)
async def create_test_run(
    test_run_data: TestRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """创建测试运行"""
    try:
        test_run = TestRunService.create_test_run(db, test_run_data, current_user)
        return TestRunResponse.model_validate(test_run.to_dict())
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.put("/test-runs/{test_run_id}", response_model=TestRunResponse)
async def update_test_run(
    test_run_id: UUID,
    update_data: TestRunUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """更新测试运行"""
    test_run = TestRunService.update_test_run(db, test_run_id, update_data)
    if not test_run:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试运行不存在"
        )
    
    return TestRunResponse.model_validate(test_run.to_dict())


@router.delete("/test-runs/{test_run_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_test_run(
    test_run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """删除测试运行"""
    success = TestRunService.delete_test_run(db, test_run_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试运行不存在"
        )


@router.post("/test-runs/{test_run_id}/add-test-case/{test_case_id}")
async def add_test_case_to_run(
    test_run_id: UUID,
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """添加测试用例到测试运行"""
    success = TestRunService.add_test_case_to_run(db, test_run_id, test_case_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试运行或测试用例不存在"
        )
    
    return {"message": "测试用例已添加到测试运行"}


@router.get("/test-runs/{test_run_id}/stats")
async def get_test_run_stats(
    test_run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试运行统计信息"""
    stats = TestRunService.get_test_run_stats(db, test_run_id)
    if not stats:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试运行不存在"
        )
    
    return stats


# ========== 测试计划API ==========

@router.get("/test-plans", response_model=PaginatedResponse[List[TestPlanResponse]])
async def get_test_plans(
    project_id: Optional[UUID] = Query(None, description="项目ID"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="每页记录数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试计划列表"""
    # 获取测试计划
    test_plans, total = TestPlanService.get_test_plans(
        db, project_id, skip, limit
    )
    
    # 转换为响应模型
    test_plan_responses = []
    for test_plan in test_plans:
        response = TestPlanResponse.model_validate(test_plan.to_dict())
        test_plan_responses.append(response)
    
    return PaginatedResponse.create(
        data=test_plan_responses,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/test-plans/{test_plan_id}", response_model=TestPlanResponse)
async def get_test_plan(
    test_plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """获取测试计划详情"""
    test_plan = TestPlanService.get_test_plan(db, test_plan_id)
    if not test_plan:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试计划不存在"
        )
    
    return TestPlanResponse.model_validate(test_plan.to_dict())


@router.post("/test-plans", response_model=TestPlanResponse, status_code=http_status.HTTP_201_CREATED)
async def create_test_plan(
    test_plan_data: TestPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """创建测试计划"""
    try:
        test_plan = TestPlanService.create_test_plan(db, test_plan_data, current_user)
        return TestPlanResponse.model_validate(test_plan.to_dict())
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.put("/test-plans/{test_plan_id}", response_model=TestPlanResponse)
async def update_test_plan(
    test_plan_id: UUID,
    update_data: TestPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """更新测试计划"""
    test_plan = TestPlanService.update_test_plan(db, test_plan_id, update_data)
    if not test_plan:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试计划不存在"
        )
    
    return TestPlanResponse.model_validate(test_plan.to_dict())


@router.delete("/test-plans/{test_plan_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_test_plan(
    test_plan_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """删除测试计划"""
    success = TestPlanService.delete_test_plan(db, test_plan_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试计划不存在"
        )


@router.post("/test-plans/{test_plan_id}/add-test-case/{test_case_id}")
async def add_test_case_to_plan(
    test_plan_id: UUID,
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """添加测试用例到测试计划"""
    success = TestPlanService.add_test_case_to_plan(db, test_plan_id, test_case_id, current_user)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试计划或测试用例不存在"
        )
    
    return {"message": "测试用例已添加到测试计划"}


@router.delete("/test-plans/{test_plan_id}/remove-test-case/{test_case_id}")
async def remove_test_case_from_plan(
    test_plan_id: UUID,
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """从测试计划中移除测试用例"""
    success = TestPlanService.remove_test_case_from_plan(db, test_plan_id, test_case_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="测试计划或测试用例不存在"
        )
    
    return {"message": "测试用例已从测试计划中移除"}


# ========== 测试报告API ==========

@router.get("/reports", response_model=TestReport)
async def generate_test_report(
    project_id: Optional[UUID] = Query(None, description="项目ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_model)
):
    """生成测试报告"""
    report = TestReportService.generate_test_report(
        db, project_id, start_date, end_date
    )
    
    return report