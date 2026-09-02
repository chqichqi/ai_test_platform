"""
LLM配置管理API端点
支持多个LLM配置的增删改查、测试连接和切换
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import success_response, error_response
from app.core.services.auth_service import AuthService
from app.core.models.llm_config import LLMConfig

router = APIRouter()


class LLMConfigCreate(BaseModel):
    """创建LLM配置请求"""
    name: str = Field(..., description="配置名称", min_length=1, max_length=100)
    provider: str = Field(..., description="LLM提供商: openai, deepseek, zhipuai, moonshot, qwen, custom")
    api_key: str = Field(..., description="API密钥")
    base_url: str = Field(default="https://api.openai.com/v1", description="API基础URL")
    model: str = Field(default="gpt-4o", description="模型名称")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=4000, ge=100, le=200000, description="最大Token数")


class LLMConfigUpdate(BaseModel):
    """更新LLM配置请求"""
    name: Optional[str] = Field(None, description="配置名称", min_length=1, max_length=100)
    provider: Optional[str] = Field(None, description="LLM提供商")
    api_key: Optional[str] = Field(None, description="API密钥")
    base_url: Optional[str] = Field(None, description="API基础URL")
    model: Optional[str] = Field(None, description="模型名称")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(None, ge=100, le=200000, description="最大Token数")


class LLMConfigResponse(BaseModel):
    """LLM配置响应"""
    id: str
    name: str
    provider: str
    api_key_masked: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    is_active: bool
    status: str
    last_test_at: Optional[datetime] = None
    last_test_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def mask_api_key(key: str) -> str:
    """隐藏API密钥中间部分"""
    if not key:
        return "***"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}****{key[-4:]}"


@router.get("", response_model=List[LLMConfigResponse])
async def list_llm_configs(
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    获取所有LLM配置列表
    """
    try:
        configs = db.query(LLMConfig).order_by(LLMConfig.created_at.desc()).all()
        
        result = []
        for config in configs:
            result.append(LLMConfigResponse(
                id=config.id,
                name=config.name,
                provider=config.provider,
                api_key_masked=mask_api_key(config.api_key),
                base_url=config.base_url,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                is_active=config.is_active,
                status=config.status,
                last_test_at=config.last_test_at,
                last_test_message=config.last_test_message,
                created_at=config.created_at,
                updated_at=config.updated_at,
            ))
        
        return result
    except Exception as e:
        logger.error(f"获取LLM配置列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM配置列表失败: {str(e)}"
        )


@router.get("/{config_id}", response_model=LLMConfigResponse)
async def get_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    获取单个LLM配置详情
    """
    try:
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM配置不存在: {config_id}"
            )
        
        return LLMConfigResponse(
            id=config.id,
            name=config.name,
            provider=config.provider,
            api_key_masked=mask_api_key(config.api_key),
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            is_active=config.is_active,
            status=config.status,
            last_test_at=config.last_test_at,
            last_test_message=config.last_test_message,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM配置失败: {str(e)}"
        )


@router.post("", response_model=LLMConfigResponse)
async def create_llm_config(
    config_data: LLMConfigCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    创建新的LLM配置
    """
    try:
        logger.info(f"创建LLM配置请求: name={config_data.name}, provider={config_data.provider}, model={config_data.model}, base_url={config_data.base_url}")
        
        existing = db.query(LLMConfig).filter(LLMConfig.name == config_data.name).first()
        if existing:
            logger.warning(f"配置名称已存在: {config_data.name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"配置名称已存在: {config_data.name}"
            )
        
        # 第一条 LLM 配置自动激活（用户 2026-09-02 需求：仅只有第一个 LLM 时自动激活，
        # 后续新建配置不自动激活，需手动「切换使用」或编辑保存后激活，避免覆盖现有活跃配置）
        is_first = db.query(LLMConfig).filter(
            LLMConfig.deleted_at.is_(None)
        ).count() == 0

        new_config = LLMConfig(
            name=config_data.name,
            provider=config_data.provider,
            api_key=config_data.api_key,
            base_url=config_data.base_url,
            model=config_data.model,
            temperature=config_data.temperature,
            max_tokens=config_data.max_tokens,
            is_active=is_first,
            status="pending",
        )
        
        logger.info(f"创建LLM配置对象: id={new_config.id}")
        
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        
        logger.info(f"创建LLM配置成功: {new_config.name}, id={new_config.id}")
        
        return LLMConfigResponse(
            id=str(new_config.id),
            name=new_config.name,
            provider=new_config.provider,
            api_key_masked=mask_api_key(new_config.api_key),
            base_url=new_config.base_url,
            model=new_config.model,
            temperature=new_config.temperature,
            max_tokens=new_config.max_tokens,
            is_active=new_config.is_active,
            status=new_config.status,
            last_test_at=new_config.last_test_at,
            last_test_message=new_config.last_test_message,
            created_at=new_config.created_at,
            updated_at=new_config.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"创建LLM配置失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建LLM配置失败: {str(e)}"
        )


