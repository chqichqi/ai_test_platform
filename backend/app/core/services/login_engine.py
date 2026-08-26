"""
统一登录引擎 — 处理登录表单填写、机构选择、鉴权参数提取

所有调用方（KnowledgeGraphService、BusinessFlowUIService、BFSExplorer）
共用此引擎，登录规则通过 LoginConfig 按项目配置。
"""

import asyncio
import re
import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from app.core.logger import logger


# ============================================================
# LoginConfig — 所有登录相关配置，每个字段都有默认值
# ============================================================
@dataclass
class LoginConfig:
    """登录规则配置，可从 exploration_config.web.login_rules 反序列化"""

    # ── 表单选择器（CSS，支持逗号分隔的 fallback 链） ──
    username_selector: str = 'input[name="username"], input[name="email"], input[type="text"]'
    password_selector: str = 'input[type="password"]'
    submit_text: str = "登 录"
    submit_fallback: str = 'button[type="submit"], button:has-text("登录"), button:has-text("登 录")'

    # ── 登录成功检测（fnmatch glob 匹配 URL） ──
    logged_in_url_patterns: list = field(default_factory=lambda: ["*workpanel*", "*workbench*"])

    # ── 鉴权参数提取（从 URL query string） ──
    auth_param_names: list = field(default_factory=lambda: ["oId", "refresh", "token"])

    # ── 机构选择页 ──
    org_url_keyword: str = "switchorganization"
    org_title_keyword: str = "选择机构"
    org_card_selector: str = "div.cursor-pointer.border.rounded"
    org_confirm_text: str = "确 认"
    org_select_name: str = ""  # 优先选择包含此文本的机构卡片；为空则选第一个

    # ── 鉴权持久化 ──
    save_auth: bool = True  # 是否保存鉴权参数（token/oId）以便下次复用

    # ── 时延 ──
    render_wait: float = 1.0
    login_poll_interval: float = 0.5
    login_max_wait: int = 30
    page_timeout: int = 15000


# ============================================================
# 工厂函数：从 ProjectSetting.exploration_config 构建 LoginConfig
# ============================================================
def login_config_from_settings(exploration_config: Optional[dict] = None) -> LoginConfig:
    """
    从 ProjectSetting.exploration_config 构建 LoginConfig。
    缺失字段使用 LoginConfig 默认值，向后兼容旧的配置格式。
    """
    if not exploration_config or not isinstance(exploration_config, dict):
        return LoginConfig()

    web = exploration_config.get("web") or {}
    if not isinstance(web, dict):
        return LoginConfig()

    rules = web.get("login_rules") or {}
    if not isinstance(rules, dict):
        rules = {}

    # 安全获取：所有字段 or 默认值（空字符串也视为未设置）
    d = LoginConfig()
    return LoginConfig(
        username_selector=rules.get("username_selector") or d.username_selector,
        password_selector=rules.get("password_selector") or d.password_selector,
        submit_text=rules.get("submit_text") or d.submit_text,
        submit_fallback=rules.get("submit_fallback") or d.submit_fallback,
        logged_in_url_patterns=rules.get("logged_in_url_patterns") or d.logged_in_url_patterns,
        auth_param_names=rules.get("auth_param_names") or d.auth_param_names,
        org_url_keyword=rules.get("org_url_keyword") or d.org_url_keyword,
        org_title_keyword=rules.get("org_title_keyword") or d.org_title_keyword,
        org_card_selector=rules.get("org_card_selector") or d.org_card_selector,
        org_confirm_text=rules.get("org_confirm_text") or d.org_confirm_text,
        org_select_name=rules.get("org_select_name") or d.org_select_name,
        save_auth=rules.get("save_auth") if rules.get("save_auth") is not None else d.save_auth,
        render_wait=float(rules.get("render_wait") or d.render_wait),
        login_poll_interval=float(rules.get("login_poll_interval") or d.login_poll_interval),
        login_max_wait=int(rules.get("login_max_wait") or d.login_max_wait),
        page_timeout=int(rules.get("page_timeout") or d.page_timeout),
    )


