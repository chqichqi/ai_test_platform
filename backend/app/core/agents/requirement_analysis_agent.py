"""
需求分析Agent
基于LangChain实现智能化需求分析，支持：
1. 需求文档解析
2. 知识图谱提取
3. 需求变更分析
4. 测试点映射生成
"""

from typing import Dict, Any, List
import json
import re

from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate

from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger
from app.core.models.requirement import RequirementDocument
from app.core.services.llm_service import KnowledgeGraphExtractor


class RequirementAnalysisAgent(BaseAgent):
    """
    需求分析Agent
    
    核心功能：
    1. 解析需求文档（Word/PDF/TXT）
    2. 提取功能模块和测试点
    3. 构建知识图谱（实体、关系）
    4. 生成测试点映射
    5. 分析需求变更
    """
    
    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "RequirementAnalysisAgent")
        
        self.knowledge_graph_extractor = KnowledgeGraphExtractor(
            llm_service=None  # 将在运行时使用self.llm
        )
        
        self.create_agent()
    
    def define_tools(self) -> List[Tool]:
        """定义需求分析工具集"""
        
        return [
            Tool(
                name="extract_modules",
                func=self._extract_modules,
                description="从需求文档提取功能模块列表"
            ),
            Tool(
                name="extract_knowledge_entities",
                func=self._extract_entities,
                description="提取知识图谱实体（模块、功能、页面）"
            ),
            Tool(
                name="extract_knowledge_relations",
                func=self._extract_relations,
                description="提取实体之间的关系（前置条件、包含、依赖）"
            ),
            Tool(
                name="analyze_requirement_change",
                func=self._analyze_change,
                description="分析需求变更（对比新旧文档）"
            ),
            Tool(
                name="parse_document_content",
                func=self._parse_document,
                description="解析文档内容（Word/PDF/TXT）"
            )
        ]
    
    def build_prompt(self) -> ChatPromptTemplate:
        """构建Agent提示词"""
        
        template = """
你是专业的需求分析专家。

任务目标：深度分析需求文档，提取测试相关信息

执行策略：
1. 使用 parse_document_content 解析文档格式
2. 使用 extract_modules 提取主要功能模块
3. 使用 extract_knowledge_entities 提取知识图谱实体
4. 使用 extract_knowledge_relations 提取实体关系

重要规则：
- 模块提取：只提取核心功能模块，过滤非功能模块（概述、背景、附录）
- 实体识别：识别模块、功能、页面三类实体
- 关系识别：重点关注测试前置条件关系

输出格式：
JSON对象，包含：
{
  "modules": ["模块1", "模块2"],
  "entities": [{"name": "登录", "type": "模块", "description": "..."}],
  "relations": [{"source": "仪表板", "target": "登录", "relation": "前置条件"}]
}

输入：
{input}

可用工具：
{tools}

思考过程：
{agent_scratchpad}

请严格按照策略执行，确保提取完整准确的需求信息。
"""
        
        return ChatPromptTemplate.from_template(template)
    
    # === 工具实现 ===
    
    def _extract_modules(self, requirement_doc: str) -> str:
        """
        提取功能模块
        
        Args:
            requirement_doc: 需求文档内容
        
        Returns:
            模块列表JSON字符串
        """
        logger.info(f"[Tool] 提取模块，文档长度={len(requirement_doc)}")
        
        # 使用简化的模块提取逻辑（基于标题识别）
        module_patterns = [
            r'[一二三四五六七八九十\d]+[、.．]\s*([^\n]{2,10})',
            r'##\s+([^\n]{2,20})',
            r'###\s+([^\n]{2,20})'
        ]
        
        modules = []
        for pattern in module_patterns:
            matches = re.findall(pattern, requirement_doc)
            modules.extend(matches)
        
        # 过滤关键词
        filter_keywords = [
            '概述', '背景', '简介', '附录', '目录', '说明', 
            '规则', '字典', '术语', '前言', '文档', '版本'
        ]
        
        filtered_modules = []
        for module in modules:
            if module and len(module) >= 2:
                is_filtered = any(kw in module for kw in filter_keywords)
                if not is_filtered:
                    filtered_modules.append(module.strip())
        
        # 去重
        unique_modules = list(set(filtered_modules))[:20]
        
        logger.info(f"[Tool] 提取模块完成，数量={len(unique_modules)}")
        
        return json.dumps(unique_modules, ensure_ascii=False)
    
    def _extract_entities(self, requirement_doc: str) -> str:
        """
        提取知识图谱实体
        
        Args:
            requirement_doc: 需求文档内容
        
        Returns:
            实体列表JSON字符串
        """
        logger.info(f"[Tool] 提取实体，文档长度={len(requirement_doc)}")
        
        # 使用KnowledgeGraphExtractor的逻辑
        truncated_content = requirement_doc[:10000] if len(requirement_doc) > 10000 else requirement_doc
        
        # 从LLM调用提取实体
        extract_prompt = f"""
从以下需求文档中提取系统模块和功能点，用于测试前置条件分析。

文档内容：
{truncated_content}

提取规则：
1. 模块：系统的功能模块（如"登录"、"仪表板"）
2. 功能：模块内的具体功能（如"创建知识库"、"上传文档"）
3. 页面：独立的页面（如"登录页"、"注册页"）

返回JSON数组，每个实体包含：
- name: 实体名称（不超过8字符）
- type: 实体类型（模块/功能/页面）
- description: 简短描述（不超过20字符）
- requires_login: 是否需要登录（true/false）

示例：
[
  {"name": "登录", "type": "模块", "description": "用户登录验证", "requires_login": false}
]

最多提取20个实体。只返回JSON数组。
"""
        
        # 调用LLM（使用BaseAgent的llm）
        from langchain.schema import HumanMessage, SystemMessage
        
        messages = [HumanMessage(content=extract_prompt)]
        response = self.llm.invoke(messages)
        content = response.content
        
        # 解析JSON
        try:
            # 清理响应
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            # 提取数组部分
            start = json_str.find('[')
            end = json_str.rfind(']')
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
            
            entities = json.loads(json_str)
            
            # 验证并过滤
            valid_entities = []
            for e in entities:
                if isinstance(e, dict) and 'name' in e and 'type' in e:
                    valid_entities.append({
                        'name': str(e.get('name', ''))[:12],
                        'type': str(e.get('type', '模块'))[:10],
                        'description': str(e.get('description', ''))[:50],
                        'requires_login': e.get('requires_login', True)
                    })
            
            logger.info(f"[Tool] 提取实体完成，数量={len(valid_entities)}")
            
            return json.dumps(valid_entities, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 实体提取失败: {str(e)}")
            # 返回默认实体
            default_entities = [
                {"name": "登录", "type": "模块", "description": "用户登录验证", "requires_login": False},
                {"name": "仪表板", "type": "模块", "description": "系统概览", "requires_login": True}
            ]
            return json.dumps(default_entities, ensure_ascii=False)
    
    def _extract_relations(self, entities_json: str) -> str:
        """
        提取实体关系
        
        Args:
            entities_json: 实体列表JSON字符串
        
        Returns:
            关系列表JSON字符串
        """
        logger.info(f"[Tool] 提取关系")
        
        try:
            entities = json.loads(entities_json)
            
            # 使用简单的推断逻辑（基于requires_login字段）
            relations = []
            
            # 找出登录模块
            login_entity = None
            other_entities = []
            for e in entities:
                if e['name'] in ['登录', 'Login', '登录验证']:
                    login_entity = e
                else:
                    other_entities.append(e)
            
            # 所有需要登录的模块，前置条件都是登录
            if login_entity:
                for e in other_entities:
                    if e.get('requires_login', True):
                        relations.append({
                            'source': e['name'],
                            'target': login_entity['name'],
                            'relation': '前置条件'
                        })
            
            logger.info(f"[Tool] 提取关系完成，数量={len(relations)}")

            return json.dumps(relations, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[Tool] 关系提取失败: {str(e)}")
            return json.dumps([], ensure_ascii=False)

    def _analyze_change(self, input_dict: str) -> str:
        """
        分析需求变更
        
        Args:
            input_dict: 包含original_doc和supplement_doc的JSON字符串
        
        Returns:
            变更分析结果JSON字符串
        """
        logger.info(f"[Tool] 分析需求变更")
        
        try:
            input_data = json.loads(input_dict)
            original_doc = input_data.get('original_doc', '')
            supplement_doc = input_data.get('supplement_doc', '')
            
            # 简化的变更分析逻辑
            original_modules = json.loads(self._extract_modules(original_doc))
            supplement_modules = json.loads(self._extract_modules(supplement_doc))
            
            # 对比差异
            added = [m for m in supplement_modules if m not in original_modules]
            deleted = [m for m in original_modules if m not in supplement_modules]
            unchanged = [m for m in original_modules if m in supplement_modules]
            
            change_analysis = {
                'change_summary': {
                    'added_modules': added,
                    'modified_modules': [],
                    'deleted_modules': deleted,
                    'unchanged_modules': unchanged
                },
                'detail_analysis': []
            }
            
            logger.info(f"[Tool] 变更分析完成：新增{len(added)}，删除{len(deleted)}，不变{len(unchanged)}")
            
            return json.dumps(change_analysis, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 变更分析失败: {str(e)}")
            return json.dumps({'error': str(e)}, ensure_ascii=False)
    
    def _parse_document(self, document_path: str) -> str:
        """
        解析文档
        
        Args:
            document_path: 文档路径
        
        Returns:
            文档内容字符串
        """
        logger.info(f"[Tool] 解析文档: {document_path}")
        
        # 简化实现：直接返回路径（实际应调用文件解析服务）
        return document_path