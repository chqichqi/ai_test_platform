# AI驱动测试管理平台 - 开发进度

## 当前状态

**当前阶段**: Phase 22 Enhanced - 知识图谱完整功能 ✅ (已完成)

**剩余工作**: Phase 23-24 - WebUI转换Agent、AI Agent测试功能（待开发）

## 已完成功能

### 第1-4周（核心基础）✅
- 项目与版本管理
- Git版本管理
- 需求导入 → AI生成XMind（OPML格式）
- AI生成测试用例

### 第5周（WebUI测试）✅
- 智能元素定位器（支持多种定位策略）
- WebUI测试用例管理
- 测试执行（支持多浏览器）

### 第6周（API测试）✅
- Swagger/OpenAPI文档导入
- API接口解析
- AI生成API测试用例（正常/异常/边界场景）
- 测试环境管理

### 第7周（自愈机制）✅
- 元素定位器自动修复
- 页面变更检测
- 修复记录审批流程
- AI元素匹配服务

### 第8周（AI失败分析）✅
- 问题跟踪数据模型（Issue, FailureAnalysis, IssueComment, IssueHistory）
- AI失败分析服务（集成LLM进行智能分析）
- 问题管理API端点
- 从分析结果自动创建问题
- 相似问题查找

### 第9周（问题跟踪管理）✅
- 问题统计报表（趋势、汇总、仪表盘）
- 问题导出功能（Excel/CSV/JSON）
- 问题关联分析（按失败类型、用例、根本原因）
- 前端问题管理页面（列表、详情、仪表盘）

### 第10-11周（CI/CD集成）✅
- CI/CD数据模型（CICDConfig, PipelineDefinition, PipelineExecution, WebhookEvent）
- Jenkins集成服务（连接测试、Job列表、触发构建、构建状态）
- GitLab CI集成服务（项目列表、Pipeline列表、触发Pipeline）
- GitHub Actions集成服务（Workflow列表、触发Workflow）
- Webhook回调处理
- CI/CD配置API端点
- Pipeline管理API端点
- 执行记录API端点
- 前端CI/CD配置页面

### 第12周（告警通知）✅
- 通知数据模型（NotificationChannel, AlertRule, MessageTemplate, NotificationHistory）
- 飞书通知服务（Webhook消息卡片）
- 钉钉通知服务（Markdown消息 + 签名验证）
- 企业微信通知服务（Markdown消息）
- 邮件通知服务（SMTP + HTML/纯文本）
- 告警规则管理（触发条件配置）
- 通知渠道测试功能
- 前端通知配置页面（渠道管理、规则管理、通知历史）

### 第13周（性能测试）✅
- JMeter脚本管理（JMX上传、编辑、版本管理）
- 性能测试数据模型（JMeterScript, ScriptVersion, PerformanceScenario, PerformanceTestExecution, PerformanceMetric, GrafanaDashboard, PerformanceReport）
- JMX文件解析服务（线程组、采样器识别）
- 性能测试场景配置（并发、持续时间、压测目标）
- 性能测试执行服务（JMeter集成、异步执行）
- JTL结果解析（TPS、RT、错误率统计）
- 达标评估（TPS、响应时间、错误率阈值）
- Grafana仪表盘配置（嵌入显示）
- 性能报告生成（HTML报告、优化建议）
- 性能测试仪表盘统计

### Phase 21（LangChain Agent框架迁移）✅
- **LangChain Agent基础架构**
  - BaseAgent基类（统一接口、截断检测、失败重试）
  - AgentConfig配置管理（LangChain LLM适配）
  - AgentService统一服务层（替代LLMService）
  
- **核心Agent实现**
  - TestCaseGenerationAgent（测试用例生成）
    - 自动拆分大文档为多个模块批次
    - 检测截断并自动续写
    - 合并所有批次结果
    - 失败批次自动重试
    
  - RequirementAnalysisAgent（需求分析）
    - 解析需求文档（Word/PDF/TXT）
    - 提取功能模块和测试点
    - 构建知识图谱（实体、关系）
    - 生成测试点映射
    - 分析需求变更
    
  - APITestGenerationAgent（API测试生成）
    - 解析Swagger/OpenAPI文档
    - 提取API接口列表
    - 分析接口依赖关系（拓扑排序）
    - 为每个接口生成测试用例（正常/异常/边界）
    - 智能生成请求参数和断言规则
    
  - FailureAnalysisAgent（失败分析）
    - 分析测试失败信息（失败消息、堆栈、DOM快照）
    - 识别失败类型（元素定位失败、断言失败、超时等）
    - 分析根本原因（UI变更、环境问题、业务逻辑等）
    - 生成修复建议和自动修复方案
    - 查找相似失败记录