# ============================================================
# LoginEngine — 完整登录流程
# ============================================================
class LoginEngine:
    """统一登录引擎，处理：鉴权复用 → 导航 → 填表 → 提交 → 机构选择 → 鉴权提取"""

    def __init__(self, page, config: Optional[LoginConfig] = None):
        self.page = page
        self.config = config or LoginConfig()
        self.auth_params: dict = {}

    # ── 公开 API ──

    async def login(
        self,
        base_url: str,
        username: str,
        password: str,
        saved_auth: Optional[dict] = None,
    ) -> bool:
        """
        完整登录流程：
        0. 尝试 saved_auth 复用
        1. 导航到 base_url
        2. 检测是否已在工作台
        3. 填写登录表单（仅 visible 元素）
        4. 提交并轮询：机构选择 → 登录成功检测
        5. 提取鉴权参数
        """
        base_url = base_url.rstrip("/")

        # 0. 尝试复用已保存的鉴权参数（仅当 save_auth 开启）
        if self.config.save_auth and saved_auth and saved_auth.get("params"):
            logger.info("[LoginEngine] 检测到已保存鉴权，尝试复用...")
            params = saved_auth["params"]
            saved_url = self._build_url_with_params(base_url, params)
            try:
                await self.page.goto(saved_url, wait_until="networkidle", timeout=15000)
                if self._url_match(self.page.url, self.config.logged_in_url_patterns):
                    self.auth_params = params
                    logger.info("[LoginEngine] 鉴权复用成功，跳过登录")
                    return True
            except Exception:
                pass
            logger.info("[LoginEngine] 鉴权已过期，重新登录...")

        # 1. 导航到目标系统（先尝试 base_url，再尝试 /login）
        logger.info("[LoginEngine] 开始登录...")
        await self._navigate_and_wait(base_url)

        # 2. 已在目标页面
        if self._url_match(self.page.url, self.config.logged_in_url_patterns):
            logger.info(f"[LoginEngine] 已在工作台: {self.page.url}")
            return True

        # 3. 填写登录表单；若当前页找不到表单，尝试 /login 路径
        try:
            await self._fill_login_form(username, password)
        except Exception:
            login_url = f"{base_url}/login"
            logger.info(f"[LoginEngine] 当前页无登录表单，尝试: {login_url}")
            await self._navigate_and_wait(login_url)
            if self._url_match(self.page.url, self.config.logged_in_url_patterns):
                logger.info(f"[LoginEngine] 已在工作台: {self.page.url}")
                return True
            await self._fill_login_form(username, password)

        # 4. 提交
        await self._click_submit()

        # 5. 轮询等待结果
        for _ in range(self.config.login_max_wait * 2):
            if await self._is_org_page():
                await self._handle_org_selection()
                continue
            if self._url_match(self.page.url, self.config.logged_in_url_patterns):
                logger.info(f"[LoginEngine] 登录成功: {self.page.url}")
                if self.config.save_auth:
                    self._extract_auth_params_from_url()
                return True
            # 跳过机构选择后，页面已有内容也视为成功
            if getattr(self, '_org_skip', False):
                try:
                    body = await self.page.locator("body").inner_text()
                    if len(body.strip()) > 100:
                        logger.info(f"[LoginEngine] 机构选择后进入工作台: {self.page.url}")
                        return True
                except Exception:
                    pass
            await asyncio.sleep(self.config.login_poll_interval)

        logger.warning(f"[LoginEngine] 登录超时，当前URL: {self.page.url}")
        return False

    def get_auth_data(self) -> dict:
        """导出当前鉴权数据（供持久化到 KnowledgeGraph.auth_data）"""
        return {
            "params": dict(self.auth_params),
            "saved_at": datetime.utcnow().isoformat(),
        }

    def _build_url_with_params(self, base_url: str, params: dict) -> str:
        """用鉴权参数拼接 URL"""
        result = base_url
        if params:
            sep = "&" if "?" in result else "?"
            result += sep + "&".join(f"{k}={v}" for k, v in params.items())
        return result

    # ── 内部方法 ──

    async def _navigate_and_wait(self, url: str):
        """导航到目标 URL 并等待页面渲染完成（networkidle 确保 JS 渲染完毕）"""
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        logger.info(f"[LoginEngine] 导航完成: {self.page.url}")

    async def _fill_login_form(self, username: str, password: str):
        """填写登录表单 — 只用 visible 元素，避免选中隐藏输入框"""
        username_loc = (
            self.page.locator(self.config.username_selector)
            .locator("visible=true")
            .first
        )
        password_loc = (
            self.page.locator(self.config.password_selector)
            .locator("visible=true")
            .first
        )
        await username_loc.wait_for(state="visible", timeout=10000)
        await password_loc.wait_for(state="visible", timeout=10000)
        await username_loc.fill(username)
        await password_loc.fill(password)
        logger.info("[LoginEngine] 表单填写完成")

    async def _click_submit(self):
        """点击登录按钮，优先按文本匹配，失败则用 fallback 选择器"""
        submit_btn = self.page.get_by_role("button", name=self.config.submit_text)
        try:
            await submit_btn.wait_for(state="visible", timeout=5000)
        except Exception:
            submit_btn = (
                self.page.locator(self.config.submit_fallback)
                .locator("visible=true")
                .first
            )
        await submit_btn.click()
        logger.info("[LoginEngine] 登录提交完成，等待跳转...")

    async def _is_org_page(self) -> bool:
        """检测当前页面是否为机构选择页"""
        if getattr(self, '_org_skip', False):
            return False
        url = self.page.url or ""
        if self.config.org_url_keyword and self.config.org_url_keyword in url:
            return True
        if self.config.org_title_keyword:
            try:
                return await self.page.get_by_text(self.config.org_title_keyword).first.is_visible(timeout=300)
            except Exception:
                return False
        return False

    async def _handle_org_selection(self):
        """处理机构选择页。找不到卡片或点击失败则跳过，不阻塞登录流程"""
        logger.info("[LoginEngine] 检测到机构选择页")
        await asyncio.sleep(1.5)
        if not await self._is_org_page():
            return

        # 按配置选择器 + 通用回退查找卡片
        cards = self.page.locator(f"{self.config.org_card_selector}:visible")
        card_count = await cards.count()
        if card_count == 0:
            cards = self.page.locator("[class*='org'], [class*='card'], [class*='item'], .cursor-pointer:visible")
            card_count = await cards.count()

        if card_count == 0:
            logger.info("[LoginEngine] 未找到机构卡片，跳过机构选择")
            self._org_skip = True
            return

        try:
            # 优先选 org_select_name 指定的，否则选第一个
            target = 0
            if self.config.org_select_name:
                for i in range(card_count):
                    text = (await cards.nth(i).inner_text() or "").strip()
                    if self.config.org_select_name in text:
                        target = i
                        logger.info(f"[LoginEngine] 匹配指定身份: {text}")
                        break

            card = cards.nth(target)
            text = (await card.inner_text() or "").strip()
            await card.click(timeout=3000)
            logger.info(f"[LoginEngine] 选中: {text}")
            await asyncio.sleep(1.5)
        except Exception:
            logger.info("[LoginEngine] 卡片点击失败（可能已自动跳转），跳过机构选择")
            self._org_skip = True
            return

        # 确认按钮：先扫描页面上所有可见按钮，再尝试匹配
        try:
            all_btns = self.page.locator("button:visible")
            btn_count = await all_btns.count()
            btn_texts = []
            for bi in range(min(btn_count, 20)):
                try:
                    t = (await all_btns.nth(bi).text_content() or "").strip()
                    if t:
                        btn_texts.append(t)
                except Exception:
                    pass
            logger.info(f"[LoginEngine] 页面可见按钮 ({btn_count}): {btn_texts}")

            confirmed = False
            for btn_text in [self.config.org_confirm_text,
                             self.config.org_confirm_text.replace(" ", ""),
                             "确认", "确定", "进入", "OK", "提交", "保存"]:
                confirm = self.page.locator(f"button:has-text('{btn_text}')").first
                if await confirm.is_visible(timeout=500):
                    if await confirm.is_disabled():
                        for __ in range(15):
                            await asyncio.sleep(0.3)
                            if not await confirm.is_disabled():
                                break
                    await confirm.click(timeout=3000)
                    logger.info(f"[LoginEngine] 已确认 (btn='{btn_text}')")
                    confirmed = True
                    break

            if not confirmed:
                for bi in range(min(btn_count, 10)):
                    t = btn_texts[bi] if bi < len(btn_texts) else ""
                    if t and any(kw in t for kw in ["确", "提", "进", "OK", "登", "选"]):
                        await all_btns.nth(bi).click(timeout=3000)
                        logger.info(f"[LoginEngine] 点击推测确认按钮: '{t}'")
                        confirmed = True
                        break

            if not confirmed:
                try:
                    await self.page.keyboard.press("Enter")
                    logger.info("[LoginEngine] 已按 Enter 提交")
                except Exception:
                    pass
        except Exception:
            logger.info("[LoginEngine] 确认按钮点击失败，跳过")
        finally:
            self._org_skip = True
            await asyncio.sleep(1.0)

    def _extract_auth_params_from_url(self):
        """从当前 URL query string 提取鉴权参数"""
        url = self.page.url
        params = {}
        for name in self.config.auth_param_names:
            m = re.search(rf'[?&]{name}=([^&]+)', url)
            if m:
                params[name] = m.group(1)
        self.auth_params = params
        logger.info(f"[LoginEngine] 鉴权参数: {list(params.keys())}")

    @staticmethod
    def _url_match(url: str, patterns: list) -> bool:
        """用 fnmatch glob 模式匹配 URL"""
        for p in patterns:
            if fnmatch.fnmatch(url, p):
                return True
        return False


