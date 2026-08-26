"""
知识图谱API端点
提供：生成触发、进度查询、详情查看、列表查询等功能
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.logger import logger
from app.core.models.knowledge_graph import KnowledgeGraph, ExplorationPageSnapshot
from app.core.schemas.knowledge_graph import (
    KnowledgeGraphGenerateRequest,
    KnowledgeGraphResponse,
    KnowledgeGraphDetailResponse,
    KnowledgeGraphProgressResponse,
    KnowledgeGraphStatsResponse
)
from app.core.services.knowledge_graph_service import KnowledgeGraphService

router = APIRouter()


@router.post("/generate", response_model=dict)
async def generate_knowledge_graph(
    request: KnowledgeGraphGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    触发知识图谱生成（异步后台执行）
    
    Args:
        request: 生成请求参数
        background_tasks: 后台任务
        db: 数据库会话
    
    Returns:
        触发结果（包含graph_id）
    """
    logger.info(f"[API] 触发知识图谱生成：项目{request.project_id}，版本{request.version_id or '无'}，模式={request.mode}")

    try:
        service = KnowledgeGraphService(db)

        # 基于已有探索结果合成（默认）：不启动浏览器、不登录、不爬取，
        # 从 KG 行 JSON 列 + 逐页快照整理合成，秒级完成
        if request.mode == 'existing':
            result = await service.generate_from_existing(
                request.project_id,
                request.version_id,
            )
            if result['success']:
                return {
                    "success": True,
                    "message": "知识图谱已基于已有探索结果生成",
                    "data": result,
                }
            return {
                "success": False,
                "message": result['error'],
                "data": {
                    "graph_id": result.get('graph_id'),
                    "needs_exploration": result.get('needs_exploration', False),
                },
            }

        # crawl 模式（全站深度爬取）：登录 + BFS 探索，需 URL/账号密码
        if not request.base_url or not request.login_username:
            raise HTTPException(
                status_code=400,
                detail="全站爬取模式需要项目基础URL和登录用户名",
            )

        # 1. 获取或重置项目唯一 KG 行（幂等：进行中返回进度，已完成/失败/超时重置同 id 重跑）
        graph, started = service.get_or_reset_graph(
            request.project_id,
            request.version_id,
            request.base_url,
            request.login_username,
            request.exploration_strategy or 'normal',
        )

        # 幂等命中：探索仍在进行中，直接返回当前进度（前端转进度弹窗）
        if not started:
            return {
                "success": True,
                "message": "知识图谱正在生成中",
                "data": {
                    "graph_id": graph.id,
                    "exploration_strategy": graph.exploration_strategy,
                    "base_url": graph.base_url,
                    "status": graph.exploration_status,
                    "progress_percentage": graph.progress_percentage,
                }
            }

        logger.info(f"[API] 知识图谱记录就绪，ID={graph.id}")

        # 2. 添加后台任务（异步执行）
        background_tasks.add_task(
            service.execute_graph_generation,
            graph.id,
            request.version_id,
            request.project_id,
            request.base_url,
            request.login_username,
            request.login_password,
            request.exploration_strategy,
            request.skip_tenant
        )

        # 3. 立即返回graph_id
        return {
            "success": True,
            "message": "知识图谱生成任务已启动",
            "data": {
                "graph_id": graph.id,
                "exploration_strategy": request.exploration_strategy,
                "base_url": request.base_url,
                "status": "pending"
            }
        }

    except Exception as e:
        logger.error(f"[API] 触发失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-sync", response_model=dict)
