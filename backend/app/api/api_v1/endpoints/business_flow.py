"""
业务流 → UI 用例 API 端点

POST /versions/{version_id}/generate-ui-from-business-flow
  - 解析业务流文本 → 按需探索 → 生成 UI 用例
"""

import json, asyncio, time
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logger import logger
from app.core.models.project import Version
from app.core.services.business_flow_ui_service import BusinessFlowUIService

router = APIRouter()


def _require_login_module(db: Session, project_id: int = None) -> None:
    """检查登录模块是否已导入（按项目校验）；未导入则拒绝"""
    from app.core.models.web_ui_test import WebUITestCase
    from app.core.models.requirement import RequirementDocument
    from app.core.models.project import Version

    _login_q = db.query(WebUITestCase).filter(
        WebUITestCase.test_case_id == '__login__',
        WebUITestCase.deleted_at.is_(None)
    )
    if project_id:
        _login_q = _login_q.filter(WebUITestCase.project_id == str(project_id))
    login = _login_q.first()
    if not login:
        raise HTTPException(
            status_code=400,
            detail="请先导入登录模块：在「项目配置 → 登录模块」中导入登录流程后再进行操作"
        )
    ts = (login.test_script or '').strip()
    if not ts or ts.startswith('#'):
        raise HTTPException(
            status_code=400,
            detail="登录模块未完成配置（步骤为空），请重新导入登录模块"
        )

    if project_id:
        login_doc = db.query(RequirementDocument).join(
            Version, RequirementDocument.version_id == Version.id
        ).filter(
            Version.project_id == project_id,
            RequirementDocument.type == 'business_flow',
            RequirementDocument.name == '登录模块',
            RequirementDocument.content != '',
            RequirementDocument.status != 'pending',
        ).first()
        if not login_doc:
            raise HTTPException(
                status_code=400,
                detail="请先在「项目配置 → 登录模块」中导入并验证登录流程后再进行操作"
            )

# ── 进度存储（内存，单进程） ──
_explore_progress: dict = {}


class BusinessFlowGenerateRequest(BaseModel):
    """业务流生成 UI 用例请求"""
    business_flow_text: str = Field(..., description="业务流文本描述")
    base_url: str = Field(..., description="目标系统 URL")
    username: str = Field(..., description="登录用户名")
    password: str = Field(..., description="登录密码")
    force_explore: bool = Field(default=False, description="是否强制重新探索（忽略缓存）")
    headless: bool = Field(default=False, description="无头模式（默认有头，可见浏览器）")
    exploration_strategy: str = Field(default="normal", description="探索策略: quick/normal/deep")
    debug_skip_explore: bool = Field(default=False, description="调试：跳过探索，仅返回 CoT 提取结果")


class BusinessFlowGenerateResponse(BaseModel):
    """业务流生成 UI 用例响应"""
    success: bool
    ui_cases: list = []
    ui_cases_count: int = 0
    saved_case_ids: list = []  # [(simple_test_case_id, web_ui_test_case_id), ...]
    explored_modules: list = []
    cached_modules: list = []
    elapsed_seconds: float = 0
    error: Optional[str] = None