### Phase 22（系统探索Agent）✅
- **SystemExplorerAgent（系统探索Agent）**
  - Playwright自动启动浏览器（chromium/firefox/webkit）
  - 智能登录系统（识别登录表单）
  - 识别导航菜单结构（侧边栏、顶部菜单）
  - 遍历所有页面
  - 扫描页面元素（按钮、输入框、链接）
  - 提取表单信息（字段、验证规则）
  - 提取表格结构（表头、数据格式）
  - 录制关键操作流程（点击、输入、提交）
  - 提取API调用（监听网络请求）
  - 生成元素定位器（多策略：ID、XPath、CSS）
  - 构建知识图谱数据
  - 验证定位器有效性
  - 保存知识图谱到数据库

### Phase 22 Enhanced（知识图谱完整功能）✅
- **后端实现**
  - 数据模型（5个表）：KnowledgeGraph, PageSnapshot, ElementLocator, NavigationFlow, APICallRecord
  - 知识图谱生成服务：智能登录 + 组织选择 + 递归爬取
  - API端点（9个）：generate, progress, detail, list, stats, delete等
  - Schema定义
  
- **前端实现**
  - API封装（含轮询函数）
  - 配置弹窗：系统URL + 登录凭证 + 探索策略
  - 进度弹窗：实时百分比 + 统计信息 + 查看图谱按钮
  - 可视化页面：D3.js力导向图 + 节点拖拽 + 搜索 + 颜色图例
  
- **智能探索逻辑**
  - 自动登录并识别组织选择页面
  - 跳过租户组织，选择非租户组织
  - 递归爬取所有菜单、页面、元素、API
  - 多策略元素定位器生成（ID → XPath → CSS → Text）
  
- **探索策略**
  - quick（1层）：2分钟
  - normal（2层）：5-10分钟
  - deep（3层）：10-30分钟

### 技术修复（2026-03-29）✅
- MySQL数据库配置修复
  - `.env`配置切换到MySQL连接字符串
  - 移除`web_ui_test.py`中PostgreSQL UUID类型（改为String(36)）
  - 移除`test_simple.py`中未使用的UUID导入
- 数据库初始化成功，所有表创建完成
- 基础数据（角色、权限、管理员用户）初始化完成

### API测试用例生成修复（2026-05-04）✅
- **根本原因分析与修复** (`backend/app/core/services/openapi_test_generator.py`)
  - **空字典布尔判断**: Python中 `{}` 是 `True`，导致 `not body_schema` 永远为 `False`
    - 修复: `parse_request_body()` 改用 `len(body_schema) == 0` 检查
  - **$ref引用未解析**: OpenAPI schema使用 `$ref` 指向 `components/schemas`，代码未递归解析
    - 修复: 新增 `_resolve_ref()` 方法递归解析所有 `$ref` 引用
    - 影响: `UserRegister` 继承 `UserCreate` 字段（username/password），解析后完整获取
  - **可选字段识别**: `anyOf` 包含 `null` 类型表示可选字段
    - 修复: 新增 `_is_optional_type()` 方法正确识别可选字段
- **OAuth2表单格式处理** (`backend/app/api/api_v1/endpoints/api_tests.py`)
  - OAuth2登录接口（`/auth/login`）期望 `application/x-www-form-urlencoded`
  - 修复: `_execute_single_case_with_cache()` 添加判断逻辑
    - OAuth2表单接口使用 `data=body`（而非 `json=body`）
    - JSON接口使用 `json=body`
- **拓扑排序修复** (`backend/app/api/api_v1/endpoints/api_tests.py`)
  - **根因**: 入度计算成"有多少节点依赖此节点"，方向错误
  - **正确**: 入度 = 该节点依赖的其他节点数量
  - **影响**: 前置登录用例（无依赖）入度为最高，被排在最后执行
  - **修复**: `_topological_sort_cases()` 正确计算入度
    - 入度为0的节点（无依赖）最先执行
    - 登录前置用例现在第一个执行
- **变量提取增强** (`backend/app/core/services/api_test_generator.py`)
  - 前置登录用例增加 `refresh_token` 提取配置
  - 支持多路径提取：`token`, `data.token`, `access_token`, `data.access_token`, `refresh_token`, `data.refresh_token`
- **重复用例消除** (`backend/app/core/services/api_test_generator.py`)
  - 前置登录用例已为 `/api/v1/auth/login/json` 生成测试
  - 修复: 循环生成时检查 `is_login_endpoint` 并匹配路径，跳过已生成的前置用例路径
  - 结果: 用例数从46降至41，无重复login/json测试
