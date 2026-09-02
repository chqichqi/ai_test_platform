"""
版本管理API端点 - 完整实现
对应需求文档 3.1.2 版本管理
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.models.project import Project, Version, VersionStatus
from app.core.schemas.project import (
    VersionCreate, VersionUpdate, VersionStatusUpdate,
    VersionResponse, VersionListResponse, VersionDetailResponse,
    VersionReuseCases,
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.post("/", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    version_in: VersionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE),
    auto_generate: bool = Query(True, description="是否自动生成测试资产"),
    async_mode: bool = Query(False, description="是否异步生成（默认同步，体验更好）")
):
    """
    创建版本
    
    功能要求（需求文档 3.1.2）:
    - 选择项目，输入版本号、版本名称、计划时间
    - 版本号在项目内唯一
    - 需求文档为必填项
    - 可选：创建后自动生成测试用例
    
    异步模式：
    - 大文档（>10KB）推荐使用异步模式
    - 异步模式立即返回版本信息，后台生成测试用例
    - 前端可通过 /generation/tasks/{task_id} 查询进度
    """
    try:
        project = db.query(Project).filter(
            Project.id == version_in.project_id,
            Project.deleted_at.is_(None)
        ).first()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"项目 ID {version_in.project_id} 不存在"
            )
        
        existing = db.query(Version).filter(
            Version.project_id == version_in.project_id,
            Version.version_number == version_in.version_number
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"版本号 '{version_in.version_number}' 在该项目中已存在"
            )

        # 项目前置配置门控（2026-09-01 用户定性）：创建项目后，必须先完成
        # ①项目配置（目标系统 URL）②登录模块（导入并验证登录流程），才能创建版本。
        # 两项判定与业务流校验/前端状态查询同源（login_module_store 统一判定源）。
        from app.core.services.login_module_store import (
            has_login_module_configured,
            has_project_web_configured,
        )
        if not has_project_web_configured(db, project.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建版本前必须先完成项目配置：请在项目卡片点击「项目配置」，填写目标系统 URL 后再创建版本"
            )
        if not has_login_module_configured(db, project.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建版本前必须先配置登录鉴权：请在项目卡片点击「项目配置」，在「登录模块」页签导入并验证登录流程后再创建版本"
            )
        
        version = Version(
            project_id=version_in.project_id,
            version_number=version_in.version_number,
            version_name=version_in.version_name,
            description=version_in.description,
            requirement_doc=version_in.requirement_doc,
            requirement_doc_file=version_in.requirement_doc_file,
            requirement_doc_file_type=version_in.requirement_doc_file_type,
            plan_start_date=version_in.plan_start_date,
            plan_end_date=version_in.plan_end_date,
            status=VersionStatus.PLANNING.value
        )
        
        db.add(version)
        db.flush()

        version_id_value = version.id

        # 登录模块业务流内容已迁至项目级（ProjectSetting.exploration_config.login_module_content，
        # 同一项目同一套登录逻辑，跨版本共享）——创建版本不再自动创建登录模块版本文档。
        if version_in.requirement_doc:
            from app.core.models.requirement import RequirementDocument, DocumentType
            req_doc = RequirementDocument(
                version_id=version_id_value,
                name=f"{version.version_number} 需求文档",
                type=DocumentType.TEXT.value,
                content=version_in.requirement_doc,
                status="parsed"
            )
            db.add(req_doc)
            db.flush()
        
        logger.info(f"已准备版本数据：{project.code}/{version.version_number}, version_id={version_id_value}")
        
        task_id = None
        task_display_id = None
        test_cases_count = 0
        
        if auto_generate and version_in.requirement_doc:
            doc_length = len(version_in.requirement_doc)
            
            if async_mode or doc_length > 10000:
                from app.core.models.generation_task import GenerationTask, TaskType
                from app.core.services.async_generation_service import (
                    create_generation_task, run_generation_task
                )
                
                task = create_generation_task(
                    db=db,
                    project_id=version.project_id,
                    version_id=version_id_value,
                    task_type=TaskType.TEST_CASE_GENERATION,
                    input_data={
                        "project_name": project.name,
                        "version_number": version.version_number,
                        "requirement_doc_content": version_in.requirement_doc,
                    },
                    user_id=current_user.get("id")
                )
                
                task_id = task.id
                
                # 生成display_id
                task_display_id = f"{task.created_at.strftime('%y%m%d%H%M%S')}{task.id}"
                
                db.commit()
                db.refresh(version)
                
                background_tasks.add_task(run_generation_task, task_id)
                
                logger.info(f"创建异步生成任务：task_id={task_id}, display_id={task_display_id}, 版本={version.version_number}")
            else:
                try:
                    from app.core.services.version_generator import VersionGeneratorService
                    
                    generator = VersionGeneratorService(db)
                    gen_result = await generator.generate_test_assets(
                        version_id=version.id,
                        requirement_doc_content=version_in.requirement_doc or '',
                        project_name=project.name,
                        version_number=version.version_number
                    )
                    
                    if gen_result.get("success"):
                        test_cases_count = gen_result.get("test_cases_count", 0)
                        logger.info(f"同步生成完成：{test_cases_count}条用例")
                        db.commit()
                    else:
                        logger.error(f"同步生成失败：{gen_result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"同步生成异常：{e}")
                    import traceback
                    traceback.print_exc()
        
        db.commit()
        db.refresh(version)
        
        version_data = {
            **version.__dict__,
            'test_cases_count': test_cases_count,
            'generation_task_id': task_id,
            'generation_task_display_id': task_display_id if task_id else None,
        }
        
        if '_sa_instance_state' in version_data:
            del version_data['_sa_instance_state']
        
        return VersionResponse(**version_data)
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"创建版本失败：{str(e)}\n{tb}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建版本失败：{type(e).__name__}: {str(e)}"
        )


@router.get("/", response_model=VersionListResponse)
def list_versions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    project_id: Optional[int] = Query(None, description="项目ID筛选"),
    status_filter: Optional[str] = Query(None, description="状态筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    版本列表
    
    功能要求（需求文档3.1.2）:
    - 分页展示
    - 按项目筛选
    - 按状态筛选
    - 支持搜索
    """
    query = db.query(Version)
    
    if project_id:
        query = query.filter(Version.project_id == project_id)
    
    if status_filter:
        query = query.filter(Version.status == status_filter)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Version.version_number.ilike(search_pattern),
                Version.version_name.ilike(search_pattern)
            )
        )
    
    total = query.count()
    
    total_pages = (total + page_size - 1) // page_size
    
    versions = query.order_by(Version.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    # 计算每个版本的测试用例数量（方案B：该版本视角的【生效行】计数，含跨版本派生链）
    from app.core.models.requirement import TestCase
    from app.core.services.case_versioning import resolve_effective_cases
    version_items = []
    for v in versions:
        tc_count = len(resolve_effective_cases(db, v.project_id, v.id))
        version_data = {
            **v.__dict__,
            'requirement_doc': v.requirement_doc,
            'test_cases_count': tc_count,
        }
        version_items.append(VersionResponse(**version_data))
    
    return VersionListResponse(
        items=version_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{version_id}", response_model=VersionDetailResponse)
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    版本详情
    
    功能要求（需求文档3.1.2）:
    - 查看版本信息
    - 查看关联的测试用例数、测试计划数
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本ID {version_id} 不存在"
        )
    
    from app.core.models.requirement import TestCase
    from app.core.services.case_versioning import resolve_effective_cases

    # 方案B：该版本视角的生效行计数（含跨版本派生链）
    test_cases_count = len(resolve_effective_cases(db, version.project_id, version_id))

    response_data = {
        **VersionResponse.model_validate(version).model_dump(),
        "requirement_doc": version.requirement_doc,
        "requirement_doc_url": version.requirement_doc_url,
        "test_cases_count": test_cases_count,
        "test_plans_count": 0
    }
    
    return VersionDetailResponse(**response_data)


@router.put("/{version_id}", response_model=VersionResponse)
def update_version(
    version_id: int,
    version_in: VersionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """
    编辑版本
    
    功能要求（需求文档3.1.2）:
    - 修改版本信息
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本ID {version_id} 不存在"
        )
    
    update_data = version_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(version, field, value)
    
    db.commit()
    db.refresh(version)
    
    logger.info(f"更新版本成功: {version.version_number}")
    
    return VersionResponse.model_validate(version)


@router.put("/{version_id}/status", response_model=VersionResponse)
def update_version_status(
    version_id: int,
    status_in: VersionStatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """
    更新版本状态
    
    功能要求（需求文档3.1.2）:
    - 版本状态流转: 规划中 → 开发中 → 测试中 → 已发布 → 已归档
    - 状态变更需符合规则
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本ID {version_id} 不存在"
        )
    
    new_status = status_in.status
    
    if not version.can_transition_to(new_status):
        current_status = VersionStatus(version.status)
        allowed = [s.value for s in version.VALID_STATUS_TRANSITIONS.get(current_status, [])]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法从 '{version.get_status_display()}' 转换到 '{new_status.value}'。允许的状态: {allowed}"
        )
    
    version.transition_to(new_status)
    db.commit()
    db.refresh(version)
    
    logger.info(f"版本状态更新: {version.version_number} -> {new_status.value}")
    
    return VersionResponse.model_validate(version)


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """
    删除版本
    
    注意：版本可以删除，但如果正在生成中需要先取消生成任务
    级联删除：测试用例、思维导图、需求文档、生成任务
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 ID {version_id} 不存在"
        )
    
    from app.core.models.generation_task import GenerationTask, TaskStatus
    
    running_tasks = db.query(GenerationTask).filter(
        GenerationTask.version_id == version_id,
        GenerationTask.status == TaskStatus.RUNNING
    ).all()
    
    if running_tasks:
        for task in running_tasks:
            task.status = TaskStatus.CANCELLED
            task.error_message = "版本被删除，任务自动取消"
        db.commit()
        logger.warning(f"取消 {len(running_tasks)} 个正在运行的生成任务")
    
    from app.core.models.requirement import TestCase, RequirementDocument
    from app.core.models.requirement_change import RequirementChangeRecord, RequirementChangeBatch
    from app.core.models.knowledge_graph import KnowledgeGraph
    from app.core.models.api_test import ApiTestCase, ApiTestExecution, ApiTestVersion

    test_cases_count = db.query(TestCase).filter(TestCase.version_id == version_id).count()
    requirement_docs_count = db.query(RequirementDocument).filter(RequirementDocument.version_id == version_id).count()
    api_test_cases_count = db.query(ApiTestCase).filter(ApiTestCase.version_id == version_id).count()
    gen_tasks_count = db.query(GenerationTask).filter(GenerationTask.version_id == version_id).count()
    change_records_count = db.query(RequirementChangeRecord).filter(RequirementChangeRecord.version_id == version_id).count()
    change_batches_count = db.query(RequirementChangeBatch).filter(RequirementChangeBatch.version_id == version_id).count()
    knowledge_graph_count = db.query(KnowledgeGraph).filter(KnowledgeGraph.version_id == version_id).count()
    
    logger.info(
        f"准备删除版本 {version.version_number}："
        f"{test_cases_count} 个功能用例，"
        f"{api_test_cases_count} 个API用例，"
        f"{requirement_docs_count} 个需求文档，"
        f"{gen_tasks_count} 个生成任务，"
        f"{change_records_count} 个变更记录，"
        f"{change_batches_count} 个变更批次，"
        f"{knowledge_graph_count} 个知识图谱"
    )
    
    gen_tasks = db.query(GenerationTask).filter(GenerationTask.version_id == version_id).all()
    for task in gen_tasks:
        db.delete(task)
    
    change_records = db.query(RequirementChangeRecord).filter(RequirementChangeRecord.version_id == version_id).all()
    for record in change_records:
        db.delete(record)
    
    change_batches = db.query(RequirementChangeBatch).filter(RequirementChangeBatch.version_id == version_id).all()
    for batch in change_batches:
        db.delete(batch)
    
    # API测试专用版本：解除关联
    api_test_versions = db.query(ApiTestVersion).filter(ApiTestVersion.version_id == version_id).all()
    for atv in api_test_versions:
        atv.version_id = None

    api_test_cases = db.query(ApiTestCase).filter(ApiTestCase.version_id == version_id).all()
    for atc in api_test_cases:
        # 先删执行记录（FK → api_test_cases），再删用例本身
        db.query(ApiTestExecution).filter(ApiTestExecution.case_id == atc.id).delete()
        db.delete(atc)

    # 知识图谱是项目级资产：删版本只解除来源关联，不删 KG（数据仍属项目）
    db.query(KnowledgeGraph).filter(KnowledgeGraph.version_id == version_id).update(
        {KnowledgeGraph.version_id: None}
    )

    db.delete(version)
    db.commit()
    
    logger.info(
        f"删除版本成功：{version.version_number}，"
        f"级联删除 {test_cases_count} 个测试用例，"
        f"{change_records_count} 个变更记录，"
        f"{change_batches_count} 个变更批次，"
        f"{knowledge_graph_count} 个知识图谱（解除来源关联，项目级保留）"
    )
    
    return None


@router.get("/project/{project_id}", response_model=VersionListResponse)
def list_versions_by_project(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: Optional[str] = Query(None),
    include_generating: bool = Query(False, description="是否包含正在生成中的版本"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    获取项目下的版本列表
    
    默认隐藏正在生成中的版本，生成完成后才显示
    """
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.deleted_at.is_(None)
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目ID {project_id} 不存在"
        )
    
    from app.core.models.generation_task import GenerationTask, TaskStatus
    
    running_version_ids = db.query(GenerationTask.version_id).filter(
        GenerationTask.project_id == project_id,
        GenerationTask.status == TaskStatus.RUNNING
    ).all()
    running_version_ids = [v[0] for v in running_version_ids]
    
    query = db.query(Version).filter(Version.project_id == project_id)
    
    if not include_generating and running_version_ids:
        query = query.filter(~Version.id.in_(running_version_ids))
    
    if status_filter:
        query = query.filter(Version.status == status_filter)
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    versions = query.order_by(Version.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    # 计算每个版本的测试用例数量
    from app.core.models.requirement import TestCase
    version_items = []
    for v in versions:
        tc_count = db.query(TestCase).filter(TestCase.version_id == v.id).count()
        version_data = {
            **v.__dict__,
            'requirement_doc': v.requirement_doc,
            'test_cases_count': tc_count,
            'is_generating': v.id in running_version_ids,
        }
        version_items.append(VersionResponse(**version_data))
    
    return VersionListResponse(
        items=version_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{version_id}/status-history")
def get_version_status_history(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    获取版本状态历史（为未来扩展预留）
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 ID {version_id} 不存在"
        )
    
    return {
        "version_id": version.id,
        "version_number": version.version_number,
        "current_status": version.status,
        "status_display": version.get_status_display(),
        "available_transitions": [
            s.value for s in version.VALID_STATUS_TRANSITIONS.get(VersionStatus(version.status), [])
        ]
    }


@router.post("/{version_id}/generate-assets")
async def generate_test_assets(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE),
    source_type: str = "ai",
):
    """
    生成测试资产（测试用例）

    根据版本的需求文档自动生成测试用例
    source_type: 来源类型，默认 'ai'（需求导入），业务流导入传 'business_flow'
    """
    version = db.query(Version).filter(Version.id == version_id).first()

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"版本 ID {version_id} 不存在"
        )

    if not version.requirement_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="版本没有关联需求文档，无法生成测试资产"
        )

    project = version.project
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目不存在"
        )

    from app.core.services.version_generator import VersionGeneratorService

    generator = VersionGeneratorService(db)
    result = await generator.generate_test_assets(
        version_id=version_id,
        requirement_doc_content=version.requirement_doc,
        project_name=project.name,
        version_number=version.version_number,
        source_type=source_type,
    )

    if result.get("success"):
        logger.info(f"测试资产生成成功：{result}")
        return {
            "success": True,
            "message": "测试资产生成成功",
            "data": result
        }
    else:
        logger.error(f"测试资产生成失败：{result.get('error')}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成失败：{result.get('error', '未知错误')}"
        )


