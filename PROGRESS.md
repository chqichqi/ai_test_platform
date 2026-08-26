# AI Agent测试平台 - 开发进度记录

## 最后更新：2026-03-28

---

## 一、项目结构

```
ai-agent-test-platform/
├── backend/                    # FastAPI后端
│   ├── app/
│   │   ├── api/api_v1/endpoints/
│   │   │   ├── llm_configs.py  # LLM配置API
│   │   │   ├── skills.py       # 技能管理API（已完成）
│   │   │   └── settings.py     # 系统设置API
│   │   ├── models/
│   │   │   └── skill.py        # 技能数据模型
│   │   └── services/
│   └── requirements.txt
├── frontend/                   # React前端
│   └── src/
│       ├── components/layout/
│       │   └── MainLayout.tsx  # 主布局（含导航栏）
│       ├── pages/
│       │   ├── knowledge/
│       │   │   ├── RagPage.tsx     # RAG知识库页面（已完成）
│       │   │   └── GraphPage.tsx   # 知识图谱页面（已完成）
│       │   ├── skills/
│       │   │   └── SkillsPage.tsx  # 技能管理页面
│       │   └── settings/
│       │       └── SettingsPage.tsx
│       ├── store/
│       │   ├── slices/
│       │   │   └── themeSlice.ts   # 主题状态管理
│       │   └── knowledgeStore.ts   # 知识库状态管理（新增）
│       └── api/
│           ├── skillApi.ts     # 技能API服务
│           └── llmConfigApi.ts
└── PROGRESS.md                 # 本文件
```

---

## 二、已完成的功能

### 1. 主题系统（3个主题）
- **炫彩科技**（tech-color）：紫色系，默认主题
- **海洋微风**（ocean-breeze）：青色系
- **暮光暖阳**（sunset-glow）：橙色系

**特性**：
- 未选中菜单项：固定炫彩渐变色
- 悬停菜单项：跟随主题变化
- 选中菜单项：跟随主题变化 + 发光效果
- 顶部标题和底部提示：固定炫彩色

**文件**：`frontend/src/store/slices/themeSlice.ts`

### 2. LLM配置管理
- 支持OpenAI、DeepSeek、智谱AI、Moonshot、通义千问、自定义
- 连接测试功能
- 配置CRUD

### 3. 技能管理模块（已完成）
**后端API**（`backend/app/api/api_v1/endpoints/skills.py`）：
- GET /skills - 列表
- POST /skills - 创建
- GET /skills/{id} - 详情
- PUT /skills/{id} - 更新
- DELETE /skills/{id} - 删除
- POST /skills/{id}/run - 运行测试
- GET /skills/{id}/usages - 执行日志
- POST /skills/{id}/test-cases - 创建测试用例

**前端**（`frontend/src/pages/skills/SkillsPage.tsx`）：
- 技能列表展示
- 创建新技能弹窗
- 编辑配置弹窗
- 运行测试弹窗
- 查看日志弹窗
- 删除确认

### 4. 知识管理模块（新增 2026-03-27）
**菜单结构**：
- 左侧"RAG知识库"改为"知识管理"
- 子菜单：RAG库、图谱库

**RAG库功能**（`frontend/src/pages/knowledge/RagPage.tsx`）：
- 知识库列表展示（名称、项目/版本、文档数、分块数、状态、图谱状态）
- **创建知识库**（支持三步流程）：
  1. 基本信息：名称、描述
  2. 上传文档：拖拽上传，支持 PDF/DOC/DOCX/TXT/MD
  3. 高级设置：
     - 分块大小（100-2000字符）
     - 分块方式（自动/段落/句子/固定/语义）
     - Embedding模型选择
     - OCR开关
- 知识库详情弹窗（基本信息 + 文档列表）
- 文档内容查看
- 生成知识图谱功能
- 删除知识库（同步删除关联图谱）

**图谱库功能**（`frontend/src/pages/knowledge/GraphPage.tsx`）：
- 图谱列表展示（名称、来源RAG、实体数、关系数、三元组数、状态）
- 图谱详情查看
- **知识图谱可视化**：
  - Canvas绘图实现
  - 节点圆形显示，不同颜色区分类型
  - 关系连线显示，标注关系名称
  - 缩放控制（放大/缩小/重置）
  - 图例说明

**数据管理**（`frontend/src/store/knowledgeStore.ts`）：
- 使用localStorage持久化数据
- 使用自定义事件同步RAG库和图谱库数据
- 类型定义：
  - RagKnowledgeBase
  - KnowledgeGraph
  - Document
  - GraphNode
  - GraphEdge

### 5. 主题同步优化（新增 2026-03-28）
**全局主题配置**（`frontend/src/App.tsx`）：
- 表格表头背景色跟随主题色
- TAB页选中状态颜色跟随主题色
- 修复所有页面的TypeScript编译错误

### 6. 知识管理后端API（新增 2026-03-28）
**数据模型**（`backend/app/models/knowledge.py`）：
- RagKnowledgeBaseModel - RAG知识库表
- RagDocumentModel - 文档表
- RagChunkModel - 文档分块表
- KnowledgeGraphModel - 知识图谱表
- GraphEntityModel - 图谱实体表
- GraphRelationModel - 图谱关系表