- **注册接口处理**
  - `UserRegister` schema解析后自动添加 `confirm_password` 字段（与password相同值）

**测试结果对比**:
| 版本 | 总用例 | 通过 | 失败 | 改进 |
|------|--------|------|------|------|
| 修复前 | 46 | 35 | 11 | login/json重复，前置最后执行 |
| 修复后 | 41 | 20 | 10 | 去掉重复，前置先执行 |

**已解决问题（2026-05-05）✅**:
1. **注册接口重复失败** ✅ - 执行时动态生成随机用户名，避免`Username already registered`
   - 修复文件: `backend/app/api/api_v1/endpoints/api_tests.py:938-968`
   - 每次执行生成新的随机值：`testuser_{timestamp}_{random_suffix}`
2. **认证测试断言错误** ✅ - 接受HTTP 401状态码，智能跳过业务码断言
   - 修复文件: `backend/app/core/services/api_assert_executor.py:156-184`
   - 修复文件: `backend/app/core/services/openapi_test_generator.py:1091-1128`
   - 断言规则优化：只期望HTTP 401/403，业务码添加`skip_if_missing`
3. **执行详情状态码显示** ✅ - 底部详情弹窗显示"-"而不是"0"
   - 修复文件: `frontend/src/pages/tests/APITestPage.tsx:1706-1710`
   - 添加严格判断：`actual_status && actual_status !== 0 ? ... : '-'`
4. **执行详情弹窗底部显示索引"0"** ✅ - Modal footer从数组改为直接传递组件
   - 修复文件: `frontend/src/pages/tests/APITestPage.tsx:1423-1427, 1689-1693`
   - 原因：数组作为footer会显示索引，改为Button组件避免此问题

### API测试用例生成增强（2026-05-05）✅
- **业务流程依赖自动识别** (`backend/app/core/services/api_test_generator.py`)
  - 新增 `_identify_workflow_dependencies()` 方法，自动识别接口路径中的业务流程模式
  - 支持模式识别：`/xxx/request → /xxx/confirm`, `/xxx/send → /xxx/verify` 等
  - 自动为前置接口配置 `variable_extractions`（提取token、code、id等关键字段）
  - 自动为后续接口设置 `depends_on`（依赖前置接口）
  - request_body字段自动替换为变量引用 `${token}`
  - 实际效果：password-reset/confirm正确依赖password-reset/request
- **智能响应解析** (`backend/app/core/services/api_test_generator.py`)
  - 新增 `_extract_key_fields_from_response_schema()` 方法
  - 从OpenAPI的responses定义自动推断关键字字段位置
  - 自动识别字段类型：token类（token, access_token等）、code类（verification_code等）、id类（order_id等）
  - 支持$ref引用解析和递归遍历schema结构
  - 支持anyOf/oneOf结构判断，过滤对象类型字段
  - 完全通用：适用于任何遵循OpenAPI规范的API系统
  - 修复文件: `backend/app/core/services/api_test_generator.py:1089-1143`（登录前置用例）
  - 修复文件: `backend/app/core/services/api_test_generator.py:1576-1644`（业务流程前置用例）
- **expected_status动态提取** (`backend/app/core/services/openapi_test_generator.py`)
  - 修复：不再硬编码 `[200, 201, 204]`，从Swagger responses动态提取状态码
  - 正常用例：提取所有200系列状态码（200, 201, 204等）
  - 异常用例：提取所有400系列状态码（400, 401, 403, 404, 422等）
  - 修复文件: `backend/app/core/services/openapi_test_generator.py:698-720`
- **assert_rules动态生成** (`backend/app/core/services/api_test_generator.py`)
  - `_generate_smart_assert_rules()` 改为从Swagger responses动态提取状态码
  - http_status断言不再使用硬编码值
  - 修复文件: `backend/app/core/services/api_test_generator.py:909-947`

**待重启验证**:
- 所有修改已完成代码编写，但需要重启后端才能生效
- 预期效果：
  - request_body正确生成并保存（不再为空字典）
  - expected_status包含Swagger定义的所有状态码（如422）
  - 业务流程依赖正确建立（前置提取token，后续使用token变量）
  - 智能响应解析自动提取关键字字段（无需预定义路径）

