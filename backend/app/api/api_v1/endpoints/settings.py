"""
系统设置API端点
用于获取和更新系统配置
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import success_response, error_response
from app.core.services.auth_service import AuthService

router = APIRouter()


class LLMConfig(BaseModel):
    """LLM配置模型"""
    provider: str = Field(..., description="LLM提供商: openai, deepseek, minimax, zhipuai, moonshot, custom")
    api_key: Optional[str] = Field(None, description="API密钥")
    base_url: Optional[str] = Field(None, description="API基础URL")
    model: Optional[str] = Field(None, description="模型名称")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(4000, ge=100, le=8000, description="最大Token数")


class LLMConfigResponse(BaseModel):
    """LLM配置响应模型"""
    llm_provider: str
    # OpenAI
    openai_api_key: Optional[str]
    openai_base_url: str
    openai_model: str
    # DeepSeek
    deepseek_api_key: Optional[str]
    deepseek_base_url: str
    deepseek_model: str
    # MiniMax
    minimax_api_key: Optional[str]
    minimax_base_url: str
    minimax_model: str
    # ZhipuAI
    zhipuai_api_key: Optional[str]
    zhipuai_base_url: str
    zhipuai_model: str
    # Moonshot
    moonshot_api_key: Optional[str]
    moonshot_base_url: str
    moonshot_model: str
    # Custom
    custom_api_key: Optional[str]
    custom_base_url: Optional[str]
    custom_model: Optional[str]
    # 通用参数
    embedding_model: str
    llm_temperature: float
    llm_max_tokens: int


class UpdateLLMConfigRequest(BaseModel):
    """更新LLM配置请求模型"""
    llm_provider: str = Field(..., description="LLM提供商")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API密钥")
    openai_base_url: str = Field("https://api.openai.com/v1", description="OpenAI API地址")
    openai_model: str = Field("gpt-4-turbo-preview", description="OpenAI模型")
    deepseek_api_key: Optional[str] = Field(None, description="DeepSeek API密钥")
    deepseek_base_url: str = Field("https://api.deepseek.com/v1", description="DeepSeek API地址")
    deepseek_model: str = Field("deepseek-chat", description="DeepSeek模型")
    minimax_api_key: Optional[str] = Field(None, description="MiniMax API密钥")
    minimax_base_url: str = Field("https://api.minimax.chat/v1", description="MiniMax API地址")
    minimax_model: str = Field("abab6.5-chat", description="MiniMax模型")
    zhipuai_api_key: Optional[str] = Field(None, description="智谱AI API密钥")
    zhipuai_base_url: str = Field("https://open.bigmodel.cn/api/paas/v4", description="智谱AI API地址")
    zhipuai_model: str = Field("glm-4", description="智谱AI模型")
    moonshot_api_key: Optional[str] = Field(None, description="Moonshot API密钥")
    moonshot_base_url: str = Field("https://api.moonshot.cn/v1", description="Moonshot API地址")
    moonshot_model: str = Field("moonshot-v1-8k", description="Moonshot模型")
    custom_api_key: Optional[str] = Field(None, description="自定义API密钥")
    custom_base_url: Optional[str] = Field(None, description="自定义API地址")
    custom_model: Optional[str] = Field(None, description="自定义模型")
    embedding_model: str = Field("text-embedding-3-small", description="Embedding模型")
    llm_temperature: float = Field(0.7, ge=0.0, le=2.0, description="温度参数")
    llm_max_tokens: int = Field(4000, ge=100, le=8000, description="最大Token数")


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(AuthService.get_current_user),
):
    """
    获取当前LLM配置
    
    返回当前系统配置的LLM提供商及其配置信息
    """
    try:
        # 返回配置，但隐藏API密钥
        def mask_api_key(key: Optional[str]) -> Optional[str]:
            if not key:
                return None
            if len(key) <= 8:
                return "***"
            return f"{key[:4]}****{key[-4:]}"
        
        return LLMConfigResponse(
            llm_provider=settings.LLM_PROVIDER,
            openai_api_key=mask_api_key(settings.OPENAI_API_KEY),
            openai_base_url=settings.OPENAI_BASE_URL,
            openai_model=settings.OPENAI_MODEL,
            deepseek_api_key=mask_api_key(settings.DEEPSEEK_API_KEY),
            deepseek_base_url=settings.DEEPSEEK_BASE_URL,
            deepseek_model=settings.DEEPSEEK_MODEL,
            minimax_api_key=mask_api_key(settings.MINIMAX_API_KEY),
            minimax_base_url=settings.MINIMAX_BASE_URL,
            minimax_model=settings.MINIMAX_MODEL,
            zhipuai_api_key=mask_api_key(settings.ZHIPUAI_API_KEY),
            zhipuai_base_url=settings.ZHIPUAI_BASE_URL,
            zhipuai_model=settings.ZHIPUAI_MODEL,
            moonshot_api_key=mask_api_key(settings.MOONSHOT_API_KEY),
            moonshot_base_url=settings.MOONSHOT_BASE_URL,
            moonshot_model=settings.MOONSHOT_MODEL,
            custom_api_key=mask_api_key(settings.CUSTOM_API_KEY),
            custom_base_url=settings.CUSTOM_BASE_URL,
            custom_model=settings.CUSTOM_MODEL,
            embedding_model=settings.EMBEDDING_MODEL,
            llm_temperature=settings.LLM_TEMPERATURE,
            llm_max_tokens=settings.LLM_MAX_TOKENS,
        )
    except Exception as e:
        logger.error(f"获取LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM配置失败: {str(e)}"
        )


@router.post("/llm")
async def update_llm_config(
    config: UpdateLLMConfigRequest,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(AuthService.get_current_user),
):
    """
    更新LLM配置
    
    更新系统的LLM提供商及其配置信息
    """
    try:
        # 注意：这里只是更新内存中的配置
        # 如果要持久化到配置文件，需要额外的文件操作
        
        # 更新配置
        settings.LLM_PROVIDER = config.llm_provider
        
        if config.openai_api_key and not config.openai_api_key.startswith("****"):
            settings.OPENAI_API_KEY = config.openai_api_key
        settings.OPENAI_BASE_URL = config.openai_base_url
        settings.OPENAI_MODEL = config.openai_model
        
        if config.deepseek_api_key and not config.deepseek_api_key.startswith("****"):
            settings.DEEPSEEK_API_KEY = config.deepseek_api_key
        settings.DEEPSEEK_BASE_URL = config.deepseek_base_url
        settings.DEEPSEEK_MODEL = config.deepseek_model
        
        if config.minimax_api_key and not config.minimax_api_key.startswith("****"):
            settings.MINIMAX_API_KEY = config.minimax_api_key
        settings.MINIMAX_BASE_URL = config.minimax_base_url
        settings.MINIMAX_MODEL = config.minimax_model
        
        if config.zhipuai_api_key and not config.zhipuai_api_key.startswith("****"):
            settings.ZHIPUAI_API_KEY = config.zhipuai_api_key
        settings.ZHIPUAI_BASE_URL = config.zhipuai_base_url
        settings.ZHIPUAI_MODEL = config.zhipuai_model
        
        if config.moonshot_api_key and not config.moonshot_api_key.startswith("****"):
            settings.MOONSHOT_API_KEY = config.moonshot_api_key
        settings.MOONSHOT_BASE_URL = config.moonshot_base_url
        settings.MOONSHOT_MODEL = config.moonshot_model
        
        if config.custom_api_key and not config.custom_api_key.startswith("****"):
            settings.CUSTOM_API_KEY = config.custom_api_key
        settings.CUSTOM_BASE_URL = config.custom_base_url
        settings.CUSTOM_MODEL = config.custom_model
        
        settings.EMBEDDING_MODEL = config.embedding_model
        settings.LLM_TEMPERATURE = config.llm_temperature
        settings.LLM_MAX_TOKENS = config.llm_max_tokens
        
        logger.info(f"LLM配置已更新，当前提供商: {config.llm_provider}")
        
        return success_response(
            data={
                "llm_provider": config.llm_provider,
                "message": "LLM配置已更新"
            },
            message="配置更新成功"
        )
        
    except Exception as e:
        logger.error(f"更新LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新LLM配置失败: {str(e)}"
        )


@router.post("/llm/test")
async def test_llm_connection(
    config: UpdateLLMConfigRequest,
    db: Session = Depends(get_db),
    current_user: Dict = Depends(AuthService.get_current_user),
):
    """
    测试LLM连接
    
    测试指定的LLM配置是否可以正常连接
    """
    try:
        import openai
        
        # 根据提供商选择配置
        provider = config.llm_provider.lower()
        
        if provider == "openai":
            api_key = config.openai_api_key
            base_url = config.openai_base_url
            model = config.openai_model
        elif provider == "deepseek":
            api_key = config.deepseek_api_key
            base_url = config.deepseek_base_url
            model = config.deepseek_model
        elif provider == "minimax":
            api_key = config.minimax_api_key
            base_url = config.minimax_base_url
            model = config.minimax_model
        elif provider == "zhipuai":
            api_key = config.zhipuai_api_key
            base_url = config.zhipuai_base_url
            model = config.zhipuai_model
        elif provider == "moonshot":
            api_key = config.moonshot_api_key
            base_url = config.moonshot_base_url
            model = config.moonshot_model
        elif provider == "custom":
            api_key = config.custom_api_key
            base_url = config.custom_base_url
            model = config.custom_model
        else:
            return error_response(
                message=f"不支持的LLM提供商: {provider}",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        if not api_key:
            return error_response(
                message="API密钥不能为空",
                code=status.HTTP_400_BAD_REQUEST
            )
        
        # 创建客户端并测试连接
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # 发送一个简单的测试请求
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )
        
        return success_response(
            data={
                "provider": provider,
                "model": model,
                "response": response.choices[0].message.content if response.choices else None
            },
            message="连接测试成功"
        )
        
    except Exception as e:
        logger.error(f"LLM连接测试失败: {str(e)}")
        return error_response(
            message=f"连接测试失败: {str(e)}",
            code=status.HTTP_400_BAD_REQUEST
        )


@router.get("/system")
async def get_system_info(
    db: Session = Depends(get_db),
    current_user: Dict = Depends(AuthService.get_current_user),
):
    """
    获取系统信息
    
    返回系统版本、数据库状态等基本信息
    """
    try:
        return success_response(
            data={
                "app_name": settings.APP_NAME,
                "app_version": settings.APP_VERSION,
                "app_env": settings.APP_ENV,
                "llm_provider": settings.LLM_PROVIDER,
                "embedding_model": settings.EMBEDDING_MODEL,
            },
            message="获取系统信息成功"
        )
    except Exception as e:
        logger.error(f"获取系统信息失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统信息失败: {str(e)}"
        )