async def generate_knowledge_graph_sync(
    request: KnowledgeGraphGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    触发知识图谱生成（同步执行，用于测试）
    
    注意：此接口会阻塞直到完成，建议使用异步接口
    """
    logger.info(f"[API] 同步触发知识图谱生成")
    
    try:
        service = KnowledgeGraphService(db)
        
        # 同步执行（会阻塞）
        result = await service.generate_knowledge_graph(
            request.version_id,
            request.project_id,
            request.base_url,
            request.login_username,
            request.login_password,
            request.exploration_strategy,
            request.skip_tenant
        )
        
        return {
            "success": True,
            "message": "知识图谱生成完成",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"[API] 同步生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{graph_id}", response_model=KnowledgeGraphProgressResponse)
def get_knowledge_graph_progress(
    graph_id: int,
    db: Session = Depends(get_db)
):
    """
    查询知识图谱生成进度
    
    Args:
        graph_id: 知识图谱ID
        db: 数据库会话
    
    Returns:
        进度信息
    """
    graph = db.query(KnowledgeGraph).filter(KnowledgeGraph.id == graph_id).first()
    
    if not graph:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    
    return KnowledgeGraphProgressResponse(
        graph_id=graph.id,
        exploration_status=graph.exploration_status,
        progress_percentage=graph.progress_percentage,
        current_page=graph.current_page,
        error_message=graph.error_message,
        page_count=graph.page_count,
        menu_count=graph.menu_count,
        element_count=graph.element_count
    )


@router.get("/{graph_id}", response_model=KnowledgeGraphDetailResponse)
def get_knowledge_graph_detail(
    graph_id: int,
    db: Session = Depends(get_db)
):
    """
    获取知识图谱详情（包含所有数据）
    
    Args:
        graph_id: 知识图谱ID
        db: 数据库会话
    
    Returns:
        知识图谱详细数据
    """
    graph = db.query(KnowledgeGraph).filter(KnowledgeGraph.id == graph_id).first()
    
    if not graph:
        raise HTTPException(status_code=404, detail="知识图谱不存在")

    # 向后兼容：如果 KG JSON 列为空，从 ExplorationPageSnapshot 回退合并
    pages = graph.pages or []
    menus = graph.menus or []
    elements = graph.elements or []
    forms = graph.forms or []
    tables = graph.tables or []
    flows = graph.flows or []
    api_calls = graph.api_calls or []
    dependencies = graph.dependencies or []

    # 逐页快照：可视化下钻用（页面 → 元素归属），按访问顺序
    snapshots = []
    _snaps = db.query(ExplorationPageSnapshot).filter(
        ExplorationPageSnapshot.graph_id == graph_id
    ).order_by(ExplorationPageSnapshot.visit_order).all()

    # 回退合并快照数据（旧版 KG 的 JSON 列为空时）
    if not pages and not elements:
        if _snaps:
            seen_pages = set()
            for snap in _snaps:
                if snap.page_url and snap.page_url not in seen_pages:
                    seen_pages.add(snap.page_url)
                    pages.append({
                        'page_url': snap.page_url,
                        'page_name': snap.page_name or '',
                        'page_title': snap.page_title or '',
                    })
                if snap.elements:
                    for el in (snap.elements if isinstance(snap.elements, list) else []):
                        if isinstance(el, dict):
                            elements.append({
                                'element_name': el.get('name', el.get('element_name', '')),
                                'name': el.get('name', ''),
                                'type': el.get('type', el.get('role', '')),
                                'text': el.get('text', ''),
                                'source': 'snapshot_fallback',
                            })

    for snap in _snaps:
        snapshots.append({
            'page_url': snap.page_url,
            'page_name': snap.page_name or '',
            'elements': snap.elements if isinstance(snap.elements, list) else [],
            'visit_order': snap.visit_order,
        })

    return KnowledgeGraphDetailResponse(
        id=graph.id,
        project_id=graph.project_id,
        version_id=graph.version_id,
        graph_name=graph.graph_name,
        base_url=graph.base_url,
        exploration_strategy=graph.exploration_strategy,
        exploration_status=graph.exploration_status,
        progress_percentage=graph.progress_percentage,
        current_page=graph.current_page,
        error_message=graph.error_message,

        pages=pages,
        menus=menus,
        elements=elements,
        forms=forms,
        tables=tables,
        flows=flows,
        api_calls=api_calls,
        dependencies=dependencies,
        dropdowns=graph.dropdowns or {},
        modals=graph.modals or [],
        snapshots=snapshots,

        page_count=graph.page_count,
        menu_count=graph.menu_count,
        element_count=graph.element_count,
        flow_count=graph.flow_count,
        api_count=graph.api_count,
        
        confidence_score=graph.confidence_score,
        locator_validation_rate=graph.locator_validation_rate,
        
        started_at=graph.started_at,
        completed_at=graph.completed_at,
        duration_seconds=graph.duration_seconds,
        created_at=graph.created_at
    )


@router.get("/version/{version_id}", response_model=List[KnowledgeGraphResponse])
def list_knowledge_graphs_by_version(
    version_id: int,
    db: Session = Depends(get_db)
):
    """
    查询版本来源的知识图谱列表（兼容旧接口；知识图谱已是项目级资产，
    项目下至多 1 行，展示用 /project/{project_id}）

    Args:
        version_id: 版本ID
        db: 数据库会话

    Returns:
        知识图谱列表
    """
    graphs = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.version_id == version_id
    ).order_by(KnowledgeGraph.created_at.desc()).all()
    
    return [KnowledgeGraphResponse.from_orm(g) for g in graphs]


@router.get("/project/{project_id}", response_model=List[KnowledgeGraphResponse])
def list_knowledge_graphs_by_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    查询项目的知识图谱列表
    
    Args:
        project_id: 项目ID
        db: 数据库会话
    
    Returns:
        知识图谱列表
    """
    graphs = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.project_id == project_id
    ).order_by(KnowledgeGraph.created_at.desc()).all()
    
    return [KnowledgeGraphResponse.from_orm(g) for g in graphs]


