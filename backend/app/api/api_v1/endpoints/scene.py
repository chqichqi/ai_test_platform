"""
场景编排 API

GET    /scenes/?project_id=&scene_type=     → 场景列表
POST   /scenes/                              → 创建场景
GET    /scenes/{id}                           → 场景详情（含items）
PUT    /scenes/{id}                           → 更新场景
DELETE /scenes/{id}                           → 删除场景
POST   /scenes/{id}/items                     → 添加用例到场景
PUT    /scenes/{id}/items/reorder             → 拖拽重排
PUT    /scenes/{id}/items/{item_id}/toggle    → 启用/禁用单条
DELETE /scenes/{id}/items/{item_id}           → 移除单条
POST   /scenes/{id}/execute                   → 执行场景
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logger import logger
from app.core.models.scene import Scene, SceneItem, SceneType, SceneStatus

router = APIRouter()


# ===== Schema =====

class SceneCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scene_type: str = "ui"
    project_id: int
    version_id: Optional[int] = None
    config: dict = {}


class SceneUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version_id: Optional[int] = None
    config: Optional[dict] = None


class SceneItemAdd(BaseModel):
    case_ids: List[int] = Field(..., description="用例ID列表")
    case_type: str = "ui"


class ReorderRequest(BaseModel):
    item_ids: List[int] = Field(..., description="按新顺序排列的item ID列表")


class ToggleRequest(BaseModel):
    enabled: bool


# ===== CRUD =====

@router.get("/")
def list_scenes(
    project_id: Optional[int] = Query(None),
    scene_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Scene)
    if project_id:
        query = query.filter(Scene.project_id == project_id)
    if scene_type:
        query = query.filter(Scene.scene_type == scene_type)
    scenes = query.order_by(Scene.updated_at.desc()).all()
    return {"items": [s.to_dict() for s in scenes], "total": len(scenes)}


@router.post("/")
def create_scene(data: SceneCreate, db: Session = Depends(get_db)):
    scene = Scene(
        name=data.name,
        description=data.description,
        scene_type=SceneType(data.scene_type),
        project_id=data.project_id,
        version_id=data.version_id,
        config=data.config,
        status=SceneStatus.DRAFT,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene.to_dict()


@router.get("/{scene_id}")
def get_scene(scene_id: int, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    result = scene.to_dict()
    result["items"] = [item.to_dict() for item in (scene.items or [])]
    return result


@router.put("/{scene_id}")
def update_scene(scene_id: int, data: SceneUpdate, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(scene, k, v)
    db.commit()
    return scene.to_dict()


@router.delete("/{scene_id}")
def delete_scene(scene_id: int, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")
    db.delete(scene)
    db.commit()
    return {"success": True}


# ===== Items =====

@router.post("/{scene_id}/items")
def add_items(scene_id: int, data: SceneItemAdd, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    # 获取当前最大 sort_order
    max_order = db.query(SceneItem).filter(
        SceneItem.scene_id == scene_id
    ).count() * 10

    added = []
    for i, raw_id in enumerate(data.case_ids):
        case_id = raw_id
        wui_id = None
        if data.case_type == "ui":
            # 方案B：case_id 存功能用例【逻辑 id】，wui_id 绑定最新非软删 WUI 实例
            from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
            from app.core.services.case_versioning import load_effective_case
            tc = load_effective_case(db, raw_id)
            if tc:
                case_id = tc.logical_case_id or tc.id
                _wui = db.query(WebUITestCaseModel).filter(
                    WebUITestCaseModel.test_case_id == str(case_id),
                    WebUITestCaseModel.deleted_at.is_(None),
                ).order_by(WebUITestCaseModel.created_at.desc()).first()
                wui_id = str(_wui.id) if _wui else None
            else:
                # 兜底：raw_id 是 WUI uuid（历史前端直接传 uuid）→ case_id 存其绑定，wui_id 存自身
                _wui = db.query(WebUITestCaseModel).filter(
                    WebUITestCaseModel.id == str(raw_id)
                ).first()
                if _wui:
                    case_id = _wui.test_case_id
                    wui_id = str(_wui.id)

        # 去重检查
        exists = db.query(SceneItem).filter(
            SceneItem.scene_id == scene_id,
            SceneItem.case_id == case_id,
            SceneItem.case_type == data.case_type,
        ).first()
        if exists:
            continue
        item = SceneItem(
            scene_id=scene_id,
            case_id=case_id,
            case_type=data.case_type,
            sort_order=max_order + (i + 1) * 10,
            wui_id=wui_id,
        )
        db.add(item)
        added.append(item)

    scene.updated_at = datetime.utcnow()
    db.commit()
    return {"added": len(added), "items": [i.to_dict() for i in added]}


@router.put("/{scene_id}/items/reorder")
def reorder_items(scene_id: int, data: ReorderRequest, db: Session = Depends(get_db)):
    """拖拽排序：传按新顺序排列的 item ID 列表"""
    for i, item_id in enumerate(data.item_ids):
        item = db.query(SceneItem).filter(
            SceneItem.id == item_id, SceneItem.scene_id == scene_id
        ).first()
        if item:
            item.sort_order = (i + 1) * 10
    db.query(Scene).filter(Scene.id == scene_id).update({"updated_at": datetime.utcnow()})
    db.commit()
    return {"success": True}


@router.put("/{scene_id}/items/{item_id}/toggle")
def toggle_item(scene_id: int, item_id: int, data: ToggleRequest, db: Session = Depends(get_db)):
    item = db.query(SceneItem).filter(
        SceneItem.id == item_id, SceneItem.scene_id == scene_id
    ).first()
    if not item:
        raise HTTPException(404, "条目不存在")
    item.enabled = data.enabled
    db.commit()
    return item.to_dict()


@router.delete("/{scene_id}/items/{item_id}")
def remove_item(scene_id: int, item_id: int, db: Session = Depends(get_db)):
    item = db.query(SceneItem).filter(
        SceneItem.id == item_id, SceneItem.scene_id == scene_id
    ).first()
    if not item:
        raise HTTPException(404, "条目不存在")
    db.delete(item)
    db.query(Scene).filter(Scene.id == scene_id).update({"updated_at": datetime.utcnow()})
    db.commit()
    return {"success": True}


# ===== 执行 =====

@router.post("/{scene_id}/execute")
async def execute_scene(
    scene_id: int,
    version_id: Optional[int] = Query(None),
    headless: Optional[bool] = Query(None, description="覆盖用例的 headless 设置"),
    browser_mode: Optional[str] = Query(None, description="浏览器模式: isolated | reuse"),
    slow_mo: Optional[int] = Query(None, description="Playwright slow_mo（毫秒）"),
    db: Session = Depends(get_db),
):
    """执行场景：按 sort_order 串行执行已启用的用例。

    支持 V1/V2 混合、浏览器隔离/复用、有头/无头切换。
    所有参数均可通过 Query 参数或 JSON body 传入。
    """
    import time as _time
    from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
    from app.core.services.execution_config import ExecutionConfig, BrowserMode
    from app.core.services.ui_test_executor import UITestExecutor
    from app.core.services.allure_reporter import AllureReporter, ReportManager

    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(404, "场景不存在")

    items = [i for i in (scene.items or []) if i.enabled]
    items.sort(key=lambda x: x.sort_order)

    # ── 构建执行配置 ──
    config = ExecutionConfig(
        headless=headless if headless is not None else True,
        browser_mode=BrowserMode(browser_mode) if browser_mode else BrowserMode.ISOLATED,
        slow_mo=slow_mo or 0,
    )

    # ── 创建 Allure 报告目录（每次运行不覆盖） ──
    import re
    project_key = re.sub(r'[^a-zA-Z0-9_-]', '_', scene.name or 'unknown')[:30]
    version_key = str(version_id or 'latest')
    run_dir = ReportManager.create_run_dir(project_key, version_key)
    allure = AllureReporter(
        results_dir=str(run_dir / "allure-results"),
        project_name=scene.name or "未命名场景",
        version_name=version_key,
        environment={
            "OS": "Windows", "Python": "3.9",
            "Browser": config.browser_type,
            "Headless": str(config.headless),
            "BrowserMode": config.browser_mode.value,
        },
    )

    scene.status = SceneStatus.RUNNING
    db.commit()
    logger.info(f"[场景] 执行 '{scene.name}': {len(items)} 条, "
                f"headless={config.headless}, mode={config.browser_mode.value}, "
                f"report={run_dir}")

    results = []
    total_start = _time.time()

    # ── 收集 UI 用例，批量交给 UITestExecutor ──
    ui_cases: list = []
    ui_item_map: dict = {}  # case_id → item

    for item in items:
        if item.case_type == "ui":
            # 方案B 重解析：条目绑定 WUI 实例，派生后旧 WUI 软删 → 自动解析最新非软删版本
            # 1) wui_id 直达（未软删 → 直接执行）
            wui = None
            re_resolved = False
            if getattr(item, 'wui_id', None):
                wui = db.query(WebUITestCaseModel).filter(
                    WebUITestCaseModel.id == str(item.wui_id),
                    WebUITestCaseModel.deleted_at.is_(None),
                ).first()
            if wui:
                re_resolved = False
            else:
                # 2) 按逻辑 id 查最新非软删 WUI（方案B 新条目 case_id=功能用例逻辑 id）
                wui = db.query(WebUITestCaseModel).filter(
                    WebUITestCaseModel.test_case_id == str(item.case_id),
                    WebUITestCaseModel.deleted_at.is_(None),
                ).order_by(WebUITestCaseModel.created_at.desc()).first()
                if wui:
                    re_resolved = bool(getattr(item, 'wui_id', None))
                else:
                    # 3) case_id=WUI uuid（历史条目）→ 原 WUI 软删则按逻辑 id 找新版
                    legacy = db.query(WebUITestCaseModel).filter(
                        WebUITestCaseModel.id == str(item.case_id)
                    ).first()
                    if legacy and legacy.deleted_at is None:
                        wui = legacy
                        re_resolved = False
                    elif legacy:
                        new_wui = db.query(WebUITestCaseModel).filter(
                            WebUITestCaseModel.test_case_id == str(legacy.test_case_id),
                            WebUITestCaseModel.deleted_at.is_(None),
                        ).order_by(WebUITestCaseModel.created_at.desc()).first()
                        if new_wui:
                            wui = new_wui
                            re_resolved = True
                    else:
                        # 4) case_id=功能用例物理 id（历史）→ 生效行 → 逻辑 id → 最新 WUI
                        from app.core.services.case_versioning import load_effective_case
                        _tc = load_effective_case(db, item.case_id)
                        if _tc:
                            new_wui = db.query(WebUITestCaseModel).filter(
                                WebUITestCaseModel.test_case_id == str(_tc.logical_case_id or _tc.id),
                                WebUITestCaseModel.deleted_at.is_(None),
                            ).order_by(WebUITestCaseModel.created_at.desc()).first()
                            if new_wui:
                                wui = new_wui
                                re_resolved = True
            if wui:
                if re_resolved and getattr(item, 'wui_id', None) != str(wui.id):
                    item.wui_id = str(wui.id)  # 回写最新 WUI 绑定
                ui_cases.append(wui)
                ui_item_map[str(wui.id)] = {"item": item, "re_resolved": re_resolved}
                if re_resolved:
                    logger.info(f"[场景] 条目{item.id}重解析: 旧 WUI 已更新，自动执行最新版本 {wui.id}")
            else:
                results.append({
                    "item_id": item.id, "case_id": item.case_id,
                    "case_type": "ui", "sort_order": item.sort_order,
                    "status": "error",
                    "error": f"用例不存在或其 UI 用例已被移除，请先重新转化后再执行: {item.case_id}",
                })

    # ── 批量执行 UI 用例 ──
    if ui_cases:
        executor = UITestExecutor(config, allure=allure)
        exec_results = await executor.execute_batch(
            ui_cases,
            progress_callback=lambda stage, msg, idx, total: logger.info(
                f"[场景] {stage}: {msg}"
            ),
        )

        for i, exec_result in enumerate(exec_results):
            tc_id = exec_result.get("test_case_id", "")
            _entry = ui_item_map.get(tc_id)
            item = _entry["item"] if _entry else None
            results.append({
                "item_id": getattr(item, 'id', None) if item else None,
                "case_id": getattr(item, 'case_id', tc_id) if item else tc_id,
                "case_type": "ui",
                "sort_order": getattr(item, 'sort_order', i) if item else i,
                "status": exec_result.get("status", "error"),
                "generation_mode": exec_result.get("generation_mode"),
                "browser_mode": exec_result.get("browser_mode"),
                "duration_ms": exec_result.get("duration_ms", 0),
                "error": exec_result.get("error"),
                "steps_executed": exec_result.get("steps_executed", 0),
                "re_resolved": _entry["re_resolved"] if _entry else False,
            })

    # ── 非 UI 用例（API / 性能测试）标记跳过 ──
    for item in items:
        if item.case_type != "ui":
            results.append({
                "item_id": item.id, "case_id": item.case_id,
                "case_type": item.case_type, "sort_order": item.sort_order,
                "status": "skipped", "error": f"{item.case_type} 执行器待接入",
            })

    # 按 sort_order 排序结果
    results.sort(key=lambda r: r.get("sort_order", 0))

    # ── 汇总 ──
    total_ms = int((_time.time() - total_start) * 1000)
    passed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
    skipped = sum(1 for r in results if r.get("status") in ("skipped", "pending"))

    # ── Allure: 完成报告 ──
    allure.finalize()
    ReportManager.write_summary(run_dir, {
        "total": len(results), "passed": passed, "failed": failed,
        "skipped": skipped, "duration_ms": total_ms,
        "generated_at": datetime.utcnow().isoformat(),
        "config": config.to_dict(),
    })
    # 尝试生成 HTML 报告
    AllureReporter.generate_html(
        str(run_dir / "allure-results"),
        str(run_dir / "allure-report"),
    )

    scene.status = SceneStatus.COMPLETED
    db.commit()

    logger.info(f"[场景] 完成 '{scene.name}': {len(results)} 条, "
                f"通过={passed}, 失败={failed}, 跳过={skipped}, {total_ms}ms")

    return {
        "scene_id": scene_id,
        "status": "completed",
        "config": {
            "headless": config.headless,
            "browser_mode": config.browser_mode.value,
            "slow_mo": config.slow_mo,
        },
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_ms": total_ms,
        "results": results,
    }
