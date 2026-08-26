# AI Agent Test Platform — 换项目配置指南

## 概述

本项目采用**分层配置架构**，换项目/换目标系统时，绝大部分情况只需在前端页面操作，**无需打开任何代码或 JSON 文件**。

```
┌──────────────────────────────────────────────┐
│  配置层级         │  修改方式      │  场景    │
├──────────────────────────────────────────────┤
│  系统环境 (.env)  │  编辑文件      │  首次部署│
│  项目设置 (前端)  │  页面表单      │  每个项目│
│  探索配置 (前端)  │  页面表单      │  每个项目│
│  高级选择器 (JSON)│  前端表单/JSON │  特殊UI库│
│  API参数 (请求体) │  API调用/页面  │  每次探索│
└──────────────────────────────────────────────┘
```

---

## 一、系统环境配置 (.env)

**位置**：`backend/.env`  
**修改时机**：首次部署、换服务器、换 LLM 提供商  
**修改方式**：文本编辑

### 1.1 必改项

| 变量 | 说明 | 示例 |
|------|------|------|
| `SECRET_KEY` | 应用密钥（生产环境务必修改） | `openssl rand -hex 32` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `openssl rand -hex 32` |
| `DATABASE_URL` | MySQL 连接串 | `mysql+pymysql://user:pass@host:3306/db` |
| `OPENAI_API_KEY` | LLM API 密钥 | `sk-...` |

### 1.2 LLM 提供商切换

```ini
# 切换到 DeepSeek
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

# 切换到智谱 GLM
LLM_PROVIDER=zhipuai
ZHIPUAI_API_KEY=xxx
ZHIPUAI_MODEL=glm-4
```

### 1.3 CORS 跨域

```ini
# 前端地址变了就加
CORS_ORIGINS=["http://localhost:3000", "http://your-frontend:3000"]
```

---

## 二、项目设置（前端页面）

**位置**：前端 → 项目 → 设置（齿轮图标）  
**修改时机**：每个新项目/新目标系统  
**修改方式**：页面表单（不需要写代码）

### 2.1 探索配置 Tab（最重要）

这是换项目的**核心配置**，在「项目设置 → 探索配置」页签中填写：

#### 必填

| 字段 | 说明 | 示例 |
|------|------|------|
| **目标系统 URL** | 你要测试的 Web 系统地址 | `https://hospitalweb.tt.xinjikang.cn:8443` |
| **登录用户名** | 测试账号 | `18113011002` |
| **登录密码** | 测试账号密码 | `X12345678` |
| **登录后进入哪个页面** | 用于判断登录成功。填入登录后 URL 中含有的关键词 | `工作台`、`home`、`dashboard` |

#### 可选

| 字段 | 说明 |
|------|------|
| **保存登录鉴权** | 开启后，登录提取的 token 会被保存，下次探索直接复用（推荐开启） |
| **是否会出现身份选择** | 有的系统登录后会让你选机构/身份 → 开启并填身份名称 |

#### 高级设置（折叠，通常无需修改）

| 字段 | 说明 | 默认值 |
|------|------|--------|
| 用户名选择器 | 登录表单用户名输入框的 CSS | 自动识别 `input[name="username"]` |
| 机构卡片选择器 | 机构选择页面的卡片元素 | 自动识别 |

> **90% 的项目只需填 URL + 用户名 + 密码 + 登录后页面关键词。其余全部自动识别。**

### 2.2 测试默认配置 Tab

| 字段 | 说明 | 默认值 |
|------|------|--------|
| 默认浏览器 | WebUI 测试使用的浏览器 | Chromium |
| 无头模式 | 后台运行不显示窗口 | 启用 |
| 视口宽度 × 高度 | 浏览器窗口尺寸 | 1920×1080 |

### 2.3 其他 Tab

- **通知设置**：测试完成/失败时的邮件/飞书/钉钉通知
- **执行默认配置**：并行数（默认4）、重试次数（默认1）、超时（默认3600s）

---

## 三、探索配置的内部流转

用户在前端填写的配置，保存后存储到数据库 `project_settings.exploration_config` 字段（JSON 格式），结构如下：

```json
{
  "web": {
    "base_url": "https://你的系统地址",
    "username": "测试账号",
    "password": "测试密码",
    "login_rules": {
      "save_auth": true,
      "logged_in_url_patterns": ["*workpanel*", "*workbench*"],
      "auth_param_names": ["oId", "refresh", "token"],
      "org_url_keyword": "switchorganization",
      "org_title_keyword": "选择机构",
      "org_card_selector": "div.cursor-pointer.border.rounded",
      "org_confirm_text": "确 认",
      "org_select_name": "测试机构"
    },
    "exploration": {
      "discover_selectors": "[class*=\"card\"], ...",
      "nav_selectors": "[role=\"menuitem\"], ...",
      "max_clicks": 80,
      "render_wait": 2.0
    }
  },
  "app": {
    "appium_url": "http://localhost:4723",
    "username": "",
    "password": "",
    "auto_launch": true
  }
}
```

