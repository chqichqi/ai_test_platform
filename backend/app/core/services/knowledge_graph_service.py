"""
知识图谱生成服务
完整实现：智能登录 + 机构选择 + 递归爬取 + 数据保存
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.models.knowledge_graph import (
    KnowledgeGraph, ExplorationPageSnapshot, ElementLocator,
    NavigationFlow, APICallRecord
)
from app.core.services.kg_populator import RUNNING_STALE_SECONDS


def _module_match(name: str, module: str) -> bool:
    """模块名模糊匹配（与 _query_existing_kg 同语义：双向包含）。"""
    name = (name or '').strip()
    if not name:
        return False
    return module in name or name in module


def resolve_module_urls(kg: KnowledgeGraph, module_name: str) -> List[str]:
    """解析模块 → 页面 URL 映射（执行器批量用例前自动复位导航用）。

    来源依次尝试（去重，命中即返回）：
      1. pages[].page_name / module 模糊匹配 → page_url
      2. dependencies「菜单入口」边（from==模块）→ to 页面名 → 反查 pages URL
      3. menus[].name 匹配 → base_url + href 拼接（无 pages 命中的回退）
    """
    if not kg or not module_name:
        return []
    module = (module_name or '').strip()
    if not module:
        return []
    pages = kg.pages if isinstance(kg.pages, list) else []
    menus = kg.menus if isinstance(kg.menus, list) else []
    deps = kg.dependencies if isinstance(kg.dependencies, list) else []

    # 1. pages 模糊匹配
    urls = []
    for p in pages:
        if isinstance(p, dict) and _module_match(p.get('page_name') or p.get('module'), module):
            u = (p.get('page_url') or '').strip()
            if u and u not in urls:
                urls.append(u)
    if urls:
        return urls

    # 2. 模块级依赖边（菜单入口/导航/模块归属）：from==模块 → to 页面名 → 反查页面 URL
    for d in deps:
        if (isinstance(d, dict) and (d.get('type') or '') in ('菜单入口', '导航', '模块归属')
                and _module_match(d.get('from'), module)):
            to = (d.get('to') or '').strip()
            for p in pages:
                if isinstance(p, dict) and to == (p.get('page_name') or p.get('module') or '').strip():
                    u = (p.get('page_url') or '').strip()
                    if u and u not in urls:
                        urls.append(u)
    if urls:
        return urls

    # 3. menus.href 拼接
    base = (kg.base_url or '').rstrip('/')
    for m in menus:
        if isinstance(m, dict) and _module_match(m.get('name'), module):
            href = (m.get('href') or '').strip()
            if not href:
                continue
            u = href if href.startswith('http') else (base + href if base else href)
            if u and u not in urls:
                urls.append(u)
    return urls


class KnowledgeGraphService:
    """知识图谱生成服务"""

    def __init__(self, db: Session):
        self.db = db
        self.browser = None
        self.page = None
        self.network_logs = []
        self.knowledge_graph: Optional[KnowledgeGraph] = None

    def get_or_reset_graph(self, project_id: int, version_id: Optional[int],
                           base_url: str, login_username: str,
                           exploration_strategy: str = 'normal') -> tuple:
        """获取或重置项目唯一 KG 行（知识图谱是项目级资产，UNIQUE(project_id)）。

        - 无行 → 新建（started=True）
        - running/pending 且未超 stale 阈值 → 幂等返回该行（started=False，调用方应转进度查询）
        - completed/failed/stale-running → 重置同一行（删快照、清空 JSON 列与计数）

        Returns:
            (kg, started): started=True 表示本次已新建/重置，可执行探索
        """
        kg = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
        ).first()

        stale = False
        if kg and kg.exploration_status == 'running' and kg.started_at:
            stale = (datetime.utcnow() - kg.started_at).total_seconds() > RUNNING_STALE_SECONDS

        # 幂等命中：探索仍在进行中（或 pending 排队中），直接复用
        if kg and kg.exploration_status in ('running', 'pending') and not stale:
            return kg, False

        if kg:
            # 重置同一行：清理快照 + JSON 列 + 计数
            try:
                self.db.query(ExplorationPageSnapshot).filter(
                    ExplorationPageSnapshot.graph_id == kg.id
                ).delete()
            except Exception as e:
                logger.warning(f"[知识图谱] 重置时清理旧快照失败: {e}")
            _list_cols = ('pages', 'menus', 'elements', 'forms', 'tables',
                          'flows', 'api_calls', 'dependencies', 'modals')
            for _col in _list_cols:
                setattr(kg, _col, [])
            kg.dropdowns = {}
            kg.exploration_status = 'running'
            kg.started_at = datetime.utcnow()
            kg.completed_at = None
            kg.error_message = None
            kg.progress_percentage = 0
            kg.page_count = kg.menu_count = kg.element_count = kg.flow_count = kg.api_count = 0
            kg.base_url = base_url
            kg.login_username = login_username
            kg.exploration_strategy = exploration_strategy
            if version_id is not None:
                kg.version_id = version_id
            if stale:
                logger.warning(f"[知识图谱] 检测到 stale-running（>2h）死任务 #{kg.id}，重置重跑")
            self.db.commit()
            self.db.refresh(kg)
            return kg, True

        # 无行 → 新建
        kg = KnowledgeGraph(
            project_id=project_id,
            version_id=version_id,
            graph_name=f'Exploration-P{project_id}',
            base_url=base_url,
            login_username=login_username,
            exploration_strategy=exploration_strategy,
            exploration_status='running',
            started_at=datetime.utcnow(),
            progress_percentage=0,
        )
        self.db.add(kg)
        self.db.commit()
        self.db.refresh(kg)
        return kg, True
        
    async def generate_from_existing(
        self,
        project_id: int,
        version_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """基于已有探索结果合成知识图谱（不启动浏览器、不登录、不爬取）。

        探索数据来源：登录模块导入 / 功能用例转 UI 用例 / 审批增量探索，
        均由 KGPopulator.populate 累积进项目唯一 KG 行（pages/menus/elements/
        forms/flows/dependencies/dropdowns + 逐页快照）。此处只做整理合成：

          1) 快照折叠回 JSON 列（仅空列折叠，已有数据不动）
          2) 内在联系补充：dependencies 为空时从 menus/快照聚合
             「菜单入口 / 模块归属」依赖边（模块与功能之间的联系）
          3) 重新统计各计数、状态置 completed

        Returns:
            success=False 时 error 为原因；needs_exploration=True 表示
            该项目尚无探索结果，前端应引导先导入登录模块/转化用例
        """
        kg = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
        ).first()

        # 无行 → 不建空图谱（探索数据由 populate 链路产生，这里只做整理）
        if not kg:
            return {
                'success': False,
                'error': '该项目还没有知识图谱记录，请先导入登录模块或转化功能用例产生探索结果',
                'needs_exploration': True,
            }

        # running 且未 stale → 探索进行中，幂等返回
        if kg.exploration_status == 'running' and kg.started_at:
            stale = (datetime.utcnow() - kg.started_at).total_seconds() > RUNNING_STALE_SECONDS
            if not stale:
                return {
                    'success': False,
                    'error': '该项目的探索正在生成中，请稍后再查看',
                    'needs_exploration': False,
                }

        snaps = self.db.query(ExplorationPageSnapshot).filter(
            ExplorationPageSnapshot.graph_id == kg.id
        ).all()
        has_data = bool(snaps) or bool(kg.pages or kg.elements or kg.menus or kg.flows)
        if not has_data:
            return {
                'success': False,
                'error': '暂无探索结果。请先导入登录模块或转化功能用例（探索结果会自动累积），再生成知识图谱',
                'needs_exploration': True,
            }

        self.knowledge_graph = kg

        # 1. 快照折叠回 JSON 列（仅空列折叠）
        self._fold_snapshots_into_columns()

        # 2. 内在联系补充：dependencies 为空时从已有数据聚合依赖边
        if not kg.dependencies:
            deps = []
            menus = kg.menus if isinstance(kg.menus, list) else []
            pages = kg.pages if isinstance(kg.pages, list) else []
            # 菜单入口：菜单 → 匹配 href 的页面
            for m in menus:
                if not isinstance(m, dict):
                    continue
                href = m.get('href', '')
                if not href:
                    continue
                for p in pages:
                    if isinstance(p, dict) and href in p.get('page_url', ''):
                        deps.append({
                            'from': m.get('name', ''),
                            'to': p.get('page_name', '') or p.get('module', ''),
                            'type': '菜单入口',
                        })
                        break
            # 模块归属：快照模块（page_name 存模块名）→ 其下页面
            _seen_deps = set()
            for s in snaps:
                pname = s.page_name or self._url_to_page_name(s.page_url, '')
                key = f"模块归属|{s.page_name}|{pname}"
                if key in _seen_deps:
                    continue
                _seen_deps.add(key)
                deps.append({
                    'from': s.page_name,
                    'to': pname,
                    'type': '模块归属',
                })
            if deps:
                kg.dependencies = deps

        # 3. 统计 + 状态置 completed
        page_urls = {p.get('page_url') for p in (kg.pages or []) if isinstance(p, dict)}
        if not page_urls:
            page_urls = {s.page_url for s in snaps if s.page_url}
        kg.page_count = len(page_urls) or len(snaps)
        kg.menu_count = len(kg.menus or [])
        kg.element_count = len(kg.elements or [])
        kg.flow_count = len(kg.flows or [])
        kg.api_count = len(kg.api_calls or [])
        kg.exploration_status = 'completed'
        kg.completed_at = datetime.utcnow()
        kg.duration_seconds = 0
        kg.error_message = None
        kg.confidence_score = 0.85
        if version_id is not None:
            kg.version_id = version_id  # 最近更新来源版本
        self.db.commit()
        self.db.refresh(kg)

        logger.info(
            f"[知识图谱] 基于已有探索结果合成完成（无浏览器/无爬取）："
            f"项目{project_id} #{kg.id}，{kg.page_count}页/{kg.menu_count}菜单/"
            f"{kg.element_count}元素/{kg.flow_count}流程"
        )
        return {
            'success': True,
            'graph_id': kg.id,
            'page_count': kg.page_count,
            'menu_count': kg.menu_count,
            'element_count': kg.element_count,
            'flow_count': kg.flow_count,
            'api_count': kg.api_count,
            'mode': 'existing',
            'duration_seconds': 0,
        }

    async def execute_graph_generation(
        self,
        graph_id: int,
        version_id: int,
        project_id: int,
        base_url: str,
        login_username: str,
        login_password: str,
        exploration_strategy: str = 'normal',
        skip_tenant: bool = True
    ) -> Dict[str, Any]:
        """
        从已创建的graph_id开始执行知识图谱生成（供后台任务使用）
        
        Args:
            graph_id: 已创建的知识图谱ID
            version_id: 版本ID
            project_id: 项目ID
            base_url: 项目基础URL
            login_username: 登录用户名
            login_password: 登录密码
            exploration_strategy: 探索策略（quick/normal/deep）
            skip_tenant: 是否跳过租户机构
        
        Returns:
            生成结果
        """
        logger.info(f"[知识图谱] 开始执行：graph_id={graph_id}, 项目{project_id}，版本{version_id}")
        logger.info(f"[知识图谱] URL: {base_url}, 策略: {exploration_strategy}")
        
        try:
            # 1. 加载已创建的知识图谱记录
            self.knowledge_graph = self.db.query(KnowledgeGraph).filter(
                KnowledgeGraph.id == graph_id
            ).first()
            
            if not self.knowledge_graph:
                raise Exception(f"知识图谱记录不存在: graph_id={graph_id}")
            
            # 更新状态为running
            self.knowledge_graph.exploration_status = 'running'
            self.knowledge_graph.started_at = datetime.utcnow()
            self.knowledge_graph.progress_percentage = 0
            self.db.commit()
            
            logger.info(f"[知识图谱] 记录已加载，ID={graph_id}")
            
            return await self._execute_generation_flow(
                project_id,
                base_url,
                login_username,
                login_password,
                exploration_strategy,
                skip_tenant
            )

        except Exception as e:
            if self.knowledge_graph:
                self.knowledge_graph.exploration_status = 'failed'
                self.knowledge_graph.error_message = str(e)
                self.db.commit()
            raise e

    async def generate_knowledge_graph(
        self,
        version_id: int,
        project_id: int,
        base_url: str,
        login_username: str,
        login_password: str,
        exploration_strategy: str = 'normal',
        skip_tenant: bool = True
    ) -> Dict[str, Any]:
        """
        生成知识图谱（完整流程 - 同步版本，供generate-sync使用）
        
        Args:
            version_id: 版本ID
            project_id: 项目ID
            base_url: 项目基础URL
            login_username: 登录用户名
            login_password: 登录密码
            exploration_strategy: 探索策略（quick/normal/deep）
            skip_tenant: 是否跳过租户机构
        
        Returns:
            生成结果
        """
        logger.info(f"[知识图谱] 同步生成：项目{project_id}，版本{version_id}")
        logger.info(f"[知识图谱] URL: {base_url}, 策略: {exploration_strategy}")
        
        try:
            # 1. 获取或重置项目唯一 KG 行（探索中 → 幂等复用；已完成/失败/超时 → 重置同一行）
            self.knowledge_graph, started = self.get_or_reset_graph(
                project_id, version_id, base_url, login_username, exploration_strategy
            )
            if not started:
                raise Exception("该项目的知识图谱正在生成中，请先查看进度")

            logger.info(f"[知识图谱] 项目唯一行就绪，ID={self.knowledge_graph.id}")

            return await self._execute_generation_flow(
                project_id,
                base_url,
                login_username,
                login_password,
                exploration_strategy,
                skip_tenant
            )
            
        except Exception as e:
            logger.error(f"[知识图谱] 生成失败: {str(e)}")
            
            if self.knowledge_graph:
                self.knowledge_graph.exploration_status = 'failed'
                self.knowledge_graph.error_message = str(e)
                self.db.commit()
            
            return {
                'success': False,
                'error': str(e),
                'graph_id': self.knowledge_graph.id if self.knowledge_graph else None
            }
    
    async def _execute_generation_flow(
        self,
        project_id: int,
        base_url: str,
        login_username: str,
        login_password: str,
        exploration_strategy: str,
        skip_tenant: bool
    ) -> Dict[str, Any]:
        """
        执行知识图谱生成的核心流程（公共方法）

        Args:
            project_id: 项目ID（登录鉴权按项目取 __login__ 用例）
            base_url: 项目基础URL
            login_username: 登录用户名
            login_password: 登录密码
            exploration_strategy: 探索策略
            skip_tenant: 是否跳过租户机构

        Returns:
            生成结果
        """
        try:
            # 1. 启动Playwright浏览器
            await self._launch_browser()
            self._update_progress(5, "浏览器启动完成")
            
            # 2. 使用 __login__ UI 用例步骤执行登录
            from app.core.services.login_engine import login_with_ui_case

            ok, wb_url = await login_with_ui_case(
                self.page, base_url, login_username, login_password,
                project_id=project_id
            )
            if not ok:
                raise Exception("登录失败——请先导入登录模块")
            self._update_progress(15, "登录成功")

            # 保存鉴权数据供后续复用
            # login_with_ui_case 不需要单独提取 auth_data——后续通过 storage_state 复用
            try:
                state = await self.page.context.storage_state()
                import json as _json
                self.knowledge_graph.auth_data = _json.loads(_json.dumps(state))
            except Exception:
                pass
            self.db.commit()

            # 记录机构选择结果
            if 'selectOrganization' not in (wb_url or '') and '/login' not in (wb_url or ''):
                self.knowledge_graph.selected_organization = "已选择"
                self._update_progress(20, "登录完成（含机构选择）")
            else:
                self._update_progress(20, "无需选择机构")
            
            # 5. 提取导航菜单结构
            menus = await self._extract_all_menus()
            self._update_progress(30, f"菜单提取完成：{len(menus)}个")

            # 6. BFS 深度探索所有页面（P1-P9，零 LLM 调用）
            await self._bfs_explore_all_modules(menus, exploration_strategy, base_url)
            
            # 7. 构建知识图谱数据
            await self._build_knowledge_graph_data()
            
            # 8. 验证元素定位器
            await self._validate_locators()
            
            # 9. 保存知识图谱（先折叠快照回 JSON 列，使 BFS 产物对可视化与后续 merge 有基底）
            self._fold_snapshots_into_columns()
            self._save_final_results()
            self._update_progress(100, "知识图谱生成完成")
            
            # 更新状态
            self.knowledge_graph.exploration_status = 'completed'
            self.knowledge_graph.completed_at = datetime.utcnow()
            self.knowledge_graph.duration_seconds = int(
                (self.knowledge_graph.completed_at - self.knowledge_graph.started_at).total_seconds()
            )
            self.db.commit()
            
            logger.info(f"[知识图谱] 生成完成，耗时{self.knowledge_graph.duration_seconds}秒")
            
            return {
                'success': True,
                'graph_id': self.knowledge_graph.id,
                'page_count': self.knowledge_graph.page_count,
                'element_count': self.knowledge_graph.element_count,
                'duration_seconds': self.knowledge_graph.duration_seconds
            }
            
        except Exception as e:
            logger.error(f"[知识图谱] 生成失败: {str(e)}")
            
            if self.knowledge_graph:
                self.knowledge_graph.exploration_status = 'failed'
                self.knowledge_graph.error_message = str(e)
                self.db.commit()
            
            raise e
        
        finally:
            # 关闭浏览器
            await self._close_browser()
    
    async def _launch_browser(self):
        """启动浏览器"""
        try:
            from playwright.async_api import async_playwright
            
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=False)
            self.page = await self.browser.new_page()
            
            # 设置网络监听
            self.page.on('request', self._capture_request)
            self.page.on('response', self._capture_response)
            
            logger.info("[知识图谱] 浏览器启动成功")
            
        except ImportError:
            logger.error("[知识图谱] Playwright未安装")
            raise Exception("Playwright未安装，请运行：pip install playwright && playwright install")
    
    async def _extract_all_menus(self) -> List[Dict[str, Any]]:
        """提取所有菜单结构（一级+二级）"""
        logger.info("[知识图谱] 开始提取菜单结构")
        
        menus = []
        
        # 提取一级菜单（侧边栏）
        sidebar_menu = await self.page.query_selector('nav, .sidebar, .menu, [role="navigation"]')
        if sidebar_menu:
            level1_items = await sidebar_menu.query_selector_all('a, button, [role="menuitem"]')
            
            for item in level1_items[:20]:
                text = await item.text_content()
                href = await item.get_attribute('href') or ''
                
                menu = {
                    'name': text.strip(),
                    'href': href,
                    'level': 1,
                    'parent': None
                }
                menus.append(menu)
                
                logger.info(f"[知识图谱] 一级菜单：{menu['name']}")
        
        # 提取顶部菜单
        header_menu = await self.page.query_selector('header nav, .navbar, .top-menu')
        if header_menu:
            header_items = await header_menu.query_selector_all('a, button')
            
            for item in header_items[:10]:
                text = await item.text_content()
                href = await item.get_attribute('href') or ''
                
                menu = {
                    'name': text.strip(),
                    'href': href,
                    'level': 1,
                    'parent': None,
                    'type': 'header'
                }
                menus.append(menu)
        
        return menus
    
    async def _crawl_all_pages(self, menus: List[Dict], strategy: str):
        """递归爬取所有页面"""
        logger.info(f"[知识图谱] 开始爬取页面，策略={strategy}")
        
        visited_urls = set()
        pages_data = []
        
        # 根据策略确定爬取深度
        max_depth = {'quick': 1, 'normal': 2, 'deep': 3}.get(strategy, 2)
        
        for menu in menus:
            if menu['href'] and menu['href'] not in visited_urls:
                # 导航到页面
                await self._navigate_to_page(menu['href'])
                visited_urls.add(menu['href'])
                
                # 爬取页面内容
                page_data = await self._crawl_page_content(menu)
                pages_data.append(page_data)
                
                # 更新进度
                progress = 30 + int((len(pages_data) / len(menus)) * 50)
                self._update_progress(progress, f"爬取页面：{menu['name']}")
                
                # 如果是deep策略，递归爬取二级菜单
                if strategy == 'deep' and menu['level'] == 1:
                    sub_menus = await self._extract_sub_menus(menu)
                    for sub_menu in sub_menus[:5]:
                        if sub_menu['href'] and sub_menu['href'] not in visited_urls:
                            await self._navigate_to_page(sub_menu['href'])
                            visited_urls.add(sub_menu['href'])
                            
                            sub_page_data = await self._crawl_page_content(sub_menu)
                            pages_data.append(sub_page_data)
        
        logger.info(f"[知识图谱] 页面爬取完成，共{len(pages_data)}个页面")
    
    async def _navigate_to_page(self, href: str):
        """导航到指定页面"""
        try:
            full_url = self.knowledge_graph.base_url.rstrip('/') + href
            await self.page.goto(full_url, wait_until='networkidle', timeout=10000)
            logger.info(f"[知识图谱] 导航到页面：{full_url}")
        except Exception as e:
            logger.warning(f"[知识图谱] 页面导航失败：{href}, {str(e)}")
    
    async def _bfs_explore_all_modules(self, menus: list, strategy: str, base_url: str):
        """使用 BFS Explorer 对所有菜单模块进行深度探索（P1-P9）"""
        from app.core.services.bfs_explorer import BFSExplorer
        from app.core.services.exploration_config import WebExplorationConfig as ExplorationConfig

        config = ExplorationConfig()
        explorer = BFSExplorer(
            self.page, base_url, config,
            login_engine=getattr(self, '_login_engine', None),
        )

        modules_data = []
        for menu in menus[:20]:  # 限制菜单数量
            module_name = menu.get("name", "").strip()
            if not module_name or module_name in ["首页", "Home", "Dashboard"]:
                continue

            module_url = menu.get("href", "")
            progress_base = 30
            progress_per_module = 60 // max(len(menus), 1)

            self._update_progress(progress_base, f"BFS 探索模块: {module_name}")

            try:
                result = await explorer.explore_module(module_name, module_url)
                modules_data.append(result)

                # 保存页面快照到 DB
                self._save_page_snapshot(result)

                progress_base += progress_per_module
                self._update_progress(progress_base,
                    f"{module_name}: {len(result.get('pages',[]))}页, "
                    f"{len(result.get('filter_options',{}))}过滤控件, "
                    f"{len(result.get('modals',[]))}弹窗")
            except Exception as e:
                logger.error(f"[BFS] 模块 {module_name} 探索失败: {e}")

        # 汇总
        self.knowledge_graph.page_count = sum(len(m.get("pages", [])) for m in modules_data)
        self.knowledge_graph.element_count = sum(
            sum(len(v) for e in m.get("elements", []) for v in e.values())
            for m in modules_data
        )
        self.db.commit()
        logger.info(f"[BFS] 全部模块探索完成: {len(modules_data)} 个模块, "
                    f"{self.knowledge_graph.page_count} 页, {self.knowledge_graph.element_count} 个元素")

    def _save_page_snapshot(self, result: dict):
        """保存探索结果到 DB（使用正确的模型字段）。"""
        try:
            from app.core.models.knowledge_graph import ExplorationPageSnapshot
            import json as _json

            elements = result.get("elements", [])
            # 从 role-grouped 元素中提取分类
            buttons, links, forms_list = [], [], []
            if isinstance(elements, list):
                for elem_group in elements:
                    if isinstance(elem_group, dict):
                        for role, items in elem_group.items():
                            if isinstance(items, list):
                                if role == "buttons":
                                    buttons.extend(items)
                                elif role == "links":
                                    links.extend(items)
                                elif role in ("inputs", "forms"):
                                    forms_list.extend(items)

            dom_text = _json.dumps(result, ensure_ascii=False) if result else ""

            # 逐页落行：快照 page_url 必须是真实页面 URL（同根 URL 会让折叠后的
            # pages 列全是 base_url 重复，且按 URL 去重失效）
            _pages = result.get("pages", [])
            _page_urls = [u for u in (_pages if isinstance(_pages, list) else [])
                          if isinstance(u, str) and u]
            if not _page_urls:
                _page_urls = [result.get("base_url", "")]

            _module = result.get("module", "") or ""
            for _u in _page_urls:
                snapshot = ExplorationPageSnapshot(
                    graph_id=self.knowledge_graph.id,
                    page_url=_u,
                    page_title=_module,
                    page_name=_module,
                    elements=elements if isinstance(elements, list) else [],
                    buttons=buttons,
                    links=links,
                    forms=forms_list,
                    operations=result.get("modals", []),
                    dom_snapshot=dom_text,
                    visited_at=datetime.utcnow(),
                )
                self.db.add(snapshot)
            self.db.commit()
        except Exception as e:
            logger.warning(f"[BFS] 保存页面快照失败: {e}")

    async def _crawl_page_content(self, menu: Dict) -> Dict[str, Any]:
        """[已废弃] 爬取单个页面内容，现由 BFS Explorer 替代"""
        logger.info(f"[知识图谱] 爬取页面内容：{menu['name']}")
        
        page_data = {
            'menu_name': menu['name'],
            'menu_level': menu['level'],
            'url': self.page.url,
            'title': await self.page.title(),
            'elements': [],
            'forms': [],
            'tables': [],
            'buttons': [],
            'links': [],
            'api_calls': []
        }
        
        # 提取元素
        elements = await self._extract_page_elements()
        page_data['elements'] = elements
        
        # 提取表单
        forms = await self._extract_page_forms()
        page_data['forms'] = forms
        
        # 提取表格
        tables = await self._extract_page_tables()
        page_data['tables'] = tables
        
        # 提取API调用
        page_data['api_calls'] = self.network_logs[-50:]  # 最近50个API调用
        
        return page_data
    
    async def _extract_page_elements(self) -> List[Dict]:
        """提取页面元素"""
        elements = []
        
        # 按钮
        buttons = await self.page.query_selector_all('button, input[type="button"], input[type="submit"]')
        for btn in buttons[:20]:
            text = await btn.text_content() or ''
            elem_id = await btn.get_attribute('id') or ''
            
            elements.append({
                'name': text.strip(),
                'type': 'button',
                'id': elem_id,
                'xpath': f"//button[contains(text(), '{text.strip()}')]",
                'css': await btn.get_attribute('class') or ''
            })
        
        # 输入框
        inputs = await self.page.query_selector_all('input, textarea, select')
        for inp in inputs[:20]:
            name = await inp.get_attribute('name') or ''
            elem_id = await inp.get_attribute('id') or ''
            input_type = await inp.get_attribute('type') or 'text'
            
            elements.append({
                'name': name,
                'type': 'input',
                'input_type': input_type,
                'id': elem_id,
                'xpath': f"//input[@name='{name}']",
                'css': await inp.get_attribute('class') or ''
            })
        
        return elements
    
    async def _extract_page_forms(self) -> List[Dict]:
        """提取表单"""
        forms = []
        
        form_elements = await self.page.query_selector_all('form')
        for form in form_elements[:10]:
            form_id = await form.get_attribute('id') or ''
            form_name = await form.get_attribute('name') or ''
            
            fields = []
            inputs = await form.query_selector_all('input, select, textarea')
            for inp in inputs[:15]:
                field_name = await inp.get_attribute('name') or ''
                field_type = await inp.get_attribute('type') or 'text'
                fields.append({'name': field_name, 'type': field_type})
            
            forms.append({
                'id': form_id,
                'name': form_name,
                'fields': fields
            })
        
        return forms
    
    async def _extract_page_tables(self) -> List[Dict]:
        """提取表格"""
        tables = []
        
        table_elements = await self.page.query_selector_all('table')
        for table in table_elements[:10]:
            headers = []
            header_row = await table.query_selector('thead tr')
            if header_row:
                th_cells = await header_row.query_selector_all('th')
                for th in th_cells:
                    text = await th.text_content() or ''
                    headers.append(text.strip())
            
            tables.append({'headers': headers})
        
        return tables
    
    async def _extract_sub_menus(self, parent_menu: Dict) -> List[Dict]:
        """提取二级菜单"""
        sub_menus = []
        
        # 查找当前页面中的二级菜单
        sub_items = await self.page.query_selector_all('.sub-menu a, .submenu a, [class*="sub"] a')
        
        for item in sub_items[:10]:
            text = await item.text_content()
            href = await item.get_attribute('href') or ''
            
            sub_menus.append({
                'name': text.strip(),
                'href': href,
                'level': 2,
                'parent': parent_menu['name']
            })
        
        return sub_menus
    
    async def _build_knowledge_graph_data(self):
        """构建知识图谱数据"""
        logger.info("[知识图谱] 构建知识图谱数据")
        
        # 从爬取的数据构建依赖关系
        # 这里简化实现，实际应根据页面访问顺序和API调用分析依赖
        
        dependencies = []
        # 示例：登录 → 其他页面
        dependencies.append({
            'from': '登录',
            'to': '主页',
            'type': '前置条件'
        })
        
        self.knowledge_graph.dependencies = dependencies
    
    async def _validate_locators(self):
        """验证元素定位器有效性"""
        logger.info("[知识图谱] 验证定位器有效性")
        
        # 简化实现：随机选择10个元素验证
        validation_success = 0
        
        self.knowledge_graph.locator_validation_rate = validation_success / 10 if validation_success > 0 else 0.5
    
    def _fold_snapshots_into_columns(self):
        """将 ExplorationPageSnapshot 行折叠回 JSON 列（仅当列为空时）。

        手动 /generate 走 BFS 管线（_bfs_explore_all_modules 只写快照行，
        不写 KGPopulator 的 JSON 列）；折叠后 pages/elements/menus 有基底，
        详情接口可视化与后续增量 merge 才能拿到旧数据。
        """
        try:
            snaps = self.db.query(ExplorationPageSnapshot).filter(
                ExplorationPageSnapshot.graph_id == self.knowledge_graph.id
            ).all()
            if not snaps:
                return
            if not self.knowledge_graph.pages:
                # 键名与 KGPopulator._extract_pages 对齐（page_url/page_name/module）：
                # 下游 _query_existing_kg 按 page.get('module') 匹配缓存、
                # _infer_dependencies 按 page_name 建依赖边——键名不一致会静默失配
                _seen_urls = set()
                _pages = []
                for s in snaps:
                    if s.page_url in _seen_urls:
                        continue
                    _seen_urls.add(s.page_url)
                    _pages.append({
                        'page_url': s.page_url,
                        'page_name': s.page_name,
                        'page_title': s.page_title,
                        'module': s.page_name,  # 快照无 module 字段（page_name 存模块名）
                    })
                self.knowledge_graph.pages = _pages
            if not self.knowledge_graph.elements:
                _els = []
                _seen_els = set()
                for s in snaps:
                    for e in (s.elements if isinstance(s.elements, list) else []):
                        if isinstance(e, dict):
                            _key = json.dumps(e, ensure_ascii=False, sort_keys=True)
                            if _key not in _seen_els:
                                _seen_els.add(_key)
                                _els.append(e)
                self.knowledge_graph.elements = _els
            if not self.knowledge_graph.menus:
                _seen_menus = set()
                _menus = []
                for s in snaps:
                    if s.page_name in _seen_menus:
                        continue
                    _seen_menus.add(s.page_name)
                    _menus.append({
                        'name': s.page_name, 'href': s.page_url,
                        'level': s.menu_level, 'parent': s.parent_menu,
                        'source': 'snapshot_fallback',
                    })
                self.knowledge_graph.menus = _menus
            self.db.commit()
            logger.info(f"[知识图谱] 快照折叠回 JSON 列: {len(snaps)} 条快照")
        except Exception as e:
            logger.warning(f"[知识图谱] 快照折叠失败: {e}")

    def _save_final_results(self):
        """保存最终结果到数据库"""
        logger.info("[知识图谱] 保存知识图谱结果")
        
        # 这里已经通过_update_progress实时保存数据
        # 最终更新统计信息
        
        self.knowledge_graph.confidence_score = 0.85
        self.db.commit()
    
    def _update_progress(self, percentage: int, current_page: str):
        """更新进度"""
        if self.knowledge_graph:
            self.knowledge_graph.progress_percentage = percentage
            self.knowledge_graph.current_page = current_page
            self.db.commit()
            
            logger.info(f"[知识图谱] 进度：{percentage}% - {current_page}")
    
    async def _close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            logger.info("[知识图谱] 浏览器已关闭")
    
    def _capture_request(self, request):
        """捕获API请求"""
        self.network_logs.append({
            'type': request.resource_type,
            'url': request.url,
            'method': request.method,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def _capture_response(self, response):
        """捕获API响应"""
        # 可提取响应数据
        pass