# 功能用例 → UI 用例转化链路设计方案

> **文档定位**：本文档是「功能用例 → UI 用例」转化链路的**唯一权威方案**。平台内任何转化相关代码的**实现、修改、重构都必须与本文档一致**；新增需求先落本档（或明确标注例外）再写代码，禁止凭感觉写代码。
>
> **盘点结论（2026-08-25）**：docs/ 此前只有 `exploration-engine-design.md`（探索引擎 V6 全量 BFS 探索设计，MCP 架构）与 `docs/需求档案_登录通用鉴权与通用性规则.md`（登录链路需求档案）。**转化链路（步骤驱动探索、LLM 转化、执行、API 用例同步生成）完全无方案文档**——本档补齐，并收录 08-23 ~ 08-25 全部新增需求。
>
> **引用关系**：
> - `docs/architecture/exploration-engine-design.md` — BFS 全量探索（本方案的探索是**步骤驱动 guided**，与 BFS 并列的第二条探索路径）
> - `docs/需求档案_登录通用鉴权与通用性规则.md` — 登录链路需求（R-01 唯一登录入口 / R-02 数据驱动+反射 / R-03 零硬编码铁律）
> - `RULES.md` — 零硬编码执行细则（判定标准/反例清单/通用性设计），所有代码改动前必读

---

## 1. 总体链路（端到端）

```
功能用例 (test_cases / test_case 模型, test_steps 字段)
    │
    ▼
① 步骤解析 step_parser.parse_steps            （「」标记第 0 层零猜测 + 指代移交 LLM）
    │  ── 正则未匹配 → _llm_parse_natural_language 回退（规则 7/8/9）
    ▼
② 分组去重 _parse_and_group_steps             （按模块分组 + navigate/go_back 页面段内去重）
    │  ── 产出 module_steps: {module: [GuidedStep...]}
    ▼
③ 缓存命中检查 _query_existing_kg             （按模块读 __step_diagnostics__:{module} 诊断 + 旧格式回退）
    │  ── 覆盖度足够 → 跳过探索；不足 → 步骤驱动探索
    ▼
④ 步骤驱动探索 _run_sync_exploration
    │  逐模块: explore_guided（每步定位→交互→capture_state）
    │         + ApiFlowCapture 同步捕获 XHR/fetch → 落 API 用例
    │         + KGPopulator.populate 按模块写诊断 flow
    ▼
⑤ 预检诊断 _check_case_steps                  （四层回退匹配：target+action → actual_text → 仅 target → 前缀）
    │  ── 仍缺 → 补充探索（仅缺失模块，KG running 时跳过）→ 重查 KG
    ▼
⑥ LLM 转化                                  （单条 _build_generation_prompt / 批量 _convert_batch_v2，**两路径同源**）
    │  ── 动作词表全量 / URL 注入 / 硬约束 / preconditions 注入 / 批量补尾
    │  ── POM 页面类生成 generate_pom_classes（批量路径）
    ▼
⑦ 落库 WebUITestCase                         （test_data = JSON spec；preconditions 顶层透传）
    ▼
⑧ 执行 step_runner.run_parametrized_specs     （参数化数据驱动 + 反射分发 + 前置条件导航）
```

**入口**：`functional_to_ui_service.convert_with_exploration_fallback`（单条/批量共用，签名为 `db, test_case_ids, base_url, browser, viewport_size, headless, script_type, script_language, project_id, force_explore, cancel_check, progress_callback, phase_cb`）。

**归属规则**：新端点 → endpoints 薄层 + services 逻辑；探索/转化/执行逻辑不往 endpoints 里塞。`_BATCH_TASKS` 任务字典与 `_update_phase` 阶段回调驻留 `endpoints/web_ui_tests.py`（薄层例外：任务状态簿）。

---

## 2. 「」对象标记约定（跨文件约定，改生成/解析代码前必读）

