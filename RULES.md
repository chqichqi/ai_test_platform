# 零硬编码与通用性规则（RULES.md）

> **本文件是编码规则的强制来源**。所有代码改动前必读，按此严格执行，违反即返工。
> 用户要求（2026-08-16 定）：「所有的代码不要硬编码，所有的功能都得做到通用性，不要换了项目就全挂了。」
> 与 CLAUDE.md 硬性规则 1/2 配套：CLAUDE.md 定原则，本文件定**判定标准、反例清单、执行机制**。

## 一、核心定义

**硬编码 = 把「具体项目的业务特征」写死在平台代码里。**
判定标准（写代码前对照，命中任一条即为硬编码）：

| # | 判定 | 反例（真实教训） |
|---|---|---|
| 1 | 代码中出现**具体系统的选择器/类名/路由** | `div.cursor-pointer.border.rounded`（医院机构卡片）、`#/login/switchorganization` |
| 2 | 代码中出现**业务文案/按钮文字** | `"确 认"`、`"登录"`、`"机构"` |
| 3 | 代码中出现**业务 URL 关键字** | `switchorganization`、`selectOrganization` |
| 4 | 代码中出现**业务术语/魔法数字** | `timeout=5000` 等裸数字、状态流转硬编码 |
| 5 | **执行器自造参数**：步骤数据里没有的参数，执行器自己编一个 | `handle_org_selection` 步骤 args 为空，执行器写死选择器 |

**反例的正确形态**：上述内容出现在**数据位**——步骤数据（`args`）、`exploration_config.explore` 配置段、项目设置。数据位可按项目覆盖，代码位永远不能变。

## 二、通用性设计原则（实现方式）

1. **步骤数据自包含**：执行器只读步骤 `args` 里的参数执行，不自己造定位参数。生成步骤时参数必须写入 args。
2. **自学习回填**：验证/执行真实跑通后，把实际用到的参数**回填到步骤数据**（如 StepRunner `_org_meta` → `__login__` 步骤 args）。换项目 = 重新导入/探索 = 数据自动更新，代码零改动。
3. **反射分发**：按 action 名从 dispatch 表取 handler（如 `_LOGIN_HANDLERS`），新增 action 类型只注册 handler，主循环不改。
4. **配置驱动**：业务词、按钮文字、URL 关键字等一切项目特征走 `exploration_config`（如 `login_username_keywords`/`login_button_keywords`/`login_org_marker_keywords`），代码引用配置变量。
5. **兜底只能是「通用候选」**：兜底选择器必须是跨系统通用的框架特征（如 antd 的 `.ant-select-dropdown`），且优先级低于步骤参数——先读参数，参数缺失才走兜底（服务旧数据），兜底不能是某个具体系统的精确选择器。
6. **同源策略**：同一 action 的多个执行器（StepRunner / login_with_ui_case / LoginEngine）必须共用同一套「参数优先 → 通用兜底」逻辑，禁止各自实现导致分叉。

## 三、执行机制（每次改动强制）

1. **写代码前**：读本文件（CLAUDE.md 硬性规则 1 已挂引用，会话必加载）。
2. **收尾三查**（CLAUDE.md 硬性规则 5 细化）：
   - ①逻辑闭环（死代码/断链/未落库）
   - ②全链路功能完整
   - ③**硬编码自查**：对改动逐行对照第二节判定表——新增的字符串是否进数据位？执行器是否读了 args？兜底是否通用候选？
3. **违规即返工**：被用户/自查发现硬编码，视为返工项，修正后重新验证（verify.py 全绿 + tsc 0 errors）。

## 四、豁免清单（已定性，不参数化）

- **平台内部约定名**：`'登录模块'`/`'系统登录'`/`__login__`——跨 6 文件 + 前端匹配，参数化会断链（平台自身概念，非被测项目特征）。
- **框架通用选择器兜底**：antd 等框架级特征类（`.ant-select-dropdown`）可作为兜底候选，但**必须**步骤参数优先。
- **平台语义判定**：`'/login' not in url` 等登录成败判定属于平台通用语义（任何项目的登录页都含 login），不属于业务硬编码。

