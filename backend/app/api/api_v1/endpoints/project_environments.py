"""
项目环境配置API
对应需求文档 3.1.3 环境配置
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.models.project import Project
from app.core.models.project_ext import ProjectEnvironment
from app.core.schemas.project_ext import (
    ProjectEnvironmentCreate,
    ProjectEnvironmentUpdate,
    ProjectEnvironmentResponse,
    ProjectEnvironmentList,
)
from app.api.api_v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/{project_id}/environments", response_model=ProjectEnvironmentList)
def list_project_environments(
    project_id: int,
    include_inactive: bool = Query(default=False, description="包含已禁用环境"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取项目环境配置列表
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 构建查询
    query = db.query(ProjectEnvironment).filter(
        ProjectEnvironment.project_id == project_id
    )
    
    if not include_inactive:
        query = query.filter(ProjectEnvironment.is_active == True)
    
    # 默认环境排在最前
    environments = query.order_by(
        ProjectEnvironment.is_default.desc(),
        ProjectEnvironment.created_at.desc()
    ).all()
    
    return ProjectEnvironmentList(
        items=environments,
        total=len(environments)
    )


@router.post("/{project_id}/environments", response_model=ProjectEnvironmentResponse)
def create_project_environment(
    project_id: int,
    env_data: ProjectEnvironmentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    创建项目环境配置
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查环境编码是否已存在
    existing = db.query(ProjectEnvironment).filter(
        ProjectEnvironment.project_id == project_id,
        ProjectEnvironment.code == env_data.code
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"环境编码 '{env_data.code}' 已存在")
    
    # 如果设置为默认环境，取消其他环境的默认状态
    if env_data.is_default:
        db.query(ProjectEnvironment).filter(
            ProjectEnvironment.project_id == project_id,
            ProjectEnvironment.is_default == True
        ).update({"is_default": False})
    
    # 创建环境配置
    environment = ProjectEnvironment(
        project_id=project_id,
        name=env_data.name,
        code=env_data.code,
        base_url=env_data.base_url,
        headers=env_data.headers,
        variables=env_data.variables,
        db_config=env_data.db_config,
        is_default=env_data.is_default,
        description=env_data.description,
        is_active=True,
        created_by=current_user.get("id"),
    )
    
    db.add(environment)
    db.commit()
    db.refresh(environment)
    
    return environment


@router.get("/{project_id}/environments/{env_id}", response_model=ProjectEnvironmentResponse)
def get_project_environment(
    project_id: int,
    env_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取环境配置详情
    """
    environment = db.query(ProjectEnvironment).filter(
        ProjectEnvironment.id == env_id,
        ProjectEnvironment.project_id == project_id
    ).first()
    
    if not environment:
        raise HTTPException(status_code=404, detail="环境配置不存在")
    
    return environment


@router.put("/{project_id}/environments/{env_id}", response_model=ProjectEnvironmentResponse)
def update_project_environment(
    project_id: int,
    env_id: int,
    env_data: ProjectEnvironmentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    更新环境配置
    """
    environment = db.query(ProjectEnvironment).filter(
        ProjectEnvironment.id == env_id,
        ProjectEnvironment.project_id == project_id
    ).first()
    
    if not environment:
        raise HTTPException(status_code=404, detail="环境配置不存在")
    
    # 如果设置为默认环境，取消其他环境的默认状态
    if env_data.is_default is True:
        db.query(ProjectEnvironment).filter(
            ProjectEnvironment.project_id == project_id,
            ProjectEnvironment.is_default == True,
            ProjectEnvironment.id != env_id
        ).update({"is_default": False})
    
    # 更新字段
    update_data = env_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(environment, field, value)
    
    db.commit()
    db.refresh(environment)
    
    return environment


@router.delete("/{project_id}/environments/{env_id}")
def delete_project_environment(
    project_id: int,
    env_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    删除环境配置
    """
    environment = db.query(ProjectEnvironment).filter(
        ProjectEnvironment.id == env_id,
        ProjectEnvironment.project_id == project_id
    ).first()
    
    if not environment:
        raise HTTPException(status_code=404, detail="环境配置不存在")
    
    # 不允许删除默认环境
    if environment.is_default:
        raise HTTPException(status_code=400, detail="不能删除默认环境，请先设置其他环境为默认")
    
    db.delete(environment)
    db.commit()
    
    return {"message": "环境配置已删除"}


@router.post("/{project_id}/environments/{env_id}/set-default")
def set_default_environment(
    project_id: int,
    env_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    设置默认环境
    """
    environment = db.query(ProjectEnvironment).filter(
        ProjectEnvironment.id == env_id,
        ProjectEnvironment.project_id == project_id
    ).first()
    
    if not environment:
        raise HTTPException(status_code=404, detail="环境配置不存在")
    
    # 取消其他环境的默认状态
    db.query(ProjectEnvironment).filter(
        ProjectEnvironment.project_id == project_id,
        ProjectEnvironment.is_default == True
    ).update({"is_default": False})
    
    # 设置当前环境为默认
    environment.is_default = True
    db.commit()
    
    return {"message": "默认环境设置成功", "environment_id": env_id}
