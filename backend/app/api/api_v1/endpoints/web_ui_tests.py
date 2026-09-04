"""
WEB UI自动化测试API端点
支持将功能测试用例转换为WEB UI自动化测试用例，并执行WEB UI测试
"""

import json
import re
import threading
import asyncio
import queue
from datetime import datetime
from typing import List, Optional, Any, Dict
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Body, Query, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.core.models.user import User
from app.services.web_ui_test_service import WebUITestService
from app.core.schemas.web_ui_test import (
    FunctionalToWebUITestConversion, WebUITestGenerationResult,
    WebUITestCaseCreate, WebUITestCaseUpdate, WebUITestCaseResponse,
    WebUITestExecutionRequest, WebUITestExecutionResult
)
from app.core.schemas.test import TestCaseFilter
from app.core.services.llm_service import LLMService, RAGRetrievalService
from app.core.logger import logger

router = APIRouter()

# 功能用例可转化为 UI 用例的状态集：审核通过（approved）/ 激活（active）
# ——与「可转化用例列表」查询条件同源（web_ui_tests.py 列表端点 approved/active 过滤）
_CONVERTIBLE_STATUSES = ("approved", "active")


def _ensure_case_convertible(db: Session, test_case_id: str):
    """功能用例 → UI 用例前提：审核通过（方案B：按【生效行】校验）。

    草稿/待评审/已驳回/已废弃/已归档(archived)等一律拒绝（400 提示先审核），不静默跳过。
    两种模型兼容：需求用例（RequirementTestCase，int id，物理/逻辑 id 均解析生效行）
    / 简单用例（SimpleTestCase，str id）。
    返回生效行（调用方经 logical_case_id 取绑定逻辑 id）。
    """
    from app.core.models.test_simple import SimpleTestCase
    from app.core.services.case_versioning import load_effective_case
    try:
        int(test_case_id)
    except (ValueError, TypeError):
        tc = db.query(SimpleTestCase).filter(SimpleTestCase.id == str(test_case_id)).first()
    else:
        tc = load_effective_case(db, test_case_id)
    if not tc:
        raise HTTPException(status_code=404, detail=f"功能用例不存在: {test_case_id}")
    _s = (getattr(tc, 'status', '') or '').strip()
    if _s not in _CONVERTIBLE_STATUSES:
        _name = getattr(tc, 'name', '') or getattr(tc, 'title', '') or str(test_case_id)
        raise HTTPException(
            status_code=400,
            detail=f"功能用例「{_name}」未审核通过（当前状态: {_s}），请先审核通过后再转化为UI用例",
        )
    return tc


def _load_case_meta(db: Session, test_case_id: str) -> Dict:
    """加载功能用例元信息（name/status），批量转化跳过名单展示用。"""
    from app.core.models.requirement import TestCase as ReqTestCase
    from app.core.models.test_simple import SimpleTestCase
    try:
        tc = db.query(ReqTestCase).filter(ReqTestCase.id == int(test_case_id)).first()
    except (ValueError, TypeError):
        tc = db.query(SimpleTestCase).filter(SimpleTestCase.id == str(test_case_id)).first()
    if not tc:
        return {"name": str(test_case_id), "status": ""}
    return {
        "name": getattr(tc, 'name', '') or getattr(tc, 'title', '') or str(test_case_id),
        "status": (getattr(tc, 'status', '') or '').strip(),
        "module": (getattr(tc, 'module', '') or '').strip(),
    }


def _require_login_module(db: Session, project_id: int = None) -> None:
    """检查登录模块是否已配置（项目级）；未配置则拒绝"""
    from app.core.services.login_module_store import has_login_module_configured
    if not has_login_module_configured(db, project_id):
        raise HTTPException(
            status_code=400,
            detail="请先在项目卡片「登录模块」中导入并验证登录流程后再进行操作"
        )


@router.get("/check-login-module")
def check_login_module(
    db: Session = Depends(get_db),
    project_id: int = Query(None, description="项目ID（按项目校验）"),
):
    """前端检查项目前置配置状态（项目级，与 _require_login_module/创建版本门控同一判定源）。

    返回 has_login_module（登录模块已导入验证）与 has_web_config（项目配置已填目标系统 URL）
    两项——创建版本门控要求两项均满足，前端卡片状态/「添加版本」引导按缺项提示。
    """
    from app.core.services.login_module_store import (
        has_login_module_configured,
        has_project_web_configured,
    )
    return {
        "has_login_module": has_login_module_configured(db, project_id),
        "has_web_config": has_project_web_configured(db, project_id),
    }


# ========== 请求/响应模型 ==========

class FunctionalTestConversionRequest(FunctionalToWebUITestConversion):
    """功能测试转换请求"""
    force_explore: bool = Field(default=False, description="是否强制重新探索（忽略缓存）")


class WebUITestCaseListResponse(BaseModel):
    """WEB UI测试用例列表响应"""
    items: List[WebUITestCaseResponse]
    total: int
    page: int
    size: int


class WebUITestCaseFilter(BaseModel):
    """WEB UI测试用例过滤器"""
    project_id: Optional[UUID] = None
    browser: Optional[str] = None
    script_type: Optional[str] = None
    search: Optional[str] = None


class ChatGenerateWebUITestRequest(BaseModel):
    """聊天生成WEB UI测试用例请求"""
    message: str = Field(..., description="聊天消息或需求文档内容")
    project_name: Optional[str] = Field(None, description="项目名称")
    base_url: Optional[str] = Field("", description="基础URL")
    browser: Optional[str] = Field("chromium", description="浏览器类型")
    viewport_size: Optional[str] = Field("1920x1080", description="视口尺寸")
    headless: Optional[bool] = Field(True, description="是否无头模式")
    generate_element_selectors: Optional[bool] = Field(True, description="是否生成元素选择器")
    generate_test_script: Optional[bool] = Field(True, description="是否生成测试脚本")
    script_type: Optional[str] = Field("playwright", description="脚本类型")
    script_language: Optional[str] = Field("python", description="脚本语言")
    knowledge_base_id: Optional[int] = Field(None, description="知识库ID（用于RAG增强）")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool = Field(..., description="是否成功")
    message_type: str = Field(..., description="消息类型: chat/generate_test")
    content: str = Field(..., description="回复内容")
    test_cases: Optional[List[dict]] = Field(None, description="生成的测试用例（仅当type=generate_test时）")
    saved_to_db: Optional[bool] = Field(None, description="是否已保存到数据库")
    sources: Optional[List[dict]] = Field(None, description="RAG检索来源")


TEST_GENERATION_KEYWORDS = [
    "生成测试用例", "生成测试", "创建测试用例", "生成用例",
    "编写测试", "写测试", "添加测试用例", "生成功能测试",
    "生成API测试", "生成WEB测试", "生成UI测试",
    "帮我生成测试", "请生成测试", "转换为测试用例",
    "根据这个生成测试", "基于这个生成测试"
]


def is_test_generation_request(message: str) -> bool:
    """判断是否是测试用例生成请求"""
    message_lower = message.lower()
    for keyword in TEST_GENERATION_KEYWORDS:
        if keyword in message:
            return True
    return False


# ========== 批量转化模型 ==========

class BatchConversionRequest(BaseModel):
    """批量转化功能用例为UI用例请求"""
    test_case_ids: List[str] = Field(..., description="功能测试用例ID列表")
    base_url: Optional[str] = Field("", description="基础URL")
    browser: Optional[str] = Field("chromium", description="浏览器类型")
    viewport_size: Optional[str] = Field("1920x1080", description="视口尺寸")
    headless: Optional[bool] = Field(True, description="是否无头模式")
    script_type: Optional[str] = Field("playwright", description="脚本类型")
    script_language: Optional[str] = Field("python", description="脚本语言")
    generate_element_selectors: Optional[bool] = Field(True, description="是否生成元素选择器")
    generate_test_script: Optional[bool] = Field(True, description="是否生成测试脚本")
    force_explore: Optional[bool] = Field(False, description="是否强制重新探索（忽略缓存），用于版本迭代变更场景")


class BatchConversionResult(BaseModel):
    """批量转化结果"""
    success: bool = Field(..., description="整体是否成功（至少一条成功即为true）")
    results: List[dict] = Field(default_factory=list, description="各用例转化结果")
    success_count: int = Field(0, description="成功数量")
    total_count: int = Field(0, description="总数量")
    explored_modules: List[str] = Field(default_factory=list, description="本次探索的模块")
    cached_modules: List[str] = Field(default_factory=list, description="使用缓存的模块")
    exploration_method: str = Field("", description="探索方式: cached/step_driven/bfs")
    summary: dict = Field(default_factory=dict, description="状态统计: {success, steps_missing, conversion_failed, exploration_insufficient, exploration_failed}")
    exploration_failures: dict = Field(default_factory=dict, description="探索失败的模块及原因")
    skipped_cases: List[Dict[str, Any]] = Field(default_factory=list, description="批量转化跳过的用例（id/name/status/reason：未审核通过|已转化为UI用例）")