| 标记 | 语义 | 消费方 |
|---|---|---|
| `「对象名」` | 可交互步骤的 **UI 元素名**（探索与执行的定位依据） | step_parser 第 0 层、探索侧、LLM prompt locator 来源③、执行定位 |
| `""` | 操作值（fill/select 的输入值） | 同上 |
| `验证：` 前缀 | **纯断言步骤**（不探索，直接进转化断言） | step_parser、_run_sync_exploration 跳过 |

**生成侧规则必须 4 路径齐备**（任何一条路径缺规则段即违反方案）：
1. 主生成：`version_generator` 四条规则（功能用例生成）
2. Step2：`two_step_generator`（两步生成）
3. 变更生成：`requirement_change_service`（单模块 + 批量 + 派生重写）
4. 补偿生成：`auditor`（缺失标记补偿）

**后置诊断**：`Auditor._check_marker_coverage` 产出 `marker_stats` 进 `AuditResult`（**仅观测不拦截**）。

**硬性约定**：新增任何生成 prompt 必须带「」约定段；`__login__`/「登录模块」/「系统登录」为平台内部约定名（跨 6 文件+前端匹配，**不参数化**，已定性）。

---

## 3. 步骤解析（step_parser）

**输入**：功能用例 `test_steps`（`_extract_raw_steps` 只认 test_steps 字段，与探索侧同源）。

**第 0 层（零猜测）**：正则消费「」标记、`""` 操作值、`验证：` 前缀。产出 `GuidedStep(action_type, target_text, fill_value/select_option, module, source)`。

**指代目标检测**（2026-08-25 新增）：`_DEICTIC_RE` 正则（`^(该条|该|此条|此|当前|这条|那条|这行|那行|这一行|上一行|下一个|下一条|上一条|第一个|第一条|最后一条|最新一条|最新|所选|选中|当前选中)`）命中且 target 纯指代（如「点击**该条**预警」）→ 移入 `_unparsed_raw` 交 LLM（LLM 有**全量步骤上下文**可推断被指代对象）。

**LLM 回退规则 7/8/9**（`_llm_parse_natural_language` prompt）：
- 规则 7：指代词 → 推断被指代对象的具体元素名（用「」标记）
- 规则 8：「记录/获取/捕获 XX 的 YY」→ target=YY 或整步跳过；**禁止臆造 assert_visible**
- 规则 9：无法推断 → `action=""`（不编造，宁缺毋假）

---

## 4. 分组与页面段去重（_parse_and_group_steps）

**分组**：按模块（`module`）分组，产出 `module_steps: {module: [GuidedStep...]}`。

**页面段去重**（2026-08-25 修「只探索了部分功能或用例」）：
- 页面边界动作 `_PAGE_BOUNDARY_ACTIONS = ('navigate', 'go_back', 'NAVIGATE', 'GO_BACK')` 处**清空去重记忆**（段间不去重）
- 段内按 `(action_type, target_text[, fill_value/select_option])` 去重（同页同对象探一次）
- **跨页面同名元素（每页的「搜索」「保存」）全保留**——避免 `_check_case_steps` 误命中第一页诊断

**可观测**：日志 `「N步→M对象」`（原始步数→去重后对象数，显式换算防用户误读为「只探索了部分」）。

---

## 5. 步骤驱动探索（guided，与 BFS 并列）

### 5.1 探索对象
只探索 `「」` 标记对象（每步一个对象）；`验证：` 前缀步骤**不探索**。执行引擎：`guided_exploration_agent.explore_guided`（每步：element_locator 评分定位 → 交互 → `_capture_state` 快照）。

### 5.2 缓存命中（_query_existing_kg）
按模块读 `__step_diagnostics__:{module}`（常量 `STEP_DIAG_FLOW_PREFIX` 同源，防键名漂移）+ **旧格式回退**（存量库兼容 `__step_diagnostics__` 无后缀 flow）。覆盖度足够 → 跳过探索直接用缓存（`steps_missing=0` 不触发补充）。