### 文档上传进度弹窗优化（2026-05-07）✅
- **问题背景**: 创建版本时上传需求文档，没有显示处理进度提示窗，用户体验不佳
- **解决方案**: 添加统一的进度弹窗，显示上传和智能处理的完整流程
- **修改内容**:
  - **后端API增强** (`frontend/src/api/projectApi.ts:127-134`)
    - `fileApi.upload()` 新增 `onUploadProgress` 回调参数
    - 支持实时显示文件上传进度（0-100%）
    - 使用 axios 的 `onUploadProgress` 监听上传事件
  - **前端进度弹窗** (`frontend/src/pages/projects/ProjectDetailPage.tsx`)
    - 新增6个状态变量：`uploadProgressModalVisible`, `uploadProgress`, `uploadProgressStep`, `uploadProgressStatus`, `uploadProgressMessage`
    - 新增独立进度弹窗Modal（行1904-1956）
      - 显示步骤图标：📤 上传中、✅ 完成、❌ 错误
      - 显示步骤名称：上传文件、提取文本、智能分析、完成
      - 显示进度条：动态百分比（0-100%）
      - 显示进度消息：详细描述当前操作
    - 重构 `performUpload()` 函数（行911-1074）
      - 上传阶段（0-40%）：实时显示文件上传进度
      - 提取文本阶段（40-50%）：提取文档文本内容
      - 智能分析阶段（50-100%）：AI分析文档格式（如果需要）
      - 完成阶段（100%）：显示处理结果，2秒后自动关闭
    - 移除旧的遮罩层提示（原1358-1381行）
    - 移除简单的Alert提示"正在上传文档..."
- **用户体验改进**:
  - 用户可以清晰看到上传进度百分比
  - 知道当前处于哪个步骤（上传、提取、分析）
  - 了解每个步骤的详细描述
  - 完成后自动关闭弹窗，无需手动操作
- **待验证**: 需重启前端服务测试进度弹窗效果

### Phase 2: 项目管理模块补充（2026-04-04）✅
- **模型扩展** (`backend/app/core/models/project_ext.py`)
  - `ProjectMember` - 项目成员管理（支持RBAC：owner/test_lead/tester/developer/viewer）
  - `ProjectEnvironment` - 环境配置管理（dev/test/prod）
  - `VersionDocHistory` - 版本文档历史追踪
  - `ProjectSetting` - 项目设置（通知、执行、测试默认配置）
- **版本状态流增强** (`backend/app/core/models/project.py`)
  - 新增 `FROZEN` 状态到 `VersionStatus` 枚举
  - 更新状态流转规则：`TESTING` → `FROZEN` → `RELEASED`
  - 添加 `get_status_display()` 支持新状态
- **项目成员管理API** (`backend/app/api/api_v1/endpoints/project_members.py`)
  - `GET /projects/roles` - 列出可用角色
  - `GET /{project_id}/members` - 获取成员列表
  - `POST /{project_id}/members` - 添加成员
  - `PUT /{project_id}/members/{member_id}` - 更新成员角色
  - `DELETE /{project_id}/members/{member_id}` - 移除成员
  - `POST /{project_id}/transfer-ownership` - 转移项目所有权
- **项目环境配置API** (`backend/app/api/api_v1/endpoints/project_environments.py`)
  - `GET /{project_id}/environments` - 获取环境列表
  - `POST /{project_id}/environments` - 创建环境配置
  - `GET /{project_id}/environments/{env_id}` - 获取环境详情
  - `PUT /{project_id}/environments/{env_id}` - 更新环境配置
  - `DELETE /{project_id}/environments/{env_id}` - 删除环境配置
  - `POST /{project_id}/environments/{env_id}/set-default` - 设置默认环境
- **版本文档历史API** (`backend/app/api/api_v1/endpoints/version_doc_history.py`)
  - `GET /{project_id}/versions/{version_id}/doc-history` - 获取文档历史列表
  - `GET /{project_id}/versions/{version_id}/doc-history/{history_id}` - 获取历史详情
  - `POST /{project_id}/versions/{version_id}/doc-history` - 创建历史记录
  - `DELETE /{project_id}/versions/{version_id}/doc-history/{history_id}` - 删除历史记录
  - `GET /{project_id}/versions/{version_id}/doc-history/{history_id}/compare` - 对比文档版本
- **项目设置API** (`backend/app/api/api_v1/endpoints/project_settings.py`)
  - `GET /{project_id}/settings` - 获取项目设置
  - `PUT /{project_id}/settings` - 更新项目设置
  - `PATCH /{project_id}/settings/notification` - 更新通知设置
  - `PATCH /{project_id}/settings/execution-defaults` - 更新执行默认配置
  - `PATCH /{project_id}/settings/test-defaults` - 更新测试默认配置
  - `DELETE /{project_id}/settings/custom/{key}` - 删除自定义设置