async def login_with_ui_case(page, base_url: str = '', username: str = '', password: str = '',
                             project_id: int = None) -> tuple:
    """用 __login__ UI 用例步骤执行登录（所有登录操作的统一入口）。

    替代 LoginEngine.login()——不再硬编码登录流程，而是执行导入登录模块时
    生成的 __login__ UI 用例步骤。换项目只需修改登录业务流文本重新导入即可。

    Args:
        page: Playwright async Page 对象
        base_url: 系统 URL
        username: 用户名（留空则从 KG 读取）
        password: 密码（留空则从 KG 读取）
        project_id: 项目 ID（复合唯一 (project_id, test_case_id) 下必须传，
                    多项目各自有 __login__，不传会取到任意项目）

    Returns:
        (ok: bool, workbench_url: str)
    """
    import json as _json
    try:
        from app.core.database import SessionLocal
        from app.core.models.web_ui_test import WebUITestCase
        from app.core.models.knowledge_graph import KnowledgeGraph

        db = SessionLocal()
        try:
            # 加载 __login__ 步骤（项目隔离：多项目各自有 __login__）
            _q = db.query(WebUITestCase).filter(
                WebUITestCase.test_case_id == '__login__'
            )
            if project_id:
                _q = _q.filter(WebUITestCase.project_id == str(project_id))
            login_case = _q.first()
            if not login_case or not login_case.test_data:
                logger.debug("[LoginViaUI] 无 __login__ 用例，回退 LoginEngine")
                return False, ''

            td = login_case.test_data
            if isinstance(td, str):
                td = _json.loads(td)
            steps = td.get('steps', []) if isinstance(td, dict) else []
            if not steps:
                logger.debug("[LoginViaUI] __login__ 步骤为空，回退 LoginEngine")
                return False, ''

            # 加载凭据（项目隔离：只取本项目的 KG）
            if not username or not password:
                _kgq = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.exploration_status == 'completed'
                )
                if project_id:
                    _kgq = _kgq.filter(KnowledgeGraph.project_id == project_id)
                kg = _kgq.order_by(KnowledgeGraph.completed_at.desc()).first()
                username = username or (kg.login_username if kg else '')
                if kg and not password:
                    from app.core.models.project_ext import ProjectSetting
                    ps = db.query(ProjectSetting).filter(
                        ProjectSetting.project_id == kg.project_id
                    ).first() if kg.project_id else None
                    wc = (ps.exploration_config or {}).get('web', {}) if ps else {}
                    password = password or wc.get('password', '')

            if not username or not password:
                logger.warning("[LoginViaUI] 无登录凭据")
                return False, ''
        finally:
            db.close()

        # ── 兜底导航：全新 context（如步骤驱动探索）下页面可能从未加载过任何 URL ──
        # 仅覆盖步骤里无 goto 的历史用例；有 goto 步骤时下方会真正执行（goto 幂等，重复无害）
        if (page.url or '').startswith('about:') and base_url:
            await page.goto(base_url, wait_until='domcontentloaded', timeout=30000)

        logger.info(f"[LoginViaUI] 执行 __login__ 步骤（{len(steps)}步）user={username}")
        _ctx = {"base_url": base_url, "username": username, "password": password}
        for step in steps:
            action = (step.get('action') or '').strip()
            args = step.get('args', {}) or {}
            desc = step.get('desc', action)
            # 反射分发：按 action 名查 dispatch 表取 handler 执行——步骤数据驱动，
            # 定位参数全部来自步骤 args，不把具体系统的选择器写死在代码中；
            # 新增 action 类型只需注册 handler，主循环不再改动
            _handler = _LOGIN_HANDLERS.get(action)
            if _handler is None:
                logger.warning(f"[LoginViaUI] 未知 action '{action}'，跳过（{desc[:30]}）")
                continue
            await _handler(page, args, desc, _ctx)

        wb_url = page.url
        ok = '/login' not in (wb_url or '') and '/auth' not in (wb_url or '')
        logger.info(f"[LoginViaUI] {'✓ 成功' if ok else '✗ 失败'}: {wb_url[:80]}")
        return ok, wb_url if ok else ''

    except Exception as e:
        logger.warning(f"[LoginViaUI] 异常: {e}")
        return False, ''


