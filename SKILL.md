---
name: webui-test-generation
description: 读取MCP探索产出的结构化数据，独立生成标准化可复用自动化工程、测试用例、报告脚本;应读取skill_explore.md探索完成的site_explore_result.json数据
---

# 测试用例生成规范（Python + pytest-playwright）（结构化强约束版）

> 🛡️ **本目录受 `.opencode/plugins/webui-skill-guard.mjs` 保护**
> 你每次 write/edit `tests/specs/**` / `tests/pages/**` / `tests/conftest.py` 之后，
> `lint_generated.py` 会自动运行；看到 `🚨 VALIDATOR FAILED` 必须先修复，
> 禁止以任何方式宣告"完成"。session 空闲时还会兜底全量扫一遍。
>
> ⚠️ 本 SKILL 全部规则使用 `[MUST]` / `[MUST NOT]` / `[CHECK]` 标签。
> 「建议/优先/尽量」语气一律视为 `[MUST]`。

## 0. 必读的随附文件

| 文件 | 角色 |
|---|---|
| `schemas/generation_input.schema.json` | 进入本阶段的硬前置契约 |
| `workflow.yaml` | 8 个 state 的严格顺序，禁止跳步 |
| `anti_patterns.json` | 代码生成红线（block / warn） |
| `checklists/delivery_checklist.md` | 退出门 |
| `validators/lint_generated.py` | 实际可跑的扫描器，退出码必须为 0 |

## 1. 目标系统

- URL：`https://hospitalweb.tt.xinjikang.cn:8443`
- 类型：医院 Web 管理系统

## 2. 启动前置（G1_precheck）

[MUST] 在做任何代码生成之前：

1. 读取 `tests/exploration/site-map.md`，把 frontmatter 解析为 JSON
2. 校验上游 `EXPLORATION_DONE` 标识已出现
3. 校验 `tests/auth/*.json` 与 `site-map.roles[*].storage_state` 一一对应
4. 拼装一份"generation_input"对象（结构见 schema），通过 `schemas/generation_input.schema.json` 校验
5. 在对话中输出校验摘要，未通过 → [MUST NOT] 继续

## 3. 技术架构（硬约束）

- [MUST] 技术栈：Python + Playwright 同步模式 + pytest
- [MUST] 设计模式：Page Object Model，三层分离（pages / specs / data）
- [MUST] 浏览器：Chromium
- [MUST NOT] 在 spec 中直接写 locator；必须通过 POM 调用

## 4. 工程目录（必须严格一致）

```
项目根/
├── tests/
│   ├── conftest.py
│   ├── specs/test_{module}_{level}.py
│   ├── pages/{module}_page.py
│   ├── data/*.yaml | *.json
│   ├── auth/{role}.json
│   └── exploration/   # 上游产物，本阶段只读
├── playwright-report/
├── pytest.ini
├── run.bat / run.sh
└── report.bat
```

## 5. POM 生成规则

[MUST] 从 `tests/exploration/{module}.module.md` 的 frontmatter 读取 `pages` + `elements` + `flows`：

- `pages[*].url` → POM 的 `goto()`
- `elements[*]` → POM 内 locator 属性，[MUST] 使用 `get_by_role / get_by_test_id / get_by_label / get_by_text`
- `flows[*]` → POM 的业务方法（例如 `add_patient(...)`）

[MUST NOT] 在 POM 中出现：
- `time.sleep(...)` / `page.wait_for_timeout(...)`
- `.ant-xxx` / `#root > div > ...` 等 CSS 路径
- 按位置索引的 xpath（如 `[1]`、`[2]`）

[兜底例外]：若元素确实无任何语义属性，[MUST] 采用以下方式且在代码注释中显式说明：
```python
# anchor by visible text (no role/name/test_id available)
card = page.get_by_text("患者人数", exact=True).locator(
    "xpath=ancestor::*[self::div or self::li][1]"
)
```

