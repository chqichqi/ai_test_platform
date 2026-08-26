"""
工作台 Page Object
基于 SKILL 中「工作台模块」业务规范生成。

工作台分两大区域：
- 上半部分：指标总览（患者概览/疾病统计/审核任务/物流看板/随访监控）+ 自定义指标
- 下半部分：预警信息（房颤预警/佩戴预警/测量预警）
"""
from typing import Optional, Dict, List
import re
import allure
from playwright.sync_api import Page, Locator, expect

from tests.utils.config_utils import get_base_url


# ============================================================
# 业务常量
# ============================================================

# 指标总览：分类 → 卡片标题列表（与 tt 环境实测页面文本一致）
METRIC_CATEGORIES: Dict[str, List[str]] = {
    "患者概览": ["患者人数", "Smart 报告(份)"],
    "疾病统计": [
        "室早", "室速", "室颤",
        "停搏", "心动过速", "心动过缓",
        "二联律", "三联律",
        "房颤", "房速", "房扑", "房早", "持续性房颤", "阵发性房颤",
    ],
    "审核任务": ["待审核数据", "待审核报告", "待审核周报"],
    "物流看板": ["待发货数", "预约回收数"],
    "随访监控": [
        "项目个数", "入组人数",
        "进行中人数", "待随访人数", "延期人数", "中止人数",
    ],
}

# 仅有「新增数量」无「总数」的分类（SKILL 关键断言1.3）
COUNT_ONLY_CATEGORIES = {"审核任务", "物流看板", "随访监控"}

# 预警卡片（下半部分）
WARNING_CARDS = ["房颤预警", "佩戴预警", "测量预警"]


