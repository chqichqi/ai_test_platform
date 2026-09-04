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
from app.core.auth import get_current_active_user
from app.core.models.user import User
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
    items_out = []
    for item in (scene.items or []):
        d = item.to_dict()
        # 注入每条用例展示名与模块（第3项）：UI 条目经 wui_id/case_id 解析，避免只见 id
        if item.case_type == "ui":
            nm, mod = _resolve_ui_case_meta(db, item)
            d["case_name"] = nm
            d["case_module"] = mod
        else:
            d["case_name"] = d.get("case_name", "")
            d["case_module"] = d.get("case_module", "")
        items_out.append(d)
    result["items"] = items_out
    return result


def _resolve_ui_case_meta(db: Session, item):
    """解析场景里 UI 条目的展示名与模块（第3项）。

    优先按绑定的 WUI 实例(wui_id)取 test_data 的 title/module；回退按逻辑 id(case_id)
    找最新 WUI。拿不到返回空串，由前端回退显示功能用例名/id。
    返回 (name, module)。
    """
    from app.core.models.web_ui_test import WebUITestCase as _W
    wui = None
    if getattr(item, "wui_id", None):
        wui = db.query(_W).filter(_W.id == str(item.wui_id)).first()
    if wui is None and getattr(item, "case_id", None):
        wui = (db.query(_W)
               .filter(_W.test_case_id == str(item.case_id), _W.deleted_at.is_(None))
               .order_by(_W.created_at.desc()).first())
    if wui is None:
        return "", ""
    td = wui.test_data if isinstance(wui.test_data, dict) else {}
    name = str(td.get("title") or td.get("name") or "")
    module = str(td.get("module") or getattr(wui, "module", "") or "")
    return name, module


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
    current_user: User = Depends(get_current_active_user),
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
    # project_key 用真实项目名（可读，中文保留；只去掉 Windows 路径非法字符），
    # 避免用场景名导致中文全部被替换成 __ 乱码（报告列表项目列正确展示）
    _proj_name = scene.name or "unknown"
    if getattr(scene, "project_id", None):
        try:
            from app.core.models.project import Project
            _p = db.query(Project).filter(Project.id == scene.project_id).first()
            if _p and getattr(_p, "name", None):
                _proj_name = _p.name
        except Exception:
            pass
    project_key = re.sub(r'[\\/:*?"<>|]', '_', str(_proj_name))[:80]
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

    # ── API 场景条目：调用 API 执行链路（拓扑 + 运行时鉴权 + httpx 单条执行）──
    # 收集场景中已启用的 API 用例条目（item.case_id = ApiTestCase.id）
    api_results = await _execute_api_items(db, items, current_user)
    results.extend(api_results)

    # ── 其它类型（performance 等）尚未接入执行器，标记跳过 ──
    for item in items:
        if item.case_type not in ("ui", "api"):
            results.append({
                "item_id": item.id, "case_id": item.case_id,
                "case_type": item.case_type, "sort_order": item.sort_order,
                "status": "skipped", "error": f"{item.case_type} 执行器待接入",
            })

    # 按 sort_order 排序结果
    results.sort(key=lambda r: r.get("sort_order", 0))

    # ── 汇总（兼容 UI 的 completed / API 的 passed）──
    total_ms = int((_time.time() - total_start) * 1000)
    passed = sum(1 for r in results if r.get("status") in ("completed", "passed"))
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


async def _execute_api_items(db: Session, items: List[SceneItem], current_user) -> List[dict]:
    """执行场景中的 API 用例条目。

    复用 api_tests 的同一套执行链路（拓扑排序 + 项目环境/项目级鉴权 + httpx 单条执行
    + 变量缓存），与 API 测试独立入口同源同行为。item.case_id = ApiTestCase.id。
    返回与场景 results 结构一致（含 sort_order 供排序）。
    """
    from app.core.models.api_test import ApiTestCase, ApiEnvironment
    from app.api.api_v1.endpoints.api_tests import (
        _topological_sort_cases, _execute_env_auth, _execute_single_case_with_cache)

    api_items = [i for i in (items or []) if i.case_type == "api"]
    if not api_items:
        return []

    # 解析场景条目 → ApiTestCase
    sel_cases = []
    for it in api_items:
        c = db.query(ApiTestCase).filter(ApiTestCase.id == it.case_id).first()
        if c:
            sel_cases.append(c)
    if not sel_cases:
        return [{
            "item_id": it.id, "case_id": it.case_id, "case_type": "api",
            "sort_order": it.sort_order, "status": "error",
            "error": f"API 用例不存在或已删除: {it.case_id}",
        } for it in api_items]

    project_ids = {c.project_id for c in sel_cases if c.project_id}

    # 拓扑排序（与 API 批量执行一致：自动把 depends_on 的前置如登录也纳入执行）
    all_cases = (db.query(ApiTestCase)
                 .filter(ApiTestCase.project_id.in_(project_ids)).all()) if project_ids else []
    all_map = {c.id: c for c in all_cases}
    sorted_cases, selected_ids = _topological_sort_cases(sel_cases, all_map)

    # 环境/鉴权（env 为 None 时 _execute_env_auth 回退项目级 api_auth）
    env = None
    if project_ids:
        env = db.query(ApiEnvironment).filter(
            ApiEnvironment.project_id.in_(project_ids),
            ApiEnvironment.is_default.is_(True),
        ).first()
    env_auth = await _execute_env_auth(
        env, env.base_url if env else None, db=db,
        project_id=sorted(project_ids)[0] if project_ids else None,
    )

    execution_cache: dict = {}
    out = []
    item_by_case = {it.case_id: it for it in api_items}
    for c in sorted_cases:
        is_sel = c.id in selected_ids
        base_url = (c.base_url or (env.base_url if env else None) or "http://localhost:8000")
        try:
            r = await _execute_single_case_with_cache(
                test_case=c, base_url=base_url, db=db, current_user=current_user,
                credentials=None, execution_cache=execution_cache,
                is_selected=is_sel, env_auth_vars=env_auth,
            )
        except Exception as e:
            logger.warning(f"[场景-API] 执行异常 {c.id}: {e}")
            r = {"status": "error", "message": str(e), "error_message": str(e)}

        st = r.get("status", "error")
        if r.get("skipped"):
            st = "skipped"
        it = item_by_case.get(c.id)
        out.append({
            "item_id": it.id if it else None,
            "case_id": c.id,
            "case_type": "api",
            "sort_order": it.sort_order if it else 0,
            "status": st,
            "name": c.name,
            "duration_ms": (r.get("duration") or 0) * 1000 if r.get("duration") else 0,
            "error": r.get("error_message") or r.get("message") or "",
            "message": r.get("message", ""),
            "actual_status": r.get("actual_status"),
            "method": c.method,
            "request_url": r.get("request_url"),
        })
    return out