### 5.3 诊断落库（kg_populator.populate）
- 按 `_module` 分组写 `{STEP_DIAG_FLOW_PREFIX}{module}` flow —— **禁止写单一全量 flow**（F1：跨批次补充探索覆盖震荡的根因）
- merge 分支剔除旧格式无后缀 flow（存量一次性迁移）
- 写路径统一 `KGPopulator.populate`（merge/full/auto 三模式）+ 手动 `/generate`（get_or_reset_graph）+ 审批 hook；**merge 只叠加数据不改状态**；running 状态由全站 BFS 管线持有；stale-running（>2h）兜底 completed

### 5.4 预检诊断（_check_case_steps）
四层回退匹配：① target+action 精确 → ② actual_text → ③ 仅 target → ④ 前缀包含。任一命中即视为已覆盖；全不命中 → 该模块进补充探索清单。

### 5.5 补充探索
**仅缺失模块**补充探索（不重探全模块）→ 重查 KG 复查 → 仍缺才标「补充探索后仍无法定位」。KG running 时跳过（等待）。

### 5.6 中断防护与可观测（2026-08-24 事故固化）
- 文件名 sanitize 控制字符（`re.sub(r'[\x00-\x1f\x7f...]', '_', ...)`）——多行 label 含 `\n` 拼文件名会 Windows Errno 22 中断探索循环
- 写盘 OSError 保护（跳过不中断）
- 循环中断原因进 `stats.interrupted`（合并时**保留首个非空原因**，F2）；`KGPopulator.populate` 检测到 interrupted 告警日志
- `_wait_for_target_text` 轮询 `body.innerText`（`target_wait_timeout` 6.0s 参数化）——SPA 骨架态「总数」等定位恢复

### 5.7 探索约束（参数化）
| 配置位 | 默认 | 语义 |
|---|---|---|
| `max_clicks` | 200 | 每模块交互上限（探索收敛闸） |
| `target_wait_timeout` | 6.0s | 目标文本轮询超时 |
| `nav_max_children` | 参数化 | 导航容器子元素上限 |
| `guided_p3_interactive` | False | guided 探索 P3 盲交互开关（BFS 保持 True） |
| 浏览器/视口 | 项目配置 | 探索跟随有头/无头模式 |

---

## 6. LLM 转化生成规则

### 6.1 两路径同源原则（硬性）
单条（`web_ui_conversion_v2._build_generation_prompt`）与批量（`_convert_batch_v2`）的 **prompt 结构、动作词表、JSON 输出模板、硬约束段必须同源**。任何单边补充必须另一路径同步（历史教训：批量缺 preconditions 段/缺 assert_url 词表 → 28 条全丢/LLM 自由发挥）。

### 6.2 动作词表（全量，与执行器一一对应）
```
click / dblclick / fill / select / hover / check / uncheck / press / goto /
go_back / reload / wait_for_render / wait_for_url / wait_for_load_state /
assert_visible / assert_text / assert_value / assert_url /
get_all_items / scroll_to_bottom / skip_if_empty
```
对应执行器 `StepRunner` 显式 dispatch（`_do_click`…`_do_skip_if_empty` 全表）。

### 6.3 URL 注入（2026-08-24，批量生成 goto 编造的根因修复）
- prompt 注入页面 URL 映射：`page_name` 键 + `module` 键（**仅唯一页绑定**）
- **排除登录页**（登录 URL 拦截见 9.5）；逗号污染防护
- 起始页推导（KG 页集合推断入口页）；POM key 白名单；goto 反例约束（禁止 `goto(locator=工作台)` 形态）
- `_sanitize_spec_steps` 三层补全：空 goto 匹配补 URL / page-only 补 URL / 返回起始页替换起始页

### 6.4 硬约束段
| 约束 | 规则 |
|---|---|
| URL 校验 | 「验证：页面URL包含」必须 `assert_url(expected=...)`；**禁止** `assert_visible(locator=URL)` |
| 动态计数 | 含 `(数字)` 的计数文本 locator 去计数部分（`佩戴预警 (0)` → `佩戴预警`） |
| 记录语义 | 「记录/获取/捕获 XX 的 YY」→ target=YY；禁止臆造 assert_visible |
| 导航语义 | 「进入XX页面」必须 `goto`（非 click）；返回起始页用 goto 替换 |