# ============================================================
# Page Object
# ============================================================
class WorkbenchPage:
    """工作台页面对象"""

    PATH = "/#/workpanel"

    def __init__(self, page: Page):
        self.page = page

        # ---- 顶层元素 ----
        self.page_title = page.get_by_text("工作台").first
        # 「自定义」入口按钮（点击后跳转到 /workpanel/customCard 自定义页面）
        self.custom_metric_button = page.get_by_text(re.compile(r"^自定义(?:指标)?$")).first

        # ---- customCard 页面（自定义模式）按钮 ----
        # 「保存布局」「取 消」位于 customCard 页面底部，不在弹窗内
        self.btn_save_layout = page.get_by_role("button", name=re.compile(r"^保\s*存\s*布\s*局$"))
        self.btn_cancel = page.get_by_role("button", name=re.compile(r"^取\s*消$"))

        # ---- 「分类选择」弹窗内按钮 ----
        # 弹窗标题：「自定义」；弹窗内按钮：「重 置」「去预览」「关闭」
        self.custom_dialog = page.get_by_role("dialog", name=re.compile(r"自定义"))
        self.btn_reset = self.custom_dialog.get_by_role(
            "button", name=re.compile(r"^重\s*置$")
        )
        self.btn_preview = self.custom_dialog.get_by_role(
            "button", name=re.compile(r"^去\s*预\s*览$")
        )
        self.btn_dialog_close = self.custom_dialog.get_by_role(
            "button", name=re.compile(r"^关闭$")
        )

    # ----------------------------------------------------------
    # 基础导航
    # ----------------------------------------------------------
    @allure.step("进入工作台页面（env={env}, force={force}）")
    def goto(self, env: str = "test", force: bool = False) -> None:
        """
        进入工作台。
        若复用模式下已在工作台，避免重复 goto 导致额外重定向。
        """
        base_url = get_base_url(env)
        current = self.page.url or ""
        if not force and ("workpanel" in current or "workbench" in current):
            return
        self.page.goto(base_url + self.PATH, wait_until="domcontentloaded")
        self.wait_ready()

    def wait_ready(self, timeout: int = 15000) -> None:
        """等待页面稳定"""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass
        self.page.wait_for_timeout(1500)

    def is_loaded(self) -> bool:
        """是否已停留在工作台 URL"""
        url = self.page.url or ""
        return "workpanel" in url or "workbench" in url

    # ----------------------------------------------------------
    # 通用：指标卡片定位与解析
    # ----------------------------------------------------------
    def _card_locator(self, name: str) -> Locator:
        """
        定位某个指标/预警卡片的容器。
        使用 get_by_text + xpath ancestor，避免硬编码 CSS 选择器。
        """
        return self.page.get_by_text(name, exact=True).first.locator(
            "xpath=ancestor::*[self::div or self::li][1]"
        )

    def card_exists(self, name: str, timeout: int = 5000) -> bool:
        """指标卡片是否存在（动态指标可能被自定义移除）"""
        try:
            loc = self.page.get_by_text(name, exact=True).first
            # 等待元素出现在 DOM 即可（不要求可视，避免被滚动遮挡误判）
            loc.wait_for(state="attached", timeout=timeout)
            return True
        except Exception:
            return False

    @allure.step("解析卡片[{name}]数据")
    def get_card_data(self, name: str) -> Dict[str, Optional[str]]:
        """
        解析卡片数字：返回 {title, total, today_new}
        - total: 卡片上的主数字（可能为 None 表示卡片只有新增）
        - today_new: "今日新增+N" / "+N" 中的数字（无则 None）
        """
        if not self.card_exists(name):
            return {"title": name, "total": None, "today_new": None}

        full_text = (self._card_locator(name).inner_text(timeout=5000) or "").strip()

        today_new = None
        # 匹配 "今日新增 +0" / "今日新增+12" / "+5"（仅当独立出现时）
        m = re.search(r"今日新增\s*([+\-]?\d+)", full_text)
        if m:
            today_new = m.group(1).lstrip("+")
        else:
            m = re.search(r"(?<!\d)([+\-]\d+)(?!\d)", full_text)
            if m:
                today_new = m.group(1).lstrip("+")

        # 总数：取卡片中第一个独立的数字（排除"今日新增"那一段）
        text_for_total = re.sub(r"今日新增\s*[+\-]?\d+", "", full_text)
        text_for_total = re.sub(r"[+\-]\d+", "", text_for_total)
        m2 = re.search(r"\d+", text_for_total)
        total = m2.group(0) if m2 else None

        return {"title": name, "total": total, "today_new": today_new}

    @allure.step("点击指标卡片[{name}]")
    def click_card(self, name: str) -> None:
        """点击指标/预警卡片"""
        card = self._card_locator(name)
        card.scroll_into_view_if_needed()
        card.click()
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        self.page.wait_for_timeout(800)

    # ----------------------------------------------------------
    # 自定义指标
    # 点击「自定义」会跳转到 /workpanel/customCard 自定义模式页：
    #   - 自动弹出「分类选择」对话框（标题=「自定义」），内含「重置」「去预览」「关闭」
    #   - 页面底部固定按钮：「取 消」「保存布局」
    #   - 「取 消」/「保存布局」都会返回 /workpanel
    # ----------------------------------------------------------
    @allure.step("点击「自定义」入口进入自定义模式")
    def open_custom_metric_dialog(self) -> None:
        """点击「自定义」入口，进入 customCard 自定义模式"""
        self.custom_metric_button.click()
        # 等待路由切换到 customCard
        try:
            self.page.wait_for_url(re.compile(r"customCard"), timeout=8000)
        except Exception:
            pass
        self.page.wait_for_timeout(600)

    def custom_dialog_visible(self) -> bool:
        """「分类选择」对话框是否可见"""
        try:
            return self.custom_dialog.is_visible(timeout=2000)
        except Exception:
            return False

    def in_custom_card_page(self) -> bool:
        """当前是否处于 customCard 自定义模式页"""
        return "customCard" in (self.page.url or "")

    @allure.step("关闭自定义模式（先关弹窗 → 点取消返回工作台）")
    def close_custom_metric_dialog(self) -> None:
        """
        关闭自定义模式：优先点对话框「关闭」按钮收起 popup（仍停在 customCard），
        随后点底部「取 消」按钮返回工作台，确保后续用例无残留状态。
        """
        try:
            if self.custom_dialog.is_visible(timeout=1000):
                self.btn_dialog_close.click(timeout=2000)
                self.page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            if self.btn_cancel.is_visible(timeout=1500):
                self.btn_cancel.click(timeout=3000)
                # 等待返回工作台
                try:
                    self.page.wait_for_url(
                        re.compile(r"workpanel(?!/customCard)"), timeout=5000
                    )
                except Exception:
                    pass
        except Exception:
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(400)

    @allure.step("点击对话框「重置」按钮")
    def reset_custom_layout(self) -> None:
        """点击对话框内「重置」按钮（需对话框已打开）"""
        self.btn_reset.click()
        self.page.wait_for_timeout(400)

    @allure.step("点击「保存布局」并等待返回工作台")
    def save_custom_layout(self) -> None:
        """
        保存自定义布局：「保存布局」按钮位于 customCard 页面底部，
        被弹窗遮挡时先关闭弹窗再点击。点击后返回 /workpanel。
        """
        # 关闭可能挡住底部按钮的对话框
        try:
            if self.custom_dialog.is_visible(timeout=800):
                self.btn_dialog_close.click(timeout=2000)
                self.page.wait_for_timeout(300)
        except Exception:
            pass
        self.btn_save_layout.click()
        try:
            self.page.wait_for_url(re.compile(r"workpanel(?!/customCard)"), timeout=5000)
        except Exception:
            pass
        self.page.wait_for_timeout(600)

    # ----------------------------------------------------------
    # 预警卡片（下半部分）
    # ----------------------------------------------------------
    def _warning_card_title_locator(self, name: str) -> Locator:
        """
        预警卡片标题定位。标题可能为：「房颤预警」/「房颤预警(3)」/「佩戴预警 (1)」。
        """
        pattern = re.compile(rf"^{re.escape(name)}\s*(?:\(\s*\d+\s*\))?$")
        return self.page.get_by_text(pattern).first

    def _warning_card_container(self, name: str) -> Locator:
        """
        预警卡片的容器 div（含标题 + 数据区）。
        各预警卡片 DOM 结构不同，分类处理：
          - 房颤预警：标题位于 .ant-tabs-extra-content，列表在同一 .ant-tabs 容器内
            → 容器 = 最近的 .ant-tabs 祖先
          - 佩戴/测量预警：标题(.ml-1.font-medium) 与数据(.divide-y 内的兄弟 div) 共同位于 .pb-3 容器
            → 容器 = 最近的 .pb-3 祖先
        """
        title = self._warning_card_title_locator(name)
        if name == "房颤预警":
            return title.locator(
                "xpath=ancestor::div[contains(concat(' ',normalize-space(@class),' '),' ant-tabs ')][1]"
            )
        # 佩戴预警 / 测量预警
        return title.locator(
            "xpath=ancestor::div[contains(concat(' ',normalize-space(@class),' '),' pb-3 ')][1]"
        )

    @allure.step("校验预警卡片[{name}]是否可见")
    def warning_card_exists(self, name: str) -> bool:
        """预警卡片标题存在性（兼容带计数后缀）。先滚动到页面底部确保下半部分加载/可见。"""
        try:
            self._scroll_to_warning_section()
        except Exception:
            pass
        try:
            loc = self._warning_card_title_locator(name)
            loc.wait_for(state="attached", timeout=5000)
            return True
        except Exception:
            return False

    def _scroll_to_warning_section(self) -> None:
        """滚动到页面底部使下半部分（预警信息）进入视口"""
        try:
            self.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(400)
        except Exception:
            pass

    @allure.step("判断预警卡片[{name}]是否暂无数据")
    def warning_has_no_data(self, name: str) -> bool:
        """
        预警卡片是否处于「无可用数据」状态。
        只在明确显示「暂无数据」或 (0) 时才返回 True
        """
        if not self.warning_card_exists(name):
            return True
        try:
            card = self._warning_card_container(name)
            # 只有明确出现「暂无数据」文本才认为无数据
            try:
                if card.get_by_text("暂无数据").first.is_visible(timeout=1500):
                    return True
            except Exception:
                pass
            # 只有标题明确带 (0) 才认为无数据
            raw = (card.inner_text(timeout=3000) or "").strip()
            if re.search(rf"{re.escape(name)}\s*\(\s*0\s*\)", raw):
                return True
            # 其他情况都认为有数据，不要跳过测试
            return False
        except Exception:
            # 异常时也不要跳过，让测试继续执行
            return False

    @allure.step("解析预警卡片[{name}]第一条记录信息")
    def get_warning_first_patient_info(self, name: str) -> Dict[str, Optional[str]]:
        """
        获取某个预警卡片中第一条记录的关键文本。
        房颤预警：尝试解析患者姓名/编号、占比%、有效时长、负荷时长
        佩戴/测量预警：仅返回患者编号/姓名
        """
        info: Dict[str, Optional[str]] = {"raw": None, "patient": None, "percent": None}
        if not self.warning_card_exists(name):
            return info
        try:
            card = self._warning_card_container(name)
            raw = (card.inner_text(timeout=5000) or "").strip()
            info["raw"] = raw
            # 患者编号（数字串，>=6位）
            m = re.search(r"\b(\d{6,})\b", raw)
            if m:
                info["patient"] = m.group(1)
            else:
                # 取「暂无数据」之外的第一行非空文本
                noise = {"图表", "列表", "全部", "暂无数据"}
                title_pattern = re.compile(rf"^{re.escape(name)}\s*(\(\s*\d+\s*\))?$")
                for line in raw.splitlines():
                    line = line.strip()
                    if not line or line in noise or title_pattern.match(line):
                        continue
                    info["patient"] = line
                    break
            mp = re.search(r"(\d+(?:\.\d+)?)\s*%", raw)
            if mp:
                info["percent"] = mp.group(1)
        except Exception:
            pass
        return info

    @allure.step("点击预警卡片[{name}]第一条记录，跳转患者详情")
    def click_warning_first_item(self, name: str) -> Dict[str, Optional[str]]:
        """
        点击预警卡片中第一条记录并跳转到患者详情。
        返回跳转前记录的数据。
        策略（按卡片结构差异分别处理）：
          - 房颤预警：点击卡片内第一个 `<li>` 行
          - 佩戴/测量预警：点击 patient_text 对应的可点击元素（cursor=pointer）
        """
        info = self.get_warning_first_patient_info(name)
        card = self._warning_card_container(name)
        patient_text = info.get("patient")

        clicked = False
        # 1) 房颤预警：直接点 li
        if name == "房颤预警":
            try:
                first_li = card.locator("ul li").first
                if first_li.count() > 0:
                    first_li.scroll_into_view_if_needed()
                    first_li.click(timeout=8000)
                    clicked = True
            except Exception:
                pass

        # 2) 佩戴/测量预警：点 patient_text 对应的元素
        if not clicked and isinstance(patient_text, str) and patient_text:
            try:
                target = card.get_by_text(patient_text, exact=True).first
                target.scroll_into_view_if_needed()
                target.click(timeout=8000)
                clicked = True
            except Exception:
                pass

        # 3) 兜底：点击卡片内第一个 cursor:pointer 的子元素
        if not clicked:
            try:
                clickable = card.locator(
                    "xpath=.//*[contains(@style,'cursor: pointer') or @class[contains(.,'cursor-pointer')]]"
                ).first
                if clickable.count() > 0:
                    clickable.click(timeout=5000)
                    clicked = True
            except Exception:
                pass

        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        self.page.wait_for_timeout(800)
        return info

    # ----------------------------------------------------------
    # 预警卡片右侧过滤下拉框（已实测 tt 环境，2026-05-26）
    # 房颤预警：选项 [全部, ≥10, ≥20, ≥30, ≥40, ≥50]  → API afLoad
    # 佩戴预警：选项 [全部, 未发送, 已发送]              → API smsSendStatus
    # 测量预警：选项 [全部, 未发送, 已发送]              → API smsSendStatus
    # ----------------------------------------------------------

    # 各预警卡片下拉框预期选项（用于断言）
    WARNING_FILTER_OPTIONS: Dict[str, List[str]] = {
        "房颤预警": ["全部", "≥10", "≥20", "≥30", "≥40", "≥50"],
        "佩戴预警": ["全部", "未发送", "已发送"],
        "测量预警": ["全部", "未发送", "已发送"],
    }

    # 各预警卡片对应的列表请求接口（按 URL 子串匹配）
    WARNING_LIST_API_KEY: Dict[str, str] = {
        "房颤预警": "newPanel/afLoad",
        "佩戴预警": "newPanel/ppg-wear-warning",
        "测量预警": "newPanel/measure-warning",
    }

    # 各预警卡片下拉值 → API query 期望（None 表示不带过滤参数）
    WARNING_FILTER_API_PARAM: Dict[str, Dict[str, Optional[str]]] = {
        "房颤预警": {
            "全部": None,
            "≥10": "afLoad=10",
            "≥20": "afLoad=20",
            "≥30": "afLoad=30",
            "≥40": "afLoad=40",
            "≥50": "afLoad=50",
        },
        "佩戴预警": {
            "全部": None,
            "未发送": "smsSendStatus=0",
            "已发送": "smsSendStatus=1",
        },
        "测量预警": {
            "全部": None,
            "未发送": "smsSendStatus=0",
            "已发送": "smsSendStatus=1",
        },
    }

    def _warning_filter_trigger(self, name: str) -> Locator:
        """
        预警卡片标题右侧的下拉触发器（ant-select-selector）。
        策略：从标题元素出发，向上查找最近的包含 .ant-select-selector 的祖先 div，
        再在该祖先范围内取**第一个**下拉触发器（即该卡片本身的下拉，避免抓到相邻卡片）。
        """
        title = self._warning_card_title_locator(name)
        # 先尝试紧邻的祖先（房颤/佩戴/测量三个卡片中，每个标题都与自己的下拉在同一容器内）
        return title.locator(
            "xpath=ancestor::*[.//*[contains(@class,'ant-select-selector')]][1]"
            "//*[contains(@class,'ant-select-selector')][1]"
        )

    @allure.step("读取预警卡片[{name}]过滤下拉当前选项")
    def get_warning_filter_current(self, name: str) -> str:
        """获取预警过滤下拉当前显示文本"""
        try:
            txt = self._warning_filter_trigger(name).inner_text(timeout=3000) or ""
            return txt.strip().splitlines()[-1].strip() if txt else ""
        except Exception:
            return ""

    def open_warning_filter(self, name: str) -> None:
        """点击下拉触发器，展开选项面板"""
        trig = self._warning_filter_trigger(name)
        trig.scroll_into_view_if_needed()
        trig.click(timeout=5000)
        self.page.wait_for_timeout(300)

    @allure.step("枚举预警卡片[{name}]过滤下拉所有选项")
    def get_warning_filter_options(self, name: str) -> List[str]:
        """
        展开后读取下拉面板中的所有选项文本。
        ant-select 面板渲染在 body 末端，需从全局查找未隐藏的 dropdown。
        """
        self.open_warning_filter(name)
        try:
            self.page.wait_for_selector(
                ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option",
                timeout=5000,
            )
        except Exception:
            return []
        opts = self.page.locator(
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option"
        ).all()
        result = []
        for o in opts:
            try:
                result.append((o.inner_text() or "").strip())
            except Exception:
                continue
        # 收起下拉，避免影响后续操作
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass
        self.page.wait_for_timeout(200)
        return result

    @allure.step("预警卡片[{name}] 选择过滤项[{option}]")
    def select_warning_filter(self, name: str, option: str) -> None:
        """
        选择预警过滤下拉框某一项。
        :param name: 预警卡片名称（房颤预警/佩戴预警/测量预警）
        :param option: 选项文本（如 全部/≥10/已发送）
        """
        self.open_warning_filter(name)
        try:
            self.page.wait_for_selector(
                ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option",
                timeout=5000,
            )
        except Exception:
            pass
        # 优先精确匹配
        opt_locator = self.page.locator(
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option"
        ).filter(has_text=re.compile(rf"^{re.escape(option)}$"))
        try:
            opt_locator.first.click(timeout=5000)
        except Exception:
            # 兜底：包含匹配
            self.page.locator(
                ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option"
            ).filter(has_text=option).first.click(timeout=5000)
        # 等列表刷新
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        self.page.wait_for_timeout(500)

    def select_warning_filter_and_capture_request(
        self, name: str, option: str, timeout_ms: int = 8000
    ) -> Optional[str]:
        """
        选择某选项并捕获触发的列表接口请求 URL（用于断言 query 参数）。
        若超时未捕获到请求，返回 None。
        """
        api_key = self.WARNING_LIST_API_KEY[name]
        with self.page.expect_request(
            lambda req: api_key in req.url, timeout=timeout_ms
        ) as info:
            self.select_warning_filter(name, option)
        try:
            return info.value.url
        except Exception:
            return None
