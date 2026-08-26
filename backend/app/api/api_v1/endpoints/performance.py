"""
性能测试API端点
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.models.performance import (
    JMeterScript, ScriptVersion, PerformanceScenario,
    PerformanceTestExecution, PerformanceMetric, PerformanceReport,
    GrafanaDashboard
)
from app.core.services.performance_service import (
    JMeterScriptService, PerformanceScenarioService, PerformanceExecutionService,
    GrafanaIntegrationService, PerformanceReportService,
    SCENARIO_STATUS_OPTIONS, SCRIPT_STATUS_OPTIONS
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


class ScriptCreate(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    file_content: Optional[str] = None


class ScriptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    file_content: Optional[str] = None
    version_note: Optional[str] = None


class ScenarioCreate(BaseModel):
    project_id: int
    script_id: int
    name: str
    description: Optional[str] = None
    concurrent_users: int = 100
    ramp_up_period: int = 60
    duration: int = 300
    target_tps: Optional[float] = None
    target_rt: Optional[float] = None
    error_rate_threshold: Optional[float] = 1.0
    thread_group_config: Optional[List[dict]] = None
    variables: Optional[dict] = None
    jmeter_properties: Optional[dict] = None


class ScenarioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    concurrent_users: Optional[int] = None
    ramp_up_period: Optional[int] = None
    duration: Optional[int] = None
    target_tps: Optional[float] = None
    target_rt: Optional[float] = None
    error_rate_threshold: Optional[float] = None
    thread_group_config: Optional[List[dict]] = None
    variables: Optional[dict] = None
    jmeter_properties: Optional[dict] = None
    enabled: Optional[bool] = None


class ExecutionStart(BaseModel):
    scenario_id: int
    name: Optional[str] = None
    triggered_by: Optional[str] = "manual"


class DashboardCreate(BaseModel):
    project_id: int
    name: str
    grafana_host: str
    api_key: Optional[str] = None
    dashboard_uid: Optional[str] = None


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    grafana_host: Optional[str] = None
    api_key: Optional[str] = None
    dashboard_uid: Optional[str] = None
    enabled: Optional[bool] = None


@router.post("/scripts", status_code=status.HTTP_201_CREATED)
def create_script(
    script_in: ScriptCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建JMeter脚本"""
    service = JMeterScriptService(db)
    script = service.create_script(
        project_id=script_in.project_id,
        name=script_in.name,
        description=script_in.description,
        file_content=script_in.file_content,
        created_by=current_user["user"].id
    )
    
    return {"id": script.id, "message": "创建成功", "version": script.version}


