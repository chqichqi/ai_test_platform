"""
Agent框架模块
基于LangChain实现智能化LLM调用，支持自动任务拆分、截断续写、失败重试
"""

from app.core.agents.base_agent import BaseAgent
from app.core.agents.agent_service import AgentService
from app.core.agents.test_case_generation_agent import TestCaseGenerationAgent
from app.core.agents.requirement_analysis_agent import RequirementAnalysisAgent
from app.core.agents.api_test_generation_agent import APITestGenerationAgent
from app.core.agents.failure_analysis_agent import FailureAnalysisAgent
from app.core.agents.system_explorer_agent import SystemExplorerAgent

__all__ = [
    "BaseAgent",
    "AgentService",
    "TestCaseGenerationAgent",
    "RequirementAnalysisAgent",
    "APITestGenerationAgent",
    "FailureAnalysisAgent",
    "SystemExplorerAgent"
]

# 待实现的Agent（Phase 23+）
# WebUITestConversionAgent, TestDataGeneratorAgent