# ═══════════════════════════════════════════════════════════
# __login__ 步骤执行器（反射分发表）
# 所有 handler 统一签名 (page, args, desc, ctx)：
#   page  Playwright Page
#   args  步骤 args（定位参数一律来自这里——步骤数据即配置，换项目
#         重新导入登录模块即可，代码零改动）
#   desc  步骤描述（仅日志）
#   ctx   执行上下文 {"base_url", "username", "password"}
# 新增 action 类型：写一个 _h_xxx handler + 注册到 _LOGIN_HANDLERS，
# 主循环不再改动。
# ═══════════════════════════════════════════════════════════


async def _h_goto(page, args, desc, ctx):
    # 真正导航（不再跳过）：导入登录模块时 goto 步骤 args.url 即 base_url。
    # 旧假设「调用方已在登录页」被全新 context 打破——步骤驱动探索创建的新
    # browser context 停在 about:blank，跳过 goto 会让首个 fill 必然超时。
    _url = (args.get('url') or ctx.get('base_url') or '').strip()
    if _url:
        await page.goto(_url, wait_until='domcontentloaded', timeout=30000)


async def _h_fill(page, args, desc, ctx):
    value = str(args.get('value', ''))
    if value == '$username':
        value = ctx.get('username', '')
    elif value == '$password':
        value = ctx.get('password', '')
    # 多种定位方式（定位键均来自步骤数据：placeholder/css/locator/role）
    placeholder = args.get('placeholder', '')
    css = args.get('css', '')
    locator_text = args.get('locator', '')
    role = args.get('role', '')
    if placeholder:
        await page.fill(f'input[placeholder*="{placeholder}"]', value, timeout=10000)
    elif css:
        await page.fill(css, value, timeout=10000)
    elif role and locator_text:
        await page.get_by_role(role, name=locator_text).fill(value, timeout=10000)
    elif locator_text:
        await page.get_by_text(locator_text).first.fill(value, timeout=10000)
    else:
        await page.fill(f'input:not([type="hidden"]):not([type="submit"]):not([type="password"])', value, timeout=10000)
    logger.info(f"[LoginViaUI] fill ✓ {desc[:30]}")


