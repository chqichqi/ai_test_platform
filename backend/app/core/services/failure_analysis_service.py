"""
AI失败分析服务
集成LLM进行智能失败原因分析
"""

import json
import re
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.core.services.llm_service import LLMService
from app.core.models.issue import (
    FailureAnalysis, Issue, FailureType, RootCauseCategory,
    IssueSeverity, IssuePriority, IssueStatus
)
from app.core.logger import logger


FAILURE_ANALYSIS_PROMPT = """你是一个专业的自动化测试失败分析专家。请分析以下测试失败信息，并提供详细的分析结果。

## 失败信息

**失败消息**:
{failure_message}

**堆栈跟踪**:
{stack_trace}

**DOM快照** (如果有):
{dom_snapshot}

**控制台日志** (如果有):
{console_logs}

**网络日志** (如果有):
{network_logs}

## 分析要求

请进行以下分析：

1. **失败类型识别**: 判断失败的类型
   - element_not_found: 元素定位失败
   - assertion_failed: 断言失败
   - timeout: 超时
   - network_error: 网络错误
   - environment_error: 环境配置问题
   - data_error: 数据问题
   - business_bug: 业务逻辑Bug
   - script_error: 测试脚本错误
   - unknown: 无法确定

2. **根本原因分析**: 判断根本原因类别
   - ui_changed: UI界面变化
   - environment: 环境问题
   - business_logic: 业务逻辑变更
   - data_issue: 测试数据问题
   - test_script: 测试脚本问题
   - infrastructure: 基础设施问题
   - third_party: 第三方服务问题
   - unknown: 未知原因

3. **详细分析**: 提供失败原因的详细分析

4. **修复建议**: 提供具体的修复步骤和建议

5. **影响范围**: 评估此失败可能影响的其他测试用例或定位器

6. **是否可自动修复**: 判断是否可以通过自愈机制自动修复

请以JSON格式返回分析结果：

```json
{
  "failure_type": "失败类型",
  "root_cause": "根本原因类别",
  "analysis": "详细分析内容（Markdown格式）",
  "confidence": 置信度(0-100的整数),
  "suggestion": "修复建议（Markdown格式）",
  "auto_fix_available": true或false,
  "affected_locators": ["受影响的定位器列表"],
  "affected_cases": ["可能受影响的用例描述"],
  "severity_recommendation": "建议的严重程度(critical/high/medium/low)",
  "priority_recommendation": "建议的优先级(P0/P1/P2/P3)"
}
```

只返回JSON对象，不要添加其他内容。"""


