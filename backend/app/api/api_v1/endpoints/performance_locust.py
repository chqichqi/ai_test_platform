"""
Locust性能测试API端点
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.performance_locust import LocustScript, LocustExecution
from app.core.schemas.performance_locust import (
    LocustScriptCreate, LocustScriptResponse, LocustScriptListResponse,
    LocustExecutionStart, LocustExecutionResponse, LocustExecutionListResponse,
    LocustMetricsResponse, ApprovedApiCaseResponse, ApprovedApiCaseListResponse,
)
from app.core.services.locust_service import LocustService
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


def get_locust_service(db: Session = Depends(get_db)) -> LocustService:
    return LocustService(db)


# ===== Locust 脚本管理 =====

@router.post("/locust/scripts", response_model=LocustScriptResponse)
def create_locust_script(
    request: LocustScriptCreate,
    service: LocustService = Depends(get_locust_service),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_CREATE)
):
    """从已审批的API用例创建Locust脚本"""
    try:
        script = service.create_script_from_api_cases(
            project_id=request.project_id,
            name=request.name,
            case_ids=request.case_ids,
            host=request.host,
            description=request.description,
            created_by=str(current_user["user"].id),
        )
        return script
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建Locust脚本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locust/scripts", response_model=LocustScriptListResponse)
def list_locust_scripts(
    project_id: int = Query(..., description="项目ID"),
    service: LocustService = Depends(get_locust_service),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """列出项目的Locust脚本"""
    scripts = service.list_scripts(project_id)
    return LocustScriptListResponse(
        items=[LocustScriptResponse.model_validate(s) for s in scripts],
        total=len(scripts)
    )


@router.get("/locust/scripts/{script_id}", response_model=LocustScriptResponse)
def get_locust_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """获取Locust脚本详情"""
    script = db.query(LocustScript).filter(LocustScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    return script


@router.put("/locust/scripts/{script_id}", response_model=LocustScriptResponse)
def update_locust_script(
    script_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    file_content: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_UPDATE)
):
    """更新Locust脚本"""
    script = db.query(LocustScript).filter(LocustScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")

    if name is not None:
        script.name = name
    if description is not None:
        script.description = description
    if file_content is not None:
        script.file_content = file_content
        script.file_size = len(file_content)
        script.version += 1

    script.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(script)
    return script


@router.delete("/locust/scripts/{script_id}")
def delete_locust_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_DELETE)
):
    """删除Locust脚本"""
    script = db.query(LocustScript).filter(LocustScript.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    db.delete(script)
    db.commit()
    return {"message": "删除成功"}


# ===== Locust 执行管理 =====

@router.post("/locust/executions", response_model=LocustExecutionResponse)
def start_locust_execution(
    request: LocustExecutionStart,
    service: LocustService = Depends(get_locust_service),
    current_user: dict = Depends(Permissions.TEST_EXECUTE)
):
    """启动Locust执行"""
    try:
        step_config = None
        if request.step_config and request.step_config.enabled:
            step_config = {
                "enabled": True,
                "step_count": request.step_config.step_count,
                "step_duration": request.step_config.step_duration,
                "step_thread_increment": request.step_config.step_thread_increment,
                "max_users": request.step_config.max_users or (
                    request.step_config.step_count * request.step_config.step_thread_increment
                ),
            }

        # 使用传入的host，或从脚本获取
        host = request.host

        execution = service.start_execution(
            script_id=request.script_id,
            host=host,
            num_users=request.num_users,
            spawn_rate=request.spawn_rate,
            run_time=request.run_time,
            step_config=step_config,
            project_id=request.project_id,
            name=request.name,
            created_by=str(current_user["user"].id),
        )
        return execution
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"启动Locust执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/locust/executions/{execution_id}/stop")
def stop_locust_execution(
    execution_id: int,
    service: LocustService = Depends(get_locust_service),
    current_user: dict = Depends(Permissions.TEST_EXECUTE)
):
    """停止Locust执行"""
    try:
        service.stop_execution(execution_id)
        return {"message": "执行已停止", "execution_id": execution_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"停止Locust执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locust/executions", response_model=LocustExecutionListResponse)
def list_locust_executions(
    project_id: Optional[int] = Query(None, description="项目ID"),
    script_id: Optional[int] = Query(None, description="脚本ID"),
    service: LocustService = Depends(get_locust_service),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """列出Locust执行记录"""
    executions = service.list_executions(project_id=project_id, script_id=script_id)
    return LocustExecutionListResponse(
        items=[LocustExecutionResponse.model_validate(e) for e in executions],
        total=len(executions)
    )


@router.get("/locust/executions/{execution_id}", response_model=LocustExecutionResponse)
def get_locust_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """获取Locust执行详情"""
    execution = db.query(LocustExecution).filter(LocustExecution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return execution


@router.get("/locust/executions/{execution_id}/metrics", response_model=LocustMetricsResponse)
def get_locust_execution_metrics(
    execution_id: int,
    service: LocustService = Depends(get_locust_service),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """获取Locust执行实时指标"""
    return service.get_metrics(execution_id)


# ===== 已审批API用例（性能测试专用） =====

@router.get("/locust/approved-cases", response_model=ApprovedApiCaseListResponse)
def get_approved_api_cases(
    project_id: int = Query(..., description="项目ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, description="搜索关键词"),
    method: Optional[str] = Query(None, description="请求方法"),
    priority: Optional[str] = Query(None, description="优先级"),
    service: LocustService = Depends(get_locust_service),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """获取已审批的API测试用例列表（用于性能测试用例选择）"""
    cases, total = service.get_approved_api_cases(
        project_id=project_id,
        page=page,
        page_size=page_size,
        search=search,
        method=method,
        priority=priority,
    )

    return ApprovedApiCaseListResponse(
        items=[ApprovedApiCaseResponse.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )
