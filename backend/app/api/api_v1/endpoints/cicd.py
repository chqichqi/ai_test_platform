"""
CI/CD集成API端点
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.cicd import (
    CICDConfig, PipelineDefinition, PipelineExecution, WebhookEvent,
    CICDPlatform, PipelineStatus, TriggerType
)
from app.core.schemas.cicd import (
    CICDConfigCreate, CICDConfigUpdate, CICDConfigResponse, CICDConfigListResponse,
    PipelineDefinitionCreate, PipelineDefinitionUpdate, PipelineDefinitionResponse, PipelineListResponse,
    PipelineExecutionResponse, ExecutionListResponse,
    TriggerPipelineRequest, TriggerPipelineResponse,
    CICDDashboardStats
)
from app.core.services.cicd_service import CICDService
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.post("/configs", response_model=CICDConfigResponse, status_code=status.HTTP_201_CREATED)
def create_config(
    config_in: CICDConfigCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建CI/CD配置"""
    config = CICDConfig(
        project_id=config_in.project_id,
        name=config_in.name,
        platform=config_in.platform,
        platform_url=config_in.platform_url,
        api_token=config_in.api_token,
        username=config_in.username,
        webhook_secret=config_in.webhook_secret,
        config_data=config_in.config_data,
        enabled=config_in.enabled,
        created_by=current_user["user"].id
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    config.webhook_url = f"/api/v1/cicd/webhook/{config.platform}/{config.id}"
    db.commit()
    
    logger.info(f"创建CI/CD配置: {config.name}, platform={config.platform}")
    
    return CICDConfigResponse.model_validate(config)


@router.get("/configs", response_model=CICDConfigListResponse)
def list_configs(
    project_id: int = Query(..., description="项目ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取CI/CD配置列表"""
    query = db.query(CICDConfig).filter(CICDConfig.project_id == project_id)
    
    total = query.count()
    configs = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return CICDConfigListResponse(
        items=[CICDConfigResponse.model_validate(c) for c in configs],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/configs/{config_id}", response_model=CICDConfigResponse)
def get_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取CI/CD配置详情"""
    config = db.query(CICDConfig).filter(CICDConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="CI/CD配置不存在")
    
    return CICDConfigResponse.model_validate(config)


@router.put("/configs/{config_id}", response_model=CICDConfigResponse)
def update_config(
    config_id: int,
    config_in: CICDConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新CI/CD配置"""
    config = db.query(CICDConfig).filter(CICDConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="CI/CD配置不存在")
    
    update_data = config_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    
    db.commit()
    db.refresh(config)
    
    logger.info(f"更新CI/CD配置: {config.name}")
    
    return CICDConfigResponse.model_validate(config)


@router.delete("/configs/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除CI/CD配置"""
    config = db.query(CICDConfig).filter(CICDConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="CI/CD配置不存在")
    
    db.delete(config)
    db.commit()
    
    logger.info(f"删除CI/CD配置: {config.name}")
    
    return {"message": "删除成功"}


@router.post("/configs/{config_id}/test")
async def test_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """测试CI/CD配置连接"""
    cicd_service = CICDService(db)
    result = await cicd_service.test_config(config_id)
    
    return result


@router.post("/pipelines", response_model=PipelineDefinitionResponse, status_code=status.HTTP_201_CREATED)
def create_pipeline(
    pipeline_in: PipelineDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建Pipeline定义"""
    config = db.query(CICDConfig).filter(CICDConfig.id == pipeline_in.config_id).first()
    if not config:
        raise HTTPException(status_code=400, detail="CI/CD配置不存在")
    
    pipeline = PipelineDefinition(
        config_id=pipeline_in.config_id,
        project_id=pipeline_in.project_id,
        name=pipeline_in.name,
        external_id=pipeline_in.external_id,
        trigger_type=pipeline_in.trigger_type,
        trigger_config=pipeline_in.trigger_config,
        test_plan_id=pipeline_in.test_plan_id,
        test_case_ids=pipeline_in.test_case_ids,
        test_params=pipeline_in.test_params,
        environment=pipeline_in.environment,
        timeout=pipeline_in.timeout,
        notification_config=pipeline_in.notification_config,
        enabled=pipeline_in.enabled,
        created_by=current_user["user"].id
    )
    
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    
    logger.info(f"创建Pipeline: {pipeline.name}")
    
    return PipelineDefinitionResponse.model_validate(pipeline)


@router.get("/pipelines", response_model=PipelineListResponse)
def list_pipelines(
    project_id: int = Query(..., description="项目ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取Pipeline列表"""
    query = db.query(PipelineDefinition).filter(PipelineDefinition.project_id == project_id)
    
    total = query.count()
    pipelines = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return PipelineListResponse(
        items=[PipelineDefinitionResponse.model_validate(p) for p in pipelines],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/pipelines/{pipeline_id}", response_model=PipelineDefinitionResponse)
def get_pipeline(
    pipeline_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取Pipeline详情"""
    pipeline = db.query(PipelineDefinition).filter(PipelineDefinition.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline不存在")
    
    return PipelineDefinitionResponse.model_validate(pipeline)


@router.put("/pipelines/{pipeline_id}", response_model=PipelineDefinitionResponse)
def update_pipeline(
    pipeline_id: int,
    pipeline_in: PipelineDefinitionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新Pipeline"""
    pipeline = db.query(PipelineDefinition).filter(PipelineDefinition.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline不存在")
    
    update_data = pipeline_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pipeline, key, value)
    
    db.commit()
    db.refresh(pipeline)
    
    logger.info(f"更新Pipeline: {pipeline.name}")
    
    return PipelineDefinitionResponse.model_validate(pipeline)


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(
    pipeline_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除Pipeline"""
    pipeline = db.query(PipelineDefinition).filter(PipelineDefinition.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline不存在")
    
    db.delete(pipeline)
    db.commit()
    
    logger.info(f"删除Pipeline: {pipeline.name}")
    
    return {"message": "删除成功"}


@router.post("/pipelines/trigger", response_model=TriggerPipelineResponse)
async def trigger_pipeline(
    request: TriggerPipelineRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """触发Pipeline执行"""
    cicd_service = CICDService(db)
    result = await cicd_service.trigger_pipeline(
        pipeline_id=request.pipeline_id,
        branch=request.branch,
        parameters=request.parameters,
        user_id=current_user["user"].id
    )
    
    return TriggerPipelineResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        execution_id=result.get("execution_id")
    )


@router.get("/executions", response_model=ExecutionListResponse)
def list_executions(
    project_id: int = Query(..., description="项目ID"),
    pipeline_id: Optional[int] = Query(None, description="Pipeline ID"),
    status: Optional[str] = Query(None, description="状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取执行记录列表"""
    query = db.query(PipelineExecution).filter(PipelineExecution.project_id == project_id)
    
    if pipeline_id:
        query = query.filter(PipelineExecution.pipeline_id == pipeline_id)
    if status:
        query = query.filter(PipelineExecution.status == status)
    
    total = query.count()
    executions = query.order_by(PipelineExecution.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return ExecutionListResponse(
        items=[
            PipelineExecutionResponse(
                **PipelineExecutionResponse.model_validate(e).model_dump(),
                pass_rate=e.pass_rate
            )
            for e in executions
        ],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/executions/{execution_id}", response_model=PipelineExecutionResponse)
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取执行记录详情"""
    execution = db.query(PipelineExecution).filter(PipelineExecution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    
    return PipelineExecutionResponse(
        **PipelineExecutionResponse.model_validate(execution).model_dump(),
        pass_rate=execution.pass_rate
    )


@router.get("/dashboard/{project_id}", response_model=CICDDashboardStats)
def get_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取CI/CD仪表盘统计"""
    cicd_service = CICDService(db)
    stats = cicd_service.get_dashboard_stats(project_id)
    
    return CICDDashboardStats(**stats)


@router.post("/webhook/{platform}/{config_id}")
async def handle_webhook(
    platform: str,
    config_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """处理Webhook回调"""
    if platform not in [p.value for p in CICDPlatform]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    config = db.query(CICDConfig).filter(CICDConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    headers = dict(request.headers)
    payload = await request.json()
    
    cicd_service = CICDService(db)
    result = await cicd_service.handle_webhook(platform, headers, payload)
    
    return result


@router.get("/jobs/{config_id}")
async def list_jobs(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取CI/CD平台的Job/Workflow列表"""
    config = db.query(CICDConfig).filter(CICDConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    cicd_service = CICDService(db)
    service = cicd_service.get_service(config)
    
    if config.platform == CICDPlatform.JENKINS.value:
        jobs = await service.list_jobs()
        return {"jobs": jobs}
    elif config.platform == CICDPlatform.GITLAB.value:
        projects = await service.list_projects()
        return {"projects": projects}
    elif config.platform == CICDPlatform.GITHUB.value:
        workflows = await service.list_workflows()
        return {"workflows": workflows}
    
    return {"jobs": []}