# 探索引擎设计方案 V6

## 概述

探索引擎是 AI 智能测试平台的**预执行模块**——在生成测试用例之前，自动浏览目标 Web 应用，发现所有可交互元素、页面状态和业务流程，产出结构化数据供后续测试用例生成使用。

本质上是一次**不加断言的测试执行**：模拟用户操作路径，记录每个动作的触发条件和结果。

---

## 一、设计依据

V6 版本基于以下 6 个行业标准工具的系统性调研：

| 工具 | 来源 | 借鉴的设计 |
|------|------|-----------|
| **Playwright codegen** | Microsoft | role→text→test-id 定位器优先级策略 |
| **VETL** | IEEE 2024 顶会 | 表单语义化输入生成、好奇心驱动探索 |
| **ouroboros-tester** | 开源 | crawl→verify→architect→write 四阶段管道 |
| **Scry** | 开源 (MIT) | 9 种标准 Action Vocabulary、最多 20 次自愈修复 |
| **WALT** | Salesforce ICLR 2026 | search/filter/sort 抽象为可复用工具 |
| **Cypress / axe-core / Verdex** | 业界标准 | `.within()` scope 限定、`<main>` 内容区 |

---

## 二、核心架构

```
┌─────────────────────────────────────────────────────┐
│                   API 调度层 (business_flow.py)       │
│  模块发现 → 子菜单收集 → 逐个模块调度 → 结果汇总      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                MCPExplorationAgent                    │
│                                                      │
│  explore()                                           │
│    ├─ Phase 0: 登录态复用 + 弹窗拦截注册              │
│    ├─ _explore_page(url, depth)   ← DFS 递归入口     │
│    │   ├─ Scope 获取 (get_main_content)               │
│    │   ├─ Phase 1: 元素发现                           │
│    │   │   ├─ 无障碍树遍历 (accessibility.snapshot)   │
│    │   │   ├─ CSS 回退扫描 (_js_find)                 │
│    │   │   ├─ 表格行补充 (Playwright row locator)     │
│    │   │   └─ 去重 + 优先级排序 + nav 过滤            │
│    │   ├─ Phase 2: 交互执行                           │
│    │   │   ├─ Step A: 表单交互 (填→选→搜→重扫)        │
│    │   │   ├─ Step B: 卡片/按钮点击 (三阶段自愈)       │
│    │   │   ├─ 表格行迭代 (DANGER_KW 安全过滤)         │
│    │   │   └─ Tab 逐页探索                            │
│    │   ├─ Phase 3: 深度探索                           │
│    │   │   ├─ 下拉选项扫描 (_p3_dropdowns)            │
│    │   │   ├─ 弹窗扫描+交互 (_p3_modals)              │
│    │   │   ├─ 表格结构提取 (_p3_tables)               │
│    │   │   ├─ 分页遍历 (_p3_pagination)               │
│    │   │   ├─ 表单结构提取 (_p3_forms)                │
│    │   │   └─ API 端点发现 (_p3_api_endpoints)        │
│    │   └─ State Graph 节点记录                        │
│    └─ Phase 4: LLM 综合生成                           │
│        ├─ 模块文档 (Markdown)                         │
│        ├─ 站点地图 (Markdown)                         │
│        └─ Page Object 代码 (Python)                   │
│                                                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  MCPClient (浏览器封装层)              │
│  goto / get_url / get_main_content /                 │
│  get_accessibility_tree / get_fingerprint /          │
│  wait_for_page_ready / inject_console_hook /         │
│  press_escape / scroll_to_load / scan_iframes        │
└─────────────────────────────────────────────────────┘
```

---

## 三、核心设计决策

### 3.1 Scope 限定（Cypress .within() 模式）

**问题**：全页扫描会引入侧边栏导航元素，导致点击后跳转到其他模块。

**方案**：元素发现从 `<main>` / `[role="main"]` 开始，而非 `document.body`。天然排除 `<nav>`、`<aside>`、侧边栏。

```
get_main_content()
  → 优先: <main>, [role="main"]
  → 回退: [class*="content"], [class*="main"], <article>
  → 兜底: None → document.body
```

