"""
V5 MCP Client — Playwright 同步浏览器封装。

纯浏览器操作层，不含有探索逻辑。所有选择器从 config 注入，框架无关。
"""

import time
import json
import hashlib


class MCPClient:
    """Playwright 同步浏览器封装（框架无关）。"""

    def __init__(self, page, config=None):
        self.page = page
        self.config = config  # WebExplorationConfig 或兼容对象

    # =====================================================
    # 点击（三阶段容错）
    # =====================================================

    def click(self, element):
        """一次点击语义：普通 click 失败后，只有确认页面没有发生变化才允许 force click。

        Playwright 的 TimeoutError 可能发生在 click 已经派发之后（例如等待事件/导航
        阶段超时）。再次 click 会把一次性卡片、链接等动作真正触发两次。
        """
        before_url = self.get_url()
        try:
            before_fp = self.get_fingerprint_dict()
        except Exception:
            before_fp = {}
        try:
            element.scroll_into_view_if_needed()
        except Exception:
            pass
        try:
            element.click(timeout=4000)
            return True
        except Exception:
            pass

        # 第一次调用可能已经完成 click，只是在等待后续事件时超时；此时禁止二次点击。
        try:
            after_url = self.get_url()
            after_fp = self.get_fingerprint_dict()
            if (after_url and after_url != before_url) or (before_fp and after_fp and after_fp != before_fp):
                return True
        except Exception:
            pass

        try:
            if bool(getattr(self.config, 'allow_force_click', True)):
                element.click(force=True, timeout=2500)
                return True
        except Exception:
            pass

        if bool(getattr(self.config, 'allow_js_click_fallback', False)):
            # JS fallback 同样只允许在前一次点击没有产生任何可观察变化时执行。
            try:
                element.evaluate("el => el.click()")
                return True
            except Exception:
                pass
        return False

    # =====================================================
    # hover / 右键（V5 新增）
    # =====================================================

    def hover(self, element, wait=0.3):
        """悬停在元素上，等待浮层出现。"""
        try:
            element.scroll_into_view_if_needed()
            element.hover()
            self.page.wait_for_timeout(int(wait * 1000))
            return True
        except Exception:
            return False

    def right_click(self, element):
        """右键点击元素。"""
        try:
            element.scroll_into_view_if_needed()
            element.click(button="right")
            return True
        except Exception:
            return False

    # =====================================================
    # 滚动
    # =====================================================

    def scroll_into_view(self, element):
        try:
            element.scroll_into_view_if_needed()
        except Exception:
            pass

    def scroll_to_load(self):
        """滚动到底再回顶，触发懒加载组件渲染。"""
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(400)
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(300)
        except Exception:
            pass

    # =====================================================
    # 导航
    # =====================================================

    def goto(self, url, timeout=15000):
        """导航到 URL。返回 True 表示成功，False 表示可能未完全加载。"""
        success = False
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            success = True
        except Exception:
            # 页面可能已部分加载
            pass
        return success

    def wait_for_page_ready_fast(self, max_wait=3.0, min_body_len=120):
        """Case 间短等待：只确认 DOM 有内容并短暂稳定。"""
        deadline = time.time() + max_wait
        last_len = -1
        stable = 0
        while time.time() < deadline:
            try:
                cur_len = self.page.evaluate("() => document.body ? document.body.innerText.length : 0")
            except Exception:
                cur_len = 0
            if cur_len >= min_body_len and cur_len == last_len:
                stable += 1
                if stable >= 2:
                    return True
            else:
                stable = 0
            last_len = cur_len
            try:
                self.page.wait_for_timeout(120)
            except Exception:
                time.sleep(0.12)
        return False

    def wait_for_page_ready(self, max_wait=10.0, min_body_len=200):
        """轮询等待 SPA 渲染完成（body 内容长度稳定）。最长等待 max_wait 秒。"""
        import time as _time
        last_len = 0
        stable_count = 0
        deadline = _time.time() + max_wait
        while _time.time() < deadline:
            try:
                cur_len = self.page.evaluate(
                    "() => document.body ? document.body.innerText.length : 0"
                )
            except Exception:
                cur_len = 0
            if cur_len > min_body_len and cur_len == last_len:
                stable_count += 1
                if stable_count >= 2:  # 连续 2 次长度不变 → 页面稳定
                    return True
            else:
                stable_count = 0
            last_len = cur_len
            self.page.wait_for_timeout(500)
        return False  # 超时未稳定，页面可能仍在加载中

    def back(self, wait=0.25):
        """简单返回。SPA 场景用 back_safe。"""
        try:
            self.page.go_back()
            self.page.wait_for_timeout(int(wait * 1000))
        except Exception:
            pass

    def back_safe(self, target_url, timeout=5.0):
        """SPA 安全返回：go_back + URL 轮询验证。"""
        try:
            self.page.go_back()
        except Exception:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.page.wait_for_timeout(500)
            try:
                cur = self.page.url
                if not cur:
                    continue
                if target_url == cur:
                    return True
                if "#" in target_url and "#" in cur:
                    if target_url.split("#", 1)[1] == cur.split("#", 1)[1]:
                        return True
            except Exception:
                pass
        return False

    # =====================================================
    # URL
    # =====================================================

    def get_url(self):
        try:
            return self.page.url
        except Exception:
            return ""

    # =====================================================
    # DOM 文本
    # =====================================================

    def get_dom_text(self, max_len=4000):
        try:
            return self.page.evaluate(
                "(maxLen) => (document.body ? document.body.innerText : '').slice(0, maxLen)",
                max_len,
            )
        except Exception:
            return ""

    # =====================================================
    # 等待
    # =====================================================

    def wait(self, t):
        self.page.wait_for_timeout(int(t * 1000))

    # =====================================================
    # DOM 状态指纹（结构化：关键节点计数，选择器从 config 注入）
    # =====================================================

    def get_fingerprint(self):
        """基于参数化 CSS selector 计算页面状态指纹。"""
        try:
            result = self.page.evaluate(
                """(sel) => {
                    const count = s => { try { return document.querySelectorAll(s).length; } catch(e) { return 0; } };
                    return {url:location.href||'', hash:location.hash||'', nodes:count(sel),
                            expanded:count('[aria-expanded="true"]'), tabs:count('[role="tab"]'),
                            bodyChildren:document.body ? document.body.children.length : 0};
                }""", self._fingerprint_selector_js())
            raw=json.dumps(result or {},ensure_ascii=False,sort_keys=True)
            return hashlib.md5(raw.encode('utf-8')).hexdigest()
        except Exception:
            return ''

    def get_fingerprint_dict(self):
        try:
            result = self.page.evaluate(
                """(sel) => {
                    const count = s => { try { return document.querySelectorAll(s).length; } catch(e) { return 0; } };
                    return {url:location.href||'', hash:location.hash||'', nodes:count(sel),
                            expanded:count('[aria-expanded="true"]'), tabs:count('[role="tab"]'),
                            bodyChildren:document.body ? document.body.children.length : 0};
                }""", self._fingerprint_selector_js())
            return result or {'url':self.get_url(),'nodes':0,'expanded':0,'tabs':0,'bodyChildren':0,'hash':''}
        except Exception:
            return {'url':self.get_url(),'nodes':0,'expanded':0,'tabs':0,'bodyChildren':0,'hash':''}

    def _fingerprint_selector_js(self):
        raw = getattr(self.config, 'fingerprint_selectors', None) if self.config else None
        return str(raw or '[role="dialog"],[role="listbox"],[role="menu"]').strip()

    # =====================================================
    # 扫描页面组件（通用实现，已框架无关）
    # =====================================================

    def scan_components(self):
        try:
            return self.page.evaluate("""
                () => {
                    const selectors = [
                        '[role]','button','input','select',
                        '[class*="select"]','[class*="picker"]',
                        '[class*="modal"]','[class*="dialog"]',
                        '[class*="table"]'
                    ];
                    let nodes = [];
                    document.querySelectorAll(selectors.join(',')).forEach(e => {
                        let r = e.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            nodes.push({
                                tag: e.tagName,
                                text: (e.innerText || '').trim().slice(0, 100),
                                role: e.getAttribute('role') || '',
                                cls: String(e.className || '').slice(0, 120)
                            });
                        }
                    });
                    return nodes.slice(0, 200);
                }
            """) or []
        except Exception:
            return []

    # =====================================================
    # 浮层状态（选择器从 config 注入）
    # =====================================================

    def get_overlay_state(self):
        try:
            sel = self._overlay_selector_js()
            return self.page.evaluate("""(sel) => {
                try { return {overlay: document.querySelectorAll(sel).length}; }
                catch(e) { return {overlay:0}; }
            }""", sel) or {'overlay':0}
        except Exception:
            return {'overlay':0}

    def _overlay_selector_js(self):
        raw = getattr(self.config, 'modal_selectors', None) if self.config else None
        return str(raw or '[role="dialog"],dialog[open],[role="listbox"],[role="menu"]').strip()

    # =====================================================
    # Console error 捕获（注入一次，后续 collect）
    # =====================================================

    def inject_console_hook(self):
        """注入 console.error 拦截器。"""
        try:
            self.page.evaluate("""
                () => {
                    if (!window.__mcp_console_errors) window.__mcp_console_errors = [];
                    const orig = console.error;
                    console.error = function() {
                        window.__mcp_console_errors.push(
                            Array.from(arguments).map(a => String(a)).join(' ')
                        );
                        orig.apply(console, arguments);
                    };
                }
            """)
        except Exception:
            pass

    def collect_console_errors(self):
        """收集并清空 console.error 日志。"""
        try:
            return self.page.evaluate("""
                () => {
                    if (!window.__mcp_console_errors) return [];
                    const errs = [...window.__mcp_console_errors];
                    window.__mcp_console_errors = [];
                    return errs;
                }
            """) or []
        except Exception:
            return []

    # =====================================================
    # 键盘
    # =====================================================

    def press_escape(self):
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
        except Exception:
            pass

    # =====================================================
    # V5 新增: iframe 穿透
    # =====================================================

    def get_iframe_frames(self):
        """返回真实 Playwright Frame 对象；需要操作 frame 时使用此方法。"""
        out = []
        try:
            for frame in self.page.frames:
                if frame != self.page.main_frame:
                    out.append(frame)
        except Exception:
            pass
        return out

    def scan_iframes(self):
        """遍历所有 frame，返回每个 iframe 的 URL 和可交互元素数量。"""
        frames_info = []
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            try:
                url = frame.url or ""
                btn_count = frame.locator("button, a, input, [onclick]").count()
                frames_info.append({
                    "url": url[:200],
                    "name": frame.name or "",
                    "element_count": btn_count,
                })
            except Exception:
                pass
        return frames_info

    def get_iframe_elements(self, frame):
        """在指定 frame 内发现可交互元素。"""
        elements = []
        try:
            btns = frame.locator("button, a, input, [onclick], [role='button']")
            count = btns.count()
            for i in range(min(count, 50)):
                try:
                    el = btns.nth(i)
                    if el.is_visible():
                        text = (el.inner_text() or "").strip()[:60]
                        if text:
                            elements.append({"name": text, "tag": el.evaluate("el => el.tagName")})
                except Exception:
                    pass
        except Exception:
            pass
        return elements

    # =====================================================
    # V5 新增: Accessibility Tree（核心发现能力）
    # =====================================================

    def get_main_content(self):
        """定位页面主内容区元素。

        返回 <main> / [role="main"] 的 ElementHandle。
        找不到则返回 None（调用方回退到 body）。

        这是探索边界控制的核心——元素发现限定在主内容区，
        天然排除 <nav>/<aside>/侧边栏。Cypress/axe-core/Verdex 均采用此模式。
        """
        try:
            el = self.page.query_selector('main, [role="main"]')
            if el:
                return el
        except Exception:
            pass
        # 回退：尝试常见的内容区容器
        for sel in [
            '[class*="content"]:not([class*="sidebar"]):not([class*="sider"])',
            '[class*="main"]:not([class*="sidebar"])',
            'article',
        ]:
            try:
                el = self.page.query_selector(sel)
                if el:
                    return el
            except Exception:
                continue
        return None

    def get_accessibility_tree(self, root=None):
        """获取页面的无障碍树快照。

        可传入 root ElementHandle 限定子树范围（用于 scope 限定）。
        所有前端框架最终都生成标准的无障碍树，这是 95% 通用性的基础。
        """
        try:
            kwargs = {}
            if root is not None:
                kwargs['root'] = root
            return self.page.accessibility.snapshot(**kwargs)
        except Exception:
            return None
