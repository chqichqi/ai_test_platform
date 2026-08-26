"""
Dashboard API - 仪表板数据接口
提供系统级和项目级的统计仪表板数据
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.models.project import Project, Version
from app.core.models.test_simple import SimpleTestCase, TestExecution
from app.core.models.issue import Issue
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.get("/stats", response_model=Dict[str, Any])
def get_system_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.AUTH_ONLY),
):
    """
    获取系统级统计数据
    """
    try:
        # 项目统计
        total_projects = db.query(Project).filter(Project.status == 'active').count()
        
        # 版本统计
        total_versions = db.query(Version).count()
        
        # 测试用例统计
        total_test_cases = db.query(SimpleTestCase).count()
        
        # 执行统计
        total_executions = db.query(TestExecution).count()
        
        # 通过率统计 - 简化统计
        total_executions = db.query(TestExecution).count()
        passed_count = db.query(TestExecution).filter(TestExecution.status == 'passed').count()
        failed_count = db.query(TestExecution).filter(TestExecution.status == 'failed').count()
        
        pass_rate = 0
        if total_executions > 0:
            pass_rate = round((passed_count / total_executions) * 100, 2)
        
        # 问题统计
        total_issues = db.query(Issue).count()
        
        # 最近执行记录
        recent_executions = db.query(TestExecution).order_by(
            desc(TestExecution.executed_at)
        ).limit(5).all()
        
        # 最近问题
        recent_issues = db.query(Issue).order_by(
            desc(Issue.created_at)
        ).limit(5).all()
        
        return {
            "total_projects": total_projects,
            "total_versions": total_versions,
            "total_test_cases": total_test_cases,
            "total_executions": total_executions,
            "total_issues": total_issues,
            "pass_rate": pass_rate,
            "recent_executions": [
                {
                    "id": e.id,
                    "status": str(e.status),
                    "executed_at": e.executed_at.isoformat() if e.executed_at else None,
                    "duration": e.duration,
                }
                for e in recent_executions
            ],
            "recent_issues": [
                {
                    "id": i.id,
                    "title": i.title,
                    "status": str(i.status) if i.status else None,
                    "priority": str(i.priority) if i.priority else None,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                    "assignee": i.assignee.username if i.assignee else None,
                }
                for i in recent_issues
            ],
        }
    except Exception as e:
        import traceback
        print(f"Dashboard stats error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/projects/{project_id}/dashboard", response_model=Dict[str, Any])
def get_project_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.AUTH_ONLY),
):
    """
    获取项目仪表板数据
    """
    # 验证项目存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 版本统计
    versions = db.query(Version).filter(Version.project_id == project_id).all()
    total_versions = len(versions)
    
    # 版本状态分布
    version_status_distribution = {}
    for v in versions:
        status = v.status.value if hasattr(v.status, 'value') else str(v.status)
        version_status_distribution[status] = version_status_distribution.get(status, 0) + 1
    
    # 测试用例统计
    test_cases = db.query(SimpleTestCase).filter(SimpleTestCase.project_id == project_id).all()
    total_test_cases = len(test_cases)
    
    # 测试用例状态分布
    test_case_status_distribution = {}
    for tc in test_cases:
        status = tc.status.value if hasattr(tc.status, 'value') else str(tc.status)
        test_case_status_distribution[status] = test_case_status_distribution.get(status, 0) + 1
    
    # 执行统计
    executions = db.query(TestExecution).filter(TestExecution.project_id == project_id).all()
    total_executions = len(executions)
    
    # 计算通过率 - 使用status字段统计
    passed_count = db.query(TestExecution).filter(
        TestExecution.project_id == project_id,
        TestExecution.status == 'passed'
    ).count()
    failed_count = db.query(TestExecution).filter(
        TestExecution.project_id == project_id,
        TestExecution.status == 'failed'
    ).count()
    total_tests = passed_count + failed_count
    pass_rate = round((passed_count / total_tests) * 100, 2) if total_tests > 0 else 0
    
    # 最近执行 - 使用executed_at字段
    recent_executions = db.query(TestExecution).filter(
        TestExecution.project_id == project_id
    ).order_by(desc(TestExecution.executed_at)).limit(10).all()
    
    # 执行趋势（最近30天） - 使用executed_at字段
    thirty_days_ago = datetime.now() - timedelta(days=30)
    execution_trend = db.query(
        func.date(TestExecution.executed_at).label('date'),
        func.count(TestExecution.id).label('count'),
    ).filter(
        TestExecution.project_id == project_id,
        TestExecution.executed_at >= thirty_days_ago
    ).group_by(
        func.date(TestExecution.executed_at)
    ).order_by('date').all()
    
    # 问题统计
    issues = db.query(Issue).filter(Issue.project_id == project_id).all()
    total_issues = len(issues)
    open_issues = sum(1 for i in issues if (i.status.value if hasattr(i.status, 'value') else str(i.status)) == 'open')
    resolved_issues = sum(1 for i in issues if (i.status.value if hasattr(i.status, 'value') else str(i.status)) == 'resolved')
    
    # 问题优先级分布
    issue_by_priority = {}
    for i in issues:
        priority = i.priority.value if hasattr(i.priority, 'value') else str(i.priority)
        issue_by_priority[priority] = issue_by_priority.get(priority, 0) + 1
    
    return {
        "total_versions": total_versions,
        "total_test_cases": total_test_cases,
        "total_executions": total_executions,
        "pass_rate": pass_rate,
        "version_status_distribution": version_status_distribution,
        "test_case_status_distribution": test_case_status_distribution,
        "recent_executions": [
            {
                "id": e.id,
                "test_case_id": e.test_case_id,
                "status": e.status.value if hasattr(e.status, 'value') else str(e.status),
                "executed_at": e.executed_at.isoformat() if e.executed_at else None,
                "duration": e.duration or 0,
                "executed_by": e.executed_by,
            }
            for e in recent_executions
        ],
        "test_execution_trend": [
            {
                "date": str(t.date),
                "count": t.count,
            }
            for t in execution_trend
        ],
        "issue_stats": {
            "total": total_issues,
            "open": open_issues,
            "resolved": resolved_issues,
            "by_priority": issue_by_priority,
        },
    }


@router.get("/test-trend", response_model=List[Dict[str, Any]])
def get_test_trend(
    project_id: int = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.AUTH_ONLY),
):
    """
    获取测试执行趋势
    """
    start_date = datetime.now() - timedelta(days=days)
    
    query = db.query(
        func.date(TestExecution.executed_at).label('date'),
        func.count(TestExecution.id).label('count'),
    ).filter(
        TestExecution.executed_at >= start_date
    )
    
    if project_id:
        query = query.filter(TestExecution.project_id == str(project_id))
    
    trend = query.group_by(
        func.date(TestExecution.executed_at)
    ).order_by('date').all()
    
    return [
        {
            "date": str(t.date),
            "count": t.count,
        }
        for t in trend
    ]


@router.get("/issue-trend", response_model=List[Dict[str, Any]])
def get_issue_trend(
    project_id: int = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.AUTH_ONLY),
):
    """
    获取问题趋势
    """
    start_date = datetime.now() - timedelta(days=days)
    
    query = db.query(
        func.date(Issue.created_at).label('date'),
        func.count(Issue.id).label('created'),
        func.sum(func.case([(Issue.resolved_at != None, 1)], else_=0)).label('resolved'),
    ).filter(
        Issue.created_at >= start_date
    )
    
    if project_id:
        query = query.filter(Issue.project_id == project_id)
    
    trend = query.group_by(
        func.date(Issue.created_at)
    ).order_by('date').all()
    
    return [
        {
            "date": str(t.date),
            "created": t.created,
            "resolved": t.resolved or 0,
        }
        for t in trend
    ]