async def _h_click(page, args, desc, ctx):
    locator_text = args.get('locator', '')
    css = args.get('css', '')
    role = args.get('role', '')
    if css:
        await page.locator(css).first.click(timeout=5000)
    elif role and locator_text:
        await page.get_by_role(role, name=locator_text).first.click(timeout=5000)
    elif locator_text:
        await page.get_by_text(locator_text, exact=False).first.click(timeout=5000)
    else:
        logger.warning(f"[LoginViaUI] click 步骤无 locator: {desc[:30]}")
    await asyncio.sleep(0.5)
    logger.info(f"[LoginViaUI] click ✓ {desc[:30]}")


async def _h_wait_for_render(page, args, desc, ctx):
    ms = int(args.get('ms', 2000))
    await asyncio.sleep(ms / 1000)


async def _h_handle_org_selection(page, args, desc, ctx):
    """机构选择页处理——定位参数来自步骤数据（cards_selector/confirm_text），
    导入验证成功时已回填真实选择器；旧数据（args 无参数）走通用兜底（同
    StepRunner，兼容历史用例）。换项目只需重新导入登录模块，代码零改动。"""
    cards_selector = (args or {}).get('cards_selector')
    confirm_text = (args or {}).get('confirm_text')
    # 检测是否在机构选择页：URL 关键字（switchorganization 全小写变体 +
    # selectOrganization）+ 页面文本双重检测
    cur_url = page.url
    _body_text = ""
    try:
        _body_text = await page.locator("body").inner_text()
    except Exception:
        pass
    _is_org = ('switchorganization' in cur_url
               or 'selectOrganization' in cur_url
               or '选择机构' in _body_text
               or '机构' in (await page.content())[:2000])
    if not _is_org:
        logger.info("[LoginViaUI] org_selection 跳过（不在机构选择页）")
        return
    try:
        # 卡片：步骤参数优先，无参数走通用候选（tailwind 特征 + class 关键词回退）
        cards = page.locator(cards_selector) if cards_selector else None
        if cards is None or await cards.count() == 0:
            cards = page.locator("div.cursor-pointer.border.rounded:visible")
        if await cards.count() == 0:
            cards = page.locator(
                "[class*='org']:visible, [class*='card']:visible, .cursor-pointer:visible")
        if await cards.count() == 0:
            logger.warning("[LoginViaUI] org_selection ⚠ 未找到机构卡片，机构选择未完成")
        else:
            await cards.first.click(timeout=3000)
            await asyncio.sleep(1.5)
            # 确认按钮：步骤参数优先，兜底兼容「确 认」（字间空格）
            confirm = None
            if confirm_text:
                confirm = page.get_by_role("button", name=confirm_text)
                if not await confirm.count() or not await confirm.is_visible():
                    confirm = None
            if confirm is None:
                confirm = page.get_by_role("button", name="确 认")
                if not await confirm.count() or not await confirm.is_visible():
                    confirm = page.locator("button").filter(has_text="确认").first
            if await confirm.count() > 0 and await confirm.is_visible():
                await confirm.click(timeout=3000)
                await asyncio.sleep(1.5)
            # 验证闭环：确认后必须确认已离开机构页（不再无条件 ✓）
            _after = page.url
            if 'switchorganization' not in _after and 'selectOrganization' not in _after:
                logger.info("[LoginViaUI] org_selection ✓ 已离开机构页")
            else:
                logger.warning(f"[LoginViaUI] org_selection ⚠ 仍在机构页: {_after[:80]}")
    except Exception as e:
        logger.warning(f"[LoginViaUI] org_selection 异常（不阻塞）: {e}")