`get_accessibility_tree(root=scope_el)` 和 `_js_find(scope_element=scope_el)` 均从 scope 开始扫描。

### 3.2 Plan 规划步骤（WALT/Scry 模式）

**问题**：Phase 2 边发现边点击，无整体规划。

**方案**：Phase 2 拆分为两步：

```
Step A: 表单交互（先执行）
  → 填所有 input/textbox/searchbox（role locator → placeholder → label）
  → 选所有 combobox/listbox（打开下拉 → 选第一个选项）
  → 找搜索按钮（匹配 search_button_keywords）
  → 点击 → 等待结果 → 刷新 scope → 重新扫描 → 合并新元素

Step B: 卡片/按钮点击（后执行）
  → 过滤掉 table-row（避免与专用表格行扫描重复）
  → 逐个点击 + 指纹检测 + 边界检查
  → 三阶段自愈点击：role locator → 文本匹配 → JS TreeWalker
```

### 3.3 交互优先级

```
input/searchbox/textbox : 0   ← 最先（搜索条件先于数据）
combobox/listbox        : 1
card                    : 2
button/link/tab         : 3
table-row               : 5   ← 最后（表格行迭代有专门的扫描逻辑）
```

### 3.4 Action Vocabulary（Scry 9 种标准动作）

```python
class ActionType(Enum):
    CLICK = "click"
    NAVIGATE = "navigate"
    FILL = "fill"          # 文本输入
    SELECT = "select"      # 下拉选择
    HOVER = "hover"
    RIGHT_CLICK = "right_click"
    KEY_PRESS = "key_press"
    WAIT_FOR = "wait_for"
    VALIDATE = "validate"
    TABLE_ROW = "table_row"
    TAB_SWITCH = "tab_switch"
```

### 3.5 三阶段自愈点击

```
1. role locator (page.get_by_role(role, name=name))
2. 文本匹配 (_click_by_text)
3. JS TreeWalker 精确查找 + 点击
```

### 3.6 边界安全（多层防护）

```
Layer 1: _explore_page 入口 → _is_within_module(url) 检查
Layer 2: Phase 2 跳转后 → _is_within_module(after_url) 检查
Layer 3: _return_to_page 四层回退:
  go_back → goto → URL验证 → force goto
Layer 4: nav 项永不点击（侧边栏由 API 调度层管理）
```

### 3.7 危险操作防护

- `DANGER_KW = ['退出', '注销', '删除', '清空', '重置密码']`
- Phase 1 发现过滤（`_js_find`、`_walk_a11y_tree`）
- Phase 2 表格行点击前检查 `cell_text`
- Phase 2 Tab 表格行点击前检查 `cell_text`
- 弹窗交互 (`_interact_modal`) 跳过危险按钮

### 3.8 子菜单通用发现算法（X 坐标聚类）

**问题**：不同 UI 框架（AntD/Element/Bootstrap）的 DOM 嵌套层级不一致，无法用 CSS 选择器或 DOM 深度可靠识别子菜单。

**方案**：纯视觉位置算法。

```
Step 1: TreeWalker 扫描全页叶子节点
  → 只取 x < 350px（侧边栏区域）
  → 过滤容器元素（子元素 textContent 拼接 = 自身 textContent）

Step 2: X 坐标聚类
  → 收集所有唯一的 X 值
  → gap > 18px = 新缩进层级
  → 每个 item 获得 indent 层级

Step 3: 子菜单收集
  → 找到 parent（text 精确匹配）
  → 收集 indent == parent_indent + 1 的后续项
  → 直到 indent <= parent_indent（下一个同级菜单）
```

**不依赖**：CSS class 名、`<a>` 标签、DOM 容器结构、框架类型。

### 3.9 DFS 递归探索

- 入口页 (depth=0)：记录 site_map、设置 nav_names
- 子页面 (depth>0)：递归调用 `_explore_page`，`max_depth=2`
- URL 去重：`_visited_urls` set
- 边界检查：`_is_within_module(url)` 精确路径前缀匹配

---

## 四、API 调度层设计

### 4.1 模块发现与调度