@router.get("/running", response_model=List[KnowledgeGraphProgressResponse])
def get_running_knowledge_graphs(
    db: Session = Depends(get_db)
):
    """
    查询正在运行的知识图谱任务
    
    Returns:
        正在运行的任务列表
    """
    graphs = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'running'
    ).all()
    
    return [
        KnowledgeGraphProgressResponse(
            graph_id=g.id,
            exploration_status=g.exploration_status,
            progress_percentage=g.progress_percentage,
            current_page=g.current_page,
            error_message=g.error_message,
            page_count=g.page_count,
            menu_count=g.menu_count,
            element_count=g.element_count
        )
        for g in graphs
    ]


@router.get("/stats", response_model=KnowledgeGraphStatsResponse)
def get_knowledge_graph_stats(
    db: Session = Depends(get_db)
):
    """
    获取知识图谱统计信息
    
    Returns:
        统计数据
    """
    total_graphs = db.query(KnowledgeGraph).count()
    completed_graphs = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'completed'
    ).count()
    running_graphs = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'running'
    ).count()
    failed_graphs = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'failed'
    ).count()
    
    # 统计总数
    total_pages = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'completed'
    ).with_entities(KnowledgeGraph.page_count).all()
    total_pages_count = sum(p[0] for p in total_pages if p[0])
    
    total_elements = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'completed'
    ).with_entities(KnowledgeGraph.element_count).all()
    total_elements_count = sum(e[0] for e in total_elements if e[0])
    
    total_apis = db.query(KnowledgeGraph).filter(
        KnowledgeGraph.exploration_status == 'completed'
    ).with_entities(KnowledgeGraph.api_count).all()
    total_apis_count = sum(a[0] for a in total_apis if a[0])
    
    return KnowledgeGraphStatsResponse(
        total_graphs=total_graphs,
        completed_graphs=completed_graphs,
        running_graphs=running_graphs,
        failed_graphs=failed_graphs,
        total_pages=total_pages_count,
        total_elements=total_elements_count,
        total_apis=total_apis_count
    )


@router.delete("/{graph_id}")
def delete_knowledge_graph(
    graph_id: int,
    db: Session = Depends(get_db)
):
    """
    删除知识图谱
    
    Args:
        graph_id: 知识图谱ID
        db: 数据库会话
    
    Returns:
        删除结果
    """
    graph = db.query(KnowledgeGraph).filter(KnowledgeGraph.id == graph_id).first()
    
    if not graph:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    
    # 检查是否正在运行
    if graph.exploration_status == 'running':
        raise HTTPException(status_code=400, detail="知识图谱正在生成，无法删除")
    
    db.delete(graph)
    db.commit()
    
    return {"success": True, "message": "知识图谱已删除"}