**代码中的读取链路**：

```
前端 ProjectSettings.tsx
  → API PATCH /projects/{id}/settings/exploration
  → DB project_settings.exploration_config (JSON)
  → login_config_from_settings()    → LoginConfig     (登录引擎用)
  → ExplorationConfig.from_project_settings() → WebExplorationConfig (探索引擎用)
```

用户无需关心 JSON 结构，前端表单会自动组装。

---

## 四、高级探索配置（换 UI 框架时需要）

当目标系统使用**非标准 UI 框架**（不是 Ant Design / Element UI），导致自动发现效果差时，需要覆盖 CSS 选择器。

**修改方式**：目前通过修改 `exploration_config.web.exploration` JSON 中的字段实现。前端界面的「高级选择器」表单面板待开发，暂时可通过 API 或数据库直接修改。

### 4.1 可覆盖的探索配置项

所有字段有默认值（覆盖主流框架），**大部分情况无需修改**。

#### 页面交互元素发现

| 字段 | 默认值（部分） | 说明 |
|------|---------------|------|
| `discover_selectors` | `[class*="card"], [class*="panel"], button, a[href], ...` | 可交互元素 CSS |
| `nav_selectors` | `[role="menuitem"], [class*="menu-item"], nav a[href], ...` | 导航/菜单 CSS |
| `dropdown_discover_selectors` | `select, [role="combobox"], [class*="select"]` | 下拉框 CSS |
| `dropdown_option_selectors` | `[role="option"], [class*="option"]` | 下拉选项 CSS |
| `modal_detect_selectors` | `[role="dialog"], dialog[open], [class*="modal"]` | 弹窗/对话框 CSS |
| `table_selectors` | `table, [role="table"], [class*="table"]` | 表格 CSS |

#### 弹窗触发关键词

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `modal_trigger_keywords` | `["自定义","新增","添加","编辑","导入","导出","设置","配置","上传","批量","新建","详情"]` | 点击这些词的元素时，引擎会检查是否弹出对话框 |

#### 噪音 & 安全过滤

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `danger_patterns` | `["退出","注销","删除","移除","清空","重置",...]` | 引擎永远不会点击含这些词的元素 |
| `noise_patterns` | 纯数字、日期格式等 | 自动过滤的非交互文本 |
| `noise_keywords` | `["暂无数据","Loading","请选择",...]` | 自动过滤的占位文本 |

#### 时延 & 阈值

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `render_wait` | `2.0` 秒 | 页面渲染等待 |
| `click_wait` | `1.5` 秒 | 点击后等待 |
| `back_nav_wait` | `1.0` 秒 | 返回导航后等待 |
| `dropdown_wait` | `0.5` 秒 | 下拉展开等待 |
| `modal_wait` | `0.8` 秒 | 弹窗出现等待 |
| `scroll_wait` | `0.5` 秒 | 滚动后等待 |

#### 探索限制

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `max_clicks` | `80` | 单次探索最大点击量 |
| `max_dropdowns` | `20` | 最大下拉探索数 |
| `max_modals` | `8` | 最大弹窗探索数 |
| `max_subpages` | `6` | 最多探索的子页面数 |
| `max_tabs` | `15` | 最大 Tab 记录数 |
| `max_api_endpoints` | `30` | 最大提取 API 端点数 |

#### 文本截断

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `short_name_len` | `40` | 元素短名截断长度 |
| `display_name_len` | `50` | 日志/进度显示名截断长度 |
| `heading_len` | `100` | 页面标题截断长度 |
| `nav_text_len` | `80` | 导航项文本截断长度 |
| `min_text_len` | `2` | 短于此值的文本被忽略 |
| `max_card_text_len` | `80` | 卡片元素最大文本长度 |

### 4.2 Element UI 示例

如果目标系统用的是 Element UI，修改 `exploration_config.web.exploration`：

```json
"exploration": {
  "discover_selectors": "[class*=\"el-card\"], .el-button, a[href], ...",
  "nav_selectors": ".el-menu-item, .el-submenu__title, nav a[href]",
  "dropdown_discover_selectors": ".el-select, select",
  "dropdown_option_selectors": ".el-select-dropdown__item, [role=\"option\"]",
  "modal_detect_selectors": ".el-dialog:not([style*=\"display: none\"]), .el-drawer",
  "table_selectors": ".el-table, table"
}
```

### 4.3 Bootstrap 示例

```json
"exploration": {
  "discover_selectors": ".card, .btn, .nav-link, a[href], [onclick]",
  "nav_selectors": ".navbar-nav .nav-link, .sidebar .nav-link, nav a",
  "dropdown_discover_selectors": ".dropdown-toggle, select",
  "dropdown_option_selectors": ".dropdown-item, [role=\"option\"]",
  "modal_detect_selectors": ".modal.show, .modal:not([style*=\"display: none\"])",
  "table_selectors": ".table, table"
}
```