### 6.5 preconditions 链路（2026-08-25，28 条批量全丢根因修复）
```
功能用例.preconditions
  → 批量 prompt 注入「前置条件: {preconditions or '无'}」
  → JSON 模板 preconditions 字段（两路径同源）
  → 解析后 setdefault 兜底（LLM 漏输出补齐，等价单条 _parse_json_spec）
  → 落 test_data.preconditions
  → WebUITestCase.to_dict 顶层透传（存量无键 → ''）
  → 前端列表「前置条件」列
  → 执行侧前置条件导航（见 9.3）
```

### 6.6 批量补尾
末尾追加返回起始页 goto（POM `navigate` full_url 同源规范化）；**无起始页 URL 可推导时跳过补尾**（不追加死 goto）。`convert_batch_size` 每批用例数（默认 15，`ProjectSetting.exploration_config.convert_batch_size` 配置位，批量越大漏条/截断风险越高）。

### 6.7 POM 生成（批量路径）
`generate_pom_classes` 按 KG 页面结构生成页面类（prompt 12KB 级）。**同步 LLM 调用必须线程化**（见 10.4）。

---

## 7. API 用例同步生成（探索期，2026-08-23 新需求）

> 用户定性：「只要有探索就生成对应 API 用例，鉴权参数完全处理进每条用例可直接运行，不影响 Swagger 生成」。

### 7.1 捕获（api_flow_capture.ApiFlowCapture）
- ctx 监听 xhr/fetch；**登录接口排除**；Authorization/Cookie **只记形态不记值**；password/token **脱敏**
- 路径归一化去重（同路径同方法跳过，二次探索 `skipped` 日志）

### 7.2 计数（A1 修复）
- **per_module 模块级计数**（`_module_counts`，`set_module` 初始化）——禁止全局计数截断（首个模块满后其余归零的历史 bug）
- 全局硬上限 `api_capture_max_total`（默认 500，配置位）——仅防单次会话病态海量；达上限**告警日志不静默**

### 7.3 过滤（A2 修复）
`_is_biz_failure()` 纯函数：success 布尔语义优先 → 顶层 code 不在成功集合（`ApiAssertExecutor.COMMON_SUCCESS_CODES` 同源）→ 业务失败；顶层 status 只认明确失败词（`"active"` 等实体状态不误杀）；嵌套业务字段不判定。**业务失败与 4xx 同策略跳过固化**（normal + error 变体都不产出——避免固化必败断言）。

### 7.4 固化规则
- 2xx → normal 用例 + error 变体（缺参数/类型错误/不存在资源/no_auth，4xx 区间断言）
- 探索期真实 4xx/5xx **不固化**（不做 error 变体来源）
- body 保留：json 解析失败**原文截断保留**（`_RAW_BODY_MAX_CHARS = 10000` 常量跨文件同源）；执行侧 dict → `json=`、字符串 → `data=` 原样发送

### 7.5 匹配与基址
- 重定向（302/307）匹配用 **`response.request.url`**（原始请求 URL，A4）
- base_url **逐用例 `rec.origin` 优先**（A5；单域退化为原行为）

### 7.6 鉴权注入（不落明文）
`{{auth_token}}` 占位符 → **运行时注入实时 token**（永不落库、永不过期）；`no_auth` 变体跳过注入（`_skip_auth`，两执行路径判定同源）。**执行侧在 `endpoints/api_tests.py`，共三处路径**：① 单条执行（1258-1276）② 批量执行（1662-1680）③ 前置用例引用路径（911-953，探索用例被引用为前置时其 headers 占位符同样替换）。无 token 可用时**移除残留占位符头**（不发字面量 `{{auth_token}}`）。断言词表 `COMMON_SUCCESS_CODES` 执行/捕获跨文件 import 同源。

