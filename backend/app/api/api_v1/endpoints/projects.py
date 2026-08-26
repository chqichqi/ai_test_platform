"""
项目管理API端点 - 完整实现
对应需求文档 3.1.1 项目管理
"""

from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.models.project import Project, Version, ProjectStatus
from app.core.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse,
    ProjectDetailResponse, ProjectStats
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_CREATE),
):
    """
    创建项目
    
    功能要求（需求文档3.1.1）:
    - 输入项目名称、编码、描述、负责人
    - 项目编码唯一
    
    权限要求: project:create
    """
    logger.info(f"创建项目请求数据: {project_in.model_dump()}")
    logger.info(f"当前用户: {current_user}")
    
    # 检查编码是否已存在
    existing = db.query(Project).filter(Project.code == project_in.code).first()
    if existing:
        if existing.deleted_at is not None:
            # 自动恢复回收站项目并更新信息
            existing.name = project_in.name
            existing.description = project_in.description
            existing.owner_id = project_in.owner_id
            existing.project_type = project_in.project_type or 'web'
            existing.restore()
            db.commit()
            db.refresh(existing)
            logger.info(f"从回收站恢复项目: {existing.code}")
            return ProjectResponse(**existing.__dict__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"项目编码 '{project_in.code}' 已存在"
        )
    
    project = Project(
        name=project_in.name,
        code=project_in.code,
        description=project_in.description,
        owner_id=project_in.owner_id or current_user["user"].id,
        status=ProjectStatus.ACTIVE.value,
        project_type=project_in.project_type or 'web',
        app_platform=project_in.app_platform,
        app_package_name=project_in.app_package_name,
        app_launch_activity=project_in.app_launch_activity,
    )
    
    db.add(project)
    db.commit()
    db.refresh(project)

    logger.info(f"创建项目成功: {project.code} - {project.name}")
    
    return ProjectResponse.model_validate(project)