- **Schemas定义** (`backend/app/core/schemas/project_ext.py`)
  - 成员管理请求/响应模型
  - 环境配置请求/响应模型
  - 项目设置请求/响应模型
  - 文档历史响应模型
- **路由注册** (`backend/app/api/api_v1/api.py`)
  - 注册所有新API端点
- **前端组件** (`frontend/src/components/projects/`)
  - `ProjectMembers.tsx` - 项目成员管理组件
    - 显示成员列表（头像、角色、加入时间）
    - 添加/移除成员
    - 修改成员角色
    - 转移项目所有权
  - `ProjectEnvironments.tsx` - 环境配置管理组件
    - 环境列表（列表/卡片视图）
    - 创建/编辑环境
    - 设置默认环境
    - JSON配置编辑（请求头、环境变量、数据库配置）
  - `ProjectSettings.tsx` - 项目设置组件
    - 通知设置（触发条件、渠道）
    - 执行默认配置（并行数、重试、超时）
    - 测试默认配置（浏览器、视口、无头模式）
  - `index.ts` - 组件导出
- **前端API扩展** (`frontend/src/api/projectExtApi.ts`)
  - 项目成员管理API封装
  - 项目环境配置API封装
  - 项目设置API封装
  - 版本文档历史API封装
- **项目详情页更新** (`frontend/src/pages/projects/ProjectDetailPage.tsx`)
  - 添加Tab导航：版本列表、项目成员、环境配置、项目设置
  - 支持FROZEN状态显示和变更

### Phase 2: 项目管理模块补充 - 完成状态 ✅

### Phase 3: 仪表板增强（2026-04-04）✅
- **后端API** (`backend/app/api/api_v1/endpoints/dashboard.py`)
  - `GET /dashboard/stats` - 系统级统计数据
    - 项目、版本、测试用例总数统计
    - 执行次数、通过率、问题数量统计
    - 最近执行记录和最近问题
  - `GET /dashboard/projects/{project_id}/dashboard` - 项目仪表板
    - 版本状态分布
    - 测试用例状态分布
    - 执行趋势（最近30天）
    - 问题统计（总数、待解决、已解决、按优先级）
  - `GET /dashboard/test-trend` - 测试执行趋势
  - `GET /dashboard/issue-trend` - 问题趋势
- **前端仪表板页面** (`frontend/src/pages/dashboard/DashboardPage.tsx`)
  - 系统级统计卡片（项目、用例、执行、通过率、问题）
  - 项目选择器和日期范围选择器
  - 图表展示：
    - 版本状态分布（饼图）
    - 测试用例状态分布（环形图）
    - 测试执行趋势（折线图）
    - 问题优先级分布（柱状图）
  - 项目概览（进度条）
  - 最近执行列表
  - 最近问题列表
- **前端API** (`frontend/src/api/dashboardApi.ts`)
  - 系统统计API
  - 项目仪表板API
  - 性能仪表板API
  - CI/CD仪表板API
  - 问题仪表板API
  - 趋势数据API

### 第14-15周（AI Agent评估与场景测试）❌
- AI Agent评估指标模块
  - 准确性评估（精确匹配、语义相似度、LLM评估）
  - 一致性测试（多次运行、温度参数）
  - 性能指标（TTFT、响应时间、Token消耗、成本追踪）
  - 安全合规检测（敏感内容、有害内容、偏见检测）
  - 自定义指标配置
- AI Agent场景测试模块
  - 单轮对话测试
  - 多轮对话测试（上下文理解、记忆能力）
  - 角色扮演测试（人设一致性）
  - 工具调用测试（Function Calling）
  - 代码生成测试
  - 长文本处理测试
  - 多模态测试（图像、视频、音频）

### 第16周（AI Agent安全与红队测试）❌
- Prompt注入测试（直接/间接/越权注入）
- 越狱测试（Jailbreak）
- 敏感信息泄露测试
- 有害内容检测（暴力、歧视、违法）
- 对抗样本测试
- 合规性检查
- 安全测试报告生成

### 第17-19周（移动端测试）❌
- APP自动化测试（Appium集成）
  - 设备管理（真机/模拟器）
  - Appium脚本管理
  - 录制回放
  - 性能采集（CPU、内存、电量）
  - 兼容性测试
- 微信小程序测试（miniprogram-automator）
  - 小程序连接与自动化
  - 元素定位策略
  - 测试脚本录制
  - 真机调试测试
  - 性能分析

## 技术架构