### 7.7 配置位
`api_capture_enabled` / `api_capture_per_module` / `api_capture_max_body_bytes` / `api_capture_max_total`（`ProjectSetting.exploration_config`，前端转化弹窗提示「探索生成API用例 N 条」）。

---

## 8. 执行引擎

### 8.1 参数化执行
`step_runner.run_parametrized_specs` —— 在线 pytest 参数化等价（spec 全量参数化含 preconditions）+ `StepRunner` 反射分发（`_do_*` 显式 dispatch 表）。

### 8.2 词表纪律
`NAVIGATION_ACTIONS = ("goto",)` —— **执行侧 goto、探索侧 navigate 两套词表不混用**（同源常量，禁止各自写特征）。

### 8.3 前置条件导航
`test_data.preconditions` → 执行前按前置条件推导起始页导航（08-23 用户定性：**只按用例自身前置条件+测试步骤执行，拒绝 KG 导航复位归因**）。

### 8.4 兜底
- 无导航旧用例 → base_url 兜底
- 生成的 pytest 工程与在线执行**同构**（spec 全量参数化 + BASE_URL 兜底）；V1/规则引擎线性脚本自包含

### 8.5 登录链路
`login_with_ui_case` 统一入口（functional_to_ui_service）；登录成功 → `storage_state()` 捕获 auth_data 落 KG 供执行复用（API 鉴权自动联动）。**单窗口会话**：登录成功同窗口直接执行，不关浏览器重开。

---

## 9. 进度与超时（2026-08-25 晚间）

### 9.1 阶段模型
`_BATCH_TASKS[task_id]`：`phase ∈ {preparing, exploring, pom, converting, done, failed}` + `phase_detail` + `explored_done/total`（模块进度）+ `step_done/total`（当前模块步骤进度）。带 phase 键的事件只更新阶段字段**不追加 results**（`_update_phase`）。

### 9.2 事件注入点
模块循环三档（开始/步骤级/完成）+ `explore_guided` 可选 `progress_cb`（**每步一报，单调用点**）+ POM 生成前 + 补充探索前 + 批量转化循环前。

### 9.3 前端阶段加权
`convertPhaseInfo` + `convertPercent`：探索 0-60%（模块+步骤双进度）、POM 62%、转化 65-100%；无阶段信息回退完成度。轮询文本「阶段详情（已完成 x/y，已运行 X 分 Y 秒）」。

### 9.4 超时与事件循环纪律（硬性）
- **任何同步 call_llm 在 async 上下文必须 `asyncio.to_thread` 线程化**（占死事件循环 → 全站挂起 → 前端轮询超时的根因链：step_parser LLM 回退、generate_pom_classes、chat_stream）
- 轮询 GET 显式 30s 超时 + **连续 3 次失败才判死**（单次瞬时失败不放弃）
- **失败不自动关弹窗**：`batchSucceeded` 标志——成功才延迟关闭；失败保留弹窗 + ❌ 错误详情，用户手动关闭；`pollResult.error` 透传结果弹窗；X 关闭重置 batchConverting

---

## 10. 关键常量与配置位总表

| 常量/配置 | 值 | 位置 | 同源约束 |
|---|---|---|---|
| `STEP_DIAG_FLOW_PREFIX` | `__step_diagnostics__` | kg_populator（写）/ functional_to_ui_service（读） | 跨文件 import |
| `_RAW_BODY_MAX_CHARS` | 10000 | api_flow_capture（捕获）/ 执行侧 | 跨文件 import |
| `COMMON_SUCCESS_CODES` | 成功码集合 | api_assert_executor（断言）/ api_flow_capture（判定） | 跨文件 import |
| `_PAGE_BOUNDARY_ACTIONS` | navigate/go_back×2 | _parse_and_group_steps | 段内去重边界 |
| `_DEICTIC_RE` | 指代词集合 | step_parser | LLM 回退触发 |
| `NAVIGATION_ACTIONS` | ("goto",) | step_runner | 执行侧词表 |
| `_LOGIN_PAGE_NAMES` | login/auth/signin/sso | step_runner + 生成侧 URL 注入 | 同源（禁止各自写特征） |
| `convert_batch_size` | 15 | project_ext 配置位 → 批量分批 | 前后端 schema 同步 |
| `max_clicks` / `target_wait_timeout` / `nav_max_children` / `api_capture_*` | 见各节 | exploration_config | 按项目可覆盖 |
| `__login__` / 「登录模块」/「系统登录」 | 平台内部名 | 跨 6 文件+前端 | **不参数化**（例外） |

