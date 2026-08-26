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
        try:
            element.scroll_into_view_if_needed()
            element.click(force=True)
            return True
        except Exception:
            pass
        try:
            element.evaluate("el => el.click()")
            return True
        except Exception:
            pass
        try:
            element.evaluate("""
                el => {
                    ['mousedown','mouseup','click'].forEach(t => {
                        el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true}));
                    });
                }
            """)
            return True
        except Exception:
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
        try:
            self.page.wait_for_timeout(1000)
        except Exception:
            pass
        return success

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

    def back(self, wait=0.8):
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
        """用 config.fingerprint_selectors 做状态指纹（MD5）。"""
        try:
            sel = self._fingerprint_selector_js()
            result = self.page.evaluate(f"""
                () => {{
                    function count(sel) {{ return document.querySelectorAll(sel).length; }}
                    return {{
                        url: location.href,
                        hash: location.hash || '',
                        nodes: count('{sel}'),
                        expanded: count('[aria-expanded="true"]'),
                        tabs: count('[role="tab"]'),
                        bodyChildren: document.body ? document.body.children.length : 0,
                    }};
                }}
            """)
            raw = json.dumps(result, ensure_ascii=False, sort_keys=True)
            return hashlib.md5(raw.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def get_fingerprint_dict(self):
        """返回指纹字典（未哈希），用于变化检测。"""
        try:
            sel = self._fingerprint_selector_js()
            result = self.page.evaluate(f"""
                () => {{
                    function count(sel) {{ return document.querySelectorAll(sel).length; }}
                    return {{
                        url: location.href || '',
                        hash: location.hash || '',
                        nodes: count('{sel}'),
                        expanded: count('[aria-expanded="true"]'),
                        tabs: count('[role="tab"]'),
                        bodyChildren: document.body ? document.body.children.length : 0,
                    }};
                }}
            """)
            return result or {"url": self.get_url(), "nodes": 0, "expanded": 0,
                              "tabs": 0, "bodyChildren": 0, "hash": ""}
        except Exception:
            return {"url": self.get_url(), "nodes": 0, "expanded": 0,
                    "tabs": 0, "bodyChildren": 0, "hash": ""}

    def _fingerprint_selector_js(self):
        """从 config 读取 fingerprint_selectors，安全转义后在 JS 中使用。"""
        if self.config and hasattr(self.config, 'fingerprint_selectors'):
            raw = self.config.fingerprint_selectors
        else:
            # 回退：通用 ARIA 角色
            raw = ('[role="dialog"]:not([style*="display: none"]), '
                   '[role="listbox"]:not([style*="display: none"]), '
                   '[role="menu"]:not([style*="display: none"])')
        # 转义单引号，去掉换行和多余空格
        return raw.replace("'", "\\'").replace("\n", " ").strip()

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
        """检测弹窗/下拉/菜单是否打开。选择器从 config 读取。"""
        try:
            sel = self._overlay_selector_js()
            return self.page.evaluate(f"""
                () => {{
                    function count(sel) {{ return document.querySelectorAll(sel).length; }}
                    return {{
                        overlay: count('{sel}'),
                    }};
                }}
            """)
        except Exception:
            return {}

    def _overlay_selector_js(self):
        """从 config 读取浮层检测选择器。"""
        if self.config and hasattr(self.config, 'modal_selectors'):
            raw = self.config.modal_selectors
        else:
            raw = ('[role="dialog"]:not([style*="display: none"]), '
                   '[role="listbox"]:not([style*="display: none"]), '
                   '[class*="modal"]:not([style*="display: none"])')
        return raw.replace("'", "\\'").replace("\n", " ").strip()

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