## 6. 测试用例规则

- [MUST] 单一业务功能 → 单条 test 用例，不耦合
- [MUST] 每个 `test_*` 函数体至少 1 次 `expect(...)` 断言
- 断言可选维度（[MUST] 至少命中其一）：
  1. URL 匹配：`expect(page).to_have_url(...)`
  2. 元素可见性：`expect(locator).to_be_visible()`
  3. 标题/文本：`expect(locator).to_contain_text(...)`
  4. 操作后状态反馈
- [MUST] 登录态由 `conftest.py` 的 `auth_context(role)` fixture 提供
- [MUST NOT] 在 spec 中写 `fill(...password...)` 或登录步骤
- [MUST] 使用 `pytest.mark.smoke` / `pytest.mark.regression` 标记层级

## 7. 等待策略

- [MUST NOT] `time.sleep` / `page.wait_for_timeout`
- [MUST] 使用条件等待：
  - `expect(locator).to_be_visible(timeout=5000)`
  - `page.wait_for_url(re.compile(r"/patient"), timeout=8000)`
  - `page.wait_for_function(...)` 监测 DOM 文本变化
- 极端例外（<100ms 动画过渡且无可观测锚点）：[MUST] 在该行旁加注释 `# rationale: ...`

## 8. Allure 报告

- [MUST] 自动生成环境配置文件，含：项目名 / 系统版本 / 浏览器类型 / 生成时间
- [MUST] 统计维度：用例总数 / 成功 / 失败 / 总耗时
- [MUST] 失败自动截图，挂在 Allure attachment

## 9. 执行脚本

- [MUST] `run.bat`：清空旧报告 → 跑 pytest → 生成 Allure 结果
- [MUST] `report.bat`：本地启动 `allure serve`
- [MUST] `run.sh`：CI 用，相同语义

## 10. 拓展能力（按需）

- 消息推送：飞书 / 企业微信 / 钉钉 webhook 占位
- 定时任务调用入口
- 版本目录隔离：`projects/{name}/{version}/`

## 11. 反模式速查（详见 `anti_patterns.json`）

### 通用代码红线（GEN）