```
POST /business-flow/explore-workbench/{version_id}
  → 登录（LoginEngine）
  → 导出 storage_state
  → sync 浏览器加载登录态
  → 点击目标模块名
    ├─ URL 变了 → 单模块探索
    └─ URL 没变 → 父菜单
        → _collect_sub_menus (X坐标聚类)
        → 逐个子菜单: goto → MCPExplorationAgent → explore
        → 汇总: stats + explored + element_jumps + deep_dive + state_graph
```

### 4.2 结果汇总

多子模块的结果自动合并：
- stats：求和
- explored：扁平化，名加 `[模块名]` 前缀
- element_jumps：按模块名 key
- deep_dive：dropdowns 合并 / modals/tables/pagination/forms/api 拼接
- state_graph：加 `_module` 标注来源
- LLM 文档：按模块分节拼接

---

## 五、数据流

```
输入: module_name, base_url, username, password
  ↓
LoginEngine → storage_state
  ↓
Playwright sync browser
  ↓
子菜单收集 (如果需要)
  ↓
MCPExplorationAgent.explore()
  ├─ site_map: [{name, href, source}]
  ├─ element_jumps: {_main: {url, elements: [...]}}
  ├─ deep_dive: {dropdowns, modals, tables, pagination, forms, api_endpoints}
  ├─ stats: {total_elements, navigated_elements, pages_explored, elapsed_seconds, errors}
  ├─ pages_visited: [url, ...]
  ├─ error_events: [{stage, error, url}]
  ├─ state_graph: [{url, fingerprint, actions, children, deep_dive}]
  └─ Phase 4: module_docs (md), site_map_md (md), page_object_code (py)
  ↓
文件输出:
  tests/exploration/{module}-jump-summary.json
  tests/exploration/{module}-click-log.json
  tests/exploration/states/{module}/*.json
  tests/exploration/explore_full_{timestamp}.json
  tests/exploration/module_docs.md
  tests/exploration/site_map_md.md
  tests/exploration/page_object_code.py
```

---

## 六、配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `page_ready_timeout` | 12.0s | 首次页面加载等待 |
| `page_ready_timeout_fast` | 8.0s | 返回页面/子页面等待 |
| `max_depth` | 2 | DFS 最大深度 |
| `max_clicks` | 200 | 单页面最大点击数 |
| `max_dropdowns` | 20 | 单页面最大下拉数 |
| `max_tabs` | 15 | 单页面最大 Tab 数 |
| `max_form_fields` | 10 | 单页面最多表单字段数 |
| `form_fill_values` | ["test","测试","admin","123","2024-01-01"] | 表单测试数据 |
| `search_button_keywords` | ["查询","搜索","search","query","检索","筛选","filter","go","确定"] | 搜索按钮识别词 |
| `sidebar_max_width` | 280px | 侧边栏位置启发式 |
| `click_wait` | 0.8s | 点击后等待 |
| `dropdown_wait` | 1.0s | 下拉展开后等待 |

---

## 七、待验证（2026-08-06）

1. 子菜单收集：X 坐标聚类算法准确性
2. 表单交互：填值 + 选下拉 + 搜按钮点击
3. 搜索后重扫：scope 刷新 + 新元素发现
4. 弹窗交互：填表 + 跳过危险按钮 + 自动关闭
5. 危险操作：表格行/弹窗按钮的 DANGER_KW 过滤
6. 换模块测试：不同父菜单的子菜单收集通用性

---

## 八、参考

- [ActionEngine: From Reactive to Programmatic GUI Agents via State Machine Memory](https://ar5iv.labs.arxiv.org/html/2602.20502)
- [Agent-E: From Autonomous Web Navigation to Foundational Design Principles](https://arxiv.org/abs/2407.13032)
- [WALT: Web Agents that Learn Tools](https://arxiv.org/abs/2510.01524)
- [Scry: Agentic web scraper with LLM-driven exploration](https://github.com/mayflower/scry)
- [Cypress .within() command](https://docs.cypress.io/api/commands/within)
- [axe-core context argument](https://github.com/dequelabs/axe-core/blob/develop/doc/context.md)