**API端点**（`backend/app/api/api_v1/endpoints/knowledge.py`）：
- GET /knowledge/rag - 获取RAG知识库列表
- POST /knowledge/rag - 创建RAG知识库
- GET /knowledge/rag/{id} - 获取知识库详情
- PUT /knowledge/rag/{id} - 更新知识库
- DELETE /knowledge/rag/{id} - 删除知识库
- POST /knowledge/rag/{id}/documents - 添加文档
- DELETE /knowledge/rag/{id}/documents/{docId} - 删除文档
- POST /knowledge/rag/{id}/generate-graph - 生成知识图谱
- GET /knowledge/graphs - 获取知识图谱列表
- GET /knowledge/graphs/{id} - 获取图谱详情（含实体和关系）
- DELETE /knowledge/graphs/{id} - 删除知识图谱
- GET /knowledge/statistics - 获取统计数据

### 4. 前端对接知识管理后端API（已完成 2026-03-28）
**RagPage.tsx**：
- 使用 `knowledgeApi.listRagBases()` 获取知识库列表
- 使用 `knowledgeApi.createRagBase()` 创建知识库
- 使用 `knowledgeApi.addDocument()` 上传文档
- 使用 `knowledgeApi.getRagBase()` 获取详情
- 使用 `knowledgeApi.deleteRagBase()` 删除知识库
- 使用 `knowledgeApi.generateGraph()` 生成图谱
- 移除 localStorage 模拟数据依赖
- 添加 loading 状态和刷新按钮

**GraphPage.tsx**：
- 使用 `knowledgeApi.listGraphs()` 获取图谱列表
- 使用 `knowledgeApi.getGraph()` 获取图谱详情和可视化数据
- 移除 localStorage 模拟数据依赖
- 添加 loading 状态和刷新按钮
- 修复 ReactFlow Handle 组件问题（添加 source/target Handle）

**knowledgeApi.ts**：
- 添加 `properties` 属性到 GraphNode 类型定义

---

## 三、待完善的功能

### 1. DeepSeek LLM连接问题
- 文件：`backend/app/api/api_v1/endpoints/llm_configs.py`
- 需要用户测试验证

### 2. 技能与LLM联动
- 技能运行时调用实际LLM
- 当前只是模拟执行

### 3. 文档处理功能
- 实际的文档解析和内容提取
- 向量化存储
- 语义检索

### 1. DeepSeek LLM连接问题

## 四、关键代码位置

| 功能 | 文件路径 |
|------|---------|
| 主题配置 | `frontend/src/store/slices/themeSlice.ts` |
| 导航栏布局 | `frontend/src/components/layout/MainLayout.tsx` |
| RAG知识库页面 | `frontend/src/pages/knowledge/RagPage.tsx` |
| 知识图谱页面 | `frontend/src/pages/knowledge/GraphPage.tsx` |
| 知识库状态管理 | `frontend/src/store/knowledgeStore.ts` |
| 知识管理API服务 | `frontend/src/api/knowledgeApi.ts` |
| 技能管理页面 | `frontend/src/pages/skills/SkillsPage.tsx` |
| 技能API服务 | `frontend/src/api/skillApi.ts` |
| 技能后端API | `backend/app/api/api_v1/endpoints/skills.py` |
| 技能数据模型 | `backend/app/models/skill.py` |
| 知识管理后端API | `backend/app/api/api_v1/endpoints/knowledge.py` |
| 知识管理数据模型 | `backend/app/models/knowledge.py` |
| LLM配置API | `backend/app/api/api_v1/endpoints/llm_configs.py` |
| 系统设置页面 | `frontend/src/pages/settings/SettingsPage.tsx` |

---

## 五、下次继续时的提示

继续开发时，只需对我说：

> "请读取 PROGRESS.md 文件，继续开发工作"

或者直接告诉我具体要做什么，比如：
> "继续完善知识管理后端API"
> "实现文档解析功能"
> "实现语义检索功能"

---

## 六、数据库表

技能相关表（已定义模型）：
- skills - 技能主表
- skill_parameters - 技能参数
- skill_usages - 执行记录
- skill_test_cases - 测试用例
- skill_templates - 技能模板

知识管理相关表（已创建 2026-03-28）：
- rag_knowledge_bases_new - RAG知识库表
- rag_documents_new - 文档表
- rag_chunks_new - 文档分块表
- knowledge_graphs - 知识图谱表
- graph_entities - 图谱实体表
- graph_relations - 图谱关系表

---

## 七、技术栈

**前端**：
- React 18 + TypeScript
- Ant Design 5.x
- Redux Toolkit（状态管理）
- React Router 6（路由）
- Vite（构建工具）

**后端**：
- FastAPI
- SQLAlchemy
- Pydantic

---

## 八、启动方式

**前端**：
```bash
cd frontend
npm install
npm run dev
```

**后端**：
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

## 九、备注

1. TypeScript编译错误已全部修复（2026-03-28）
2. 知识图谱可视化使用Canvas实现，后续可考虑升级为D3.js或AntV G6
3. 数据持久化当前使用localStorage，生产环境需要对接后端API