# ========== 转换功能测试为WEB UI测试 ==========

@router.post("/convert-from-functional", response_model=WebUITestGenerationResult)
async def convert_functional_to_web_ui(
    conversion_request: FunctionalTestConversionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    将功能测试用例转换为WEB UI测试用例（AI驱动 + 知识图谱增强）

    新逻辑（先探索、再转化）：
    1. 如果 KnowledgeGraph 已存在 → 直接 V2 转化
    2. 如果 KnowledgeGraph 不存在 → 触发 BFS 探索 → 等待完成 → V2 转化
    3. 如果 V2 失败 → 回退 V1 AI 转化
    4. 如果探索本身失败 → 回退规则引擎（最终兜底）
    """
    try:
        from app.core.models.knowledge_graph import KnowledgeGraph

        test_case_id = str(conversion_request.functional_test_case_id)
        browser = conversion_request.browser.value if hasattr(conversion_request.browser, 'value') else str(conversion_request.browser)
        viewport = conversion_request.viewport_size.value if hasattr(conversion_request.viewport_size, 'value') else str(conversion_request.viewport_size)
        base_url = conversion_request.base_url or ""

        # 守卫：功能用例转 UI 用例的前提是审核通过（approved/active，按生效行校验）
        _guard_tc = _ensure_case_convertible(db, test_case_id)
        # 登录模块用例随业务流导入时已转化（__login__），不允许重复转化
        if (getattr(_guard_tc, 'module', '') or '') == '登录模块':
            raise HTTPException(status_code=400,
                                detail="登录模块已随业务流导入转化，无需重复转化")
        # 方案B：WUI 绑定逻辑 id——后续链路统一传逻辑 id（内容查询/绑定均幂等兼容物理 id；
        # SimpleTestCase 无 logical_case_id 属性，getattr 兜底原样返回 str id）
        test_case_id = str(getattr(_guard_tc, 'logical_case_id', None) or _guard_tc.id)
        # 尝试获取关联的项目ID 和 version_id
        project_id = getattr(conversion_request, 'project_id', None)
        version_id = None
        if not project_id:
            project_id = getattr(_guard_tc, 'project_id', None)
            version_id = getattr(_guard_tc, 'version_id', None)

        _require_login_module(db, project_id)
        from app.core.agents.web_ui_conversion_v2 import convert_functional_to_web_ui_v2
        from app.core.agents.web_ui_conversion_agent import convert_functional_to_web_ui_ai

        # 检查知识图谱是否可用（按项目和版本过滤）
        kg_available = False
        if project_id:
            # 知识图谱是项目级资产（UNIQUE(project_id)），不再按 version_id 过滤
            kg = db.query(KnowledgeGraph).filter(
                KnowledgeGraph.project_id == project_id,
                KnowledgeGraph.exploration_status == "completed"
            ).first()
            kg_available = kg is not None

        force_explore = getattr(conversion_request, 'force_explore', False)

        if kg_available and not force_explore:
            # === KG 可用且非强制探索 → 直接 V2 转化 ===
            logger.info(f"[convert-from-functional] KG 可用，V2 转化: test_case_id={test_case_id}")
            # 探索校正：KG 已有 `__step_diagnostics__`（最近一次探索的真实页面文本），
            # 以探索结果为准回写用例步骤（落库）再转化——用户定性 2026-08-23：
            # 探索结果与用例文本有出入时以探索为准，先把用例改正再转 UI 用例。
            try:
                from app.core.services.functional_to_ui_service import FunctionalToUIService as _FTUI
                _kg_diags = [
                    _d for _flow in (kg.flows or [])
                    if isinstance(_flow, dict) and _flow.get("flow_name") == "__step_diagnostics__"
                    for _d in (_flow.get("steps") or [])
                ]
                _diags = _FTUI._check_case_steps(_guard_tc, {"step_diagnostics": _kg_diags})
                _n_corrected = _FTUI._correct_case_steps(db, _guard_tc, _diags)
                if _n_corrected:
                    logger.info(f"[convert-from-functional] 探索校正 {_n_corrected} 步: "
                                f"test_case_id={test_case_id}")
            except Exception as _ce:
                logger.warning(f"[convert-from-functional] 探索校正异常（不影响转化）: {_ce}")
            result = convert_functional_to_web_ui_v2(
                db=db,
                test_case_id=test_case_id,
                base_url=base_url,
                browser=browser,
                viewport_size=viewport,
                headless=conversion_request.headless,
                script_type=conversion_request.script_type or "playwright",
                script_language=conversion_request.script_language or "python",
                project_id=project_id,
            )
            if result.get("success"):
                return result
            # V2 失败 → 回退 V1
            logger.warning(f"[convert-from-functional] V2 失败，回退 V1: {result.get('error')}")
            v1_result = convert_functional_to_web_ui_ai(
                db=db,
                test_case_id=test_case_id,
                base_url=base_url,
                browser=browser,
                viewport_size=viewport,
                headless=conversion_request.headless,
                script_type=conversion_request.script_type or "playwright",
                script_language=conversion_request.script_language or "python",
                project_id=project_id,
            )
            if v1_result.get("success"):
                return v1_result
            # V1 也失败 → 规则引擎兜底
            logger.warning(f"[convert-from-functional] V1 也失败，回退规则引擎: {v1_result.get('error')}")
            service = WebUITestService(db)
            return service.convert_functional_to_web_ui(
                conversion_data=conversion_request,
                current_user=current_user
            )

        else:
            # === KG 不可用 → 先探索、再转化 ===
            logger.info(f"[convert-from-functional] KG 不可用，触发探索优先转化: test_case_id={test_case_id}")
            from app.core.services.functional_to_ui_service import convert_with_exploration_fallback

            batch_result = await convert_with_exploration_fallback(
                db=db,
                test_case_ids=[test_case_id],
                base_url=base_url,
                browser=browser,
                viewport_size=viewport,
                headless=conversion_request.headless,
                script_type=conversion_request.script_type or "playwright",
                script_language=conversion_request.script_language or "python",
                project_id=project_id,
                force_explore=force_explore,
            )

            if batch_result.get("success") and batch_result.get("results"):
                first_result = batch_result["results"][0]
                if first_result.get("status") in ("success", "steps_missing"):
                    script = first_result.get("script", "")
                    # V2 返回 dict 格式的 test_spec，需序列化为 JSON 字符串
                    if isinstance(script, dict):
                        import json as _json
                        script = _json.dumps(script, ensure_ascii=False)
                    # 构建警告列表（步骤未定位等）
                    warnings = []
                    diag = first_result.get("diagnostics")
                    if diag and diag.get("warning"):
                        warnings.append(diag["warning"])
                    if first_result.get("status") == "steps_missing":
                        warnings.append(f"部分步骤未定位，已用可用数据生成。请检查用例描述是否与当前页面匹配。")
                    return {
                        "success": True,
                        "test_case_id": test_case_id,
                        "case_name": first_result.get("case_name", ""),
                        "test_script": script,
                        "script_type": conversion_request.script_type or "playwright",
                        "script_language": conversion_request.script_language or "python",
                        "metadata": {
                            "explored_modules": batch_result.get("explored_modules", []),
                            "cached_modules": batch_result.get("cached_modules", []),
                            "exploration_method": batch_result.get("exploration_method", "bfs"),
                            "diagnostics": first_result.get("diagnostics"),
                        },
                        "warnings": warnings if warnings else None,
                    }
                else:
                    # 转化失败但有探索数据时，提供诊断信息帮助用户排查
                    status = first_result.get("status", "unknown")
                    error_msg = first_result.get("error", "未知错误")
                    diag = first_result.get("diagnostics")
                    if diag and diag.get("missing_steps"):
                        missing_names = [s.get("target", "?") for s in diag["missing_steps"]]
                        error_msg += f" | 未定位步骤: {', '.join(missing_names)}"
                    logger.warning(
                        f"[convert-from-functional] 探索优先转化失败 "
                        f"(status={status}): {error_msg}, "
                        f"回退规则引擎"
                    )

            # 探索或转化失败 → 最终回退规则引擎
            logger.info(f"[convert-from-functional] 回退规则引擎: test_case_id={test_case_id}")
            service = WebUITestService(db)
            return service.convert_functional_to_web_ui(
                conversion_data=conversion_request,
                current_user=current_user
            )

    except Exception as e:
        logger.error(f"[convert-from-functional] 转换失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"转换功能测试用例到WEB UI测试用例失败: {str(e)}"
        )


# ========== 批量转化功能用例为UI用例 ==========

# ── 异步批量转化任务存储（内存）──
_BATCH_TASKS: Dict[str, Dict] = {}
import threading as _threading
# 取消事件独立存放（不挂 task dict——状态端点 return task 直接 JSON 化，threading.Event
# 不可序列化会 500（2026-08-25 22:14 真机踩坑：_thread.lock 编码 ValueError））
_TASK_CANCEL_EVENTS: Dict[str, _threading.Event] = {}

@router.post("/convert-batch-from-functional")
async def convert_batch_functional_to_web_ui(
    batch_request: BatchConversionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    http_req: Request = None,
    debug: str = Query(None, description="调试模式: 'parse'=仅解析步骤, 'score'=解析+页面元素评分"),
    async_mode: bool = Query(True, description="异步模式（默认开启）: 立即返回task_id，前端需轮询状态"),
):
    """
    批量将功能测试用例转换为WEB UI测试用例。
    async_mode=true（默认）→ 立即返回 {task_id}，通过 GET /convert-batch-async-status/{task_id} 轮询结果。
    """
    # 从第一个用例推导 project_id
    _pid = None
    try:
        from app.core.models.requirement import TestCase as ReqTC
        from app.core.models.test_simple import SimpleTC
        _tid = batch_request.test_case_ids[0] if batch_request.test_case_ids else None
        if _tid:
            _tc = db.query(ReqTC).filter(ReqTC.id == int(_tid)).first()
            if _tc: _pid = _tc.project_id
            else:
                _tc2 = db.query(SimpleTC).filter(SimpleTC.id == _tid).first()
                if _tc2: _pid = _tc2.project_id
    except Exception: pass
    _require_login_module(db, _pid)
    try:
        from app.core.services.functional_to_ui_service import FunctionalToUIService
        from app.core.services.step_parser import parse_steps, parse_single_step

        test_case_ids = batch_request.test_case_ids
        if not test_case_ids:
            raise HTTPException(status_code=400, detail="test_case_ids 不能为空")

        # 守卫：批量转化跳过未审核/已转化用例（不中断其余用例的转化），
        # 跳过名单（含 reason）随结果返回供前端展示；全部跳过 → 整批拒绝
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        from app.core.services.case_versioning import find_existing_wui
        skipped_cases: List[Dict] = []
        _convertible_ids = []
        for _tid in test_case_ids:
            # 已转化检查：已有未删除的 UI 用例 → 跳过（显式跳过，与前端
            # 「批量勾选已转化用例直接跳过并提示」语义一致，不做覆盖更新）
            # 方案B：按逻辑 id 匹配（兼容历史物理 id 绑定）
            _ui_existing, _ = find_existing_wui(db, _pid, _tid)
            if _ui_existing and _ui_existing.deleted_at is None:
                _meta = _load_case_meta(db, _tid)
                skipped_cases.append({
                    "id": _tid,
                    "name": _meta.get("name") or _tid,
                    "status": _meta.get("status") or "",
                    "reason": "已转化为UI用例",
                })
                continue
            # 登录模块提前排除（平台内部约定名）：业务流导入时已生成 __login__ 用例，
            # find_existing_wui 按逻辑 id 匹配不到它（WUI 绑定 __login__），且其 status 为
            # published（业务流导入自动发布，非人工审核 approved/active）——若放到审核守卫
            # (_ensure_case_convertible) 之后会被误判「未审核通过」。提前到审核判定之前，理由更准确。
            _probe_meta = _load_case_meta(db, _tid)
            if _probe_meta.get("module") == "登录模块":
                skipped_cases.append({
                    "id": _tid,
                    "name": _probe_meta.get("name") or _tid,
                    "status": _probe_meta.get("status") or "",
                    "reason": "登录模块已随业务流导入转化，无需重复转化",
                })
                continue
            try:
                _guard_tc = _ensure_case_convertible(db, _tid)
                # 同项目校验：批量转化按首条用例的项目推导探索配置/保存归属，
                # 混入跨项目用例会按错误项目过滤与落库——显式跳过（前端按项目选择，此为 API 直调防护）
                _tc_pid = getattr(_guard_tc, 'project_id', None)
                if _pid is not None and _tc_pid is not None and str(_tc_pid) != str(_pid):
                    _meta = _load_case_meta(db, _tid)
                    skipped_cases.append({
                        "id": _tid,
                        "name": _meta.get("name") or _tid,
                        "status": _meta.get("status") or "",
                        "reason": "跨项目用例，批量转化仅支持同一项目",
                    })
                    continue
                # 方案B：下游统一传逻辑 id（WUI 绑定逻辑 id）
                _convertible_ids.append(str(getattr(_guard_tc, 'logical_case_id', None) or _guard_tc.id))
            except HTTPException as _e:
                if _e.status_code == 404:
                    raise  # 用例不存在 → 硬错误（数据问题不静默跳过）
                _meta = _load_case_meta(db, _tid)
                skipped_cases.append({
                    "id": _tid,
                    "name": _meta.get("name") or _tid,
                    "status": _meta.get("status") or "",
                    "reason": "未审核通过",
                })
        if not _convertible_ids:
            raise HTTPException(status_code=400,
                                detail="所选功能用例均未审核通过，本次无用例可转化，请先审核通过后再转化")
        test_case_ids = _convertible_ids

        # ── 调试模式：parse=仅解析, score=解析+页面扫描评分 ──
        if debug and debug != 'score':
            service = FunctionalToUIService(db)
            debug_results = []
            for tid in test_case_ids:
                tc = service._load_test_case(tid)
                if not tc:
                    continue
                case_name = getattr(tc, 'name', None) or getattr(tc, 'title', '未命名')
                module = getattr(tc, 'module', '') or '通用'
                steps_raw = getattr(tc, 'test_steps', None)
                if not steps_raw:
                    debug_results.append({"case_name": case_name, "module": module, "steps": [], "error": "无测试步骤"})
                    continue
                parsed = parse_steps(steps_raw)
                steps_out = []
                for gs in parsed:
                    steps_out.append({
                        "seq": getattr(gs, 'seq', 0),
                        "raw_action": getattr(gs, 'raw_action', ''),
                        "action_type": getattr(gs, 'action_type', ''),
                        "target_text": getattr(gs, 'target_text', ''),
                        "role_hint": getattr(gs, 'role_hint', ''),
                        "ui_pattern": getattr(gs, 'ui_pattern', ''),
                        "fill_value": getattr(gs, 'fill_value', ''),
                        "select_option": getattr(gs, 'select_option', ''),
                        "context_hint": getattr(gs, 'context_hint', ''),
                        "source": getattr(gs, 'source', ''),
                    })
                debug_results.append({
                    "case_name": case_name,
                    "module": module,
                    "total_steps": len(steps_out),
                    "valid_steps": sum(1 for s in steps_out if s["target_text"]),
                    "skipped_steps": sum(1 for s in steps_out if not s["target_text"] and not s["action_type"]),
                    "steps": steps_out,
                })
            return {
                "success": True,
                "debug": True,
                "total_cases": len(debug_results),
                "cases": debug_results,
            }

        # ── 调试模式 score：登录 → 扫描页面 → 对每个关键词评分 ──
        if debug == 'score':
            from app.core.services.functional_to_ui_service import FunctionalToUIService
            from app.core.services.step_parser import parse_steps
            from app.core.services.exploration_config import WebExplorationConfig
            from app.core.models.project_ext import ProjectSetting

            service = FunctionalToUIService(db)
            # 解析所有步骤
            all_targets = {}  # target_text → {role, ui_pattern}
            for tid in test_case_ids:
                tc = service._load_test_case(tid)
                if not tc: continue
                steps_raw = getattr(tc, 'test_steps', None)
                if not steps_raw: continue
                for gs in parse_steps(steps_raw):
                    t = getattr(gs, 'target_text', '')
                    if t:
                        all_targets[t] = {
                            'role': getattr(gs, 'role_hint', ''),
                            'ui_pattern': getattr(gs, 'ui_pattern', ''),
                            'action': getattr(gs, 'action_type', ''),
                        }

            if not all_targets:
                return {"success": True, "debug": "score", "error": "没有可评分的目标关键词"}

            # 复用 FunctionalToUIService 的登录 + 探索基础设施，只做页面扫描评分
            score_result = await service._debug_score_elements(
                test_case_ids=test_case_ids,
                all_targets=all_targets,
                base_url=batch_request.base_url,
                headless=batch_request.headless if batch_request.headless is not None else True,
            )

            return {
                "success": True,
                "debug": "score",
                "login_ok": score_result.get("login_ok", False),
                "page_url": score_result.get("page_url", ""),
                "total_targets": len(all_targets),
                "found_count": sum(1 for v in score_result.get("scores", {}).values() if v.get("found")),
                "not_found_count": sum(1 for v in score_result.get("scores", {}).values() if not v.get("found")),
                "targets": score_result.get("scores", {}),
                "error": score_result.get("error"),
            }

        from app.core.services.functional_to_ui_service import convert_with_exploration_fallback

        logger.info(
            f"[convert-batch] 批量转化 {len(test_case_ids)} 条用例: "
            f"base_url={batch_request.base_url}"
        )

        # ── 异步模式：立即返回 task_id，后台处理，前端轮询 ──
        if async_mode:
            task_id = str(uuid4())
            _BATCH_TASKS[task_id] = {
                "task_id": task_id,
                "status": "processing",
                # 阶段进度字段（2026-08-25：探索/POM/转化分阶段上报，前端进度条从点击转化即开始移动）
                # phase: preparing|exploring|pom|converting|done|failed
                "phase": "preparing",
                "phase_detail": "正在准备转化...",
                "explored_done": 0,
                "explored_total": 0,
                "step_done": 0,
                "step_total": 0,
                "total": len(test_case_ids),
                "completed": 0,
                "results": [],
                "summary": {},
                "skipped_cases": skipped_cases,
                "error": None,
                "created_at": datetime.utcnow().isoformat(),
            }

            async def _process_async():
                cancel_event = _threading.Event()
                # 取消事件存独立字典（不能挂 task dict——状态端点 JSON 化 task 会因
                # threading.Event 不可序列化 500）；取消端点按 task_id 找到并 set
                # （前端「取消转化」按钮闭环——探索线程 cancel_check 检测到后停止探索、finally 关浏览器）
                _TASK_CANCEL_EVENTS[task_id] = cancel_event

                async def _watchdog():
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        cancel_event.set()

                _wt = asyncio.create_task(_watchdog())

                def _is_cancelled():
                    return cancel_event.is_set()

                def _update_progress(result_item: dict = None):
                    """每完成一条用例就更新进度"""
                    if result_item:
                        _BATCH_TASKS[task_id]["results"].append(result_item)
                    _BATCH_TASKS[task_id]["completed"] = len(_BATCH_TASKS[task_id]["results"])

                def _update_phase(ev: dict = None):
                    """阶段进度事件（探索/POM/转化阶段）——与用例结果事件（_update_progress）互斥：
                    带 phase 键的事件只更新阶段字段，不追加 results。
                    由探索线程调用（dict 写入 GIL 下线程安全）。"""
                    if not ev:
                        return
                    _BATCH_TASKS[task_id]["phase"] = ev.get(
                        "phase", _BATCH_TASKS[task_id].get("phase", "processing"))
                    if ev.get("phase_detail") is not None:
                        _BATCH_TASKS[task_id]["phase_detail"] = ev["phase_detail"]
                    for _k in ("explored_done", "explored_total", "step_done", "step_total"):
                        if ev.get(_k) is not None:
                            _BATCH_TASKS[task_id][_k] = ev[_k]

                try:
                    from app.core.database import SessionLocal
                    _bg_db = SessionLocal()
                    try:
                        result = await convert_with_exploration_fallback(
                            db=_bg_db,
                            test_case_ids=test_case_ids,
                            base_url=batch_request.base_url or "",
                            browser=batch_request.browser or "chromium",
                            viewport_size=batch_request.viewport_size or "1920x1080",
                            headless=batch_request.headless if batch_request.headless is not None else True,
                            script_type=batch_request.script_type or "playwright",
                            script_language=batch_request.script_language or "python",
                            project_id=None,
                            force_explore=batch_request.force_explore if batch_request.force_explore is not None else False,
                            cancel_check=_is_cancelled,
                            progress_callback=_update_progress,
                            phase_cb=_update_phase,
                        )
                        # 用户取消优先：探索/转化已被取消（cancel_event set）→ 最终状态 cancelled，
                        # 不被 completed/partial 覆盖——前端据此知道流程确实结束了
                        if cancel_event.is_set():
                            _BATCH_TASKS[task_id]["status"] = "cancelled"
                            _BATCH_TASKS[task_id]["phase"] = "cancelled"
                            _BATCH_TASKS[task_id]["phase_detail"] = "已取消"
                        else:
                            _BATCH_TASKS[task_id]["status"] = "completed" if result.get("success") else "partial"
                            _BATCH_TASKS[task_id]["phase"] = "done"
                            _BATCH_TASKS[task_id]["phase_detail"] = "转化完成"
                        _BATCH_TASKS[task_id]["success_count"] = result.get("success_count", 0)
                        _BATCH_TASKS[task_id]["total_count"] = result.get("total_count", len(test_case_ids))
                        _BATCH_TASKS[task_id]["summary"] = result.get("summary", {})
                        # 探索期生成的 API 用例统计（探索自动生成 API 用例）
                        _BATCH_TASKS[task_id]["api_cases_generated"] = result.get("api_cases_generated", {})
                    finally:
                        _bg_db.close()
                except Exception as e:
                    logger.error(f"[convert-batch-async] 转化异常: {e}")
                    if cancel_event.is_set():
                        _BATCH_TASKS[task_id]["status"] = "cancelled"
                        _BATCH_TASKS[task_id]["phase"] = "cancelled"
                        _BATCH_TASKS[task_id]["phase_detail"] = "已取消"
                    else:
                        _BATCH_TASKS[task_id]["status"] = "failed"
                        _BATCH_TASKS[task_id]["error"] = str(e)
                        _BATCH_TASKS[task_id]["phase"] = "failed"
                        _BATCH_TASKS[task_id]["phase_detail"] = f"转化失败：{e}"
                finally:
                    cancel_event.set()
                    _TASK_CANCEL_EVENTS.pop(task_id, None)  # 任务结束清理取消句柄（幂等）
                    if _wt:
                        _wt.cancel()

            asyncio.create_task(_process_async())
            logger.info(f"[convert-batch-async] Task {task_id} 已启动（{len(test_case_ids)} 条）")
            # 兼容旧前端：加上 success/results 字段
            return {
                "task_id": task_id,
                "status": "processing",
                "total": len(test_case_ids),
                "success": True,
                "results": [],
                "success_count": 0,
                "total_count": len(test_case_ids),
                "summary": {},
                "skipped_cases": skipped_cases,
                "api_cases_generated": {},
            }

        # ── 同步模式（async_mode=false）──
        # ── 取消令牌：前端断开时立即通知后端停止 LLM 调用 ──
        # 双重保障：
        #   1. ASGI CancelledError: 当 Uvicorn 检测到客户端 TCP 断开，自动取消 handler 任务
        #   2. is_disconnected 轮询: 500ms 一次，兼容部分不取消任务的服务器
        cancel_event = threading.Event()

        async def _watchdog():
            """看门狗：阻塞等待 ASGI 取消信号（客户端断开时 Uvicorn 取消所有子任务）"""
            try:
                await asyncio.Event().wait()  # 永久阻塞，直到被取消
            except asyncio.CancelledError:
                cancel_event.set()
                logger.info("[convert-batch] ⛔ ASGI 任务取消（客户端断开），设置取消令牌")

        async def _poll_disconnect():
            """轮询 is_disconnected（兼容不发送 CancelledError 的服务器）"""
            try:
                while not cancel_event.is_set():
                    try:
                        if http_req and await http_req.is_disconnected():
                            cancel_event.set()
                            logger.info("[convert-batch] ⛔ is_disconnected 检测到断开，设置取消令牌")
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                pass

        _watchdog_task = asyncio.create_task(_watchdog())
        _poll_task = asyncio.create_task(_poll_disconnect())

        # 同步版取消检查（供同步代码调用）
        def _is_cancelled() -> bool:
            return cancel_event.is_set()

        result = None
        try:
            result = await convert_with_exploration_fallback(
                db=db,
                test_case_ids=test_case_ids,
                base_url=batch_request.base_url or "",
                browser=batch_request.browser or "chromium",
                viewport_size=batch_request.viewport_size or "1920x1080",
                headless=batch_request.headless if batch_request.headless is not None else True,
                script_type=batch_request.script_type or "playwright",
                script_language=batch_request.script_language or "python",
                project_id=None,
                force_explore=batch_request.force_explore if batch_request.force_explore is not None else False,
                cancel_check=_is_cancelled,
            )

            return BatchConversionResult(
                success=result.get("success", False),
                results=result.get("results", []),
                success_count=result.get("success_count", 0),
                total_count=result.get("total_count", len(test_case_ids)),
                explored_modules=result.get("explored_modules", []),
                cached_modules=result.get("cached_modules", []),
                exploration_method=result.get("exploration_method", ""),
                summary=result.get("summary", {}),
                exploration_failures=result.get("exploration_failures") or {},
                skipped_cases=skipped_cases,
            )
        except asyncio.CancelledError:
            cancel_event.set()
            logger.info("[convert-batch] ⛔ Handler 被取消（客户端断开），返回部分结果")
            return BatchConversionResult(
                success=False,
                results=result.get("results", []) if result else [],
                success_count=result.get("success_count", 0) if result else 0,
                total_count=len(test_case_ids),
                summary={"cancelled": True, **(result.get("summary", {}) if result else {})},
                skipped_cases=skipped_cases,
            )
        finally:
            cancel_event.set()
            for _t in (_watchdog_task, _poll_task):
                if _t:
                    _t.cancel()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[convert-batch] 批量转化失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"批量转化失败: {str(e)}"
        )


# ========== 异步批量转化状态查询 ==========

@router.get("/convert-batch-async-status/{task_id}")
async def get_batch_async_status(task_id: str):
    """查询异步批量转化任务的进度和结果"""
    task = _BATCH_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已过期")
    return task


@router.post("/convert-batch-cancel/{task_id}")
async def cancel_batch_conversion(task_id: str):
    """取消异步批量转化任务（用户点击「取消转化」）。

    置取消标志 → 探索线程 cancel_check 检测到 → 探索停止 → finally 关浏览器 →
    转化循环/POM/LLM 各检查点相继退出 → 任务最终状态 cancelled。
    （幂等：任务不存在/已结束返回当前状态，不报错。）
    """
    task = _BATCH_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已过期")
    _ce = _TASK_CANCEL_EVENTS.get(task_id)
    if _ce:
        _ce.set()
        task["status"] = "cancelled"
        task["phase"] = "cancelled"
        task["phase_detail"] = "已取消（正在停止探索并关闭浏览器）"
        logger.info(f"[convert-batch-cancel] Task {task_id} 取消信号已发送，等待探索线程退出")
    else:
        # 任务已结束（无 cancel_event 残留）——返回当前终态
        logger.info(f"[convert-batch-cancel] Task {task_id} 无活跃取消句柄（终态 {task.get('status')}）")
    return {"task_id": task_id, "status": task.get("status"), "phase_detail": task.get("phase_detail")}


# ========== WEB UI测试用例管理 ==========

@router.get("/test-cases", response_model=WebUITestCaseListResponse)
async def get_web_ui_test_cases(
    browser: Optional[str] = Query(None, description="浏览器类型"),
    script_type: Optional[str] = Query(None, description="脚本类型"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    project_id: Optional[int] = Query(None, description="项目ID（按项目过滤）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取WEB UI测试用例列表（支持按项目过滤）
    """
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        from app.core.models.requirement import TestCase as ReqTestCase
        from app.core.models.test_simple import SimpleTestCase

        # ── 确保登录用例存在（项目隔离：只检查/创建当前项目的 __login__）──
        _login_q = db.query(WebUITestCaseModel).filter(
            WebUITestCaseModel.test_case_id == '__login__'
        )
        if project_id:
            _login_q = _login_q.filter(WebUITestCaseModel.project_id == str(project_id))
        _login_exists = _login_q.first()
        if not _login_exists:
            try:
                from app.core.models.knowledge_graph import KnowledgeGraph
                _kgq = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.exploration_status == 'completed'
                )
                if project_id:
                    _kgq = _kgq.filter(KnowledgeGraph.project_id == project_id)
                _kg = _kgq.order_by(KnowledgeGraph.completed_at.desc()).first()
                if _kg and _kg.base_url:
                    _login = WebUITestCaseModel(
                        test_case_id='__login__',
                        project_id=str(_kg.project_id) if _kg.project_id else None,
                        base_url=_kg.base_url,
                        browser='chromium',
                        viewport_width=1920, viewport_height=1080,
                        headless=False, timeout=30000,
                        test_script='# 登录用例 — 由 storage_state 自动处理',
                        test_data={
                            'title': '系统登录', 'module': '前置条件',
                            'case_id': '__login__',
                            'steps': [{'seq': 1, 'action': 'login',
                                       'desc': '加载登录态', 'expected': '成功进入系统首页'}],
                        },
                        generation_mode='pom_data_driven',
                    )
                    db.add(_login)
                    db.commit()
            except Exception:
                db.rollback()

        query = db.query(WebUITestCaseModel)

        # 按项目过滤（核心——防止跨项目数据泄露）
        if project_id:
            query = query.filter(WebUITestCaseModel.project_id == str(project_id))

        # 过滤条件
        if browser:
            query = query.filter(WebUITestCaseModel.browser == browser)
        if script_type:
            query = query.filter(WebUITestCaseModel.script_type == script_type)

        total = query.count()
        items = query.order_by(WebUITestCaseModel.created_at.desc()).offset(
            (page - 1) * size
        ).limit(size).all()

        # 构建响应，从原始用例表查询名称和模块
        result_items = []
        for item in items:
            resp = WebUITestCaseResponse.model_validate(item)
            related_case = None
            try:
                tc_id_int = int(item.test_case_id)
                related_case = db.query(ReqTestCase).filter(ReqTestCase.id == tc_id_int).first()
            except (ValueError, TypeError):
                related_case = db.query(SimpleTestCase).filter(
                    SimpleTestCase.id == item.test_case_id
                ).first()

            case_name = "未命名"
            case_module = "通用"
            if related_case:
                case_name = (getattr(related_case, 'name', None)
                            or getattr(related_case, 'title', None)
                            or '未命名')
                case_module = getattr(related_case, 'module', '') or '通用'
            # test_data JSON 中的更准确（LLM 生成时写入）
            td = getattr(item, 'test_data', None)
            if isinstance(td, dict):
                if td.get('title'):
                    case_name = td['title']
                if td.get('module'):
                    case_module = td['module']
            resp.test_case = {"name": str(case_name), "module": str(case_module)}
            # 前置条件以功能用例为权威来源；存量 UI 用例即使 test_data 没有该字段，
            # 这里也能正常展示。新生成用例则优先使用 test_data 中的同一份原文。
            _td_pre = td.get("preconditions", "") if isinstance(td, dict) else ""
            resp.preconditions = _td_pre or (getattr(related_case, "preconditions", "") if related_case else "") or ""
            result_items.append(resp)

        return WebUITestCaseListResponse(
            items=result_items,
            total=total,
            page=page,
            size=size
        )

    except Exception as e:
        logger.error(f"获取WEB UI测试用例列表失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取WEB UI测试用例列表失败: {str(e)}"
        )


