# -*- coding: utf-8 -*-
"""
生成任务管理API
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.generation_task import GenerationTask, TaskStatus, TaskType
from app.core.services.async_generation_service import (
    create_generation_task, get_task_status, run_generation_task
)
from pydantic import BaseModel

router = APIRouter()


class TaskResponse(BaseModel):
    """任务响应模型"""
    id: int
    display_id: str
    task_type: str
    status: str
    project_id: int
    version_id: int
    progress: int
    current_step: Optional[str]
    total_batches: int
    current_batch: int
    generated_count: int
    error_message: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    tasks: List[TaskResponse]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """获取任务状态"""
    task_data = get_task_status(db, task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskResponse(
        id=task_data["id"],
        display_id=task_data.get("display_id", str(task_data["id"])),
        task_type=task_data["task_type"],
        status=task_data["status"],
        project_id=task_data["project_id"],
        version_id=task_data["version_id"],
        progress=task_data["progress"],
        current_step=task_data["current_step"],
        total_batches=task_data["total_batches"],
        current_batch=task_data["current_batch"],
        generated_count=task_data["generated_count"],
        error_message=task_data["error_message"],
        started_at=task_data["started_at"],
        completed_at=task_data["completed_at"],
        duration_seconds=task_data["duration_seconds"],
        created_at=task_data["created_at"],
        updated_at=task_data["updated_at"]
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    project_id: Optional[int] = Query(None, description="项目ID"),
    version_id: Optional[int] = Query(None, description="版本ID"),
    status: Optional[str] = Query(None, description="任务状态"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取任务列表"""
    query = db.query(GenerationTask)
    
    if project_id:
        query = query.filter(GenerationTask.project_id == project_id)
    if version_id:
        query = query.filter(GenerationTask.version_id == version_id)
    if status:
        query = query.filter(GenerationTask.status == TaskStatus(status))
    
    query = query.order_by(GenerationTask.created_at.desc())
    
    total = query.count()
    tasks = query.offset(skip).limit(limit).all()
    
    task_responses = []
    for task in tasks:
        # 使用 to_dict 方法获取 display_id
        task_dict = task.to_dict()
        task_responses.append(TaskResponse(
            id=task_dict["id"],
            display_id=task_dict.get("display_id", str(task.id)),
            task_type=task_dict["task_type"],
            status=task_dict["status"],
            project_id=task_dict["project_id"],
            version_id=task_dict["version_id"],
            progress=task_dict["progress"],
            current_step=task_dict["current_step"],
            total_batches=task_dict["total_batches"],
            current_batch=task_dict["current_batch"],
            generated_count=task_dict["generated_count"],
            error_message=task_dict["error_message"],
            started_at=task_dict["started_at"],
            completed_at=task_dict["completed_at"],
            duration_seconds=task_dict["duration_seconds"],
            created_at=task_dict["created_at"],
            updated_at=task_dict["updated_at"]
        ))
    
    return TaskListResponse(total=total, tasks=task_responses)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """取消任务并删除相关版本数据"""
    task = db.query(GenerationTask).filter(GenerationTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务已完成，无法取消")
    
    version_id = task.version_id
    
    task.status = TaskStatus.CANCELLED.value
    task.error_message = "用户手动取消"
    
    if version_id is not None:
        from app.core.models.project import Version
        from app.core.models.requirement import RequirementDocument, TestCase

        version = db.query(Version).filter(Version.id == version_id).first()

        if version is not None:
            # 删除测试用例
            db.query(TestCase).filter(TestCase.version_id == version_id).delete()

            # 删除需求文档
            db.query(RequirementDocument).filter(RequirementDocument.version_id == version_id).delete()

            # 删除版本记录
            db.delete(version)
            
    db.commit()
    
    return {"success": True, "message": "任务已取消，相关数据已删除"}