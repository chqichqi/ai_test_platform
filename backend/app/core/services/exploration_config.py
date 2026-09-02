"""
探索配置中心 — 框架无关，ARIA-first，零硬编码。

所有魔法数字、业务术语、框架选择器全部参数化为配置字段。
换项目/换 UI 框架只需修改此文件——代码零修改。
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class ExplorationConfig:
    """探索引擎基础配置（平台无关）。"""

    # ═══════════════════════════════════════════════════════════
    # 时延
    # ═══════════════════════════════════════════════════════════
    # 动作后的最小稳定等待；探索不再对每一步固定睡眠 0.8~1.0s。
    click_wait: float = 0.12
    dropdown_wait: float = 0.20
    modal_wait: float = 0.4
    # Case 间复位后的快速就绪等待。只有页面确实未稳定时才继续等待。
    case_reset_ready_timeout: float = 2.0
    # 引导步骤定位失败时的等待上限；目标已在 DOM 中时不会等待。
    target_wait_timeout: float = 0.6
    # 引导动作发生后是否额外等待；默认只做轻量等待，导航/异步页面由状态验证决定。
    action_post_wait: float = 0.08
    # Guided 模式是否执行昂贵的 Phase-4 LLM 文档/POM 综合。UI 用例转化不依赖它，默认关闭。
    guided_phase4_synthesis: bool = False
    # 功能用例→UI 用例是否预生成共享 POM。默认关闭，避免在已有 KG locator 时额外产生一次 LLM 请求。
    generate_shared_pom: bool = False
    # 缺失步骤补充探索默认关闭：补充探索会重新执行同一业务动作，容易造成重复点击。
    # 需要时可在项目 exploration_config.explore 中显式设为 true。
    enable_supplement_exploration: bool = False

    # ═══════════════════════════════════════════════════════════
    # DFS 控制
    # ═══════════════════════════════════════════════════════════
    max_depth: int = 2
    max_clicks: int = 200

    # ═══════════════════════════════════════════════════════════
    # 文本 / 视觉
    # ═══════════════════════════════════════════════════════════
    min_text_len: int = 2
    min_element_width: int = 20
    min_element_height: int = 12

    # ═══════════════════════════════════════════════════════════
    # 页面就绪等待
    # ═══════════════════════════════════════════════════════════
    page_ready_timeout: float = 12.0
    page_ready_timeout_fast: float = 8.0
    page_goto_timeout: int = 15000         # page.goto() 超时 (ms)
    spa_render_min_len: int = 200           # SPA 渲染检测最小 body 文本长度
    spa_render_max_rounds: int = 8         # SPA 渲染检测最大轮询次数
    spa_render_interval: int = 250         # SPA 渲染检测轮询间隔 (ms)

    # ═══════════════════════════════════════════════════════════
    # 子名重试（末尾N字 + 分隔符拆解）
    # ═══════════════════════════════════════════════════════════
    sub_name_retry_lengths: List[int] = field(default_factory=lambda: [4, 3, 2])
    sub_name_min_len: int = 2
    sub_name_max_len: int = 4

    # ═══════════════════════════════════════════════════════════
    # 探索限制
    # ═══════════════════════════════════════════════════════════
    max_dropdowns: int = 20
    max_tabs: int = 15
    max_form_fields: int = 10
    max_loop_items: int = 50           # JS 循环最大迭代次数
    max_text_display: int = 60         # URL/文本截断显示长度
    max_name_length: int = 80          # 元素名称最大长度
    max_capture_elements: int = 200    # _capture_state 最多元素数
    max_behavior_items: int = 100      # behavior scan 最多元素数
    max_steps_per_module: int = 60     # 每模块最大步骤数（步骤驱动探索用）

    # ═══════════════════════════════════════════════════════════
    # 浏览器 / 视口
    # ═══════════════════════════════════════════════════════════
    viewport_width: int = 1280
    viewport_height: int = 900

    # ═══════════════════════════════════════════════════════════
    # 导航目标
    # ═══════════════════════════════════════════════════════════
    home_module_names: List[str] = field(default_factory=lambda: ["工作台", ""])
    # 识别为"首页"的模块名——这些模块直接探索，不需要侧边栏导航

    # ═══════════════════════════════════════════════════════════
    # 步骤驱动探索
    # ═══════════════════════════════════════════════════════════
    select_option_retries: int = 4      # 下拉选项定位最大重试次数
    select_option_interval: float = 0.3 # 下拉选项重试间隔 (s)
    # Phase 3 深度探索是否交互（默认 False：仅静态统计元素，
    # 不点击触发器/逐页翻页；步骤驱动场景交互已由引导循环完成）
    guided_p3_interactive: bool = False
    # 模块导航元素树遍历：子节点数超过该阈值的容器跳过（过滤导航容器/布局组件）
    nav_max_children: int = 4

    # ═══════════════════════════════════════════════════════════
    # 步骤解析器（多语言支持——默认中文，替换为英文/日文等即可切换）
    # ═══════════════════════════════════════════════════════════
    step_verb_patterns: List[Dict[str, str]] = field(default_factory=lambda: [
        {"pattern": r'^(点击|单击|点选|点)', "action": "click", "role": "button"},
        {"pattern": r'^(按下|按)', "action": "click", "role": "button"},
        {"pattern": r'^(填写|输入|填入|录入|键入|设置|写)', "action": "fill", "role": "textbox"},
        {"pattern": r'^(选择|下拉选择|选中|切换选项|改为|选取)', "action": "select", "role": "combobox"},
        {"pattern": r'^(悬停|悬浮|鼠标悬停)', "action": "hover", "role": "button"},
        {"pattern": r'^(右键|右击)', "action": "right_click", "role": "button"},
        {"pattern": r'^(切换|点Tab|切换到.*(?:页|标签|Tab))', "action": "tab_switch", "role": "tab"},
        {"pattern": r'^(进入|打开|跳转|访问|导航|点击进入|点击打开)', "action": "navigate", "role": "link"},
        {"pattern": r'^(等待|延时|暂停)', "action": "wait_for", "role": ""},
        {"pattern": r'^(验证|断言|检查|确认|应该显示|期望|预期)', "action": "validate", "role": ""},
        {"pattern": r'^(获取|记录|读取|抓取|提取|观察|查看)', "action": "validate", "role": ""},  # 数据提取类步骤视为验证
    ])
    step_role_suffixes: List[Dict[str, str]] = field(default_factory=lambda: [
        {"pattern": r'按钮$', "role": "button"},
        {"pattern": r'(链接|连接)$', "role": "link"},
        {"pattern": r'(输入框|文本框|搜索框|搜索栏)$', "role": "textbox"},
        {"pattern": r'(下拉框|下拉列表|下拉菜单|下拉|选择框)$', "role": "combobox"},
        {"pattern": r'(选项卡|Tab|标签页|标签)$', "role": "tab"},
        {"pattern": r'(菜单|菜单项)$', "role": "menuitem"},
        {"pattern": r'(图标|Icon)$', "role": "button"},
        {"pattern": r'(行|记录)$', "role": "table_row"},
    ])
    step_context_patterns: List[Dict[str, str]] = field(default_factory=lambda: [
        {"pattern": r'在弹窗中|在对话框中|在模态框中|弹出.*中', "context": "modal"},
        {"pattern": r'在表格(第?\d*)行', "context": "table_row"},
        {"pattern": r'在表单中', "context": "form"},
        {"pattern": r'在侧边栏|在导航栏|在菜单中', "context": "sidebar"},
    ])

    # ═══════════════════════════════════════════════════════════
    # 组件探索开关
    # ═══════════════════════════════════════════════════════════
    enable_modal_explore: bool = True
    enable_table_explore: bool = True

    # ═══════════════════════════════════════════════════════════
    # 探索期 API 接口捕获（ApiFlowCapture）——按项目可关/可调
    # ═══════════════════════════════════════════════════════════
    api_capture_enabled: bool = True            # 探索时是否捕获 API 接口生成用例
    api_capture_per_module: int = 20            # 每模块捕获接口上限（模块级独立计数，防海量）
    api_capture_max_total: int = 500            # 单次探索会话捕获全局硬上限（防病态海量）
    api_capture_max_body_bytes: int = 50000     # 响应体截断参考上限 (bytes)

    # ═══════════════════════════════════════════════════════════
    # 关键词 — 通用默认值（所有项目共享），DB web_cfg 可追加/覆盖
    # ═══════════════════════════════════════════════════════════
    noise_keywords: List[str] = field(default_factory=lambda: [
        "暂无数据", "今日新增", "Loading", "加载中", "No data", "No results",
        "—", "-", "N/A", "无", "空",
    ])
    danger_keywords: List[str] = field(default_factory=lambda: [
        "退出", "注销", "删除", "清空", "重置密码", "移除",
        "Delete", "Remove", "Clear", "Reset", "Logout", "Sign out",
    ])
    modal_close_keywords: List[str] = field(default_factory=lambda: [
        "取消", "关闭", "Cancel", "Close", "返回", "Back", "No", "否",
    ])
    nav_roles: List[str] = field(default_factory=lambda: [
        "menuitem", "navigation", "menu", "sidebar",
    ])
    modal_trigger_keywords: List[str] = field(default_factory=lambda: [
        "新增", "添加", "创建", "编辑", "设置", "详情", "配置",
        "导入", "导出", "上传", "批量", "自定义",
        "Add", "Create", "New", "Edit", "Settings", "Details",
        "Import", "Export", "Upload", "Batch", "Custom",
    ])
    search_button_keywords: List[str] = field(default_factory=lambda: [
        "查询", "搜索", "检索", "筛选", "Search", "Query", "Filter", "Go", "Find",
    ])
    form_fill_values: List[str] = field(default_factory=lambda: [
        "test", "admin", "123", "2024-01-01", "测试", "demo",
    ])

    # ═══════════════════════════════════════════════════════════
    # 侧边栏 / 子菜单启发式参数
    # ═══════════════════════════════════════════════════════════
    sidebar_max_x: int = 280            # 侧边栏最大 x 坐标
    submenu_parent_y_sanity: int = 400  # 子项距父项最大 Y 距离
    submenu_xcluster_gap: int = 18      # X 聚类层级间距
    submenu_dedup_y_tolerance: int = 6  # Y 坐标去重容差


@dataclass
class WebExplorationConfig(ExplorationConfig):
    """Web 端探索配置 — 框架无关，ARIA-first。

    核心发现策略: accessibility.snapshot() 无障碍树遍历
    回退策略: 标准 HTML/ARIA 选择器（不含框架专属类名）
    第三回退: getComputedStyle 行为扫描（cursor:pointer）

    默认值为通用语义（跨项目适用）；项目可在 exploration_config.explore 段
    覆盖任意字段定制（apply_overrides）——换项目无需改代码。
    """

    def apply_overrides(self, overrides: dict) -> "WebExplorationConfig":
        """应用项目级覆盖（exploration_config.explore 段的字段 → 同名配置项）。

        反射赋值仅作用于已存在的字段（未知键自动忽略，防拼写错误污染）。
        """
        for _k, _v in (overrides or {}).items():
            if hasattr(self, _k) and _v is not None:
                setattr(self, _k, _v)
        return self

    # ═══════════════════════════════════════════════════════════
    # Accessibility 角色列表（用于无障碍树遍历）
    # ═══════════════════════════════════════════════════════════
    accessible_roles: List[str] = field(default_factory=lambda: [
        "button", "link", "combobox", "listbox", "tab",
        "menuitem", "textbox", "searchbox", "radio", "checkbox",
        "option", "menuitemcheckbox", "menuitemradio",
        "switch", "slider", "spinbutton",
    ])

    # ═══════════════════════════════════════════════════════════
    # CSS 回退选择器 — 只用标准 HTML/ARIA，零 class 依赖
    # ═══════════════════════════════════════════════════════════
    discover_selectors: str = (
        'button, a[href], input:not([type="hidden"]), select, textarea, '
        '[role="button"], [role="link"], [role="combobox"], [role="listbox"], '
        '[role="tab"], [role="textbox"], [role="searchbox"], [role="switch"], '
        '[onclick], [tabindex="0"]'
    )

    # ── 点击目标选择器（_click_by_text JS 回退）──
    click_selectors: str = (
        'button, a[href], '
        '[role="button"], [role="link"], '
        '[onclick], [tabindex="0"]'
    )

    # ── 下拉触发控件 ──
    dropdown_trigger_selectors: str = (
        'select, [role="combobox"], [role="listbox"], '
        '[class*="select"]:not([class*="dropdown"]):not([class*="option"]), '
        '[class*="picker"]:not([class*="date"]):not([class*="time"])'
    )

    # ── 下拉选项选择器（Portal 全局扫描）──
    # 注意：这个选择器会传给 document.querySelectorAll()（JavaScript），
    # 不是 Playwright locator。不能用 jQuery 伪选择器（如 :visible）。
    # Ant Design / Element UI 的下拉选项大多是 <div class="ant-select-item">，
    # 没有 role="option" —— 必须包含 class 选择器才能匹配。
    dropdown_option_selectors: str = (
        '[role="option"]:not([aria-hidden="true"]), '
        '[role="menuitem"]:not([aria-hidden="true"]), '
        '[class*="option"]:not([class*="disabled"]), '
        '[class*="select-item"]:not([class*="disabled"]), '
        '[class*="menu-item"]:not([class*="disabled"]), '
        '[class*="dropdown-item"]:not([class*="disabled"])'
    )

    # ── 表格 ──
    table_selectors: str = 'table, [role="table"], [role="grid"]'

    # ── 表单控件 ──
    form_selectors: str = (
        'input[type="password"]:not([disabled]), '
        'input[type="tel"]:not([disabled]), '
        'input[type="radio"]:not([disabled]), input[type="checkbox"]:not([disabled]), '
        'input[type="date"]:not([disabled]), '
        'input[type="text"]:not([disabled]), input:not([type]):not([disabled]), '
        'textarea:not([disabled])'
    )

    # ── 登录元素识别（LoginAgent 模式：LLM 识别"是什么"→ Playwright 定位，不用 JS 扫描）──
    login_element_inputs: str = 'input, textarea, [role="textbox"], [contenteditable="true"]'
    login_element_buttons: str = 'button, [role="button"]'
    login_username_keywords: str = '帐号,账号,用户名,手机号,手机,手机号码,username,user name,email,邮箱'
    login_password_keywords: str = '密码,口令,password'
    # 登录模块业务流内容校验关键词（导入时判断内容确为登录描述，业务词参数化）
    login_flow_keywords: str = '登录,密码,账号,用户名,手机号,验证码,sign in,login,password,username'
    login_button_keywords: str = '登录,登陆,立即登录,进入系统,sign in,signin,login'
    login_org_confirm_keywords: str = '确定,确认'
    # 机构选择页标识词（业务流文本中判断"是否存在机构选择环节"）
    login_org_marker_keywords: str = '机构,选择机构,身份,多身份'
    # 登录成功标志词（探索/验证阶段判断"已进入系统"的页面元素，业务词参数化）
    login_success_marker: str = '工作台'

    # ── 登录 API 捕获（浏览器网络监听识别登录接口与 token 字段，零硬编码）──
    login_token_keywords: str = 'token,jwt,access,authorization'
    login_api_keywords: str = 'login,登录,auth,认证,鉴权,signin,sign-in,sign_in,oauth,session'

    # ── 登录功能用例步骤模板（业务措辞，不带元素——与 UI 用例的元素定位步骤区分）──
    # JSON: {"动作键": [业务描述, 预期结果]}
    # 动作键: navigate / username_fill / password_fill / login_click / org_select / org_confirm / validate
    login_func_step_templates: str = (
        '{"navigate": ["打开系统并进入到登录页面", "登录页面正常显示"], '
        '"username_fill": ["输入正确的登录账号", "账号输入成功"], '
        '"password_fill": ["输入正确的登录密码", "密码输入成功"], '
        '"login_click": ["点击登录", "系统登录成功，进入工作台"], '
        '"org_select": ["若存在多个身份，选择第一个机构", "机构选择成功"], '
        '"org_confirm": ["若出现机构选择页，选择第一个机构并确认", "进入工作台"], '
        '"validate": ["验证成功进入工作台", "工作台页面正常显示"], '
        '"default": ["执行操作", "执行成功"]}'
    )

    # ── 分页 ──
    pagination_selectors: str = (
        '[class*="pagination"] li, [class*="pagination"] button, '
        '[class*="pager"] li, [class*="pager"] button'
    )

    # ── 导航发现 ──
    nav_selectors: str = (
        '[role="menuitem"], [role="navigation"] a, '
        'nav a[href], aside a[href], li a[href]'
    )
    # 站点地图模块识别排除容器：主内容区内的项是「页面内容/功能入口」（如工作台
    # 页内的功能卡片），不是独立模块——与 mcp_client.get_main_content 同源选择器。
    # 按项目可覆盖（如导航渲染在 main 内的特殊布局置空即可恢复全扫）。
    nav_exclude_containers: str = (
        'main, [role="main"], [class*="content"]:not([class*="sidebar"]):not([class*="sider"]), '
        '[class*="main"]:not([class*="sidebar"]), article'
    )

    # ── 弹窗检测 ──
    modal_selectors: str = (
        '[role="dialog"]:not([style*="display: none"]), '
        'dialog[open]'
    )

    # ── 状态指纹 ──
    fingerprint_selectors: str = (
        '[role="dialog"]:not([style*="display: none"]), '
        '[role="listbox"]:not([style*="display: none"]), '
        '[role="menu"]:not([style*="display: none"])'
    )

    # ── Tab / 表格 / 弹窗关闭 ──
    tab_active: str = '[role="tab"][aria-selected="true"]'
    tab_inactive: str = '[role="tab"]:not([aria-selected="true"])'
    table_action_cell: str = 'td:last-child'
    table_row_selector: str = 'table tbody tr, [role="row"]'
    table_header_selector: str = 'th, thead td'
    modal_close: str = '[role="dialog"] button, dialog button'
    modal_detect_selector: str = '[role="dialog"]:not([style*="display: none"]), dialog[open]'

    # ── 通用 class 回退（仅在 ARIA 缺失时使用，全为通用语义——不绑定框架）──
    # 下拉框/选项选择器（框架无关，覆盖 Ant Design / Element UI / Material UI / Bootstrap / 原生 HTML）
    combobox_fallback: str = (
        'select:not([multiple]), '
        '[role="combobox"], [role="listbox"], '
        '[class*="select"]:not([class*="dropdown"]):not([class*="option"]), '
        '[class*="picker"]:not([class*="date"]):not([class*="time"]), '
        '[class*="dropdown"]:not([class*="menu"]), '
        '[class*="combobox"], [class*="listbox"]'
    )
    option_fallback: str = (
        'option:visible, '
        '[role="option"]:not([aria-hidden="true"]), '
        '[class*="option"]:not([class*="disabled"]), '
        '[class*="select-item"]:not([class*="disabled"]), '
        '[class*="menu-item"]:not([class*="disabled"]), '
        '[class*="dropdown-item"]:not([class*="disabled"]), '
        'li[class*="item"]:not([class*="disabled"])'
    )
    dropdown_arrow: str = (
        '[class*="arrow"], [class*="suffix"], [class*="icon"], '
        '[class*="selector"], [class*="indicator"], [class*="toggle"]'
    )

    # ── 同义词回退：需求描述 ≠ 页面实际文本时的映射 ──
    element_synonyms: Dict[str, List[str]] = field(default_factory=dict)

    # ── 描述词 → UI 呈现形式映射（语言约定，通用）──
    # 用于解析 "点击「室早」卡片" → target="室早" + ui_pattern="card"
    ui_pattern_mapping: Dict[str, str] = field(default_factory=lambda: {
        '卡片': 'card', 'card': 'card',
        '按钮': 'button', 'button': 'button',
        '输入框': 'input', '文本框': 'input', '搜索框': 'input',
        '下拉框': 'dropdown', '下拉列表': 'dropdown', '选择框': 'dropdown',
        '链接': 'link', '连接': 'link',
        '图标': 'icon', 'icon': 'icon',
        '选项卡': 'tab', '标签页': 'tab', '标签': 'tab', 'Tab': 'tab',
        '菜单': 'menu', '菜单项': 'menu',
        '行': 'row', '记录': 'row',
    })

    # ── UI 模式 → class 搜索关键词（用于评分引擎的 UI hints）──
    ui_pattern_keywords: Dict[str, List[str]] = field(default_factory=lambda: {
        'card': ['card', 'panel', 'tile', 'widget'],
        'button': ['btn', 'button'],
        'input': ['input', 'field', 'textbox'],
        'dropdown': ['select', 'dropdown', 'picker', 'combobox'],
        'link': ['link', 'anchor', 'href'],
        'icon': ['icon', 'svg', 'img'],
        'tab': ['tab', 'nav-item', 'nav'],
        'menu': ['menu', 'menuitem', 'nav'],
        'row': ['row', 'tr', 'item', 'record'],
    })


def build_web_exploration_config(project_exploration_config: dict) -> WebExplorationConfig:
    """从项目 exploration_config 构建 WebExplorationConfig。

    项目可在 exploration_config.explore 段预置任意字段覆盖默认值
    （登录词/按钮文案/成功标志等业务词定制——换项目不改代码，零硬编码落地）。
    """
    cfg = WebExplorationConfig()
    cfg.apply_overrides((project_exploration_config or {}).get("explore") or {})
    return cfg
