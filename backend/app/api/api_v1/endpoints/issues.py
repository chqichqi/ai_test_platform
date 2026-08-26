"""
问题跟踪和AI失败分析API端点
对应需求文档 3.10 结果与问题管理
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.core.database import get_db
from app.core.models.issue import (
    Issue, FailureAnalysis, IssueComment, IssueHistory,
    IssueStatus, IssueSeverity, IssuePriority,
    FailureType, RootCauseCategory
)
from app.core.schemas.issue import (
    IssueCreate, IssueUpdate, IssueResponse, IssueListResponse,
    AnalyzeFailureRequest, FailureAnalysisResponse,
    IssueCommentCreate, IssueCommentResponse,
    IssueStatsResponse, BatchUpdateStatusRequest, AssignIssuesRequest
)
from app.core.services.failure_analysis_service import FailureAnalysisService
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.post("/", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
def create_issue(
    issue_in: IssueCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建问题"""
    issue = Issue(
        project_id=issue_in.project_id,
        version_id=issue_in.version_id,
        execution_id=issue_in.execution_id,
        case_id=issue_in.case_id,
        title=issue_in.title,
        description=issue_in.description,
        severity=issue_in.severity,
        priority=issue_in.priority,
        failure_type=issue_in.failure_type,
        tags=issue_in.tags,
        assignee_id=issue_in.assignee_id,
        reporter_id=current_user["user"].id
    )
    
    db.add(issue)
    db.commit()
    db.refresh(issue)
    
    _add_history(db, issue.id, "created", None, "open", current_user["user"].id)
    
    logger.info(f"创建问题: {issue.title}")
    
    return IssueResponse.model_validate(issue)


