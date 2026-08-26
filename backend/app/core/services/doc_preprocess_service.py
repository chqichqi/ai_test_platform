"""
文档预处理服务 - 使用 LLM 智能分析需求文档，生成标准格式
"""

import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.services.llm_service import LLMService


DOC_ANALYSIS_SYSTEM_PROMPT = """你是一个专业的需求分析专家。你的任务是将需求文档转换为标准的功能模块格式，便于后续生成详细的测试用例。

## 输入说明
你将收到一份需求文档的原始内容（可能是 Word、PDF、Markdown 或纯文本）。

## 输出要求
请输出 JSON 格式的功能模块列表，包含以下字段：
- document_title: 文档标题
- modules: 功能模块列表，每个模块包含：
  - name: 模块名称（简短，不超过10个字）
  - description: 模块描述（一句话）
  - features: 子功能列表，每个功能包含：
    - name: 功能名称
    - description: 功能描述（一句话）
    - inputs: 输入字段列表（如：用户名、密码、邮箱）
    - outputs: 输出/预期结果（如：登录成功、显示首页）
    - rules: 业务规则列表（如：密码长度6-20位）
    - edge_cases: 边界条件列表（如：密码为空、密码超长）
  - priority: 模块优先级（P0/P1/P2/P3）

## 分析规则
1. 识别文档中的所有功能模块
2. 每个功能必须包含：
   - 具体的输入字段（不要笼统）
   - 具体的预期结果（不要笼统）
   - 具体的业务规则（如长度限制、格式要求）
   - 具体的边界条件（最小值、最大值、空值）
3. 根据业务重要性判断优先级
4. 过滤非功能性内容

## 示例输出
```json
{
  "document_title": "用户管理系统",
  "modules": [
    {
      "name": "用户注册",
      "description": "新用户注册账号功能",
      "features": [
        {
          "name": "填写注册信息",
          "description": "用户输入注册信息并提交",
          "inputs": ["用户名", "密码", "邮箱", "手机号"],
          "outputs": ["注册成功提示", "跳转到登录页"],
          "rules": ["用户名长度3-20字符", "密码长度6-20字符", "邮箱格式验证", "手机号11位"],
          "edge_cases": ["用户名为空", "用户名超长", "密码为空", "邮箱格式错误"]
        },
        {
          "name": "验证邮箱",
          "description": "发送并验证邮箱验证码",
          "inputs": ["验证码"],
          "outputs": ["邮箱验证成功", "账号激活"],
          "rules": ["验证码6位数字", "验证码有效期5分钟"],
          "edge_cases": ["验证码为空", "验证码错误", "验证码过期"]
        }
      ],
      "priority": "P0"
    }
  ]
}
```

请只输出 JSON，不要输出其他内容。"""


DOC_ANALYSIS_USER_PROMPT = """请分析以下需求文档，提取功能模块并输出标准格式的 JSON。

---
文档内容：
{content}
---

请输出 JSON 格式的功能模块列表。"""