@router.put("/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(
    config_id: str,
    config_data: LLMConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    更新LLM配置
    """
    try:
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM配置不存在: {config_id}"
            )
        
        if config_data.name is not None:
            existing = db.query(LLMConfig).filter(
                and_(LLMConfig.name == config_data.name, LLMConfig.id != config_id)
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"配置名称已存在: {config_data.name}"
                )
            config.name = config_data.name
        
        if config_data.provider is not None:
            config.provider = config_data.provider
        if config_data.api_key is not None:
            config.api_key = config_data.api_key
        if config_data.base_url is not None:
            config.base_url = config_data.base_url
        if config_data.model is not None:
            config.model = config_data.model
        if config_data.temperature is not None:
            config.temperature = config_data.temperature
        if config_data.max_tokens is not None:
            config.max_tokens = config_data.max_tokens
        
        config.updated_at = datetime.utcnow()

        # 用户修改配置保存后自动激活该配置（用户 2026-09-02 需求）
        # 唯一活跃原则：先将其余未删除配置置非活跃，再激活当前配置
        db.query(LLMConfig).filter(
            LLMConfig.id != config.id,
            LLMConfig.deleted_at.is_(None),
        ).update({"is_active": False})
        config.is_active = True

        db.commit()
        db.refresh(config)

        logger.info(f"更新LLM配置成功: {config.name}（已自动激活）")
        
        return LLMConfigResponse(
            id=config.id,
            name=config.name,
            provider=config.provider,
            api_key_masked=mask_api_key(config.api_key),
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            is_active=config.is_active,
            status=config.status,
            last_test_at=config.last_test_at,
            last_test_message=config.last_test_message,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新LLM配置失败: {str(e)}"
        )


@router.delete("/{config_id}")
async def delete_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    删除LLM配置
    """
    try:
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM配置不存在: {config_id}"
            )
        
        was_active = config.is_active
        config_name = config.name
        
        db.delete(config)
        db.commit()
        
        if was_active:
            first_config = db.query(LLMConfig).first()
            if first_config:
                first_config.is_active = True
                db.commit()
        
        logger.info(f"删除LLM配置成功: {config_name}")
        
        return success_response(
            data={"id": config_id, "name": config_name},
            message="删除LLM配置成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除LLM配置失败: {str(e)}"
        )