@router.post("/generate-ui-from-business-flow/{version_id}")
async def generate_ui_from_business_flow(
    version_id: int,
    request: BusinessFlowGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    从业务流文本生成 UI 测试用例

    流程:
    1. 解析业务流 → 提取模块和所需元素
    2. 检查 KnowledgeGraph 探索缓存
    3. 缺失模块 → 自动触发 BFS 探索
    4. 探索结果 → LLM 生成 UI 用例
    5. 保存到 WebUITestCase 表

    与 generateAssets 的区别:
    - 不生成功能测试用例
    - 先探索页面再生成 UI 用例
    - 探索缓存可复用
    """
    # 获取版本和项目
    version = db.query(Version).filter(Version.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本 {version_id} 不存在")

    project = version.project
    if not project:
        raise HTTPException(status_code=404, detail="关联项目不存在")

    _require_login_module(db, project.id)

    if not request.business_flow_text.strip():
        raise HTTPException(status_code=400, detail="业务流文本不能为空")

    if not request.base_url.strip():
        raise HTTPException(status_code=400, detail="目标系统 URL 不能为空")

    logger.info(
        f"[API] 业务流UI生成: version={version_id}, project={project.id}, "
        f"text_len={len(request.business_flow_text)}, force={request.force_explore}"
    )

    try:
        # 进度追踪 key
        progress_key = f"{project.id}:{version_id}"
        _explore_progress[progress_key] = {"stage": "starting", "message": "正在启动...", "progress": 0, "total": 0}

        def on_progress(p: dict):
            _explore_progress[progress_key] = p

        service = BusinessFlowUIService(db)
        result = await service.generate(
            version_id=version_id,
            business_flow_text=request.business_flow_text,
            project_id=project.id,
            base_url=request.base_url,
            username=request.username,
            password=request.password,
            force_explore=request.force_explore,
            headless=request.headless,
            progress_callback=on_progress,
            debug_skip_explore=request.debug_skip_explore,
        )

        _explore_progress.pop(progress_key, None)
        return result

    except Exception as e:
        logger.error(f"[API] 业务流UI生成异常: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.get("/explore-progress/{project_id}/{version_id}")
def get_explore_progress(project_id: int, version_id: int):
    """轮询探索进度"""
    key = f"{project_id}:{version_id}"
    return _explore_progress.get(key, {"stage": "idle", "message": "无进行中的任务", "progress": 0, "total": 0})


class ImportLoginModuleRequest(BaseModel):
    version_id: int = Field(..., description="版本ID")
    login_content: str = Field(default="", description="登录模块业务流内容（用户手工编辑后传入）")


@router.post("/import-login-module")
async def import_login_module(
    request: ImportLoginModuleRequest,
    db: Session = Depends(get_db),
):
    """
    导入登录模块（专用——验证成功才保存业务流文档）：
    1. 有头探索 + 生成 UI 用例（__login__）
    2. 立即执行 __login__ 验证登录
    3. 成功 → 保存登录模块业务流文档
    4. 失败 → 不保存，返回错误，用户可修改重试
    """
    from app.core.models.project import Version
    from app.core.models.requirement import RequirementDocument
    from app.core.services.step_parser import parse_steps

    version = db.query(Version).filter(Version.id == request.version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本 {request.version_id} 不存在")
    project = version.project
    if not project:
        raise HTTPException(status_code=404, detail="关联项目不存在")

    login_content = request.login_content.strip()
    if not login_content:
        # 没传内容 → 尝试读已有文档
        login_doc = db.query(RequirementDocument).filter(
            RequirementDocument.version_id == request.version_id,
            RequirementDocument.type == 'business_flow',
            RequirementDocument.name == '登录模块'
        ).first()
        if login_doc:
            login_content = (login_doc.content or '').strip()
    if not login_content:
        raise HTTPException(status_code=400, detail="请填写登录模块的业务流描述")

    # 前置检查：根据项目类型验证必要配置
    from app.core.models.project_ext import ProjectSetting
    psetting = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project.id
    ).first()
    _ec = (psetting.exploration_config or {}) if psetting else {}
    _pt = (project.project_type or 'web').lower()

    if _pt == 'app':
        _cfg = _ec.get('app', {})
        if not _cfg.get('apk_package'):
            raise HTTPException(status_code=400, detail="请先在「项目设置 → APP 配置」中上传 APK 安装包后再导入登录模块")
        if not _cfg.get('username'):
            raise HTTPException(status_code=400, detail="请先在「项目设置 → 探索配置」中配置登录用户名后再导入登录模块")
        if not _cfg.get('password'):
            raise HTTPException(status_code=400, detail="请先在「项目设置 → 探索配置」中配置登录密码后再导入登录模块")
    else:
        _cfg = _ec.get('web', {})
        # 解析有效的 base_url：优先用 base_url 字段，为空时回退到 active_environment 对应环境的 URL
        _effective_base_url = _cfg.get('base_url', '') or ''
        if not _effective_base_url:
            _envs = _cfg.get('environments') or []
            _active_env = _cfg.get('active_environment') or ''
            if isinstance(_envs, list) and _active_env:
                _matched = [e for e in _envs if isinstance(e, dict) and e.get('name') == _active_env]
                if _matched:
                    _effective_base_url = _matched[0].get('url', '') or ''
        if not _effective_base_url:
            raise HTTPException(status_code=400, detail="请先在「项目设置 → 探索配置」中配置目标系统 URL（base_url）后再导入登录模块")
        if not _cfg.get('username'):
            raise HTTPException(status_code=400, detail="请先在「项目设置 → 探索配置」中配置登录用户名（username）后再导入登录模块")
        if not _cfg.get('password'):
            raise HTTPException(status_code=400, detail="请先在「项目设置 → 探索配置」中配置登录密码（password）后再导入登录模块")

    # 内容校验：必须包含登录相关描述（防止用户误导入非登录模块的业务流）
    # 业务词参数化：关键词从 exploration_config.explore 段可覆盖（build_web_exploration_config）
    from app.core.services.exploration_config import build_web_exploration_config
    _login_keywords = build_web_exploration_config(_ec).login_flow_keywords.split(',')
    _login_keywords = [kw.strip() for kw in _login_keywords if kw.strip()]
    _content_lower = login_content.lower()
    if not any(kw in _content_lower for kw in _login_keywords):
        raise HTTPException(
            status_code=400,
            detail="导入内容未检测到登录相关业务流描述，请确认并重新导入。"
        )

    try:
        from app.core.services.functional_to_ui_service import FunctionalToUIService
        service = FunctionalToUIService(db)

        result = await service.import_login_module(
            version_id=request.version_id,
            login_content=login_content,
            project_id=project.id,
        )

        # 成功 → 保存/更新业务流文档
        if result.get("success"):
            from app.core.models.requirement import RequirementDocument, DocumentType
            existing_doc = db.query(RequirementDocument).filter(
                RequirementDocument.version_id == request.version_id,
                RequirementDocument.type == 'business_flow',
                RequirementDocument.name == '登录模块'
            ).first()
            if existing_doc:
                existing_doc.content = login_content
            else:
                new_doc = RequirementDocument(
                    version_id=request.version_id,
                    name='登录模块',
                    type='business_flow',
                    content=login_content,
                    status='parsed'
                )
                db.add(new_doc)
            db.commit()
            logger.info(f"[import-login-module] 登录模块验证成功，已保存业务流文档")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[import-login-module] 失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"登录模块导入失败: {str(e)}")


class ExploreWorkbenchRequest(BaseModel):
    module_name: str = Field(default="患者档案", description="要探索的模块名")
    headless: bool = Field(default=False, description="无头模式")


@router.post("/explore-workbench/{version_id}")
async def explore_workbench(
    version_id: int,
    request: ExploreWorkbenchRequest,
    db: Session = Depends(get_db),
):
    """
    [DEPRECATED - 内部调试用] 纯 BFS 探索：打开浏览器 → 登录 → 探索指定模块 → 返回原始元素清单。

    此端点已由步骤驱动探索替代。前端不再调用此端点。
    新的探索流程集成在 /web-ui-tests/convert-from-functional 中：
    测试用例步骤 → StepParser → GuidedExplorationAgent → KGPopulator → V2 转化。

    保留此端点仅用于内部调试和向后兼容。
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    project = version.project
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 读项目配置
    from app.core.models.project_ext import ProjectSetting

    psetting = db.query(ProjectSetting).filter(ProjectSetting.project_id == project.id).first()
    web_cfg = (psetting.exploration_config or {}).get("web", {}) if psetting else {}
    # 多环境支持
    base_url = web_cfg.get("base_url", "")
    if not base_url and web_cfg.get("environments"):
        envs = web_cfg.get("environments", [])
        active = web_cfg.get("active_environment", "")
        env = next((e for e in envs if e.get("name") == active), envs[0] if envs else None)
        if env: base_url = env.get("url", "")
    username = web_cfg.get("username", "")
    password = web_cfg.get("password", "")

    if not base_url:
        raise HTTPException(status_code=400, detail="请先在项目设置中配置目标系统 URL")

    def _do_explore():
        """Windows: 必须用 ProactorEventLoop 才能跑 Playwright async"""
        import asyncio as _aio
        _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
        _loop = _aio.new_event_loop()
        _aio.set_event_loop(_loop)
        return _loop.run_until_complete(_login_and_explore())

    async def _login_and_explore():
        """V4: async 登录 (LoginEngine) → 导出 storage_state → sync 探索"""
        from playwright.async_api import async_playwright
        from app.core.services.login_engine import LoginEngine, login_config_from_settings

        progress_key = f"{project.id}:{version_id}"

        # ── Step 1: LoginEngine 登录（async，完整流程含机构选择）──
        _explore_progress[progress_key] = {"stage": "login", "message": "正在登录...", "progress": 5, "total": 0}

        login_cfg = login_config_from_settings(psetting.exploration_config if psetting else None)
        storage_state_str = None
        workbench_url = base_url

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=request.headless,
                args=["--start-maximized"] if not request.headless else [],
            )
            ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
            page = await ctx.new_page()
            engine = LoginEngine(page, login_cfg)
            ok = await engine.login(base_url, username, password)
            workbench_url = page.url

            # ── 硬校验：如果还在 login / switchorganization 页，登录未真正完成 ──
            if "login" in workbench_url.lower() or "switchorganization" in workbench_url.lower():
                logger.warning(f"[API] LoginEngine returned ok but URL still on auth page: {workbench_url}")
                # 再等 5 秒，看是否会跳转
                await asyncio.sleep(5)
                workbench_url = page.url
                if "login" in workbench_url.lower() or "switchorganization" in workbench_url.lower():
                    await browser.close()
                    _explore_progress[progress_key] = {"stage": "error", "message": f"登录后未能进入工作台: {workbench_url}", "progress": 0, "total": 0}
                    return {"error": f"登录后未能进入工作台，当前页: {workbench_url}"}

            if not ok and ("login" in workbench_url.lower() or "switchorganization" in workbench_url.lower()):
                await browser.close()
                _explore_progress[progress_key] = {"stage": "error", "message": "登录失败", "progress": 0, "total": 0}
                return {"error": "登录失败", "current_url": page.url}

            logger.info(f"[API] LoginEngine OK: {workbench_url}")

            # 导出登录态（cookies + localStorage），供 sync 浏览器复用
            state = await page.context.storage_state()
            import json as _json
            storage_state_str = _json.dumps(state, ensure_ascii=False)
            await browser.close()

        # ── Step 2: sync Playwright + 加载登录态 + DFS 探索（线程池避免阻塞事件循环）──
        _explore_progress[progress_key] = {"stage": "exploring", "message": "正在探索页面...", "progress": 20, "total": 0}
        import concurrent.futures as _cf
        import asyncio as _aio
        with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
            _loop = _aio.get_event_loop()
            return await _loop.run_in_executor(
                _pool, _do_explore_sync, workbench_url, storage_state_str, progress_key
            )

    def _resolve_hash_url(base_url, href):
        """将相对 hash href 解析为完整 URL。如 '#/device/list' → 'http://x/#/device/list'"""
        if not href:
            return ""
        if href.startswith("http://") or href.startswith("https://"):
            return href
        # hash 路由
        if href.startswith("#"):
            return base_url.split("#")[0] + href
        # 相对路径
        if href.startswith("/"):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        return base_url.rstrip("/") + "/" + href.lstrip("/")

    def _dump_menu_dom(page, parent_name):
        """诊断：dump 父菜单的完整 DOM 树，保存到文件。"""
        import os, json as _json, time as _time
        try:
            info = page.evaluate("""
                (parentName) => {
                    // 找 parentName 文本元素
                    let bestEl = null, bestLen = Infinity;
                    document.querySelectorAll('*').forEach(el => {
                        if (el.children.length > 5) return;
                        const t = (el.textContent || '').trim();
                        if (t === parentName && t.length < bestLen) {
                            bestEl = el; bestLen = t.length;
                        }
                    });
                    if (!bestEl) return {found: false};

                    // 往上找到 <li> 容器（不是 submenu-title div——那样会漏掉子菜单）
                    const li = bestEl.closest('li');
                    const ul = bestEl.closest('ul');

                    // 递归 dump 整个 <ul> 树
                    const dumpNode = (el, depth) => {
                        if (depth > 8 || !el) return null;
                        const node = {
                            tag: el.tagName,
                            cls: (el.className || '').toString().substring(0, 100),
                            text: (el.textContent || '').trim().substring(0, 50),
                            href: el.getAttribute('href') || '',
                            role: el.getAttribute('role') || '',
                            visible: el.offsetParent !== null,
                            rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                            children: []
                        };
                        if (depth < 6) {
                            for (const child of el.children) {
                                const c = dumpNode(child, depth + 1);
                                if (c) node.children.push(c);
                            }
                        }
                        return node;
                    };

                    return {
                        found: true,
                        parentTag: bestEl.tagName,
                        liTag: li ? li.tagName + '.' + (li.className||'').substring(0,60) : 'null',
                        ulTag: ul ? ul.tagName + '.' + (ul.className||'').substring(0,60) : 'null',
                        tree: ul ? dumpNode(ul, 0) : (li ? dumpNode(li, 0) : null),
                    };
                }
            """, parent_name) or {}

            # 保存到文件
            _explore_dir = os.path.abspath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..", "tests", "exploration"))
            os.makedirs(_explore_dir, exist_ok=True)
            _ts = _time.strftime("%Y%m%d_%H%M%S")
            _dump_file = os.path.join(_explore_dir, f"dom_dump_{parent_name}_{_ts}.json")
            with open(_dump_file, 'w', encoding='utf-8') as f:
                _json.dump(info, f, ensure_ascii=False, indent=2)
            logger.info(f"[API] DOM tree saved: {_dump_file}")

            # 简要日志
            logger.info(f"[API] Menu DOM for '{parent_name}': found={info.get('found')}, "
                        f"li={info.get('liTag','?')}, ul={info.get('ulTag','?')}")
            return info
        except Exception as e:
            logger.warning(f"[API] DOM dump failed: {e}")
            return {}

    def _collect_sub_menus(page, parent_name, sidebar_max_x=280, submenu_xcluster_gap=18, submenu_y_sanity=400, submenu_dedup_y=6):
        """通用子菜单收集 — 混合算法：X坐标聚类 + DOM子树回退。
        Phase A 和 Phase B 独立容错，一个失败不影响另一个。
        """
        items_a = []
        items_b = []

        # ═══════════════════════════════════════════════════════
        # Phase A: X 坐标聚类
        # ═══════════════════════════════════════════════════════
        try:
            items_a = page.evaluate("""
                (params) => {
                    const parentName = params.parentName;
                    const sidebarMaxX = params.sidebarMaxX;
                    const xclusterGap = params.xclusterGap;
                    const ySanity = params.ySanity;
                    const dedupY = params.dedupY;
                    // Step 1: 收集侧边栏所有叶子节点
                    const allItems = [];
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_ELEMENT, null, false
                    );
                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        if (el.offsetParent === null) continue;
                        const text = (el.textContent || '').trim();
                        if (!text || text.length < 2 || text.length > 30) continue;
                        if (el.children.length > 0) {
                            let childTexts = '';
                            for (const c of el.children) {
                                childTexts += (c.textContent || '').trim();
                            }
                            const tag = el.tagName.toLowerCase();
                            const isLeafTag = ['a', 'button', 'span', 'label'].includes(tag);
                            if (childTexts === text && !isLeafTag) continue;
                        }

                        const rect = el.getBoundingClientRect();
                        if (rect.x > sidebarMaxX || rect.width < 10) continue;

                        let href = el.getAttribute('href') || '';
                        if (!href) {
                            const a = el.closest('a[href]') || el.querySelector('a[href]');
                            if (a) href = a.getAttribute('href') || '';
                        }

                        allItems.push({
                            text, href,
                            y: Math.round(rect.y),
                            x: Math.round(rect.x),
                        });
                    }

                    // Step 2: 排序 + 去重
                    allItems.sort((a, b) => a.y - b.y || a.x - b.x);
                    const uniqueItems = [];
                    for (const item of allItems) {
                        const last = uniqueItems[uniqueItems.length - 1];
                        if (last && Math.abs(item.y - last.y) < dedupY && item.text === last.text) continue;
                        uniqueItems.push(item);
                    }

                    // Step 3: X 坐标聚类
                    const xValues = [...new Set(uniqueItems.map(it => it.x))].sort((a,b) => a-b);
                    const xClusters = [];
                    for (const x of xValues) {
                        const last = xClusters[xClusters.length - 1];
                        if (last === undefined || x - last > xclusterGap) {
                            xClusters.push(x);
                        }
                    }
                    for (const item of uniqueItems) {
                        for (let lvl = 0; lvl < xClusters.length; lvl++) {
                            if (Math.abs(item.x - xClusters[lvl]) <= xclusterGap) {
                                item.indent = lvl;
                                break;
                            }
                        }
                        if (item.indent === undefined) item.indent = 0;
                    }

                    // Step 4: 找到 parent
                    let parentIdx = -1, parentY = 0;
                    for (let i = 0; i < uniqueItems.length; i++) {
                        if (uniqueItems[i].text === parentName) {
                            parentIdx = i; parentY = uniqueItems[i].y; break;
                        }
                    }
                    if (parentIdx < 0) return [];

                    const parentIndent = uniqueItems[parentIdx].indent;

                    // Step 5: 收集子项
                    const subItems = [];
                    for (let i = parentIdx + 1; i < uniqueItems.length; i++) {
                        const item = uniqueItems[i];
                        if (item.indent <= parentIndent) break;
                        if (item.y - parentY > ySanity) break;
                        if (item.indent === parentIndent + 1) {
                            subItems.push({name: item.text, href: item.href, source: 'xcluster'});
                        }
                    }
                    return subItems;
                }
            """, {"parentName": parent_name, "sidebarMaxX": sidebar_max_x, "xclusterGap": submenu_xcluster_gap, "ySanity": submenu_y_sanity, "dedupY": submenu_dedup_y}) or []
        except Exception as e:
            logger.warning(f"[API] Phase A (xcluster) failed: {e}")

        # ═══════════════════════════════════════════════════════
        # Phase B: DOM 子树扫描（独立容错）
        # Phase B: DOM 树遍历 — 带诊断日志
        # ═══════════════════════════════════════════════════════
        try:
            raw_b = page.evaluate("""
                (parentName) => {
                    const dbg = [];
                    // Step 1: 找到 parent
                    const allEls = document.querySelectorAll('*');
                    let parentEl = null;
                    for (const el of allEls) {
                        if ((el.textContent || '').trim() === parentName &&
                            el.children.length <= 2 && el.offsetParent !== null) {
                            parentEl = el; break;
                        }
                    }
                    if (!parentEl) { return {items: [], dbg: ['parentEl not found']}; }
                    dbg.push('parentEl: ' + parentEl.tagName);
                    const pr = parentEl.getBoundingClientRect();

                    // Step 2: 往上走，看能走到哪
                    const liContainer = parentEl.closest('li');
                    const ulContainer = parentEl.closest('ul');
                    dbg.push('closest(li): ' + (liContainer ? liContainer.tagName + '.' + (liContainer.className||'').substring(0,40) : 'null'));
                    dbg.push('closest(ul): ' + (ulContainer ? ulContainer.tagName + '.' + (ulContainer.className||'').substring(0,40) : 'null'));

                    // Step 3: 直接用整个 sidebar ul 找所有 li
                    const sidebarUl = parentEl.closest('[role="menu"]') || ulContainer;
                    if (!sidebarUl) { return {items: [], dbg: ['sidebarUl not found']}; }
                    const allLis = sidebarUl.querySelectorAll('li');
                    dbg.push('total li in sidebar: ' + allLis.length);

                    // Step 4: 收集 parent 下方可见的 li
                    const results = [];
                    const seen = new Set();
                    for (const li of allLis) {
                        if (li.offsetParent === null) { dbg.push('hidden: ' + (li.textContent||'').trim().substring(0,20)); continue; }
                        const r = li.getBoundingClientRect();
                        if (r.y <= pr.y) continue;
                        if (r.y - pr.y > 400) continue;
                        const text = (li.textContent || '').trim();
                        if (!text || text.length < 2 || text.length > 30) continue;
                        if (text === parentName) continue;
                        if (seen.has(text)) continue;
                        seen.add(text);
                        let href = '';
                        const a = li.querySelector('a[href]');
                        if (a) href = a.getAttribute('href') || '';
                        dbg.push('found: ' + text + ' href=' + href.substring(0,30) + ' y=' + r.y);
                        results.push({name: text, href: href, source: 'dom'});
                    }
                    if (results.length === 0) dbg.push('no results after filters');
                    return {items: results, dbg: dbg};
                }
            """, parent_name) or {}
            if isinstance(raw_b, dict):
                items_b = raw_b.get('items', [])
                dbg = raw_b.get('dbg', [])
                if dbg:
                    logger.info(f"[API] PhaseB debug: {' | '.join(str(d) for d in dbg)}")
            else:
                items_b = raw_b or []
        except Exception as e:
            logger.warning(f"[API] Phase B (DOM scan) failed: {e}")

        # ═══════════════════════════════════════════════════════
        # 合并：Phase A + Phase B，按 name 去重
        # ═══════════════════════════════════════════════════════
        seen_names = set()
        merged = []
        # Phase B (DOM scan) 直接找真实 a[href]——不合并 Phase A X 聚类
        for it in items_b:
            n = it.get('name', '')
            if n and n not in seen_names:
                seen_names.add(n)
                merged.append(it)

        logger.info(f"[API] Sub-menus: PhaseA={len(items_a)} {[i.get('name','') for i in items_a[:10]]}, "
                    f"PhaseB={len(items_b)} {[i.get('name','') for i in items_b[:10]]}, "
                    f"merged={len(merged)}")
        return merged

    def _wait_spa_render(page, min_len=200, max_rounds=10, interval=800):
        """等待 SPA 渲染完成：轮询 body 文本长度直到稳定。返回是否就绪。"""
        last_len = 0
        for _ in range(max_rounds):
            page.wait_for_timeout(interval)
            try:
                cur_len = page.evaluate("() => document.body ? document.body.innerText.length : 0")
            except Exception:
                cur_len = 0
            if cur_len >= min_len and cur_len == last_len:
                return True
            last_len = cur_len
        return False

    def _do_explore_sync(workbench_url, storage_state_str, progress_key):
        """V5 sync 探索：加载已登录的 storage_state，执行 DFS。

        父菜单（可展开/收起）→ 收集所有子菜单，每个子菜单作为独立模块逐一探索。
        普通模块 / 工作台 → 直接探索。
        """
        from playwright.sync_api import sync_playwright
        from app.core.services.mcp_client import MCPClient
        from app.core.services.exploration_config import WebExplorationConfig
        from app.core.services.mcp_exploration_agent import MCPExplorationAgent
        import json as _json

        pw = None
        browser = None

        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                headless=request.headless,
                args=["--start-maximized"] if not request.headless else [],
            )

            state = _json.loads(storage_state_str) if storage_state_str else None
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                storage_state=state,
            )
            page = ctx.new_page()
            page.goto(workbench_url, wait_until="domcontentloaded", timeout=15000)

            logger.info(f"[API] waiting for SPA render...")
            _wait_spa_render(page, min_len=200, max_rounds=15, interval=1000)
            logger.info(f"[API] sync browser ready at: {page.url}")

            # ═══════════════════════════════════════════════════════
            # 确定探索目标模块列表
            # ═══════════════════════════════════════════════════════
            modules_to_explore = []  # [(module_name, start_url, click_text_or_none), ...]

            if request.module_name in ("工作台", ""):
                modules_to_explore = [(request.module_name, page.url, None)]
            else:
                logger.info(f"[API] navigating to module: {request.module_name}...")
                before_url = page.url

                # 多策略点击父菜单（展开子菜单或跳转）
                clicked = False
                try:
                    page.get_by_text(request.module_name, exact=False).first.click(timeout=5000)
                    clicked = True
                except Exception:
                    pass

                if not clicked:
                    # 策略2：JS TreeWalker 精确定位并点击
                    try:
                        clicked = page.evaluate("""
                            (text) => {
                                const walker = document.createTreeWalker(
                                    document.body, NodeFilter.SHOW_ELEMENT, null, false
                                );
                                let bestEl = null, bestLen = Infinity;
                                while (walker.nextNode()) {
                                    const el = walker.currentNode;
                                    if (el.offsetParent === null) continue;
                                    if (el.children.length > 2) continue;
                                    const t = (el.textContent || '').trim();
                                    if (t === text && t.length < bestLen) {
                                        bestEl = el; bestLen = t.length;
                                    }
                                }
                                if (bestEl) {
                                    // 点击最外层的可点击容器
                                    const target = bestEl.closest('li') ||
                                                   bestEl.closest('[onclick]') ||
                                                   bestEl.closest('[class*="menu-item"]') ||
                                                   bestEl.closest('[class*="submenu-title"]') ||
                                                   bestEl;
                                    target.scrollIntoView({block: 'center', behavior: 'instant'});
                                    target.click();
                                    return true;
                                }
                                return false;
                            }
                        """, request.module_name)
                    except Exception:
                        pass

                page.wait_for_timeout(3000)

                if page.url != before_url:
                    # 直接跳转 → 单模块
                    modules_to_explore = [(request.module_name, page.url, None)]
                else:
                    # 父菜单（可展开/收起，不跳转）→ 验证展开状态 → 收集子菜单
                    logger.info(f"[API] '{request.module_name}' is a parent menu, verifying expansion...")
                    # 诊断：Dump 父菜单 DOM 结构
                    _dump_menu_dom(page, request.module_name)

                    # 验证子菜单是否真的展开了（父项下方可见的链接数 > 0）
                    expanded_check = page.evaluate("""
                        (parentName) => {
                            const walker = document.createTreeWalker(
                                document.body, NodeFilter.SHOW_ELEMENT, null, false
                            );
                            let parentEl = null;
                            while (walker.nextNode()) {
                                const el = walker.currentNode;
                                if ((el.textContent || '').trim() === parentName &&
                                    el.children.length <= 2 && el.offsetParent !== null) {
                                    parentEl = el; break;
                                }
                            }
                            if (!parentEl) return -1;
                            const pr = parentEl.getBoundingClientRect();
                            // 统计父项下方 400px 内可见的 <a> 链接
                            let count = 0;
                            const allVisible = document.querySelectorAll('*');
                            for (const el of allVisible) {
                                if (el.offsetParent === null) continue;
                                const r = el.getBoundingClientRect();
                                if (r.width < 30 || r.height < 10) continue;
                                if (r.y > pr.y && r.y - pr.y < 400 && r.x < 400) {
                                    count++; break;
                                }
                            }
                            return count;
                        }
                    """, request.module_name)
                    logger.info(f"[API] Expanded check: {expanded_check} visible elements below parent")

                    # 如果没展开，尝试点击箭头图标
                    if not expanded_check or expanded_check <= 0:
                        logger.info(f"[API] Menu not expanded, clicking submenu-title...")
                        try:
                            page.evaluate("""
                                (parentName) => {
                                    const walker = document.createTreeWalker(
                                        document.body, NodeFilter.SHOW_ELEMENT, null, false
                                    );
                                    while (walker.nextNode()) {
                                        const el = walker.currentNode;
                                        if ((el.textContent || '').trim() === parentName) {
                                            const title = el.closest('[class*="submenu-title"]');
                                            if (title) { title.click(); return true; }
                                        }
                                    }
                                    return false;
                                }
                            """, request.module_name)
                            page.wait_for_timeout(2000)
                        except Exception:
                            pass

                                        # 从 config 读取子菜单参数（零硬编码）
                    sidebar_max_x = web_cfg.get('sidebar_max_x', 280)
                    submenu_xcluster_gap = web_cfg.get('submenu_xcluster_gap', 18)
                    submenu_y_sanity = web_cfg.get('submenu_parent_y_sanity', 400)
                    submenu_dedup_y = web_cfg.get('submenu_dedup_y_tolerance', 6)
                    sub_menus = _collect_sub_menus(page, request.module_name, sidebar_max_x, submenu_xcluster_gap, submenu_y_sanity, submenu_dedup_y)

                    if sub_menus:
                        logger.info(f"[API] Found {len(sub_menus)} sub-menus: {[s['name'] for s in sub_menus]}")
                        for sm in sub_menus:
                            sm_name = sm["name"]
                            sm_href = sm.get("href", "")
                            sm_url = _resolve_hash_url(workbench_url, sm_href) if sm_href else ""
                            modules_to_explore.append((
                                f"{request.module_name}-{sm_name}",
                                sm_url,
                                sm_name,
                            ))
                    else:
                        logger.warning(f"[API] No sub-menus found for '{request.module_name}' — "
                                       f"menu structure may not match expected patterns. "
                                       f"Try selecting a specific sub-menu module directly.")
                        _explore_progress[progress_key] = {
                            "stage": "error",
                            "message": f"未找到「{request.module_name}」的子菜单，请直接选择子模块探索",
                            "progress": 0, "total": 0,
                        }
                        return {"error": f"No sub-menus found under '{request.module_name}'"}

            logger.info(f"[API] Modules to explore ({len(modules_to_explore)}): {[m[0] for m in modules_to_explore]}")

            # ═══════════════════════════════════════════════════════
            # 逐个探索每个模块
            # ═══════════════════════════════════════════════════════
            from app.core.services.llm_service import LLMService

            all_results = []           # [{module, result, url}, ...]
            all_explored = []          # 扁平化的探索元素列表
            all_pages_visited = []
            total_stats = {"total_elements": 0, "navigated_elements": 0, "pages_explored": 0,
                           "elapsed_seconds": 0, "errors": 0}
            combined_site_map = {"modules": []}
            combined_element_jumps = {}
            combined_deep_dive = {"dropdowns": {}, "modals": [], "tables": [],
                                  "pagination": [], "forms": [], "api_endpoints": []}
            combined_module_docs = []
            combined_site_map_md = []
            combined_page_object_code = []
            combined_state_graph = []  # V6: 汇总状态图

            for idx, (mod_name, mod_url, click_text) in enumerate(modules_to_explore):
                _explore_progress[progress_key] = {
                    "stage": "exploring",
                    "message": f"正在探索 [{idx+1}/{len(modules_to_explore)}]: {mod_name}",
                    "progress": 20 + int(60 * (idx + 1) / max(len(modules_to_explore), 1)),
                    "total": len(modules_to_explore),
                }

                # 导航到子模块页面
                if mod_url:
                    page.goto(mod_url, wait_until="domcontentloaded", timeout=15000)
                    _wait_spa_render(page, min_len=100, max_rounds=10, interval=800)
                elif click_text:
                    # 现场重新扫描+点击（不依赖预收集的文本，DOM 可能已变）
                    clicked = page.evaluate("""
                        (text) => {
                            const walker = document.createTreeWalker(
                                document.body, NodeFilter.SHOW_ELEMENT, null, false
                            );
                            let bestEl = null, bestLen = Infinity;
                            while (walker.nextNode()) {
                                const el = walker.currentNode;
                                if (el.children.length > 1) continue;
                                if (el.offsetParent === null) continue;
                                const t = (el.textContent || '').trim();
                                if (t === text && t.length < bestLen) {
                                    bestEl = el; bestLen = t.length;
                                }
                            }
                            if (bestEl) {
                                let clickTarget = bestEl.closest('li') ||
                                                  bestEl.closest('[class*="menu-item"]') ||
                                                  bestEl.closest('[onclick]') ||
                                                  bestEl;
                                clickTarget.scrollIntoView({block: 'center', behavior: 'instant'});
                                clickTarget.click();
                                return true;
                            }
                            return false;
                        }
                    """, click_text)
                    if clicked:
                        page.wait_for_timeout(3000)
                    else:
                        logger.warning(f"[API] Cannot navigate to sub-menu '{click_text}', skipping")
                        continue

                logger.info(f"[API] Exploring module [{idx+1}/{len(modules_to_explore)}]: '{mod_name}' at {page.url}")

                # 创建独立的探索 agent（数据库配置覆盖默认值——零硬编码）
                client = MCPClient(page)
                config = WebExplorationConfig()
                # 从数据库 web_cfg 注入项目特定关键词（既有白名单，向后兼容）
                for key in ('noise_keywords', 'danger_keywords', 'modal_trigger_keywords',
                            'search_button_keywords', 'form_fill_values'):
                    if key in web_cfg and web_cfg[key]:
                        setattr(config, key, web_cfg[key])
                # explore 段全量覆盖（任意配置字段可定制，换项目不改代码）
                config.apply_overrides((psetting.exploration_config or {}).get("explore") or {})
                llm_service = None
                try:
                    llm_service = LLMService(db)
                except Exception:
                    pass
                agent = MCPExplorationAgent(client, config, llm_service, module_name=mod_name)

                result = agent.explore()
                all_results.append({"module": mod_name, "result": result, "url": page.url})

                # ── 汇总 explored 元素 ──
                for pd in result.get("element_jumps", {}).values():
                    if isinstance(pd, dict):
                        for el in pd.get("elements", []):
                            all_explored.append({
                                "name": f"[{mod_name}] {el.get('name', '')}",
                                "interaction_type": "navigation" if el.get("navigated") else "static",
                                "navigated": el.get("navigated", False),
                            })

                all_pages_visited.extend(result.get("pages_visited", []))

                # ── 汇总 stats ──
                stats = result.get("stats", {})
                for k in total_stats:
                    total_stats[k] += stats.get(k, 0)

                # ── 汇总 site_map（标注来源模块）──
                combined_site_map["modules"].extend(
                    {"name": f"[{mod_name}] {m['name']}", "href": m.get("href", ""), "source": m.get("source", "")}
                    for m in result.get("site_map", {}).get("modules", [])
                )

                # ── 汇总 element_jumps ──
                combined_element_jumps[mod_name] = result.get("element_jumps", {}).get("_main", {})

                # ── 汇总 deep_dive ──
                dd = result.get("deep_dive", {})
                for dk in combined_deep_dive:
                    if isinstance(combined_deep_dive[dk], dict):
                        combined_deep_dive[dk].update(dd.get(dk, {}))
                    elif isinstance(combined_deep_dive[dk], list):
                        combined_deep_dive[dk].extend(dd.get(dk, []))

                # ── 汇总 LLM 文档 ──
                if result.get("module_docs"):
                    combined_module_docs.append(f"## {mod_name}\n\n{result['module_docs']}")
                if result.get("site_map_md"):
                    combined_site_map_md.append(f"## {mod_name}\n\n{result['site_map_md']}")
                if result.get("page_object_code"):
                    combined_page_object_code.append(f"# {mod_name}\n{result['page_object_code']}")

                # ── 汇总状态图（标注来源模块）──
                for sg in result.get("state_graph", []):
                    sg["_module"] = mod_name
                    combined_state_graph.append(sg)

                # ── 返回工作台准备下一个子菜单 ──
                if idx < len(modules_to_explore) - 1:
                    logger.info(f"[API] Returning to workbench for next sub-menu...")
                    # 强制刷新页面（避免 SPA 状态残留导致菜单 toggle）
                    page.evaluate("() => location.reload()")
                    _wait_spa_render(page, min_len=100, max_rounds=10, interval=800)
                    # 重新展开父菜单——检查展开状态，避免 toggle
                    if request.module_name not in ("工作台", ""):
                        parent_li = page.evaluate(f"""
                            (name) => {{
                                const all = document.querySelectorAll('*');
                                for (const el of all) {{
                                    if ((el.textContent||'').trim() === name && el.children.length <= 2) {{
                                        const li = el.closest('li');
                                        if (li) {{
                                            const sub = li.querySelector('ul');
                                            const expanded = sub && sub.offsetParent !== null;
                                            return expanded ? 'expanded' : 'collapsed';
                                        }}
                                    }}
                                }}
                                return 'not_found';
                            }}
                        """, request.module_name)
                        logger.info(f"[API] Parent menu state: {parent_li}")
                        if parent_li == 'collapsed':
                            try:
                                page.get_by_text(request.module_name, exact=False).first.click(timeout=5000)
                                page.wait_for_timeout(2000)
                            except Exception:
                                pass

            # ═══════════════════════════════════════════════════════
            # 汇总并保存结果
            # ═══════════════════════════════════════════════════════
            _explore_progress[progress_key] = {"stage": "done", "message": "探索完成", "progress": 100, "total": 0}

            import os
            _explore_dir = os.path.abspath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..", "tests", "exploration"))
            os.makedirs(_explore_dir, exist_ok=True)

            # 跳转摘要（按父模块命名）
            import re as _re
            _safe_module = _re.sub(r'[\\/:*?"<>|]', '_', request.module_name)
            _summary_file = os.path.join(_explore_dir, f"{_safe_module}-jump-summary.json")
            with open(_summary_file, 'w', encoding='utf-8') as f:
                _json.dump({
                    "parent_module": request.module_name,
                    "sub_modules": [r["module"] for r in all_results],
                    "element_jumps": {k: v for k, v in combined_element_jumps.items()},
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"[API] 跳转摘要: {_summary_file}")

            # 完整探索结果
            _ts = time.strftime("%Y%m%d_%H%M%S")
            _result_file = os.path.join(_explore_dir, f"explore_full_{_ts}.json")
            with open(_result_file, 'w', encoding='utf-8') as f:
                _json.dump({
                    "module": request.module_name,
                    "sub_modules": [{"name": r["module"], "url": r["url"]} for r in all_results],
                    "base_url": base_url,
                    "pages_visited": all_pages_visited,
                    "explored": all_explored,
                    "stats": total_stats,
                    "site_map": combined_site_map,
                    "element_jumps": combined_element_jumps,
                    "deep_dive": combined_deep_dive,
                    "state_graph": combined_state_graph,
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"[API] 完整结果: {_result_file}")

            # LLM 文档（合并所有子模块）
            for key, ext, combined in [
                ("module_docs", "md", combined_module_docs),
                ("site_map_md", "md", combined_site_map_md),
                ("page_object_code", "py", combined_page_object_code),
            ]:
                if combined:
                    doc_file = os.path.join(_explore_dir, f"{_safe_module}_{key}.{ext}")
                    with open(doc_file, 'w', encoding='utf-8') as f:
                        f.write("\n\n".join(combined))

            return {
                "module": request.module_name,
                "sub_modules": [r["module"] for r in all_results],
                "base_url": base_url,
                "mcp_driven": True,
                "pages_visited": all_pages_visited,
                "explored": all_explored,
                "stats": total_stats,
                "site_map": combined_site_map,
                "element_jumps": combined_element_jumps,
                "deep_dive": combined_deep_dive,
                "state_graph": combined_state_graph,  # V6
                "module_docs": "\n\n".join(combined_module_docs),
                "site_map_md": "\n\n".join(combined_site_map_md),
                "page_object_code": "\n\n".join(combined_page_object_code),
                "result_file": _result_file,
            }

        except Exception as e:
            logger.error(f"[API] V4 explore error: {e}")
            _explore_progress[progress_key] = {"stage": "error", "message": str(e), "progress": 0, "total": 0}
            return {"error": str(e)}
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return await asyncio.get_event_loop().run_in_executor(pool, _do_explore)