@router.get("/test-cases/{test_case_id}", response_model=WebUITestCaseResponse)
async def get_web_ui_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """获取WEB UI测试用例详情"""
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        from app.core.models.requirement import TestCase as ReqTestCase
        from app.core.models.test_simple import SimpleTestCase

        item = db.query(WebUITestCaseModel).filter(WebUITestCaseModel.id == str(test_case_id)).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"WEB UI测试用例不存在: {test_case_id}")

        resp = WebUITestCaseResponse.model_validate(item)
        # 查找原始用例名称和模块
        related_case = None
        try:
            tc_id_int = int(item.test_case_id)
            related_case = db.query(ReqTestCase).filter(ReqTestCase.id == tc_id_int).first()
        except (ValueError, TypeError):
            related_case = db.query(SimpleTestCase).filter(SimpleTestCase.id == item.test_case_id).first()
        case_name = "未命名"
        case_module = "通用"
        if related_case:
            case_name = (getattr(related_case, 'name', None)
                        or getattr(related_case, 'title', None)
                        or '未命名')
            case_module = getattr(related_case, 'module', '') or '通用'
        td = getattr(item, 'test_data', None)
        if isinstance(td, dict):
            if td.get('title'):
                case_name = td['title']
            if td.get('module'):
                case_module = td['module']
        resp.test_case = {"name": str(case_name), "module": str(case_module)}
        resp.preconditions = (td.get("preconditions", "") if isinstance(td, dict) else "") or (getattr(related_case, "preconditions", "") if related_case else "") or ""
        return resp

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取WEB UI测试用例详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取WEB UI测试用例详情失败: {str(e)}")


