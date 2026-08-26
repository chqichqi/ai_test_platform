"""
LLM配置模型
支持多个LLM配置的管理
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from app.core.models.base import BaseModel


class LLMConfig(BaseModel):
    """LLM配置模型 - 保存多个LLM配置"""
    __tablename__ = "llm_configs"
    
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    api_key = Column(String(255), nullable=False)
    base_url = Column(String(500), nullable=False)
    model = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4000)
    is_active = Column(Boolean, default=False)
    status = Column(String(20), default="pending")
    last_test_at = Column(DateTime, nullable=True)
    last_test_message = Column(Text, nullable=True)