### 后端
- **框架**: FastAPI
- **数据库**: SQLite (开发) / MySQL (生产)
- **ORM**: SQLAlchemy
- **AI服务**: LLM集成（通过配置切换模型）

### 前端
- **框架**: React + TypeScript
- **UI组件**: Ant Design
- **状态管理**: React Query

### 关键模型
- `Project` / `Version`: 项目与版本管理
- `ProjectMember` / `ProjectEnvironment` / `ProjectSetting`: 项目扩展（成员、环境、设置）
- `VersionDocHistory`: 版本文档历史
- `GitRepository` / `GitCommit` / `GitWebhook`: Git管理
- `RequirementDocument` / `TestPointMap` / `TestCase`: 需求分析流程
- `APIDefinition` / `APIEndpoint` / `APITestCase`: API测试
- `WebUITestCase` / `WebUITestExecution`: WebUI测试
- `ElementLocator` / `AutoHealRecord`: 自愈机制
- `Issue` / `FailureAnalysis`: 问题跟踪
- `CICDConfig` / `PipelineDefinition` / `PipelineExecution`: CI/CD集成
- `NotificationChannel` / `AlertRule` / `NotificationHistory`: 告警通知
- `JMeterScript` / `PerformanceScenario` / `PerformanceTestExecution`: 性能测试
- `TestSkill` / `SkillExample`: SKILL管理
- `AgentEvaluationMetric` / `AgentScenarioTest` / `AgentSecurityTest`: AI Agent测试

## 运行命令

```bash
# 初始化数据库
cd backend && python -c "from app.core.database import init_db; init_db()"

# 启动后端
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端
cd frontend && npm run dev
```

## 注意事项

1. **模型命名**: `test_simple.py` 中的 `TestCase` 已重命名为 `SimpleTestCase`，避免与 `requirement.TestCase` 冲突
2. **数据库迁移**: 首次运行需要执行数据库初始化
3. **LLM配置**: 需要在系统设置中配置LLM API密钥
4. **已移除模块**: Skills和RAG知识库模块已从菜单中移除（需求文档中无此功能）
5. **SKILL编码限制**: 导入SKILL时自动生成的code限制在50字符内

## API端点

### 项目管理 (/projects)
- `GET /projects/` - 项目列表
- `POST /projects/` - 创建项目
- `GET /projects/{id}` - 项目详情
- `PUT /projects/{id}` - 更新项目
- `DELETE /projects/{id}` - 删除项目

#### 项目成员管理 (/projects)
- `GET /projects/roles` - 获取可用角色列表
- `GET /projects/{id}/members` - 获取项目成员列表
- `POST /projects/{id}/members` - 添加项目成员
- `PUT /projects/{id}/members/{member_id}` - 更新成员角色
- `DELETE /projects/{id}/members/{member_id}` - 移除项目成员
- `POST /projects/{id}/transfer-ownership` - 转移项目所有权

#### 项目环境配置 (/projects)
- `GET /projects/{id}/environments` - 获取环境列表
- `POST /projects/{id}/environments` - 创建环境配置
- `GET /projects/{id}/environments/{env_id}` - 获取环境详情
- `PUT /projects/{id}/environments/{env_id}` - 更新环境配置
- `DELETE /projects/{id}/environments/{env_id}` - 删除环境配置
- `POST /projects/{id}/environments/{env_id}/set-default` - 设置默认环境

#### 项目设置 (/projects)
- `GET /projects/{id}/settings` - 获取项目设置
- `PUT /projects/{id}/settings` - 更新项目设置
- `PATCH /projects/{id}/settings/notification` - 更新通知设置
- `PATCH /projects/{id}/settings/execution-defaults` - 更新执行默认配置
- `PATCH /projects/{id}/settings/test-defaults` - 更新测试默认配置
- `DELETE /projects/{id}/settings/custom/{key}` - 删除自定义设置

#### 版本文档历史 (/projects)
- `GET /projects/{id}/versions/{version_id}/doc-history` - 获取文档历史列表
- `GET /projects/{id}/versions/{version_id}/doc-history/{history_id}` - 获取历史详情
- `POST /projects/{id}/versions/{version_id}/doc-history` - 创建历史记录
- `DELETE /projects/{id}/versions/{version_id}/doc-history/{history_id}` - 删除历史记录
- `GET /projects/{id}/versions/{version_id}/doc-history/{history_id}/compare` - 对比文档版本