@router.post("/scripts/upload", status_code=status.HTTP_201_CREATED)
async def upload_script(
    project_id: int,
    name: str,
    file: UploadFile = File(...),
    description: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """上传JMX脚本文件"""
    if not file.filename.endswith(".jmx"):
        raise HTTPException(status_code=400, detail="只支持JMX文件")
    
    content = await file.read()
    file_content = content.decode("utf-8")
    
    service = JMeterScriptService(db)
    script = service.create_script(
        project_id=project_id,
        name=name,
        description=description,
        file_content=file_content,
        created_by=current_user["user"].id
    )
    
    return {"id": script.id, "message": "上传成功", "version": script.version}


@router.get("/scripts")
def list_scripts(
    project_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取脚本列表"""
    query = db.query(JMeterScript).filter(JMeterScript.project_id == project_id)
    
    total = query.count()
    scripts = query.order_by(JMeterScript.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "version": s.version,
                "status": s.status,
                "test_plan_name": s.test_plan_name,
                "file_size": s.file_size,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None
            }
            for s in scripts
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/scripts/{script_id}")
def get_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取脚本详情"""
    script = db.query(JMeterScript).filter(JMeterScript.id == script_id).first()
    
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    
    return {
        "id": script.id,
        "project_id": script.project_id,
        "name": script.name,
        "description": script.description,
        "version": script.version,
        "version_note": script.version_note,
        "status": script.status,
        "validation_message": script.validation_message,
        "test_plan_name": script.test_plan_name,
        "thread_groups": script.thread_groups,
        "samplers": script.samplers,
        "file_size": script.file_size,
        "created_at": script.created_at.isoformat() if script.created_at else None,
        "updated_at": script.updated_at.isoformat() if script.updated_at else None
    }


@router.put("/scripts/{script_id}")
def update_script(
    script_id: int,
    script_in: ScriptUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新脚本"""
    service = JMeterScriptService(db)
    
    try:
        script = service.update_script(
            script_id=script_id,
            name=script_in.name,
            description=script_in.description,
            file_content=script_in.file_content,
            version_note=script_in.version_note
        )
        return {"message": "更新成功", "version": script.version}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scripts/{script_id}/validate")
def validate_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """验证脚本"""
    service = JMeterScriptService(db)
    result = service.validate_script(script_id)
    
    return result


@router.get("/scripts/{script_id}/versions")
def list_script_versions(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取脚本版本历史"""
    versions = db.query(ScriptVersion).filter(
        ScriptVersion.script_id == script_id
    ).order_by(ScriptVersion.version.desc()).all()
    
    return {
        "items": [
            {
                "id": v.id,
                "version": v.version,
                "version_note": v.version_note,
                "created_at": v.created_at.isoformat() if v.created_at else None
            }
            for v in versions
        ]
    }


@router.delete("/scripts/{script_id}")
def delete_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除脚本"""
    script = db.query(JMeterScript).filter(JMeterScript.id == script_id).first()
    
    if not script:
        raise HTTPException(status_code=404, detail="脚本不存在")
    
    db.query(ScriptVersion).filter(ScriptVersion.script_id == script_id).delete()
    db.delete(script)
    db.commit()
    
    logger.info(f"删除JMeter脚本: {script.name}")
    
    return {"message": "删除成功"}


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
def create_scenario(
    scenario_in: ScenarioCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建性能测试场景"""
    service = PerformanceScenarioService(db)
    
    try:
        scenario = service.create_scenario(
            project_id=scenario_in.project_id,
            script_id=scenario_in.script_id,
            name=scenario_in.name,
            description=scenario_in.description,
            concurrent_users=scenario_in.concurrent_users,
            ramp_up_period=scenario_in.ramp_up_period,
            duration=scenario_in.duration,
            target_tps=scenario_in.target_tps,
            target_rt=scenario_in.target_rt,
            created_by=current_user["user"].id
        )
        return {"id": scenario.id, "message": "创建成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scenarios")
def list_scenarios(
    project_id: int = Query(...),
    script_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取场景列表"""
    query = db.query(PerformanceScenario).filter(
        PerformanceScenario.project_id == project_id
    )
    
    if script_id:
        query = query.filter(PerformanceScenario.script_id == script_id)
    
    total = query.count()
    scenarios = query.order_by(PerformanceScenario.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "script_id": s.script_id,
                "concurrent_users": s.concurrent_users,
                "duration": s.duration,
                "target_tps": s.target_tps,
                "target_rt": s.target_rt,
                "enabled": s.enabled,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in scenarios
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/scenarios/{scenario_id}")
def get_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取场景详情"""
    scenario = db.query(PerformanceScenario).filter(
        PerformanceScenario.id == scenario_id
    ).first()
    
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    
    return {
        "id": scenario.id,
        "project_id": scenario.project_id,
        "script_id": scenario.script_id,
        "name": scenario.name,
        "description": scenario.description,
        "concurrent_users": scenario.concurrent_users,
        "ramp_up_period": scenario.ramp_up_period,
        "duration": scenario.duration,
        "target_tps": scenario.target_tps,
        "target_rt": scenario.target_rt,
        "error_rate_threshold": scenario.error_rate_threshold,
        "thread_group_config": scenario.thread_group_config,
        "variables": scenario.variables,
        "jmeter_properties": scenario.jmeter_properties,
        "jmeter_args": scenario.jmeter_args,
        "slave_count": scenario.slave_count,
        "enabled": scenario.enabled,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None
    }


@router.put("/scenarios/{scenario_id}")
def update_scenario(
    scenario_id: int,
    scenario_in: ScenarioUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新场景"""
    service = PerformanceScenarioService(db)
    
    try:
        scenario = service.update_scenario(
            scenario_id=scenario_id,
            **scenario_in.model_dump(exclude_unset=True)
        )
        return {"message": "更新成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除场景"""
    scenario = db.query(PerformanceScenario).filter(
        PerformanceScenario.id == scenario_id
    ).first()
    
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    
    db.delete(scenario)
    db.commit()
    
    logger.info(f"删除性能测试场景: {scenario.name}")
    
    return {"message": "删除成功"}


@router.post("/executions/start", status_code=status.HTTP_201_CREATED)
async def start_execution(
    execution_in: ExecutionStart,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """启动性能测试执行"""
    service = PerformanceExecutionService(db)
    
    try:
        execution = service.start_execution(
            scenario_id=execution_in.scenario_id,
            name=execution_in.name,
            triggered_by=execution_in.triggered_by or "manual",
            created_by=current_user["user"].id
        )
        
        return {
            "id": execution.id,
            "name": execution.name,
            "status": execution.status,
            "message": "测试已启动"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/executions")
def list_executions(
    project_id: int = Query(...),
    scenario_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取执行记录列表"""
    query = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.project_id == project_id
    )
    
    if scenario_id:
        query = query.filter(PerformanceTestExecution.scenario_id == scenario_id)
    if status:
        query = query.filter(PerformanceTestExecution.status == status)
    
    total = query.count()
    executions = query.order_by(PerformanceTestExecution.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": e.id,
                "name": e.name,
                "scenario_id": e.scenario_id,
                "status": e.status,
                "passed": e.passed,
                "avg_tps": e.avg_tps,
                "avg_rt": e.avg_rt,
                "error_rate": e.error_rate,
                "start_time": e.start_time.isoformat() if e.start_time else None,
                "end_time": e.end_time.isoformat() if e.end_time else None,
                "created_at": e.created_at.isoformat() if e.created_at else None
            }
            for e in executions
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/executions/{execution_id}")
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取执行详情"""
    execution = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.id == execution_id
    ).first()
    
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    
    return {
        "id": execution.id,
        "project_id": execution.project_id,
        "scenario_id": execution.scenario_id,
        "script_id": execution.script_id,
        "name": execution.name,
        "status": execution.status,
        "start_time": execution.start_time.isoformat() if execution.start_time else None,
        "end_time": execution.end_time.isoformat() if execution.end_time else None,
        "actual_duration": execution.actual_duration,
        "avg_tps": execution.avg_tps,
        "max_tps": execution.max_tps,
        "avg_rt": execution.avg_rt,
        "min_rt": execution.min_rt,
        "max_rt": execution.max_rt,
        "p90_rt": execution.p90_rt,
        "p95_rt": execution.p95_rt,
        "p99_rt": execution.p99_rt,
        "total_samples": execution.total_samples,
        "success_samples": execution.success_samples,
        "error_samples": execution.error_samples,
        "error_rate": execution.error_rate,
        "throughput_kb": execution.throughput_kb,
        "passed": execution.passed,
        "pass_reason": execution.pass_reason,
        "report_path": execution.report_path,
        "grafana_dashboard_url": execution.grafana_dashboard_url,
        "triggered_by": execution.triggered_by,
        "created_at": execution.created_at.isoformat() if execution.created_at else None
    }


@router.post("/executions/{execution_id}/stop")
def stop_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """停止执行"""
    service = PerformanceExecutionService(db)
    
    try:
        execution = service.stop_execution(execution_id)
        return {"message": "已停止", "status": execution.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/executions/{execution_id}/metrics")
def get_execution_metrics(
    execution_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取执行指标"""
    service = PerformanceExecutionService(db)
    metrics = service.get_execution_metrics(execution_id, limit)
    
    return {
        "items": [
            {
                "id": m.id,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "elapsed_seconds": m.elapsed_seconds,
                "sampler_name": m.sampler_name,
                "tps": m.tps,
                "avg_rt": m.avg_rt,
                "active_threads": m.active_threads,
                "error_rate": m.error_rate
            }
            for m in metrics
        ]
    }


@router.post("/executions/{execution_id}/report")
def generate_report(
    execution_id: int,
    title: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """生成性能报告"""
    service = PerformanceReportService(db)
    
    try:
        report = service.generate_report(
            execution_id=execution_id,
            title=title,
            created_by=current_user["user"].id
        )
        return {"id": report.id, "message": "报告生成成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reports")
def list_reports(
    project_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取报告列表"""
    query = db.query(PerformanceReport).filter(
        PerformanceReport.project_id == project_id
    )
    
    total = query.count()
    reports = query.order_by(PerformanceReport.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "execution_id": r.execution_id,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in reports
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取报告详情"""
    report = db.query(PerformanceReport).filter(
        PerformanceReport.id == report_id
    ).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    
    return {
        "id": report.id,
        "title": report.title,
        "summary": report.summary,
        "conclusion": report.conclusion,
        "recommendations": report.recommendations,
        "metrics_summary": report.metrics_summary,
        "charts_data": report.charts_data,
        "report_path": report.report_path,
        "created_at": report.created_at.isoformat() if report.created_at else None
    }


@router.post("/dashboards", status_code=status.HTTP_201_CREATED)
def create_dashboard(
    dashboard_in: DashboardCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建Grafana仪表盘配置"""
    service = GrafanaIntegrationService(db)
    dashboard = service.create_dashboard(
        project_id=dashboard_in.project_id,
        name=dashboard_in.name,
        grafana_host=dashboard_in.grafana_host,
        api_key=dashboard_in.api_key,
        dashboard_uid=dashboard_in.dashboard_uid,
        created_by=current_user["user"].id
    )
    
    return {"id": dashboard.id, "message": "创建成功"}


@router.get("/dashboards")
def list_dashboards(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取仪表盘列表"""
    dashboards = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.project_id == project_id
    ).all()
    
    return {
        "items": [
            {
                "id": d.id,
                "name": d.name,
                "dashboard_url": d.dashboard_url,
                "grafana_host": d.grafana_host,
                "enabled": d.enabled,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in dashboards
        ]
    }


@router.get("/dashboards/{dashboard_id}")
def get_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取仪表盘详情"""
    dashboard = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.id == dashboard_id
    ).first()
    
    if not dashboard:
        raise HTTPException(status_code=404, detail="仪表盘不存在")
    
    service = GrafanaIntegrationService(db)
    embed_url = service.get_embed_url(dashboard_id)
    
    return {
        "id": dashboard.id,
        "name": dashboard.name,
        "dashboard_uid": dashboard.dashboard_uid,
        "dashboard_url": dashboard.dashboard_url,
        "embed_url": embed_url,
        "grafana_host": dashboard.grafana_host,
        "api_key": "***" if dashboard.api_key else None,
        "datasource_config": dashboard.datasource_config,
        "panels_config": dashboard.panels_config,
        "enabled": dashboard.enabled,
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None
    }


@router.put("/dashboards/{dashboard_id}")
def update_dashboard(
    dashboard_id: int,
    dashboard_in: DashboardUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新仪表盘配置"""
    dashboard = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.id == dashboard_id
    ).first()
    
    if not dashboard:
        raise HTTPException(status_code=404, detail="仪表盘不存在")
    
    update_data = dashboard_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(dashboard, key, value)
    
    if dashboard.dashboard_uid and dashboard.grafana_host:
        dashboard.dashboard_url = f"{dashboard.grafana_host}/d/{dashboard.dashboard_uid}"
    
    db.commit()
    
    return {"message": "更新成功"}


@router.post("/dashboards/{dashboard_id}/sync")
def sync_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """同步仪表盘配置"""
    service = GrafanaIntegrationService(db)
    result = service.sync_dashboard_config(dashboard_id)
    
    return result


@router.delete("/dashboards/{dashboard_id}")
def delete_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除仪表盘配置"""
    dashboard = db.query(GrafanaDashboard).filter(
        GrafanaDashboard.id == dashboard_id
    ).first()
    
    if not dashboard:
        raise HTTPException(status_code=404, detail="仪表盘不存在")
    
    db.delete(dashboard)
    db.commit()
    
    return {"message": "删除成功"}


@router.get("/dashboard/{project_id}")
def get_performance_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取性能测试仪表盘统计"""
    total_scripts = db.query(JMeterScript).filter(
        JMeterScript.project_id == project_id
    ).count()
    
    total_scenarios = db.query(PerformanceScenario).filter(
        PerformanceScenario.project_id == project_id
    ).count()
    
    total_executions = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.project_id == project_id
    ).count()
    
    passed_executions = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.project_id == project_id,
        PerformanceTestExecution.passed == True
    ).count()
    
    failed_executions = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.project_id == project_id,
        PerformanceTestExecution.passed == False
    ).count()
    
    recent_executions = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.project_id == project_id
    ).order_by(PerformanceTestExecution.created_at.desc()).limit(5).all()
    
    avg_metrics = {}
    completed_executions = db.query(PerformanceTestExecution).filter(
        PerformanceTestExecution.project_id == project_id,
        PerformanceTestExecution.status == "completed",
        PerformanceTestExecution.avg_tps != None
    ).limit(10).all()
    
    if completed_executions:
        avg_metrics["avg_tps"] = sum(e.avg_tps or 0 for e in completed_executions) / len(completed_executions)
        avg_metrics["avg_rt"] = sum(e.avg_rt or 0 for e in completed_executions) / len(completed_executions)
        avg_metrics["avg_error_rate"] = sum(e.error_rate or 0 for e in completed_executions) / len(completed_executions)
    
    return {
        "total_scripts": total_scripts,
        "total_scenarios": total_scenarios,
        "total_executions": total_executions,
        "passed_executions": passed_executions,
        "failed_executions": failed_executions,
        "pass_rate": (passed_executions / total_executions * 100) if total_executions > 0 else 0,
        "avg_metrics": avg_metrics,
        "recent_executions": [
            {
                "id": e.id,
                "name": e.name,
                "status": e.status,
                "passed": e.passed,
                "avg_tps": e.avg_tps,
                "avg_rt": e.avg_rt,
                "created_at": e.created_at.isoformat() if e.created_at else None
            }
            for e in recent_executions
        ]
    }


# ========== API→性能桥接端点 ==========

@router.get("/approved-cases")
def get_approved_api_cases(
    project_id: int = Query(..., description="项目ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """获取已审批的API测试用例列表（用于性能测试用例选择）"""
    from app.core.models.api_test import ApiTestCase

    query = db.query(ApiTestCase).filter(
        ApiTestCase.project_id == project_id,
        ApiTestCase.status.in_(["approved", "active"])
    )
    if search:
        query = query.filter(
            ApiTestCase.name.ilike(f"%{search}%") |
            ApiTestCase.path.ilike(f"%{search}%")
        )
    if method:
        query = query.filter(ApiTestCase.method == method.upper())
    if priority:
        query = query.filter(ApiTestCase.priority == priority)

    total = query.count()
    cases = query.order_by(ApiTestCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [
            {
                "id": c.id, "name": c.name, "method": c.method, "path": c.path,
                "priority": c.priority, "case_type": c.case_type,
                "description": c.description, "tags": c.tags,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in cases
        ],
        "total": total, "page": page, "page_size": page_size,
    }


class LinkCasesRequest(BaseModel):
    case_ids: List[int] = Field(...)


@router.post("/scenarios/{scenario_id}/link-cases")
def link_cases_to_scenario(
    scenario_id: int,
    request: LinkCasesRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_UPDATE)
):
    """关联已审批的API用例到性能测试场景"""
    from app.core.models.performance import PerformanceTestSource
    from app.core.models.api_test import ApiTestCase

    scenario = db.query(PerformanceScenario).filter(PerformanceScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")

    # 删除旧关联
    db.query(PerformanceTestSource).filter(
        PerformanceTestSource.scenario_id == scenario_id
    ).delete()

    # 创建新关联
    linked_count = 0
    for case_id in request.case_ids:
        case = db.query(ApiTestCase).filter(
            ApiTestCase.id == case_id,
            ApiTestCase.status.in_(["approved", "active"])
        ).first()
        if case:
            source = PerformanceTestSource(
                scenario_id=scenario_id,
                case_id=case_id,
                source_type="api_test",
            )
            db.add(source)
            linked_count += 1

    db.commit()
    return {"message": f"已关联 {linked_count} 个用例到场景", "linked_count": linked_count}


@router.get("/scenarios/{scenario_id}/linked-cases")
def get_linked_cases(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """获取场景已关联的API用例"""
    from app.core.models.performance import PerformanceTestSource
    from app.core.models.api_test import ApiTestCase

    sources = db.query(PerformanceTestSource).filter(
        PerformanceTestSource.scenario_id == scenario_id
    ).all()

    case_ids = [s.case_id for s in sources]
    cases = db.query(ApiTestCase).filter(ApiTestCase.id.in_(case_ids)).all() if case_ids else []

    return {
        "items": [
            {
                "id": c.id, "name": c.name, "method": c.method, "path": c.path,
                "priority": c.priority, "case_type": c.case_type,
            }
            for c in cases
        ],
        "total": len(cases),
    }


@router.post("/scenarios/{scenario_id}/generate-script")
def generate_performance_script(
    scenario_id: int,
    script_type: str = Query("locust", pattern="^(jmeter|locust)$", description="脚本类型"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_CREATE)
):
    """根据场景关联的API用例生成压测脚本（JMX或locustfile）"""
    from app.core.models.performance import PerformanceTestSource
    from app.core.models.api_test import ApiTestCase
    from app.core.services.performance_script_generator import (
        generate_jmx_from_api_cases, generate_locustfile_from_api_cases
    )

    scenario = db.query(PerformanceScenario).filter(PerformanceScenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")

    sources = db.query(PerformanceTestSource).filter(
        PerformanceTestSource.scenario_id == scenario_id
    ).all()

    if not sources:
        raise HTTPException(status_code=400, detail="场景未关联任何API用例，请先关联")

    case_ids = [s.case_id for s in sources]
    cases = db.query(ApiTestCase).filter(ApiTestCase.id.in_(case_ids)).all()

    if script_type == "jmeter":
        script_content = generate_jmx_from_api_cases(cases, scenario)
        filename = f"jmeter_scenario_{scenario_id}.jmx"
    else:
        script_content = generate_locustfile_from_api_cases(cases, None, scenario)
        filename = f"locustfile_scenario_{scenario_id}.py"

    return {
        "scenario_id": scenario_id,
        "script_type": script_type,
        "filename": filename,
        "content": script_content,
        "case_count": len(cases),
    }


@router.get("/options")
def get_options():
    """获取选项配置"""
    return {
        "scenario_status": SCENARIO_STATUS_OPTIONS,
        "script_status": SCRIPT_STATUS_OPTIONS
    }