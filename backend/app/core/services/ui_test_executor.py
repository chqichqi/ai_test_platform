"""
UI 测试统一执行引擎 — 支持浏览器隔离 / 复用两种模式。

模式说明：
- isolated: 每条用例启动独立浏览器 → 执行 → 关闭（默认，安全但慢）
- reuse:    同场景用例共享一个浏览器实例。
            V2 用例在同一 context 上开新 page；
            V1 用例通过 storage_state 文件桥接 session 状态。
            适用于需要登录态连续性的场景。
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logger import logger
from app.core.services.test_data_manager import TestDataManager


def _materialize_runtime_test_data(test_data: dict, case_id: str = ""):
    """执行阶段实例化 DataPlan；返回渲染后的 spec 与数据审计信息。"""
    from types import SimpleNamespace
    raw = test_data if isinstance(test_data, dict) else {}
    tc = SimpleNamespace(id=case_id, test_data=raw, logical_case_id=case_id, revision_no=1)
    manager = TestDataManager()
    plan = manager.build_plan(tc)
    dataset = manager.materialize(plan)

    def render_obj(obj):
        if isinstance(obj, dict):
            return {k: render_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [render_obj(v) for v in obj]
        return manager.render(obj, dataset.values) if isinstance(obj, str) else obj

    rendered = render_obj(raw)
    for req in plan.requirements:
        if req.data_type == "consumable":
            # 一个 Case Run 内实例唯一；真正是否被步骤消费由执行结果决定。
            pass
    return rendered, dataset, plan, manager
from app.core.services.execution_config import ExecutionConfig, BrowserMode
from app.core.services.allure_reporter import AllureReporter, AllureStatus


# ═══════════════════════════════════════════════════════════════
# V2 执行辅助
# ═══════════════════════════════════════════════════════════════

def _compile_pom_classes(page_objects: dict, page: Any) -> Dict[str, Any]:
    """动态编译 POM 类代码字符串 → 实例化对象"""
    instances = {}
    for class_name, code in (page_objects or {}).items():
        if not isinstance(code, str) or not code.strip():
            continue
        namespace: dict = {}
        try:
            exec(code, namespace)
        except Exception as e:
            logger.warning(f"[Executor] POM 类 {class_name} 编译失败: {e}")
            continue
        for name, obj in namespace.items():
            if name == class_name or (isinstance(obj, type) and name.lower() == class_name.lower()):
                try:
                    instances[name] = obj(page)
                except Exception as e:
                    logger.warning(f"[Executor] POM 类 {name} 实例化失败: {e}")
                break
    return instances


async def _run_v2_steps(page, test_data, page_objects, base_url, timeout_ms):
    """Async V2 执行（保留兼容）"""
    return _run_v2_steps_sync(page, test_data, page_objects, base_url, timeout_ms)


def _run_v2_steps_sync(
    page: Any,
    test_data: dict,
    page_objects: dict,
    base_url: str,
    timeout_ms: int,
    skip_goto: bool = False,
    case_id: str = "",
) -> dict:
    """在给定 sync page 上执行 V2 JSON 步骤（单用例便捷入口）。

    通用执行语义委托 run_parametrized_specs（pytest 参数化 + 反射 + 前置条件导航，
    与生成的 pytest 工程 test_runner.py 同源）：
      1. 用例步骤自带导航（goto 步骤 = 前置条件导航）→ 不预跳 base_url，按步骤执行；
      2. 无导航步骤（历史旧数据）→ 兜底 goto base_url（登录态由调用方保证）；
      3. 反射分发由 StepRunner._run_step 承担（action 名 → handler）。
    """
    from app.core.services.step_runner import run_parametrized_specs

    try:
        runtime_spec, dataset, plan, data_manager = _materialize_runtime_test_data(test_data, case_id)
        pom = _compile_pom_classes(page_objects or {}, page)
        results = run_parametrized_specs(
            [runtime_spec], page, pom, base_url, timeout_ms, skip_goto=skip_goto
        )
        result = results[0] if results else {"status": "error", "error": "无执行结果"}
        # 执行成功后，消费型数据只在本次实例上结束生命周期；默认不 DELETE 数据库。
        if result.get("success"):
            for req in plan.requirements:
                if req.data_type == "consumable":
                    data_manager.mark_consumed(dataset, req.key, {"case_id": case_id, "execution_status": result.get("status", "completed")})
        result["data_cleanup"] = data_manager.complete(dataset, plan)
        result["data_set_id"] = dataset.run_id
        result["runtime_test_data"] = dataset.values
        result["test_data_plan"] = plan.to_dict()
        return result
    except Exception as e:
        import traceback
        logger.error(f"[Execute] V2 执行异常: {e}\n{traceback.format_exc()}")
        return {"status": "error", "error": str(e), "steps_executed": 0}


def _run_v1_subprocess(test_script: str, storage_state_path: Optional[str] = None,
                       timeout_sec: float = 60) -> dict:
    """subprocess 执行 V1 脚本，可选注入 storage_state"""
    # 守卫：空脚本或 V2 占位脚本
    if not test_script or not test_script.strip():
        return {"status": "failed", "error": "测试脚本为空", "exit_code": -1}
    if 'POM + 数据驱动测试' in (test_script or ''):
        return {"status": "failed", "error": "V2 占位脚本不可执行，请使用 StepRunner 执行", "exit_code": -1}

    script = test_script
    if storage_state_path and os.path.exists(storage_state_path):
        inject = (
            f'import json, os\n'
            f'_storage_path = {json.dumps(storage_state_path)}\n'
            f'if os.path.exists(_storage_path):\n'
            f'    os.environ["STORAGE_STATE_PATH"] = _storage_path\n'
        )
        script = inject + "\n" + script

    script_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(script)
            script_path = f.name

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True,
            timeout=max(timeout_sec, 1),
            cwd=tempfile.gettempdir(),
        )
        return {
            "status": "completed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "console_errors": [result.stderr] if result.stderr else [],
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "console_errors": ["执行超时"]}
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# 统一执行器
# ═══════════════════════════════════════════════════════════════

class UITestExecutor:
    """UI 测试统一执行引擎"""

    def __init__(self, config: ExecutionConfig, allure: "AllureReporter" = None):
        self.config = config
        self.allure = allure
        self._browser = None
        self._context = None
        self._storage_state_path: Optional[str] = None

    # ═══════════════════════════════════════════════════════════
    # 公共入口
    # ═══════════════════════════════════════════════════════════

    async def execute_batch(
        self,
        test_cases: List[Any],
        progress_callback=None,
    ) -> List[dict]:
        """
        批量执行 UI 用例。

        Args:
            test_cases: WebUITestCase 对象列表
            progress_callback: 可选进度回调 fn(stage, message, index, total)

        Returns:
            每条用例的执行结果列表
        """
        if not test_cases:
            return []

        # 过滤登录模块用例（__login__，平台内部约定名）：其账号/密码的 value 注入在
        # 项目级 exploration_config（login_engine 负责），作为普通 UI 用例执行会因
        # fill 缺 value 失败（12:07 实证「系统登录」失败）；批量执行的登录阶段已完成登录。
        # 登录模块的验证由「导入并验证」/ login_engine 承担，不在此处普通执行。
        test_cases = [
            tc for tc in test_cases
            if (str(getattr(tc, 'test_case_id', None) or '') != '__login__')
        ]
        if not test_cases:
            return []

        if self.config.browser_mode == BrowserMode.REUSE:
            return await self._execute_reuse(test_cases, progress_callback)
        else:
            return await self._execute_isolated(test_cases, progress_callback)

    async def execute_single(self, test_case: Any) -> dict:
        """执行单条 UI 用例"""
        results = await self.execute_batch([test_case])
        return results[0] if results else {"status": "error", "error": "无结果"}

    # ═══════════════════════════════════════════════════════════
    # 隔离模式
    # ═══════════════════════════════════════════════════════════

    async def _execute_isolated(self, test_cases: List[Any],
                                progress_callback=None) -> List[dict]:
        """每条用例独立浏览器"""
        results = []
        total = len(test_cases)
        for i, tc in enumerate(test_cases):
            case_id = str(getattr(tc, 'id', ''))
            case_name = getattr(tc, 'test_case', {}).get('name', '') if hasattr(tc, 'test_case') else getattr(tc, 'id', 'unknown')
            module = getattr(tc, 'module', '') or '默认模块'

            if progress_callback:
                progress_callback("running", f"执行用例 {i+1}/{total}", i, total)

            # Allure: 开始用例
            if self.allure:
                self.allure.start_case(
                    case_id=case_id, name=str(case_name), module=str(module),
                    description=getattr(tc, 'description', '') or '',
                )

            case_config = self.config.merge_with_case(tc)
            result = await self._run_one_isolated(tc, case_config)
            result["index"] = i

            # Allure: 结束用例
            if self.allure:
                status = AllureStatus.PASSED if result.get("status") == "completed" else (
                    AllureStatus.FAILED if result.get("status") == "failed" else AllureStatus.BROKEN
                )
                self.allure.end_case(case_id, status, result.get("error", ""))
                # 失败截图
                if status != AllureStatus.PASSED and result.get("screenshot"):
                    self.allure.add_screenshot(case_id, result["screenshot"])

            results.append(result)

        return results

    async def _run_one_isolated(self, tc: Any, config: ExecutionConfig) -> dict:
        """隔离模式：在线程池中用同步 Playwright 执行，不依赖 asyncio 子进程"""
        mode = getattr(tc, 'generation_mode', None) or 'linear'
        base_url = getattr(tc, 'base_url', 'http://localhost:3000')
        test_data = getattr(tc, 'test_data', {})
        page_objects = getattr(tc, 'page_objects', {})
        test_script = getattr(tc, 'test_script', '')
        case_id = str(getattr(tc, 'id', ''))

        # 加载登录态（从 KG auth_data）
        storage_state = self._load_auth_state(tc)

        def _run_sync():
            from playwright.sync_api import sync_playwright
            import time as _time
            _start = _time.time()
            _pw = None
            _browser = None
            _state_path = None
            try:
                _pw = sync_playwright().start()
                _browser = _pw.chromium.launch(headless=config.headless)
                _ctx_kwargs = {"viewport": {"width": config.viewport_width, "height": config.viewport_height}}
                if storage_state:
                    _ctx_kwargs["storage_state"] = storage_state
                _ctx = _browser.new_context(**_ctx_kwargs)
                _page = _ctx.new_page()

                # 导航到 base_url，检测是否被重定向到登录页
                _page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
                _page.wait_for_timeout(500)
                _cur = _page.url
                if '/login' in _cur or '/auth' in _cur:
                    return {"status": "error", "error": "登录态过期，请使用批量执行(有头+复用)"}

                if mode == "pom_data_driven":
                    _result = _run_v2_steps_sync(
                        _page, test_data, page_objects, base_url, config.timeout_ms, skip_goto=True, case_id=str(getattr(tc, 'id', ''))
                    )
                else:
                    _state_path = _ctx.storage_state()
                    _result = _run_v1_subprocess(test_script, _state_path, config.timeout_ms / 1000)
                _ctx.close()
            except Exception as e:
                _result = {"status": "error", "error": str(e)}
            finally:
                if _browser:
                    try: _browser.close()
                    except Exception: pass
                if _pw:
                    try: _pw.stop()
                    except Exception: pass
            _result["test_case_id"] = case_id
            _result["generation_mode"] = mode
            _result["duration_ms"] = int((_time.time() - _start) * 1000)
            _result["browser_mode"] = "isolated"
            return _result

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_sync)

    # ═══════════════════════════════════════════════════════════
    # 登录（复用探索时的 LoginEngine，保证登录逻辑一致）
    # ═══════════════════════════════════════════════════════════

    def _login_fresh(self, base_url: str, project_id: int = None) -> tuple:
        """用 LoginEngine 重新登录（与探索一致，含机构选择），返回 (storage_state, workbench_url)

        注意：此方法在 ThreadPoolExecutor 线程中调用，必须创建独立的 event loop。
        不能在子线程中调用 asyncio.run()（它只能从主线程调用）。
        """
        import sys, json as _json, asyncio as _aio
        from concurrent.futures import ThreadPoolExecutor as _TPE
        try:
            from app.core.database import SessionLocal
            from app.core.models.project_ext import ProjectSetting
            from app.core.models.knowledge_graph import KnowledgeGraph

            db = SessionLocal()
            try:
                _kgq = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.exploration_status == 'completed'
                )
                if project_id:
                    _kgq = _kgq.filter(KnowledgeGraph.project_id == project_id)
                kg = _kgq.order_by(KnowledgeGraph.completed_at.desc()).first()
                if not kg or not kg.login_username:
                    return None, None
                username = kg.login_username
                psetting = db.query(ProjectSetting).filter(
                    ProjectSetting.project_id == kg.project_id
                ).first() if kg and kg.project_id else None
                web_cfg = (psetting.exploration_config or {}).get('web', {}) if psetting else {}
                password = web_cfg.get('password', '')
                if not password:
                    return None, None
            finally:
                db.close()

            async def _do_login():
                from playwright.async_api import async_playwright
                from app.core.services.login_engine import login_with_ui_case
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=True)
                    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
                    page = await ctx.new_page()
                    ok, wb_url = await login_with_ui_case(page, base_url, username, password, project_id=project_id)
                    if not ok:
                        await browser.close()
                        return None, None
                    state = await ctx.storage_state()
                    await browser.close()
                    return _json.loads(_json.dumps(state, ensure_ascii=False)), wb_url

            # thread-safe: 每个线程创建自己的 event loop
            # 不调用 set_event_loop_policy() —— 那是全局操作，会在 FastAPI 主线程
            # 已有运行中 event loop 时抛 "Cannot run the event loop while another loop is running"
            try:
                _loop = _aio.get_running_loop()
            except RuntimeError:
                _loop = None

            if _loop is not None:
                # 当前线程已有运行中的 event loop，在新线程中执行
                result_holder = []
                def _run_in_new_thread():
                    _inner = _aio.new_event_loop()
                    try:
                        _aio.set_event_loop(_inner)
                        result_holder.append(_inner.run_until_complete(_do_login()))
                    finally:
                        _inner.close()
                import threading
                t = threading.Thread(target=_run_in_new_thread)
                t.start()
                t.join()
                return result_holder[0] if result_holder else (None, None)
            else:
                # 当前线程无运行中的 event loop，直接创建新的
                _loop = _aio.new_event_loop()
                try:
                    _aio.set_event_loop(_loop)
                    return _loop.run_until_complete(_do_login())
                finally:
                    _loop.close()
        except Exception as e:
            logger.warning(f"[Execute] 重新登录失败: {e}")
            return None, None

    def _login_sync_visible(self, page, ctx, base_url: str, project_id: int = None) -> tuple:
        """在可见同步浏览器中执行登录（用户能看到整个过程）。

        严格按照导入登录模块时生成的 __login__ UI 用例步骤来执行登录：
        1. 从 DB 加载 __login__ 测试用例的 steps（项目隔离）
        2. 设置 $username / $password 变量
        3. 通过 StepRunner 执行步骤
        4. 返回 storage_state 用于后续用例执行
        """
        import json as _json
        try:
            from app.core.database import SessionLocal
            from app.core.models.project_ext import ProjectSetting
            from app.core.models.knowledge_graph import KnowledgeGraph
            from app.core.models.web_ui_test import WebUITestCase
            from app.core.services.step_runner import StepRunner

            db = SessionLocal()
            try:
                _kgq = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.exploration_status == 'completed'
                )
                if project_id:
                    _kgq = _kgq.filter(KnowledgeGraph.project_id == project_id)
                kg = _kgq.order_by(KnowledgeGraph.completed_at.desc()).first()
                if not kg or not kg.login_username:
                    logger.warning("[Execute] KG 无登录凭据")
                    return None, None
                username = kg.login_username
                psetting = db.query(ProjectSetting).filter(
                    ProjectSetting.project_id == kg.project_id
                ).first() if kg and kg.project_id else None
                web_cfg = (psetting.exploration_config or {}).get('web', {}) if psetting else {}
                password = web_cfg.get('password', '')
                if not password:
                    logger.warning("[Execute] 未配置密码")
                    return None, None

                # 加载 __login__ UI 用例的测试步骤（项目隔离）
                _q = db.query(WebUITestCase).filter(
                    WebUITestCase.test_case_id == '__login__'
                )
                if project_id:
                    _q = _q.filter(WebUITestCase.project_id == str(project_id))
                login_case = _q.first()
                login_steps = []
                if login_case and login_case.test_data:
                    td = login_case.test_data
                    if isinstance(td, str):
                        td = _json.loads(td)
                    login_steps = td.get('steps', []) if isinstance(td, dict) else []
                if not login_steps:
                    logger.warning("[Execute] __login__ 用例无步骤，回退硬编码登录")
                    return self._login_fallback(page, ctx, base_url, username, password)
            finally:
                db.close()

            if not base_url:
                base_url = (psetting.exploration_config or {}).get('web', {}).get('base_url', '') if psetting else ''
            if not base_url:
                logger.warning("[Execute] 未配置 base_url")
                return None, None

            logger.info(f"[Execute] 按 __login__ 步骤执行登录（{len(login_steps)}步）: goto {base_url}")
            page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1500)

            cur_url = page.url or ''
            # 如果已在工作台（没被重定向到登录页），说明已有有效 session
            if '/login' not in cur_url and '/auth' not in cur_url:
                logger.info(f"[Execute] 已有有效 session: {cur_url[:60]}")
                state = ctx.storage_state()
                return _json.loads(_json.dumps(state)), cur_url

            # 用 StepRunner 执行 __login__ 步骤
            logger.info(f"[Execute] 执行 __login__ 步骤，user={username}")
            runner = StepRunner(page, {})
            runner.set_var('username', username)
            runner.set_var('password', password)
            # 过滤 goto 步骤：导航登录页已由上方手动 goto base_url 完成；seq5「点击登录后回 base_url」
            # 的残留 goto 会把页面重新导航回登录页，破坏登录流程（真实场景：点击登录后回到 #/login）。
            # 与 import 时 _verify_steps 过滤 goto、login_engine 跳过后续 goto 三路径同源（RULES.md 二.6/7）。
            result = runner.run(
                [s for s in login_steps if (s.get('action') or '').strip() != 'goto']
            )

            if not result.get('success'):
                logger.warning(f"[Execute] __login__ 步骤执行失败: {result.get('error')}")
                # 回退硬编码登录
                return self._login_fallback(page, ctx, base_url, username, password)

            state = ctx.storage_state()
            wb_url = page.url or ''
            logger.info(f"[Execute] __login__ 步骤登录完成: {wb_url[:80]}")
            return _json.loads(_json.dumps(state)), wb_url

        except Exception as e:
            logger.warning(f"[Execute] 可见登录失败: {e}")
            return None, None

    def _login_fallback(self, page, ctx, base_url, username, password) -> tuple:
        """硬编码回退登录——当 __login__ 步骤不可用时的最后手段。"""
        import json as _json
        try:
            logger.info(f"[Execute] 回退硬编码登录: user={username}")
            # 如果不在登录页，尝试导航到 base_url
            cur = page.url or ''
            if '/login' not in cur and '/auth' not in cur:
                page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)

            # 填写手机号
            try:
                page.fill('input[placeholder*="手机号"], input[placeholder*="用户名"], '
                          'input[name="username"], input[type="text"]:not([placeholder*="密码"])',
                          username, timeout=5000)
            except Exception:
                page.fill('input:not([type="password"]):not([type="hidden"]):not([type="submit"])',
                          username, timeout=5000)
            page.wait_for_timeout(300)

            # 密码
            page.fill('input[placeholder*="密码"], input[type="password"]', password, timeout=5000)
            page.wait_for_timeout(300)

            # 登录按钮
            for btn_text in ('登 录', '登录', 'Sign in', 'Login'):
                try:
                    btn = page.get_by_text(btn_text, exact=False).first
                    if btn.is_visible():
                        btn.click(timeout=5000)
                        break
                except Exception:
                    continue

            page.wait_for_timeout(3000)

            # 机构选择
            if 'selectOrganization' in (page.url or ''):
                try:
                    cards = page.locator('.org-card, .ant-card, [class*="org"]')
                    if cards.count() > 0:
                        cards.first.click(timeout=3000)
                        page.wait_for_timeout(500)
                        page.get_by_text('确定', exact=False).first.click(timeout=3000)
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

            state = ctx.storage_state()
            return _json.loads(_json.dumps(state)), page.url or ''
        except Exception as e:
            logger.warning(f"[Execute] 回退登录也失败: {e}")
            return None, None

    def _load_auth_state(self, tc) -> dict | None:
        """从 KnowledgeGraph 加载登录态 storage_state（项目隔离：只取本项目 KG）"""
        _pid = None
        try:
            _pid = getattr(tc, 'project_id', None) or None
        except Exception:
            _pid = None
        try:
            from app.core.database import SessionLocal
            from app.core.models.knowledge_graph import KnowledgeGraph
            db = SessionLocal()
            try:
                _q = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.exploration_status == 'completed'
                )
                if _pid:
                    _q = _q.filter(KnowledgeGraph.project_id == _pid)
                kg = _q.order_by(KnowledgeGraph.completed_at.desc()).first()
                if kg and kg.auth_data and isinstance(kg.auth_data, dict):
                    logger.info(f"[Execute] 加载登录态 (KG #{kg.id})")
                    return kg.auth_data
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[Execute] 加载登录态失败: {e}")
        return None

    def _save_auth_state(self, project_id, storage_state) -> None:
        """登录成功后把最新 storage_state 写回本项目 KG auth_data（供下次执行复用）

        与 _load_auth_state 同源：同为「本项目最新完成的 KG 行」。
        应用会话过期后策略1校验会失败 → 自动重新可见登录 → 再回写，循环自洽。
        """
        if not storage_state:
            return
        try:
            from app.core.database import SessionLocal
            from app.core.models.knowledge_graph import KnowledgeGraph
            db = SessionLocal()
            try:
                _q = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.exploration_status == 'completed'
                )
                if project_id:
                    _q = _q.filter(KnowledgeGraph.project_id == project_id)
                kg = _q.order_by(KnowledgeGraph.completed_at.desc()).first()
                if kg:
                    kg.auth_data = storage_state
                    db.commit()
                    logger.info(f"[Execute] 登录态已回写 KG #{kg.id}（下次执行复用）")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[Execute] 登录态回写失败: {e}")

    # ═══════════════════════════════════════════════════════════
    # 复用模式
    # ═══════════════════════════════════════════════════════════

    async def _execute_reuse(self, test_cases: List[Any],
                             progress_callback=None) -> List[dict]:
        """有头+复用模式：浏览器开一次 → 登录 → 依次执行全部用例 → 关闭"""
        # 项目隔离：从用例推导 project_id，加载本项目登录态
        storage_state = self._load_auth_state(test_cases[0] if test_cases else None)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._run_batch_reuse_sync(test_cases, storage_state, self.config)
        )

    def _run_batch_reuse_sync(self, test_cases, storage_state, config) -> List[dict]:
        """同步执行：单浏览器 + 单次登录 + 多用例"""
        from playwright.sync_api import sync_playwright

        if not test_cases:
            return []
        base_url = getattr(test_cases[0], 'base_url', '') or ''
        _pid = None
        try:
            _pid = getattr(test_cases[0], 'project_id', None) or None
        except Exception:
            _pid = None

        results = []
        _pw = None
        _browser = None
        try:
            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch(headless=config.headless)
            ctx_kwargs = {"viewport": {"width": config.viewport_width, "height": config.viewport_height}}
            if storage_state:
                ctx_kwargs["storage_state"] = storage_state
            _ctx = _browser.new_context(**ctx_kwargs)
            _page = _ctx.new_page()

            # ── 登录：优先用已保存的 storage_state，否则在可见浏览器中执行登录 ──
            logger.info("[ExecuteBatch] 检查登录态...")
            fresh_state = None
            wb_url = ''

            # 策略1: storage_state 已加载 → 直接验证（导航到 base_url 看是否被重定向到登录页）
            if storage_state:
                from app.core.services.step_runner import _looks_like_login_url as _is_login
                try:
                    _page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
                    _page.wait_for_timeout(500)
                    _cur = _page.url or ''
                    if not _is_login(_cur):
                        logger.info("[ExecuteBatch] storage_state 有效，跳过重登录")
                        fresh_state = storage_state
                        wb_url = _cur
                    else:
                        logger.info("[ExecuteBatch] storage_state 已过期，需要重新登录")
                except Exception as _g:
                    # 目标系统瞬时导航超时/网络波动（11:33 实证：goto 15s 超时整批中止）：
                    # 不整批失败，回退策略2 用项目级登录模块在可见浏览器重新登录；重登录失败才报错。
                    logger.warning(f"[ExecuteBatch] storage_state 验证导航超时({_g})，回退可见浏览器重新登录")
                    fresh_state = None

            # 策略2: 在可见浏览器中执行登录
            if not fresh_state:
                logger.info("[ExecuteBatch] 开始可见浏览器登录...")
                fresh_state, wb_url = self._login_sync_visible(
                    _page, _ctx, base_url, project_id=_pid
                )

            if not fresh_state:
                _ctx.close()
                return [{"status": "error", "error": "登录失败——请确认已导入登录模块且项目URL/账号密码配置正确"} for _ in test_cases]

            # 登录态回写 KG auth_data（下次执行优先复用；应用会话过期后会自动重新登录）
            self._save_auth_state(_pid, fresh_state)

            # ── 单窗口会话：登录成功 → 同窗口立即执行（不关闭浏览器重开）──
            # 08-13 设计：登录完成后不关浏览器，同一 page 直接执行用例；
            # 用例各自的导航步骤（goto 首步/兜底 base_url）负责进入目标页面。
            if wb_url:
                base_url = wb_url
            logger.info("[ExecuteBatch] 登录成功，开始执行用例")

            # ── 逐条执行 ──
            for i, tc in enumerate(test_cases):
                mode = getattr(tc, 'generation_mode', None) or 'linear'
                td = getattr(tc, 'test_data', {})
                po = getattr(tc, 'page_objects', {})
                ts = getattr(tc, 'test_script', '')
                cid = str(getattr(tc, 'id', ''))
                case_name = (td.get('title', '') if isinstance(td, dict) else '') or cid[:8]

                logger.info(f"[ExecuteBatch] {i+1}/{len(test_cases)}: {case_name}")

                # ── 浏览器存活自愈 ──
                # 可见浏览器被外部关闭（用户关窗/浏览器崩溃）时，用已保存的最新
                # 登录态重开浏览器继续执行，不整批空跑（21:17 批量执行实证：
                # 浏览器关闭后剩余 58 条全部 TargetClosedError 空跑）。
                try:
                    _browser_dead = _page.is_closed()
                except Exception:
                    _browser_dead = True
                if _browser_dead:
                    logger.warning(f"[ExecuteBatch] 浏览器已关闭，自愈重启（第 {i+1}/{len(test_cases)} 条继续）")
                    _pw, _browser, _ctx, _page, fresh_state, _wb = self._relaunch_browser(
                        _pw, _browser, _ctx, _page, fresh_state, base_url, config, _pid
                    )
                    if not fresh_state:
                        logger.error("[ExecuteBatch] 自愈失败：重新登录失败，中止批量")
                        for j in range(i, len(test_cases)):
                            cj = str(getattr(test_cases[j], 'id', ''))
                            results.append({"status": "error",
                                            "error": "浏览器关闭且重新登录失败（批量中止）",
                                            "test_case_id": cj, "browser_mode": "reuse"})
                        break
                    base_url = _wb or base_url
                    logger.info(f"[ExecuteBatch] 自愈完成，继续执行（base_url={base_url[:60]}）")

                _start = time.time()
                try:
                    if mode == "pom_data_driven":
                        # 通用执行：用例自带前置条件导航（test_data.preconditions +
                        # 步骤中的 goto/navigate 步骤）→ 直接按用例执行；
                        # 无导航步骤的旧用例由 _run_v2_steps_sync 兜底跳 base_url。
                        # 不依赖知识图谱复位——用例自身的步骤就是它的前置条件导航。
                        r = _run_v2_steps_sync(_page, td, po, base_url, config.timeout_ms, case_id=cid)
                    else:
                        r = _run_v1_subprocess(ts, None, config.timeout_ms / 1000)
                except Exception as e:
                    r = {"status": "error", "error": str(e)}
                r["test_case_id"] = cid
                r["duration_ms"] = int((time.time() - _start) * 1000)
                r["browser_mode"] = "reuse"
                results.append(r)

            _ctx.close()
            ok = sum(1 for r in results if r.get("status") == "completed")
            logger.info(f"[ExecuteBatch] 完成: {ok}/{len(results)} 成功, errors: {[r.get('error','')[:60] for r in results if r.get('status')!='completed'][:5]}")
        except Exception as e:
            import traceback
            logger.error(f"[ExecuteBatch] 异常: {e}\n{traceback.format_exc()}")
            results.append({"status": "error", "error": str(e), "browser_mode": "reuse"})
        finally:
            if _browser:
                try: _browser.close()
                except Exception: pass
            if _pw:
                try: _pw.stop()
                except Exception: pass
        return results

    def _relaunch_browser(self, pw, browser, ctx, page, fresh_state, base_url, config,
                          project_id):
        """浏览器/上下文被外部关闭后自愈重启（批量执行中途）。

        清理旧实例 → 带最新登录态（storage_state）重开 → 导航 base_url 验证：
        - 未重定向到登录页 → 登录态有效，直接继续；
        - 已过期 → 重新可见登录（__login__ 步骤自动执行）并回写 KG。
        返回 (pw, browser, ctx, page, fresh_state, wb_url)；登录失败 fresh_state=None。
        """
        from playwright.sync_api import sync_playwright
        from app.core.services.step_runner import _looks_like_login_url as _is_login

        for _old in (page, ctx, browser, pw):
            if _old is None:
                continue
            try:
                if hasattr(_old, "stop"):
                    _old.stop()
                else:
                    _old.close()
            except Exception:
                pass

        _pw = None
        try:
            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch(headless=config.headless)
            _kw = {"viewport": {"width": config.viewport_width, "height": config.viewport_height}}
            if fresh_state:
                _kw["storage_state"] = fresh_state
            _ctx = _browser.new_context(**_kw)
            _page = _ctx.new_page()
            _page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
            _page.wait_for_timeout(1000)
            _cur = _page.url or ''
            if not _is_login(_cur):
                logger.info("[ExecuteBatch] 自愈：登录态仍有效，直接继续")
                return _pw, _browser, _ctx, _page, fresh_state, _cur
            logger.info("[ExecuteBatch] 自愈：登录态已过期，重新可见登录")
            fresh_state, wb_url = self._login_sync_visible(
                _page, _ctx, base_url, project_id=project_id
            )
            if not fresh_state:
                return _pw, _browser, _ctx, _page, None, ''
            self._save_auth_state(project_id, fresh_state)
            return _pw, _browser, _ctx, _page, fresh_state, wb_url
        except Exception as e:
            logger.error(f"[ExecuteBatch] 自愈失败: {e}")
            if _pw:
                try: _pw.stop()
                except Exception: pass
            return None, None, None, None, None, ''

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    async def _save_storage_state(self, context) -> Optional[str]:
        """导出 context 的 storage_state 到临时文件，跟踪以便清理"""
        try:
            state = await context.storage_state()
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False, encoding='utf-8'
            ) as f:
                path = f.name
                json.dump(state, f)
            if not hasattr(self, '_temp_files'):
                self._temp_files = []
            self._temp_files.append(path)
            return path
        except Exception as e:
            logger.warning(f"[Executor] storage_state 导出失败: {e}")
            return None

    @staticmethod
    def _cleanup_file(path: str):
        """清理单个临时文件"""
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass

    def cleanup(self):
        """清理所有临时文件"""
        for path in getattr(self, '_temp_files', []):
            self._cleanup_file(path)
        self._temp_files = []


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

async def execute_ui_tests(
    test_cases: List[Any],
    config: Optional[ExecutionConfig] = None,
    progress_callback=None,
) -> List[dict]:
    """便捷函数：一键执行"""
    cfg = config or ExecutionConfig()
    executor = UITestExecutor(cfg)
    try:
        return await executor.execute_batch(test_cases, progress_callback)
    finally:
        executor.cleanup()
