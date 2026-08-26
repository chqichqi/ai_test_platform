"""
版本生成服务
用于在创建版本时自动生成测试用例和 XMind 思维导图
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.services.llm_service import LLMService
from app.core.models.test_skill import TestSkill, SkillType, SkillStatus
from app.core.models.requirement import RequirementDocument, TestPointMap, TestCase as RequirementTestCase, TestCaseStatus, TestCasePriority
from app.core.models.project import Version
from app.core.services.version_generator_utils import clean_module_name


def _calc_limits(max_tokens: int) -> tuple:
    """根据LLM max_tokens动态计算输入/输出上限，预留安全余量。

    策略：
    - 系统prompt固定预留 ~2000 tokens
    - 输入占30%（中文约2字/token）
    - 输出占60%（JSON格式，每条用例约300 token）
    - 剩余10%缓冲
    """
    mt = max_tokens or 8192
    system_overhead = 2000
    available = mt - system_overhead
    input_tokens = int(available * 0.3)
    output_tokens = int(available * 0.6)
    max_input_chars = input_tokens * 2
    safe_cases = max(5, output_tokens // 300)
    return max_input_chars, safe_cases


class VersionGeneratorService:
    """版本生成服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
    
    async def generate_test_assets(
        self,
        version_id: int,
        requirement_doc_content: str,
        project_name: str,
        version_number: str,
        skip_xmind: bool = False,
    ) -> Dict[str, Any]:
        """
        生成测试资产（测试用例和 XMind）- 优化版
        
        优化措施：
        1. 分批处理（每批最多6个模块）
        2. 使用LLM配置的max_tokens，上限100000
        3. 需求内容截断到8KB避免输入过长
        """
        try:
            logger.info(f"[{project_name} v{version_number}] 开始生成测试资产")
            logger.info(f"需求文档长度：{len(requirement_doc_content)} 字符")
            
            # 获取LLM配置的max_tokens（上限100000，因为有些模型限制32768）
            llm_config = self.llm_service.get_active_config()
            config_max_tokens = llm_config.max_tokens if llm_config else 4000
            max_tokens_limit = min(config_max_tokens, 100000)
            logger.info(f"LLM配置max_tokens: {config_max_tokens}, 实际上限: {max_tokens_limit}")
            
            # 1. 获取功能测试 SKILL 模板
            skill = self.db.query(TestSkill).filter(
                TestSkill.skill_type == SkillType.FUNCTIONAL.value,
                TestSkill.is_global == True,
                TestSkill.status == SkillStatus.ACTIVE.value,
            ).first()

            if not skill:
                skill = self.db.query(TestSkill).filter(
                    TestSkill.is_global == True,
                    TestSkill.status == SkillStatus.ACTIVE.value,
                ).first()
                logger.info("未找到功能测试 SKILL，使用通用 SKILL")
            else:
                logger.info(f"找到 SKILL 模板：{skill.name}")
            
            skill_dict = None
            if skill:
                skill_content = skill.content if hasattr(skill, 'content') else None
                skill_dict = skill_content if isinstance(skill_content, dict) else None
            else:
                skill_dict = None
            
            # 2. 先识别模块，再判断是否分批（修复流程顺序）
            logger.info("开始识别模块...")
            modules = self._extract_modules_from_requirement(requirement_doc_content)
            
            # 统一预估用例数量（每模块5个）
            estimated_cases_per_module = 5
            
            logger.info(f"需求文档长度：{len(requirement_doc_content)}字符，识别模块：{len(modules)}个")
            
            # 分批策略：每批次最多6个模块，避免LLM响应截断
            # 每模块约生成6-8个用例，6模块约36-48个用例，JSON约15KB-20KB
            max_modules_per_batch = 6
            
            if len(modules) > max_modules_per_batch:
                # 分批生成
                batch_count = (len(modules) + max_modules_per_batch - 1) // max_modules_per_batch
                logger.info(f"========== 分批生成策略启动 ========== ")
                logger.info(f"总模块数: {len(modules)}, 每批处理: {max_modules_per_batch}个, 共分: {batch_count}批")
                logger.info(f"模块列表: {', '.join(modules[:10])}...")
                
                all_test_cases = []
                
                for batch_idx in range(batch_count):
                    start_idx = batch_idx * max_modules_per_batch
                    end_idx = min(start_idx + max_modules_per_batch, len(modules))
                    current_modules = modules[start_idx:end_idx]
                    
                    logger.info(f"========== 第 {batch_idx+1}/{batch_count} 批开始 ========== ")
                    logger.info(f"处理模块: [{start_idx+1}-{end_idx}] {', '.join(current_modules)}")
                    
                    # 为当前批次构建提示词
                    from typing import cast
                    content_to_use = skill.content if skill and hasattr(skill, 'content') else None
                    skill_content_for_batch = content_to_use if isinstance(content_to_use, dict) else None
                    
                    batch_modules_list = self._format_modules_list(current_modules)
                    # 预估用例数量（每模块6-8个）
                    batch_estimated_cases = len(current_modules) * 8
                    # max_tokens计算：使用LLM配置值，上限max_tokens_limit
                    batch_max_tokens = min(max_tokens_limit, batch_estimated_cases * 400 + 1000)
                    logger.info(f"预计生成: {batch_estimated_cases}条用例，max_tokens: {batch_max_tokens}")
                    
                    # 根据LLM配置动态计算输入上限，截断当前批次相关的需求内容
                    batch_input_limit, _ = _calc_limits(batch_max_tokens)
                    batch_content = self._extract_batch_content(requirement_doc_content, current_modules, batch_input_limit)
                    logger.info(f"需求内容长度: {len(batch_content)}字符 (上限{batch_input_limit})")
                    
                    # 使用SKILL模板变量替换（当前批次）
                    if (skill_content_for_batch and 
                        isinstance(skill_content_for_batch, dict) and 
                        isinstance(skill_content_for_batch.get("prompt_template"), dict)):
                        
                        user_prompt_template = skill_content_for_batch.get("prompt_template", {}).get("user_prompt", "")
                        batch_user_prompt = user_prompt_template.replace("{{project_name}}", project_name)
                        batch_user_prompt = batch_user_prompt.replace("{{version_number}}", version_number)
                        batch_user_prompt = batch_user_prompt.replace("{{requirement_content}}", batch_content)
                        batch_user_prompt = batch_user_prompt.replace("{{modules_list}}", batch_modules_list)
                        batch_user_prompt = batch_user_prompt.replace("{{estimated_cases}}", str(batch_estimated_cases))
                        batch_system_prompt = skill_content_for_batch.get("prompt_template", {}).get("system_prompt", "")
                    else:
                        batch_user_prompt = self._build_user_prompt(project_name, version_number, batch_content, current_modules)
                        batch_system_prompt = self._build_system_prompt(skill_content_for_batch)
                    
                    # 调用LLM生成当前批次
                    batch_response = await self.llm_service.async_call_llm(
                        prompt=batch_user_prompt,
                        system_prompt=batch_system_prompt,
                        temperature=0.3,
                        max_tokens=batch_max_tokens,
                        json_mode=True,
                    )
                    
                    if batch_response:
                        batch_parsed = self._parse_llm_response(batch_response)
                        if batch_parsed and batch_parsed.get("test_cases"):
                            batch_test_case_list = batch_parsed.get("test_cases")
                            all_test_cases.extend(batch_test_case_list)
                            logger.info(f"第{batch_idx+1}批成功生成{len(batch_test_case_list)}条用例")
                        else:
                            # 尝试从截断响应中提取部分用例
                            partial_cases = self._extract_partial_cases_from_response(batch_response)
                            if partial_cases:
                                all_test_cases.extend(partial_cases)
                                logger.warning(f"第{batch_idx+1}批JSON截断，提取到{len(partial_cases)}条部分用例")
                    else:
                        logger.warning(f"第{batch_idx+1}批LLM调用失败，跳过")
                
                # 汇总结果
                if all_test_cases:
                        parsed_result = {
                            "test_cases": all_test_cases,
                            "analysis_summary": {
                                "total_count": len(all_test_cases),
                                "p0_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P0"),
                                "p1_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P1"),
                                "p2_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P2"),
                                "p3_count": sum(1 for tc in all_test_cases if tc.get("priority") == "P3"),
                            }
                        }
                        logger.info(f"分批生成完成，共{len(all_test_cases)}条用例")
                        # 分批生成完成，直接跳转到保存步骤
                        llm_response = None  # 标记为分批生成
                else:
                    logger.error("所有批次生成失败")
                    return {"success": False, "error": "分批生成失败"}
            else:
                # 单次生成（模块数<=6，可以一次生成）
                logger.info(f"模块数{len(modules)}个，不分批，一次性生成")

                # 不限制用例数量，由LLM根据文档内容自行决定
                # 使用LLM配置的max_tokens作为输出上限（留足空间）
                dynamic_max_tokens = max_tokens_limit
                logger.info(f"max_tokens：{dynamic_max_tokens}（交由LLM自行决定用例数量）")
                
                # 构建提示词
                modules_list = self._format_modules_list(modules)
                
                # 根据LLM配置动态计算输入上限
                max_input_chars, _ = _calc_limits(dynamic_max_tokens)
                truncated_content = requirement_doc_content
                if len(requirement_doc_content) > max_input_chars:
                    truncated_content = self._extract_key_content(requirement_doc_content, modules, max_input_chars)
                    logger.info(f"需求文档过长({len(requirement_doc_content)}字符)，截断到{len(truncated_content)}字符(上限{max_input_chars})")
                else:
                    logger.info(f"需求文档长度: {len(requirement_doc_content)}字符，在LLM输入上限{max_input_chars}内")
                
                # 使用SKILL模板构建提示词
                if (skill_dict and isinstance(skill_dict, dict) and skill_dict.get("prompt_template")):
                    prompt_template = skill_dict.get("prompt_template")
                    
                    if isinstance(prompt_template, dict):
                        system_prompt = prompt_template.get("system_prompt", "")
                        
                        user_prompt_template = prompt_template.get("user_prompt", "")
                        user_prompt = user_prompt_template.replace("{{project_name}}", project_name)
                        user_prompt = user_prompt.replace("{{version_number}}", version_number)
                        user_prompt = user_prompt.replace("{{requirement_content}}", truncated_content)
                        user_prompt = user_prompt.replace("{{modules_list}}", modules_list)
                        user_prompt = user_prompt.replace("{{estimated_cases}}", str(estimated_cases))
                        logger.info(f"使用SKILL模板提示词，变量替换完成")
                    else:
                        system_prompt = self._build_system_prompt(skill_dict)
                        user_prompt = self._build_user_prompt(project_name, version_number, truncated_content, modules)
                else:
                    system_prompt = self._build_system_prompt(skill_dict)
                    user_prompt = self._build_user_prompt(project_name, version_number, truncated_content, modules)
                
                logger.info(f"提示词长度：system={len(system_prompt)}, user={len(user_prompt)}")
                
                # 调用LLM生成（强制JSON模式）
                logger.info("开始调用 LLM API (json_mode=True)...")
                llm_response = await self.llm_service.async_call_llm(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=0.3,
                    max_tokens=dynamic_max_tokens,
                    json_mode=True,
                )
                
                if not llm_response:
                    logger.error("LLM 调用失败：返回为空")
                    return {"success": False, "error": "LLM 调用失败"}
                
                logger.info(f"LLM 响应长度：{len(llm_response)} 字符")
                
                # 4. 解析 LLM 响应
                logger.info("开始解析 LLM 响应...")
                parsed_result = self._parse_llm_response(llm_response)
                
                if not parsed_result:
                    logger.error("LLM 响应解析失败")
                    return {"success": False, "error": "LLM 响应解析失败"}
                
                logger.info(f"解析成功，测试用例数量：{len(parsed_result.get('test_cases', []))}")
            
            # 5. 保存测试用例到数据库（分批生成或单次生成共用）
            logger.info("开始保存测试用例...")
            test_cases_count = await self._save_test_cases(
                version_id,
                parsed_result.get("test_cases", [])
            )
            logger.info(f"保存测试用例完成：{test_cases_count} 个")
            
            # 6. 生成 XMind 思维导图（OPML 格式）—— 可跳过
            xmind_count = 0
            if not skip_xmind:
                logger.info("开始生成 XMind 思维导图...")
                xmind_content = self._generate_xmind_opml(
                    parsed_result.get("test_cases", []),
                    parsed_result.get("test_summary", {})
                )
                xmind_count = await self._save_xmind(
                    version_id,
                    xmind_content,
                    parsed_result.get("test_cases", []),
                    parsed_result.get("test_summary", {})
                )
                logger.info(f"保存思维导图完成：{xmind_count} 个")
            else:
                logger.info("跳过 XMind 思维导图生成")
            
            logger.info(
                f"[{project_name} v{version_number}] 测试资产生成完成：{test_cases_count} 个测试用例，{xmind_count} 个思维导图"
            )
            
            return {
                "success": True,
                "test_cases_count": test_cases_count,
                "xmind_count": xmind_count,
                "analysis_summary": parsed_result.get("analysis_summary", {})
            }
            
        except Exception as e:
            logger.error(f"[{project_name} v{version_number}] 生成测试资产失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _build_prompts_from_skill(
        self,
        skill_content: Optional[Dict[str, Any]],
        project_name: str,
        version_number: str,
        requirement_content: str,
        modules: List[str] = None,
        estimated_cases_per_module: int = 5
    ) -> tuple:
        """从 SKILL 模板构建系统提示词和用户提示词
        
        Args:
            skill_content: SKILL内容字典
            project_name: 项目名称
            version_number: 版本号
            requirement_content: 需求文档内容
            modules: 已识别的模块列表（避免重复识别）
            estimated_cases_per_module: 每模块预估用例数（统一为5）
        """
        # 如果未提供模块，才识别（但通常应该传入已识别的模块）
        if modules is None:
            modules = self._extract_modules_from_requirement(requirement_content)
        
        # 统一预估数量（每模块5个）
        estimated_cases = len(modules) * estimated_cases_per_module
        
        if skill_content and skill_content.get("prompt_template"):
            prompt_template = skill_content.get("prompt_template")
            
            # 如果是字符串格式（旧版），使用默认方法
            if isinstance(prompt_template, str):
                system_prompt = self._build_system_prompt(skill_content)
                user_prompt = self._build_user_prompt(project_name, version_number, requirement_content, modules)
                return system_prompt, user_prompt
            
            # 如果是对象格式（新版），使用模板变量替换
            if isinstance(prompt_template, dict):
                system_prompt = prompt_template.get("system_prompt", "")
                
                modules_list = self._format_modules_list(modules)
                
                # 大文档优化：截断需求内容（保留关键部分）
                max_doc_length = 20000
                truncated_content = requirement_content
                if len(requirement_content) > max_doc_length:
                    truncated_content = self._extract_key_content(requirement_content, modules, max_doc_length)
                    logger.info(f"需求文档过长({len(requirement_content)}字符)，已截断为{len(truncated_content)}字符")
                
                # 变量替换
                user_prompt_template = prompt_template.get("user_prompt", "")
                user_prompt = user_prompt_template.replace("{{project_name}}", project_name)
                user_prompt = user_prompt.replace("{{version_number}}", version_number)
                user_prompt = user_prompt.replace("{{requirement_content}}", truncated_content)
                user_prompt = user_prompt.replace("{{modules_list}}", modules_list)
                user_prompt = user_prompt.replace("{{estimated_cases}}", str(estimated_cases))
                
                logger.info(f"使用 SKILL 模板提示词，模块数：{len(modules)}，预估用例：{estimated_cases}")
                return system_prompt, user_prompt
        
        # 使用默认方法
        system_prompt = self._build_system_prompt(skill_content)
        user_prompt = self._build_user_prompt(project_name, version_number, requirement_content, modules)
        return system_prompt, user_prompt
    
    def _extract_key_content(self, content: str, modules: List[str], max_length: int) -> str:
        """从大文档中提取关键内容
        
        提取策略：
        1. 保留文档开头（项目信息）
        2. 保留每个模块的标题和功能清单表格
        3. 保留重要的业务规则
        """
        import re
        
        lines = content.split('\n')
        result_lines = []
        current_length = 0
        
        # 1. 保留开头100行（文档信息、目录等）
        for i, line in enumerate(lines[:100]):
            result_lines.append(line)
            current_length += len(line) + 1
        
        # 2. 提取每个模块的关键部分（标题+功能清单表格）
        for module in modules[:20]:  # 最多处理20个模块
            # 找到模块标题位置
            module_pattern = re.escape(module)
            for i, line in enumerate(lines):
                if re.search(module_pattern, line) and i not in result_lines:
                    # 从模块标题开始，保留接下来的50行（功能清单表格）
                    start = max(0, i - 2)  # 包含标题前2行
                    end = min(len(lines), i + 50)
                    for j in range(start, end):
                        if j not in [len(result_lines) + k for k in range(end - start)]:
                            if current_length + len(lines[j]) + 1 < max_length:
                                result_lines.append(lines[j])
                                current_length += len(lines[j]) + 1
                    break
        
        # 3. 如果还有空间，添加业务规则部分
        if current_length < max_length * 0.8:
            for i, line in enumerate(lines):
                if '业务规则' in line or '业务逻辑' in line or '核心业务' in line:
                    start = max(0, i)
                    end = min(len(lines), i + 30)
                    for j in range(start, end):
                        if current_length + len(lines[j]) + 1 < max_length:
                            if lines[j] not in result_lines:
                                result_lines.append(lines[j])
                                current_length += len(lines[j]) + 1
                    break
        
        return '\n'.join(result_lines)
    
    def _extract_batch_content(self, content: str, batch_modules: List[str], max_length: int) -> str:
        """提取批次相关的需求内容
        
        Args:
            content: 需求文档完整内容
            batch_modules: 当前批次的模块列表
            max_length: 最大长度限制
        
        Returns:
            当前批次模块相关的需求内容
        """
        import re
        
        lines = content.split('\n')
        result_lines = []
        current_length = 0
        
        # 保留开头50行（文档信息）
        for i in range(min(50, len(lines))):
            result_lines.append(lines[i])
            current_length += len(lines[i]) + 1
        
        # 提取当前批次模块的内容
        for module in batch_modules:
            module_pattern = re.escape(module)
            for i, line in enumerate(lines):
                if re.search(module_pattern, line):
                    start = max(0, i)
                    end = min(len(lines), i + 100)  # 每个模块保留100行
                    for j in range(start, end):
                        if current_length + len(lines[j]) + 1 < max_length:
                            if lines[j] not in result_lines:
                                result_lines.append(lines[j])
                                current_length += len(lines[j]) + 1
                    break
        
        return '\n'.join(result_lines)
    
    def _build_system_prompt(self, skill_content: Optional[Dict[str, Any]]) -> str:
        """构建系统提示词，充分利用 SKILL 模板的完整内容"""
        if skill_content:
            role = skill_content.get("role", {})
            role_name = role.get("name", "功能测试用例生成专家")
            role_desc = role.get("description", "")
            expertise = role.get("expertise", [])
            behavior_rules = role.get("behavior_rules", [])
            
            methods = skill_content.get("methods", [])
            methods_text = self._format_methods(methods)
            
            domain_rules = skill_content.get("domain_rules", [])
            domain_text = self._format_domain_rules(domain_rules)
            
            quality_checks = skill_content.get("quality_checks", [])
            quality_text = "\n".join(["- " + q for q in quality_checks])
            
            expertise_text = "\n".join(["- " + e for e in expertise])
            behavior_text = "\n".join(["- " + r for r in behavior_rules])
            
            system_prompt = self._build_full_system_prompt(
                role_name, role_desc, expertise_text, behavior_text,
                methods_text, domain_text, quality_text
            )
            
            return system_prompt
        else:
            return self._build_default_system_prompt()
    
    def _format_methods(self, methods: List[Dict]) -> str:
        """格式化测试方法库"""
        lines = []
        for m in methods:
            name = m.get("name", "")
            desc = m.get("description", "")
            scenarios = m.get("applicable_scenarios", [])
            
            line = f"【{name}】{desc}"
            if scenarios:
                line += f"\n适用场景：{', '.join(scenarios)}"
            lines.append(line)
        return "\n".join(lines)
    
    def _format_domain_rules(self, domain_rules: List[Dict]) -> str:
        """格式化领域规则"""
        lines = []
        for rule in domain_rules:
            domain = rule.get("domain", "")
            must_test = rule.get("must_test", [])
            security = rule.get("security_focus", [])
            
            line = f"【{domain}】"
            if must_test:
                line += f"\n必须测试：{', '.join(must_test)}"
            if security:
                line += f"\n安全关注：{', '.join(security)}"
            lines.append(line)
        return "\n".join(lines)
    
    def _build_full_system_prompt(
        self, role_name: str, role_desc: str, expertise: str,
        behavior: str, methods: str, domain: str, quality: str
    ) -> str:
        """构建完整的系统提示词"""
        json_example = '''
{
  "test_cases": [
    {
      "id": "TC001",
      "title": "用例标题",
      "module": "所属模块",
      "sub_module": "子模块",
      "priority": "P0/P1/P2/P3",
      "test_type": "positive/negative/boundary/exception",
      "preconditions": ["前置条件1", "前置条件2"],
      "test_steps": [
        {"step_no": 1, "action": "操作描述", "expected_result": "预期结果"}
      ],
      "test_data": {},
      "tags": ["标签1"],
      "automation_level": "high/medium/low"
    }
  ],
  "test_summary": {
    "total_count": 100,
    "p0_count": 10,
    "p1_count": 30,
    "p2_count": 40,
    "p3_count": 20,
    "coverage_analysis": "覆盖率分析",
    "risk_areas": ["风险点"]
  }
}
'''
        
        return f"""# 角色设定

你是一位资深的【{role_name}】。

{role_desc}

## 专业知识领域
{expertise}

## 行为准则
{behavior}

---

# 测试方法库

请根据需求特点，灵活运用以下测试方法：

{methods}

---

# 领域规则

{domain}

---

# 质量检查规则

生成用例时必须满足以下要求：
{quality}

---

# 输出格式要求

请严格按照 JSON 格式输出：
```json
{json_example}
```

---

# 核心要求

1. **每个功能模块生成充分的测试用例（正常场景、异常场景、边界场景）**
2. **每个用例必须包含完整的测试步骤和预期结果**
3. **覆盖所有功能点，确保测试覆盖率**
4. **标注合理的优先级（P0核心功能，P1重要功能，P2一般功能，P3次要功能）**
5. **测试数据必须具体、有效、符合业务逻辑**

请开始生成测试用例。"""
    
    def _build_default_system_prompt(self) -> str:
        """构建默认系统提示词"""
        return """# 角色设定

你是一位资深的功能测试用例生成专家，拥有10年以上测试经验。擅长从需求文档中提取测试点，设计高覆盖率的测试用例。

## 核心要求

1. **每个功能模块至少生成5-10个测试用例**
2. **每个用例必须包含完整的测试步骤和预期结果**
3. **覆盖正常场景、异常场景、边界场景**
4. **标注合理的优先级（P0核心功能，P1重要功能，P2一般功能，P3次要功能）**
5. **测试数据必须具体、有效、符合业务逻辑**

---

# 测试方法

- 等价类划分法：划分有效和无效输入
- 边界值分析法：测试边界值及附近值
- 场景法：基于业务流程设计测试场景
- 状态迁移法：测试系统状态转换
- 错误推测法：基于经验推测可能缺陷

---

# 输出格式

请以JSON格式输出，包含test_cases数组和test_summary对象。"""
    
    def _build_user_prompt(
        self,
        project_name: str,
        version_number: str,
        requirement_content: str,
        modules: Optional[List[str]] = None
    ) -> str:
        """构建用户提示词，包含模块分解和用例数量引导
        
        注意：使用字符串拼接而非 f-string，避免需求文档中的花括号导致格式化错误
        """
        
        if modules is None:
            modules = self._extract_modules_from_requirement(requirement_content) or []
        modules_text = self._format_modules_list(modules)
        estimated_cases = len(modules) * 8
        
        prompt_parts = [
            "# 项目信息\n",
            f"- **项目名称**: {project_name}\n",
            f"- **版本号**: {version_number}\n",
            "\n---\n\n",
            "# 需求文档内容\n\n",
            requirement_content,
            "\n\n---\n\n",
            "# 功能模块列表（已识别）\n\n",
            "根据需求文档分析，识别出以下功能模块：\n\n",
            modules_text,
            "\n\n---\n\n",
            "# 用例生成要求\n\n",
            "## 1. 模块覆盖要求\n\n",
            "请为**每个模块**单独生成测试用例，确保覆盖所有功能点。\n\n",
            f"**用例数量估算**: 预计生成约 {estimated_cases} 个测试用例（每个模块约 8 个）。\n\n",
            "## 2. 每个模块的用例要求\n\n",
            "对于每个模块，请生成以下类型的用例：\n\n",
            "- **正常场景用例（2-3个）**: 验证功能正常运行\n",
            "- **异常场景用例（2-3个）**: 验证错误处理和异常情况\n",
            "- **边界场景用例（2-3个）**: 验证边界值和极限情况\n\n",
            "## 3. 用例字段要求\n\n",
            "每个测试用例必须包含以下字段：\n\n",
            "| 字段 | 说明 | 示例 |\n",
            "|------|------|------|\n",
            "| id | 用例编号 | TC001 |\n",
            "| title | 用例标题（简洁明了） | 验证用户登录-正常登录 |\n",
            "| module | 所属模块 | 用户管理模块 |\n",
            "| priority | 优先级 | P0/P1/P2/P3 |\n",
            "| test_type | 测试类型 | positive/negative/boundary |\n",
            "| preconditions | 前置条件列表 | ['用户已注册', '系统运行正常'] |\n",
            "| test_steps | 测试步骤（每步含action和expected_result） | [{'step_no':1,'action':'点击登录','expected_result':'显示登录页'}] |\n",
            "| expected_result | **整体预期结果**（整个用例完成后的最终结果） | 用户成功登录系统，进入首页 |\n",
            "| tags | 标签 | ['登录', '功能测试'] |\n\n",
            "**重要：expected_result是整体预期结果，与test_steps中每步的expected_result不同！**\n",
            "- test_steps中的expected_result：每个步骤完成后的即时结果\n",
            "- 顶层的expected_result：整个测试用例执行完成后的最终结果\n",
            "- 两者不应重复！\n\n",
            "## 4. 优先级分配原则\n\n",
            "- **P0**: 核心功能、关键业务流程\n",
            "- **P1**: 重要功能、主要业务场景\n",
            "- **P2**: 一般功能、常规场景\n",
            "- **P3**: 次要功能、边缘场景\n\n",
            "## 5. 特别关注\n\n",
            "请特别关注以下内容：\n\n",
            "- 业务规则和约束条件\n",
            "- 数据验证规则\n",
            "- 状态流转逻辑\n",
            "- 权限控制\n",
            "- 安全性要求\n",
            "- 异常处理机制\n\n",
            "---\n\n",
            "# 输出要求\n\n",
            "请输出 JSON 格式，结构如下：\n\n",
            '{"test_cases": [{"id": "TC001", "title": "验证用户登录-正常登录", "module": "用户管理", "priority": "P0", "test_type": "positive", "preconditions": ["用户已注册"], "test_steps": [{"step_no": 1, "action": "输入用户名", "expected_result": "输入成功"}, {"step_no": 2, "action": "点击登录", "expected_result": "登录成功"}], "expected_result": "用户成功登录系统，进入首页", "tags": ["登录"]}], "test_summary": {"total_count": 100}}\n\n',
            "**请开始生成完整的测试用例列表，确保每个模块都有充分的覆盖。**",
        ]
        
        return "".join(prompt_parts)
    
    def _extract_modules_from_requirement(self, requirement_content: str) -> List[str]:
        """从需求文档中提取一级功能模块（支持多种格式）
        
        支持格式：
        1. Markdown标题（## 开头）
        2. Word/PDF解析后的纯文本标题（中文编号、数字编号）
        3. 功能清单表格
        4. 关键词模式（常见功能名称）
        """
        import re
        
        modules = []
        
        # 过滤关键词列表
        skip_keywords = [
            '概述', '背景', '简介', '附录', '目录', '说明',
            '规则', '字典', '术语', '前言', '文档', '版本',
            '修订', '变更', '范围', '目的', '总体', '引言',
            '编写', '审核', '审批', '发布', '修订记录', '变更记录'
        ]
        
        # 策略1: Markdown二级标题（### 开头）- 优先识别具体功能模块
        # 使用负向先行断言确保###后面不是#（排除####标题）
        md_level2_patterns = [
            r'^(###)(?!\#)\s*\d+[、.]\d+[、.]*\s*([^\n]+)',  # ### 2.1 登录功能（X.Y格式）
            r'^(###)(?!\#)\s*[一二三四五六七八九十]+[、.]\d+[、.]*\s*([^\n]+)',  # ### 一.1 登录功能
        ]
        
        for pattern in md_level2_patterns:
            matches = re.findall(pattern, requirement_content, re.MULTILINE)
            for match in matches:
                # match是元组 (###, 标题内容)，取第二个元素
                module_name = match[1] if isinstance(match, tuple) else match
                module_name = module_name.strip()
                # 排除以#开头的结果（错误匹配）
                if module_name.startswith('#'):
                    continue
                # 清理编号前缀
                module_name = re.sub(r'^\d+[、.]*\d*[、.]*\s*', '', module_name)
                module_name = re.sub(r'^[一二三四五六七八九十]+[、.]*\d*[、.]*\s*', '', module_name)
                module_name = module_name.strip()
                if module_name and len(module_name) > 2:
                    # 只保留包含功能关键词的标题（确保是功能模块而非子节）
                    functional_keywords = ['功能', '模块', '接口', '管理', '系统', '组件', '服务']
                    if any(fk in module_name for fk in functional_keywords):
                        if not any(kw in module_name for kw in skip_keywords):
                            if module_name not in modules:
                                modules.append(module_name)
                                logger.info(f"从###标题识别功能模块: {module_name}")
        
        # 策略2: Markdown一级标题（## 开头）- 仅在未识别到二级模块时使用
        if not modules:
            md_level1_patterns = [
                r'^##\s+[一二三四五六七八九十]+[、.]\s*([^\n]+)',  # ## 一、登录功能
                r'^##\s+\d+[、.]\s*([^\n]+)',  # ## 2. 功能需求
                r'^##\s+([^\n]+)',  # ## 登录功能（确保##后面不是#）
            ]
            
            for pattern in md_level1_patterns:
                matches = re.findall(pattern, requirement_content, re.MULTILINE)
                for match in matches:
                    module_name = match.strip()
                    if module_name and len(module_name) > 3:
                        if not any(kw in module_name for kw in skip_keywords):
                            if module_name not in modules:
                                modules.append(module_name)
        
        # 策略2: 纯文本标题（Word/PDF解析后，无Markdown格式）
        # 中文编号：一、登录功能
        chinese_num_pattern = r'[一二三四五六七八九十百]+[、.]\s*([^\n]{3,30})'
        chinese_matches = re.findall(chinese_num_pattern, requirement_content)
        for match in chinese_matches:
            module_name = match.strip()
            # 过滤非功能标题
            if module_name and len(module_name) > 3:
                if not any(kw in module_name for kw in skip_keywords):
                    # 检查是否包含常见功能关键词
                    functional_keywords = ['功能', '管理', '测试', '接口', '配置', '设置', '查询', '操作', '模块', '页面', '系统']
                    if any(fk in module_name for fk in functional_keywords) or len(module_name) > 5:
                        if module_name not in modules:
                            modules.append(module_name)
        
        # 策略3: 数字编号标题（1. 登录功能）
        digit_pattern = r'\d+[、.]\s*([^\n]{3,30})'
        digit_matches = re.findall(digit_pattern, requirement_content)
        for match in digit_matches:
            module_name = match.strip()
            if module_name and len(module_name) > 3:
                if not any(kw in module_name for kw in skip_keywords):
                    functional_keywords = ['功能', '管理', '测试', '接口', '配置', '设置', '查询', '操作', '模块', '页面', '系统']
                    if any(fk in module_name for fk in functional_keywords) or len(module_name) > 5:
                        if module_name not in modules:
                            modules.append(module_name)
        
        # 策略4: 从表格提取（功能模块列）
        if not modules:
            table_patterns = [
                r'\|\s*功能模块\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*模块名称\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*模块\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*功能\s*\|\s*([^\|]+)\s*\|',
                r'\|\s*功能名称\s*\|\s*([^\|]+)\s*\|',
            ]
            
            for pattern in table_patterns:
                matches = re.findall(pattern, requirement_content)
                for match in matches:
                    module_name = match.strip()
                    if module_name and len(module_name) > 2:
                        if not any(kw in module_name for kw in ['功能模块', '模块名称']):
                            if module_name not in modules:
                                modules.append(module_name)
        
        # 策略5: 关键词模式（常见功能名称）
        if not modules:
            keyword_patterns = [
                r'(RAG知识库管理|SKILL管理|功能测试|API接口测试|WEB UI测试|测试报告管理|测试管理|项目管理|用户管理|权限管理|配置管理|数据管理|登录管理|注册管理)',
                r'(?:功能|模块|管理)[:：]\s*([^\n，。]{3,30})',
            ]
            
            for pattern in keyword_patterns:
                matches = re.findall(pattern, requirement_content)
                for match in matches:
                    module_name = match.strip()
                    if module_name and len(module_name) >= 3:
                        if not any(kw in module_name for kw in skip_keywords):
                            if module_name not in modules:
                                modules.append(module_name)
        
        # 策略6: 如果还是识别不到，尝试识别段落标题（换行后的独立行）
        if not modules:
            lines = requirement_content.split('\n')
            for line in lines[:50]:  # 只检查前50行
                line = line.strip()
                # 检查是否是标题行（不以小写字母开头，长度3-30，不含特殊符号）
                if line and len(line) >= 3 and len(line) <= 30:
                    # 排除包含特殊符号的行
                    if not any(sym in line for sym in ['|', '*', '-', '=', '#', '>', '<', '【', '】', '[', ']']):
                        # 排除纯数字或纯英文单词
                        if not re.match(r'^[\d\s]+$|^[\w\s]+$', line):
                            # 检查是否包含功能关键词
                            functional_keywords = ['功能', '管理', '测试', '接口', '配置', '设置', '查询', '操作', '模块', '页面', '系统']
                            if any(fk in line for fk in functional_keywords):
                                if not any(kw in line for kw in skip_keywords):
                                    if line not in modules:
                                        modules.append(line)
        
        # 策略7: 如果所有策略都失败，返回默认值
        if not modules:
            modules = ["核心功能模块"]
            logger.warning("未能识别功能模块，使用默认值")
        
        # 清理和去重
        cleaned_modules = []
        for m in modules:
            # 去除编号前缀
            clean_name = re.sub(r'^[一二三四五六七八九十百\d]+[、.]\s*', '', m)
            clean_name = re.sub(r'[【\[].*?[】\]]', '', clean_name)
            clean_name = clean_name.strip()
            
            # 去除"功能"、"模块"后缀并去重
            base_name = clean_name.replace('功能', '').replace('模块', '').strip()
            existing_base_names = [
                x.replace('功能', '').replace('模块', '').strip()
                for x in cleaned_modules
            ]
            
            if base_name and base_name not in existing_base_names:
                cleaned_modules.append(clean_name if len(clean_name) > 3 else m)
        
        # 限制模块数量（最多20个）
        if len(cleaned_modules) > 20:
            logger.info(f"模块过多（{len(cleaned_modules)}个），限制为前20个")
            cleaned_modules = cleaned_modules[:20]
        
        logger.info(f"模块识别完成：识别到{len(cleaned_modules)}个一级模块")
        return cleaned_modules
    
    def _format_modules_list(self, modules: Optional[List[str]]) -> str:
        """格式化模块列表"""
        import re
        if not modules:
            return "（未能识别具体模块，请根据需求文档自行分析）"

        lines = []
        for i, module in enumerate(modules, 1):
            # 去掉 emoji 和特殊符号，保留中文和字母
            clean = re.sub(r'[^\w一-鿿\s]', '', module).strip()
            lines.append(f"{i}. **{clean}**")
        
        lines.append("")
        lines.append(f"总计识别到 **{len(modules)}** 个功能模块")
        
        return "\n".join(lines)
    
    def _parse_llm_response(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 响应"""
        try:
            import re
            import json
            
            # 尝试 1: 提取 JSON 代码块
            json_match = None
            pattern = r'```json\s*(.*?)\s*```'
            match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
            
            if match:
                json_str = match.group(1)
                logger.info(f"从 JSON 代码块中提取内容，长度：{len(json_str)}")
            else:
                # 尝试 2: 提取任何花括号包围的内容
                pattern = r'\{.*\}'
                match = re.search(pattern, llm_response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    logger.info(f"从文本中提取 JSON 内容，长度：{len(json_str)}")
                else:
                    # 尝试 3: 直接使用整个响应
                    json_str = llm_response.strip()
                    logger.info(f"使用整个响应作为 JSON，长度：{len(json_str)}")
            
            # 清理 JSON 字符串
            json_str = json_str.strip()
            
            # 尝试解析
            try:
                parsed = json.loads(json_str)
                logger.info("JSON 解析成功")
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败：{e}，尝试修复...")
                
                # 记录响应内容以便调试
                debug_file_path = f"./logs/llm_response_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                try:
                    import os
                    os.makedirs("./logs", exist_ok=True)
                    with open(debug_file_path, 'w', encoding='utf-8') as f:
                        f.write(f"=== LLM Response Debug ===\n")
                        f.write(f"Error: {e}\n")
                        f.write(f"Response Length: {len(llm_response)}\n")
                        f.write(f"JSON String Length: {len(json_str)}\n")
                        f.write(f"\n=== First 5000 chars of JSON ===\n")
                        f.write(json_str[:5000])
                        f.write(f"\n\n=== Last 500 chars of JSON ===\n")
                        f.write(json_str[-500:])
                    logger.info(f"LLM响应已保存到: {debug_file_path}")
                except Exception as save_err:
                    logger.warning(f"保存LLM响应失败: {save_err}")
                
                # 多种修复策略
                fix_strategies = [
                    # 策略1: 移除末尾逗号
                    lambda s: re.sub(r',(\s*[}\]])', r'\1', s),
                    # 策略2: 替换单引号为双引号
                    lambda s: s.replace("'", '"'),
                    # 策略3: 修复键名引号
                    lambda s: re.sub(r'(["\']?)\s*(\w+)\s*(["\']?)\s*:', r'"\2":', s),
                    # 策略4: 移除控制字符
                    lambda s: re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s),
                    # 策略5: 修复未闭合的数组/对象
                    lambda s: self._fix_unclosed_json(s),
                    # 策略6: 移除注释
                    lambda s: re.sub(r'//.*?\n|/\*.*?\*/', '', s, flags=re.DOTALL),
                    # 策略7: 修复多余的空格和换行
                    lambda s: re.sub(r'\s+', ' ', s),
                ]
                
                for i, fix_func in enumerate(fix_strategies):
                    try:
                        fixed_str = fix_func(json_str)
                        parsed = json.loads(fixed_str)
                        logger.info(f"JSON 修复策略{i+1}成功")
                        return parsed
                    except Exception:
                        continue
                
                logger.error(f"所有JSON修复策略失败")
                
                # 最后尝试：从响应中提取测试用例信息
                logger.info("尝试从文本中提取测试用例...")
                return self._extract_test_cases_from_text(llm_response)
        
        except Exception as e:
            logger.error(f"解析 LLM 响应失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _fix_unclosed_json(self, json_str: str) -> str:
        """修复未闭合的JSON"""
        try:
            # 1. 先修复截断的字符串（未闭合的引号）
            # 检测最后是否是未闭合的字符串
            last_quote_pos = json_str.rfind('"')
            if last_quote_pos > 0:
                # 检查从该位置到末尾是否有闭合引号
                after_last_quote = json_str[last_quote_pos + 1:]
                next_quote_pos = after_last_quote.find('"')
                if next_quote_pos == -1 and len(after_last_quote.strip()) > 0:
                    # 可能是截断的字符串，尝试闭合它
                    # 找到字符串值的开始位置
                    # 简单策略：在截断处添加闭合引号并截断后续内容
                    truncated_pos = json_str.rfind('"expected_result":')
                    if truncated_pos > 0:
                        # 截断到expected_result字段，闭合整个对象
                        json_str = json_str[:truncated_pos]
                        logger.warning(f"JSON截断，已截断到expected_result字段前")
            
            # 2. 修复未闭合的花括号和方括号
            open_braces = json_str.count('{') - json_str.count('}')
            open_brackets = json_str.count('[') - json_str.count(']')
            
            if open_braces > 0:
                json_str += '}' * open_braces
            if open_brackets > 0:
                json_str += ']' * open_brackets
            
            # 3. 确保test_cases数组有闭合
            if 'test_cases' in json_str and not json_str.rstrip().endswith('}'):
                # 添加test_summary对象闭合
                if 'test_summary' not in json_str:
                    json_str += ', "test_summary": {"total_count": 0}'
            
            return json_str
        except Exception as e:
            logger.warning(f"JSON修复失败: {e}")
            return json_str
    
    def _extract_test_cases_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取测试用例信息（备用方案）"""
        try:
            import re
            
            test_cases = []
            
            # 尝试提取类似测试用例的结构
            # 匹配模式：数字。标题 或 数字、标题
            patterns = [
                r'(\d+)[\.、]\s*([^\n]+)',
                r'测试用例 [:-]\s*([^\n]+)',
                r'用例 [:-]\s*([^\n]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        title = match[1]
                    elif isinstance(match, tuple) and len(match) >= 1:
                        title = match[0]
                    elif isinstance(match, str):
                        title = match
                    else:
                        continue
                    
                    if title and len(title.strip()) > 5:
                        test_cases.append({
                            "title": title.strip(),
                            "module": "通用模块",
                            "description": "",
                            "priority": "P2",
                            "preconditions": "",
                            "test_steps": [title.strip()],
                            "expected_results": "操作成功"
                        })
            
            if test_cases:
                logger.info(f"从文本中提取到 {len(test_cases)} 个测试用例")
                return {
                    "test_cases": test_cases[:20],  # 限制最多 20 个
                    "analysis_summary": {
                        "total_count": len(test_cases),
                        "p0_count": 0,
                        "coverage_analysis": "基于文本提取",
                        "risk_points": []
                    }
                }
            
            return None
        except Exception as e:
            logger.error(f"从文本中提取测试用例失败：{e}")
            return None
    
    def _extract_partial_cases_from_response(self, llm_response: str) -> Optional[List[Dict[str, Any]]]:
        """从截断的LLM响应中提取已生成的部分测试用例
        
        当JSON解析失败时，尝试从响应中提取已生成的测试用例（即使JSON不完整）
        
        Args:
            llm_response: LLM返回的原始响应
            
        Returns:
            提取到的测试用例列表，或None
        """
        try:
            import re
            import json
            
            test_cases = []
            
            # 策略1：提取完整的测试用例对象（即使JSON整体不完整）
            # 匹配模式：{ "id": "TC001", ... }
            case_pattern = r'\{\s*"id":\s*"TC\d+"\s*,.*?\}'
            matches = re.findall(case_pattern, llm_response, re.DOTALL)
            
            for match in matches:
                case_str = match.strip()  # 先定义，避免未绑定错误
                try:
                    # 尝试解析单个测试用例对象
                    
                    # 确保对象闭合
                    if not case_str.endswith('}'):
                        case_str += '}'
                    
                    # 尝试修复常见错误
                    case_str = re.sub(r',(\s*})', r'}', case_str)  # 移除末尾逗号
                    
                    case = json.loads(case_str)
                    if case and case.get("title"):
                        test_cases.append(case)
                        logger.info(f"提取到部分用例: {case.get('title')[:30]}")
                except json.JSONDecodeError:
                    # 尝试修复并重新解析
                    try:
                        # 策略2：截断到最后一个完整字段
                        if '"expected_result"' in case_str:
                            # 截断到expected_result字段
                            truncated = case_str[:case_str.rfind('"expected_result"')]
                            # 闭合JSON
                            truncated = truncated.rstrip(',')
                            truncated += '}'
                            
                            # 尝试再次解析
                            case = json.loads(truncated)
                            if case and case.get("title"):
                                test_cases.append(case)
                                logger.info(f"修复后提取到部分用例: {case.get('title')[:30]}")
                    except Exception:
                        continue
            
            # 策略3：如果还是提取不到，使用正则提取关键字段
            if not test_cases:
                logger.info("尝试正则提取关键字段...")
                
                # 提取所有用例ID和标题
                id_title_pattern = r'"id":\s*"TC(\d+)"\s*,\s*"title":\s*"([^"]+)"'
                id_title_matches = re.findall(id_title_pattern, llm_response)
                
                for tc_id, title in id_title_matches:
                    # 提取module字段
                    module_pattern = '"id":\\s*"TC' + str(tc_id) + '"[^}]*"module":\\s*"([^"]+)"'
                    module_match = re.search(module_pattern, llm_response)
                    module = module_match.group(1) if module_match else "通用模块"
                    
                    # 提取priority字段
                    priority_pattern = '"id":\\s*"TC' + str(tc_id) + '"[^}]*"priority":\\s*"([^"]+)"'
                    priority_match = re.search(priority_pattern, llm_response)
                    priority = priority_match.group(1) if priority_match else "P2"
                    
                    # 构造基础测试用例
                    test_cases.append({
                        "id": f"TC{tc_id}",
                        "title": title,
                        "module": module,
                        "priority": priority,
                        "test_type": "positive",
                        "preconditions": [],
                        "test_steps": [],
                        "expected_result": "功能正常运行",
                        "tags": []
                    })
                    logger.info(f"正则提取到用例: {title[:30]}")
            
            if test_cases:
                logger.info(f"共提取到 {len(test_cases)} 条部分测试用例")
                return test_cases
            
            logger.warning("未能提取到任何部分测试用例")
            return None
            
        except Exception as e:
            logger.error(f"提取部分测试用例失败：{e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _save_test_cases(
        self,
        version_id: int,
        test_cases: List[Dict[str, Any]]
    ) -> int:
        """保存测试用例到数据库"""
        count = 0
        
        from app.core.models.project import Version

        version = self.db.query(Version).filter(Version.id == version_id).first()
        if not version:
            logger.error(f"版本 ID {version_id} 不存在")
            return 0
        
        project_id = version.project_id
        logger.info(f"保存测试用例到项目 {project_id}, 版本 {version_id}")

        # 获取当前版本已有用例的最大 sort_order
        from app.core.models.requirement import TestCase as TC
        max_order = self.db.query(TC).filter(TC.version_id == version_id).count() * 10
        base_order = max_order + 10  # 从现有用例之后以10间隔递增

        for idx, tc_data in enumerate(test_cases):
            try:
                priority_map = {
                    "P0": TestCasePriority.P0.value,
                    "P1": TestCasePriority.P1.value,
                    "P2": TestCasePriority.P2.value,
                    "P3": TestCasePriority.P3.value,
                }
                
                # 字段提取
                tc_name = tc_data.get("title") or tc_data.get("name") or "未命名用例"
                tc_module = tc_data.get("module") or "通用模块"
                tc_module = clean_module_name(tc_module)  # 清洗逗号/BIZ标签
                tc_description = tc_data.get("description") or ""
                tc_priority = tc_data.get("priority") or "P2"

                # 前置条件
                tc_preconditions = tc_data.get("preconditions") or ""
                if isinstance(tc_preconditions, list):
                    tc_preconditions_text = "\n".join([str(p) for p in tc_preconditions if p])
                else:
                    tc_preconditions_text = str(tc_preconditions) if tc_preconditions else ""

                # 测试步骤
                tc_test_steps = tc_data.get("test_steps") or []
                processed_steps = self._process_test_steps(tc_test_steps)
                
                # 预期结果：兼容多种字段名，过滤无效值
                tc_expected_result = (tc_data.get("expected_result") or tc_data.get("expected_results") or
                                     tc_data.get("expected") or tc_data.get("预期结果") or "")
                if tc_expected_result in ("测试通过", "功能正常", "操作成功", "功能正常运行"):
                    tc_expected_result = ""
                
                # 如果没有顶层预期结果，从步骤中汇总
                if not tc_expected_result and tc_test_steps:
                    expected_list = []
                    for step in tc_test_steps:
                        if isinstance(step, dict):
                            step_expected = step.get("expected_result") or step.get("expected") or ""
                            if step_expected:
                                expected_list.append(f"{step.get('step_no', step.get('step', len(expected_list)+1))}. {step_expected}")
                    if expected_list:
                        tc_expected_result = "\n".join(expected_list)
                
                # ---- 质量兜底：自动修复，不阻塞 ----
                # 1. 前置条件为空 → 根据模块自动补
                if not tc_preconditions_text or tc_preconditions_text.strip() in ("", "无", "暂无"):
                    tc_preconditions_text = f"已登录系统并进入{tc_module}页面"
                    logger.info(f"  自动补充前置条件: {tc_preconditions_text}")
                # 2. 预期结果无效 → 从最后一步expected_result取
                bad_exp = ("测试通过", "功能正常", "操作成功", "功能正常运行")
                if not tc_expected_result or tc_expected_result.strip() in bad_exp:
                    if processed_steps:
                        last = processed_steps[-1]
                        tc_expected_result = last.get("expected", "") or last.get("expected_result", "")
                        if not tc_expected_result or tc_expected_result.strip() in bad_exp:
                            tc_expected_result = f"{tc_name}操作完成，页面正常响应"
                    else:
                        tc_expected_result = f"{tc_name}操作完成，页面正常响应"
                    logger.info(f"  自动补充预期结果")
                # 3. 步骤不足 → 记录但不阻塞
                if not processed_steps or len(processed_steps) < 2:
                    logger.warning(f"  步骤不足({len(processed_steps)}步)，仍入库")

                logger.info(f"处理测试用例：{tc_name[:50]}")
                
                # 以10为间隔自动分配执行顺序
                auto_sort_order = base_order + (idx * 10)

                test_case = RequirementTestCase(
                    project_id=project_id,
                    version_id=version_id,
                    name=tc_name,
                    module=tc_module,
                    description=tc_description,
                    priority=priority_map.get(tc_priority, TestCasePriority.P2.value),
                    status=TestCaseStatus.APPROVED.value,
                    preconditions=tc_preconditions_text,
                    test_steps=processed_steps,
                    expected_result=str(tc_expected_result),
                    tags=tc_data.get("tags", []),
                    sort_order=auto_sort_order,
                    generated_by="ai",
                    created_by=1
                )
                
                self.db.add(test_case)
                count += 1
                
            except Exception as e:
                logger.error(f"保存测试用例失败：{str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        self.db.commit()
        return count
    
    def _process_test_steps(self, test_steps: List[Any]) -> List[Dict[str, Any]]:
        """处理测试步骤，统一为 [{step, action, expected}] 格式

        LLM 返回的格式可能是：
        - [{"step_no": 1, "action": "...", "expected_result": "..."}]
        - [{"step": 1, "action": "...", "expected": "..."}]
        - ["步骤1: 操作...", "步骤2: 操作..."]

        统一输出：每步保留 step/action/expected 三个字段
        """
        if not test_steps:
            return []

        processed = []
        for i, step in enumerate(test_steps, 1):
            if isinstance(step, dict):
                action = step.get("action", "") or step.get("desc", "")
                expected = step.get("expected_result") or step.get("expected") or step.get("expect", "")
                processed.append({
                    "step": i,
                    "action": action,
                    "expected": expected,
                })
            elif isinstance(step, str):
                # 纯文本步骤：尝试拆分 "操作 → 预期"
                if "→" in step:
                    parts = step.split("→", 1)
                    processed.append({
                        "step": i,
                        "action": parts[0].strip(),
                        "expected": parts[1].strip(),
                    })
                else:
                    processed.append({
                        "step": i,
                        "action": step,
                        "expected": "",
                    })
            else:
                processed.append(str(step))
        
        return processed
    
    def _generate_xmind_opml(
        self,
        test_cases: List[Dict[str, Any]],
        analysis_summary: Dict[str, Any]
    ) -> str:
        """生成 XMind OPML 格式内容"""
        # 按模块分组
        modules: Dict[str, List[Dict]] = {}
        for tc in test_cases:
            module = tc.get("module", "通用模块")
            if module not in modules:
                modules[module] = []
            modules[module].append(tc)
        
        # 构建 OPML 结构
        opml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<opml version="2.0">',
            '  <head>',
            f'    <title>测试思维导图 - {analysis_summary.get("title", "功能测试")}</title>',
            '  </head>',
            '  <body>',
            '    <outline text="测试大纲">'
        ]
        
        # 添加模块和测试用例
        for module_name, cases in modules.items():
            opml_lines.append(f'      <outline text="{module_name}">')
            for case in cases:
                opml_lines.append(
                    f'        <outline text="{case.get("title", "未命名")}"/>'
                )
            opml_lines.append('      </outline>')
        
        opml_lines.extend([
            '    </outline>',
            '  </body>',
            '</opml>'
        ])
        
        return '\n'.join(opml_lines)
    
    async def _save_xmind(
        self,
        version_id: int,
        opml_content: str,
        test_cases: List[Dict[str, Any]],
        analysis_summary: Dict[str, Any] = None
    ) -> int:
        """保存 XMind 思维导图"""
        try:
            xmind = TestPointMap(
                version_id=version_id,
                name=f"功能测试思维导图",
                content={"opml": opml_content},
                module_count=len(set(
                    tc.get("module", "通用模块") 
                    for tc in test_cases
                )),
                test_point_count=len(test_cases),
                generated_by="ai",
                created_by=1  # TODO: 使用当前用户 ID
            )
            
            self.db.add(xmind)
            self.db.commit()
            
            return 1
        except Exception as e:
            logger.error(f"保存思维导图失败：{str(e)}")
            self.db.rollback()
            return 0

