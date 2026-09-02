"""
失败分析Agent
基于LangChain实现智能化失败分析，支持：
1. 失败类型识别
2. 根本原因分析
3. 自动修复建议生成
4. 相似失败查找
"""

from typing import Dict, Any, List
import json
import re

from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate

from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger
from app.core.models.issue import (
    FailureAnalysis, Issue, FailureType, RootCauseCategory,
    IssueSeverity, IssuePriority, IssueStatus
)


class FailureAnalysisAgent(BaseAgent):
    """
    失败分析Agent
    
    核心功能：
    1. 分析测试失败信息（失败消息、堆栈、DOM快照等）
    2. 识别失败类型（元素定位失败、断言失败、超时等）
    3. 分析根本原因（UI变更、环境问题、业务逻辑等）
    4. 生成修复建议和自动修复方案
    5. 查找相似失败记录
    """
    
    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "FailureAnalysisAgent")
        
        self.create_agent()
    
    def define_tools(self) -> List[Tool]:
        """定义失败分析工具集"""
        
        return [
            Tool(
                name="analyze_failure_info",
                func=self._analyze_failure,
                description="分析失败信息，识别失败类型和根本原因"
            ),
            Tool(
                name="identify_failure_type",
                func=self._identify_type,
                description="识别失败类型（元素定位失败、断言失败等）"
            ),
            Tool(
                name="analyze_root_cause",
                func=self._analyze_cause,
                description="分析根本原因（UI变更、环境问题等）"
            ),
            Tool(
                name="generate_fix_suggestion",
                func=self._generate_fix,
                description="生成修复建议和自动修复方案"
            ),
            Tool(
                name="find_similar_failures",
                func=self._find_similar,
                description="查找相似的失败记录"
            ),
            Tool(
                name="create_issue_from_analysis",
                func=self._create_issue,
                description="根据分析结果创建Issue记录"
            ),
            Tool(
                name="check_auto_fix_availability",
                func=self._check_auto_fix,
                description="检查是否可自动修复（自愈机制）"
            )
        ]
    
    def build_prompt(self) -> ChatPromptTemplate:
        """构建Agent提示词"""
        
        template = """
你是专业的自动化测试失败分析专家。

任务目标：深度分析测试失败，提供修复方案

执行策略：
1. 使用 analyze_failure_info 综合分析失败信息
2. 使用 identify_failure_type 识别失败类型
3. 使用 analyze_root_cause 分析根本原因
4. 使用 generate_fix_suggestion 生成修复建议
5. 使用 find_similar_failures 查找相似失败
6. 如果可以自动修复，使用 check_auto_fix_availability 检查
7. 使用 create_issue_from_analysis 创建Issue记录

重要规则：
- 失败类型识别要准确（element_not_found、assertion_failed等）
- 根本原因分析要深入（UI变更、环境问题、数据问题等）
- 修复建议要具体可执行
- 自动修复需满足条件：元素定位失败 + UI变更 + 能找到替代定位器
- 相似失败查找要基于失败消息和堆栈特征
- Issue创建要包含完整的分析结果

输出格式：
JSON对象，包含：
{
  "failure_type": "元素定位失败",
  "root_cause": "UI变更",
  "analysis": "详细分析...",
  "suggestion": "修复建议...",
  "auto_fix_available": true,
  "similar_failures": [
    {"id": 123, "failure_message": "..."}
  ],
  "issue_id": 456
}

输入：
{input}

可用工具：
{tools}

思考过程：
{agent_scratchpad}

请严格按照策略执行，确保提供准确的失败分析和可行的修复方案。
"""
        
        return ChatPromptTemplate.from_template(template)
    
    # === 工具实现 ===
    
    def _analyze_failure(self, failure_info_json: str) -> str:
        """
        综合分析失败信息
        
        Args:
            failure_info_json: 失败信息JSON字符串
        
        Returns:
            分析结果JSON字符串
        """
        logger.info(f"[Tool] 综合分析失败信息")
        
        try:
            failure_info = json.loads(failure_info_json)
            
            failure_message = failure_info.get('failure_message', '')
            stack_trace = failure_info.get('stack_trace', '')
            dom_snapshot = failure_info.get('dom_snapshot', '')
            console_logs = failure_info.get('console_logs', '')
            network_logs = failure_info.get('network_logs', '')
            
            # 调用LLM进行深度分析
            analysis_prompt = f"""
你是一个专业的自动化测试失败分析专家。请分析以下测试失败信息。

## 失败信息

**失败消息**:
{failure_message}

**堆栈跟踪**:
{stack_trace[:1000] if stack_trace else '无'}

**DOM快照** (如果有):
{dom_snapshot[:500] if dom_snapshot else '无'}

**控制台日志** (如果有):
{console_logs[:500] if console_logs else '无'}

请以JSON格式返回分析结果：
{
  "failure_type": "失败类型（element_not_found/assertion_failed/timeout/network_error等）",
  "root_cause": "根本原因（ui_changed/environment/business_logic等）",
  "analysis": "详细分析内容",
  "confidence": 置信度(0-100),
  "suggestion": "修复建议"
}

只返回JSON对象。
"""
            
            from langchain.schema import HumanMessage, SystemMessage
            
            messages = [HumanMessage(content=analysis_prompt)]
            response = self.llm.invoke(messages)
            content = response.content
            
            # 解析JSON
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            # 提取对象部分
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
            
            analysis_result = json.loads(json_str)
            
            logger.info(f"[Tool] 失败分析完成：{analysis_result.get('failure_type', 'unknown')}")
            
            return json.dumps(analysis_result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 失败分析失败: {str(e)}")
            # 返回默认分析
            default_analysis = {
                'failure_type': 'unknown',
                'root_cause': 'unknown',
                'analysis': '无法自动分析失败原因',
                'confidence': 0,
                'suggestion': '请人工检查失败日志'
            }
            return json.dumps(default_analysis, ensure_ascii=False)
    
    def _identify_type(self, failure_message: str) -> str:
        """
        识别失败类型
        
        Args:
            failure_message: 失败消息
        
        Returns:
            失败类型字符串
        """
        logger.info(f"[Tool] 识别失败类型")
        
        # 简化的失败类型识别（基于关键词）
        failure_type = 'unknown'
        
        if 'element not found' in failure_message.lower() or 'no such element' in failure_message.lower():
            failure_type = 'element_not_found'
        elif 'assertion failed' in failure_message.lower() or 'expected' in failure_message.lower():
            failure_type = 'assertion_failed'
        elif 'timeout' in failure_message.lower() or 'timed out' in failure_message.lower():
            failure_type = 'timeout'
        elif 'network error' in failure_message.lower() or 'connection refused' in failure_message.lower():
            failure_type = 'network_error'
        elif 'environment' in failure_message.lower() or 'config' in failure_message.lower():
            failure_type = 'environment_error'
        elif 'data' in failure_message.lower() or 'null' in failure_message.lower():
            failure_type = 'data_error'
        elif 'bug' in failure_message.lower() or 'error' in failure_message.lower():
            failure_type = 'business_bug'
        elif 'script' in failure_message.lower() or 'syntax' in failure_message.lower():
            failure_type = 'script_error'
        
        logger.info(f"[Tool] 失败类型识别完成：{failure_type}")
        
        return failure_type
    
    def _analyze_cause(self, failure_type: str) -> str:
        """
        分析根本原因
        
        Args:
            failure_type: 失败类型
        
        Returns:
            根本原因字符串
        """
        logger.info(f"[Tool] 分析根本原因")
        
        # 根据失败类型推断根本原因
        cause_mapping = {
            'element_not_found': 'ui_changed',
            'assertion_failed': 'business_logic',
            'timeout': 'infrastructure',
            'network_error': 'third_party',
            'environment_error': 'environment',
            'data_error': 'data_issue',
            'business_bug': 'business_logic',
            'script_error': 'test_script',
            'unknown': 'unknown'
        }
        
        root_cause = cause_mapping.get(failure_type, 'unknown')
        
        logger.info(f"[Tool] 根本原因分析完成：{root_cause}")
        
        return root_cause
    
    def _generate_fix(self, analysis_json: str) -> str:
        """
        生成修复建议
        
        Args:
            analysis_json: 分析结果JSON字符串
        
        Returns:
            修复建议字符串
        """
        logger.info(f"[Tool] 生成修复建议")
        
        try:
            analysis = json.loads(analysis_json)
            
            failure_type = analysis.get('failure_type', 'unknown')
            root_cause = analysis.get('root_cause', 'unknown')
            
            # 根据失败类型和根本原因生成修复建议
            fix_suggestions = {
                'element_not_found': """
修复建议：
1. 检查页面是否加载完成，增加等待时间
2. 使用智能定位器尝试多种定位策略（XPath、CSS、ID等）
3. 检查元素是否因UI变更而移除或修改
4. 如果元素被移除，考虑修改测试逻辑或跳过此步骤
""",
                'assertion_failed': """
修复建议：
1. 检查预期值是否正确，可能与业务逻辑变更有关
2. 检查实际值获取方式是否正确
3. 考虑增加容错逻辑或调整预期值
""",
                'timeout': """
修复建议：
1. 增加超时等待时间
2. 检查网络连接是否稳定
3. 检查页面加载性能，可能需要优化前端代码
""",
                'network_error': """
修复建议：
1. 检查网络连接和服务器状态
2. 检查API接口是否可用
3. 检查防火墙和代理配置
""",
                'environment_error': """
修复建议：
1. 检查测试环境配置是否正确
2. 检查浏览器版本和驱动版本
3. 检查环境变量和依赖项
"""
            }
            
            suggestion = fix_suggestions.get(failure_type, '请人工检查失败原因并修复')
            
            logger.info(f"[Tool] 修复建议生成完成")
            
            return suggestion
            
        except Exception as e:
            logger.error(f"[Tool] 修复建议生成失败: {str(e)}")
            return '请人工检查失败原因并修复'
    
    def _find_similar(self, failure_message: str) -> str:
        """
        查找相似失败
        
        Args:
            failure_message: 失败消息
        
        Returns:
            相似失败列表JSON字符串
        """
        logger.info(f"[Tool] 查找相似失败")
        
        try:
            # 从数据库查找相似的失败记录
            similar_failures = self.db.query(FailureAnalysis).filter(
                FailureAnalysis.failure_message.ilike(f'%{failure_message[:50]}%')
            ).limit(5).all()
            
            results = []
            for failure in similar_failures:
                results.append({
                    'id': failure.id,
                    'failure_message': failure.failure_message[:100],
                    'failure_type': failure.failure_type,
                    'root_cause': failure.root_cause,
                    'created_at': failure.created_at.isoformat() if failure.created_at else None
                })
            
            logger.info(f"[Tool] 相似失败查找完成，数量={len(results)}")
            
            return json.dumps(results, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 相似失败查找失败: {str(e)}")
            return json.dumps([], ensure_ascii=False)
    
    def _create_issue(self, analysis_json: str) -> str:
        """
        根据分析结果创建Issue
        
        Args:
            analysis_json: 分析结果JSON字符串
        
        Returns:
            Issue ID字符串
        """
        logger.info(f"[Tool] 创建Issue记录")
        
        try:
            analysis = json.loads(analysis_json)
            
            # 创建Issue记录
            issue = Issue(
                title=f"[失败分析] {analysis.get('failure_type', 'unknown')}",
                description=analysis.get('analysis', ''),
                severity=IssueSeverity.MEDIUM,
                priority=IssuePriority.P2,
                status=IssueStatus.OPEN,
                failure_type=FailureType(analysis.get('failure_type', 'unknown')),
                root_cause=RootCauseCategory(analysis.get('root_cause', 'unknown'))
            )
            
            self.db.add(issue)
            self.db.commit()
            self.db.refresh(issue)
            
            logger.info(f"[Tool] Issue创建完成，ID={issue.id}")
            
            return str(issue.id)
            
        except Exception as e:
            logger.error(f"[Tool] Issue创建失败: {str(e)}")
            return '0'
    
    def _check_auto_fix(self, analysis_json: str) -> str:
        """
        检查是否可自动修复
        
        Args:
            analysis_json: 分析结果JSON字符串
        
        Returns:
            是否可自动修复字符串（true/false）
        """
        logger.info(f"[Tool] 检查自动修复可用性")
        
        try:
            analysis = json.loads(analysis_json)
            
            failure_type = analysis.get('failure_type', 'unknown')
            root_cause = analysis.get('root_cause', 'unknown')
            
            # 自动修复条件：元素定位失败 + UI变更
            can_auto_fix = (
                failure_type == 'element_not_found' and
                root_cause == 'ui_changed'
            )
            
            logger.info(f"[Tool] 自动修复检查完成：{can_auto_fix}")
            
            return 'true' if can_auto_fix else 'false'
            
        except Exception as e:
            logger.error(f"[Tool] 自动修复检查失败: {str(e)}")
            return 'false'