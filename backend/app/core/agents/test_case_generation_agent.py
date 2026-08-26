"""
测试用例生成Agent
解决截断问题的核心Agent
"""

from typing import Dict, Any, List
import json
import re

from langchain.tools import Tool
from langchain.prompts import ChatPromptTemplate

from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger
from app.core.models.test_skill import TestSkill, SkillType
from app.core.models.requirement import TestCase as RequirementTestCase


class TestCaseGenerationAgent(BaseAgent):
    """
    测试用例生成Agent
    
    核心功能：
    1. 自动拆分大文档为多个模块批次
    2. 检测截断并自动续写
    3. 合并所有批次结果
    4. 失败批次自动重试
    """
    
    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "TestCaseGenerationAgent")
        
        # 创建Agent执行器
        self.create_agent()
    
    def define_tools(self) -> List[Tool]:
        """定义测试用例生成工具集"""
        
        return [
            Tool(
                name="extract_modules_from_requirement",
                func=self._extract_modules_from_requirement,
                description="从需求文档提取功能模块列表"
            ),
            Tool(
                name="generate_cases_for_single_module",
                func=self._generate_cases_for_module,
                description="为单个模块生成测试用例（避免截断）"
            ),
            Tool(
                name="detect_json_truncation",
                func=self._detect_json_truncation,
                description="检测JSON响应是否截断"
            ),
            Tool(
                name="continue_truncated_generation",
                func=self._continue_truncated_generation,
                description="续写截断的JSON响应"
            ),
            Tool(
                name="merge_batch_results",
                func=self._merge_batch_results,
                description="合并多个批次的生成结果"
            ),
            Tool(
                name="save_test_cases_to_db",
                func=self._save_test_cases_to_db,
                description="保存测试用例到数据库"
            ),
            Tool(
                name="get_skill_template",
                func=self._get_skill_template,
                description="获取SKILL模板配置"
            )
        ]
    
    def build_prompt(self) -> ChatPromptTemplate:
        """构建Agent提示词"""
        
        template = """
你是专业的测试用例生成专家。

任务目标：为需求文档生成完整的测试用例（JSON格式）

执行策略：
1. 使用 extract_modules_from_requirement 提取功能模块
2. 对每个模块使用 generate_cases_for_single_module 生成用例
   - 如果生成截断，立即使用 continue_truncated_generation 续写
   - 不要丢弃已生成的内容
3. 使用 merge_batch_results 合并所有批次结果
4. 使用 save_test_cases_to_db 保存到数据库

重要规则：
- 每批次生成后，必须使用 detect_json_truncation 检查截断
- 截断时立即续写，确保JSON完整
- 单个模块生成避免超出max_tokens限制
- 合并结果时去重（避免重复用例）
- 失败批次最多重试3次

输出格式：
JSON数组，每个测试用例包含：
{
  "id": "TC001",
  "title": "用例标题",
  "module": "所属模块",
  "priority": "P0/P1/P2/P3",
  "test_steps": ["步骤1", "步骤2"],
  "expected_result": "预期结果",
  "test_data": {"key": "value"}
}

输入：
{input}

可用工具：
{tools}

思考过程（逐步执行）：
{agent_scratchpad}

请严格按照策略执行，确保生成完整无截断的测试用例。
"""
        
        return ChatPromptTemplate.from_template(template)
    
    # === 工具实现 ===
    
    def _extract_modules_from_requirement(self, requirement_doc: str) -> str:
        """
        提取模块工具
        
        Args:
            requirement_doc: 需求文档内容
        
        Returns:
            模块列表JSON字符串
        """
        logger.info(f"[Tool] 提取模块，文档长度={len(requirement_doc)}")
        
        # 使用LLM提取模块
        extract_prompt = f"""
从以下需求文档中提取主要功能模块：
{requirement_doc[:8000]}

请返回JSON数组格式：
["模块1", "模块2", "模块3"]

规则：
1. 只提取主要功能模块（二级标题或明显功能块）
2. 过滤掉：概述、背景、简介、附录、目录等非功能模块
3. 模块名称简短（不超过8个字符）
4. 最多提取20个模块
"""
        
        modules_str = self.llm.predict(extract_prompt)
        
        # 解析JSON
        try:
            modules = json.loads(modules_str)
            logger.info(f"[Tool] 提取到{len(modules)}个模块: {modules[:10]}")
            return json.dumps({"modules": modules, "count": len(modules)})
        except:
            # Fallback：使用正则提取
            pattern = r'##?\s*([^\n模块管理配置]{2,8})(模块|管理|配置)'
            matches = re.findall(pattern, requirement_doc)
            modules = [match[0].strip() for match in matches[:20]]
            
            logger.warning(f"[Tool] 正则Fallback提取到{len(modules)}个模块")
            return json.dumps({"modules": modules, "count": len(modules)})
    
    def _generate_cases_for_module(
        self,
        module_name: str,
        requirement_doc: str,
        project_name: str = "测试项目"
    ) -> str:
        """
        为单个模块生成测试用例（避免截断）
        
        Args:
            module_name: 模块名称
            requirement_doc: 需求文档
            project_name: 项目名称
        
        Returns:
            测试用例JSON字符串
        """
        logger.info(f"[Tool] 为模块'{module_name}'生成测试用例")
        
        # 获取SKILL模板
        skill_template = self._get_skill_template()
        
        # 构建提示词（单个模块，避免截断）
        prompt = f"""
项目：{project_name}
模块：{module_name}

需求内容（仅此模块相关部分）：
{requirement_doc[:3000]}

请生成该模块的测试用例（JSON格式，示例用例标题格式为：{module_name}_测试场景1）：

规则：
预估6-8条用例（避免超出max_tokens）
包含正常、异常、边界场景
JSON必须完整，不要截断
"""
        
        # 调用LLM生成
        response = self.llm.predict(prompt)
        
        # 检测截断
        truncation_result = self._detect_json_truncation(response)
        
        if truncation_result["is_truncated"]:
            logger.warning(f"[Tool] 模块'{module_name}'生成截断，启动续写")
            
            # 自动续写
            remaining_count = 8 - truncation_result["generated_count"]
            continued_response = self._continue_truncated_generation(
                response,
                remaining_count,
                {"module": module_name}
            )
            
            return continued_response
        
        logger.info(f"[Tool] 模块'{module_name}'生成成功，JSON长度={len(response)}")
        return response
    
    def _detect_json_truncation(self, response: str) -> str:
        """
        检测JSON截断工具
        
        Args:
            response: LLM响应字符串
        
        Returns:
            截断检测结果JSON
        """
        result = self.detect_truncation(response)
        
        return json.dumps(result)
    
    def _continue_truncated_generation(
        self,
        truncated_response: str,
        remaining_count: int,
        context: Dict[str, Any] = None
    ) -> str:
        """
        续写截断的JSON
        
        Args:
            truncated_response: 截断的响应
            remaining_count: 需要续写的数量
            context: 上下文信息
        
        Returns:
            续写后的完整JSON
        """
        logger.info(f"[Tool] 续写截断JSON，剩余{remaining_count}个对象")
        
        module_name = context.get("module", "未知模块") if context else "未知模块"
        
        continuation_prompt = f"""
之前的生成在以下位置截断：
{truncated_response[-200:]}

模块：{module_name}
已生成对象数：{self._count_generated_objects(truncated_response)}
需继续生成：{remaining_count}个测试用例

请继续生成剩余的测试用例（JSON格式）。
从最后一个完整对象之后开始。
保持相同的JSON结构格式。
不要重复已生成的内容。
"""
        
        # 调用LLM续写
        continuation = self.llm.predict(continuation_prompt)
        
        # 合并两部分
        merged = self._merge_responses(truncated_response, continuation)
        
        logger.info(f"[Tool] 续写成功，合并后长度={len(merged)}")
        
        return merged
    
    def _merge_batch_results(self, batch_results: str) -> str:
        """
        合并多个批次结果
        
        Args:
            batch_results: 批次结果列表（JSON字符串）
        
        Returns:
            合并后的完整结果
        """
        try:
            results_list = json.loads(batch_results)
            
            all_cases = []
            seen_ids = set()
            
            for batch_json in results_list:
                try:
                    cases = json.loads(batch_json)
                    for case in cases:
                        case_id = case.get("id")
                        
                        # 去重
                        if case_id and case_id not in seen_ids:
                            all_cases.append(case)
                            seen_ids.add(case_id)
                except:
                    logger.warning(f"[Tool] 批次结果解析失败，跳过")
                    continue
            
            logger.info(f"[Tool] 合并完成，总用例数={len(all_cases)}，去重={len(seen_ids)}")
            
            return json.dumps(all_cases)
        except Exception as e:
            logger.error(f"[Tool] 合并失败: {str(e)}")
            return batch_results
    
    def _save_test_cases_to_db(self, test_cases_json: str) -> str:
        """
        保存测试用例到数据库
        
        Args:
            test_cases_json: 测试用例JSON字符串
        
        Returns:
            保存结果
        """
        try:
            test_cases = json.loads(test_cases_json)
            
            saved_count = 0
            
            for case_data in test_cases:
                # 创建测试用例对象
                test_case = RequirementTestCase(
                    title=case_data.get("title", ""),
                    module=case_data.get("module", ""),
                    priority=case_data.get("priority", "P1"),
                    test_steps=json.dumps(case_data.get("test_steps", [])),
                    expected_result=case_data.get("expected_result", ""),
                    test_data=json.dumps(case_data.get("test_data", {})),
                    status="pending"
                )
                
                self.db.add(test_case)
                self.db.flush()
                # 方案B：新建用例逻辑=物理（logical_case_id=自身id，变更派生时新行共享此 id）
                test_case.logical_case_id = test_case.id
                saved_count += 1

            self.db.commit()
            
            logger.info(f"[Tool] 成功保存{saved_count}条测试用例到数据库")
            
            return json.dumps({
                "success": True,
                "saved_count": saved_count,
                "message": f"成功保存{saved_count}条测试用例"
            })
        except Exception as e:
            logger.error(f"[Tool] 保存失败: {str(e)}")
            self.db.rollback()
            
            return json.dumps({
                "success": False,
                "error": str(e)
            })
    
    def _get_skill_template(self) -> str:
        """获取SKILL模板"""
        try:
            skill = self.db.query(TestSkill).filter(
                TestSkill.skill_type == SkillType.FUNCTIONAL.value,
                TestSkill.is_global == True
            ).first()
            
            if skill and skill.content:
                logger.info(f"[Tool] 获取到SKILL模板: {skill.name}")
                return json.dumps(skill.content)
            else:
                logger.warning("[Tool] 未找到SKILL模板，使用默认配置")
                return json.dumps({"default": True})
        except Exception as e:
            logger.error(f"[Tool] 获取SKILL模板失败: {str(e)}")
            return json.dumps({"error": str(e)})