# AI Agent 测试平台 — 项目指令（CLAUDE.md）

> 本文件是**每日工作的入口**：开工先读本文件 + 记忆索引，再动手。
> 原则：少走弯路、提高效率、不做无效事。规则是硬性的，违反即返工。

## 项目是什么

AI 驱动测试管理平台：需求导入 → AI 生成测试用例（功能/API/WebUI）→ 执行 → 失败分析 → 自愈 → CI/CD/通知/性能测试/知识图谱。**通用项目**——换被测项目不改平台代码，一切项目相关配置走 `ProjectSetting.exploration_config`。

- 后端：FastAPI + SQLAlchemy + Playwright（`backend/`）
- 前端：React + AntD v5 + TypeScript（`frontend/`）
- 数据库：SQLite（开发/冒烟）/ MySQL（生产）
- 启动：`backend/` 下 `uvicorn app.main:app --reload --port 8000`；`frontend/` 下 `npm run dev`

## 每日启动协议（每天开工第一步，按序执行）

1. 读记忆索引 `C:\Users\Lenovo\.claude\projects\D--test-programs-opencode-ai-agent-test-platform\memory\MEMORY.md`（项目全景：子系统状态、规则、雷区）
2. 读最新 `session-changes-YYYY-MM-DD.md`（昨天/最近一天改了哪些、结论是什么）
3. 处理其中的「⚠️ 明天第一件事」清单（验证 → 通过后在当日记忆里标记「已证实」→ 从清单移除）
4. 用户直接下达新任务时：先确认任务涉及哪个子系统，读对应专项记忆（exploration/登录模块/KG/Allure 等）再动手
5. **写任何代码前**：读 `RULES.md`（零硬编码/通用性执行细则），改动收尾对照其第三节做硬编码自查

## 目录地图

```
backend/app/
  core/
    agents/       # LLM Agent（web_ui_conversion_v2 功能→UI转化、system_explorer_agent 等）
    services/     # 核心服务：探索引擎、登录、KG、转化、执行、审批、Allure 等
    models/       # SQLAlchemy 模型（knowledge_graph/project/web_ui_test/requirement_change…）
    schemas/      # Pydantic 请求/响应模型
    api/api_v1/endpoints/  # FastAPI 端点（薄层：参数校验+调服务，逻辑放 services）
    database.py   # 引擎/会话；_apply_schema_migrations 做 SQLite 迁移
    config.py     # 全局配置
  logs/           # 运行日志 + smoke_*.py 冒烟脚本 + explore_results
frontend/src/
  api/            # axios API 封装（轮询类带 isActive 取消回调）
  pages/          # 页面（projects/ProjectDetailPage、tests/…、knowledgeGraph/…）
  components/     # 通用组件（进度弹窗等）
  types/ utils/ hooks/ store/ slices/
docs/             # 需求档案（登录通用鉴权/通用性规则等）+ 架构/用户指南——新需求落档处，改功能前可查询
```

**归属规则**：新端点 → endpoints 薄层 + services 逻辑；新模型 → models；新页面 → pages；逻辑改动不往 endpoints 里塞。

## 硬性规则（违反即返工）

1. **零硬编码**：业务术语、魔法数字、框架选择器全部参数化；可在 `exploration_config.explore` 段按项目覆盖。**例外**：平台内部约定名（'登录模块'/'系统登录'/`__login__`）跨 6 文件+前端匹配，参数化会断链，不参数化（已定性）。**⚠️ 执行细则必读项目根 `RULES.md`（判定标准/反例清单/通用性设计原则/执行机制）——所有代码改动前必读，违反即返工。**
2. **通用项目**：换一个被测系统不应改平台代码。
3. **credentials 不明文入库**：运行时替换占位符，绝不落明文密钥。
4. **不压制错误**：禁止改 tsconfig 压 tsc 错误；tsc 必须 0 errors 才收尾。
5. **逻辑闭环**：任何改动完成后自查三查——①实现逻辑闭环（有没有死代码/断链/未落库）②全链路功能完整 ③硬编码。
6. **每日 memory 收尾**：当天改动写 `session-changes-YYYY-MM-DD.md`（改动清单/验证结果/待办三段式），未完成项进「⚠️ 明天第一件事」段。
7. **删除先看目标**：删文件/删代码前先读，与描述不符先提出，不静默删除。