class FailureAnalysisService:
    """AI失败分析服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
    
    def analyze_failure_with_llm(
        self,
        failure_message: str,
        stack_trace: Optional[str] = None,
        dom_snapshot: Optional[str] = None,
        console_logs: Optional[List[str]] = None,
        network_logs: Optional[List[Dict]] = None,
        case_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        使用LLM进行智能失败分析
        
        Args:
            failure_message: 失败消息
            stack_trace: 堆栈跟踪
            dom_snapshot: DOM快照
            console_logs: 控制台日志
            network_logs: 网络日志
            case_info: 测试用例信息
        
        Returns:
            分析结果字典
        """
        console_logs_str = ""
        if console_logs:
            console_logs_str = "\n".join(console_logs[:20])
        
        network_logs_str = ""
        if network_logs:
            network_logs_str = json.dumps(network_logs[:10], indent=2, ensure_ascii=False)
        
        dom_str = dom_snapshot[:5000] if dom_snapshot else "无DOM快照"
        
        prompt = FAILURE_ANALYSIS_PROMPT.format(
            failure_message=failure_message or "无失败消息",
            stack_trace=stack_trace[:3000] if stack_trace else "无堆栈信息",
            dom_snapshot=dom_str,
            console_logs=console_logs_str or "无控制台日志",
            network_logs=network_logs_str or "无网络日志"
        )
        
        if case_info:
            prompt += f"\n\n## 测试用例信息\n{json.dumps(case_info, indent=2, ensure_ascii=False)}"
        
        # 获取LLM配置的max_tokens
        llm_config = self.llm_service.get_active_config()
        config_max_tokens = llm_config.max_tokens if llm_config else 4000
        # 失败分析需要较小输出空间，取配置值的15%
        analysis_max_tokens = min(int(config_max_tokens * 0.15), 3000)
        logger.info(f"失败分析max_tokens: 配置值{config_max_tokens}, 实际使用{analysis_max_tokens}")
        
        result = self.llm_service.call_llm_json(
            prompt=prompt,
            system_prompt="你是一个专业的自动化测试失败分析专家，专注于提供准确、实用的失败分析和修复建议。",
            temperature=0.3,
            max_tokens=analysis_max_tokens
        )
        
        if result and isinstance(result, dict):
            validated_result = self._validate_analysis_result(result)
            logger.info(f"LLM分析完成: type={validated_result['failure_type']}, confidence={validated_result['confidence']}")
            return validated_result
        
        logger.warning("LLM分析失败，使用规则引擎备选方案")
        return self._rule_based_analysis(failure_message, stack_trace)
    
    def _validate_analysis_result(self, result: Dict) -> Dict[str, Any]:
        """验证和规范化分析结果"""
        valid_failure_types = [ft.value for ft in FailureType]
        valid_root_causes = [rc.value for rc in RootCauseCategory]
        valid_severities = [s.value for s in IssueSeverity]
        valid_priorities = [p.value for p in IssuePriority]
        
        failure_type = result.get('failure_type', 'unknown')
        if failure_type not in valid_failure_types:
            failure_type = 'unknown'
        
        root_cause = result.get('root_cause', 'unknown')
        if root_cause not in valid_root_causes:
            root_cause = 'unknown'
        
        confidence = result.get('confidence', 50)
        if not isinstance(confidence, int) or confidence < 0 or confidence > 100:
            confidence = 50
        
        severity = result.get('severity_recommendation', 'medium')
        if severity not in valid_severities:
            severity = 'medium'
        
        priority = result.get('priority_recommendation', 'P2')
        if priority not in valid_priorities:
            priority = 'P2'
        
        return {
            'failure_type': failure_type,
            'root_cause': root_cause,
            'analysis': result.get('analysis', '未能生成详细分析'),
            'confidence': confidence,
            'suggestion': result.get('suggestion', '请检查测试日志获取更多信息'),
            'auto_fix_available': bool(result.get('auto_fix_available', False)),
            'affected_locators': result.get('affected_locators', []),
            'affected_cases': result.get('affected_cases', []),
            'severity_recommendation': severity,
            'priority_recommendation': priority
        }
    
    def _rule_based_analysis(self, failure_message: str, stack_trace: Optional[str]) -> Dict[str, Any]:
        """基于规则的失败分析（备选方案）"""
        result = {
            'failure_type': FailureType.UNKNOWN.value,
            'root_cause': RootCauseCategory.UNKNOWN.value,
            'analysis': '',
            'confidence': 50,
            'suggestion': '',
            'auto_fix_available': False,
            'affected_locators': [],
            'affected_cases': [],
            'severity_recommendation': IssueSeverity.MEDIUM.value,
            'priority_recommendation': IssuePriority.P2.value
        }
        
        combined = f"{failure_message}\n{stack_trace or ''}".lower()
        
        if any(kw in combined for kw in ['element not found', 'no such element', 'unable to locate', 'selector']):
            result['failure_type'] = FailureType.ELEMENT_NOT_FOUND.value
            result['root_cause'] = RootCauseCategory.UI_CHANGED.value
            result['analysis'] = self._analyze_element_not_found(failure_message, stack_trace)
            result['suggestion'] = self._suggest_element_fix()
            result['auto_fix_available'] = True
            result['confidence'] = 85
            result['severity_recommendation'] = IssueSeverity.MEDIUM.value
        
        elif any(kw in combined for kw in ['assertion', 'assert', 'expect', 'should']):
            result['failure_type'] = FailureType.ASSERTION_FAILED.value
            result['root_cause'] = RootCauseCategory.BUSINESS_LOGIC.value
            result['analysis'] = self._analyze_assertion_failure(failure_message, stack_trace)
            result['suggestion'] = self._suggest_assertion_fix()
            result['confidence'] = 75
            result['severity_recommendation'] = IssueSeverity.HIGH.value
        
        elif any(kw in combined for kw in ['timeout', 'timed out', 'timeoutexception']):
            result['failure_type'] = FailureType.TIMEOUT.value
            result['root_cause'] = RootCauseCategory.ENVIRONMENT.value
            result['analysis'] = "页面加载或元素等待超时。可能原因：网络延迟、页面资源加载慢、页面重定向过多。"
            result['suggestion'] = "建议：增加超时时间、检查网络连接、优化页面加载性能。"
            result['confidence'] = 80
            result['severity_recommendation'] = IssueSeverity.LOW.value
        
        elif any(kw in combined for kw in ['network', 'connection', 'econnrefused', 'socket']):
            result['failure_type'] = FailureType.NETWORK_ERROR.value
            result['root_cause'] = RootCauseCategory.INFRASTRUCTURE.value
            result['analysis'] = "网络连接失败。可能原因：服务不可用、DNS解析失败、防火墙阻止。"
            result['suggestion'] = "建议：检查服务器状态、验证网络配置、检查防火墙规则。"
            result['confidence'] = 90
            result['severity_recommendation'] = IssueSeverity.HIGH.value
        
        elif any(kw in combined for kw in ['environment', 'config', 'env', 'variable']):
            result['failure_type'] = FailureType.ENVIRONMENT_ERROR.value
            result['root_cause'] = RootCauseCategory.ENVIRONMENT.value
            result['analysis'] = "环境配置问题。可能原因：环境变量缺失、配置文件错误、服务未启动。"
            result['suggestion'] = "建议：检查环境配置、验证服务状态、检查配置文件。"
            result['confidence'] = 85
            result['severity_recommendation'] = IssueSeverity.HIGH.value
        
        elif any(kw in combined for kw in ['data', 'null', 'undefined', 'empty']):
            result['failure_type'] = FailureType.DATA_ERROR.value
            result['root_cause'] = RootCauseCategory.DATA_ISSUE.value
            result['analysis'] = "测试数据问题。可能原因：数据缺失、数据格式错误、数据不一致。"
            result['suggestion'] = "建议：检查测试数据、验证数据源、准备正确的测试数据。"
            result['confidence'] = 75
            result['severity_recommendation'] = IssueSeverity.MEDIUM.value
        
        return result
    
    def _analyze_element_not_found(self, failure_message: str, stack_trace: Optional[str]) -> str:
        """分析元素定位失败"""
        locator_match = re.search(r'locator[:\s]+["\']([^"\']+)["\']', failure_message or '', re.IGNORECASE)
        locator_info = locator_match.group(1) if locator_match else "未知定位器"
        
        return f"""## 元素定位失败分析

**定位器**: `{locator_info}`

### 可能原因

1. **UI变更**: 页面结构发生变化，元素被移除或属性修改
2. **动态加载**: 元素需要等待或触发特定条件才出现
3. **定位器策略**: 当前定位器策略不够稳定
4. **iframe嵌套**: 元素位于iframe内，未正确切换

### 诊断建议

1. 检查页面最近是否有UI更新
2. 使用开发者工具验证元素是否存在
3. 检查元素是否在iframe中
4. 确认元素是否需要特定操作才可见"""
    
    def _suggest_element_fix(self) -> str:
        """建议元素定位修复方案"""
        return """## 修复建议

### 1. 更新定位器策略

优先使用以下稳定定位器：
- `data-testid` 属性（最推荐）
- `data-*` 自定义属性
- 稳定的 `id` 属性
- 避免使用动态生成的class

### 2. 添加备选定位器

```python
locators = [
    "data-testid=submit-btn",
    "#submit-button",
    "button[type='submit']"
]
```

### 3. 增强等待策略

```python
element = page.wait_for_selector(locator, timeout=30000, state="visible")
```

### 4. 启用自愈机制

系统可以自动尝试相似元素匹配，推荐开启此功能。

### 5. 检查iframe

```python
frame = page.frame_locator("iframe[name='main']")
element = frame.locator(locator)
```"""
    
    def _analyze_assertion_failure(self, failure_message: str, stack_trace: Optional[str]) -> str:
        """分析断言失败"""
        return f"""## 断言失败分析

### 可能原因

1. **业务逻辑变更**: 实际结果与预期不符，可能是业务规则改变
2. **测试数据问题**: 测试数据不满足断言条件
3. **环境差异**: 不同环境的数据或配置不一致
4. **时序问题**: 断言时机不当，页面状态未稳定

### 失败详情

{failure_message[:500] if failure_message else '无详细信息'}

### 诊断建议

1. 检查实际返回值和预期值的具体差异
2. 与开发团队确认业务逻辑是否有变更
3. 验证测试数据是否正确
4. 检查是否需要增加等待时间"""
    
    def _suggest_assertion_fix(self) -> str:
        """建议断言修复方案"""
        return """## 修复建议

### 1. 更新断言条件

根据最新业务逻辑调整预期值：

```python
# 更精确的断言
expect(element).to_have_text("新预期值")
expect(element).to_be_visible(timeout=10000)
```

### 2. 增加断言容错

```python
# 使用正则匹配
expect(element).to_have_text(re.compile(r"预期.*值"))

# 范围断言
assert actual_value >= expected_min
```

### 3. 确认业务变更

与开发团队确认：
- 功能是否已更新
- 预期行为是否已变更
- 是否需要更新测试预期

### 4. 修复测试数据

```python
# 准备正确的测试数据
test_data = {
    "username": "valid_user",
    "status": "active"
}
```"""
    
    def find_similar_issues(
        self,
        failure_type: str,
        project_id: int,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        查找相似的历史问题
        
        Args:
            failure_type: 失败类型
            project_id: 项目ID
            limit: 返回数量
        
        Returns:
            相似问题列表
        """
        similar_issues = self.db.query(Issue).filter(
            Issue.project_id == project_id,
            Issue.failure_type == failure_type,
            Issue.status.in_([
                IssueStatus.RESOLVED.value,
                IssueStatus.CLOSED.value
            ])
        ).order_by(Issue.created_at.desc()).limit(limit).all()
        
        return [
            {
                'id': issue.id,
                'title': issue.title,
                'resolution_note': issue.resolution_note,
                'created_at': issue.created_at.isoformat() if issue.created_at else None,
                'resolved_at': issue.resolved_at.isoformat() if issue.resolved_at else None
            }
            for issue in similar_issues
        ]
    
    def create_issue_from_analysis(
        self,
        analysis: FailureAnalysis,
        reporter_id: int,
        additional_info: Optional[str] = None
    ) -> Issue:
        """
        从分析结果创建问题
        
        Args:
            analysis: 分析记录
            reporter_id: 报告人ID
            additional_info: 补充说明
        
        Returns:
            创建的Issue对象
        """
        description = f"""## AI分析结果

**失败类型**: {analysis.failure_type}
**根本原因**: {analysis.root_cause}
**置信度**: {analysis.confidence}%

### 分析详情
{analysis.ai_analysis}

### 修复建议
{analysis.suggested_fix}

### 受影响范围
- 定位器: {json.dumps(analysis.affected_locators or [], ensure_ascii=False)}
- 用例: {json.dumps(analysis.affected_cases or [], ensure_ascii=False)}
"""
        
        if additional_info:
            description += f"\n### 补充说明\n{additional_info}"
        
        severity = self._get_severity_from_type(analysis.failure_type)
        
        issue = Issue(
            project_id=analysis.project_id,
            execution_id=analysis.execution_id,
            case_id=analysis.case_id,
            title=f"[{analysis.failure_type}] 测试执行失败",
            description=description,
            severity=severity,
            priority=IssuePriority.P2.value,
            failure_type=analysis.failure_type,
            root_cause=analysis.root_cause,
            ai_analysis=analysis.ai_analysis,
            ai_suggestion=analysis.suggested_fix,
            ai_confidence=analysis.confidence,
            reporter_id=reporter_id
        )
        
        self.db.add(issue)
        self.db.commit()
        self.db.refresh(issue)
        
        logger.info(f"创建问题: {issue.title}, ID={issue.id}")
        
        return issue
    
    def _get_severity_from_type(self, failure_type: str) -> str:
        """根据失败类型确定严重程度"""
        severity_map = {
            FailureType.ELEMENT_NOT_FOUND.value: IssueSeverity.MEDIUM.value,
            FailureType.ASSERTION_FAILED.value: IssueSeverity.HIGH.value,
            FailureType.TIMEOUT.value: IssueSeverity.LOW.value,
            FailureType.NETWORK_ERROR.value: IssueSeverity.HIGH.value,
            FailureType.ENVIRONMENT_ERROR.value: IssueSeverity.HIGH.value,
            FailureType.DATA_ERROR.value: IssueSeverity.MEDIUM.value,
            FailureType.BUSINESS_BUG.value: IssueSeverity.CRITICAL.value,
            FailureType.SCRIPT_ERROR.value: IssueSeverity.LOW.value,
        }
        return severity_map.get(failure_type, IssueSeverity.MEDIUM.value)
    
    def get_issue_stats(self, project_id: int) -> Dict[str, Any]:
        """获取问题统计"""
        base_query = self.db.query(Issue).filter(Issue.project_id == project_id)
        
        total = base_query.count()
        
        by_status = {}
        for status in IssueStatus:
            by_status[status.value] = base_query.filter(Issue.status == status.value).count()
        
        by_severity = {}
        for severity in IssueSeverity:
            by_severity[severity.value] = base_query.filter(Issue.severity == severity.value).count()
        
        by_failure_type = {}
        for ft in FailureType:
            by_failure_type[ft.value] = base_query.filter(Issue.failure_type == ft.value).count()
        
        open_count = by_status.get(IssueStatus.OPEN.value, 0)
        in_progress = by_status.get(IssueStatus.IN_PROGRESS.value, 0)
        resolved = by_status.get(IssueStatus.RESOLVED.value, 0)
        closed = by_status.get(IssueStatus.CLOSED.value, 0)
        
        return {
            'total': total,
            'open': open_count,
            'in_progress': in_progress,
            'resolved': resolved,
            'closed': closed,
            'by_status': by_status,
            'by_severity': by_severity,
            'by_failure_type': by_failure_type
        }