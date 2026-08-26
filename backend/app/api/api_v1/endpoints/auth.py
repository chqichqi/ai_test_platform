"""
认证相关API端点
"""

from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.schemas.auth import (
    Token,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.core.services.auth_service import AuthService
from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import success_response, error_response
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    用户登录
    
    Args:
        form_data: OAuth2密码请求表单
        db: 数据库会话
        
    Returns:
        统一响应格式的令牌信息
    """
    auth_service = AuthService(db)
    
    try:
        # 验证用户凭据
        user = auth_service.authenticate_user(
            username=form_data.username,
            password=form_data.password,
        )
        
        if not user:
            logger.warning(f"Failed login attempt for username: {form_data.username}")
            return error_response(
                message="Incorrect username or password",
                code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # 检查用户是否激活
        if not user.is_active:
            return error_response(
                message="User account is inactive",
                code=status.HTTP_400_BAD_REQUEST,
            )
        
        # 更新最后登录时间
        auth_service.update_last_login(user)
        
        # 创建访问令牌
        access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": user.username},
            expires_delta=access_token_expires,
        )
        
        # 创建刷新令牌
        refresh_token_expires = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token = auth_service.create_refresh_token(
            data={"sub": user.username},
            expires_delta=refresh_token_expires,
        )
        
        # 记录登录成功
        logger.info(f"User logged in: {user.username}")
        
        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": UserResponse.from_orm(user).dict(),
        }
        
        return success_response(
            data=token_data,
            message="Login successful",
        )
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )


@router.post("/login/json", response_model=TokenResponse)
async def login_json(
    login_data: UserLogin = Body(...),
    db: Session = Depends(get_db),
):
    """
    用户登录（JSON格式）
    支持API测试用例使用JSON请求体登录
    
    Args:
        login_data: JSON格式的登录数据（username, password）
        db: 数据库会话
        
    Returns:
        统一响应格式的令牌信息
    """
    auth_service = AuthService(db)
    
    user = auth_service.authenticate_user(
        username=login_data.username,
        password=login_data.password,
    )
    
    if not user:
        logger.warning(f"Failed login attempt for username: {login_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
    
    auth_service.update_last_login(user)
    
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    
    refresh_token_expires = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = auth_service.create_refresh_token(
        data={"sub": user.username},
        expires_delta=refresh_token_expires,
    )
    
    logger.info(f"User logged in via JSON: {user.username}")
    
    return TokenResponse(
        success=True,
        code=200,
        message="Login successful",
        data=Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            token=access_token,
            user=UserResponse.from_orm(user).dict()
        )
    )


@router.post("/register")
async def register(
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    用户注册
    
    Args:
        user_data: 用户注册数据
        db: 数据库会话
        
    Returns:
        统一响应格式的用户信息
    """
    auth_service = AuthService(db)
    
    try:
        # 检查用户名是否已存在
        if auth_service.get_user_by_username(user_data.username):
            return error_response(
                message="Username already registered",
                code=status.HTTP_400_BAD_REQUEST,
            )
        
        # 检查邮箱是否已存在
        if auth_service.get_user_by_email(user_data.email):
            return error_response(
                message="Email already registered",
                code=status.HTTP_400_BAD_REQUEST,
            )
        
        # 创建用户
        user = auth_service.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name,
            department=user_data.department,
            position=user_data.position,
        )
        
        # 记录注册成功
        logger.info(f"New user registered: {user.username}")
        
        # 转换为响应模型
        user_response = UserResponse.from_orm(user).dict()
        
        return success_response(
            data=user_response,
            message="User registered successfully",
            code=status.HTTP_201_CREATED,
        )
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )


@router.post("/refresh")
async def refresh_token(
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """
    刷新访问令牌
    
    Args:
        refresh_token: 刷新令牌
        db: 数据库会话
        
    Returns:
        统一响应格式的令牌信息
    """
    auth_service = AuthService(db)
    
    try:
        # 验证刷新令牌
        token_data = auth_service.verify_refresh_token(refresh_token)
        if not token_data:
            return error_response(
                message="Invalid refresh token",
                code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # 获取用户
        if not token_data.username:
            return error_response(
                message="Invalid token data",
                code=status.HTTP_401_UNAUTHORIZED,
            )
        
        user = auth_service.get_user_by_username(token_data.username)
        if not user or not user.is_active:
            return error_response(
                message="User not found or inactive",
                code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # 创建新的访问令牌
        access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": user.username},
            expires_delta=access_token_expires,
        )
        
        # 创建新的刷新令牌
        refresh_token_expires = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        new_refresh_token = auth_service.create_refresh_token(
            data={"sub": user.username},
            expires_delta=refresh_token_expires,
        )
        
        token_data = {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": UserResponse.from_orm(user).dict(),
        }
        
        return success_response(
            data=token_data,
            message="Token refreshed successfully",
        )
        
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )


@router.post("/logout")
async def logout(
    token: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """
    用户登出
    
    Args:
        token: 访问令牌
        db: 数据库会话
        
    Returns:
        统一响应格式的登出结果
    """
    auth_service = AuthService(db)
    
    try:
        # 将令牌加入黑名单（在实际应用中需要实现令牌黑名单）
        # 这里只是示例，实际需要存储到Redis或数据库
        auth_service.revoke_token(token)
        
        logger.info("User logged out successfully")
        
        return success_response(
            message="Logged out successfully",
        )
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )


@router.post("/password-reset/request")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """
    请求密码重置
    
    Args:
        reset_request: 密码重置请求
        db: 数据库会话
        
    Returns:
        统一响应格式的请求结果
    """
    auth_service = AuthService(db)
    
    try:
        # 获取用户
        user = auth_service.get_user_by_email(reset_request.email)
        if not user:
            # 出于安全考虑，不透露用户是否存在
            logger.info(f"Password reset requested for email: {reset_request.email}")
            return success_response(
                message="If the email exists, a reset link has been sent",
            )
        
        # 生成密码重置令牌
        reset_token = auth_service.create_password_reset_token(user.email)
        
        # 发送密码重置邮件（这里只是记录，实际需要实现邮件发送）
        logger.info(f"Password reset token generated for user: {user.username}")
        
        # 在实际应用中，这里应该发送包含重置链接的邮件
        # reset_link = f"https://example.com/reset-password?token={reset_token}"
        # send_reset_email(user.email, reset_link)
        
        return success_response(
            message="If the email exists, a reset link has been sent",
        )
        
    except Exception as e:
        logger.error(f"Password reset request error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    """
    确认密码重置
    
    Args:
        reset_confirm: 密码重置确认
        db: 数据库会话
        
    Returns:
        统一响应格式的重置结果
    """
    auth_service = AuthService(db)
    
    try:
        # 验证重置令牌
        email = auth_service.verify_password_reset_token(reset_confirm.token)
        if not email:
            return error_response(
                message="Invalid or expired reset token",
                code=status.HTTP_400_BAD_REQUEST,
            )
        
        # 获取用户
        user = auth_service.get_user_by_email(email)
        if not user:
            return error_response(
                message="User not found",
                code=status.HTTP_400_BAD_REQUEST,
            )
        
        # 更新密码
        auth_service.update_user_password(user, reset_confirm.new_password)
        
        logger.info(f"Password reset successful for user: {user.username}")
        
        return success_response(
            message="Password reset successfully",
        )
        
    except Exception as e:
        logger.error(f"Password reset confirm error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )


@router.get("/me")
async def get_current_user(
    current_user: Dict[str, Any] = Depends(AuthService.get_current_user),
):
    """
    获取当前用户信息
    
    Args:
        current_user: 当前用户
        
    Returns:
        统一响应格式的用户信息
    """
    return success_response(
        data=current_user,
        message="User information retrieved successfully",
    )


@router.get("/permissions")
async def get_user_permissions(
    current_user: Dict[str, Any] = Depends(AuthService.get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取用户权限列表
    
    Args:
        current_user: 当前用户
        db: 数据库会话
        
    Returns:
        统一响应格式的权限列表
    """
    auth_service = AuthService(db)
    
    try:
        user = auth_service.get_user_by_username(current_user["username"])
        if not user:
            return error_response(
                message="User not found",
                code=status.HTTP_404_NOT_FOUND,
            )
        
        permissions = user.get_all_permissions()
        
        return success_response(
            data={
                "permissions": permissions,
                "is_superuser": user.is_superuser,
            },
            message="Permissions retrieved successfully",
        )
        
    except Exception as e:
        logger.error(f"Get permissions error: {str(e)}")
        return error_response(
            message="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_detail=str(e) if settings.DEBUG else None,
        )