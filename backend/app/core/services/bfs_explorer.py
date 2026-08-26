"""
BFS 深度探索引擎 — 按模块确定性递归爬取，不依赖 LLM Agent

遵循 SKILL: .opencode/skills/webui-exploration/SKILL.md
覆盖 P1-P9 全部阶段。

V5 更新: 配置从 exploration_config 统一读取，移除内嵌 ExplorationConfig。
"""
import asyncio, hashlib, json, re, time, fnmatch
from datetime import datetime
from typing import Optional
from pathlib import Path
from urllib.parse import urljoin, urlparse

from app.core.logger import logger
from app.core.services.exploration_config import WebExplorationConfig as ExplorationConfig


# ============================================================
# BFS Explorer
# ============================================================
class BFSExplorer:
    """BFS 深度探索引擎"""

    def _url_match(self, url: str, patterns: list) -> bool:
        """用 fnmatch glob 模式匹配 URL（非 regex）"""
        for p in patterns:
            if fnmatch.fnmatch(url, p):
                return True
        return False

    def __init__(self, page, base_url: str, config: ExplorationConfig = None,
                 login_engine=None):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.config = config or ExplorationConfig()
        self._login_engine = login_engine  # LoginEngine 实例，由调用方创建并完成登录
        self.visited_urls: set = set()
        self.visited_fingerprints: set = set()
        self.modules_explored: dict = {}
        self.new_pages_found: list = []

    # ====== P1: 登录（由 LoginEngine 处理，BFSExplorer 仅作代理） ======
    @property
    def auth_params(self) -> dict:
        """鉴权参数 — 从 LoginEngine 读取"""
        if self._login_engine:
            return self._login_engine.auth_params
        return {}

    def get_auth_data(self) -> dict:
        """导出鉴权数据（供持久化到 KnowledgeGraph）"""
        if self._login_engine:
            return self._login_engine.get_auth_data()
        return {"params": {}, "saved_at": datetime.utcnow().isoformat()}

    def _build_url(self, path: str) -> str:
        """拼接带鉴权参数的完整 URL"""
        return self._build_url_with_params(path, getattr(self, 'auth_params', {}))

    def _build_url_with_params(self, url: str, params: dict) -> str:
        """用指定参数拼接 URL（跳过已存在的参数，避免重复）"""
        result = self.base_url + url if url.startswith("/") else url
        if params:
            new_params = {k: v for k, v in params.items() if k not in result}
            if new_params:
                sep = "&" if "?" in result else "?"
                result += sep + "&".join(f"{k}={v}" for k, v in new_params.items())
        return result

    # ====== P2: 入口导航 ======
    async def navigate_to_module(self, module_name: str, module_url: str = None) -> bool:
        logger.info(f"[BFS P2] 导航到模块: {module_name}")
        url = module_url or self.config.module_routes.get(module_name)
        if not url:
            # 尝试从页面菜单中点击
            try:
                link = self.page.get_by_role("link", name=re.compile(module_name)).first
                if await link.is_visible(timeout=3000):
                    await link.click()
                    await asyncio.sleep(self.config.render_wait)
                    logger.info(f"[BFS P2] 通过菜单点击进入: {module_name}")
                    return True
            except Exception:
                pass
            logger.warning(f"[BFS P2] 找不到模块 '{module_name}' 的入口")
            return False
        full_url = self._build_url(url)
        await self.page.goto(full_url, wait_until="domcontentloaded", timeout=self.config.page_timeout)
        await asyncio.sleep(self.config.render_wait)
        return True

    # ====== P3: 被动发现 ======
    async def discover_elements(self) -> dict:
        """扫描页面，提取 9 种元素类型（先滚动到底再回顶，触发懒加载）"""
        logger.info("[BFS P3] 被动发现元素...")
        # 滚动页面确保懒加载内容可见
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.3)
        except Exception:
            pass
        elements = {k: [] for k in ["buttons", "links", "tabs", "inputs", "dropdowns",
                                      "date_pickers", "search_inputs", "cards", "table_actions"]}

        # 1. 按钮 (SKILL 3.1.1: button, [role="button"], a.btn, div[onclick])
        btn_sel = 'button, [role="button"], a.btn, div[onclick]'
        btns = self.page.locator(btn_sel)
        for i in range(min(await btns.count(), 80)):
            try:
                el = btns.nth(i)
                name = await self._get_element_name(el)
                if name and not any(dk in name for dk in self.config.danger_keywords):
                    elements["buttons"].append({"role": "button", "name": name})
            except Exception:
                pass

        # 2. 链接 (SKILL 3.1.2: a[href], span.link)
        links = self.page.locator('a[href], span.link, span[class*="link"]')
        for i in range(min(await links.count(), 100)):
            try:
                el = links.nth(i)
                name = await self._get_element_name(el)
                href = await el.get_attribute("href") or ""
                if name:
                    elements["links"].append({"role": "link", "name": name, "href": href})
            except Exception:
                pass

        # 3. Tab
        for sel in self.config.tab_selectors:
            tabs = self.page.locator(sel)
            for i in range(min(await tabs.count(), 20)):
                try:
                    name = await tabs.nth(i).text_content()
                    if name and name.strip():
                        elements["tabs"].append({"role": "tab", "name": name.strip()})
                except Exception:
                    pass

        # 4. 输入框
        inputs = self.page.locator('input[type="text"], input:not([type]), textarea, input[type="number"]')
        for i in range(min(await inputs.count(), 30)):
            try:
                el = inputs.nth(i)
                placeholder = await el.get_attribute("placeholder") or ""
                name = await el.get_attribute("name") or placeholder or f"input-{i}"
                elements["inputs"].append({"role": "textbox", "name": name, "placeholder": placeholder})
            except Exception:
                pass

        # 5. 下拉框
        for sel in self.config.dropdown_selectors:
            dropdowns = self.page.locator(sel)
            for i in range(min(await dropdowns.count(), 20)):
                try:
                    name = await self._get_element_name(dropdowns.nth(i))
                    if name:
                        elements["dropdowns"].append({"role": "combobox", "name": name, "selector": sel})
                except Exception:
                    pass

        # 6. 日期选择器
        for sel in self.config.date_picker_selectors:
            dps = self.page.locator(sel)
            for i in range(min(await dps.count(), 10)):
                try:
                    placeholder = await dps.nth(i).get_attribute("placeholder") or ""
                    elements["date_pickers"].append({"role": "date_picker", "placeholder": placeholder})
                except Exception:
                    pass

        # 7. 搜索框
        for sel in self.config.search_selectors:
            searches = self.page.locator(sel)
            for i in range(min(await searches.count(), 10)):
                try:
                    placeholder = await searches.nth(i).get_attribute("placeholder") or ""
                    elements["search_inputs"].append({"role": "search", "placeholder": placeholder})
                except Exception:
                    pass

        # 8. 卡片
        for sel in self.config.card_selectors:
            cards = self.page.locator(sel)
            for i in range(min(await cards.count(), 20)):
                try:
                    name = await self._get_element_name(cards.nth(i))
                    if name:
                        elements["cards"].append({"role": "card", "name": name})
                except Exception:
                    pass

        # 9. 表格操作列
        for sel in self.config.table_selectors:
            tables = self.page.locator(sel)
            for ti in range(min(await tables.count(), 5)):
                try:
                    table = tables.nth(ti)
                    actions = table.locator("td a, td button, td span[class*='action']")
                    for ai in range(min(await actions.count(), 50)):
                        try:
                            name = await self._get_element_name(actions.nth(ai))
                            if name and any(k in name for k in self.config.table_action_keywords):
                                elements["table_actions"].append({"role": "cell_action", "name": name})
                        except Exception:
                            pass
                except Exception:
                    pass

        total = sum(len(v) for v in elements.values())
        logger.info(f"[BFS P3] 发现 {total} 个元素")
        return elements

    async def _get_element_name(self, el) -> str:
        """获取元素语义化名称"""
        try:
            text = (await el.text_content() or "").strip()
            if text and len(text) < 50:
                return text
        except Exception:
            pass
        try:
            aria = await el.get_attribute("aria-label")
            if aria:
                return aria
        except Exception:
            pass
        try:
            title = await el.get_attribute("title")
            if title:
                return title
        except Exception:
            pass
        return ""

    # ====== P4: Tab 状态探索（含子 Tab 递归，SKILL 4） ======
    async def explore_tabs(self, tabs: list, depth: int = 0) -> list:
        """逐个点击 Tab，在每个 Tab 下重新发现元素；若含子 Tab 则递归"""
        if depth > 3:
            return []
        logger.info(f"[BFS P4] 探索 {len(tabs)} 个 Tab (depth={depth})...")
        tab_results = []
        for tab in tabs[:15]:
            name = tab.get("name", "")
            try:
                el = self.page.get_by_role("tab", name=name).first
                if not await el.is_visible(timeout=1000):
                    el = self.page.locator(f'[role="tab"]:has-text("{name}")').first
                await el.click(timeout=3000)
                await asyncio.sleep(self.config.tab_wait)
                sub_elements = await self.discover_elements()
                # SKILL 4: 若 Tab 内有子 Tab，递归探索
                sub_tabs = sub_elements.get("tabs", [])
                sub_tab_results = await self.explore_tabs(sub_tabs, depth + 1) if sub_tabs else []
                tab_results.append({"tab": name, "elements": sub_elements, "sub_tabs": sub_tab_results})
                logger.info(f"[BFS P4] Tab '{name}': {sum(len(v) for v in sub_elements.values())} 个元素, {len(sub_tab_results)} 个子Tab")
            except Exception as e:
                logger.warning(f"[BFS P4] Tab '{name}' 探索失败: {e}")
        return tab_results

    # ====== P5: 弹窗探索 ======
    async def explore_modals(self, elements: dict) -> list:
        """点击弹窗触发器，捕获弹窗内容"""
        modals_found = []
        triggers = [e for e in elements.get("buttons", []) + elements.get("links", [])
                    if any(k in e.get("name", "") for k in self.config.modal_trigger_keywords)]
        logger.info(f"[BFS P5] 尝试 {len(triggers)} 个弹窗触发器...")

        for trigger in triggers[:10]:
            name = trigger.get("name", "")
            try:
                pages_before = len(self.page.context.pages)
                el = self.page.get_by_role("button", name=name).first
                if not await el.is_visible(timeout=500):
                    el = self.page.get_by_text(name, exact=False).first
                await el.click(timeout=3000)
                await asyncio.sleep(self.config.modal_wait)

                pages_after = len(self.page.context.pages)
                if pages_after > pages_before:
                    # 新窗口/标签页
                    new_page = self.page.context.pages[-1]
                    await new_page.wait_for_load_state(timeout=5000)
                    new_elements = await self._discover_on_page(new_page)
                    modals_found.append({"trigger": name, "type": "new_tab", "elements": new_elements})
                    await new_page.close()
                    await self.page.bring_to_front()
                else:
                    # 检查弹窗
                    for sel in self.config.modal_selectors:
                        modal = self.page.locator(sel).first
                        if await modal.is_visible(timeout=500):
                            modal_content = await self._scan_modal(modal)
                            modals_found.append({"trigger": name, "type": "modal", "content": modal_content})
                            # 关闭弹窗
                            try:
                                await self.page.locator(f'{sel} button:has-text("取消"), {sel} button:has-text("关闭"), {sel} [class*="close"]').first.click(timeout=2000)
                            except Exception:
                                await self.page.keyboard.press("Escape")
                            await asyncio.sleep(0.3)
                            break
                logger.info(f"[BFS P5] 触发器 '{name}': {'弹窗' if modals_found else '无变化'}")
            except Exception as e:
                logger.debug(f"[BFS P5] '{name}' 触发失败: {e}")
        return modals_found

    async def _discover_on_page(self, page) -> dict:
        """在指定 page 上执行 P3"""
        saved_page = self.page
        self.page = page
        elements = await self.discover_elements()
        self.page = saved_page
        return elements

    async def _scan_modal(self, modal) -> dict:
        """扫描弹窗内容（滚动到底再回顶，触发懒加载）"""
        try:
            await modal.evaluate("el => { el.scrollTo(0, el.scrollHeight); }")
            await asyncio.sleep(0.3)
            await modal.evaluate("el => { el.scrollTo(0, 0); }")
            await asyncio.sleep(0.2)
        except Exception:
            pass
        text = await modal.text_content() or ""
        # 提取表单字段 + 按钮
        fields = []
        inputs = modal.locator("input, textarea, select")
        for i in range(min(await inputs.count(), 30)):
            try:
                placeholder = await inputs.nth(i).get_attribute("placeholder") or ""
                name = await inputs.nth(i).get_attribute("name") or placeholder
                fields.append(name)
            except Exception:
                pass
        # 也记录弹窗内的按钮
        btns = []
        for i in range(min(await modal.locator("button").count(), 20)):
            try:
                t = (await modal.locator("button").nth(i).text_content() or "").strip()
                if t:
                    btns.append(t)
            except Exception:
                pass
        return {"text": text[:500], "fields": fields, "buttons": btns}

    # ====== P6: 过滤控件探索（SKILL 6：每个选项都点） ======
    async def explore_filters(self, elements: dict) -> dict:
        """展开每个下拉→记录全部选项→逐个点击每个选项→记录变化"""
        filter_options = {}
        dropdowns = elements.get("dropdowns", [])
        logger.info(f"[BFS P6] 探索 {len(dropdowns)} 个过滤控件...")

        for dd in dropdowns[:10]:
            name = dd.get("name", "")
            try:
                el = self.page.get_by_role("combobox", name=name).first
                if not await el.is_visible(timeout=500):
                    el = self.page.locator(f'[role="combobox"]:has-text("{name}"), select:has-text("{name}")').first
                await el.click(timeout=2000)
                await asyncio.sleep(self.config.dropdown_wait)

                # 收集下拉选项
                options = []
                option_els = self.page.locator('[role="option"], [class*="option"]:not([class*="disabled"])')
                for oi in range(min(await option_els.count(), 50)):
                    try:
                        opt_text = (await option_els.nth(oi).text_content() or "").strip()
                        if opt_text:
                            options.append(opt_text)
                    except Exception:
                        pass

                if options:
                    filter_options[name] = {"type": "dropdown", "options": options, "tested": []}
                    for opt in options[:15]:
                        try:
                            await el.click(timeout=2000)  # 重新打开下拉
                            await asyncio.sleep(0.4)
                            target = self.page.locator(f'[role="option"]:has-text("{opt}"), [class*="option"]:has-text("{opt}")').first
                            if await target.is_visible(timeout=800):
                                await target.click(timeout=2000)
                                await asyncio.sleep(0.4)
                                filter_options[name]["tested"].append(opt)
                                logger.info(f"[BFS P6] '{name}' 点击: {opt}")
                        except Exception:
                            pass

                    # 恢复默认（点"全部"或第一个选项）
                    try:
                        await el.click(timeout=2000)
                        await asyncio.sleep(0.2)
                        default = self.page.get_by_text(options[0], exact=True).first
                        if await default.is_visible(timeout=500):
                            await default.click(timeout=2000)
                    except Exception:
                        pass
                    await asyncio.sleep(0.2)

                logger.info(f"[BFS P6] '{name}': {len(options)} 个选项, 测试了 {len(filter_options[name].get('tested', []))} 个")
            except Exception as e:
                logger.debug(f"[BFS P6] '{name}' 探索失败: {e}")

        # 搜索框试填
        for si in elements.get("search_inputs", [])[:3]:
            placeholder = si.get("placeholder", "")
            try:
                sel = f'input[placeholder="{placeholder}"]'
                inp = self.page.locator(sel).first
                if await inp.is_visible(timeout=500):
                    await inp.fill("test_search_value")
                    await asyncio.sleep(0.3)
                    await inp.fill("")
                    filter_options[f"search_{placeholder}"] = {"type": "search_input", "placeholder": placeholder}
            except Exception:
                pass

        return filter_options

    # ====== P7: 日期控件探索（SKILL 7） ======
    async def explore_date_pickers(self, elements: dict) -> list:
        """点击日期选择器 → 切换上下月 → 选日期 → 记录"""
        results = []
        dps = elements.get("date_pickers", [])
        logger.info(f"[BFS P7] 探索 {len(dps)} 个日期控件...")

        for dp in dps[:5]:
            placeholder = dp.get("placeholder", "")
            try:
                sel = f'input[type="date"], [class*="picker"]:not([class*="disabled"])'
                if placeholder:
                    sel = f'input[placeholder="{placeholder}"], {sel}'
                el = self.page.locator(sel).first
                if not await el.is_visible(timeout=500):
                    continue
                await el.click(timeout=2000)
                await asyncio.sleep(0.5)

                info = {"placeholder": placeholder, "actions": []}

                # 切换上一个月
                prev_btn = self.page.locator('[class*="prev"], [class*="arrow-left"], [aria-label*="上"]').first
                if await prev_btn.is_visible(timeout=500):
                    await prev_btn.click()
                    await asyncio.sleep(0.3)
                    info["actions"].append("prev_month")

                # 切换下一个月
                next_btn = self.page.locator('[class*="next"], [class*="arrow-right"], [aria-label*="下"]').first
                if await next_btn.is_visible(timeout=500):
                    await next_btn.click()
                    await asyncio.sleep(0.3)
                    info["actions"].append("next_month")

                # 选一个日期
                date_cell = self.page.locator('[class*="cell"]:not([class*="disabled"]), td:not([class*="disabled"])').first
                if await date_cell.is_visible(timeout=500):
                    selected = (await date_cell.text_content() or "").strip()
                    await date_cell.click()
                    await asyncio.sleep(0.3)
                    info["selected_date"] = selected
                    info["actions"].append("select_date")

                # 关闭
                try:
                    await self.page.keyboard.press("Escape")
                except Exception:
                    pass
                await asyncio.sleep(0.2)

                results.append(info)
                logger.info(f"[BFS P7] 日期控件 '{placeholder}': {info}")
            except Exception as e:
                logger.debug(f"[BFS P7] 日期控件探索失败: {e}")
        return results

    # ====== P8: 表格探索（SKILL 8） ======
    async def explore_tables(self, elements: dict) -> list:
        """滚动表格 → 点击每个分页 → 点击每个操作按钮 → 记录"""
        results = []
        logger.info("[BFS P8] 探索表格...")

        for sel in self.config.table_selectors:
            tables = self.page.locator(sel)
            for ti in range(min(await tables.count(), 5)):
                try:
                    table = tables.nth(ti)
                    # 滚动表格
                    try:
                        await table.evaluate("el => { el.scrollLeft = el.scrollWidth; }")
                        await asyncio.sleep(0.2)
                        await table.evaluate("el => { el.scrollTop = el.scrollHeight; }")
                        await asyncio.sleep(0.2)
                        await table.evaluate("el => { el.scrollLeft = 0; el.scrollTop = 0; }")
                    except Exception:
                        pass

                    table_info = {"index": ti, "columns": [], "pagination": [], "actions": []}

                    # 提取表头
                    headers = table.locator("th, thead td")
                    for hi in range(min(await headers.count(), 30)):
                        try:
                            h_text = (await headers.nth(hi).text_content() or "").strip()
                            if h_text:
                                table_info["columns"].append(h_text)
                        except Exception:
                            pass

                    # 点击每个分页按钮
                    pagers = self.page.locator('[class*="pagination"] li, [class*="pager"] li, [class*="pagination"] button')
                    pager_count = await pagers.count()
                    for pi in range(min(pager_count, 10)):
                        try:
                            pager = pagers.nth(pi)
                            p_text = (await pager.text_content() or "").strip()
                            if p_text and p_text not in table_info["pagination"]:
                                await pager.click(timeout=2000)
                                await asyncio.sleep(0.5)
                                table_info["pagination"].append(p_text)
                                logger.info(f"[BFS P8] 表格 {ti} 切换到第 {p_text} 页")
                        except Exception:
                            pass

                    # 点击操作列的每个按钮
                    action_btns = table.locator("td button, td a, td [class*='action'], td [class*='操作'] button, td [class*='操作'] a")
                    for ai in range(min(await action_btns.count(), 30)):
                        try:
                            btn = action_btns.nth(ai)
                            btn_text = (await btn.text_content() or "").strip()
                            if not btn_text or any(dk in btn_text for dk in self.config.danger_keywords):
                                continue
                            if btn_text not in table_info["actions"]:
                                table_info["actions"].append(btn_text)
                                logger.info(f"[BFS P8] 表格 {ti} 操作按钮: {btn_text}")
                        except Exception:
                            pass

                    results.append(table_info)
                    logger.info(f"[BFS P8] 表格 {ti}: {len(table_info['columns'])} 列, {len(table_info['pagination'])} 页, {len(table_info['actions'])} 个操作")
                except Exception as e:
                    logger.debug(f"[BFS P8] 表格 {ti} 探索失败: {e}")
        return results

    # ====== P9: 主动导航探测 ======
    async def probe_navigation(self, elements: dict) -> list:
        """
        P7 主动导航探测 — SKILL 7：
        对 P3 发现的「所有卡片 + 所有表格操作列 + 所有链接」，全部点击探测。
        """
        probes = (
            elements.get("cards", []) +
            elements.get("table_actions", []) +
            elements.get("links", [])
        )
        seen, unique = set(), []
        for p in probes:
            name = p.get("name", "").strip()
            # 只探测含数字的数据卡片（可点击跳转），跳过纯文字的分类标题
            if not name or name in seen:
                continue
            if any(dk in name for dk in self.config.danger_keywords):
                continue
            if not re.search(r'\d', name):  # 不含数字 → 可能是分类标题，跳过
                continue
            seen.add(name)
            unique.append(p)

        logger.info(f"[BFS P7] 探测 {len(unique)} 个导航元素（卡片+表格+链接全量）")
        discovered_urls = []
        workbench_url = self.page.url  # 保存干净的工作台 URL，每次返回用

        for probe in unique[:30]:
            name = probe.get("name", "")
            url_before = self.page.url
            pages_before = len(self.page.context.pages)
            try:
                # 从 "Smart 报告(份)35今日新增+0" 提取关键词尝试多个变体
                base = re.split(r'[\d\n]+', re.sub(r'\([^)]*\)', '', name))[0].strip()
                keywords = [base, base.replace(' ', ''), ''.join(base.split()[:2])]
                keywords = [k for k in keywords if len(k) >= 2]
                el = None
                for kw in keywords:
                    el = self.page.locator(f'[class*="card"]:has-text("{kw}")').first
                    if await el.is_visible(timeout=300):
                        break
                    el = self.page.get_by_text(kw, exact=False).first
                    if await el.is_visible(timeout=300):
                        break
                if not el:
                    continue  # 跳过找不到的
                logger.info(f"[BFS P7] 点击: '{name[:30]}'")
                await el.click(timeout=2000)

                # 等待导航完成（最多 5 秒）
                try:
                    await self.page.wait_for_url(lambda u: u != url_before, timeout=5000)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

                pages_after = len(self.page.context.pages)
                url_after = self.page.url

                if pages_after > pages_before:
                    # 新标签：探索子页面 → 关闭 → 回到主页
                    new_page = self.page.context.pages[-1]
                    new_url = new_page.url
                    logger.info(f"[BFS P7] NewTab: '{name}' → {new_url[:80]}")
                    try:
                        await new_page.wait_for_load_state("networkidle", timeout=8000)
                        sub_elements = await self._discover_on_page(new_page)
                        discovered_urls.append({"trigger": name, "type": "new_tab", "url": new_url, "elements": sub_elements})
                    except Exception:
                        discovered_urls.append({"trigger": name, "type": "new_tab", "url": new_url})
                    await new_page.close()
                    await self.page.bring_to_front()
                elif url_after != url_before:
                    # SPA 导航：go_back + wait networkidle（行业标准模式）
                    discovered_urls.append({"trigger": name, "type": "spa_navigation", "url": url_after})
                    logger.info(f"[BFS P7] SPA: '{name}' → {url_after[:60]}")
                    try:
                        await self.page.go_back()
                        await self.page.wait_for_load_state("networkidle", timeout=8000)
                        logger.info(f"[BFS P7] back ok: {self.page.url[:60]}")
                    except Exception:
                        logger.warning(f"[BFS P7] go_back fail, goto workbench")
                        await self.page.goto(workbench_url, wait_until="networkidle", timeout=10000)
                # 弹窗情况已在 P5 处理
            except Exception as e:
                logger.debug(f"[BFS P7] '{name}' 探测失败: {e}")
        return discovered_urls

    # ====== P8: 递归 ======
    def _normalize_url(self, url: str) -> str:
        """URL 归一化——去 query 参数差异"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    async def _fingerprint(self) -> str:
        """页面结构指纹（SKILL 8: 用元素数量+文本哈希去重）"""
        try:
            body = await self.page.locator("body").inner_text()
            text_hash = hashlib.md5(body[:2000].encode()).hexdigest()
            btn_count = await self.page.locator("button").count()
            link_count = await self.page.locator("a").count()
            return f"{text_hash}:{btn_count}:{link_count}"
        except Exception:
            return "fp_err"

    def is_within_module(self, url: str, module_name: str) -> bool:
        """判断 URL 是否在模块边界内"""
        boundary = self.config.module_url_boundaries.get(module_name, "")
        if boundary:
            return boundary in url
        return True  # 默认全部允许

    # ====== P9: 组装输出 ======
    def assemble_output(self, module_name: str, all_elements: list, filter_options: dict,
                        modals: list, tab_results: list, pages_visited: list,
                        date_pickers: list = None, tables: list = None) -> dict:
        """组装探索结果为标准化结构"""
        return {
            "module": module_name,
            "base_url": self.base_url,
            "pages": pages_visited,
            "elements_count": sum(len(v) for e in all_elements for v in e.values()) if all_elements and isinstance(all_elements[0], dict) else 0,
            "elements": all_elements,
            "filter_options": filter_options,
            "modals": modals,
            "tab_results": tab_results,
            "date_pickers": date_pickers or [],
            "tables": tables or [],
            "config_snapshot": {
                "auth_param_names": (
                    self._login_engine.config.auth_param_names
                    if self._login_engine else []
                ),
                "module_routes": self.config.module_routes,
            },
        }

    def format_for_llm(self, result: dict) -> str:
        """格式化为 LLM 可用的 Markdown"""
        lines = [f"# 模块探索结果: {result.get('module', '')}", "",
                 f"## 页面列表"]
        for p in result.get("pages", []):
            lines.append(f"- {p}")
        lines.append("")
        lines.append("## 元素清单")
        for element_group in result.get("elements", []):
            for role, items in element_group.items():
                if items:
                    lines.append(f"### {role}")
                    for item in items[:10]:
                        lines.append(f"- `{item.get('name', '?')}`")
        if result.get("filter_options"):
            lines.append("")
            lines.append("## 过滤控件及选项")
            for name, info in result.get("filter_options", {}).items():
                opts = info.get("options", [])
                lines.append(f"- **{name}**: {', '.join(opts[:15])}")
        if result.get("modals"):
            lines.append("")
            lines.append("## 弹窗")
            for m in result.get("modals", []):
                lines.append(f"- {m.get('trigger', '?')} → {m.get('type', '?')}")
        return "\n".join(lines)

    # ====== 完整探索流程（单模块） ======
    async def explore_module(self, module_name: str, module_url: str = None) -> dict:
        """完整 BFS 探索一个模块（P1-P9）"""
        logger.info(f"[BFS] ====== 开始探索模块: {module_name} ======")

        # P2: 导航到模块入口
        ok = await self.navigate_to_module(module_name, module_url)
        if not ok:
            return {"error": f"无法导航到模块: {module_name}"}

        pages_visited = [self.page.url]
        all_elements = []
        all_tab_results = []
        all_modals = []
        all_filter_options = {}
        all_date_results = []
        all_table_results = []
        queue = [self.page.url]

        while queue and len(pages_visited) < self.config.max_pages:
            current_url = queue.pop(0)
            normalized = self._normalize_url(current_url)
            if normalized in self.visited_urls:
                continue

            if current_url != self.page.url:
                try:
                    await self.page.goto(current_url, wait_until="domcontentloaded", timeout=self.config.page_timeout)
                    await asyncio.sleep(self.config.render_wait)
                except Exception:
                    continue

            # SKILL 8: 指纹去重（页面结构相同 = 已访问）
            fp = await self._fingerprint()
            if fp in self.visited_fingerprints:
                continue
            self.visited_urls.add(normalized)
            self.visited_fingerprints.add(fp)
            pages_visited.append(current_url)

            # P3: 被动发现
            elements = await self.discover_elements()
            all_elements.append(elements)

            # P9: 主动导航探测（先点卡片——页面干净，过滤/表格还未改动 DOM）
            discovered = await self.probe_navigation(elements)

            # P4: Tab 探索
            tabs = elements.get("tabs", [])
            if tabs:
                tab_results = await self.explore_tabs(tabs)
                all_tab_results.extend(tab_results)

            # P5: 弹窗探索
            modals = await self.explore_modals(elements)
            all_modals.extend(modals)

            # P6: 过滤控件探索（每个选项都点）
            filters = await self.explore_filters(elements)
            all_filter_options.update(filters)

            # P7: 日期控件探索
            date_results = await self.explore_date_pickers(elements)
            all_date_results.extend(date_results)

            # P8: 表格探索（分页+操作列）
            table_results = await self.explore_tables(elements)
            all_table_results.extend(table_results)
            for d in discovered:
                url = d.get("url", "")
                if url and self.is_within_module(url, module_name):
                    if self._normalize_url(url) not in self.visited_urls:
                        queue.append(url)

        # P9: 组装输出
        result = self.assemble_output(module_name, all_elements, all_filter_options,
                                       all_modals, all_tab_results, pages_visited,
                                       all_date_results, all_table_results)
        logger.info(f"[BFS] ====== 模块 {module_name} 探索完成: {len(pages_visited)} 页, "
                    f"{len(all_filter_options)} 过滤, {len(all_modals)} 弹窗, "
                    f"{len(all_date_results)} 日期, {len(all_table_results)} 表格 ======")
        return result
