---
name: webui-test-generation
description: 功能用例→UI自动化用例生成规范——含探索预检、覆盖度判断、强制探索策略、动态数据提取
version: 2.0
---

# UI 用例生成规范 v2.0（探索驱动 + 结构化强约束）

> [MUST] / [MUST NOT] / [CHECK] 标签为硬约束。
> 引擎实现见 `backend/app/core/agents/web_ui_conversion_agent.py`。
> 对应预设 SKILL 模板：`backend/app/core/data/preset_skills/webui_automation_template.json`

---

## 0. 生成前必读

| 文件 | 角色 |
|------|------|
| `../webui-exploration/SKILL.md` | 探索阶段规范（P1-P9），了解探索结果格式 |
| `../webui-exploration/schemas/module.schema.json` | module.md 的 schema |
| `schemas/generation_input.schema.json` | 本阶段的输入契约 |

---

## 1. 探索预检（G0 —— 生成前必须执行）

> 这是最关键阶段。生成 UI 用例前 [MUST] 先完成探索覆盖度检查。

### 1.1 预检流程

```
输入: project_id, case_ids[], force_explore=false
  │
  ├─ 1. 提取模块: 从 cases 中收集所有涉及的模块名
  │
  ├─ 2. 检查探索状态:
  │     for each module:
  │       has_explored = ExplorationService.is_explored(module)
  │
  ├─ 3. 决策: need_explore = force_explore OR NOT has_explored
  │
  ├─ 4. 若 has_explored 且 NOT force_explore:
  │     加载缓存 → check_coverage(缓存, 用例所需元素)
  │     覆盖不足 → need_explore = true
  │
  ├─ 5. 若 need_explore:
  │     [MUST] 自动触发深度探索
  │     [MUST] 等待探索完成 → 验证结果无 error
  │     [MUST] 新结果直接覆盖旧缓存（无论有无冲突）
  │     [MUST NOT] 合并新旧结果、保留旧结果、询问用户 —— 一律覆盖
  │
  └─ 6. 探索结果 + PO 目录 → 拼装为 {module_operations} → 注入 LLM prompt
```

### 1.2 三种触发场景

| 场景 | 条件 | 行为 |
|------|------|------|
| **首次生成** | 模块从未探索过 | 自动触发完整深度探索 → 等待完成 → 用新结果生成 |
| **缓存不足** | 有探索缓存，但用例所需元素不被覆盖 | 自动触发重新探索 → 等待完成 |
| **强制探索** | force_explore=true | 无视缓存 → 重新探索 → 直接覆盖旧结果 |
| **缓存充足** | 有探索缓存，覆盖所有用例元素 | 直接加载缓存 → 注入 LLM → 生成 |

### 1.3 覆盖度检查规则

- [MUST] 从功能用例的 steps[*].action 和 steps[*].desc 中提取目标元素名
- [MUST] 与探索结果 elements[*].name 做匹配（精确 + 子串）
- [MUST] 零容忍：缺任意一个元素 → 覆盖不足 → 触发重新探索

### 1.4 探索结果注入

- [MUST] 探索结果通过 format_exploration_for_llm() 格式化为 Markdown
- [MUST] 包含：页面列表、元素清单（按 role 分组）、弹窗详情、过滤控件及选项、跨模块链接
- [MUST] 与 PO 方法目录合并为 `{module_operations}` 注入 SYSTEM_PROMPT
- [MUST] 探索结果优先于 PO 方法（探索是最新页面状态，PO 可能过时）

---

## 2. 目标系统

- 类型：Web 管理系统（SPA）
- 认证：手机号 + 密码 → 机构选择（可选）→ 工作台
- 多角色：单角色直入工作台；多角色经机构选择页

---

## 3. 技术架构（硬约束）

- [MUST] 技术栈：Python + Playwright 同步模式 + pytest
- [MUST] 设计模式：Page Object Model，三层分离（pages / specs / data）
- [MUST] 支持两种生成模式：
  - **JSON 数据驱动**：输出 JSON 步骤定义 → StepRunner 反射调用执行
  - **Python 代码**：输出 .py spec 文件 → pytest 直接执行