@router.post("/{version_id}/reuse-cases")
def reuse_cases(
    version_id: int,
    reuse_in: VersionReuseCases,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE),
):
    """跨版本复用用例（用户确认：创建新版本时从任意历史版本复制用例到新版本，两种模式）：
    - 全模块模式：module 指定 → 源版本视角该模块全部生效用例一起复制
    - 勾选模式：case_ids 指定 → 只复制勾选的用例（模块只是 UI 筛选维度）

    共同语义：
    - 来源视角生效行（被派生冻结的旧行在来源视角不可见，与生效口径一致）
    - 复用新行延续逻辑用例时间线：logical_case_id 保留、revision_no 递增、derived_from_id=源行 id、
      status=源行状态原样（非冻结源）、generated_by="version_reuse"
    - 幂等：目标版本已有该逻辑用例显式行 → 跳过，重复提交不产生重复行
    """
    if not reuse_in.case_ids and not reuse_in.module:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="case_ids（勾选模式）与 module（全模块模式）至少提供一项"
        )

    target = db.query(Version).filter(Version.id == version_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"目标版本 ID {version_id} 不存在"
        )

    source = db.query(Version).filter(Version.id == reuse_in.source_version_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"来源版本 ID {reuse_in.source_version_id} 不存在"
        )
    if source.project_id != target.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="来源版本与目标版本不属于同一项目，无法复用"
        )

    from app.core.services.case_versioning import reuse_cases as _reuse_cases

    result = _reuse_cases(
        db,
        project_id=target.project_id,
        target_version_id=target.id,
        source_version_id=source.id,
        case_ids=reuse_in.case_ids,
        module=reuse_in.module,
        created_by=current_user["user"].id,
    )
    logger.info(
        f"[Version] 跨版本复用用例: target={target.id} source={source.id} "
        f"module={reuse_in.module} cases={reuse_in.case_ids} "
        f"→ {result['reused_count']} 复用 / {result['skipped_count']} 跳过"
    )
    mode = "全模块" if reuse_in.module and not reuse_in.case_ids else "勾选"
    return {"success": True, "message": f"{mode}复用完成：{result['reused_count']} 条", **result}