class DocumentPreprocessService:
    """文档预处理服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
    
    async def analyze_document(
        self, 
        content: str, 
        document_type: str = "unknown"
    ) -> Dict[str, Any]:
        """
        使用 LLM 分析文档内容，生成标准功能模块格式
        
        Args:
            content: 文档原始内容
            document_type: 文档类型（docx/pdf/md/txt）
        
        Returns:
            分析结果，包含：
            - success: 是否成功
            - document_title: 文档标题
            - modules: 功能模块列表
            - markdown_content: 转换后的 Markdown 内容
            - raw_response: LLM 原始响应
        """
        # 截断过长内容
        max_length = 15000
        if len(content) > max_length:
            content = content[:max_length]
            logger.info(f"文档内容过长，截断为 {max_length} 字符")
        
        logger.info(f"开始 LLM 文档分析，类型: {document_type}, 内容长度: {len(content)}")
        
        # 获取LLM配置的max_tokens
        llm_config = self.llm_service.get_active_config()
        config_max_tokens = llm_config.max_tokens if llm_config else 4000
        # 文档分析需要较大输出空间，取配置值的30%
        analysis_max_tokens = min(int(config_max_tokens * 0.3), 8000)
        logger.info(f"文档分析max_tokens: 配置值{config_max_tokens}, 实际使用{analysis_max_tokens}")
        
        try:
            # 调用 LLM 分析
            response = await self.llm_service.async_call_llm(
                prompt=DOC_ANALYSIS_USER_PROMPT.format(content=content),
                system_prompt=DOC_ANALYSIS_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=analysis_max_tokens
            )
            
            if not response:
                logger.error("LLM 文档分析返回为空")
                return {"success": False, "error": "LLM 调用失败"}
            
            logger.info(f"LLM 响应长度: {len(response)}")
            
            # 解析 JSON
            result = self._parse_llm_response(response)
            
            if result and "modules" in result:
                # 生成标准 Markdown 格式
                markdown_content = self._generate_markdown(result)
                
                logger.info(f"文档分析成功: 标题={result.get('document_title')}, 模块数={len(result.get('modules', []))}")
                
                # 统计功能点数量（兼容两种格式）
                total_features = 0
                for m in result.get("modules", []):
                    m_features = m.get("features", [])
                    if m_features:
                        # 如果是对象数组，每个对象是一个功能
                        # 如果是字符串数组，每个字符串是一个功能
                        total_features += len(m_features)
                
                return {
                    "success": True,
                    "document_title": result.get("document_title", "需求文档"),
                    "modules": result.get("modules", []),
                    "markdown_content": markdown_content,
                    "raw_response": response,
                    "stats": {
                        "total_modules": len(result.get("modules", [])),
                        "p0_count": sum(1 for m in result.get("modules", []) if m.get("priority") == "P0"),
                        "p1_count": sum(1 for m in result.get("modules", []) if m.get("priority") == "P1"),
                        "total_features": total_features
                    }
                }
            else:
                logger.error(f"LLM 响应解析失败: {response[:500]}")
                return {"success": False, "error": "JSON 解析失败", "raw_response": response}
                
        except Exception as e:
            logger.error(f"文档分析异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        """解析 LLM 响应，提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(response)
        except:
            pass
        
        # 尝试提取 JSON 块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass
        
        # 尝试查找 JSON 对象
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(response[start:end+1])
            except:
                pass
        
        return None
    
    def _generate_markdown(self, result: Dict) -> str:
        """根据分析结果生成标准 Markdown 格式（包含详细功能描述）"""
        lines = []
        
        # 文档标题
        title = result.get("document_title", "需求文档")
        lines.append(f"# {title}")
        lines.append("")
        
        # 功能模块
        for module in result.get("modules", []):
            name = module.get("name", "")
            description = module.get("description", "")
            priority = module.get("priority", "P2")
            features = module.get("features", [])
            
            # 模块标题
            lines.append(f"## {name}")
            lines.append(f"> 描述：{description} | 优先级：{priority}")
            lines.append("")
            
            # 子功能（详细格式）
            if features:
                lines.append("**子功能：**")
                lines.append("")
                
                for feature in features:
                    # 兼容两种格式：详细对象格式和简单字符串格式
                    if isinstance(feature, dict):
                        f_name = feature.get("name", "")
                        f_desc = feature.get("description", "")
                        f_inputs = feature.get("inputs", [])
                        f_outputs = feature.get("outputs", [])
                        f_rules = feature.get("rules", [])
                        f_edge_cases = feature.get("edge_cases", [])
                        
                        lines.append(f"### {f_name}")
                        lines.append(f"- 功能描述：{f_desc}")
                        
                        if f_inputs:
                            lines.append(f"- 输入字段：{', '.join(f_inputs)}")
                        if f_outputs:
                            lines.append(f"- 预期结果：{', '.join(f_outputs)}")
                        if f_rules:
                            lines.append(f"- 业务规则：")
                            for rule in f_rules:
                                lines.append(f"  - {rule}")
                        if f_edge_cases:
                            lines.append(f"- 边界条件：")
                            for edge in f_edge_cases:
                                lines.append(f"  - {edge}")
                        
                        lines.append("")
                    elif isinstance(feature, str):
                        # 简单字符串格式
                        lines.append(f"- {feature}")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def quick_extract_modules(self, content: str) -> List[str]:
        """快速提取模块列表（不调用 LLM，用于预览或 fallback）
        
        Returns:
            模块名称列表
        """
        modules = []
        
        # Markdown 二级标题
        md_matches = re.findall(r'##\s*[一二三四五六七八九十\d]+[、.．]?\s*([^\n]+)', content)
        for m in md_matches:
            name = m.strip()
            if name and len(name) > 2 and name not in modules:
                modules.append(name)
        
        # 纯中文编号
        if not modules:
            chinese_matches = re.findall(r'[一二三四五六七八九十]+[、.．]\s*([^\n]{3,20})', content)
            for m in chinese_matches:
                name = m.strip()
                if name and '功能' in name or '管理' in name or '模块' in name:
                    if name not in modules:
                        modules.append(name)
        
        return modules[:20]  # 最多20个模块