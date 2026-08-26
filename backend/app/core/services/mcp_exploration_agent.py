"""
MCP 探索 Agent — V6 版。

Phase 1: accessibility.snapshot() 无障碍树发现（scope=主内容区，ARIA-first）
Phase 2: DFS + 标准 Action 分发 + 指纹检测
Phase 3: Portal 下拉 + 弹窗 + 表格扫描（scope 限定）
Phase 4: LLM 综合生成 + 状态图输出

核心原则:
  1. Scope 限定 — 元素发现从 <main>/[role="main"] 开始（Cypress/axe-core 模式）
  2. Action Vocabulary — 标准动作类型，统一分发（Scry/BrowserAgent 模式）
  3. State Graph — 输出结构化状态图而非扁平列表（ActionEngine/profiq 模式）
"""

import json, re, time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from app.core.logger import logger


# ═══════════════════════════════════════════════════════════════
# Action Vocabulary — 标准动作抽象（Scry / BrowserAgent 模式）
# ═══════════════════════════════════════════════════════════════

class ActionType(Enum):
    CLICK = "click"
    NAVIGATE = "navigate"
    FILL = "fill"
    SELECT = "select"
    HOVER = "hover"
    RIGHT_CLICK = "right_click"
    KEY_PRESS = "key_press"
    WAIT_FOR = "wait_for"
    VALIDATE = "validate"
    TABLE_ROW = "table_row"
    TAB_SWITCH = "tab_switch"
    GO_BACK = "go_back"


@dataclass
class Action:
    """标准动作定义。"""
    type: ActionType
    label: str                     # 人类可读标签
    target_text: str = ""          # 目标元素文本
    target_role: str = ""          # ARIA role
    target_selector: str = ""      # CSS 选择器（回退用）
    href: str = ""                 # 链接目标（NAVIGATE 类型）
    source: str = ""               # 发现来源: a11y / css_fallback / row_locator


@dataclass
class ActionResult:
    """动作执行结果。"""
    action: Action
    success: bool
    navigated: bool = False
    jump_url: str = ""
    overlay_detected: bool = False
    fingerprint_diff: Optional[Dict] = None
    console_errors: List[str] = field(default_factory=list)
    error: str = ""
    sub_page_explored: bool = False  # 是否触发了递归探索


@dataclass
class StateNode:
    """状态图节点（ActionEngine / profiq 模式）。"""
    url: str
    title: str = ""                # LLM 生成的状态标题
    fingerprint: str = ""          # 状态指纹
    actions: List[str] = field(default_factory=list)  # 从此状态可执行的动作标签列表
    children: List[str] = field(default_factory=list)  # 子状态 URL 列表
    deep_dive: Dict = field(default_factory=dict)