@router.get("/converted-ids")
async def get_converted_ids(
    db: Session = Depends(get_db),
):
    """返回已转化为UI用例的功能用例ID列表。"""
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        # 过滤软删（与全站 deleted_at 语义一致）：软删的 UI 用例不再计为「已转化」
        rows = db.query(WebUITestCaseModel.test_case_id).filter(
            WebUITestCaseModel.deleted_at.is_(None)
        ).all()
        ids = [r[0] for r in rows]
        return {"converted_ids": ids, "count": len(ids)}
    except Exception as e:
        logger.error(f"获取已转化ID列表失败: {e}")
        return {"converted_ids": [], "count": 0}


@router.get("/all-ids")
async def get_all_ui_test_case_ids(
    db: Session = Depends(get_db),
):
    """返回所有 UI 用例的 ID 列表（无分页，供批量操作使用）。"""
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        # 排除登录模块用例（__login__）：它是前置条件不可删除、也不参与普通批量执行，
        # 全选删除/执行若含它会因 403/无意义而干扰（用户 2026-09-02）。
        rows = db.query(WebUITestCaseModel).filter(
            WebUITestCaseModel.test_case_id != '__login__'
        ).all()
        return {"ids": [str(r.id) for r in rows], "count": len(rows)}
    except Exception as e:
        return {"ids": [], "count": 0}