---

## 五、登录配置详解

`web.login_rules` 控制登录行为。前端表单会自动填写大部分字段。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `username_selector` | CSS | `input[name="username"]` | 用户名输入框 |
| `password_selector` | CSS | `input[type="password"]` | 密码输入框 |
| `submit_text` | 文本 | `登 录` | 登录按钮文本（精确匹配） |
| `submit_fallback` | CSS | `button[type="submit"]` | 登录按钮回退选择器 |
| `save_auth` | 布尔 | `true` | 是否保存鉴权参数 |
| `logged_in_url_patterns` | 列表 | `["*workpanel*","*workbench*"]` | 登录成功 URL 匹配（fnmatch 模式） |
| `auth_param_names` | 列表 | `["oId","refresh","token"]` | URL 中要提取的鉴权参数名 |
| `org_url_keyword` | 文本 | `switchorganization` | 机构选择页 URL 关键词 |
| `org_title_keyword` | 文本 | `选择机构` | 机构选择页标题关键词 |
| `org_card_selector` | CSS | `div.cursor-pointer.border.rounded` | 机构卡片选择器 |
| `org_confirm_text` | 文本 | `确 认` | 机构确认按钮文本 |
| `org_select_name` | 文本 | (空) | 优先选择的机构名称 |
| `render_wait` | 秒 | `1.0` | 登录等待 |
| `login_poll_interval` | 秒 | `0.5` | 登录轮询间隔 |
| `login_max_wait` | 秒 | `30` | 登录最大等待时间 |
| `page_timeout` | 毫秒 | `15000` | 页面超时 |

---

## 六、API 请求参数（每次探索可覆盖）

### explore-workbench 端点

`POST /api/v1/business-flow/explore-workbench/{version_id}`

```json
{
  "module_name": "工作台",   // 探索的模块名（仅用于标记）
  "headless": false          // true=后台运行不显示浏览器窗口
}
```

### generate-ui-from-business-flow 端点

`POST /api/v1/business-flow/generate-ui-from-business-flow/{version_id}`

```json
{
  "business_flow_text": "工作台点击患者人数卡片 → 验证跳转患者档案...",
  "force_explore": false,     // 强制重新探索（忽略缓存）
  "headless": false,          // 无头模式
  "debug_skip_explore": false // 调试模式：跳过探索，只看 LLM 提取的用例
}
```

---

## 七、换项目操作清单

### 新项目接入（90% 的情况）

1. **前端 → 项目设置 → 探索配置**
   - 填写目标系统 URL
   - 填写登录用户名和密码
   - 填写登录后页面关键词（如 `工作台` 或 `dashboard`）
2. **保存**
3. **去业务流页面点击「工作台探索」**

完成。不需要改任何代码。

### 特殊 UI 框架（5% 的情况）

目标系统使用不常见的 UI 框架，自动发现不完整：

1. 打开浏览器开发者工具，观察目标页面的 CSS class 规律
2. 修改 `exploration_config.web.exploration` 中的选择器字段（参见第四章）
3. 重新探索

### 登录流程特殊（5% 的情况）

登录页面有验证码、多步认证等：

1. 先在「探索配置 → 高级设置」中调整 `username_selector`、`submit_fallback` 等
2. 如果自动登录完全不可行 → 手动登录后导出 cookies → 配置 `storage_state`

---

## 八、配置优先级

当同一配置在多处出现时，优先级如下：

```
1. API 请求参数（最高优先级，覆盖本次调用）
2. ProjectSetting.exploration_config（项目级，前端设置）
3. WebExplorationConfig 默认值（代码级）
```

例如：
- `render_wait` 默认 `2.0` → 可在项目 JSON 中覆盖为 `3.0`
- `headless` 默认 `false` → 可在 API 请求中传 `true`

---

## 九、常见问题

### Q: 换项目后探索不到元素？
A: 检查 `web.exploration.discover_selectors` 是否匹配目标系统的 CSS class。参见第四章。

### Q: 登录后一直显示"登录失败"？
A: 检查 `logged_in_url_patterns`。它用 fnmatch 匹配登录成功后的 URL。例如登录后 URL 变为 `/#/home`，则填 `*home*`。

### Q: 探索太慢了？
A: 减小 `max_clicks`（默认 80 → 30）、`max_subpages`（默认 6 → 3）、`render_wait`（默认 2.0s → 1.0s）。

### Q: 探索一直点同一个元素？
A: 可能该元素的 CSS 选择器太通用，导致 `querySelector` 总是返回第一个。在 `discover_selectors` 中增加更具体的 class 名。

### Q: 高级配置 JSON 在哪里编辑？
A: 目前可通过 API PATCH `/projects/{id}/settings/exploration` 直接提交 JSON，或通过数据库工具编辑 `project_settings` 表。前端的高级选择器表单面板计划后续开发中。
