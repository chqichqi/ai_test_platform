# AI Agent测试平台 - 开发进度记录

## 最近更新时间
2026-03-29

---

## 一、已完成的功能

### 1. 知识管理模块
- [x] RAG知识库管理（创建、上传文档、分块）
- [x] 知识图谱生成（LLM/正则提取实体关系）
- [x] ReactFlow图谱可视化（已修复Handle组件问题）
- [x] 文档自动分块功能
- [x] 前端对接后端API（移除localStorage模拟数据）
- [x] **修复文档解析问题（2026-03-29）**：正确解析docx/pdf文件内容

### 2. RAG检索功能
- [x] Embedding向量化服务（`LLMService.get_embedding()`）
- [x] 批量文本向量化（`LLMService.get_embeddings_batch()`）
- [x] 向量相似度检索（`RAGRetrievalService.search_similar_chunks()`）
- [x] RAG查询接口（`/api/v1/knowledge/rag/query`）
- [x] 前端集成RAG检索开关
- [x] **支持阿里云dashscope embedding模型（2026-03-29）**
- [x] **修复SQLAlchemy NULL比较问题（2026-03-29）**
- [x] **修复文档内容解析后重新向量化（2026-03-29）**

### 3. AI助手生成模块
- [x] 左侧菜单添加"AI助手生成"按钮
- [x] 收起/展开状态下的按钮显示
- [x] 用户意图识别（区分普通聊天和测试用例生成）
- [x] 流式聊天API端点（`/api/v1/web-ui-tests/chat/stream`）
- [x] 前端流式显示AI回复
- [x] **流式响应修复（2026-03-29）**：使用真正的流式LLM调用
- [x] **聊天页面UI优化（2026-03-29）**：输入框保持焦点，发送按钮在右侧

### 4. 技能管理模块（新增 2026-03-29）
- [x] 技能CRUD（创建、编辑、删除）
- [x] 技能运行和日志
- [x] 前置依赖管理（prerequisites）
- [x] 测试用例管理
- [x] **References（引用）功能**：
  - 支持8种引用类型：知识库、脚本、API、文档、数据源、技能、URL、文件
  - 引用CRUD API
  - 编辑弹窗Tab页管理
- [x] **Assets（资源）功能**：
  - 支持7种资源类型：配置、模板、示例数据、脚本、依赖、模型、其他
  - 资源CRUD API
  - 支持文本内容存储
  - 编辑弹窗Tab页管理

### 5. 其他修复
- [x] 修复401认证错误（使用axiosInstance替代axios）
- [x] 修复TestStatus未导入错误
- [x] 修复图谱列表重复问题（按knowledge_base_id去重）
- [x] **修复AI聊天流式显示问题（2026-03-29）**
- [x] **修复WebUIChatPage token获取问题（2026-03-29）**
- [x] **修复文档内容存储为base64而非文本的问题（2026-03-29）**

---

## 二、待解决的问题

### 1. RAG检索验证
**问题描述**：
- 开启RAG后，需要验证回答内容是否正确从知识库获取
- 需确保分块已向量化

**相关文件**：
- `backend/app/core/services/llm_service.py` - RAGRetrievalService类

### 2. 右侧"生成的测试用例"区域
**问题描述**：
- 区域命名需要修改（可能改为"测试结果"或类似）
- 需要支持：不生成测试用例，直接执行测试并显示结果

### 3. 测试用例保存
**问题描述**：
- 生成的测试用例需要保存到对应的测试管理模块
- 功能测试 → 测试管理 > 功能测试
- API测试 → 测试管理 > API测试
- WEB UI测试 → 测试管理 > WEB UI测试

---

## 三、关键代码位置

### 后端
| 功能 | 文件路径 |
|------|----------|
| LLM服务 | `backend/app/core/services/llm_service.py` |
| RAG检索服务 | `backend/app/core/services/llm_service.py` (RAGRetrievalService类) |
| 知识管理API | `backend/app/api/api_v1/endpoints/knowledge.py` |
| WEB UI测试API | `backend/app/api/api_v1/endpoints/web_ui_tests.py` |
| 向量分块模型 | `backend/app/models/knowledge.py` (RagChunkModel) |
| **技能管理API** | `backend/app/api/api_v1/endpoints/skills.py` |
| **技能数据模型** | `backend/app/models/skill.py` (Skill, SkillReference, SkillAsset) |

### 前端
| 功能 | 文件路径 |
|------|----------|
| AI助手页面 | `frontend/src/pages/tests/WebUIChatPage.tsx` |
| RAG知识库页面 | `frontend/src/pages/knowledge/RagPage.tsx` |
| 知识图谱页面 | `frontend/src/pages/knowledge/GraphPage.tsx` |
| 知识管理API | `frontend/src/api/knowledgeApi.ts` |
| 主布局 | `frontend/src/components/layout/MainLayout.tsx` |
| **技能管理页面** | `frontend/src/pages/skills/SkillsPage.tsx` |
| **技能API服务** | `frontend/src/api/skillApi.ts` |

---

## 四、数据库表结构

### 知识管理相关表
- `rag_knowledge_bases_new` - RAG知识库
- `rag_documents_new` - 文档
- `rag_chunks_new` - 分块（含embedding字段）
- `knowledge_graphs` - 知识图谱
- `graph_entities` - 图谱实体
- `graph_relations` - 图谱关系

### 检查命令
```bash
sqlite3 backend/data/ai_agent_test.db "SELECT COUNT(*) FROM rag_chunks_new WHERE embedding IS NOT NULL;"
```

---

## 五、下次继续的任务

1. **验证RAG检索功能**
   - 确认分块已向量化
   - 测试知识库查询是否返回正确结果
   - 验证开启RAG后的回答质量

2. **完善测试用例保存逻辑**
   - 生成后保存到对应测试管理模块
   - 右侧区域支持直接执行测试

3. **修改右侧区域命名和功能**
   - 根据用户需求调整UI

---

## 六、启动命令

### 后端
```bash
cd backend
python -m uvicorn main:app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm run dev
```

### 构建
```bash
cd frontend
npm run build
```

---

## 七、注意事项

1. **LLM配置**：确保在系统设置中配置了有效的LLM API（DeepSeek/OpenAI等）
2. **向量化**：首次使用RAG时，需要对分块进行向量化
3. **认证Token**：前端必须使用`axiosInstance`而非`axios`，否则会401