@router.put("/test-cases/{test_case_id}", response_model=WebUITestCaseResponse)
async def update_web_ui_test_case(
    test_case_id: UUID,
    update_data: WebUITestCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """更新WEB UI测试用例"""
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel

        item = db.query(WebUITestCaseModel).filter(WebUITestCaseModel.id == str(test_case_id)).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"WEB UI测试用例不存在: {test_case_id}")

        # 登录用例不可编辑（由系统自动维护）
        if getattr(item, 'test_case_id', '') == '__login__':
            raise HTTPException(status_code=403, detail="登录用例由系统自动维护，不可手动编辑")

        update_dict = update_data.dict(exclude_unset=True)
        for key, value in update_dict.items():
            if hasattr(item, key):
                setattr(item, key, value)

        item.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(item)

        return WebUITestCaseResponse.model_validate(item)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新WEB UI测试用例失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新WEB UI测试用例失败: {str(e)}")


@router.delete("/test-cases/{test_case_id}")
async def delete_web_ui_test_case(
    test_case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """删除WEB UI测试用例（有执行记录时阻止删除）"""
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        from app.core.models.web_ui_test import WebUITestExecution as WebUITestExecutionModel

        item = db.query(WebUITestCaseModel).filter(WebUITestCaseModel.id == str(test_case_id)).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"WEB UI测试用例不存在: {test_case_id}")

        # 登录用例不可删除
        if getattr(item, 'test_case_id', '') == '__login__':
            raise HTTPException(status_code=403, detail="登录用例是所有用例的前置条件，不可删除")

        # 检查是否有关联的执行记录——只阻止「执行中心场景测试(scenario)」记录。
        # UI 用例页的临时执行(ui_verify)只是验证转化后的用例是否正确，对结果无要求，
        # 不应阻塞删除（用户 2026-09-02：UI 用例验证结果落库不阻断删除）。
        from app.core.models.test_simple import TestExecution
        exec_count = db.query(TestExecution).filter(
            TestExecution.test_case_id == str(test_case_id),
            TestExecution.execution_type == 'scenario',
        ).count()
        if exec_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"该UI用例已添加到执行中心（{exec_count} 条场景执行记录），请先从执行中心移除后再删除"
            )

        # 同时删除关联的元素选择器（WebUIElementSelector 有 ondelete=CASCADE，但显式处理更安全）
        from app.core.models.web_ui_test import WebUIElementSelector
        db.query(WebUIElementSelector).filter(
            WebUIElementSelector.web_ui_test_case_id == str(test_case_id)
        ).delete()

        db.delete(item)
        db.commit()

        return {"success": True, "message": "WEB UI测试用例删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除WEB UI测试用例失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除WEB UI测试用例失败: {str(e)}")