## 验证基线（改动后必跑，全过才收尾）

```bash
# 一键验证（推荐）：py_compile 全量 + 全部冒烟 + tsc，汇总报告+统一退出码
python scripts/verify.py           # 全量（约 1 分钟）
python scripts/verify.py --no-tsc  # 跳过 tsc 快速回归（约 15 秒）
```

单步排查时可用原始命令：`cd backend && python -m py_compile <文件>` / `python logs/smoke_kg_project.py` / `cd frontend && npx tsc --noEmit`。

新增核心逻辑时，把关键行为补进对应 smoke 脚本（历史 bug 已固化为断言：menus 合并/快照键名/running 仲裁/键名同源…）。

## 临时文件约定（2026-08-23 用户定性）

- 验证/诊断的临时脚本、临时产物**统一放 `backend/logs/tmp/`**（`_tmp_*` 命名），不散落 logs/ 根目录；用完即删，当天收尾清空（`rm -rf backend/logs/tmp/*`）
- **验证一律走真实用例 + 真实服务调用**；临时探针仅诊断应用侧真相（DOM 真实文本/竞态根因），不是验证手段（见 memory/verify-with-real-cases.md）

## 雷区清单（历史踩坑，防重蹈——改动前对照）

| 雷区 | 后果 | 反制 |
|---|---|---|
| **键名不同源**：提取器产出 `page_url`，消费方 `p.get('url')` | 静默死代码（已中招 2 次） | 提取器与消费方共用同一 key helper |
| **JSON 列原地 mutate**：`kg.pages.append()` 后赋回原对象 | SQLAlchemy 认为未变更，**不落库**（丢了 2 项冒烟） | 必须 `list()/dict()` 拷贝新对象再赋回 |
| **version 过滤残留**：KG/探索已项目级，仍按 version_id 过滤 | 数据查不到 | 项目级改造相关改动全仓 grep 旧语义 |
| **乐观更新不回流**：前端改了状态后端不同步 | 刷新丢失 | 前端状态变更必须回流后端 |
| **轮询泄漏**：setInterval 无取消 | 后台死循环 | 轮询带 `isActive` 回调 + useEffect cleanup |
| **异步 fire-and-forget 被 GC**：create_task 无引用 | 任务消失 | 模块级 set 持有 + done_callback discard |
| **f-string prompt 字面花括号**：prompt 用 `f"""..."""` 拼接时写 `{ID}` 会被当变量插值 | 构建 prompt 即 NameError，整批转化崩（2026-08-17 中招） | f-string prompt 内描述性花括号一律 `{{}}` 转义或改用无花括号措辞 |
| **IO/文件名异常吞掉 → 循环静默中断**：多行 label（含 `\n`）拼 state 文件名 → Windows Errno 22 → `explore_guided` try/except 吞异常 | 99 步只探索 35 步，58 条转化报「探索未覆盖此步骤」（2026-08-24 中招） | 文件名 sanitize 控制字符（`re.sub(r'[\x00-\x1f\x7f...]', '_', ...)`）+ 写盘 OSError 保护（跳过不中断）+ 循环中断原因进 stats（`interrupted`）可观测 |
| **线程同步原语挂任务 dict**：cancel_event（threading.Event）挂进 `_BATCH_TASKS[task_id]`，状态端点 `return task` 全 dict JSON 化 | 轮询 GET 500（jsonable_encoder 序列化 `_thread.lock` → ValueError）（2026-08-25 中招） | 异步任务字典只存纯 JSON 数据；Event/Lock 等句柄放独立模块级 dict（如 `_TASK_CANCEL_EVENTS`），任务收尾清理 |

