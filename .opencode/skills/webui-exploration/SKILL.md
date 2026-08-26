---
name: webui-exploration
description: 探索阶段专用SKILL——模块级深度递归探索的行业通用标准规范
version: 3.0
---

# Web UI 深度探索规范 v3.0

> [MUST] / [MUST NOT] 标签为硬约束。
> 引擎实现见 `backend/app/core/services/bfs_explorer.py`。

## 0. 核心理念

**按模块 BFS 递归，穷尽所有交互路径。** 一次探索一个模块，从入口 URL 开始，覆盖该模块内所有页面、Tab、弹窗、过滤控件、表格分页、日期选择器，直到该模块的每一个可交互元素都被操作并记录。跨模块链接只记录不递归。

## 1. 探索生命周期

每个模块的探索必须覆盖以下全部阶段：

| # | 阶段 | 必须产出 | 说明 |
|---|------|---------|------|
| P0 | 页面预处理 | 完整 DOM | 滚动到底触发懒加载 → 回到顶部 |
| P1 | 登录与鉴权 | 已登录 page | 处理机构选择页，提取鉴权参数 |
| P2 | 入口导航 | 模块主页 page | 带鉴权参数跳转到模块入口 URL |
| P3 | 被动发现 | elements[] | 提取按钮/链接/Tab/输入框/下拉框/卡片/表格，按 role+name 语义化 |
| P4 | Tab 状态探索 | 每 Tab 的 elements[] | 逐个点击 Tab → 内容区重新 P3 → 子 Tab 递归 |
| P5 | 弹窗探索 | modals[] | 点击弹窗触发器 → P3 扫描弹窗内元素 → 关闭弹窗 |
| P6 | 过滤控件探索 | filter_options{} | 展开每个下拉 → 点击**每一个**选项 → 记录变化 → 恢复 |
| P7 | 日期控件探索 | date_pickers[] | 点击打开 → 切换上下月 → 选日期 → 记录 |
| P8 | 表格探索 | tables[] | 滚动表格 → 点击**每一个**分页 → 点击**每一个**操作按钮 → 记录跳转 |
| P9 | 主动导航探测 | 子页面 URL 列表 | 点击卡片/链接/操作按钮，区分新窗口/SPA导航/弹窗 |
| P10 | 递归 | 子页面探索 | P9 发现的模块内 URL 入队，回到 P2 |
| P11 | 组装输出 | module.md + .json | 含 frontmatter schema + 完整探索结果 |

---

## 2. 页面预处理 (P0)

- [MUST] 每进入一个新页面，先 `window.scrollTo(0, document.body.scrollHeight)` 滚动到底
- [MUST] 等待 0.5s 后 `window.scrollTo(0, 0)` 回到顶部，确保懒加载内容已渲染
- [MUST] 滚动过程中监控新增 DOM 元素，若有则继续滚动直到无新元素

---

## 3. 被动发现 (P3)

### 3.1 元素提取规则
[MUST] 扫描当前页面，提取以下类型：
1. **按钮** — `button`, `[role="button"]`, `a.btn`, `div[onclick]`
2. **链接** — `a[href]`, `span.link`, `span[class*="link"]`
3. **Tab** — `.ant-tabs-tab`, `[role="tab"]`, `.el-tabs__item`, `.nav-tabs > li`
4. **输入框** — `input[type="text"]`, `input[type="password"]`, `textarea`, `input:not([type])`
5. **下拉框** — `.ant-select`, `[role="combobox"]`, `select:not([multiple])`
6. **日期选择器** — `.ant-picker`, `input[type="date"]`, `.el-date-editor`
7. **搜索框** — `input[placeholder*="搜索"]`, `input[placeholder*="Search"]`
8. **卡片** — `.ant-card`, `[class*="card"]`, `[class*="Card"]`
9. **表格** — `table`, `.ant-table`, `.el-table`

### 3.2 语义化命名
[MUST] 元素用 `role + name` 描述，禁止 CSS/XPath：
- ✅ `{"role": "button", "name": "新增患者"}`
- ❌ `{"selector": ".ant-btn-primary > span"}`

### 3.3 安全跳过
[MUST] 以下危险操作静态跳过，不点击：
- 退出登录、注销账号、删除操作（含确认弹窗中确认按钮）
- 修改密码、重置数据
- 关键词：退出、注销、删除、移除、清空、重置密码、登出、sign out、log out、delete、remove

---

## 4. Tab 状态探索 (P4)

- [MUST] 逐个点击每个 Tab，等待内容渲染
- [MUST] 每个 Tab 内重新执行 P0+P3
- [MUST] 若 Tab 内有子 Tab，递归执行 P4（最大深度 3）
- [MUST] 子 Tab 探索涉及弹窗/过滤控件时，调用 P5/P6

