"""
认证服务
处理用户认证、授权、令牌管理等
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.models.user import User, Role, Permission
from app.core.schemas.auth import TokenData
from app.core.logger import logger
from app.core.database import get_db


# 密码哈希上下文
# 使用sha256_crypt作为主要方案（更稳定）
pwd_context = CryptContext(
    schemes=["sha256_crypt"],
    deprecated="auto",
    sha256_crypt__default_rounds=100000,
)

# OAuth2密码承载令牌
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)


class AuthService:
    """认证服务类"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # 密码相关方法
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """获取密码哈希值"""
        # 确保密码不超过72字节（bcrypt限制）
        if len(password.encode('utf-8')) > 72:
            password = password[:72]
        return pwd_context.hash(password)
    
    # 用户相关方法
    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return self.db.query(User).filter(
            User.username == username,
            User.deleted_at.is_(None)
        ).first()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        return self.db.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)
        ).first()
    
    def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """根据ID获取用户"""
        return self.db.query(User).filter(
            User.id == user_id,
            User.deleted_at.is_(None)
        ).first()
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """验证用户凭据"""
        # 尝试通过用户名查找
        user = self.get_user_by_username(username)
        
        # 如果用户名没找到，尝试通过邮箱查找
        if not user:
            user = self.get_user_by_email(username)
        
        if not user:
            return None
        
        if not self.verify_password(password, user.password_hash):
            return None
        
        return user
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        department: Optional[str] = None,
        position: Optional[str] = None,
        is_active: bool = True,
        is_superuser: bool = False,
    ) -> User:
        """创建新用户"""
        # 检查用户名和邮箱是否已存在
        if self.get_user_by_username(username):
            raise ValueError(f"Username {username} already exists")
        
        if self.get_user_by_email(email):
            raise ValueError(f"Email {email} already exists")
        
        # 创建用户
        user = User(
            username=username,
            email=email,
            password_hash=self.get_password_hash(password),
            full_name=full_name,
            department=department,
            position=position,
            is_active=is_active,
            is_superuser=is_superuser,
        )
        
        # 分配默认角色
        default_role = self.db.query(Role).filter(
            Role.is_default == True,
            Role.deleted_at.is_(None)
        ).first()
        
        if default_role:
            user.roles.append(default_role)
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        return user
    
    def update_user_password(self, user: User, new_password: str) -> None:
        """更新用户密码"""
        user.password_hash = self.get_password_hash(new_password)
        user.updated_at = datetime.utcnow()
        self.db.commit()
    
    def update_last_login(self, user: User) -> None:
        """更新最后登录时间"""
        user.last_login = datetime.utcnow()
        user.last_active = datetime.utcnow()
        self.db.commit()
    
    def update_last_active(self, user: User) -> None:
        """更新最后活动时间"""
        user.last_active = datetime.utcnow()
        self.db.commit()
    
    # 令牌相关方法
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建访问令牌"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """创建刷新令牌"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=7)
        
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        return encoded_jwt
    
    @staticmethod
    def create_password_reset_token(email: str, expires_delta: Optional[timedelta] = None) -> str:
        """创建密码重置令牌"""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=1)
        
        to_encode = {"sub": email, "exp": expire, "type": "password_reset"}
        encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[TokenData]:
        """验证令牌"""
        try:
            logger.debug(f"Verifying token of type: {token_type}")
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            logger.debug(f"Token payload: {payload}")
            
            # 检查令牌类型
            token_type_in_payload = payload.get("type")
            logger.debug(f"Token type in payload: {token_type_in_payload}")
            if token_type_in_payload != token_type:
                logger.warning(f"Token type mismatch: expected {token_type}, got {token_type_in_payload}")
                return None
            
            username = payload.get("sub")
            logger.debug(f"Username in payload: {username}, type: {type(username)}")
            if username is None:
                logger.warning("Token missing 'sub' claim")
                return None
            
            # Ensure username is a string
            if not isinstance(username, str):
                logger.warning(f"Username is not a string: {type(username)}")
                return None
            
            token_data = TokenData(username=username, exp=payload.get("exp"))
            logger.debug(f"Created token data: {token_data}")
            return token_data
        except JWTError as e:
            logger.error(f"JWT decode error: {str(e)}")
            return None
        except KeyError as e:
            logger.error(f"Key error in token verification: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {type(e).__name__}: {str(e)}")
            return None
    
    def verify_access_token(self, token: str) -> Optional[TokenData]:
        """验证访问令牌"""
        return self.verify_token(token, "access")
    
    def verify_refresh_token(self, token: str) -> Optional[TokenData]:
        """验证刷新令牌"""
        return self.verify_token(token, "refresh")
    
    def verify_password_reset_token(self, token: str) -> Optional[str]:
        """验证密码重置令牌"""
        token_data = self.verify_token(token, "password_reset")
        if token_data and token_data.username:
            return token_data.username
        return None
    
    def revoke_token(self, token: str) -> None:
        """撤销令牌（加入黑名单）"""
        # 在实际应用中，这里应该将令牌加入Redis黑名单
        # 这里只是示例，实际需要存储到Redis或数据库
        logger.info(f"Token revoked: {token[:20]}...")
    
    # 权限相关方法
    def get_user_permissions(self, user: User) -> List[str]:
        """获取用户所有权限代码"""
        return user.get_all_permissions()
    
    def check_user_permission(self, user: User, permission_code: str) -> bool:
        """检查用户是否有指定权限"""
        return user.has_permission(permission_code)
    
    def get_user_roles(self, user: User) -> List[str]:
        """获取用户角色列表"""
        return [role.name for role in user.roles]
    
    # 依赖注入方法
    @classmethod
    def get_current_user(
        cls,
        token: Optional[str] = Depends(oauth2_scheme),
        db: Session = Depends(get_db),
    ) -> Dict[str, Any]:
        """获取当前用户（依赖注入）"""
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 创建服务实例
        auth_service = cls(db)
        
        # 验证令牌
        token_data = auth_service.verify_access_token(token)
        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 获取用户
        user = auth_service.get_user_by_username(token_data.username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user",
            )
        
        # 更新最后活动时间
        auth_service.update_last_active(user)
        
        # 返回用户信息
        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "is_verified": user.is_verified,
            "department": user.department,
            "position": user.position,
            "avatar_url": user.avatar_url,
            "phone": user.phone,
            "roles": auth_service.get_user_roles(user),
            "permissions": auth_service.get_user_permissions(user),
            "last_login": user.last_login,
            "last_active": user.last_active,
        }
    
    @classmethod
    def get_current_active_user(
        cls,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """获取当前活跃用户"""
        if not current_user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user",
            )
        return current_user
    
    @classmethod
    def get_current_superuser(
        cls,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """获取当前超级用户"""
        if not current_user["is_superuser"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user
    
    # 权限检查装饰器（替代方案）
    @classmethod
    def require_permission(cls, permission_code: str):
        """权限检查装饰器工厂"""
        def permission_dependency(
            current_user: Dict[str, Any] = Depends(cls.get_current_user),
        ) -> Dict[str, Any]:
            if not current_user["is_superuser"] and permission_code not in current_user["permissions"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission_code}",
                )
            return current_user
        return permission_dependency
    
    # 菜单权限相关
    def get_user_menus(self, user: User) -> List[Dict[str, Any]]:
        """获取用户有权限的菜单"""
        # 这里应该从配置或数据库加载菜单配置
        # 这里只是示例，实际需要完整的菜单配置
        menus = [
            {
                "id": "dashboard",
                "name": "仪表盘",
                "icon": "DashboardOutlined",
                "path": "/dashboard",
                "required_permission": "dashboard:view",
            },
            {
                "id": "project_management",
                "name": "项目管理",
                "icon": "ProjectOutlined",
                "path": "/projects",
                "required_permission": "project:read",
                "children": [
                    {
                        "id": "project_list",
                        "name": "项目列表",
                        "path": "/projects/list",
                        "required_permission": "project:read",
                    },
                ],
            },
        ]
        
        # 过滤用户有权限的菜单
        return self._filter_menus_by_permission(menus, user)
    
    def _filter_menus_by_permission(self, menus: List[Dict[str, Any]], user: User) -> List[Dict[str, Any]]:
        """根据用户权限过滤菜单"""
        filtered_menus = []
        
        for menu in menus:
            # 检查菜单权限
            required_permission = menu.get("required_permission")
            if required_permission and not user.has_permission(required_permission):
                continue
            
            # 递归过滤子菜单
            filtered_menu = menu.copy()
            children = menu.get("children", [])
            if children:
                filtered_menu["children"] = self._filter_menus_by_permission(children, user)
            
            filtered_menus.append(filtered_menu)
        
        return filtered_menus
    
    def get_page_permissions(self, user: User, page_path: str) -> Dict[str, Any]:
        """获取页面操作权限"""
        # 这里应该从配置或数据库加载页面权限配置
        # 这里只是示例，实际需要完整的页面权限配置
        page_permissions_config = {
            "/projects/list": {
                "buttons": {
                    "create": "project:create",
                    "edit": "project:update",
                    "delete": "project:delete",
                    "export": "project:export",
                },
                "row_actions": {
                    "view": "project:read",
                    "edit": "project:update",
                    "delete": "project:delete",
                },
            },
        }
        
        page_config = page_permissions_config.get(page_path, {})
        
        # 计算按钮权限
        buttons = {}
        for button_name, required_permission in page_config.get("buttons", {}).items():
            buttons[button_name] = user.has_permission(required_permission)
        
        # 计算行操作权限
        row_actions = {}
        for action_name, required_permission in page_config.get("row_actions", {}).items():
            row_actions[action_name] = user.has_permission(required_permission)
        
        # 生成UI配置
        ui_config = {
            "show_create_button": buttons.get("create", False),
            "show_delete_button": buttons.get("delete", False),
            "show_export_button": buttons.get("export", False),
            "allow_row_edit": row_actions.get("edit", False),
            "allow_row_delete": row_actions.get("delete", False),
        }
        
        return {
            "buttons": buttons,
            "row_actions": row_actions,
            "ui_config": ui_config,
        }