## 关键架构语义（改代码前必读，避免按旧语义改）

- **知识图谱是项目级资产**：`system_exploration_graphs` 每项目物理唯一一行（`UNIQUE(project_id)`）；`version_id` 可空，语义为「最近更新来源版本」；删版本 → `version_id=None` 解除关联，**不删 KG 行**。入口在**项目详情页顶部**，不在版本详情页。
- **写路径统一走 KGPopulator.populate**（merge/full/auto 三模式）+ 手动 /generate（get_or_reset_graph）+ 审批 hook（kg_incremental_explorer）。running 状态由全站 BFS 管线持有；merge 只叠加数据不改状态；stale-running（>2h）兜底置 completed。
- **登录模块**：`login_with_ui_case` 统一入口（functional_to_ui_service）；登录成功 → `storage_state()` 捕获 auth_data 落 KG 供执行复用（API 鉴权自动联动）。**需求定义见 `docs/需求档案_登录通用鉴权与通用性规则.md`（R-01 唯一登录入口/R-02 数据驱动+反射/R-03 零硬编码铁律）——改登录相关代码前先读。**
- **探索引擎链路**：step_parser → element_locator → kg_populator → guided_exploration_agent（步骤驱动）；BFS 全量探索走 bfs_explorer。下拉/Portal/iframe 等特殊场景探索见专项记忆。
- **功能用例 → UI 用例**：web_ui_conversion_v2（LLM 转化，读项目级 KG）；批量每次条数由 `exploration_config.web.convert_batch_size` 控制（默认 15，按项目可调；批量越大漏条/截断风险越高）。
- **「」对象标记约定（跨 7 文件，改生成/解析代码前必读）**：可交互步骤用「」标记 UI 元素名、`""` 标记操作值、`验证：` 开头标记纯断言步骤（step_parser 第 0 层零猜测消费，转化 prompt locator 来源③）。生成侧规则必须 4 路径齐备（主生成 version_generator 四条约 / Step2 two_step_generator / 变更生成 requirement_change_service 单模块+批量+派生重写 / 补偿生成 auditor）；落库前 Auditor `_check_marker_coverage` 做覆盖率诊断（仅观测不拦截，`marker_stats` 进 AuditResult）。**新增生成 prompt 必须带「」约定段。**
- **审批 → 增量探索**：requirement_change_service 审批 commit 后 fire-and-forget `explore_affected_modules`；KG running 时跳过。
- **执行**：ui_test_executor 复用 LoginEngine 手动 loop 管理；trace 文件按模块覆盖。
- **Allure**：JSON/HTML 报告、步骤级追踪、失败截图、不覆盖目录。

## 边界（不主动做，用户明确要求才做）

1. **不修改**：`AGENTS.md`（开发进度历史）、`SKILL.md`（opencode 生成规范）、项目根早期文档（PROGRESS/HOW_TO_RUN 等）、`*.bak` 文件
2. **先确认再动**：生产 MySQL 直接操作、现有 API 签名批量重构、外部发布/推送、删除用户数据
3. **记忆体系**：`memory/MEMORY.md` 是索引，`session-changes-*.md` 是每日流水，专项记忆是子系统状态——新增记忆先查重（同主题更新旧文件），不复制粘贴堆叠

## 验证过的结论（「已证实」清单，不再重复验证）

- 2026-08-14：KG 项目级改造冒烟 35/35 全绿、py_compile 通过、tsc 0 errors（代码层验证完成）
- ⚠️ 待真机验证（见当日 session-changes）：项目页顶部入口 → 登录导入 KG 增长 → 审批增量探索 → 删版本保留 → 换项目隔离。**真机验证通过后移到本清单。**