- [MUST NOT] 在 spec 中直接写 locator；必须通过 POM 调用
- [MUST] 登录态由 conftest.py 的 fixture 提供；[MUST NOT] 在用例中写登录步骤
- [MUST] 功能用例前置条件中的角色信息（如"以医生角色登录"）仅用于选择正确的测试账号/fixture。生成UI步骤时 [MUST] 跳过登录操作，直接从"进入XX页面"开始。角色 → 账号的映射由 conftest.py 或环境变量管理，不在用例代码中体现。

---

## 4. 生成输出格式

### 4.1 JSON 数据驱动（推荐）

```json
{
  "case_id": "TC-001-0001",
  "title": "验证患者档案-按姓名搜索",
  "module": "患者档案",
  "steps": [
    {"seq": 1, "action": "goto", "desc": "进入患者档案页"},
    {"seq": 2, "action": "search_by_name", "args": {"name": "$row.name"}, "desc": "按姓名搜索"},
    {"seq": 3, "action": "assert_total_count", "args": {"min": 1}, "desc": "断言有搜索结果", "assert": true}
  ]
}
```

- [MUST] `action` 必须是探索结果或 PO 方法中存在的操作
- [MUST] `args` 参数键值对与 PO 方法签名一致
- [MUST] 下拉选项值必须来自探索结果 filter_options
- [MUST] 断言步骤设置 `"assert": true` 或具体期望值

---

## 5. 动态数据处理（运行时提取，禁止硬编码）

### 5.1 测试数据来源
- [MUST NOT] 硬编码任何测试数据值——姓名、编号、手机号等一律禁止
- [MUST NOT] 假设某个数据一定存在——页面可能被清空、账号可能换环境
- [MUST] 测试数据从页面运行时提取：

```
1. 先从列表/表格中提取存在的真实数据（姓名、编号、ID等）
2. 存入变量：save_as → $变量
3. 若列表为空（暂无数据）→ pytest.skip("无可用测试数据")
4. 后续步骤全部引用 $变量，不使用硬编码值
```

### 5.2 搜索/查询类用例强制模式
```json
[
  {"seq": 1, "action": "goto", "desc": "进入列表页"},
  {"seq": 2, "action": "get_first_row_data", "save_as": "row", "desc": "提取第一行数据"},
  {"seq": 3, "action": "search_by_name", "args": {"name": "$row.name"}, "desc": "用真实数据搜索"},
  {"seq": 4, "action": "assert_total_count", "args": {"min": 1}, "assert": true}
]
```
- [MUST] 至少有一条用例验证"不存在的值搜索"场景

---

## 6. 过滤控件用例生成规则

- [MUST] 对探索结果中每个 type="dropdown" 的过滤控件：生成"全部"选项用例 + 每个非"全部"选项一条独立用例
- [MUST] 对每个 type="search_input" 的搜索框：已知值查询 + 不存在值查询
- [MUST] 重置用例：设置筛选 → 点重置 → 断言恢复默认

---

## 7. 过滤/搜索——数据存在性判断规则（强制）

> 这是最容易出错的环节。过滤或搜索操作前，[MUST] 先判断目标数据在页面中是否存在，
> 再决定后续操作和断言逻辑，避免因数据不存在而导致断言失败或假通过。

### 7.1 数据存在时（过滤命中场景）

```json
[
  {"seq": 1, "action": "goto", "desc": "进入列表页"},
  {"seq": 2, "action": "get_first_row_data", "save_as": "row", "desc": "提取第一行真实数据"},
  {"seq": 3, "action": "check_data_exists", "args": {"value": "$row.name"}, "save_as": "exists", "desc": "判断数据是否存在"},
  {"seq": 4, "action": "skip_if_not_exists", "args": {"condition": "$exists"}, "desc": "数据不存在则跳过本用例"},
  {"seq": 5, "action": "search_by_name", "args": {"name": "$row.name"}, "desc": "用真实数据搜索"},
  {"seq": 6, "action": "assert_total_count", "args": {"min": 1}, "assert": true, "desc": "断言有搜索结果"}
]
```