@router.get("/", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词（名称/编码）"),
    status_filter: Optional[str] = Query(None, description="状态筛选: active/archived"),
    include_deleted: bool = Query(False, description="是否包含已删除"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_READ),
):
    """
    项目列表
    
    功能要求（需求文档3.1.1）:
    - 分页展示
    - 支持搜索（名称、编码）
    - 支持筛选（状态）
    
    权限要求: project:read
    """
    try:
        query = db.query(Project).filter(Project.deleted_at.is_(None))
        
        if status_filter:
            query = query.filter(Project.status == status_filter)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Project.name.ilike(search_pattern),
                    Project.code.ilike(search_pattern)
                )
            )
        
        total = query.count()
        
        total_pages = (total + page_size - 1) // page_size
        
        projects = query.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        
        return ProjectListResponse(
            items=[ProjectResponse.model_validate(p, from_attributes=True) for p in projects],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        import traceback
        print(f"List projects error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_READ),
):
    """
    项目详情
    
    功能要求（需求文档3.1.1）:
    - 查看项目概览
    - 版本列表
    - 统计信息
    
    权限要求: project:read
    """
    project = db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    # 过滤正在生成的版本
    from app.core.models.generation_task import GenerationTask, TaskStatus
    
    running_version_ids = db.query(GenerationTask.version_id).filter(
        GenerationTask.project_id == project_id,
        GenerationTask.status == TaskStatus.RUNNING
    ).all()
    running_version_ids = [v[0] for v in running_version_ids]
    
    versions_query = db.query(Version).filter(Version.project_id == project_id)
    if running_version_ids:
        versions_query = versions_query.filter(~Version.id.in_(running_version_ids))
    
    versions_count = versions_query.count()
    
    from app.core.models.test_simple import SimpleTestCase
    test_cases_count = db.query(SimpleTestCase).filter(SimpleTestCase.project_id == project_id).count()
    
    # 最新版本也过滤正在生成的
    latest_version_query = db.query(Version).filter(
        Version.project_id == project_id
    )
    if running_version_ids:
        latest_version_query = latest_version_query.filter(~Version.id.in_(running_version_ids))
    latest_version = latest_version_query.order_by(Version.created_at.desc()).first()
    
    response_data = {
        **ProjectResponse.model_validate(project).model_dump(),
        "versions_count": versions_count,
        "test_cases_count": test_cases_count,
        "latest_version": {
            "id": latest_version.id,
            "version_number": latest_version.version_number,
            "version_name": latest_version.version_name,
            "status": latest_version.status
        } if latest_version else None
    }
    
    return ProjectDetailResponse(**response_data)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE),
):
    """
    编辑项目
    
    功能要求（需求文档3.1.1）:
    - 修改项目基本信息
    
    权限要求: project:update
    """
    project = db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    update_data = project_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(project, field, value)
    
    db.commit()
    db.refresh(project)
    
    logger.info(f"更新项目成功: {project.code}")
    
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    hard_delete: bool = Query(False, description="是否硬删除"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_DELETE),
):
    """
    删除项目
    
    功能要求（需求文档3.1.1）:
    - 软删除，保留历史数据
    - 可选硬删除
    
    权限要求: project:delete
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    if hard_delete:
        # 级联清理项目关联的 UI 用例、功能用例、执行记录
        try:
            from app.core.models.web_ui_test import WebUITestCase as WUI
            from app.core.models.test_simple import SimpleTestCase, TestExecution
            _pid = str(project_id)
            # 清理执行中心记录
            db.query(TestExecution).filter(TestExecution.project_id == _pid).delete()
            # 清理 UI 用例（按 project_id）
            db.query(WUI).filter(WUI.project_id == _pid).delete()
            # 清理功能用例
            db.query(SimpleTestCase).filter(SimpleTestCase.project_id == _pid).delete()
            logger.info(f"已清理项目 {project.code} 的测试资产")
        except Exception as e:
            logger.warning(f"清理项目测试资产失败（可忽略）: {e}")
        db.delete(project)
        logger.info(f"硬删除项目: {project.code}")
    else:
        project.soft_delete()
        logger.info(f"软删除项目: {project.code}")

    db.commit()
    
    return None


@router.post("/{project_id}/restore", response_model=ProjectResponse)
def restore_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE),
):
    """
    恢复已删除的项目
    
    权限要求: project:update
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    if not project.is_deleted():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="项目未被删除，无需恢复"
        )
    
    project.restore()
    db.commit()
    db.refresh(project)
    
    logger.info(f"恢复项目: {project.code}")
    
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}/stats", response_model=ProjectStats)
def get_project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_READ),
):
    """
    获取项目统计信息
    
    权限要求: project:read
    """
    project = db.query(Project).filter(Project.id == project_id, Project.deleted_at.is_(None)).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    try:
        from app.core.models.test_simple import SimpleTestCase, TestExecution, TestStatus
        from app.core.models.generation_task import GenerationTask, TaskStatus
        
        # 过滤正在生成的版本
        running_version_ids = db.query(GenerationTask.version_id).filter(
            GenerationTask.project_id == project_id,
            GenerationTask.status == TaskStatus.RUNNING
        ).all()
        running_version_ids = [v[0] for v in running_version_ids]
        
        versions_query = db.query(Version).filter(Version.project_id == project_id)
        if running_version_ids:
            versions_query = versions_query.filter(~Version.id.in_(running_version_ids))
        
        total_versions = versions_query.count()
        
        total_test_cases = db.query(SimpleTestCase).filter(SimpleTestCase.project_id == str(project_id)).count()
        
        passed = db.query(SimpleTestCase).filter(
            SimpleTestCase.project_id == str(project_id),
            SimpleTestCase.status == TestStatus.ACTIVE.value
        ).count()
        
        failed = db.query(SimpleTestCase).filter(
            SimpleTestCase.project_id == str(project_id),
            SimpleTestCase.status == TestStatus.INACTIVE.value
        ).count()
        
        pending = db.query(SimpleTestCase).filter(
            SimpleTestCase.project_id == str(project_id),
            SimpleTestCase.status == TestStatus.DRAFT.value
        ).count()
        
        total_executions = db.query(TestExecution).filter(
            TestExecution.project_id == project_id
        ).count()
        
        latest_execution = db.query(TestExecution).filter(
            TestExecution.project_id == project_id
        ).order_by(TestExecution.created_at.desc()).first()
        
        return ProjectStats(
            total_versions=total_versions,
            total_test_cases=total_test_cases,
            passed_test_cases=passed,
            failed_test_cases=failed,
            pending_test_cases=pending,
            total_executions=total_executions,
            latest_execution_time=latest_execution.created_at if latest_execution else None
        )
    except Exception as e:
        logger.error(f"获取项目统计失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取项目统计失败: {str(e)}"
        )