---

## 11. 方案 vs 代码一致性核对表

> 任何实现改动后，必须保证下表每行仍成立；新增需求在此表追加行并落代码。

| # | 方案条款 | 代码位置 | 冒烟断言 |
|---|---|---|---|
| 1 | 第 0 层零猜测消费「」标记 | step_parser.parse_steps | smoke P2 |
| 2 | 指代移交 LLM | step_parser `_DEICTIC_RE` + `_llm_parse_natural_language` 规则 7/8/9 | smoke P5 |
| 3 | 页面段去重 | functional_to_ui_service._parse_and_group_steps | smoke P4 |
| 4 | 诊断按模块 flow | kg_populator.populate（写）/ _query_existing_kg（读+旧格式回退） | smoke P2 |
| 5 | 预检四层回退 | _check_case_steps | smoke P1 |
| 6 | 补充探索仅缺失模块 | _run_sync_exploration → 补充路径 | smoke P1 |
| 7 | 批量 preconditions 全链路 | _convert_batch_v2 注入+模板+兜底 / to_dict 透传 / 前端列 | smoke P6 |
| 8 | 动作词表两路径同源 + URL 断言/动态计数/记录语义 | _build_generation_prompt ↔ _convert_batch_v2 | smoke P6 |
| 9 | URL 注入 + _sanitize 三层补全 + 补尾跳过 | _convert_batch_v2 + _sanitize_spec_steps | smoke 2026-08-24 块 |
| 10 | API per_module 计数 + 全局上限 | api_flow_capture._module_counts + api_capture_max_total | smoke A1 块 |
| 11 | 业务失败跳过固化 | _is_biz_failure + COMMON_SUCCESS_CODES 同源 | smoke A2 块 |
| 12 | 非 JSON body 保留 + 执行侧 json=/data= | _RAW_BODY_MAX_CHARS 跨文件 | smoke A3 块 |
| 13 | 重定向 request.url / base_url 逐用例 | api_flow_capture | smoke A4/A5 块 |
| 14 | 鉴权占位符运行时注入（两路径） | api_assert_executor / step_runner | smoke H2 块 |
| 15 | 执行参数化 + 词表纪律 | run_parametrized_specs + NAVIGATION_ACTIONS | smoke 执行块 |
| 16 | 阶段事件 + progress_cb + 前端加权 | _BATCH_TASKS/_update_phase/explore_guided + WebUITestPage | smoke P1-P3（H） |
| 17 | LLM 同步调用线程化 | step_parser 回退/generate_pom_classes to_thread | smoke P2（H） |
| 18 | 中断防护 | sanitize/OSError 保护/interrupted 合并 | smoke 2026-08-24 块 |

---

## 12. 变更纪律（以后必须遵守）

1. **方案先行**：任何转化链路改动，先在本档落条款（含配置位/常量/词表），再写代码
2. **两路径同源**：单条/批量、执行侧单条/批量、捕获/断言——单边改动必须查另一侧
3. **同源优先**：跨文件共享的常量/词表/判定规则必须 import 同源，禁止各自写特征
4. **零硬编码**：业务术语/魔法数字/框架选择器参数化进 `exploration_config`；平台内部名豁免
5. **验证走真实用例**：真实用例 + 真实服务调用；临时探针只诊断不验证，放 `logs/tmp/` 用完即删
6. **改动收尾**：跑 `python scripts/verify.py` 全绿（py_compile + 冒烟 + tsc 0）+ 逻辑闭环三查