# ========== WEB UI测试执行 ==========
# 执行归口唯一：单条/批量/场景全部走 UITestExecutor
# （pytest 参数化数据驱动在线等价：用例前置条件 → 步骤反射分发执行）

@router.post("/execute", response_model=WebUITestExecutionResult)
async def execute_web_ui_test(
    execution_request: WebUITestExecutionRequest,
    headless: Optional[bool] = Query(None, description="覆盖用例的 headless 设置"),
    browser_mode: Optional[str] = Query(None, description="浏览器模式: isolated | reuse（单条无意义，仅兼容）"),
    slow_mo: Optional[int] = Query(None, description="Playwright slow_mo（毫秒）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    执行单条 WEB UI 测试（统一 V1/V2 执行器）。

    根据 generation_mode 自动选择执行引擎：
    - pom_data_driven (V2): StepRunner + POM 动态编译执行
    - linear (V1): subprocess .py 脚本执行

    Query 参数可覆盖用例的 headless / browser_mode 设置。
    单条执行始终使用 isolated 模式（复用模式仅场景执行有意义）。
    """
    try:
        from app.core.models.web_ui_test import WebUITestCase as WebUITestCaseModel
        from app.core.services.execution_config import ExecutionConfig, BrowserMode
        from app.core.services.ui_test_executor import UITestExecutor
        import time

        wui = db.query(WebUITestCaseModel).filter(
            WebUITestCaseModel.id == str(execution_request.web_ui_test_case_id)
        ).first()

        if not wui:
            raise HTTPException(status_code=404, detail="WebUI测试用例不存在")

        # 构建配置：单条执行强制 isolated
        config = ExecutionConfig(
            headless=headless if headless is not None else (
                wui.headless if wui.headless is not None else True
            ),
            browser_mode=BrowserMode.ISOLATED,  # 单条执行不允许复用
            slow_mo=slow_mo or 0,
            timeout_ms=execution_request.timeout or wui.timeout or 60000,
        )

        generation_mode = getattr(wui, 'generation_mode', None) or 'linear'
        logger.info(f"[Execute] 用例 {wui.id}, mode={generation_mode}, "
                    f"headless={config.headless}")

        start_time = time.time()
        executor = UITestExecutor(config)
        exec_result = await executor.execute_single(wui)

        duration = int((time.time() - start_time) * 1000)

        # 落库：UI 用例单条临时执行（ui_verify），与执行中心场景测试(scenario)区分。
        # UI 用例页的执行仅验证转化后的用例是否正确，对测试结果无过多要求。落库失败不影响执行。
        try:
            from app.core.models.test_simple import TestExecution
            _st = str(exec_result.get("status") or "")
            if _st in ("completed", "passed", "success"):
                _exec_status = "passed"
            elif _st == "skipped":
                _exec_status = "skipped"
            else:
                _exec_status = "failed"
            db.add(TestExecution(
                test_case_id=str(wui.id),
                project_id=str(wui.project_id) if getattr(wui, 'project_id', None) else None,
                status=_exec_status,
                executed_by=str(current_user.id),
                execution_type='ui_verify',
                duration=duration // 1000,
                failure_reason=exec_result.get("error") or None,
            ))
            db.commit()
        except Exception as _e:
            logger.warning(f"[Execute] 执行结果落库失败(不影响执行): {_e}")

        return WebUITestExecutionResult(
            execution_id=uuid4(),
            status=exec_result.get("status", "failed"),
            duration=duration,
            screenshots=[],
            video_path=None,
            performance_metrics={
                "duration_ms": duration,
                "generation_mode": generation_mode,
                "browser_mode": exec_result.get("browser_mode", "isolated"),
                "steps_executed": exec_result.get("steps_executed", 0),
                "headless": config.headless,
            },
            console_errors=exec_result.get("console_errors", []),
            error=exec_result.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Execute] 执行失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


# ========== 批量执行（有头+复用模式）==========

class BatchExecuteRequest(BaseModel):
    ids: List[str] = Field(..., description="UI用例ID列表")

@router.post("/execute-batch")
async def execute_batch_web_ui(
    req: BatchExecuteRequest,
    headless: bool = Query(False, description="无头模式"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量执行：浏览器开一次，登录一次，依次执行全部用例。有头+复用模式。"""
    try:
        from app.core.models.web_ui_test import WebUITestCase as WUI
        from app.core.services.execution_config import ExecutionConfig, BrowserMode
        from app.core.services.ui_test_executor import UITestExecutor

        cases = []
        for cid in req.ids:
            wui = db.query(WUI).filter(WUI.id == cid).first()
            if wui:
                cases.append(wui)

        if not cases:
            return {"success": False, "error": "无有效用例"}

        selected_ids = {str(w.id) for w in cases}

        # ── 依赖展开 + 拓扑排序（执行层 · 通用，2026-09-03）──
        # 当选中用例里有 depends_on（指向共享准备/setup 前置 UI 用例）时：
        #   1) 从 DB 补加载前置用例，排到前面先执行；
        #   2) 同一前置在调度序里只出现一次 → 首条执行后，后续依赖用例不再重复执行它（共享去重）；
        #   3) 前置未通过时，依赖它的用例在执行器里被标记 skipped，不再空跑。
        # 无 depends_on 的用例不展开，行为与历史完全一致。
        from app.core.services.ui_dependency import resolve_execution_order
        dep_map: dict = {}
        if any(getattr(w, 'depends_on', None) for w in cases):
            def _dep_loader(cid: str):
                return db.query(WUI).filter(WUI.id == cid).first()
            cases, dep_map = resolve_execution_order(cases, loader=_dep_loader)

        config = ExecutionConfig(
            headless=headless,
            browser_mode=BrowserMode.REUSE,
            timeout_ms=60000,
        )

        executor = UITestExecutor(config)
        results = await executor.execute_batch(cases, dep_map=dep_map)

        # ── 落库：UI 用例临时执行（ui_verify）──
        # 用户 2026-09-02：UI 用例页的批量执行只是「验证转化后的用例是否正确」，
        # 对测试结果无过多要求。execution_type='ui_verify'，与执行中心场景测试(scenario)严格区分。
        # 落库失败不影响执行结果返回。
        try:
            from app.core.models.test_simple import TestExecution
            case_map = {str(w.id): w for w in cases}
            for r in results:
                cid = r.get("test_case_id")
                if not cid or cid not in case_map:
                    continue
                # 状态归一：completed(+skipped) → passed/skipped；依赖前置失败显式 skipped → skipped；其余 failed/error
                _st = r.get("status")
                if _st == "completed":
                    _st = "skipped" if r.get("skipped") else "passed"
                elif _st != "skipped":
                    _st = "failed"
                _w = case_map[cid]
                db.add(TestExecution(
                    test_case_id=str(_w.id),
                    project_id=str(_w.project_id) if getattr(_w, 'project_id', None) else None,
                    status=_st,
                    executed_by=str(current_user.id),
                    execution_type='ui_verify',
                    duration=int(r.get("duration_ms") or 0) // 1000,
                    failure_reason=r.get("error") or None,
                    actual_results=json.dumps(r, ensure_ascii=False),
                ))
            db.commit()
        except Exception as _e:
            logger.warning(f"[ExecuteBatch] 执行结果落库失败(不影响执行): {_e}")

        # 统计仅针对用户选中的用例（前置/setup 用例是内部调度，已落库但不计入本次响应统计，
        # 避免依赖共享前置的批量把 setup 算进 total 造成误解）。test_case_id 为不透明字符串。
        sel_res = [r for r in results if r.get("test_case_id") in selected_ids]
        # P0-2（2026-09-01 迁移）：三分统计——completed 且 skipped=True（动态数据为空跳过）、
        # 以及 status=="skipped"（前置依赖失败跳过）均计 skipped，不计失败。
        skipped = sum(1 for r in sel_res if r.get("status") == "skipped"
                      or (r.get("status") == "completed" and r.get("skipped")))
        ok = sum(1 for r in sel_res if r.get("status") == "completed" and not r.get("skipped"))
        fail = len(sel_res) - ok - skipped
        return {
            "success": True,
            "total": len(sel_res),
            "ok": ok,
            "skipped": skipped,
            "fail": fail,
            "results": sel_res,
        }
    except Exception as e:
        logger.error(f"[ExecuteBatch] 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 获取可转换的功能测试用例 ==========

@router.get("/convertible-functional-tests")
async def get_convertible_functional_tests(
    project_id: Optional[int] = Query(None, description="项目ID"),
    version_id: Optional[int] = Query(None, description="版本ID（方案B：该版本视角的生效行，防 deprecated 旧版混入）"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取可转换为WEB UI测试的功能测试用例列表
    从需求-based test_cases 表和 simple test_case 表中查询功能测试用例
    """
    try:
        from app.core.models.requirement import TestCase as ReqTestCase
        from app.core.models.test_simple import SimpleTestCase
        from app.core.services.case_versioning import resolve_effective_cases

        items = []
        total = 0

        # 1. 查询需求-based功能测试用例 (test_cases 表)
        #    方案B：带 version_id → 该版本视角的生效行（跨版本派生链，仅 approved/active）
        if version_id:
            from app.core.models.project import Version as VersionModel
            _v = db.query(VersionModel).filter(VersionModel.id == version_id).first()
            if _v:
                eff_rows = [
                    r for r in resolve_effective_cases(db, _v.project_id, version_id)
                    if (r.status or "") in ("approved", "active")
                ]
                req_cases = eff_rows
                # search 过滤（内存侧，生效行集合量级小）
                if search:
                    _s = search.lower()
                    req_cases = [r for r in req_cases
                                 if _s in (r.name or "").lower()
                                 or _s in (r.description or "").lower()]
            else:
                req_cases = []
        else:
            req_query = db.query(ReqTestCase).filter(
                ReqTestCase.status.in_(["approved", "active"])
            )
            if project_id:
                req_query = req_query.filter(ReqTestCase.project_id == project_id)
            if search:
                req_query = req_query.filter(
                    ReqTestCase.name.ilike(f"%{search}%") |
                    ReqTestCase.description.ilike(f"%{search}%")
                )
            req_cases = req_query.order_by(ReqTestCase.created_at.desc()).all()

        for tc in req_cases:
            # 排除登录模块：其业务流导入时已生成 __login__ 用例（转化成功），
            # 再进可转化列表会在全选时被误带入（module 为平台内部约定名）
            if (tc.module or '') == '登录模块':
                continue
            items.append({
                "id": str(tc.id),
                "title": tc.name,
                "description": tc.description or "",
                "test_type": "functional",
                "priority": tc.priority or "P2",
                "status": tc.status,
                "source": "requirement",
                "project_id": tc.project_id,
                "module": tc.module or "",
                "created_at": tc.created_at.isoformat() if tc.created_at else None,
            })

        # 2. 查询简单功能测试用例 (test_case 表)
        simple_query = db.query(SimpleTestCase).filter(
            SimpleTestCase.test_type == "functional",
            SimpleTestCase.status.in_(["active", "approved"])
        )
        if search:
            simple_query = simple_query.filter(
                SimpleTestCase.title.ilike(f"%{search}%") |
                SimpleTestCase.description.ilike(f"%{search}%")
            )

        simple_cases = simple_query.order_by(SimpleTestCase.created_at.desc()).all()
        for tc in simple_cases:
            if (tc.module or '') == '登录模块':
                continue
            items.append({
                "id": str(tc.id),
                "title": tc.title,
                "description": tc.description or "",
                "test_type": "functional",
                "priority": tc.priority or "P2",
                "status": tc.status,
                "source": "simple",
                "project_id": tc.project_id,
                "module": tc.module or "",
                "created_at": tc.created_at.isoformat() if tc.created_at else None,
            })

        total = len(items)
        # 分页
        start = (page - 1) * size
        end = start + size
        paged_items = items[start:end]

        return {
            "items": paged_items,
            "total": total,
            "page": page,
            "size": size
        }

    except Exception as e:
        logger.error(f"获取可转换的功能测试用例列表失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取可转换的功能测试用例列表失败: {str(e)}"
        )


# ========== 聊天生成WEB UI测试用例 ==========

@router.post("/generate/chat")
async def generate_web_ui_from_chat(
    request: ChatGenerateWebUITestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    AI助手聊天接口 - 支持普通聊天和测试用例生成
    
    当用户消息包含"生成测试用例"等关键词时，会生成并保存测试用例
    否则返回普通的AI对话回复
    
    - **message**: 聊天消息或需求文档内容（必须）
    - **knowledge_base_id**: 知识库ID（可选，用于RAG增强）
    - **project_name**: 项目名称（可选）
    - **base_url**: 基础URL（默认：http://localhost:3000）
    - **browser**: 浏览器类型（默认：chromium）
    - **viewport_size**: 视口尺寸（默认：1920x1080）
    - **headless**: 是否无头模式（默认：true）
    - **generate_element_selectors**: 是否生成元素选择器（默认：true）
    - **generate_test_script**: 是否生成测试脚本（默认：true）
    - **script_type**: 脚本类型（默认：playwright）
    - **script_language**: 脚本语言（默认：python）
    """
    try:
        llm_service = LLMService(db)
        rag_service = RAGRetrievalService(db)
        
        rag_context = ""
        rag_sources = []
        
        if request.knowledge_base_id:
            try:
                rag_result = rag_service.rag_query(
                    query=request.message,
                    knowledge_base_id=request.knowledge_base_id,
                    top_k=3
                )
                if rag_result.get("success") and rag_result.get("answer"):
                    rag_context = rag_result["answer"]
                    rag_sources = rag_result.get("sources", [])
            except Exception as e:
                logger.warning(f"RAG query failed: {str(e)}")
        
        is_generate_test = is_test_generation_request(request.message)
        
        if not is_generate_test:
            system_prompt = """你是一个专业的AI测试助手，帮助用户解答关于软件测试、自动化测试、测试用例设计等问题。
你可以：
1. 解答测试相关的技术问题
2. 提供测试用例设计建议
3. 解释测试方法和最佳实践
4. 帮助分析测试需求

如果用户想要生成测试用例，请提示用户在消息中包含"生成测试用例"关键词。"""
            
            user_message = request.message
            if rag_context:
                user_message = f"{request.message}\n\n【参考知识库内容】：\n{rag_context}"
            
            response = llm_service.call_llm(
                prompt=user_message,
                system_prompt=system_prompt,
                temperature=0.7
            )
            
            return {
                "success": True,
                "message_type": "chat",
                "content": response or "抱歉，我暂时无法回答这个问题。",
                "test_cases": None,
                "saved_to_db": False,
                "sources": rag_sources if rag_sources else None
            }
        
        logger.info(f"检测到测试用例生成请求: {request.message[:100]}...")
        
        enhanced_message = request.message
        if rag_context:
            enhanced_message = f"{request.message}\n\n【参考知识库内容】：\n{rag_context}"
        
        service = WebUITestService(db)
        
        result = service.generate_from_chat(
            chat_message=enhanced_message,
            project_name=request.project_name or "默认项目",
            base_url=request.base_url or "",
            browser=request.browser or "chromium",
            viewport_size=request.viewport_size or "1920x1080",
            headless=request.headless if request.headless is not None else True,
            generate_element_selectors=request.generate_element_selectors if request.generate_element_selectors is not None else True,
            generate_test_script=request.generate_test_script if request.generate_test_script is not None else True,
            script_type=request.script_type or "playwright",
            script_language=request.script_language or "python",
            current_user=current_user
        )
        
        return {
            "success": result.success,
            "message_type": "generate_test",
            "content": f"✅ 成功生成 {len(result.web_ui_test_cases or [])} 个WEB UI测试用例" if result.success else f"❌ 生成失败：{', '.join(result.errors or ['未知错误'])}",
            "test_cases": result.web_ui_test_cases,
            "saved_to_db": result.success,
            "sources": rag_sources if rag_sources else None
        }
        
    except Exception as e:
        logger.error(f"Chat processing failed: {str(e)}")
        return {
            "success": False,
            "message_type": "error",
            "content": f"处理失败: {str(e)}",
            "test_cases": None,
            "saved_to_db": False,
            "sources": None
        }


# ========== 健康检查 ==========

@router.get("/health")
async def health_check():
    """WEB UI测试服务健康检查"""
    return {"status": "healthy", "service": "web-ui-tests"}


# ========== 流式聊天接口 ==========

class ChatStreamRequest(BaseModel):
    """流式聊天请求"""
    message: str = Field(..., description="聊天消息")
    knowledge_base_id: Optional[int] = Field(None, description="知识库ID")
    base_url: Optional[str] = Field("")
    browser: Optional[str] = Field("chromium")
    viewport_size: Optional[str] = Field("1920x1080")
    headless: Optional[bool] = Field(True)
    script_type: Optional[str] = Field("playwright")
    script_language: Optional[str] = Field("python")
    generate_element_selectors: Optional[bool] = Field(True)
    generate_test_script: Optional[bool] = Field(True)


@router.post("/chat/stream")
async def chat_stream(
    request: ChatStreamRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    流式AI助手聊天接口 - 逐步返回AI回复
    
    - **message**: 聊天消息（必须）
    - **knowledge_base_id**: 知识库ID（可选，用于RAG增强）
    """
    async def generate():
        llm_service = LLMService(db)
        
        # 检查是否有激活的LLM配置
        active_config = llm_service.get_active_config()
        if not active_config:
            yield f"data: {json.dumps({'type': 'error', 'message': '系统未配置AI服务。请先前往系统设置 → LLM配置页面添加并激活LLM配置。'})}\n\n"
            return
        
        rag_service = RAGRetrievalService(db)
        
        rag_context = ""
        rag_sources = []
        
        if request.knowledge_base_id:
            try:
                rag_result = await asyncio.to_thread(
                    rag_service.rag_query,
                    query=request.message,
                    knowledge_base_id=request.knowledge_base_id,
                    top_k=3,
                )
                if rag_result.get("success") and rag_result.get("answer"):
                    rag_context = rag_result["answer"]
                    rag_sources = rag_result.get("sources", [])
                    yield f"data: {json.dumps({'type': 'rag_info', 'sources': rag_sources})}\n\n"
            except Exception as e:
                logger.warning(f"RAG query failed: {str(e)}")
        
        is_generate_test = is_test_generation_request(request.message)
        
        if not is_generate_test:
            system_prompt = """你是一个专业的AI测试助手，帮助用户解答关于软件测试、自动化测试、测试用例设计等问题。
你可以：
1. 解答测试相关的技术问题
2. 提供测试用例设计建议
3. 解释测试方法和最佳实践
4. 帮助分析测试需求

如果用户想要生成测试用例，请提示用户在消息中包含"生成测试用例"关键词。

请用简洁、专业的方式回答。"""
            
            user_message = request.message
            if rag_context:
                user_message = f"{request.message}\n\n【参考知识库内容】：\n{rag_context}"
            
            yield f"data: {json.dumps({'type': 'start'})}\n\n"

            # 同步 LLM 流式调用在独立线程中执行，事件循环不被占死
            # （修复：流式回答期间后端所有请求挂起、AI 助手假死不回复）
            stream_q = queue.Queue()

            def _llm_stream_producer():
                try:
                    for chunk in llm_service.call_llm_stream(
                        prompt=user_message,
                        system_prompt=system_prompt,
                        temperature=0.7
                    ):
                        if chunk:
                            stream_q.put(chunk)
                except Exception as e:  # 流式异常投递给前端，不静默挂起
                    stream_q.put(("__stream_error__", str(e)))
                finally:
                    stream_q.put(None)

            threading.Thread(target=_llm_stream_producer, daemon=True).start()
            while True:
                item = await asyncio.to_thread(stream_q.get)
                if item is None:
                    break
                if isinstance(item, tuple) and item and item[0] == "__stream_error__":
                    yield f"data: {json.dumps({'type': 'error', 'message': f'AI 服务调用失败: {item[1]}'})}\n\n"
                    return
                yield f"data: {json.dumps({'type': 'content', 'content': item})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'start_generate'})}\n\n"
            
            enhanced_message = request.message
            if rag_context:
                enhanced_message = f"{request.message}\n\n【参考知识库内容】：\n{rag_context}"
            
            yield f"data: {json.dumps({'type': 'info', 'content': '正在生成测试用例，请稍候...'})}\n\n"
            
            service = WebUITestService(db)
            
            result = await asyncio.to_thread(
                service.generate_from_chat,
                chat_message=enhanced_message,
                project_name="默认项目",
                base_url=request.base_url,
                browser=request.browser,
                viewport_size=request.viewport_size,
                headless=request.headless,
                generate_element_selectors=request.generate_element_selectors,
                generate_test_script=request.generate_test_script,
                script_type=request.script_type,
                script_language=request.script_language,
                current_user=current_user
            )
            
            test_cases_data = []
            for tc in (result.web_ui_test_cases or []):
                tc_dict = {
                    'id': str(tc.id) if hasattr(tc, 'id') else '',
                    'test_case_id': tc.test_case_id if hasattr(tc, 'test_case_id') else '',
                    'test_case': {},  # 手动查询 test_case 表
                    'base_url': tc.base_url if hasattr(tc, 'base_url') else '',
                    'browser': tc.browser if hasattr(tc, 'browser') else 'chromium',
                    'viewport_size': tc.viewport_size if hasattr(tc, 'viewport_size') else '1920x1080',
                    'headless': tc.headless if hasattr(tc, 'headless') else True,
                    'script_type': tc.script_type if hasattr(tc, 'script_type') else 'playwright',
                    'script_language': tc.script_language if hasattr(tc, 'script_language') else 'python',
                    'test_script': tc.test_script if hasattr(tc, 'test_script') else '',
                    'element_selectors': tc.element_selectors if hasattr(tc, 'element_selectors') else {},
                    'created_at': tc.created_at if hasattr(tc, 'created_at') else '',
                }
                test_cases_data.append(tc_dict)
            
            yield f"data: {json.dumps({'type': 'result', 'success': result.success, 'test_cases': test_cases_data, 'message': '生成完成'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


# ==================== OCR图像识别API ====================

from app.core.services.ocr_service import get_ocr_service

@router.post("/ocr/analyze")
async def analyze_image_ocr(
    images: List[UploadFile] = File(..., description="上传的图片文件"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    OCR图像识别 - 识别上传图片中的文本内容
    """
    if not images:
        raise HTTPException(status_code=400, detail="请至少上传一张图片")
    
    ocr_service = get_ocr_service('tesseract')
    combined_text = []
    results = []
    
    for idx, image in enumerate(images):
        try:
            image_data = await image.read()
            result = ocr_service.recognize_text(image_data)
            
            if result['success']:
                combined_text.append(f"【图片{idx + 1}】\n{result['text']}")
                results.append({
                    'index': idx + 1,
                    'filename': image.filename,
                    'success': True,
                    'text': result['text'][:500],
                    'full_length': len(result['text'])
                })
            else:
                results.append({
                    'index': idx + 1,
                    'filename': image.filename,
                    'success': False,
                    'error': result['error']
                })
        except Exception as e:
            logger.error(f"处理图片{idx + 1}失败: {str(e)}")
            results.append({
                'index': idx + 1,
                'filename': image.filename,
                'success': False,
                'error': str(e)
            })
    
    final_text = '\n\n'.join(combined_text)
    
    return {
        "success": len([r for r in results if r['success']]) > 0,
        "text": final_text,
        "total_images": len(images),
        "successful": len([r for r in results if r['success']]),
        "results": results
    }


@router.post("/generate-from-image")
async def generate_from_image(
    image_text: str = Body(..., description="OCR识别的图片文本"),
    base_url: str = Body(""),
    browser: str = Body("chromium"),
    viewport_size: str = Body("1920x1080"),
    headless: bool = Body(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    根据图片OCR文本生成测试用例
    """
    if not image_text or len(image_text.strip()) < 10:
        raise HTTPException(status_code=400, detail="识别文本太短，无法生成测试用例")
    
    try:
        llm_service = LLMService(db)
        
        prompt = f"""请根据以下从需求截图中识别出的内容，生成测试用例：

识别内容：
{image_text}

请生成结构化的测试用例，包括测试用例名称、测试步骤、预期结果、优先级等。
"""
        
        # 使用异步方法调用LLM
        llm_response = await llm_service.async_call_llm(
            prompt=prompt,
            system_prompt="你是一个专业的测试用例设计专家，擅长从需求文档中提取测试点并生成详细的测试用例。",
            temperature=0.3
        )
        
        if not llm_response:
            raise HTTPException(status_code=500, detail="LLM服务调用失败")
        
        return {
            "success": True,
            "count": 1,
            "text": image_text[:200],
            "generated": llm_response[:500],
            "message": "根据图片内容成功生成测试用例"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成测试用例失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")