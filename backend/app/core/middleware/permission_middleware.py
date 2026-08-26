"""
权限验证中间件
用于保护API端点基于用户权限
"""

from typing import List, Optional, Callable
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.services.auth_service import AuthService
from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import error_response

# HTTP Bearer认证方案
security = HTTPBearer(auto_error=False)


class PermissionMiddleware:
    """权限验证中间件"""
    
    def __init__(self, required_permissions: Optional[List[str]] = None):
        """
        初始化权限中间件
        
        Args:
            required_permissions: 需要的权限列表，如果为None则只需要认证
        """
        self.required_permissions = required_permissions or []
    
    async def __call__(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        db: Session = Depends(get_db),
    ):
        """
        权限验证逻辑
        
        Args:
            request: FastAPI请求对象
            credentials: HTTP Bearer认证凭证
            db: 数据库会话
            
        Returns:
            如果验证通过，返回用户信息
            
        Raises:
            HTTPException: 如果认证或授权失败
        """
        # 检查是否有认证凭证
        if not credentials:
            logger.warning(f"Missing authentication token for {request.method} {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication token",
            )
        
        token = credentials.credentials
        auth_service = AuthService(db)
        
        try:
            # 验证访问令牌
            token_data = auth_service.verify_access_token(token)
            if not token_data:
                logger.warning(f"Invalid authentication token for {request.method} {request.url.path}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                )
            
            # 获取用户
            user = auth_service.get_user_by_username(token_data.username)
            if not user:
                logger.warning(f"User not found: {token_data.username}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )
            
            # 检查用户是否激活
            if not user.is_active:
                logger.warning(f"Inactive user attempted access: {user.username}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is inactive",
                )
            
            # 更新最后活跃时间
            auth_service.update_last_active(user)
            
            # 如果不需要特定权限，只验证认证
            if not self.required_permissions:
                logger.debug(f"Authentication successful for user: {user.username} on {request.method} {request.url.path}")
                return {
                    "user": user,
                    "token_data": token_data,
                }
            
            # 检查用户权限
            user_permissions = auth_service.get_user_permissions(user)
            
            # 超级用户拥有所有权限
            if user.is_superuser:
                logger.debug(f"Superuser access granted for {user.username} on {request.method} {request.url.path}")
                return {
                    "user": user,
                    "token_data": token_data,
                    "permissions": user_permissions,
                }
            
            # 检查是否拥有所有需要的权限
            missing_permissions = []
            for required_perm in self.required_permissions:
                if required_perm not in user_permissions:
                    missing_permissions.append(required_perm)
            
            if missing_permissions:
                logger.warning(
                    f"Permission denied for user {user.username} on {request.method} {request.url.path}. "
                    f"Missing permissions: {missing_permissions}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permissions: {', '.join(missing_permissions)}",
                )
            
            logger.debug(f"Permission check passed for user {user.username} on {request.method} {request.url.path}")
            return {
                "user": user,
                "token_data": token_data,
                "permissions": user_permissions,
            }
            
        except HTTPException:
            # 重新抛出HTTP异常
            raise
        except Exception as e:
            logger.error(f"Permission middleware error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during permission verification",
            )


# 权限装饰器函数
def require_permissions(*permissions: str):
    """
    权限验证装饰器
    
    Args:
        *permissions: 需要的权限代码列表
        
    Returns:
        权限验证依赖项
    """
    return PermissionMiddleware(list(permissions))


# 常用权限组合
class Permissions:
    """常用权限组合"""
    
    AUTH_ONLY = require_permissions()
    
    PROJECT_READ = require_permissions("project:read")
    PROJECT_CREATE = require_permissions("project:create")
    PROJECT_UPDATE = require_permissions("project:update")
    PROJECT_DELETE = require_permissions("project:delete")
    PROJECT_EXPORT = require_permissions("project:export")
    
    VERSION_READ = require_permissions("version:read")
    VERSION_CREATE = require_permissions("version:create")
    VERSION_UPDATE = require_permissions("version:update")
    VERSION_DELETE = require_permissions("version:delete")
    
    GIT_READ = require_permissions("git:read")
    GIT_CREATE = require_permissions("git:create")
    GIT_UPDATE = require_permissions("git:update")
    GIT_DELETE = require_permissions("git:delete")
    GIT_SYNC = require_permissions("git:sync")
    GIT_WEBHOOK = require_permissions("git:webhook")
    
    TEST_READ = require_permissions("test:read")
    TEST_CREATE = require_permissions("test:create")
    TEST_UPDATE = require_permissions("test:update")
    TEST_DELETE = require_permissions("test:delete")
    TEST_EXECUTE = require_permissions("test:execute")
    TEST_APPROVE = require_permissions("test:approve")
    
    API_TEST_READ = require_permissions("api_test:read")
    API_TEST_CREATE = require_permissions("api_test:create")
    API_TEST_EXECUTE = require_permissions("api_test:execute")
    
    WEB_TEST_READ = require_permissions("web_test:read")
    WEB_TEST_CREATE = require_permissions("web_test:create")
    WEB_TEST_EXECUTE = require_permissions("web_test:execute")
    
    FUNCTIONAL_TEST_READ = require_permissions("functional_test:read")
    FUNCTIONAL_TEST_CREATE = require_permissions("functional_test:create")
    FUNCTIONAL_TEST_GENERATE = require_permissions("functional_test:generate")
    
    REQUIREMENT_CHANGE_READ = require_permissions("requirement_change:read")
    REQUIREMENT_CHANGE_CREATE = require_permissions("requirement_change:create")
    REQUIREMENT_CHANGE_APPROVE = require_permissions("requirement_change:approve")
    REQUIREMENT_CHANGE_PROCESS = require_permissions("requirement_change:process")
    REQUIREMENT_CHANGE_DELETE = require_permissions("requirement_change:delete")
    
    RAG_ACCESS = require_permissions("rag:read")
    RAG_READ = require_permissions("rag:read")
    RAG_UPLOAD = require_permissions("rag:upload")
    RAG_QUERY = require_permissions("rag:query")
    RAG_DELETE = require_permissions("rag:delete")
    RAG_PROCESS = require_permissions("rag:process")
    
    SKILL_READ = require_permissions("skill:read")
    SKILL_CREATE = require_permissions("skill:create")
    SKILL_UPDATE = require_permissions("skill:update")
    SKILL_DELETE = require_permissions("skill:delete")
    SKILL_USE = require_permissions("skill:use")
    RAG_SEARCH = require_permissions("rag:search")
    
    SKILL_READ = require_permissions("skill:read")
    SKILL_CREATE = require_permissions("skill:create")
    SKILL_UPDATE = require_permissions("skill:update")
    SKILL_DELETE = require_permissions("skill:delete")
    SKILL_USE = require_permissions("skill:use")
    
    REPORT_VIEW = require_permissions("report:view")
    REPORT_EXPORT = require_permissions("report:export")
    REPORT_DELETE = require_permissions("report:delete")
    
    DASHBOARD_VIEW = require_permissions("dashboard:view")
    
    SYSTEM_CONFIG = require_permissions("system:config")
    USER_MANAGE = require_permissions("user:manage")
    ROLE_MANAGE = require_permissions("role:manage")
    
    # 组合权限（多个权限都需要）
    @staticmethod
    def all_of(*perms: str):
        """需要所有指定的权限"""
        return require_permissions(*perms)
    
    @staticmethod
    def any_of(*perms: str):
        """需要任意一个指定的权限"""
        # 这个需要自定义实现，因为PermissionMiddleware当前要求所有权限
        # 这里先返回一个占位符，实际使用时需要特殊处理
        class AnyPermissionMiddleware(PermissionMiddleware):
            async def __call__(self, request: Request, credentials=None, db=None):
                # 简化实现：检查是否有任意一个权限
                if not credentials:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Missing authentication token",
                    )
                
                token = credentials.credentials
                auth_service = AuthService(db)
                
                token_data = auth_service.verify_access_token(token)
                if not token_data:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired token",
                    )
                
                user = auth_service.get_user_by_username(token_data.username)
                if not user or not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User not found or inactive",
                    )
                
                # 超级用户直接通过
                if user.is_superuser:
                    return {
                        "user": user,
                        "token_data": token_data,
                    }
                
                # 检查是否有任意一个权限
                user_permissions = auth_service.get_user_permissions(user)
                for perm in perms:
                    if perm in user_permissions:
                        return {
                            "user": user,
                            "token_data": token_data,
                            "permissions": user_permissions,
                        }
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission. Need any of: {', '.join(perms)}",
                )
        
        return AnyPermissionMiddleware()