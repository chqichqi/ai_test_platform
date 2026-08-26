"""
项目成员管理API端点
对应需求文档 3.1.3 项目成员管理
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.models.project import Project
from app.core.models.project_ext import ProjectMember, ProjectRole
from app.core.models.user import User
from app.core.schemas.project_ext import (
    ProjectMemberCreate, ProjectMemberUpdate, ProjectMemberResponse,
    ProjectMemberList, ProjectRoleInfo
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.get("/roles", response_model=List[ProjectRoleInfo])
def get_project_roles():
    """
    获取项目角色列表
    
    返回所有可用的项目角色及其权限说明
    """
    roles = [
        {
            "code": ProjectRole.OWNER.value,
            "name": "项目负责人",
            "description": "对项目有完全控制权，可管理所有配置和成员",
            "permissions": ["全部权限"]
        },
        {
            "code": ProjectRole.TEST_LEAD.value,
            "name": "测试负责人",
            "description": "可管理测试计划、用例执行和团队成员",
            "permissions": ["project:view", "version:manage", "case:manage", "execution:manage", "issue:manage"]
        },
        {
            "code": ProjectRole.TESTER.value,
            "name": "测试工程师",
            "description": "可创建和编辑用例、执行测试、提交问题",
            "permissions": ["project:view", "case:manage", "execution:execute", "issue:create"]
        },
        {
            "code": ProjectRole.DEVELOPER.value,
            "name": "开发工程师",
            "description": "可查看测试报告、修复问题",
            "permissions": ["project:view", "case:view", "issue:view", "issue:edit"]
        },
        {
            "code": ProjectRole.VIEWER.value,
            "name": "观察员",
            "description": "只读权限，可查看项目和测试报告",
            "permissions": ["project:view", "case:view", "execution:view", "issue:view"]
        }
    ]
    return roles


@router.get("/{project_id}/members", response_model=ProjectMemberList)
def list_project_members(
    project_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    role_filter: Optional[str] = Query(None, description="角色筛选"),
    search: Optional[str] = Query(None, description="搜索用户名/姓名"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_READ)
):
    """
    获取项目成员列表
    
    权限要求: project:read
    """
    # 检查项目存在
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at.is_(None)
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    query = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True
    )
    
    if role_filter:
        query = query.filter(ProjectMember.role == role_filter)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.join(User).filter(
            or_(
                User.username.ilike(search_pattern),
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )
    
    total = query.count()
    members = query.order_by(ProjectMember.joined_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return ProjectMemberList(
        items=[ProjectMemberResponse.model_validate(m) for m in members],
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: int,
    member_in: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE)
):
    """
    添加项目成员
    
    权限要求: project:update (或 member:manage)
    """
    # 检查项目存在
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at.is_(None)
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    # 检查用户存在
    user = db.query(User).filter(User.id == member_in.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户ID {member_in.user_id} 不存在"
        )
    
    # 检查是否已是成员
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == member_in.user_id,
        ProjectMember.is_active == True
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户已是项目成员"
        )
    
    # 创建成员记录
    member = ProjectMember(
        project_id=project_id,
        user_id=member_in.user_id,
        role=member_in.role or ProjectRole.VIEWER.value,
        permissions=member_in.permissions,
        joined_by=current_user["user"].id
    )
    
    db.add(member)
    db.commit()
    db.refresh(member)
    
    logger.info(f"添加项目成员: project={project_id}, user={member_in.user_id}, role={member.role}")
    
    return ProjectMemberResponse.model_validate(member)


@router.put("/{project_id}/members/{member_id}", response_model=ProjectMemberResponse)
def update_project_member(
    project_id: int,
    member_id: int,
    member_in: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE)
):
    """
    更新项目成员信息（角色、权限）
    
    权限要求: project:update (或 member:manage)
    """
    member = db.query(ProjectMember).filter(
        ProjectMember.id == member_id,
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员不存在"
        )
    
    # 不能修改项目负责人的角色（除非自己是项目负责人）
    if member.role == ProjectRole.OWNER.value and member_in.role != ProjectRole.OWNER.value:
        # 检查当前用户是否是项目负责人
        if current_user["user"].id != str(project.owner_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目负责人可以修改其他负责人的角色"
            )
    
    update_data = member_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(member, field, value)
    
    db.commit()
    db.refresh(member)
    
    logger.info(f"更新项目成员: member={member_id}, role={member.role}")
    
    return ProjectMemberResponse.model_validate(member)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE)
):
    """
    移除项目成员
    
    权限要求: project:update (或 member:manage)
    """
    member = db.query(ProjectMember).filter(
        ProjectMember.id == member_id,
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员不存在"
        )
    
    # 不能移除项目负责人
    if member.role == ProjectRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除项目负责人，请先转移项目所有权"
        )
    
    # 软删除
    member.is_active = False
    db.commit()
    
    logger.info(f"移除项目成员: member={member_id}")
    
    return None


@router.post("/{project_id}/transfer-ownership")
def transfer_project_ownership(
    project_id: int,
    new_owner_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE)
):
    """
    转移项目所有权
    
    只有当前项目负责人可以转移所有权
    """
    from app.core.models.project import Project
    
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at.is_(None)
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    # 检查当前用户是否是项目负责人
    if str(project.owner_id) != current_user["user"].id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有项目负责人可以转移所有权"
        )
    
    # 检查新负责人是否存在
    new_owner = db.query(User).filter(User.id == new_owner_id).first()
    if not new_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户ID {new_owner_id} 不存在"
        )
    
    # 检查新负责人是否是项目成员
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == new_owner_id,
        ProjectMember.is_active == True
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新负责人必须是项目成员"
        )
    
    # 更新原负责人角色为test_lead
    old_owner_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == project.owner_id
    ).first()
    
    if old_owner_member:
        old_owner_member.role = ProjectRole.TEST_LEAD.value
    
    # 更新新负责人角色为owner
    member.role = ProjectRole.OWNER.value
    
    # 更新项目负责人
    project.owner_id = new_owner_id
    
    db.commit()
    
    logger.info(f"转移项目所有权: project={project_id}, new_owner={new_owner_id}")
    
    return {"message": "项目所有权转移成功"}