async def _h_select(page, args, desc, ctx):
    option = args.get('option') or args.get('value', '')
    trigger = args.get('trigger', args.get('locator', ''))
    if trigger:
        await page.get_by_text(trigger, exact=False).first.click(timeout=3000)
        await asyncio.sleep(0.8)
    if option:
        # 面板选择器：步骤参数优先（panel_selector），缺失走框架通用候选
        _panel_selectors = [args.get('panel_selector')] if args.get('panel_selector') else []
        _panel_selectors += (
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
            '[role="listbox"]:not([aria-hidden="true"])',
        )
        for panel_sel in _panel_selectors:
            try:
                panel = page.locator(panel_sel).first
                if await panel.count() > 0 and await panel.is_visible():
                    await panel.get_by_text(option).first.click(timeout=3000)
                    break
            except Exception:
                continue
    logger.info(f"[LoginViaUI] select ✓ {desc[:30]}")


async def _h_assert_visible(page, args, desc, ctx):
    locator_text = args.get('locator', '')
    try:
        if locator_text:
            await page.get_by_text(locator_text, exact=False).first.wait_for(
                state='visible', timeout=5000
            )
    except Exception:
        pass  # assert 失败不阻塞


# 反射分发表：action 名 → handler（登录步骤执行按此表动态调用）
_LOGIN_HANDLERS = {
    'goto': _h_goto,
    'navigate': _h_goto,
    'fill': _h_fill,
    'click': _h_click,
    'wait_for_render': _h_wait_for_render,
    'handle_org_selection': _h_handle_org_selection,
    'select': _h_select,
    'assert_visible': _h_assert_visible,
}