@router.get("/", response_model=IssueListResponse)
def list_issues(
    project_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """问题列表"""
    query = db.query(Issue).filter(Issue.project_id == project_id)
    
    if status:
        query = query.filter(Issue.status == status)
    if severity:
        query = query.filter(Issue.severity == severity)
    if priority:
        query = query.filter(Issue.priority == priority)
    if assignee_id:
        query = query.filter(Issue.assignee_id == assignee_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Issue.title.ilike(pattern),
                Issue.description.ilike(pattern)
            )
        )
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    issues = query.order_by(Issue.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return IssueListResponse(
        items=[IssueResponse.model_validate(i) for i in issues],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{issue_id}", response_model=IssueResponse)
def get_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取问题详情"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    return IssueResponse.model_validate(issue)


@router.put("/{issue_id}", response_model=IssueResponse)
def update_issue(
    issue_id: int,
    issue_in: IssueUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新问题"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    update_data = issue_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        old_value = getattr(issue, field)
        if old_value != value:
            _add_history(db, issue_id, field, str(old_value), str(value), current_user["user"].id)
        setattr(issue, field, value)
    
    db.commit()
    db.refresh(issue)
    
    logger.info(f"更新问题: {issue.title}")
    
    return IssueResponse.model_validate(issue)


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除问题"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    db.delete(issue)
    db.commit()
    
    return None


@router.post("/{issue_id}/assign")
def assign_issue(
    issue_id: int,
    assignee_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """分配问题"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    old_assignee = issue.assignee_id
    issue.assignee_id = assignee_id
    issue.status = IssueStatus.IN_PROGRESS.value
    
    _add_history(db, issue_id, "assignee", str(old_assignee), str(assignee_id), current_user["user"].id)
    _add_history(db, issue_id, "status", str(old_assignee) or "open", "in_progress", current_user["user"].id)
    
    db.commit()
    
    return {"message": "分配成功"}


@router.post("/{issue_id}/resolve")
def resolve_issue(
    issue_id: int,
    resolution_note: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """解决问题"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    issue.status = IssueStatus.RESOLVED.value
    issue.resolved_at = datetime.utcnow()
    issue.resolved_by = current_user["user"].id
    issue.resolution_note = resolution_note
    
    _add_history(db, issue_id, "status", issue.status, "resolved", current_user["user"].id)
    
    db.commit()
    
    logger.info(f"解决问题: {issue.title}")
    
    return {"message": "已解决"}


@router.post("/{issue_id}/close")
def close_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """关闭问题"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    issue.status = IssueStatus.CLOSED.value
    
    _add_history(db, issue_id, "status", issue.status, "closed", current_user["user"].id)
    
    db.commit()
    
    return {"message": "已关闭"}


@router.post("/{issue_id}/reopen")
def reopen_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """重新打开问题"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    issue.status = IssueStatus.REOPENED.value
    
    _add_history(db, issue_id, "status", issue.status, "reopened", current_user["user"].id)
    
    db.commit()
    
    return {"message": "已重新打开"}


@router.post("/analyze", response_model=FailureAnalysisResponse)
def analyze_failure(
    request: AnalyzeFailureRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """
    AI分析失败原因
    
    功能要求（需求文档3.10.2）:
    - 自动分析失败原因
    - 原因分类：元素变化、环境问题、业务Bug、数据问题
    - 影响范围分析
    - 修复建议
    """
    analysis_service = FailureAnalysisService(db)
    
    result = analysis_service.analyze_failure_with_llm(
        failure_message=request.failure_message,
        stack_trace=request.stack_trace,
        dom_snapshot=request.dom_snapshot,
        console_logs=request.console_logs,
        network_logs=request.network_logs
    )
    
    analysis = FailureAnalysis(
        execution_id=request.execution_id,
        case_id=request.case_id,
        project_id=request.project_id,
        failure_message=request.failure_message,
        stack_trace=request.stack_trace,
        dom_snapshot=request.dom_snapshot,
        console_logs=request.console_logs,
        network_logs=request.network_logs,
        failure_type=result['failure_type'],
        root_cause=result['root_cause'],
        ai_analysis=result['analysis'],
        confidence=result['confidence'],
        suggested_fix=result['suggestion'],
        auto_fix_available=1 if result['auto_fix_available'] else 0,
        affected_locators=result['affected_locators'],
        affected_cases=result['affected_cases']
    )
    
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    
    similar_issues = analysis_service.find_similar_issues(
        result['failure_type'],
        request.project_id
    )
    
    logger.info(f"AI分析失败: execution_id={request.execution_id}, type={result['failure_type']}, confidence={result['confidence']}%")
    
    return FailureAnalysisResponse(
        id=analysis.id,
        execution_id=analysis.execution_id,
        case_id=analysis.case_id,
        failure_type=analysis.failure_type,
        failure_message=analysis.failure_message,
        root_cause=analysis.root_cause,
        ai_analysis=analysis.ai_analysis,
        confidence=analysis.confidence,
        suggested_fix=analysis.suggested_fix,
        auto_fix_available=bool(analysis.auto_fix_available),
        affected_locators=analysis.affected_locators,
        affected_cases=analysis.affected_cases,
        created_at=analysis.created_at,
        similar_issues=similar_issues,
        severity_recommendation=result.get('severity_recommendation'),
        priority_recommendation=result.get('priority_recommendation')
    )


def _get_severity_from_type(failure_type: str) -> str:
    """根据失败类型确定严重程度"""
    severity_map = {
        FailureType.ELEMENT_NOT_FOUND.value: IssueSeverity.MEDIUM.value,
        FailureType.ASSERTION_FAILED.value: IssueSeverity.HIGH.value,
        FailureType.TIMEOUT.value: IssueSeverity.LOW.value,
        FailureType.NETWORK_ERROR.value: IssueSeverity.HIGH.value,
        FailureType.ENVIRONMENT_ERROR.value: IssueSeverity.HIGH.value,
        FailureType.BUSINESS_BUG.value: IssueSeverity.CRITICAL.value,
    }
    return severity_map.get(failure_type, IssueSeverity.MEDIUM.value)


@router.get("/stats/{project_id}", response_model=IssueStatsResponse)
def get_issue_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取问题统计"""
    base_query = db.query(Issue).filter(Issue.project_id == project_id)
    
    total = base_query.count()
    
    open_count = base_query.filter(Issue.status == IssueStatus.OPEN.value).count()
    in_progress = base_query.filter(Issue.status == IssueStatus.IN_PROGRESS.value).count()
    resolved = base_query.filter(Issue.status == IssueStatus.RESOLVED.value).count()
    closed = base_query.filter(Issue.status == IssueStatus.CLOSED.value).count()
    
    by_severity = {}
    for sev in [IssueSeverity.CRITICAL, IssueSeverity.HIGH, IssueSeverity.MEDIUM, IssueSeverity.LOW]:
        by_severity[sev.value] = base_query.filter(Issue.severity == sev.value).count()
    
    by_priority = {}
    for pri in [IssuePriority.P0, IssuePriority.P1, IssuePriority.P2, IssuePriority.P3]:
        by_priority[pri.value] = base_query.filter(Issue.priority == pri.value).count()
    
    by_failure_type = {}
    for ft in FailureType:
        by_failure_type[ft.value] = base_query.filter(Issue.failure_type == ft.value).count()
    
    return IssueStatsResponse(
        total=total,
        open=open_count,
        in_progress=in_progress,
        resolved=resolved,
        closed=closed,
        by_severity=by_severity,
        by_priority=by_priority,
        by_failure_type=by_failure_type
    )


@router.post("/batch/assign")
def batch_assign(
    request: AssignIssuesRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """批量分配问题"""
    db.query(Issue).filter(Issue.id.in_(request.issue_ids)).update(
        {"assignee_id": request.assignee_id, "status": IssueStatus.IN_PROGRESS.value},
        synchronize_session=False
    )
    
    for issue_id in request.issue_ids:
        _add_history(db, issue_id, "assignee", None, str(request.assignee_id), current_user["user"].id)
    
    db.commit()
    
    return {"message": f"已分配 {len(request.issue_ids)} 个问题"}


@router.post("/batch/status")
def batch_update_status(
    request: BatchUpdateStatusRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """批量更新状态"""
    update_data = {"status": request.status}
    
    if request.status == IssueStatus.RESOLVED.value:
        update_data["resolved_at"] = datetime.utcnow()
        update_data["resolved_by"] = current_user["user"].id
        update_data["resolution_note"] = request.resolution_note
    
    db.query(Issue).filter(Issue.id.in_(request.issue_ids)).update(update_data, synchronize_session=False)
    
    for issue_id in request.issue_ids:
        _add_history(db, issue_id, "status", None, request.status, current_user["user"].id)
    
    db.commit()
    
    return {"message": f"已更新 {len(request.issue_ids)} 个问题状态"}


@router.post("/{issue_id}/comments", response_model=IssueCommentResponse)
def add_comment(
    issue_id: int,
    comment_in: IssueCommentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """添加评论"""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    comment = IssueComment(
        issue_id=issue_id,
        content=comment_in.content,
        author_id=current_user["user"].id,
        is_internal=int(comment_in.is_internal),
        parent_id=comment_in.parent_id
    )
    
    db.add(comment)
    db.commit()
    db.refresh(comment)
    
    return IssueCommentResponse.model_validate(comment)


@router.get("/{issue_id}/comments", response_model=List[IssueCommentResponse])
def list_comments(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取问题评论列表"""
    comments = db.query(IssueComment).filter(
        IssueComment.issue_id == issue_id
    ).order_by(IssueComment.created_at.asc()).all()
    
    return [IssueCommentResponse.model_validate(c) for c in comments]


def _add_history(db: Session, issue_id: int, field_name: str, old_value: Optional[str], new_value: Optional[str], changed_by: int):
    """添加历史记录"""
    history = IssueHistory(
        issue_id=issue_id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_by=changed_by
    )
    db.add(history)


@router.get("/stats/{project_id}/trend")
def get_issue_trend(
    project_id: int,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    问题趋势统计
    
    返回每日新增、解决、关闭的问题数量
    """
    from datetime import timedelta
    from sqlalchemy import func, and_
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    daily_created = db.query(
        func.date(Issue.created_at).label('date'),
        func.count(Issue.id).label('count')
    ).filter(
        Issue.project_id == project_id,
        Issue.created_at >= start_date
    ).group_by(func.date(Issue.created_at)).all()
    
    daily_resolved = db.query(
        func.date(Issue.resolved_at).label('date'),
        func.count(Issue.id).label('count')
    ).filter(
        Issue.project_id == project_id,
        Issue.resolved_at >= start_date,
        Issue.resolved_at.isnot(None)
    ).group_by(func.date(Issue.resolved_at)).all()
    
    trend_data = {}
    for i in range(days):
        date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
        trend_data[date] = {'created': 0, 'resolved': 0, 'closed': 0}
    
    for item in daily_created:
        if item.date:
            date_str = item.date.strftime('%Y-%m-%d') if hasattr(item.date, 'strftime') else str(item.date)
            if date_str in trend_data:
                trend_data[date_str]['created'] = item.count
    
    for item in daily_resolved:
        if item.date:
            date_str = item.date.strftime('%Y-%m-%d') if hasattr(item.date, 'strftime') else str(item.date)
            if date_str in trend_data:
                trend_data[date_str]['resolved'] = item.count
    
    return {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'trend': [{'date': k, **v} for k, v in sorted(trend_data.items())]
    }


@router.get("/stats/{project_id}/summary")
def get_issue_summary(
    project_id: int,
    version_id: Optional[int] = Query(None, description="版本ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    问题汇总统计
    
    返回各维度的统计数据
    """
    from sqlalchemy import func
    
    base_query = db.query(Issue).filter(Issue.project_id == project_id)
    if version_id:
        base_query = base_query.filter(Issue.version_id == version_id)
    
    total = base_query.count()
    
    by_status = {}
    for status in IssueStatus:
        by_status[status.value] = base_query.filter(Issue.status == status.value).count()
    
    by_severity = {}
    for severity in IssueSeverity:
        by_severity[severity.value] = base_query.filter(Issue.severity == severity.value).count()
    
    by_priority = {}
    for priority in IssuePriority:
        by_priority[priority.value] = base_query.filter(Issue.priority == priority.value).count()
    
    by_failure_type = {}
    for ft in FailureType:
        count = base_query.filter(Issue.failure_type == ft.value).count()
        if count > 0:
            by_failure_type[ft.value] = count
    
    top_assignees = db.query(
        Issue.assignee_id,
        func.count(Issue.id).label('count')
    ).filter(
        Issue.project_id == project_id,
        Issue.assignee_id.isnot(None),
        Issue.status.in_([IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value])
    ).group_by(Issue.assignee_id).order_by(func.count(Issue.id).desc()).limit(5).all()
    
    avg_resolution_time = None
    resolved_issues = base_query.filter(
        Issue.resolved_at.isnot(None),
        Issue.created_at.isnot(None)
    ).all()
    
    if resolved_issues:
        total_hours = sum(
            (issue.resolved_at - issue.created_at).total_seconds() / 3600
            for issue in resolved_issues
        )
        avg_resolution_time = round(total_hours / len(resolved_issues), 2)
    
    return {
        'total': total,
        'by_status': by_status,
        'by_severity': by_severity,
        'by_priority': by_priority,
        'by_failure_type': by_failure_type,
        'top_assignees': [
            {'assignee_id': a[0], 'count': a[1]} 
            for a in top_assignees
        ],
        'avg_resolution_time_hours': avg_resolution_time,
        'resolution_rate': round(
            (by_status.get(IssueStatus.RESOLVED.value, 0) + by_status.get(IssueStatus.CLOSED.value, 0)) / total * 100, 2
        ) if total > 0 else 0
    }


@router.get("/export")
def export_issues(
    project_id: int = Query(..., description="项目ID"),
    format: str = Query("excel", pattern="^(excel|csv|json)$", description="导出格式"),
    status: Optional[str] = Query(None, description="筛选状态"),
    severity: Optional[str] = Query(None, description="筛选严重程度"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    导出问题列表
    
    支持Excel、CSV、JSON格式
    """
    import io
    import csv
    from fastapi.responses import StreamingResponse
    
    query = db.query(Issue).filter(Issue.project_id == project_id)
    
    if status:
        query = query.filter(Issue.status == status)
    if severity:
        query = query.filter(Issue.severity == severity)
    
    issues = query.order_by(Issue.created_at.desc()).all()
    
    if format == "json":
        data = [IssueResponse.model_validate(i).model_dump() for i in issues]
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=data,
            headers={
                "Content-Disposition": f"attachment; filename=issues_{project_id}.json"
            }
        )
    
    output = io.StringIO()
    
    if format == "csv":
        writer = csv.writer(output)
        writer.writerow([
            'ID', '标题', '描述', '严重程度', '优先级', '状态',
            '失败类型', '分配人ID', '报告人ID', '创建时间', '解决时间'
        ])
        
        for issue in issues:
            writer.writerow([
                issue.id,
                issue.title,
                issue.description[:200] if issue.description else '',
                issue.severity,
                issue.priority,
                issue.status,
                issue.failure_type or '',
                issue.assignee_id or '',
                issue.reporter_id or '',
                issue.created_at.strftime('%Y-%m-%d %H:%M') if issue.created_at else '',
                issue.resolved_at.strftime('%Y-%m-%d %H:%M') if issue.resolved_at else ''
            ])
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=issues_{project_id}.csv"
            }
        )
    
    if format == "excel":
        try:
            import pandas as pd
        except ImportError:
            raise HTTPException(status_code=500, detail="Excel导出需要安装pandas库")
        
        data = []
        for issue in issues:
            data.append({
                'ID': issue.id,
                '标题': issue.title,
                '描述': issue.description[:500] if issue.description else '',
                '严重程度': issue.severity,
                '优先级': issue.priority,
                '状态': issue.status,
                '失败类型': issue.failure_type or '',
                '根本原因': issue.root_cause or '',
                'AI分析': issue.ai_analysis[:200] if issue.ai_analysis else '',
                '分配人ID': issue.assignee_id or '',
                '报告人ID': issue.reporter_id or '',
                '创建时间': issue.created_at.strftime('%Y-%m-%d %H:%M') if issue.created_at else '',
                '更新时间': issue.updated_at.strftime('%Y-%m-%d %H:%M') if issue.updated_at else '',
                '解决时间': issue.resolved_at.strftime('%Y-%m-%d %H:%M') if issue.resolved_at else '',
                '解决方案': issue.resolution_note or ''
            })
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='问题列表')
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=issues_{project_id}.xlsx"
            }
        )


@router.get("/{issue_id}/related")
def get_related_issues(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    获取关联问题
    
    基于相同失败类型、相同用例等关联关系
    """
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail=f"问题ID {issue_id} 不存在")
    
    related_by_type = db.query(Issue).filter(
        Issue.id != issue_id,
        Issue.project_id == issue.project_id,
        Issue.failure_type == issue.failure_type,
        Issue.failure_type.isnot(None)
    ).order_by(Issue.created_at.desc()).limit(10).all()
    
    related_by_case = []
    if issue.case_id:
        related_by_case = db.query(Issue).filter(
            Issue.id != issue_id,
            Issue.case_id == issue.case_id
        ).order_by(Issue.created_at.desc()).limit(10).all()
    
    related_by_root_cause = []
    if issue.root_cause:
        related_by_root_cause = db.query(Issue).filter(
            Issue.id != issue_id,
            Issue.project_id == issue.project_id,
            Issue.root_cause == issue.root_cause
        ).order_by(Issue.created_at.desc()).limit(10).all()
    
    return {
        'issue_id': issue_id,
        'by_failure_type': [
            {'id': i.id, 'title': i.title, 'status': i.status, 'created_at': i.created_at.isoformat() if i.created_at else None}
            for i in related_by_type
        ],
        'by_case': [
            {'id': i.id, 'title': i.title, 'status': i.status, 'created_at': i.created_at.isoformat() if i.created_at else None}
            for i in related_by_case
        ],
        'by_root_cause': [
            {'id': i.id, 'title': i.title, 'status': i.status, 'created_at': i.created_at.isoformat() if i.created_at else None}
            for i in related_by_root_cause
        ]
    }


@router.get("/dashboard/{project_id}")
def get_issue_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    问题仪表盘数据
    
    用于前端仪表盘展示的综合统计数据
    """
    from sqlalchemy import func
    from datetime import timedelta
    
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    base_query = db.query(Issue).filter(Issue.project_id == project_id)
    
    total_issues = base_query.count()
    
    open_issues = base_query.filter(Issue.status == IssueStatus.OPEN.value).count()
    in_progress = base_query.filter(Issue.status == IssueStatus.IN_PROGRESS.value).count()
    resolved_this_week = base_query.filter(
        Issue.status == IssueStatus.RESOLVED.value,
        Issue.resolved_at >= week_ago
    ).count()
    
    new_this_week = base_query.filter(Issue.created_at >= week_ago).count()
    new_this_month = base_query.filter(Issue.created_at >= month_ago).count()
    
    critical_open = base_query.filter(
        Issue.severity == IssueSeverity.CRITICAL.value,
        Issue.status.in_([IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value])
    ).count()
    
    high_open = base_query.filter(
        Issue.severity == IssueSeverity.HIGH.value,
        Issue.status.in_([IssueStatus.OPEN.value, IssueStatus.IN_PROGRESS.value])
    ).count()
    
    recent_issues = base_query.order_by(Issue.created_at.desc()).limit(5).all()
    
    return {
        'summary': {
            'total': total_issues,
            'open': open_issues,
            'in_progress': in_progress,
            'resolved_this_week': resolved_this_week,
            'new_this_week': new_this_week,
            'new_this_month': new_this_month,
            'critical_open': critical_open,
            'high_open': high_open
        },
        'recent_issues': [
            {
                'id': i.id,
                'title': i.title,
                'severity': i.severity,
                'status': i.status,
                'created_at': i.created_at.isoformat() if i.created_at else None
            }
            for i in recent_issues
        ],
        'health_score': max(0, 100 - (critical_open * 20) - (high_open * 10) - (open_issues * 2))
    }