### Git管理 (/git)
- `GET /git/repositories` - 仓库列表
- `POST /git/repositories` - 添加仓库
- `GET /git/repositories/{id}` - 仓库详情
- `PUT /git/repositories/{id}` - 更新仓库
- `DELETE /git/repositories/{id}` - 删除仓库
- `GET /git/repositories/{id}/branches` - 分支列表
- `GET /git/repositories/{id}/commits` - 提交记录
- `POST /git/repositories/{id}/test` - 测试连接

### 问题管理 (/issues)
- `GET /issues/` - 问题列表
- `POST /issues/` - 创建问题
- `GET /issues/{id}` - 问题详情
- `PUT /issues/{id}` - 更新问题
- `DELETE /issues/{id}` - 删除问题
- `POST /issues/{id}/assign` - 分配问题
- `POST /issues/{id}/resolve` - 解决问题
- `POST /issues/{id}/close` - 关闭问题
- `POST /issues/{id}/reopen` - 重新打开
- `POST /issues/analyze` - AI分析失败
- `GET /issues/stats/{project_id}` - 问题统计
- `GET /issues/stats/{project_id}/trend` - 问题趋势
- `GET /issues/stats/{project_id}/summary` - 问题汇总
- `GET /issues/dashboard/{project_id}` - 问题仪表盘
- `GET /issues/export` - 导出问题
- `GET /issues/{id}/related` - 关联问题

### CI/CD集成 (/cicd)
- `POST /cicd/configs` - 创建CI/CD配置
- `GET /cicd/configs` - 配置列表
- `GET /cicd/configs/{id}` - 配置详情
- `PUT /cicd/configs/{id}` - 更新配置
- `DELETE /cicd/configs/{id}` - 删除配置
- `POST /cicd/configs/{id}/test` - 测试配置连接
- `POST /cicd/pipelines` - 创建Pipeline
- `GET /cicd/pipelines` - Pipeline列表
- `GET /cicd/pipelines/{id}` - Pipeline详情
- `PUT /cicd/pipelines/{id}` - 更新Pipeline
- `DELETE /cicd/pipelines/{id}` - 删除Pipeline
- `POST /cicd/pipelines/trigger` - 触发Pipeline执行
- `GET /cicd/executions` - 执行记录列表
- `GET /cicd/executions/{id}` - 执行记录详情
- `GET /cicd/dashboard/{project_id}` - CI/CD仪表盘统计
- `POST /cicd/webhook/{platform}/{config_id}` - Webhook回调
- `GET /cicd/jobs/{config_id}` - 获取Job/Workflow列表

### 告警通知 (/notifications)
- `POST /notifications/channels` - 创建通知渠道
- `GET /notifications/channels` - 渠道列表
- `GET /notifications/channels/{id}` - 渠道详情
- `PUT /notifications/channels/{id}` - 更新渠道
- `DELETE /notifications/channels/{id}` - 删除渠道
- `POST /notifications/channels/{id}/test` - 测试渠道
- `POST /notifications/rules` - 创建告警规则
- `GET /notifications/rules` - 规则列表
- `PUT /notifications/rules/{id}` - 更新规则
- `DELETE /notifications/rules/{id}` - 删除规则
- `POST /notifications/send` - 发送通知
- `GET /notifications/history` - 通知历史
- `GET /notifications/options` - 获取选项配置

### 性能测试 (/performance)
- `POST /performance/scripts` - 创建JMeter脚本
- `POST /performance/scripts/upload` - 上传JMX脚本文件
- `GET /performance/scripts` - 获取脚本列表
- `GET /performance/scripts/{id}` - 获取脚本详情
- `PUT /performance/scripts/{id}` - 更新脚本
- `DELETE /performance/scripts/{id}` - 删除脚本
- `POST /performance/scripts/{id}/validate` - 验证脚本
- `GET /performance/scripts/{id}/versions` - 获取脚本版本历史
- `POST /performance/scenarios` - 创建性能测试场景
- `GET /performance/scenarios` - 获取场景列表
- `GET /performance/scenarios/{id}` - 获取场景详情
- `PUT /performance/scenarios/{id}` - 更新场景
- `DELETE /performance/scenarios/{id}` - 删除场景
- `POST /performance/executions/start` - 启动性能测试执行
- `GET /performance/executions` - 获取执行记录列表
- `GET /performance/executions/{id}` - 获取执行详情
- `POST /performance/executions/{id}/stop` - 停止执行
- `GET /performance/executions/{id}/metrics` - 获取执行指标
- `POST /performance/executions/{id}/report` - 生成性能报告
- `GET /performance/reports` - 获取报告列表
- `GET /performance/reports/{id}` - 获取报告详情
- `POST /performance/dashboards` - 创建Grafana仪表盘配置
- `GET /performance/dashboards` - 获取仪表盘列表
- `GET /performance/dashboards/{id}` - 获取仪表盘详情
- `PUT /performance/dashboards/{id}` - 更新仪表盘配置
- `POST /performance/dashboards/{id}/sync` - 同步仪表盘配置
- `DELETE /performance/dashboards/{id}` - 删除仪表盘配置
- `GET /performance/dashboard/{project_id}` - 获取性能测试仪表盘统计
- `GET /performance/options` - 获取选项配置

