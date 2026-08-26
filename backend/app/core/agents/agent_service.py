"""
统一Agent服务层
替代原LLMService，所有LLM调用改为Agent调用
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.models.llm_config import LLMConfig
from app.core.agents.test_case_generation_agent import TestCaseGenerationAgent
from app.core.agents.requirement_analysis_agent import RequirementAnalysisAgent
from app.core.agents.api_test_generation_agent import APITestGenerationAgent
from app.core.agents.failure_analysis_agent import FailureAnalysisAgent


class AgentService:
    """
    统一Agent服务层
    
    所有LLM调用改为Agent调用，Agent自动处理：
    1. 任务拆分（大文档自动分批）
    2. 截断检测和续写
    3. 失败重试
    4. 执行日志追踪
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_config: Optional[LLMConfig] = None
        
        # Agent注册表（按任务类型）
        self.agents = {}
        
        # 初始化Agent实例（延迟加载）
        self._initialized = False
    
    def get_active_config(self) -> Optional[LLMConfig]:
        """获取当前激活的LLM配置"""
        self.llm_config = self.db.query(LLMConfig).filter(
            LLMConfig.is_active == True
        ).first()
        
        return self.llm_config
    
    def _initialize_agents(self):
        """初始化所有Agent实例（延迟加载）"""
        if self._initialized:
            return
        
        llm_config = self.get_active_config()
        if not llm_config:
            logger.warning("未找到激活的LLM配置，Agent初始化失败")
            return
        
        # 注册所有Agent
        self.agents = {
            "test_case_generation": TestCaseGenerationAgent(llm_config, self.db),
            "requirement_analysis": RequirementAnalysisAgent(llm_config, self.db),
            "api_test_generation": APITestGenerationAgent(llm_config, self.db),
            "failure_analysis": FailureAnalysisAgent(llm_config, self.db)
        }
        
        self._initialized = True
        logger.info(f"AgentService初始化成功，已注册{len(self.agents)}个Agent")
    
    async def call_agent(
        self,
        task_type: str,
        task_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用指定类型的Agent
        
        Args:
            task_type: 任务类型
                - test_case_generation: 测试用例生成
                - requirement_analysis: 需求分析
                - api_test_generation: API测试生成
                - failure_analysis: 失败分析
            task_input: 任务输入参数
        
        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (if failed),
                "stats": Dict (执行统计),
                "agent_name": str
            }
        """
        # 初始化Agent（延迟加载）
        self._initialize_agents()
        
        # 检查Agent是否存在
        agent = self.agents.get(task_type)
        
        if not agent:
            logger.error(f"不支持的Agent类型: {task_type}")
            return {
                "success": False,
                "error": f"不支持的Agent类型: {task_type}",
                "available_agents": list(self.agents.keys())
            }
        
        logger.info(f"调用Agent: {agent.agent_name}, 任务类型={task_type}")
        
        # Agent自动处理：任务拆分、截断续写、失败重试
        result = await agent.execute(task_input)
        
        return result
    
    def get_available_agents(self) -> list:
        """获取可用的Agent类型列表"""
        self._initialize_agents()
        return list(self.agents.keys())
    
    def get_agent_stats(self, task_type: str) -> Dict[str, Any]:
        """获取指定Agent的执行统计"""
        agent = self.agents.get(task_type)
        
        if not agent:
            return {"error": "Agent不存在"}
        
        return agent.get_execution_stats()
    
    # === 兼容LLMService的旧接口（逐步替换） ===
    
    async def async_call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """
        兼容LLMService的异步调用接口
        
        注意：此方法仅用于过渡期，新代码请使用call_agent
        """
        # 使用测试用例生成Agent作为默认
        task_input = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        result = await self.call_agent("test_case_generation", task_input)
        
        if result["success"]:
            return result["data"]
        else:
            logger.error(f"Agent调用失败: {result['error']}")
            return None
    
    def call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """
        兼容LLMService的同步调用接口
        
        注意：此方法仅用于过渡期，新代码请使用call_agent
        """
        import asyncio
        
        # 在同步环境中调用异步方法
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                self.async_call_llm(prompt, system_prompt, temperature, max_tokens)
            )
            return result
        finally:
            loop.close()