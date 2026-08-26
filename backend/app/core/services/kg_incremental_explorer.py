"""
需求变更审批后的增量探索器

需求变更（added/modified）审批通过后，后台异步探索受影响模块，
将结果 merge 进项目唯一 KnowledgeGraph——知识图谱随需求变更实时更新。

关键设计（与全站 BFS 管线并发仲裁一致）：
- 自开 SessionLocal 会话（禁止使用请求级 db——审批请求已结束）
- 项目 KG 若 running → 全站探索进行中，跳过增量探索
- KGPopulator.populate(replace_mode='merge')：只叠加新模块数据，不动旧数据
- 整体 try/except 降级：失败仅 warning，不影响审批结果
"""

import logging
from datetime import datetime
from typing import List, Optional

from app.core.logger import logger
from app.core.database import SessionLocal
from app.core.models.knowledge_graph import KnowledgeGraph
from app.core.models.project import Version
from app.core.models.project_ext import ProjectSetting


async def explore_affected_modules(version_id: int, module_names: List[str]) -> bool:
    """审批通过后，探索受影响模块并 merge 进项目 KG。

    Args:
        version_id: 版本 ID（用于定位项目 + 记录 KG 最近来源版本）
        module_names: 受影响模块名列表（已按 change_type 过滤 added/modified）

    Returns:
        True=增量探索成功完成；False=跳过或失败（不影响审批）
    """
    if not module_names:
        return False

    db = SessionLocal()
    try:
        # 1. 版本 → 项目
        version = db.query(Version).filter(Version.id == version_id).first()
        if not version:
            logger.warning(f"[KGIncremental] 版本{version_id}不存在，跳过增量探索")
            return False
        project_id = version.project_id

        # 2. 读项目探索配置（零硬编码：base_url/username/password 全部来自项目设置）
        psetting = db.query(ProjectSetting).filter(
            ProjectSetting.project_id == project_id
        ).first()
        _ec = (psetting.exploration_config or {}) if psetting else {}
        _cfg = _ec.get('web', {})
        base_url = _cfg.get('base_url', '') or ''
        if not base_url:
            _envs = _cfg.get('environments') or []
            _active_env = _cfg.get('active_environment') or ''
            if isinstance(_envs, list) and _active_env:
                _matched = [e for e in _envs
                            if isinstance(e, dict) and e.get('name') == _active_env]
                if _matched:
                    base_url = _matched[0].get('url', '') or ''
        username = _cfg.get('username', '') or ''
        password = _cfg.get('password', '') or ''

        if not base_url or not username or not password:
            logger.warning(
                f"[KGIncremental] 项目{project_id}未配置 base_url/username/password，跳过增量探索")
            return False

        # 3. 并发仲裁：项目 KG running → 全站探索进行中，跳过增量探索
        kg = db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
        ).first()
        if kg and kg.exploration_status == 'running':
            logger.info(f"[KGIncremental] 项目{project_id}全站探索进行中，跳过增量探索")
            return False

        # 4. 起浏览器 → __login__ 用例登录 → 逐模块 BFS 探索 → merge 进项目 KG
        from playwright.async_api import async_playwright
        from app.core.services.exploration_config import build_web_exploration_config
        from app.core.services.bfs_explorer import BFSExplorer
        from app.core.services.login_engine import login_with_ui_case
        from app.core.services.kg_populator import KGPopulator

        explore_cfg = build_web_exploration_config(_ec)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-gpu"],
            )
            try:
                ctx = await browser.new_context(
                    viewport={"width": explore_cfg.viewport_width,
                              "height": explore_cfg.viewport_height},
                )
                page = await ctx.new_page()

                login_ok, workbench_url = await login_with_ui_case(
                    page, base_url, username, password, project_id=project_id
                )
                if not login_ok or not workbench_url:
                    logger.warning(f"[KGIncremental] 项目{project_id}登录失败，跳过增量探索")
                    return False

                # 登录态：浏览器 storage_state（后续执行/探索直接复用登录态）
                import json as _json
                auth_state = None
                try:
                    auth_state = _json.loads(_json.dumps(await page.context.storage_state()))
                except Exception:
                    pass

                explorer = BFSExplorer(page, base_url, explore_cfg)
                populator = KGPopulator(db)
                explored_modules = []
                for module_name in module_names:
                    try:
                        result = await explorer.explore_module(module_name)
                        if not result or result.get("error"):
                            logger.warning(
                                f"[KGIncremental] 模块 '{module_name}' 探索无结果，跳过")
                            continue
                        explored_modules.append(module_name)
                        populator.populate(
                            project_id=project_id,
                            version_id=version_id,
                            module_name=module_name,
                            exploration_result={
                                'pages_visited': [
                                    p for p in result.get('pages', []) if isinstance(p, str)
                                ],
                                'site_map': {
                                    'modules': [{
                                        'name': module_name, 'href': '',
                                        'source': 'incremental',
                                    }],
                                },
                                'deep_dive': {
                                    'dropdowns': result.get('filter_options', {}) or {},
                                    'modals': result.get('modals', []) or [],
                                },
                            },
                            base_url=base_url,
                            username=username,
                            auth_data=auth_state,
                            replace_mode='merge',
                            explored_modules=explored_modules,
                        )
                    except Exception as e:
                        logger.warning(
                            f"[KGIncremental] 模块 '{module_name}' 增量探索失败: {e}")

                logger.info(
                    f"[KGIncremental] 审批后增量探索完成：项目{project_id}，"
                    f"版本{version_id}，成功 {len(explored_modules)}/{len(module_names)} 个模块")
                return bool(explored_modules)
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[KGIncremental] 增量探索整体失败（不影响审批）: {e}")
        return False
    finally:
        db.close()