| ID | 反模式 | 级别 |
|---|---|---|
| GEN001 | time.sleep / wait_for_timeout | block |
| GEN002 | .ant- / #root> 选择器 | block |
| GEN003 | 位置索引 xpath | warn |
| GEN004 | 测试函数无 expect( | block |
| GEN005 | spec 中写登录 | block |
| GEN006 | 工作台用 goto 而非 go_back | block |
| GEN007 | spec 未 import tests.pages | block |
| GEN008 | localhost / 127.0.0.1 | warn |

### 业务级硬约束（BIZ，全部 block）

| ID | 触发条件（文件 + 函数名） | 必须命中 |
|---|---|---|
| BIZ001 | `*workbench*.py` + fn 含 `afib/房颤` | 必含 4 字段：患者姓名/负荷占比/有效时长/持续时间 |
| BIZ002 | `*workbench*.py` + fn 含 `remove/移除` | 必含 `移除` + `for ` 循环；禁止用『重置』按钮 click |
| BIZ003 | `*workbench*.py` + fn 含 `add/添加指标` | 必含 `len(` + `expect(`（断言恰好 N 个） |
| BIZ004 | `*workbench*.py` + fn 含 `disease/疾病` | 必含 `筛选` + `expect(` |
| BIZ005 | `*workbench*.py` + fn 含 `card/click/跳转` | 必含 `go_back` |
| BIZ006 | `*workbench*.py` 文件级 | 至少 1 次 `pytest.skip(` |
| BIZ007 | `*workbench*.py` + fn 含 `joinstatus/入组` | 必含字符串 `joinStatus=1` |
| BIZ008 | `*patient_archive*.py` 文件级 | 必须存在 5 个核心 add_patient 函数 |
| BIZ009 | `*patient_archive*.py` + fn 含 `add_patient_success` | 必含 `今日新增` + `+ 1` |
| BIZ010 | `*patient_archive*.py` + fn 名以 `test_search_` 开头 | 必含 `btn_query` + `expect(` |
| BIZ011 | `*patient_archive*.py` + fn 含 `reset` | 必含 `expect(`（验证清空） |

## 12. 退出门

[MUST] 全部产物完成后，跑：
```
python .opencode/skills/webui-test-generation/validators/lint_generated.py tests/
```
退出码必须为 0；然后逐项核对 `checklists/delivery_checklist.md`，全部 ✅ 后在对话中输出：
```
GENERATION_DONE  pages=<N>  specs=<M>  smoke_passed=<K>
```

---

# 业务模块知识库（生成测试时必须遵守）

> 以下内容为领域知识，是生成用例的"原料"。每条规则前的 `[MUST]` 同样为硬约束。

## 📊 工作台模块

### 页面区域划分
工作台分为两大独立区域，[MUST] 分开生成测试用例：
1. **上半区：指标总览** → 可配置的指标卡片（患者概览 / 疾病统计 / 审核任务 / 物流看板 / 随访监控）
2. **下半区：预警信息** → 动态数据卡片（房颤预警 / 佩戴预警 / 测量预警）

### 指标总览 - 正常流程

| 分类 | 包含卡片 | 跳转目标 | 字段说明 |
|------|---------|---------|---------|
| 患者概览 | 患者人数、Smart报告(份) | 患者档案 | 「总数」+「今日新增」 |
| 疾病统计 | 室早/室速/房颤/房扑/房速/房早/持续性房颤/阵发性房颤/二联律/三联律/停搏/心动过速/心动过缓等 | 患者档案（带疾病筛选） | 「总数」+「今日新增」 |
| 审核任务 | 待审核数据/待审核报告/待审核周报 | 数据管理子页 | 仅「今日新增」 |
| 物流看板 | 待发货数、预约回收数 | 设备收发各 tab | 仅「今日新增」 |
| 随访监控 | 项目个数、入组人数、进行中人数、待随访人数、延期人数、中止人数 | 随访管理子页 | 仅「今日新增」 |

特殊跳转：
- [MUST] (BIZ004) 疾病统计卡片跳转后，页面筛选框必须断言已选中对应疾病名
- [MUST] (BIZ007) 入组人数跳转患者档案，URL [MUST] 带 `joinStatus=1`
- [MUST] 随访状态类卡片（进行中/待随访等）跳转随访管理「已入组」tab

### 指标总览 - 自定义功能（核心易错点）

[MUST NOT] (BIZ002) 用"重置"按钮来移除所有指标。
重置真实作用：仅恢复**本次弹窗打开后**的操作，无法恢复上次保存结果。

[MUST] (BIZ002) 移除所有指标的正确流程：
打开自定义弹窗 → 用 `for` 循环逐个点击指标右侧的「移除」→ 保存布局 → 返回工作台验证。

[MUST] (BIZ003) 添加指标的验证逻辑：
添加 N 个 → 保存 → 工作台必须用 `expect(...).to_have_count(N)` 断言恰好 N 个卡片（不多不少）。

[MUST] 「自定义」按钮非所有账号可见；用例 [MUST] 开头先判断存在性，不可见则 `pytest.skip()`。

### 预警信息 - 正常流程

| 预警类型 | 数据时间范围 | 下拉筛选选项 | 跳转目标 |
|---------|-------------|------------|---------|
| 房颤预警 | 最近 7 天 | 全部、≥10、≥20、≥30、≥40、≥50 | 患者详情页 |
| 佩戴预警 | 当天 | 全部、未发送、已发送 | 患者详情页 |
| 测量预警 | 最近 3 天 | 全部、未发送、已发送 | 患者详情页 |

### 房颤预警 - 字段精确映射（[MUST] (BIZ001) 全部断言一致）

| 卡片位置 | 卡片字段 | 详情页对应字段 |
|---------|---------|---------------|
| 左上角 | 患者姓名 | 页面左上角患者姓名 |
| 进度条右侧 | 占比 | 中间「负荷占比」 |
| 底部左侧 | 有效时长 | 中间「有效时长」（完全一致） |
| 底部右侧 | 负荷时长 | 中间「持续时间」 |

[MUST] (BIZ001) 房颤预警跳转后，以上 4 个字段全部断言；[MUST NOT] 只断言患者姓名。

### 预警下拉筛选

1. [CHECK] 默认进入页面就是「全部」状态 → 用例间无需复位
2. [MUST] 选择筛选后必须验证数据一致性：
   - 房颤选「≥X」→ 所有显示的占比 [MUST] ≥ X
   - 佩戴/测量选「已发送」→ 数据状态必须匹配
3. [MUST] 卡片显示「暂无数据」→ 用例 `pytest.skip()`

### 动态数据处理（所有工作台用例必须遵守）

- [MUST NOT] 假设任何指标/预警一定存在
- [MUST] (BIZ006) 工作台 spec 文件至少出现一次 `pytest.skip()`：指标卡片不存在 → skip；预警「暂无数据」→ skip
- [MUST NOT] 硬编码任何指标名的存在性

### 关键断言矩阵

| 场景 | [MUST] 断言项 |
|------|--------------|
| 普通指标点击跳转 | URL 正确；卡片总数 = 列表总记录数；若为 0 必须显示「暂无数据」；患者人数额外验证今日新增 |
| 疾病统计跳转 | 上述全部 + 筛选框包含该疾病名 |
| 审核/物流/随访跳转 | 卡片今日新增数 = 列表总记录数 |
| 自定义添加 N 个 | 保存后恰好显示 N 个 |
| 自定义移除全部 | 保存后显示空状态「去添加指标」 |
| 房颤预警跳转 | 4 字段全匹配（姓名/占比/有效时长/持续时间） |
| 佩戴/测量预警跳转 | 患者姓名一致 |
| 预警下拉筛选 | 接口参数正确 + 页面数据符合过滤 |

### 操作返回规范

[MUST] (BIZ005) 所有卡片点击跳转并断言完成后，使用 `page.go_back()` 返回工作台。
[MUST NOT] (GEN006) `page.goto(工作台URL)` —— 会丢失机构ID参数导致登录失效弹窗。

---

## 👤 患者档案模块

### 入口
1. 工作台 → 点击「患者档案」
2. [MUST] 断言：URL 正确、页面标题正确、Tab 栏含「全部」「我的患者」

### 搜索查询（每个搜索框独立一条用例）

[MUST] 对以下每个搜索框分别生成一条 test，函数名前缀 `test_search_`：
录入时间、编号、姓名、手机号码、性别、疾病标签、年龄、绑定设备、关注、随访项目、报告类型、入组情况。

每条用例步骤：
1. 输入/选择数据
2. 点击查询
3. [MUST] (BIZ010) 函数体必须出现 `btn_query` 调用与 `expect(` 断言列表中显示的记录符合筛选条件

重置按钮用例（函数名前缀 `test_reset_` 或 `test_search_reset_`）：
1. 先输入任意多个搜索框
2. 点击重置
3. [MUST] (BIZ011) 断言所有搜索框被清空：`expect(locator).to_have_value("")` 或 `to_be_empty()`

### 新增患者按钮（细分多条用例，函数命名规范见 BIZ008）

[MUST] (BIZ008) 至少覆盖以下 5 个核心函数名（缺一即 block）：
- `test_add_patient_open_*` （打开弹窗）
- `test_add_patient_required_*` （必填校验）
- `test_add_patient_phone_checkbox_*` （手机号复选框）
- `test_add_patient_success_*` （完整成功）
- `test_add_patient_cancel_*` （取消）

完整用例清单：

- **用例1** `test_add_patient_open_dialog`：打开弹窗 → 断言弹窗打开 + 默认「新增」Tab 选中
- **用例2** `test_add_patient_required_fields`：不输入数据点确定 → 断言每个必填项下方显示对应异常提示
- **用例3** `test_add_patient_phone_checkbox`：手机号复选框
  - 3.1 未勾选：手机号输入框 [MUST] 可输入
  - 3.2 勾选：手机号输入框 [MUST] 禁用
  - 3.3 勾选 + 填其他必填 + 确定 → 断言无手机号异常，创建成功
- **用例4**：逐个必填项输入非法数据（每框一条用例） → 断言对应异常提示
- **用例5**：逐个输入框输入合法数据（每框一条用例） → 断言无异常
- **用例6** `test_add_patient_success_full`：完整成功流程
  1. 全部合法 → 确定
  2. [MUST] 断言弹窗关闭、列表出现新患者
  3. [MUST] (BIZ009) 返回工作台断言患者人数「今日新增」= 原数字 `+ 1`（[MUST] 新增前先记录原数字；函数体必须出现 "今日新增" 和 "+ 1" 两个关键字）
  4. 验证完成 [MUST] 切回患者档案页便于后续用例
- **用例7**：切换批量导入 Tab → 断言界面切换
- **用例8**：下载模板 → 断言下载成功
- **用例9**：批量导入数据校验 → 断言合法性结果 + 非法数据标红
- **用例10** `test_add_patient_cancel`：取消按钮 → 断言弹窗关闭 + 列表无新增

### 新增收发按钮

- **用例1**：打开弹窗 → 断言弹窗打开
- **用例2**：不输入点确定 → 断言必填项异常提示
- **用例3**：输入不存在手机号 → 断言下拉「暂无数据」
- **用例4**：输入存在手机号
  - 断言下拉显示该手机号
  - 选择后断言姓名、身份证号自动带入
- **用例5**：点发货类型下拉 → 断言选项：正常发货、重新发货、补充耗材、其他
- **用例6**：完整成功流程
  - 输入存在手机号 + 选发货类型 + 备注 + 确定
  - [MUST] 断言：弹窗关闭、进入设备收发列表、记录显示、手机号/类型/备注正确

### 患者详情页

[MUST] 对详情页所有 tab（基本数据/原始数据/个人报告/身体状态/就诊记录/患者问卷）逐个生成用例，验证数据正常展示及点击跳转前后数据一致性。

---

## 设备管理模块 / 问卷管理模块 / 数据管理模块

（探索阶段补齐后，按相同 [MUST] 规则展开）

---

## Python 代码示例

### POM
```python
# tests/pages/patient_archive_page.py
from playwright.sync_api import Page, expect

class PatientArchivePage:
    URL = "https://hospitalweb.tt.xinjikang.cn:8443/patient"

    def __init__(self, page: Page):
        self.page = page
        self.search_name   = page.get_by_label("姓名")
        self.btn_query     = page.get_by_role("button", name="查询")
        self.btn_reset     = page.get_by_role("button", name="重置")
        self.btn_add       = page.get_by_role("button", name="新增患者")

    def goto(self):
        self.page.goto(self.URL)
        expect(self.page).to_have_url(self.URL)

    def search_by_name(self, name: str):
        self.search_name.fill(name)
        self.btn_query.click()
```

### test
```python
# tests/specs/test_patient_archive_smoke.py
import pytest
from playwright.sync_api import expect
from tests.pages.patient_archive_page import PatientArchivePage

@pytest.mark.smoke
def test_search_by_name(auth_context):
    page = auth_context("admin_hospital")
    p = PatientArchivePage(page)
    p.goto()
    p.search_by_name("张三")
    expect(page.get_by_role("cell", name="张三")).to_be_visible()
```