class MCPExplorationAgent:

    # ── V6 Action Vocabulary: role → ActionType 映射 ──
    ROLE_TO_ACTION = {
        "input": ActionType.FILL, "textbox": ActionType.FILL, "searchbox": ActionType.FILL,
        "combobox": ActionType.SELECT, "listbox": ActionType.SELECT,
        "button": ActionType.CLICK, "card": ActionType.CLICK,
        "link": ActionType.NAVIGATE, "nav": ActionType.NAVIGATE, "menuitem": ActionType.NAVIGATE,
        "tab": ActionType.TAB_SWITCH,
        "table-row": ActionType.TABLE_ROW,
        "form": ActionType.CLICK,  # radio/checkbox → click
    }

    def __init__(self, client, config, llm_service=None, module_name=""):
        self.client = client
        self.page = client.page
        self.config = config
        self.llm = llm_service
        self.visited_states = {}
        self.action_count = 0
        self._nav_names = set()
        self._module = module_name or "module"
        self._visited_urls = set()    # DFS 已访问 URL
        self._pages_explored = []     # 所有探索过的页面结果
        self._all_element_jumps = []  # 跨页面的元素跳转汇总
        self._click_log = []          # 每步点击记录
        self._state_counter = 0       # 增量计数器
        self._module_url_root = ""    # 目标模块 URL 前缀（用于边界检查）
        self._scope_element = None    # 主内容区 ElementHandle（当前页面的 scope）
        self._state_graph: List[StateNode] = []  # V6: 状态图
        self._observer_injected = False          # 防止重复注入 dialog handler

    # ── Config 访问器（零硬编码：所有关键词/角色从 config 读取，带通用回退）──
    @property
    def _noise_kw(self):
        return getattr(self.config, 'noise_keywords', None) or ['Loading']

    @property
    def _danger_kw(self):
        return getattr(self.config, 'danger_keywords', None) or ['delete', 'remove', 'destroy']

    @property
    def _nav_roles(self):
        return set(getattr(self.config, 'nav_roles', None) or ['menuitem', 'navigation', 'menu', 'sidebar'])


    # ═══════════════════════════════════════════════════════════
    # 对外入口
    # ═══════════════════════════════════════════════════════════

    def explore(self):
        t0 = time.time()
        self.client.inject_console_hook()
        self._visited_urls = set()
        self._pages_explored = []
        self._all_element_jumps = []
        self._click_log = []
        self._state_counter = 0
        self._error_events = []
        self._site_map = {"modules": []}
        self._state_graph = []      # V6: 重置状态图
        self._scope_element = None  # V6: 重置 scope
        self._observer_injected = False  # 每个 agent 实例独立注入

        # 清理旧 state 目录（同模块替换，不同模块保留）
        import os as _os, shutil as _shutil
        _state_dir = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..", "tests", "exploration", "states", self._module))
        if _os.path.exists(_state_dir):
            try: _shutil.rmtree(_state_dir)
            except Exception: pass

        start_url = self.client.get_url()
        url_key = self._norm_url_key(start_url)
        if url_key.startswith("/"):
            self._module_url_root = url_key.split("/")[1] if len(url_key.split("/")) > 1 else url_key.strip("/")
        else:
            # 非 hash URL：用 pathname
            from urllib.parse import urlparse as _up
            self._module_url_root = _up(start_url).path.strip("/").split("/")[0] if _up(start_url).path else url_key
        logger.info(f"[Agent] Module boundary root=/{self._module_url_root}")

        self._setup_dialog_handlers()
        try:
            self._explore_page(start_url, 0)
        except Exception as e:
            self._error_events.append({"stage": "explore", "error": str(e), "url": start_url})
            logger.error(f"[Agent] Fatal error: {e}")

        elapsed = time.time() - t0
        stats = {
            "total_elements": self.action_count,
            "navigated_elements": sum(1 for e in self._all_element_jumps if e.get("navigated")),
            "pages_explored": len(self._pages_explored),
            "visited_states": len(self.visited_states),
            "elapsed_seconds": round(elapsed, 1),
            "errors": len(self._error_events),
        }
        logger.info(f"[Agent] Done: {json.dumps(stats, ensure_ascii=False)}")

        # Phase 4: LLM 生成文档（如果 llm_service 可用）
        deep_dive_summary = self._collect_deep_dive()
        phase4 = {}
        if self.llm:
            phase4 = self._phase4_synthesis(start_url, self._site_map, self._all_element_jumps, deep_dive_summary)

        # 最终保存
        self._save_results(start_url)
        # 状态图序列化（dataclass → dict）
        state_graph_dicts = []
        for sn in self._state_graph:
            state_graph_dicts.append({
                "url": sn.url,
                "title": sn.title,
                "fingerprint": sn.fingerprint,
                "actions": sn.actions,
                "children": sn.children,
                "deep_dive": sn.deep_dive,
            })

        return {
            "site_map": self._site_map,
            "element_jumps": {"_main": {"url": start_url, "elements": self._all_element_jumps}},
            "deep_dive": deep_dive_summary,
            "stats": stats,
            "pages_visited": list(self._visited_urls),
            "error_events": self._error_events,
            "state_graph": state_graph_dicts,  # V6: 结构化状态图
            "module_docs": phase4.get("module_docs", ""),
            "site_map_md": phase4.get("site_map_md", ""),
            "page_object_code": phase4.get("page_object_code", ""),
        }

    def _collect_deep_dive(self):
        """汇总所有页面的 deep_dive 数据。"""
        dd = {"dropdowns": {}, "modals": [], "tables": [], "pagination": [], "forms": [], "api_endpoints": []}
        for page in self._pages_explored:
            pd = page.get("deep_dive") or {}
            # 合并 dropdowns
            for k, v in (pd.get("dropdowns") or {}).items():
                if k not in dd["dropdowns"]:
                    dd["dropdowns"][k] = v
            dd["modals"].extend(pd.get("modals") or [])
            dd["tables"].extend(pd.get("tables") or [])
            if pd.get("pagination"):
                dd["pagination"].append(pd["pagination"])
            if pd.get("forms"):
                dd["forms"].append(pd["forms"])
            dd["api_endpoints"].extend(pd.get("api_endpoints") or [])
        return dd

    def _save_results(self, start_url=None):
        """实时保存探索进度。每探索完一个页面就调用。"""
        import os as _os
        _log_dir = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "..", "..", "tests", "exploration"))
        _os.makedirs(_log_dir, exist_ok=True)
        # F37 修复（2026-08-25）：与 _capture_state 的 state 文件名同源 sanitize——
        # module 含多行文本（\n 等控制字符）时 open() 抛 Errno 22 中断探索主流程
        # （08-24 实证：99 步只执行 35 步）；写盘失败跳过不中断
        _safe_mod = re.sub(r'[\x00-\x1f\x7f\\/:*?"<>| ]', '_', self._module or '')[:50]
        _log_file = _os.path.join(_log_dir, f"{_safe_mod}-click-log.json")
        try:
            with open(_log_file, 'w', encoding='utf-8') as f:
                json.dump({"module": self._module, "total_clicks": len(self._click_log), "pages": len(self._pages_explored), "clicks": self._click_log}, f, ensure_ascii=False, indent=2)
        except OSError as _se:
            logger.warning(f"[Agent] click-log 写盘失败（跳过，不中断探索）: {_se}")
        # 跳转摘要：nav + cards + dropdowns + sub_menus（层级结构）
        nav_names = getattr(self, '_nav_names', set())
        summary = {"nav": {}, "cards": {}, "dropdowns": {}, "sub_menus": {}}
        for e in self._all_element_jumps:
            name = e.get("name", "")
            if not name: continue
            entry = {"label": name, "clicked": e.get("clicked", True), "jumped": e.get("navigated", False), "url_hash": (e.get("jump_url","") or "").split("#")[-1].split("?")[0] if e.get("jump_url") else "", "role": e.get("role", "")}
            is_nav = name in nav_names or e.get("role") == "nav"
            if is_nav and e.get("navigated"):
                # 子菜单 → 记录跳转目标，附带在 sub_menus 中
                summary["sub_menus"][name] = {**entry, "sub_url": e.get("jump_url", ""), "elements_found": e.get("elements_count", 0)}
            elif is_nav:
                summary["nav"][name] = entry
            else:
                summary["cards"][name] = entry

        # Phase 3 下拉结果合并（来自 deep_dive）
        for page in self._pages_explored:
            dd = (page.get("deep_dive") or {}).get("dropdowns") or {}
            for dd_name, dd_info in dd.items():
                if dd_name not in summary["dropdowns"]:
                    summary["dropdowns"][dd_name] = {
                        "options": dd_info.get("options", []),
                        "option_count": dd_info.get("option_count", 0),
                    }

        _summary_file = _os.path.join(_log_dir, f"{_safe_mod}-jump-summary.json")
        try:
            with open(_summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        except OSError as _se:
            logger.warning(f"[Agent] jump-summary 写盘失败（跳过，不中断探索）: {_se}")

    def _setup_dialog_handlers(self):
        """拦截打印/下载/上传对话框 + Modal 自动关闭。"""
        if self._observer_injected:
            return
        try:
            c = self.config
            modal_sel = getattr(c, 'modal_detect_selector',
                '[role="dialog"]:not([style*="display: none"]), dialog[open]')
            modal_sel_escaped = modal_sel.replace("'", "\\'")
            cancel_kw = json.dumps(getattr(c, 'modal_close_keywords',
                ['Cancel', 'Close', '取消', '关闭', 'No', '否', '返回', 'Back']))
            self.page.evaluate(f"""
                () => {{
                    window.print = () => {{}};
                    window.alert = () => {{}};
                    window.confirm = () => false;
                    window.prompt = () => null;
                    window.__mcp_modal_interacting = false;

                    const cancelKw = {cancel_kw};
                    const observer = new MutationObserver(() => {{
                        if (window.__mcp_modal_interacting) return;
                        const dialogs = document.querySelectorAll('{modal_sel_escaped}');
                        dialogs.forEach(dlg => {{
                            const btns = dlg.querySelectorAll('button, [role="button"]');
                            if (!btns.length) return;
                            for (const b of btns) {{
                                const t = (b.textContent||'').trim();
                                if (cancelKw.some(kw => t.includes(kw))) {{
                                    try {{ b.click(); }} catch(e) {{}}
                                    return;
                                }}
                            }}
                            try {{ btns[btns.length-1].click(); }} catch(e) {{}}
                        }});
                    }});
                    observer.observe(document.body, {{ childList: true, subtree: true }});

                    setInterval(() => {{
                        if (window.__mcp_modal_interacting) return;
                        const dlg = document.querySelector('{modal_sel_escaped}');
                        if (dlg) {{
                            document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', keyCode: 27, bubbles: true}}));
                        }}
                    }}, 2000);
                }}
            """)
            self._observer_injected = True
        except Exception: pass

    def _return_to_page(self, target_url, from_url=""):
        """返回目标页并验证。goto 失败时 fallback 到 go_back。"""
        # 恢复目标本身是 about:blank 时直接拒绝——goto('about:blank') 会「成功」把页面
        # 停在空白页（合法 URL），恢复即污染（2026-08-25 22:02 真机实证连锁作废根因）
        if not target_url or target_url == "about:blank":
            logger.warning(f"[Agent] 恢复目标无效（{target_url or '空'}），跳过页面恢复")
            return False
        c = self.config
        pft = getattr(c, 'page_ready_timeout_fast', 8.0)

        # 先尝试 go_back（SPA 内 hash 切换更高效，且能保留页面状态）
        try:
            self.page.go_back()
            self.client.wait_for_page_ready(max_wait=3.0)
            cur = self.client.get_url()
            cur_key = self._norm_url_key(cur)
            target_key = self._norm_url_key(target_url)
            if cur_key == target_key:
                logger.info(f"[Agent] Return via go_back OK: {target_url[-60:]}")
                return
        except Exception:
            pass

        # go_back 无效 → goto 完整加载
        goto_ok = False
        try:
            goto_ok = self.client.goto(target_url)
        except Exception as e:
            logger.warning(f"[Agent] goto failed ({e}), trying go_back as last resort")
            try:
                self.page.go_back()
            except Exception:
                pass
            # go_back 回退后验证
            try:
                cur = self.client.get_url()
                if cur and self._norm_url_key(cur) != self._norm_url_key(target_url):
                    logger.warning(f"[Agent] go_back also failed, forcing goto")
                    self.client.goto(target_url)
            except Exception:
                pass

        is_custom_page = '/custom' in (from_url or "").lower()
        if is_custom_page:
            logger.info(f"[Agent] CustomCard sub-page detected, reloading to clear SPA edit state")
            try:
                self.page.reload()
            except Exception:
                pass

        self.client.wait_for_page_ready(max_wait=pft)

        # 验证是否真的回到了目标页面
        cur = self.client.get_url()
        if cur and target_url:
            cur_key = self._norm_url_key(cur)
            target_key = self._norm_url_key(target_url)
            if cur_key != target_key:
                logger.warning(f"[Agent] Return mismatch! expected={target_url[-60:]} actual={cur[-60:]} — force goto")
                try:
                    if not self.client.goto(target_url):
                        logger.warning(f"[Agent] Force goto returned False, reloading")
                        self.page.reload()
                    self.client.wait_for_page_ready(max_wait=pft)
                except Exception:
                    pass

    def _is_within_module(self, url):
        """检查 URL 是否在目标模块边界内（精确路径前缀匹配）。

        规则: /workpanel 匹配 /workpanel, /workpanel/customCard
             但不匹配 /workpanelXXX 或 /patientarchieve
        """
        if not self._module_url_root: return True
        hash_path = self._norm_url_key(url)
        root = "/" + self._module_url_root
        return hash_path == root or hash_path.startswith(root + "/")

    def _explore_page(self, url, depth):
        """递归探索一个页面。depth=0 为入口页。"""
        if depth > self.config.max_depth: return
        url_key = self._norm_url_key(url)
        if url_key in self._visited_urls: return

        # ── 边界安全网：绝不探索目标模块之外的页面 ──
        if not self._is_within_module(url):
            logger.warning(f"[DFS] BLOCKED: {url[-80:]} is outside module /{self._module_url_root}")
            return

        self._visited_urls.add(url_key)

        c = self.config
        logger.info(f"[DFS d={depth}] exploring: {url[-60:]}")

        ok = self.client.goto(url)
        if not ok:
            logger.warning(f"[DFS d={depth}] goto may have failed for {url[-60:]}, verifying URL...")
            cur = self.client.get_url()
            cur_key = self._norm_url_key(cur)
            url_key_check = self._norm_url_key(url)
            if cur_key != url_key_check:
                logger.error(f"[DFS d={depth}] Wrong page! expected={url[-60:]} actual={cur[-60:]} — skipping")
                return
        # 智能等待 SPA 渲染完成（替代固定 render_wait，防止慢页面卡死）
        pt = getattr(c, 'page_ready_timeout', 12.0)
        ready = self.client.wait_for_page_ready(max_wait=pt)
        if not ready:
            logger.warning(f"[DFS d={depth}] Page not fully ready after {pt}s, continuing anyway...")
        self.client.scroll_to_load()

        # ── 定位主内容区（scope 限定——行业标准：Cypress/axe-core/Verdex）──
        self._scope_element = self.client.get_main_content()
        if self._scope_element:
            logger.info(f"[DFS d={depth}] Scope: main content area found")
        else:
            logger.info(f"[DFS d={depth}] Scope: fallback to body (no <main> detected)")

        # Phase 1: 站点地图（全页） + 无障碍树元素发现（scope 限定）
        site_map = self._phase1_site_map() if depth == 0 else {"modules": []}
        if depth == 0:
            self._site_map = site_map
            self._nav_names = {self._norm(m["name"]) for m in site_map.get("modules", [])}
        plan = self._phase1_discover(depth=depth, scope_element=self._scope_element)
        self._capture_state(f"{self._module}_d{depth}", url)

        # Phase 2: DFS 批量点击
        logger.info(f"[DFS d={depth}] Phase 2: {len(plan)} items")
        element_jumps = self._phase2_execute(plan, url, depth)

        # iframe 穿透（V5 新增）
        self._phase_iframe_scan(url, depth)

        # Phase 3: 深度探索（确保回到目标页面再开始）
        ok = self.client.goto(url)
        if not ok:
            logger.warning(f"[DFS d={depth}] Phase 3 goto failed, trying again...")
            self.client.goto(url)
        pft = getattr(c, 'page_ready_timeout_fast', 8.0)
        self.client.wait_for_page_ready(max_wait=pft)
        self.client.scroll_to_load()
        # 重新获取 scope——goto 后旧 handle 已过期
        self._scope_element = self.client.get_main_content()
        deep_dive = self._phase3_deep_dive()
        self._pages_explored.append({"url": url, "depth": depth, "elements": len(plan), "jumps": len(element_jumps), "deep_dive": deep_dive})
        self._all_element_jumps.extend(element_jumps)

        # ── 记录状态图节点（ActionEngine / profiq 模式）──
        state_node = StateNode(
            url=url,
            fingerprint=self.client.get_fingerprint(),
            actions=[e.get("name", "") for e in element_jumps if e.get("navigated")],
            children=[e.get("jump_url", "") for e in element_jumps if e.get("navigated") and e.get("jump_url")],
            deep_dive=deep_dive,
        )
        self._state_graph.append(state_node)

        self._save_results()

    # ═══════════════════════════════════════════════════════════
    # V5 新增: iframe 穿透
    # ═══════════════════════════════════════════════════════════

    def _phase_iframe_scan(self, start_url, depth):
        """扫描 iframe 内的可交互元素，点击并记录跳转。"""
        frames = self.client.scan_iframes()
        if not frames:
            return
        logger.info(f"[iframe] Found {len(frames)} iframe(s): {[f['url'][:50] for f in frames]}")

        for fi, frame_info in enumerate(frames):
            try:
                frame = self.page.frames[fi + 1]
                if frame == self.page.main_frame:
                    continue
                elements = self.client.get_iframe_elements(frame)
                if not elements:
                    continue
                self._capture_state(f"iframe_{fi}", frame.url)
                logger.info(f"[iframe] frame#{fi}: {len(elements)} elements at {frame.url[:60]}")
                # 点击 iframe 内元素并检测跳转
                for elem in elements[:10]:
                    try:
                        name = elem.get("name", "")
                        if not name: continue
                        before_u = self.client.get_url()
                        el = frame.get_by_text(name, exact=True).first
                        if el.is_visible(timeout=500):
                            el.click(force=True, timeout=2000)
                            self.client.wait(self.config.click_wait)
                            after_u = self.client.get_url()
                            if after_u and after_u != before_u:
                                logger.info(f"[iframe] frame#{fi} click '{name[:30]}' → jump")
                                self.action_count += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"[iframe] frame#{fi} error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Phase 1: 站点地图 + 无障碍树元素发现（V5 ARIA-first）
    # ═══════════════════════════════════════════════════════════

    def _phase1_site_map(self):
        """扫描导航结构（CSS fallback——导航菜单通常没有 ARIA role）。

        模块识别只认「导航区」的项：主内容区（main/[role=main] 等）内的元素是
        页面内容/功能入口（如工作台页内的功能卡片），不是独立模块——排除它们，
        否则「房颤预警」这类内容卡片会被平级误判为模块（2026-08-23 用户反馈）。
        排除容器选择器参数化（nav_exclude_containers），按项目可覆盖。
        """
        c = self.config
        modules = []
        seen = set()
        try:
            items = self.page.evaluate(f"""
                () => {{
                    const items = [];
                    const excludeSels = '{c.nav_exclude_containers}'.replace(/'/g, "\\\\'");
                    document.querySelectorAll('{c.nav_selectors}'.replace(/'/g, "\\\\'")).forEach(el => {{
                        const r = el.getBoundingClientRect();
                        if (r.width < {c.min_element_width} || r.height < {c.min_element_height}) return;
                        const text = (el.textContent || '').trim();
                        if (text.length < {c.min_text_len}) return;
                        // 主内容区内的项不是导航模块（与 get_main_content 同源选择器）
                        if (excludeSels && el.closest(excludeSels)) return;
                        let href = el.getAttribute('href') || '';
                        if (!href) {{
                            const a = el.querySelector('a[href]');
                            if (a) href = a.getAttribute('href') || '';
                        }}
                        items.push({{ name: text.substring(0, 40), href }});
                    }});
                    return items;
                }}
            """) or []
        except Exception:
            pass
        for item in items:
            name = (item.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                modules.append({"name": name, "href": item.get("href", ""), "source": "nav"})
        logger.info(f"[Phase 1] site_map: {len(modules)} nav items")
        return {"modules": modules}

    def _phase1_discover(self, depth=0, scope_element=None):
        """V6: accessibility.snapshot() 无障碍树遍历（主路径）+ CSS 回退（仅 a11y 不足时）。

        scope_element: 主内容区 ElementHandle（<main> / [role="main"]）。
                      限定后发现天然排除侧边栏 <nav>/<aside>。
        """
        action_roles = getattr(self.config, 'accessible_roles', None)
        if action_roles is None:
            action_roles = ["button", "link", "combobox", "listbox", "tab",
                            "menuitem", "textbox", "searchbox", "radio", "checkbox",
                            "option", "switch", "slider"]

        elements = []

        # ── 主路径: 无障碍树遍历（限定在主内容区内）──
        tree = self.client.get_accessibility_tree(root=scope_element)
        if tree:
            # 记录 a11y 树顶层角色分布（诊断为什么可能返回 0）
            top_roles = set()
            for child in (tree.get("children") or [])[:10]:
                top_roles.add(child.get("role", "?"))
            logger.info(f"[Phase 1] A11y tree top roles: {top_roles}, root role={tree.get('role','?')}")
            self._walk_a11y_tree(tree, elements, action_roles, depth=0)

        a11y_count = len(elements)

        # ── 回退路径: CSS 标准选择器（仅当 a11y 结果不足 < 5 时启用）──
        if a11y_count < 5:
            css_items = self._js_find(
                getattr(self.config, 'discover_selectors',
                        'button, a[href], input:not([type="hidden"]), [role="button"], [onclick], [tabindex="0"]'),
                min_text=2,
                scope_element=scope_element
            )
            a11y_names = {(e["name"], e.get("role", "")) for e in elements}
            for item in css_items:
                if (item["name"], "button") not in a11y_names and (item["name"], "link") not in a11y_names:
                    elements.append({"name": item["name"], "selector": item["selector"], "role": "button", "source": "css_fallback"})

        # ── 第三回退: 行为扫描（cursor:pointer + 可见文本）──
        # 当 a11y 和 CSS 都失败时，用 getComputedStyle 找可点击元素
        css_count = len(elements) - a11y_count
        if a11y_count + css_count == 0:
            behavior_items = self._js_find_behaviour(scope_element=scope_element)
            for item in behavior_items:
                elements.append({"name": item["name"], "selector": item.get("selector", ""), "role": "button", "source": "behavior"})

        # ── 表格行补充（Playwright row locator——表格通常无 ARIA role）──
        try:
            row_count = self.page.locator(getattr(c, 'table_row_selector', 'table tbody tr, [role="row"]')).count()
            a11y_names = {(e["name"], e.get("role", "")) for e in elements}
            for i in range(min(row_count, 50)):
                try:
                    row = self.page.locator(getattr(c, 'table_row_selector', 'table tbody tr, [role="row"]')).nth(i)
                    text = (row.inner_text() or "").strip()[:60]
                    if text and len(text) > 5:
                        key = (self._norm(text), "table-row")
                        if key not in a11y_names:
                            elements.append({"name": text, "selector": "", "role": "table-row", "source": "row_locator"})
                except Exception:
                    pass
        except Exception:
            pass

        logger.info(f"[Phase 1] A11y: {a11y_count}, CSS fallback: {len(elements) - a11y_count} (total {len(elements)})")

        # ── 去重 + 排序 ──
        unique = self._dedup_elements(elements)
        # 探索优先级：输入控件 > 下拉 > 卡片/按钮 > 表格行
        # 先探索过滤/搜索条件，再操作表格数据
        priority_order = {"input": 0, "searchbox": 0, "textbox": 0,
                          "combobox": 1, "listbox": 1,
                          "card": 2, "button": 3, "link": 3, "tab": 3,
                          "table-row": 5}
        unique.sort(key=lambda e: priority_order.get(e.get("role", ""), 4))

        # 侧边栏导航项永远不点击 —— 跨模块导航由 API 层统一调度
        # （scope 限定已天然排除大部分侧边栏元素；这里做 name-based 兜底过滤）
        nav_items = [e for e in unique if self._is_nav(e) or self._norm(e["name"]) in self._nav_names]
        plan = [e for e in unique if e not in nav_items]

        logger.info(f"[Phase 1] plan: {len(plan)} clickable + {len(nav_items)} nav(skipped, inter-module nav handled by API)")
        return plan

    def _walk_a11y_tree(self, node, results, action_roles, depth):
        """递归遍历无障碍树，收集所有匹配角色的节点。"""
        if not node or depth > 20:
            return
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()

        if role in action_roles and name and len(name) >= 2:
            if not any(kw in name for kw in self._noise_kw):
                if not any(kw in name for kw in self._danger_kw):
                    mapped_role = role
                    if role in ("textbox", "searchbox"):
                        mapped_role = "input"
                    elif role in ("radio", "checkbox"):
                        mapped_role = "form"
                    elif role == "option":
                        mapped_role = "combobox"
                    results.append({
                        "name": name[:80],
                        "selector": "",
                        "role": mapped_role,
                        "source": "a11y",
                        "a11y_depth": depth,
                    })

        for child in node.get("children") or []:
            self._walk_a11y_tree(child, results, action_roles, depth + 1)

    def _dedup_elements(self, elements):
        """去重：同名 + 同 role 保留一个；嵌套包含时保留短名。

        使用 _norm() 归一化名称后再比较，确保 "室早 室性" 和 "室早室性"
        被视为同一前缀关系。
        """
        # 第一遍：精确去重（归一化 name + role）
        seen = {}
        for e in elements:
            key = (self._norm(e["name"]), e.get("role", ""))
            if key in seen:
                # 保留名字更短的（更精确的命名）
                if len(e["name"]) < len(seen[key]["name"]):
                    seen[key] = e
                continue
            seen[key] = e
        uniq = list(seen.values())

        # 第二遍：前缀去重（归一化后比较）
        uniq.sort(key=lambda x: len(x["name"]))
        final = []
        for e in uniq:
            add = True
            for existing in list(final):
                e_norm = self._norm(e["name"])
                ex_norm = self._norm(existing["name"])
                # 新元素归一化后包含已有元素 → 跳过（已有更短）
                if len(e_norm) >= len(ex_norm) and e_norm.startswith(ex_norm):
                    add = False
                    break
                # 已有元素归一化后包含新元素 → 替换（新元素更短）
                if len(ex_norm) > len(e_norm) and ex_norm.startswith(e_norm):
                    final.remove(existing)
                    add = True
                    break
            if add:
                final.append(e)
        return final

    def _js_find_behaviour(self, scope_element=None):
        """通用行为扫描——不依赖 class/css/框架，只靠浏览器原生 API。

        扫描主内容区中 cursor:pointer 且有可见文本的元素。
        适用场景：a11y 树和标准 CSS 选择器都返回空时（如 React 纯 div 卡片）。
        """
        try:
            js = """
                (scopeEl) => {
                    const root = scopeEl || document;
                    const found = []; const seen = new Set();
                    const all = root.querySelectorAll('*');
                    for (const el of all) {
                        if (el.offsetParent === null) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width < 20 || r.height < 12 || r.x < 0 || r.y < 0) continue;
                        const cs = getComputedStyle(el);
                        if (cs.cursor !== 'pointer') continue;
                        const text = (el.textContent || '').trim();
                        if (!text || text.length < 2 || text.length > 60) continue;
                        // 跳过纯文本节点（无交互语义）
                        const tag = el.tagName.toLowerCase();
                        if (tag === 'body' || tag === 'html' || tag === 'main') continue;
                        // 只拿最内层可点击元素
                        let leaf = el;
                        for (const child of el.querySelectorAll('*')) {
                            if (getComputedStyle(child).cursor === 'pointer' && child.offsetParent !== null) {
                                leaf = child;
                            }
                        }
                        const leafText = (leaf.textContent || '').trim().substring(0, 80);
                        if (leafText && !seen.has(leafText)) {
                            seen.add(leafText);
                            found.push({n: leafText, s: leaf.tagName.toLowerCase()});
                        }
                    }
                    return found.slice(0, 100);
                }
            """
            items = self.page.evaluate(js, scope_element) or []
            out = []
            for i in items:
                n = (i.get("n") or "").strip()
                if len(n) < 2: continue
                if re.match(r'^[\d\s\.\+\-\/\%\:]+$', n): continue
                if any(kw in n for kw in self._noise_kw): continue
                out.append({"name": n, "selector": i.get("s", "")})
            return out
        except Exception:
            return []

    def _js_find(self, css_selector, min_text=4, scope_element=None):
        """通用 JS 元素发现回退（CSS 选择器扫描）。

        scope_element: 限定扫描范围的 ElementHandle（主内容区）。
                      行业标准：Cypress .within() / axe-core include / Verdex container。
        """
        sel = css_selector.replace("'", "\\'")
        try:
            js_code = f"""
                (scopeEl) => {{
                    const root = scopeEl || document;
                    const found = []; const seen = new Set();
                    root.querySelectorAll('{sel}').forEach(el => {{
                        const r = el.getBoundingClientRect();
                        if (r.width < 15 || r.height < 10 || el.offsetParent === null) return;
                        let t = (el.textContent || el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                        if (t && t.length < 2) t = '';
                        if (!t) {{
                            const parent = el.closest('button,a,label,[role="button"],[role="link"],[tabindex="0"]');
                            if (parent) t = (parent.textContent || '').trim().substring(0, 40);
                        }}
                        if (!t || seen.has(t)) return; seen.add(t);
                        let css = el.tagName.toLowerCase();
                        if (el.id) css = '#' + el.id;
                        else if (el.className && typeof el.className === 'string') {{
                            const c = el.className.split(/\\s+/).filter(x => x && x.length > 1 && x.length < 40 && /^[a-zA-Z_-]/.test(x) && /^[a-zA-Z0-9_-]+$/.test(x))[0];
                            if (c) css = el.tagName.toLowerCase() + '.' + c;
                        }}
                        found.push({{n: t.substring(0, 80), s: css}});
                    }});
                    return found;
                }}
            """
            items = self.page.evaluate(js_code, scope_element) or []
        except Exception:
            return []
        out = []
        for i in items:
            n = (i.get("n") or "").strip()
            if len(n) < min_text: continue
            if re.match(r'^[\d\s\.\+\-\/\%\:]+$', n): continue
            if any(kw in n for kw in self._noise_kw): continue
            if any(kw in n for kw in self._danger_kw): continue
            out.append({"name": n, "selector": i.get("s", "")})
        return out

    def _is_nav(self, item):
        return item.get("role") in self._nav_roles

    def _capture_state(self, label, url=None):
        """捕获当前页面状态：URL + 主内容区可见交互元素 + 弹窗元素。

        使用 self._scope_element 限定范围。若 scope 过期（页面跳转后）则自动回退全页。
        """
        import os, json as _json
        url = url or self.client.get_url()
        sel = (getattr(self.config, 'behavior_selectors',
                'button, a[href], input:not([type="hidden"]), select, textarea, '
                '[role="button"], [role="link"], [role="combobox"], [role="listbox"], '
                '[role="tab"], [role="textbox"], [role="searchbox"], [role="switch"], '
                '[onclick], [tabindex="0"]')).replace("'", "\\'")
        js_body = f"""
            (scopeEl) => {{
                const root = scopeEl || document;
                const results = [];
                root.querySelectorAll('{sel}').forEach(el => {{
                    if (el.offsetParent === null) return;
                    const r = el.getBoundingClientRect();
                    if (r.width < 15 || r.height < 10) return;
                    const text = (el.textContent || '').trim().substring(0, 80);
                    if (!text) return;
                    results.push({{
                        tag: el.tagName,
                        role: el.getAttribute('role') || '',
                        cls: (el.className || '').toString().substring(0, 100),
                        text: text,
                        onclick: !!el.getAttribute('onclick'),
                        href: el.getAttribute('href') || '',
                        size: Math.round(r.width) + 'x' + Math.round(r.height),
                    }});
                }});
                return results.slice(0, 200);
            }}
        """
        elements = []
        # 先尝试 scoped（ElementHandle 可能在页面跳转后过期）
        if self._scope_element is not None:
            try:
                elements = self.page.evaluate(js_body, self._scope_element) or []
            except Exception:
                pass  # scope 过期，回退到全页
        if not elements:
            try:
                elements = self.page.evaluate(js_body, None) or []
            except Exception:
                pass

        # 弹窗/浮层内的元素（选择器从 config 读取）
        overlay_sel = (getattr(self.config, 'modal_selectors',
                        '[role="dialog"]:not([style*="display: none"]), [class*="modal"]:not([style*="display: none"])'))
        overlay_sel = overlay_sel.replace("'", "\\'")
        overlay_els = self.page.evaluate(f"""
            () => {{
                const results = [];
                document.querySelectorAll('{overlay_sel}').forEach(container => {{
                    container.querySelectorAll('button, a, input, select, [onclick], [role="button"]').forEach(el => {{
                        if (el.offsetParent === null) return;
                        const t = (el.textContent || '').trim().substring(0, 60);
                        if (!t) return;
                        results.push({{
                            tag: el.tagName,
                            text: t,
                            cls: (el.className || '').toString().substring(0, 80),
                        }});
                    }});
                }});
                return results.slice(0, 50);
            }}
        """) or []

        result_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tests", "exploration", "states", self._module))
        os.makedirs(result_dir, exist_ok=True)
        # Windows 文件名非法字符 = 路径分隔/保留符 + 控制字符（\n\r\t 等，0x00-0x1f/0x7f）。
        # 2026-08-24 实证：target 为多行文本（子菜单「数据管理\n文件审核\n…」）时旧 sanitize
        # 只过滤 \\/:*?"<>|，漏掉 \n → open() 抛 Errno 22 → explore_guided 循环中断，
        # 99 步只执行 35 步，剩余步骤从未探索（批量转化 58/63 steps_missing 连锁根因）。
        safe_label = re.sub(r'[\x00-\x1f\x7f\\/:*?"<>| ]', '_', label)[:50]
        self._state_counter += 1
        state_file = os.path.join(result_dir, f"{self._state_counter:04d}_{safe_label}.json")
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                _json.dump({
                    "label": label,
                    "url": url,
                    "total_elements": len(elements),
                    "elements": elements,
                    "overlay_elements": overlay_els,
                }, f, ensure_ascii=False, indent=2)
        except OSError as _se:
            # 快照写盘失败只丢该状态快照，绝不中断探索主流程
            # （2026-08-24 实证：写盘异常上抛 → guided 循环整体中断，后 61 步未探索）
            logger.warning(f"[Agent] State 快照写盘失败（跳过该快照，不中断探索）: {_se}")
            return
        # V6: 更新 visited_states（State Graph 状态追踪）
        self.visited_states[self._norm_url_key(url)] = True
        logger.info(f"[Agent] State captured: {state_file} ({len(elements)} elements, {len(overlay_els)} overlay)")

    # ═══════════════════════════════════════════════════════════
    # V6: 表单交互方法（行业标准：WALT/Scry/VETL 均把表单作为一等交互）
    # ═══════════════════════════════════════════════════════════

    def _fill_input(self, name, role):
        """填充文本输入框。role 为 input/textbox/searchbox 时触发。"""
        c = self.config
        test_vals = getattr(c, 'form_fill_values', ['test', '测试', 'admin'])
        try:
            # 优先 role locator
            mapped = {"input": "textbox", "textbox": "textbox", "searchbox": "searchbox"}
            r = mapped.get(role, "textbox")
            el = self.page.get_by_role(r, name=name).first
            if el.is_visible():
                el.fill(test_vals[0])
                logger.info(f"[Phase 2] FILL {name[:20]} = '{test_vals[0]}'")
                return True
        except Exception:
            pass
        # 回退：placeholder / label 匹配
        try:
            el = self.page.get_by_placeholder(name).first
            if el.is_visible():
                el.fill(test_vals[0])
                return True
        except Exception:
            pass
        try:
            el = self.page.get_by_label(name).first
            if el.is_visible():
                el.fill(test_vals[0])
                return True
        except Exception:
            pass
        return False

    def _select_combobox(self, name):
        """打开并选择下拉框的第一个可见选项。"""
        c = self.config
        try:
            # 安全转义：name 可能含引号等特殊字符
            safe_name = name.replace('"', '').replace("'", '')[:30]
            trigger = self.page.get_by_role("combobox", name=safe_name).first
            if not trigger.is_visible():
                fb = getattr(c, 'combobox_fallback', '[class*="select"]')
                trigger = self.page.locator(f'{fb}:has-text("{safe_name}")').first
            trigger.click(force=True, timeout=2000)
            self.client.wait(c.dropdown_wait)
            # 选第一个可见选项
            opt_fb = getattr(c, 'option_fallback', '[class*="option"]')
            opts = self.page.locator(f'[role="option"]:visible, {opt_fb}:visible')
            cnt = opts.count()
            if cnt > 0:
                opts.first.click(force=True, timeout=2000)
                logger.info(f"[Phase 2] SELECT {name[:20]} → option 1/{cnt}")
                return True
            self.client.press_escape()
        except Exception:
            pass
        return False

    def _find_and_click_search(self):
        """查找并点击搜索按钮——限定在主内容区内。关键词从 config 读取。"""
        c = self.config
        kws = getattr(c, 'search_button_keywords', None) or ['search', 'query', 'filter']
        selectors = 'button, [role="button"]'
        max_items = getattr(c, 'max_loop_items', 50)
        sidebar_edge = getattr(c, 'sidebar_max_x', 280)
        try:
            buttons = self.page.locator(selectors)
            count = buttons.count()
            for i in range(min(count, max_items)):
                try:
                    btn = buttons.nth(i)
                    if not btn.is_visible():
                        continue
                    box = btn.bounding_box()
                    if box and box['x'] < sidebar_edge:
                        continue
                    text = (btn.inner_text() or '').strip()
                    if any(kw in text for kw in kws):
                        btn.click(force=True, timeout=2000)
                        self.client.wait(c.click_wait)
                        logger.info(f"[Phase 2] SEARCH clicked: '{text[:c.max_text_display]}'")
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    # ═══════════════════════════════════════════════════════════
    # Phase 2: 表单交互 → 搜索 → 卡片点击 → 表格行
    # ═══════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════
    # V6: Action Vocabulary — 标准动作抽象接入执行管线
    # ═══════════════════════════════════════════════════════════

    def _to_action(self, item: dict) -> Action:
        """将 Phase 1 发现的元素 dict 转换为标准 Action 对象。"""
        role = item.get("role", "button")
        name = item.get("name", "")
        return Action(
            type=self.ROLE_TO_ACTION.get(role, ActionType.CLICK),
            label=name,
            target_text=name,
            target_role=role,
            target_selector=item.get("selector", ""),
            source=item.get("source", ""),
        )

    def _execute_action(self, action: Action) -> ActionResult:
        """按 ActionType 分发到对应 handler。"""
        handler_map = {
            ActionType.FILL: self._handle_fill,
            ActionType.SELECT: self._handle_select,
            ActionType.CLICK: self._handle_click,
            ActionType.NAVIGATE: self._handle_click,
            ActionType.TAB_SWITCH: self._handle_tab_switch,
            ActionType.TABLE_ROW: self._handle_click,
            ActionType.HOVER: self._handle_hover,
            ActionType.RIGHT_CLICK: self._handle_right_click,
        }
        handler = handler_map.get(action.type)
        if handler:
            return handler(action)
        return ActionResult(action=action, success=False, error=f"No handler for {action.type}")

    # ── Action handlers ──

    def _handle_fill(self, action: Action) -> ActionResult:
        ok = self._fill_input(action.target_text, action.target_role)
        self.action_count += 1
        return ActionResult(action=action, success=ok)

    def _handle_select(self, action: Action) -> ActionResult:
        ok = self._select_combobox(action.target_text)
        self.action_count += 1
        return ActionResult(action=action, success=ok)

    def _handle_click(self, action: Action) -> ActionResult:
        """点击按钮/卡片元素（3 阶段自愈）。"""
        name = action.target_text
        role = action.target_role
        clicked = False
        # 1. role locator
        role_map = {"button": "button", "link": "link", "tab": "tab"}
        mapped = role_map.get(role, "")
        if mapped:
            try:
                el = self.page.get_by_role(mapped, name=name).first
                if el.is_visible():
                    el.click(force=True, timeout=2000)
                    clicked = True
            except Exception:
                pass
        # 2. 文本匹配
        if not clicked:
            try:
                self._click_by_text(name, role)
                clicked = True
            except Exception:
                pass
        # 3. JS TreeWalker 回退
        if not clicked:
            try:
                clicked = self.page.evaluate(f"""
                    (text) => {{
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                        while (walker.nextNode()) {{
                            const el = walker.currentNode;
                            if (el.offsetParent === null || el.children.length > 1) continue;
                            if ((el.textContent||'').trim() === text) {{
                                (el.closest('li') || el.closest('button') || el.closest('[onclick]') || el).click();
                                return true;
                            }}
                        }}
                        return false;
                    }}
                """, name)
            except Exception:
                pass

        self.action_count += 1
        return ActionResult(action=action, success=clicked,
                          error="" if clicked else "all click strategies failed")

    # _handle_navigate 合并到 _handle_click：link/nav/menuitem 点击后由调用方检测 URL 变化
    # NAVIGATE → CLICK 映射通过 _execute_action 中的 handler_map 直接路由到 _handle_click

    def _handle_tab_switch(self, action: Action) -> ActionResult:
        """切换 Tab。"""
        try:
            self.page.get_by_role("tab", name=action.target_text).first.click(force=True, timeout=2000)
            self.action_count += 1
            return ActionResult(action=action, success=True)
        except Exception:
            return ActionResult(action=action, success=False, error="Tab switch failed")

    def _handle_hover(self, action: Action) -> ActionResult:
        """悬浮——触发 hover 菜单/提示。"""
        try:
            el = self.page.get_by_text(action.target_text, exact=True).first
            if el.is_visible():
                el.hover()
                self.action_count += 1
                return ActionResult(action=action, success=True)
        except Exception:
            pass
        return ActionResult(action=action, success=False, error="Hover failed")

    def _handle_right_click(self, action: Action) -> ActionResult:
        """右键点击——触发上下文菜单。"""
        try:
            el = self.page.get_by_text(action.target_text, exact=True).first
            if el.is_visible():
                el.click(button="right")
                self.action_count += 1
                return ActionResult(action=action, success=True)
        except Exception:
            pass
        return ActionResult(action=action, success=False, error="Right-click failed")

    # ═══════════════════════════════════════════════════════════

    def _phase2_execute(self, plan, start_url, depth=0):
        c = self.config
        results = []
        action_fingerprints = set()

        # 确保在第一个 Tab 上
        try:
            tab_active = getattr(c, 'tab_active', '[role="tab"][aria-selected="true"]')
            self.page.locator(tab_active).first.click(force=True, timeout=2000)
            self.client.wait(1)
        except Exception: pass

        # ═══════════════════════════════════════════════════════
        # Step A: 表单交互（FILL + SELECT → 搜索按钮）
        # ═══════════════════════════════════════════════════════
        # 将 dict plan 转为 Action 对象
        all_actions = [self._to_action(it) for it in plan]
        form_actions = [a for a in all_actions if a.type in (ActionType.FILL, ActionType.SELECT)]
        click_actions = [a for a in all_actions if a.type not in (ActionType.FILL, ActionType.SELECT)]

        search_clicked = False
        if form_actions:
            logger.info(f"[Phase 2] Form interaction: {len(form_actions)} fields")
            for action in form_actions[:c.max_form_fields]:
                if not action.target_text: continue
                result = self._execute_action(action)
                results.append({
                    "name": action.target_text, "clicked": result.success,
                    "navigated": False, "role": action.target_role,
                })

            # 填完表单 → 点搜索
            search_clicked = self._find_and_click_search()
            if search_clicked:
                self.action_count += 1
                self.client.wait_for_page_ready(max_wait=getattr(c, 'page_ready_timeout_fast', 8.0))
                self.client.scroll_to_load()
                self._scope_element = self.client.get_main_content()
                self._capture_state(f"search_results", self.client.get_url())
                new_plan = self._phase1_discover(depth=depth, scope_element=self._scope_element)
                # 合并新发现的非表单、非表格行元素
                existing = {(a.target_text, a.target_role) for a in click_actions}
                for new_item in new_plan:
                    new_action = self._to_action(new_item)
                    if new_action.type in (ActionType.FILL, ActionType.SELECT, ActionType.TABLE_ROW):
                        continue
                    key = (new_action.target_text, new_action.target_role)
                    if key not in existing:
                        existing.add(key)
                        click_actions.append(new_action)
                logger.info(f"[Phase 2] After search: {len(click_actions)} clickable items (+{len(new_plan)} new)")

        # ═══════════════════════════════════════════════════════
        # Step B: 卡片/按钮点击（CLICK / NAVIGATE / TAB_SWITCH）
        # ═══════════════════════════════════════════════════════
        click_actions = [a for a in click_actions if a.type != ActionType.TABLE_ROW]
        for i, action in enumerate(click_actions[:c.max_clicks]):
            if self.action_count >= c.max_clicks:
                break
            name = action.target_text[:60]
            if not name: continue
            afp = f"{start_url}|{self._norm(name)}"
            if afp in action_fingerprints: continue
            action_fingerprints.add(afp)
            before_fp = self.client.get_fingerprint_dict()
            before_url = self.client.get_url()

            logger.info(f"[Phase 2] [{i+1}/{min(len(click_actions),c.max_clicks)}] "
                        f"{action.type.value}:{name[:40]} | before={before_url[-60:]}")
            item_role = action.target_role

            try:
                # V6: 通过 Action Vocabulary 分发执行（内置 3 阶段自愈）
                result = self._execute_action(action)
                if not result.success:
                    results.append({
                        "name": name, "clicked": False, "navigated": False,
                        "role": action.target_role, "error": result.error,
                    })
                    continue

                self.client.wait(c.click_wait)

                after_fp = self.client.get_fingerprint_dict()
                after_url = self.client.get_url()
                console_errors = self.client.collect_console_errors()
                diff = self._fingerprint_diff(before_fp, after_fp)

                url_changed = self._norm_url_key(after_url) != self._norm_url_key(before_url) and after_url != "about:blank"
                overlay = diff is not None and (before_fp.get("nodes", 0) != after_fp.get("nodes", 0))

                logger.info(f"[Phase 2]   after={after_url[-60:]} | url_changed={url_changed} overlay={overlay}")

                self._click_log.append({"name": name, "before": before_url, "after": after_url, "result": "jump" if url_changed else ("overlay" if overlay else "static")})
                if url_changed:
                    self._capture_state(name, after_url)
                    results.append({"name": name, "clicked": True, "navigated": True,
                                    "jump_url": after_url, "role": action.target_role,
                                    "action_type": action.type.value,
                                    "diff": diff, "console_errors": console_errors})
                    logger.info(f"[Phase 2] JUMP: {name[:30]} -> {after_url[-60:]}")
                    should_explore = self._is_within_module(after_url)
                    if depth < c.max_depth and should_explore:
                        url_key = self._norm_url_key(after_url)
                        if url_key not in self._visited_urls:
                            logger.info(f"[Phase 2] Exploring sub-page: {name[:30]}")
                            self._explore_page(after_url, depth + 1)
                    self._return_to_page(start_url, after_url)
                elif overlay:
                    self._capture_state(name, after_url)
                    results.append({"name": name, "clicked": True, "navigated": True,
                                    "interaction_type": "overlay", "diff": diff, "console_errors": console_errors})
                    logger.info(f"[Phase 2] OVERLAY: {name[:30]}")
                    # 弹窗交互：扫描弹窗内表单 → 填写 → 关闭
                    self._interact_modal()
                    self.client.press_escape()
                    self.client.wait(c.dropdown_wait)
                else:
                    # 不跳转 → 末尾N字 + 分隔符拆解重试
                    sub_candidates = []
                    retry_lens = getattr(c, 'sub_name_retry_lengths', [4, 3, 2])
                    min_sl = getattr(c, 'sub_name_min_len', 2)
                    if len(name) > min_sl:
                        for n in retry_lens:
                            if n > len(name): continue
                            sub = name[-n:]
                            if sub != name and sub not in sub_candidates:
                                sub_candidates.append(sub)
                    max_sl = getattr(c, 'sub_name_max_len', 4)
                    for sep in ['---', '--', ' - ', '-', ' ']:
                        for p in name.split(sep):
                            p = p.strip()
                            if min_sl <= len(p) <= max_sl and p not in sub_candidates:
                                sub_candidates.append(p)
                    retry_ok = False
                    for sub in sub_candidates:
                        try:
                            btn = self.page.get_by_text(sub, exact=False).first
                            if btn.is_visible():
                                btn.click(force=True, timeout=2000)
                        except Exception:
                            continue
                        self.client.wait(c.click_wait)
                        after_url2 = self.client.get_url()
                        if after_url2 and self._norm_url_key(after_url2) != self._norm_url_key(before_url):
                            self._capture_state(f"{name}_via_{sub}", after_url2)
                            results.append({"name": name, "clicked": True, "navigated": True, "jump_url": after_url2})
                            logger.info(f"[Phase 2] SUB JUMP: {name[:30]} (via :text('{sub}')) -> {after_url2[-60:]}")
                            if depth < c.max_depth and self._is_within_module(after_url2):
                                url_key = self._norm_url_key(after_url2)
                                if url_key not in self._visited_urls:
                                    self._explore_page(after_url2, depth + 1)
                            self._return_to_page(start_url, after_url2)
                            retry_ok = True
                            break
                    if not retry_ok:
                        results.append({"name": name, "clicked": True, "navigated": False})
            except Exception as e:
                logger.warning(f"[Phase 2] ERROR {name[:30]}: {e}")
                results.append({"name": name, "clicked": False, "navigated": False, "error": str(e)[:100]})
                try:
                    self.client.goto(start_url); self.client.wait_for_page_ready(max_wait=getattr(c, 'page_ready_timeout_fast', 8.0))
                except Exception:
                    pass

        # Playwright get_by_role("row") 表格行逐行迭代
        try:
            rows = self.page.get_by_role('row').all()
            logger.info(f"[Phase 2] Table rows: {len(rows)}")
            # 安全检查：收集所有行的 danger 文本，提前发现危险页面
            all_danger = set()
            danger_kws = self._danger_kw
            for row in rows:
                try:
                    row_text = (row.inner_text() or "").strip()
                    for kw in danger_kws:
                        if kw in row_text:
                            all_danger.add(kw)
                except Exception:
                    pass
            if all_danger:
                logger.warning(f"[Phase 2] DANGER keywords found in table: {all_danger} — "
                               f"skipping ALL table row clicks to prevent data loss")
                rows = []  # 清空行列表，跳过所有表格操作
            for i, row in enumerate(rows):
                if i == 0: continue
                try:
                    action_cell = getattr(c, 'table_action_cell', 'td:last-child')
                    cell = row.locator(action_cell).first
                    if not cell.is_visible(): continue
                    cell_text = (cell.inner_text() or "").strip()
                    # 如果 cell 文本为空（图标按钮），检查按钮 title/aria-label
                    if not cell_text:
                        try:
                            btn = cell.locator('button').first
                            cell_text = (btn.get_attribute('title') or
                                        btn.get_attribute('aria-label') or
                                        (btn.inner_text() or "").strip())
                        except Exception:
                            pass
                    # 安全检查
                    if any(kw in cell_text for kw in danger_kws):
                        logger.info(f"[Phase 2] SKIP row#{i} (danger: {cell_text[:30]})")
                        continue
                    before_u = self.client.get_url()
                    cell.click(force=True, timeout=2000)
                    self.client.wait(c.click_wait)
                    after_u = self.client.get_url()
                    if after_u and after_u != before_u:
                        self._capture_state(f"row_{i}", after_u)
                        results.append({"name": f"表格行#{i}", "clicked": True, "navigated": True, "jump_url": after_u})
                        logger.info(f"[Phase 2] TABLE row#{i} -> {after_u[-60:]}")
                        self._click_log.append({"name": f"表格行#{i}", "before": before_u, "after": after_u, "result": "jump"})
                        self.action_count += 1
                        if self._is_within_module(after_u):
                            uk = self._norm_url_key(after_u)
                            if uk not in self._visited_urls and depth < c.max_depth:
                                self._explore_page(after_u, depth + 1)
                        self._return_to_page(start_url, after_u)
                except Exception:
                    continue
        except Exception:
            pass

        # Tab 逐页探索（先收集文本再点击，避免 DOM 变化后 locator 失效）
        try:
            tab_inactive = getattr(c, 'tab_inactive', '[role="tab"]:not([aria-selected="true"])')
            inactive_locator = self.page.locator(tab_inactive)
            tab_count = inactive_locator.count()
            max_t = getattr(c, 'max_tabs', 15)

            # 先收集所有非活跃 tab 的文本（在 DOM 变化前）
            tab_texts = []
            for ti in range(min(tab_count, max_t)):
                try:
                    t = (inactive_locator.nth(ti).inner_text() or "").strip()[:30]
                    if t:
                        tab_texts.append(t)
                except Exception:
                    pass

            logger.info(f"[Phase 2] Tab iteration: {len(tab_texts)} inactive tabs: {tab_texts}")

            # 用文本逐一切换（不受 DOM 顺序变化影响）
            for tab_text in tab_texts:
                try:
                    self.page.get_by_text(tab_text, exact=True).first.click(force=True, timeout=2000)
                    self.client.wait(1.5)
                    self._capture_state(f"tab_{tab_text}", self.client.get_url())

                    # 扫描该 Tab 下的表格行（带安全检查）
                    rows = self.page.get_by_role('row').all()
                    danger_kws = self._danger_kw
                    # 预扫描：发现危险关键词则跳过整个 Tab 的表格操作
                    tab_has_danger = False
                    for row in rows:
                        try:
                            row_text = (row.inner_text() or "")
                            if any(kw in row_text for kw in danger_kws):
                                tab_has_danger = True
                                break
                        except Exception: pass
                    if tab_has_danger:
                        logger.warning(f"[Phase 2] Tab '{tab_text}': danger keywords detected, skipping all rows")
                        continue
                    for ri, row in enumerate(rows):
                        if ri == 0: continue
                        try:
                            action_cell = getattr(c, 'table_action_cell', 'td:last-child')
                            cell = row.locator(action_cell).first
                            if not cell.is_visible(): continue
                            cell_text = (cell.inner_text() or "").strip()
                            if not cell_text:
                                try:
                                    btn = cell.locator('button').first
                                    cell_text = (btn.get_attribute('title') or
                                                btn.get_attribute('aria-label') or
                                                (btn.inner_text() or "").strip())
                                except Exception: pass
                            if any(kw in cell_text for kw in danger_kws):
                                continue
                            before_u = self.client.get_url()
                            cell.click(force=True, timeout=2000)
                            self.client.wait(c.click_wait)
                            after_u = self.client.get_url()
                            if after_u and after_u != before_u:
                                self._capture_state(f"tab_{tab_text}_row_{ri}", after_u)
                                results.append({"name": f"Tab{tab_text}行#{ri}", "clicked": True, "navigated": True, "jump_url": after_u})
                                self._click_log.append({"name": f"Tab{tab_text}行#{ri}", "before": before_u, "after": after_u, "result": "jump"})
                                self.action_count += 1
                                if self._is_within_module(after_u):
                                    uk = self._norm_url_key(after_u)
                                    if uk not in self._visited_urls and depth < c.max_depth:
                                        self._explore_page(after_u, depth + 1)
                                self._return_to_page(start_url, after_u)
                                # 回到当前 Tab
                                try: self.page.get_by_text(tab_text, exact=True).first.click(force=True, timeout=2000); self.client.wait(1)
                                except Exception: pass
                        except Exception:
                            continue
                except Exception:
                    continue

            # 回到第一个 Tab
            try:
                tab_active = getattr(c, 'tab_active', '[role="tab"][aria-selected="true"]')
                first_tab = self.page.locator(tab_active).first
                first_tab_text = (first_tab.inner_text() or "").strip()
                if first_tab_text:
                    self.page.get_by_text(first_tab_text, exact=True).first.click(force=True, timeout=2000)
                else:
                    first_tab.click(force=True, timeout=2000)
                self.client.wait(1)
            except Exception: pass
        except Exception:
            pass

        return results

    def _click_by_text(self, text, role_hint=""):
        """Playwright 原生点击：优先 role locator，其次文本匹配，最后 JS 回退。"""
        if not text or len(text) < 2: return

        # 1. 有 role_hint → 优先 get_by_role
        role_map = {"combobox": "combobox", "button": "button", "link": "link", "tab": "tab", "table-row": "row", "nav": "menuitem"}
        mapped = role_map.get(role_hint, "")
        if mapped:
            try:
                el = self.page.get_by_role(mapped, name=text).first
                if el.is_visible():
                    el.click(force=True, timeout=1000)
                    return
            except Exception:
                pass

        # 2. 表格行优先
        try:
            row = self.page.get_by_role('row').filter(has_text=text).first
            if row.is_visible():
                row.click(force=True, timeout=1000)
                return
        except Exception:
            pass

        # 3. 文本匹配（用标准选择器 + 前缀匹配，不含 class 通配）
        c = self.config
        safe = text[:c.max_name_length].replace("\\", "\\\\").replace("'", "\\'")
        sel = (getattr(c, 'click_selectors',
                'button, a[href], [role="button"], [role="link"], [onclick], [tabindex="0"]')).replace("'", "\\'")
        min_w = getattr(c, 'min_element_width', 20)
        min_h = getattr(c, 'min_element_height', 10)
        found = self.page.evaluate(f"""
            () => {{
                const all = document.querySelectorAll('{sel}');
                let best = null, bestArea = Infinity;
                for (const el of all) {{
                    if (el.offsetParent === null) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < {min_w} || r.height < {min_h}) continue;
                    const t = (el.textContent || '').trim();
                    if (!t.startsWith('{safe}')) continue;
                    const area = r.width * r.height;
                    if (area < bestArea) {{ best = el; bestArea = area; }}
                }}
                if (!best) return null;
                best.scrollIntoView({{block:'center',behavior:'instant'}});
                best.setAttribute('data-mcp-target', '1');
                return 'ok';
            }}
        """)
        if found:
            try:
                self.page.locator('[data-mcp-target="1"]').first.click(force=True, timeout=2000)
            except Exception: pass
            try:
                self.page.evaluate("() => { const el = document.querySelector('[data-mcp-target=\"1\"]'); if (el) el.removeAttribute('data-mcp-target'); }")
            except Exception: pass

    # ═══════════════════════════════════════════════════════════
    # Phase 3: 深度探索（配置驱动的通用选择器）
    # ═══════════════════════════════════════════════════════════

    def _phase3_deep_dive(self, interactive: bool = True):
        """Phase 3 深度探索。

        Args:
            interactive: 是否执行交互（点击弹窗触发器/逐页翻页）。
                BFS 全量探索默认 True；步骤驱动探索按配置
                guided_p3_interactive 决定（默认 False——交互已由引导循环完成，
                P3 只做静态统计，避免步骤后重复点击改变页面状态）。
        """
        return {
            "dropdowns": self._p3_dropdowns(interactive=interactive),
            "modals": self._p3_modals() if interactive else {},
            "tables": self._p3_tables(),
            "pagination": self._p3_pagination(interactive=interactive),
            "forms": self._p3_forms(),
            "api_endpoints": self._p3_api_endpoints(),
        }

    def _p3_pagination(self, interactive: bool = True):
        """扫描分页控件 + 逐页点击，记录每页表格行数；无数据时停止。

        Args:
            interactive: False 时仅静态扫描页码并记录当前页行数，不逐页点击
                （步骤驱动场景下翻页交互已由引导循环执行，P3 不再改变页面状态）。
        """
        c = self.config
        # 第一步：扫描页码
        try:
            pag_sel = getattr(c, 'pagination_selectors', '[class*="pagination"] li, [class*="pager"] li')
            pag_sel = pag_sel.replace("'", "\\'")
            page_items = self.page.evaluate(f"""
                () => {{
                    const results = [];
                    document.querySelectorAll('{pag_sel}').forEach(el => {{
                        const t = (el.textContent || '').trim();
                        if (t && t.length < 10 && /^\d+$/.test(t)) results.push(t);
                    }});
                    return [...new Set(results)].slice(0, 20);
                }}
            """) or []
        except Exception:
            page_items = []

        page_results = []
        if not page_items:
            # 单页表格，统计行数即可
            try:
                row_count = self.page.locator('[role="row"], tbody tr').count()
                page_results.append({"page": 1, "rows": max(0, row_count - 1)})
            except Exception:
                pass
            return {"pages": page_items, "page_count": len(page_items), "page_results": page_results}

        logger.info(f"[Phase 3] Pagination: {len(page_items)} pages to explore")

        # 第二步：先记录第 1 页的数据行数
        try:
            rows = self.page.locator('[role="row"], tbody tr').count()
            page_results.append({"page": 1, "rows": max(0, rows - 1)})
        except Exception:
            pass

        if interactive:
            # 第三步：逐页点击（最多 10 页），检查数据
            clicked_pages = set()
            for page_num in page_items[:10]:
                try:
                    num = int(page_num)
                except ValueError:
                    continue
                if num <= 1 or num in clicked_pages:
                    continue
                clicked_pages.add(num)

                try:
                    # 点击页码——优先精确匹配（避免 :has-text("2") 匹配 "12"/"20"）
                    btn = self.page.get_by_text(str(num), exact=True).first
                    if not btn.is_visible(timeout=500):
                        # 回退：class 分页器内匹配
                        btn = self.page.locator(f'[class*="pagination"] :has-text("{num}"), [class*="pager"] :has-text("{num}")').first
                    if not btn.is_visible(timeout=500):
                        continue
                    btn.click(force=True, timeout=2000)
                    self.client.wait_for_page_ready(max_wait=getattr(c, 'page_ready_timeout_fast', 8.0))

                    # 检查该页是否有数据行
                    rows = self.page.locator('[role="row"], tbody tr').count()
                    data_rows = max(0, rows - 1)  # 减去表头
                    page_results.append({"page": num, "rows": data_rows})
                    self._capture_state(f"page_{num}", self.client.get_url())

                    if data_rows == 0:
                        logger.info(f"[Phase 3] Page {num}: no data rows, stopping pagination")
                        break
                    logger.info(f"[Phase 3] Page {num}: {data_rows} data rows")
                except Exception as e:
                    logger.debug(f"[Phase 3] Page {num} error: {e}")
                    continue

            # 回到第 1 页（后续 _p3_dropdowns/_p3_tables 需要正确的页面）
            if len(page_items) > 1 and len(clicked_pages) > 0:
                try:
                    btn = self.page.get_by_text("1", exact=True).first
                    if btn.is_visible(timeout=500):
                        btn.click(force=True, timeout=2000)
                        self.client.wait_for_page_ready(max_wait=getattr(c, 'page_ready_timeout_fast', 8.0))
                except Exception:
                    pass

        return {"pages": page_items, "page_count": len(page_items), "page_results": page_results}

    def _p3_forms(self):
        c = self.config
        try:
            form_sel = getattr(c, 'form_selectors',
                'input[type="radio"]:not([disabled]), input[type="checkbox"]:not([disabled]), input[type="text"]:not([disabled]), input:not([type]):not([disabled]), textarea:not([disabled])')
            form_sel = form_sel.replace("'", "\\'")
            forms = self.page.evaluate(f"""
                () => {{
                    const results = {{ radios: [], checkboxes: [], datepickers: [], inputs: [] }};
                    document.querySelectorAll('{form_sel}').forEach(el => {{
                        const tag = el.tagName;
                        const t = el.getAttribute('type') || '';
                        const placeholder = el.getAttribute('placeholder') || '';
                        const name = el.getAttribute('name') || '';
                        const label = el.closest('label') ? (el.closest('label').textContent || '').trim().substring(0, 40) : '';
                        const value = el.value || '';
                        const checked = el.checked || false;
                        if (t === 'radio') results.radios.push({{ label, value, checked, name }});
                        else if (t === 'checkbox') results.checkboxes.push({{ label, value, checked, name }});
                        else if (tag === 'INPUT' && (t === 'date' || t === 'datetime-local'))
                            results.datepickers.push({{ placeholder, name }});
                        else if ((tag === 'INPUT' && (t === 'text' || !t)) || tag === 'TEXTAREA')
                            results.inputs.push({{ placeholder, name }});
                    }});
                    return results;
                }}
            """) or {}
            return forms
        except Exception:
            return {"radios": [], "checkboxes": [], "datepickers": [], "inputs": []}

    def _p3_dropdowns(self, interactive: bool = True):
        """通用下拉扫描：先收集文本再逐一触发（避免 ElementHandle 过期）。

        Args:
            interactive: False 时跳过触发器点击（不改变页面状态）——
                步骤驱动场景下拉选项已由引导循环 _guided_select + 补扫块覆盖，
                直接返回空结果。
        """
        c = self.config
        results = {}
        if not interactive:
            logger.info("[Phase 3] dropdowns: 非交互模式，跳过下拉触发（由引导循环覆盖）")
            return results

        dd_sel = getattr(c, 'dropdown_trigger_selectors', 'select, [role="combobox"], [role="listbox"]')
        try:
            handles = self.page.query_selector_all(dd_sel)
        except Exception:
            return results

        # 先收集所有候选的文本/选择器（DOM 交互前）
        candidates = []
        for el in handles[:c.max_dropdowns]:
            try:
                if not el.is_visible(): continue
                text = (el.inner_text() or "").strip()[:c.max_name_length]
                if text:
                    candidates.append(text)
            except Exception:
                continue

        # 去重后逐一用 locator 重新查找并点击
        seen_texts = set()
        for text in candidates:
            if text in seen_texts: continue
            seen_texts.add(text)
            try:
                # 用文本重新定位（避免过期 handle）
                trigger = self.page.locator(dd_sel).filter(has_text=text).first
                if not trigger.is_visible(timeout=500):
                    continue
                # 优先点内部箭头
                try:
                    arrow = trigger.locator(getattr(c, 'dropdown_arrow', '[class*="arrow"]')).first
                    if arrow.is_visible(timeout=300):
                        arrow.click(force=True, timeout=2000)
                    else:
                        trigger.click(force=True, timeout=2000)
                except Exception:
                    trigger.click(force=True, timeout=2000)

                self.client.wait(c.dropdown_wait)
                opts = self._scan_dropdown_options()
                if opts:
                    key = f"{text}" if text not in results else f"{text}_{len(results)}"
                    results[key] = {"options": opts, "option_count": len(opts)}
                    logger.info(f"[Phase 3] dropdown '{key}': {opts}")
                    self._capture_state(f"dd_{key}", self.client.get_url())
                self.client.press_escape()
                self.client.wait(c.dropdown_wait)
            except Exception:
                continue
        return results

    def _scan_dropdown_options(self):
        """Portal 选项扫描——Playwright 原生定位优先，JS 回退兜底。

        旧 POM（workbench_page.py:get_warning_filter_options）已验证：
        page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option").all()
        比 page.evaluate(js) 更可靠，因为 Playwright 原生处理了动态渲染的 Portal 元素。
        """
        # ── 策略0: Playwright 原生定位器（首选，旧 POM 验证过的可靠方式）──
        portal_loc_sel = (
            '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option, '
            '.ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item, '
            '.el-select-dropdown:not([style*="display: none"]) .el-select-dropdown__item, '
            '.el-dropdown-menu:not([style*="display: none"]) .el-dropdown-menu__item'
        )
        try:
            panel = self.page.locator(portal_loc_sel)
            cnt = panel.count()
            if cnt > 0:
                texts = []
                for i in range(min(cnt, 50)):
                    try:
                        t = panel.nth(i).inner_text()
                        t = (t or '').strip()
                        if t and 2 <= len(t) <= 80:
                            texts.append(t)
                    except Exception:
                        continue
                if texts:
                    logger.info(f"[Agent] _scan_dropdown_options Playwright → {len(texts)} options: {texts[:12]}")
                    return texts
        except Exception as e:
            logger.debug(f"[Agent] _scan_dropdown_options Playwright fallback error: {e}")

        # ── 策略1: JS Portal 容器扫描（框架无关）──
        try:
            opt_sel = (getattr(self.config, 'dropdown_option_selectors',
                       '[role="option"]:not([aria-hidden="true"]), [class*="option"]:not([class*="disabled"])'))
            opt_sel = opt_sel.replace("'", "\\'")
            portal_sel = (
                '.ant-select-dropdown:not(.ant-select-dropdown-hidden), '
                '.ant-dropdown:not(.ant-dropdown-hidden), '
                '.el-select-dropdown:not([style*="display: none"]), '
                '.el-dropdown-menu:not([style*="display: none"])'
            ).replace("'", "\\'")
            js_portal = f"""
                () => {{
                    const opts = new Set();
                    const containers = document.querySelectorAll('{portal_sel}');
                    containers.forEach(container => {{
                        container.querySelectorAll('{opt_sel}').forEach(el => {{
                            const t = (el.textContent || '').trim();
                            if (t && t.length >= 2 && t.length <= 50) opts.add(t);
                        }});
                    }});
                    return [...opts];
                }}
            """
            result = self.page.evaluate(js_portal)
            if result:
                logger.info(f"[Agent] _scan_dropdown_options JS portal → {len(result)} options: {result[:12]}")
                return result
        except Exception as e:
            logger.warning(f"[Agent] _scan_dropdown_options JS portal error: {e}")

        # ── 策略2: JS 全页回退 ──
        try:
            opt_sel = (getattr(self.config, 'dropdown_option_selectors',
                       '[role="option"]:not([aria-hidden="true"]), [class*="option"]:not([class*="disabled"])'))
            opt_sel = opt_sel.replace("'", "\\'")
            js_page = f"""
                (scopeEl) => {{
                    const root = scopeEl || document;
                    const opts = new Set();
                    root.querySelectorAll('{opt_sel}').forEach(el => {{
                        const t = (el.textContent || '').trim();
                        if (t && t.length >= 2 && t.length <= 50) opts.add(t);
                    }});
                    return [...opts];
                }}
            """
            if self._scope_element is not None:
                try:
                    result = self.page.evaluate(js_page, self._scope_element)
                    if result:
                        logger.info(f"[Agent] _scan_dropdown_options JS page scoped → {len(result)} options")
                        return result
                except Exception:
                    pass
            result = self.page.evaluate(js_page, None) or []
            if result:
                logger.info(f"[Agent] _scan_dropdown_options JS page full → {len(result)} options")
            return result
        except Exception as e:
            logger.warning(f"[Agent] _scan_dropdown_options JS page error: {e}")
            return []

    def _interact_modal(self):
        """弹窗交互：扫描弹窗内表单 → 填写 → 点非危险按钮 → 关闭。
        行业标准：ouroboros-tester/Scry 均把弹窗交互作为标准能力。

        通过 window.__mcp_modal_interacting 协调旗帜，暂停自动关闭 Observer。
        """
        c = self.config
        modal_sel = getattr(c, 'modal_selectors',
            getattr(c, 'modal_detect_selector', '[role="dialog"]'))
        try:
            modals = self.page.locator(modal_sel)
            cnt = modals.count()
            if cnt == 0: return
            modal = modals.first
            logger.info(f"[Phase 2] Modal interaction: {cnt} modal(s) found")

            # ── 暂停自动关闭 Observer ──
            try:
                self.page.evaluate("() => { window.__mcp_modal_interacting = true; }")
            except Exception:
                pass

            # 填弹窗内的输入框
            inputs = modal.locator('input:not([type="hidden"]):not([disabled]), textarea:not([disabled])')
            in_cnt = min(inputs.count(), 5)
            test_vals = getattr(c, 'form_fill_values', ['test', '测试'])
            for fi in range(in_cnt):
                try:
                    inp = inputs.nth(fi)
                    if inp.is_visible():
                        inp.fill(test_vals[min(fi, len(test_vals)-1)])
                        self.action_count += 1
                except Exception:
                    pass

            # 点弹窗内非危险按钮（跳过删除/清空类）
            buttons = modal.locator('button:not([disabled]), [role="button"]')
            btn_cnt = min(buttons.count(), 10)
            for bi in range(btn_cnt):
                try:
                    btn = buttons.nth(bi)
                    if not btn.is_visible(): continue
                    text = (btn.inner_text() or '').strip()
                    if any(kw in text for kw in self._danger_kw): continue
                    close_kws = getattr(c, 'modal_close_keywords', ['Cancel', 'Close'])
                    if text in close_kws or any(kw in text for kw in close_kws):
                        btn.click(force=True, timeout=1000)
                        logger.info(f"[Phase 2] Modal closed via '{text}'")
                        return
                except Exception:
                    continue

            # 关闭弹窗
            self.client.press_escape()
            self.client.wait(c.dropdown_wait)
        except Exception:
            pass
        finally:
            # ── 恢复自动关闭 Observer ──
            try:
                self.page.evaluate("() => { window.__mcp_modal_interacting = false; }")
            except Exception:
                pass

    def _p3_modals(self):
        """关键词扫描弹窗触发器 → 点击 → 交互 → Escape。"""
        c = self.config
        if not c.enable_modal_explore: return []
        results = []
        seen = set()
        all_actions = self._phase1_discover(depth=1, scope_element=self._scope_element)
        for a in all_actions:
            text = a.get("name", "")[:40]
            if not text or text in seen: continue
            if not any(kw in text for kw in c.modal_trigger_keywords): continue
            seen.add(text)
            try:
                self._click_by_text(text, a.get("role", ""))
                self.client.wait(c.modal_wait)
                modal_sel = getattr(c, 'modal_selectors',
                    getattr(c, 'modal_detect_selector', '[role="dialog"]'))
                modal_sel = modal_sel.replace("'", "\\'")
                content = self.page.evaluate(f"""
                    () => {{
                        const modals = [];
                        document.querySelectorAll('{modal_sel}').forEach(m => {{
                            const fields = [];
                            m.querySelectorAll('input,textarea,select').forEach(f => {{
                                const p = f.getAttribute('placeholder') || f.getAttribute('name') || '';
                                if (p) fields.push(p);
                            }});
                            const buttons = [];
                            m.querySelectorAll('button').forEach(b => {{
                                const t = (b.textContent || '').trim();
                                if (t) buttons.push(t);
                            }});
                            modals.push({{ text: (m.textContent || '').trim().substring(0, 300), fields, buttons }});
                        }});
                        return modals;
                    }}
                """) or []
                if content:
                    results.append({"trigger": text, "content": content})
                    logger.info(f"[Phase 3] modal '{text}': {len(content)} layer(s)")
                    self._capture_state(f"modal_{text}", self.client.get_url())
                    # V6: 弹窗交互（填表 + 点按钮）
                    self._interact_modal()
                    self.client.press_escape()
                self.client.wait(c.modal_wait)
            except Exception:
                continue
        return results

    def _p3_tables(self):
        """JS 提取表头 + 操作列（通用选择器）。"""
        c = self.config
        if not c.enable_table_explore: return []
        try:
            tbl_sel = getattr(c, 'table_selectors',
                'table, [role="table"], [role="grid"]')
            hdr_sel = getattr(c, 'table_header_selector', 'th, thead td')
            tbl_sel = tbl_sel.replace("'", "\\'")
            hdr_sel = hdr_sel.replace("'", "\\'")
            return self.page.evaluate(f"""
                () => {{
                    const results = [];
                    document.querySelectorAll('{tbl_sel}').forEach(tbl => {{
                        if (tbl.offsetParent === null) return;
                        const headers = [];
                        tbl.querySelectorAll('{hdr_sel}').forEach(h => {{
                            const t = (h.textContent || '').trim();
                            if (t) headers.push(t);
                        }});
                        const actions = [];
                        tbl.querySelectorAll('td button, td a').forEach(a => {{
                            const t = (a.textContent || '').trim();
                            if (t && t.length < 30 && !actions.includes(t)) actions.push(t);
                        }});
                        if (headers.length || actions.length)
                            results.push({{ columns: headers.slice(0, 20), actions: actions.slice(0, 20) }});
                    }});
                    return results.slice(0, 3);
                }}
            """) or []
        except Exception:
            return []

    def _p3_api_endpoints(self):
        """扫描 <script> 中的 API 路径。"""
        try:
            return self.page.evaluate("""
                () => {
                    const apis = new Set();
                    document.querySelectorAll('script').forEach(s => {
                        const t = s.textContent || '';
                        const m = t.match(/['\"]\/([a-zA-Z][a-zA-Z0-9_\/-]*\??[a-zA-Z0-9_=&-]*)['\"]/g);
                        if (m) m.forEach(x => apis.add(x.replace(/['\"]/g, '')));
                    });
                    return [...apis].filter(a => a.length > 3).slice(0, 30);
                }
            """) or []
        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════
    # Phase 4: LLM 综合生成
    # ═══════════════════════════════════════════════════════════

    def _phase4_synthesis(self, start_url, site_map, element_jumps, deep_dive):
        result = {"module_docs": "", "site_map_md": "", "page_object_code": ""}
        if not self.llm:
            return result
        ctx = json.dumps({
            "start_url": start_url,
            "nav_items": site_map.get("modules", []),
            "elements": [{k: v for k, v in e.items() if k != "selector"} for e in element_jumps],
            "dropdowns": deep_dive.get("dropdowns", {}),
            "tables": deep_dive.get("tables", []),
            "modals": deep_dive.get("modals", []),
        }, ensure_ascii=False, indent=2)

        try:
            result["module_docs"] = self._llm_gen(
                "你是技术文档专家。根据探索数据生成页面文档(Markdown)。输出:页面概览/导航结构/可交互元素/交互控件/业务流程。禁止编造。",
                f"## Data\n```json\n{ctx[:8000]}\n```", 8000) or ""
        except Exception: pass
        try:
            result["site_map_md"] = self._llm_gen(
                "你是技术文档专家。根据探索数据生成站点地图(Markdown)。输出:模块路由表格/页面内跳转表格/注意事项。禁止编造URL。",
                f"## Data\n```json\n{ctx[:4000]}\n```", 4000) or ""
        except Exception: pass
        try:
            result["page_object_code"] = self._llm_gen(
                "你是Playwright Python专家。根据探索数据生成Page Object代码。使用playwright.sync_api，选择器来自探索数据，禁止编造。只输出Python代码。",
                f"## 探索数据\n{ctx[:12000]}", 8000) or ""
        except Exception: pass

        return result

    def _llm_gen(self, sys_prompt, user_prompt, max_tokens):
        """同步调用 LLM——避免手写事件循环与 async_call_llm 冲突。"""
        try:
            r = self.llm.call_llm(
                prompt=user_prompt, system_prompt=sys_prompt,
                temperature=0, max_tokens=max_tokens)
            if r:
                r = r.strip()
                if r.startswith("```"): r = r.split("\n", 1)[1] if "\n" in r else r[3:]
                if r.endswith("```"): r = r[:-3]
                return r.strip()
        except Exception as e:
            logger.warning(f"[Phase 4] LLM error: {e}")
        return None

    # ═══════════════════════════════════════════════════════════
    # 指纹
    # ═══════════════════════════════════════════════════════════

    def _fingerprint_diff(self, before, after):
        if not before or not after: return None
        changes = {}
        for key in ("nodes", "expanded", "tabs", "bodyChildren"):
            if before.get(key) != after.get(key):
                changes[key] = {"before": before.get(key, 0), "after": after.get(key, 0)}
        if before.get("url") != after.get("url"):
            changes["url"] = {"before": before.get("url", ""), "after": after.get("url", "")}
        return changes or None

    @staticmethod
    def _norm_url_key(url: str) -> str:
        """统一 URL 归一化：提取 hash 路径（去掉 query params）。

        所有 _visited_urls、_is_within_module、_return_to_page 共用此方法。
        标准：先提取 hash（# 之后），再去除 query string（? 之后）。
        对无 hash 的 URL，直接去掉 query string。
        """
        if not url:
            return ""
        if "#" in url:
            return url.split("#")[-1].split("?")[0]
        return url.split("?")[0]

    @staticmethod
    def _norm(text):
        return "".join(text.split()).lower()