---

## 5. 弹窗探索 (P5)

- [MUST] 识别弹窗触发元素（含关键词：新增、添加、详情、编辑、导入、导出、设置、配置、上传、批量、新建、自定义）
- [MUST] 点击触发 → 等待弹窗出现
- [MUST] 在弹窗内执行 P0+P3
- [MUST] 弹窗内表单：记录所有字段名和类型
- [MUST] 弹窗内按钮：记录所有按钮文本
- [MUST] 关闭弹窗（点取消/关闭/×按钮，或按 Escape）
- [MUST NOT] 在弹窗内点"确认"/"保存"/"提交"——避免副作用

---

## 6. 过滤控件探索 (P6)

- [MUST] 展开每个下拉框
- [MUST] **记录所有选项**
- [MUST] **逐个点击每一个选项**（非仅"试选一个"）
- [MUST] 每次点击后记录页面变化（URL 参数、表格刷新、筛选标签等）
- [MUST] 点击后恢复默认选项（或点"全部"/"All"）
- [MUST] 对搜索框：记录 placeholder，试填一个值，记录自动补全建议

---

## 7. 日期控件探索 (P7)

- [MUST] 点击日期选择器打开日期面板
- [MUST] 记录面板内所有可操作元素（上月/下月按钮、年份切换、日期单元格）
- [MUST] 切换上一个月 → 记录 → 切换下一个月 → 记录
- [MUST] 选择一个日期 → 记录输入框回填的值
- [MUST] 如有快捷选项（今天/昨天/本周/本月）→ 点击每一个并记录

---

## 8. 表格探索 (P8)

- [MUST] 对每个 `<table>` / `.ant-table` / `.el-table`：
- [MUST] 横向滚动表格查看所有列
- [MUST] 纵向滚动表格查看所有行
- [MUST] **点击每一个分页按钮**（第1页、第2页...下一页），每次记录表格数据变化
- [MUST] **点击表格操作栏的每一个操作按钮**（详情、编辑、删除、查看等）
- [MUST] 操作按钮点击后检测：弹窗 → P5 / 新页面 → 记录 URL / SPA 跳转 → 记录 URL 并返回
- [MUST] 删除类操作：点击 → 捕获确认弹窗 → 点取消 → 记录元素
- [MUST] 记录每列的表头名称和排序按钮

---

## 9. 主动导航探测 (P9)

- [MUST] 对 P3 发现的所有卡片 + 所有表格操作列 + 所有链接，全部点击探测
- [MUST] 去重（同名元素只点一次）+ 排除危险操作
- [MUST] 点击后检测三种结果：
  - **新窗口/标签页**：切换到新页 → P0+P3 → 记录元素 → 关闭 → 回到原页
  - **SPA 导航**：URL 变化 → 记录新 URL → `goto` 回到原页（非 `go_back`）
  - **弹窗**：按 P5 处理
- [MUST] 每次回到原页后重新 P0 确保 DOM 完整恢复

---

## 10. 递归 (P10)

- [MUST] P9 发现的模块内子页面 URL 入队，回到 P2 继续
- [MUST] URL 归一化（去 query 参数差异）+ 指纹去重（body 哈希 + 元素计数）
- [MUST] 模块边界：URL 前缀匹配，跨模块链接仅记录不递归
- [MUST] 设置 max_pages 上限（默认 200）

---

## 11. 组装输出 (P11)

### 11.1 module.md（供人阅读）
```markdown
---
module: 患者档案
url: /#/patientarchieve
explored_at: 2026-07-25T10:00:00
elements_count: 45
pages_count: 12
---

# 患者档案

## 页面列表
1. 患者列表页
2. 患者详情页...

## 元素清单
### 按钮
- `新增患者` — 打开新增弹窗
### 链接
- `患者详情` → /#/detail

## 过滤控件
### 科室筛选: [全部, 心内科, 神经内科...]

## 表格
### 患者列表
- 分页: 共5页
- 操作列: [详情, 编辑, 删除]
```

### 11.2 module.json（供程序解析）
完整 JSON 结构包含所有探索结果。

---

## 12. 配置项（ExplorationConfig）

系统切换时修改以下配置（零代码）：

| 配置组 | 可配置项 |
|--------|---------|
| 模块路由 | module_routes, module_en_map, module_url_boundaries |
| 认证登录 | LoginConfig（见 login_engine.py） |
| UI框架 | tab/modal/dropdown/date_picker/search/card/table selectors |
| 关键词 | danger_keywords, modal_trigger_keywords |
| 时延限制 | max_pages, render_wait, probe_wait, tab_wait, modal_wait |

---

> **维护规则**: 每次修改 `bfs_explorer.py` 的探索逻辑，必须同步更新本文档。
> 最后更新: 2026-07-26