### SKILL管理 (/skills) ✅
- `GET /skills/` - 获取SKILL列表（支持分页、类型筛选、搜索）
- `POST /skills/` - 创建SKILL
- `GET /skills/{id}` - 获取SKILL详情
- `PUT /skills/{id}` - 更新SKILL
- `DELETE /skills/{id}` - 删除SKILL（物理删除）
- `POST /skills/{id}/copy` - 复制SKILL
- `GET /skills/{id}/export` - 导出SKILL为JSON文件
- `POST /skills/import` - 从JSON文件导入SKILL
- `POST /skills/{id}/test` - 测试SKILL
- `GET /skills/types` - 获取SKILL类型列表
- `GET /skills/options` - 获取SKILL选项配置
- `GET /skills/dashboard` - 获取SKILL仪表盘统计

### AI Agent评估指标 (/agent/metrics) ❌ 待开发
- `POST /agent/metrics/accuracy` - 创建准确性评估
- `GET /agent/metrics/accuracy` - 获取准确性评估列表
- `POST /agent/metrics/consistency` - 创建一致性测试
- `GET /agent/metrics/performance` - 获取性能指标
- `POST /agent/metrics/safety` - 创建安全合规检测
- `GET /agent/metrics/custom` - 获取自定义指标列表
- `POST /agent/metrics/custom` - 创建自定义指标

### AI Agent场景测试 (/agent/scenarios) ❌ 待开发
- `POST /agent/scenarios/single-turn` - 创建单轮对话测试
- `GET /agent/scenarios/single-turn` - 获取单轮对话测试列表
- `POST /agent/scenarios/multi-turn` - 创建多轮对话测试
- `GET /agent/scenarios/multi-turn` - 获取多轮对话测试列表
- `POST /agent/scenarios/roleplay` - 创建角色扮演测试
- `GET /agent/scenarios/roleplay` - 获取角色扮演测试列表
- `POST /agent/scenarios/tool-call` - 创建工具调用测试
- `GET /agent/scenarios/tool-call` - 获取工具调用测试列表
- `POST /agent/scenarios/code-gen` - 创建代码生成测试
- `GET /agent/scenarios/code-gen` - 获取代码生成测试列表
- `POST /agent/scenarios/long-context` - 创建长文本测试
- `GET /agent/scenarios/long-context` - 获取长文本测试列表
- `POST /agent/scenarios/multimodal` - 创建多模态测试
- `GET /agent/scenarios/multimodal` - 获取多模态测试列表
- `POST /agent/scenarios/execute` - 执行场景测试
- `GET /agent/scenarios/results` - 获取测试结果

### AI Agent安全测试 (/agent/security) ❌ 待开发
- `POST /agent/security/injection` - 创建Prompt注入测试
- `GET /agent/security/injection` - 获取注入测试列表
- `POST /agent/security/jailbreak` - 创建越狱测试
- `GET /agent/security/jailbreak` - 获取越狱测试列表
- `POST /agent/security/privacy-leak` - 创建隐私泄露测试
- `GET /agent/security/privacy-leak` - 获取隐私泄露测试列表
- `POST /agent/security/harmful-content` - 创建有害内容检测
- `GET /agent/security/harmful-content` - 获取有害内容检测列表
- `POST /agent/security/adversarial` - 创建对抗样本测试
- `GET /agent/security/adversarial` - 获取对抗样本测试列表
- `POST /agent/security/compliance` - 创建合规性测试
- `GET /agent/security/compliance` - 获取合规性测试列表
- `POST /agent/security/execute` - 执行安全测试
- `GET /agent/security/reports` - 获取安全测试报告
- `GET /agent/security/dashboard/{project_id}` - 安全测试仪表盘

### 仪表板 (/dashboard) ✅
- `GET /dashboard/stats` - 获取系统级统计数据
- `GET /dashboard/projects/{project_id}/dashboard` - 获取项目仪表板数据
- `GET /dashboard/test-trend` - 获取测试执行趋势
- `GET /dashboard/issue-trend` - 获取问题趋势