## 五、历史教训档案（每次违规沉淀于此）

| 日期 | 违规 | 修正 | 沉淀 |
|---|---|---|---|
| 2026-08-16 | login_engine.py 修复机构选择时写死医院卡片选择器/「确 认」按钮 | 步骤数据参数化（cards_selector/confirm_text 回填 args）+ 反射分发 `_LOGIN_HANDLERS` + StepRunner 自学习 `_org_meta` | 生成步骤时 args 必须承载参数；执行器只读 args |
| 2026-08-16 | 批量转化 `max_tokens=8000` 硬编码——推理模型（deepseek-v4-pro）推理写入 reasoning_content，8000 只够推理、正文未开始就 finish_reason=length（配置 160000 的 5%） | 全部 LLM 调用点统一 `get_scaled_max_tokens(ratio, cap)` 百分比预算 | LLM 调用点禁止裸数字；预算 = 配置 max_tokens 的百分比 |
| 2026-08-16 | 默认 50%/cap 32000 过保守——配置 160000 时 min(0.5×160000, 32000)=32000 封顶，50% 与 70% 同值，比例实际失效 | 默认 0.7（70%，留 30% 余量）/cap 100000（日志实证 API 上限：17:50 deepseek-v4-flash max_tokens=100000 成功，无 400） | 比例与 cap 必须同时生效——cap 小于 ratio×配置时比例形同虚设；cap 定值前查日志实证，不猜 |

## 六、LLM max_tokens 百分比规则（2026-08-16 固化，08-16 修订 70%/100000）

1. **所有 `call_llm` / `async_call_llm` 调用点禁止写死 max_tokens 裸数字**。推理模型把推理过程写入 `reasoning_content`，预算不足时正文还没开始输出就 `finish_reason=length`（content 为空）——2026-08-16 批量转化 8000 tokens 耗尽是直接事故。
2. **统一预算函数**：`LLMService.get_scaled_max_tokens(ratio, cap)` = `min(int(config.max_tokens * ratio), cap)`。**默认 ratio=0.7（70%，留 30% 余量）、cap=100000**——cap 是日志实证的 API 安全上限（2026-08-16 17:50 deepseek-v4-flash max_tokens=100000 调用成功，全日志无 400 报错）；原 0.5/32000 已被 160000 配置封顶（50% 与 70% 同值），比例形同虚设，2026-08-16 修订。
3. **比例先例表**（按任务输出规模选档，不用小裸数字）：

   | 任务类型 | ratio | cap | 示例 |
   |---|---|---|---|
   | 大输出（批量/多步骤/POM/业务流/审计生成） | 0.7 | 100000 | 批量转化、web_ui_conversion_v2、pom_generator、test_case_auditor:209 |
   | 中等（元素提取/单用例重写/API 提取） | 0.1 | 8000 | step_parser、requirement_change_service:1349、api_test_generator:271 |
   | 文档分析 | 0.3 | 8000 | doc_preprocess_service |
   | 失败分析 | 0.15 | 3000 | failure_analysis_service |
   | 小 JSON（编号匹配/缺失索引/去重） | 0.05 | 2000 | requirement_change_service:667、test_case_auditor:158/328、version_generator:1360 |

4. **判定**：代码中出现 `max_tokens=数字` 且非 `get_scaled_max_tokens(...)` → 违规即返工。
5. **豁免**：配置位（`llm_configs.max_tokens` 配置表 / `settings.LLM_MAX_TOKENS` 环境配置）、工具调用链路（llm_explorer 工具循环 4000）、连通性探测（settings:273 max_tokens=10）、智能分批发包策略（async_generation_service SmartBatchStrategy）。
6. **自愈重试**（llm_service.py call_llm）：content 空 + reasoning_content 非空 + finish_reason=length → 预算 ×4（封顶配置值）重试一次；调用点预算已统一百分比后此路径自动受益。
7. **cap 定值纪律**：cap 必须同时让比例生效（cap ≥ ratio×配置典型值），并查日志实证 API 上限（搜 `max_tokens: N (passed` 历史最大值 + 400 报错），不猜、不取过保守值。