@router.post("/{config_id}/test")
async def test_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    测试LLM配置连接
    """
    config = None
    try:
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM配置不存在: {config_id}"
            )
        
        import requests
        
        base_url = config.base_url.rstrip('/')
        if not base_url.endswith('/chat/completions'):
            if base_url.endswith('/v1'):
                api_url = f"{base_url}/chat/completions"
            elif '/v1' not in base_url:
                api_url = f"{base_url}/v1/chat/completions"
            else:
                api_url = f"{base_url}/chat/completions"
        else:
            api_url = base_url
        
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": config.model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        
        logger.info(f"测试LLM连接: {config.name}, URL: {api_url}, Model: {config.model}")
        
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=30,
        )
        
        logger.info(f"LLM响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            content = None
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0].get("message", {}).get("content")
            
            config.status = "success"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = "连接测试成功"
            db.commit()
            
            logger.info(f"LLM配置连接测试成功: {config.name}")
            
            return success_response(
                data={
                    "id": config_id,
                    "name": config.name,
                    "status": "success",
                    "response": content
                },
                message="连接测试成功"
            )
        elif response.status_code == 401:
            error_msg = "认证失败，请检查API密钥是否正确"
            config.status = "failed"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = error_msg
            db.commit()
            logger.error(f"LLM认证失败: {error_msg}")
            return error_response(message=error_msg, code=status.HTTP_401_UNAUTHORIZED)
        elif response.status_code == 404:
            error_msg = f"API端点不存在，请检查BASE_URL或模型名称。响应: {response.text[:200]}"
            config.status = "failed"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = error_msg
            db.commit()
            logger.error(f"LLM端点错误: {error_msg}")
            return error_response(message=error_msg, code=status.HTTP_404_NOT_FOUND)
        else:
            error_msg = f"API返回错误 [{response.status_code}]: {response.text[:200]}"
            config.status = "failed"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = error_msg
            db.commit()
            logger.error(f"LLM配置API错误: {error_msg}")
            return error_response(message=error_msg, code=response.status_code)
            
    except HTTPException:
        raise
    except requests.exceptions.Timeout:
        error_msg = "连接超时，请检查网络或BASE_URL是否正确"
        if config:
            config.status = "failed"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = error_msg
            db.commit()
        logger.error(f"LLM连接超时: {error_msg}")
        return error_response(message=error_msg, code=status.HTTP_504_GATEWAY_TIMEOUT)
    except requests.exceptions.ConnectionError as e:
        error_msg = f"无法连接到API服务，请检查BASE_URL是否正确: {str(e)[:100]}"
        if config:
            config.status = "failed"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = error_msg
            db.commit()
        logger.error(f"LLM连接失败: {error_msg}")
        return error_response(message=error_msg, code=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        error_msg = f"连接测试失败: {str(e)}"
        if config:
            config.status = "failed"
            config.last_test_at = datetime.utcnow()
            config.last_test_message = error_msg
            db.commit()
        logger.error(f"LLM配置连接测试失败: {error_msg}")
        return error_response(message=error_msg, code=status.HTTP_400_BAD_REQUEST)


@router.post("/{config_id}/activate")
async def activate_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    激活/切换LLM配置
    """
    try:
        config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM配置不存在: {config_id}"
            )
        
        if config.status != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请先测试连接成功后再激活配置"
            )
        
        db.query(LLMConfig).update({"is_active": False})
        
        config.is_active = True
        config.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"激活LLM配置成功: {config.name}")
        
        return success_response(
            data={
                "id": config_id,
                "name": config.name,
                "is_active": True
            },
            message=f"已切换到配置: {config.name}"
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"激活LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"激活LLM配置失败: {str(e)}"
        )


@router.get("/active/current")
async def get_active_llm_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(AuthService.get_current_user),
):
    """
    获取当前激活的LLM配置
    """
    try:
        config = db.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        
        if not config:
            return success_response(
                data=None,
                message="当前没有激活的LLM配置"
            )
        
        return success_response(
            data={
                "id": config.id,
                "name": config.name,
                "provider": config.provider,
                "model": config.model,
                "base_url": config.base_url,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
            },
            message="获取当前激活配置成功"
        )
    except Exception as e:
        logger.error(f"获取当前激活LLM配置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取当前激活LLM配置失败: {str(e)}"
        )