**规则**：
- [MUST] 过滤前先从列表提取一条真实数据 → `save_as`
- [MUST] 验证该数据在当前页面确实存在（`check_data_exists`）
- [MUST] 若数据不存在 → `pytest.skip("无可用的过滤测试数据")`
- [MUST] 仅数据存在时，执行过滤 → 断言过滤结果 ≥ 1

### 7.2 数据不存在时（过滤未命中场景）

```json
[
  {"seq": 1, "action": "goto", "desc": "进入列表页"},
  {"seq": 2, "action": "search_by_name", "args": {"name": "不存在的值_XYZ_test_999"}, "desc": "输入不可能存在的值"},
  {"seq": 3, "action": "assert_total_count", "args": {"eq": 0}, "assert": true, "desc": "断言结果为0"},
  {"seq": 4, "action": "assert_empty_state", "desc": "断言显示'暂无数据'"}
]
```

**规则**：
- [MUST] 使用一个确定不可能存在的值（如 `不存在的值_XYZ_test_999`）
- [MUST] 断言结果数为 0 或页面显示"暂无数据"
- [MUST] 这是一条独立的负向用例，不与正向用例合在一起

### 7.3 下拉筛选——选项选择规则

```json
[
  {"seq": 1, "action": "goto", "desc": "进入列表页"},
  {"seq": 2, "action": "expand_filter_dropdown", "args": {"name": "科室筛选"}, "desc": "展开科室下拉框"},
  {"seq": 3, "action": "get_dropdown_options", "args": {"name": "科室筛选"}, "save_as": "options", "desc": "获取所有选项"},
  {"seq": 4, "action": "select_dropdown_option", "args": {"name": "科室筛选", "value": "$options[1]"}, "desc": "选择第一个非全部选项"},
  {"seq": 5, "action": "click_search", "desc": "点击查询"},
  {"seq": 6, "action": "assert_total_count", "args": {"min": 0}, "assert": true, "desc": "断言有筛选结果"}
]
```

**规则**：
- [MUST] 下拉选项值必须从探索结果的 `filter_options.{下拉名}.options` 数组中取
- [MUST NOT] 凭空编造选项值（如探索结果中没有"心内科"就不能写"心内科"）
- [MUST] 选择后点击查询 → 断言结果更新
- [MUST] 对每个非"全部"选项生成一条独立用例

---

## 8. 动态列表操作（foreach 循环）规则

> 当用例描述"取消所有选项""移除全部指标""遍历列表操作"等场景时，
> 选项数量在设计时是未知的——必须在运行时动态获取，使用 `foreach` 循环处理。

### 8.1 适用场景

| 用例描述 | 动态操作 | 原因 |
|---------|---------|------|
| "取消所有已选指标" | foreach 遍历已选列表 | 不知道当前勾选了几个 |
| "移除全部自定义卡片" | foreach 遍历可见卡片 | 卡片数量随配置变化 |
| "关闭所有弹窗提示" | foreach 遍历弹窗列表 | 弹窗数量不固定 |
| "批量删除筛选结果" | foreach 遍历查询结果 | 筛选结果数量动态变化 |

### 8.2 foreach 模式（强制 JSON 格式）

```json
{
  "seq": 4,
  "action": "foreach",
  "args": {
    "items": "$selected_indicators",
    "as": "indicator",
    "do": [
      {"action": "click_remove_button", "args": {"name": "$indicator.name"}, "desc": "点击移除按钮"},
      {"action": "confirm_dialog", "desc": "确认移除"}
    ]
  },
  "desc": "遍历并移除所有已选指标"
}
```

**规则**：
- [MUST] `items` 必须是前面步骤通过 `save_as` 保存的**列表变量**（如 `$selected_indicators`）
- [MUST] `as` 定义迭代变量名（如 `indicator`），子步骤中用 `$indicator.xxx` 引用
- [MUST] `do` 是子步骤数组，每步结构与普通步骤相同（action + args + desc）
- [MUST] foreach 循环中**不使用** `save_as` 和 `assert`（这两个在外层步骤中使用）
- [MUST] 循环结束后 [MUST] 有断言验证操作结果（如列表为空）

### 8.3 完整示例：取消所有已选指标