@router.get("/code/{code}", response_model=ProjectResponse)
def get_project_by_code(
    code: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_READ),
):
    """
    根据项目编码获取项目
    
    权限要求: project:read
    """
    project = db.query(Project).filter(
        Project.code == code.lower(),
        Project.deleted_at.is_(None)
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目编码 '{code}' 不存在"
        )
    
    return ProjectResponse.model_validate(project)



# ═══════════════════════════════════════════════════════════
# APK 上传解析 — 自动提取包名、启动 Activity
# ═══════════════════════════════════════════════════════════

@router.post("/{project_id}/upload-apk")
async def upload_apk(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.PROJECT_UPDATE),
):
    """上传 APK 文件，自动解析包名、启动 Activity 等并保存到项目配置。"""
    import os, tempfile, subprocess, re

    project = db.query(Project).filter(
        Project.id == project_id, Project.deleted_at.is_(None)
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"项目ID {project_id} 不存在")
    if not file.filename or not file.filename.lower().endswith('.apk'):
        raise HTTPException(status_code=400, detail="请上传 .apk 格式的 Android 安装包")

    apk_content = await file.read()
    if len(apk_content) < 1024:
        raise HTTPException(status_code=400, detail="APK 文件无效")

    tmp = tempfile.NamedTemporaryFile(suffix='.apk', delete=False)
    apk_path = tmp.name
    try:
        tmp.write(apk_content); tmp.close()
        info = {"package_name": "", "launch_activity": "", "version_name": "", "version_code": ""}

        # aapt
        try:
            r = subprocess.run(['aapt', 'dump', 'badging', apk_path],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if line.startswith('package:'):
                        m = re.search(r"name='([^']+)'", line)
                        if m: info['package_name'] = m.group(1)
                        m = re.search(r"versionName='([^']*)'", line)
                        if m: info['version_name'] = m.group(1)
                        m = re.search(r"versionCode='([^']*)'", line)
                        if m: info['version_code'] = m.group(1)
                    elif line.startswith('launchable-activity:'):
                        m = re.search(r"name='([^']+)'", line)
                        if m: info['launch_activity'] = m.group(1)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # zipfile 内解析 AndroidManifest.xml
        if not info['package_name']:
            import zipfile as _zf
            try:
                with _zf.ZipFile(apk_path, 'r') as zf:
                    if 'AndroidManifest.xml' in zf.namelist():
                        raw = zf.read('AndroidManifest.xml')
                        text = raw.decode('utf-8', errors='ignore')
                        m = re.search(r'package\s*=\s*"([^"]+)"', text)
                        if m: info['package_name'] = m.group(1)
                        acts = re.findall(r'activity.*?android:name\s*=\s*"([^"]+)"', text, re.DOTALL)
                        if acts: info['launch_activity'] = acts[-1]
                        m = re.search(r'versionName\s*=\s*"([^"]+)"', text)
                        if m: info['version_name'] = m.group(1)
                        m = re.search(r'versionCode\s*=\s*"([^"]+)"', text)
                        if m: info['version_code'] = m.group(1)
            except Exception:
                pass

        if not info['package_name']:
            raise HTTPException(status_code=400, detail="无法解析 APK，请确认文件完整")

        # 保存到项目探索配置
        from app.core.models.project_ext import ProjectSetting
        psetting = db.query(ProjectSetting).filter(
            ProjectSetting.project_id == project_id
        ).first()
        if not psetting:
            psetting = ProjectSetting(project_id=project_id, exploration_config={})
            db.add(psetting)
        _ec = psetting.exploration_config or {}
        _ec['app'] = {
            **(_ec.get('app', {}) or {}),
            'apk_package': info['package_name'],
            'apk_activity': info['launch_activity'],
            'apk_version_name': info['version_name'],
            'apk_version_code': info['version_code'],
            'apk_filename': file.filename,
        }
        psetting.exploration_config = _ec
        db.commit()

        return {
            "success": True,
            "filename": file.filename,
            "package_name": info['package_name'],
            "launch_activity": info['launch_activity'],
            "version_name": info['version_name'],
            "version_code": info['version_code'],
        }
    finally:
        try: os.unlink(apk_path)
        except Exception: pass
