"""
LangChain Agent配置
适配现有的LLMConfig配置到LangChain框架
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_community.llms import FakeListLLM

from app.core.models.llm_config import LLMConfig
from app.core.logger import logger


class AgentConfig:
    """Agent配置管理"""
    
    def __init__(self, db: Session):
        self.db = db
        self._llm_config: Optional[LLMConfig] = None
    
    def get_active_llm_config(self) -> Optional[LLMConfig]:
        """获取当前激活的LLM配置"""
        self._llm_config = self.db.query(LLMConfig).filter(
            LLMConfig.is_active == True
        ).first()
        return self._llm_config
    
    def get_langchain_llm(
        self,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[ChatOpenAI]:
        """
        将LLMConfig转换为LangChain的ChatOpenAI模型
        
        Args:
            temperature: 温度参数（覆盖默认值）
            max_tokens: 最大token数（覆盖默认值）
        
        Returns:
            LangChain ChatOpenAI实例，失败返回None
        """
        config = self.get_active_llm_config()
        if not config:
            logger.warning("No active LLM config found for LangChain")
            return None
        
        try:
            base_url = config.base_url.rstrip('/')
            if not base_url.endswith('/v1'):
                if '/v1' not in base_url:
                    base_url = f"{base_url}/v1"
            
            llm = ChatOpenAI(
                model=config.model,
                openai_api_key=config.api_key,
                openai_api_base=base_url,
                temperature=temperature if temperature is not None else config.temperature,
                max_tokens=max_tokens if max_tokens is not None else config.max_tokens,
                request_timeout=900,  # 15分钟超时
            )
            
            logger.info(f"LangChain LLM initialized: {config.name}, Model: {config.model}")
            return llm
            
        except Exception as e:
            logger.error(f"Failed to create LangChain LLM: {str(e)}")
            return None
    
    def get_fake_llm_for_testing(self) -> FakeListLLM:
        """
        获取用于测试的FakeListLLM
        用于在没有真实LLM配置时测试Agent逻辑
        """
        return FakeListLLM(
            responses=[
                "这是一个测试响应",
                "这是另一个测试响应",
            ]
        )