```json
{
  "case_id": "TC-001-0008",
  "title": "自定义指标-取消所有已选指标",
  "module": "工作台",
  "steps": [
    {"seq": 1, "action": "goto", "desc": "进入工作台页面"},
    {"seq": 2, "action": "open_custom_metric_dialog", "desc": "打开自定义指标弹窗"},
    {"seq": 3, "action": "get_selected_indicators", "save_as": "selected", "desc": "获取当前已选指标列表"},
    {"seq": 4, "action": "skip_if_empty", "args": {"list": "$selected"}, "desc": "若无已选指标则跳过"},
    {
      "seq": 5,
      "action": "foreach",
      "args": {
        "items": "$selected",
        "as": "item",
        "do": [
          {"action": "click_indicator_toggle", "args": {"name": "$item.name"}, "desc": "取消勾选指标"}
        ]
      },
      "desc": "遍历取消所有已选指标"
    },
    {"seq": 6, "action": "click_save", "desc": "点击保存"},
    {"seq": 7, "action": "assert_no_indicators_selected", "assert": true, "desc": "断言所有指标已取消"}
  ]
}
```

**规则**：
- [MUST] 动态列表操作前 [MUST] 先 `save_as` 保存列表 → 判断是否为空 → 再 foreach
- [MUST] foreach 后 [MUST] 有验证步骤（断言操作结果正确）
- [MUST NOT] 用固定次数的循环替代 foreach（如 `for i in range(10)`）——列表长度在设计时不可知

### 8.4 需要滚动加载的列表场景

```
当页面/弹窗中列表项需要滚动才能全部加载时：

1. 先滚动到底部，触发懒加载
2. 等待新数据渲染完成
3. 重新获取完整列表
4. 再执行 foreach
```

```json
[
  {"seq": 3, "action": "scroll_to_bottom", "args": {"container": ".list-container"}, "desc": "滚动到底部触发加载"},
  {"seq": 4, "action": "wait_for_render", "desc": "等待新数据渲染"},
  {"seq": 5, "action": "get_all_items", "save_as": "all_items", "desc": "重新获取完整列表"},
  {"seq": 6, "action": "skip_if_empty", "args": {"list": "$all_items"} },
  {
    "seq": 7, "action": "foreach",
    "args": {"items": "$all_items", "as": "item", "do": [...]},
    "desc": "遍历所有列表项"
  }
]
```

**规则**：
- [MUST] 若探索结果标记了列表需要滚动加载（`scroll_to_load: true`），生成时 [MUST] 加 `scroll_to_bottom` 步骤
- [MUST] 滚动后 [MUST] 重新获取列表，不能使用滚动前的旧列表

---

## 9. 反模式

| ID | 反模式 | 级别 |
|----|--------|------|
| GEN001 | time.sleep / wait_for_timeout | block |
| GEN002 | CSS/XPath 选择器 | block |
| GEN003 | spec 中写登录步骤 | block |
| GEN004 | 无 expect() | block |
| GEN005 | 硬编码数据预期值 | warn |
| GEN006 | 凭空编造不存在的元素名/选项值 | block |
| GEN007 | 下拉选项值不在 filter_options 中 | block |
| GEN008 | 生成前未完成探索预检 | block |
| GEN009 | 探索结果有 error 仍继续生成 | block |
| GEN010 | 过滤前不判断数据是否存在，直接设定期望值 | block |
| GEN011 | 过滤"不存在的值"场景与正向场景合并为一条用例 | block |
| GEN012 | 用固定次数 for 循环替代 foreach 处理动态列表 | block |
| GEN013 | foreach 循环内使用 save_as 或 assert | block |
| GEN014 | 滚动加载列表不重新获取数据，直接用旧列表 | block |
| GEN015 | foreach 结束后无断言验证操作结果 | block |

---

## 10. 退出门

[MUST] 全部完成后输出：
```
GENERATION_DONE  specs=<N>  explored_modules=<M>  force_explore=<true|false>
```

---

> **维护规则**: 每次修改 `web_ui_conversion_agent.py` 的生成逻辑或 `webui_automation_template.json` 的 prompt，必须同步更新本文档。
> 最后更新: 2026-07-25
