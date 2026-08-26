"""
认证相关的Pydantic模式定义
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, validator


class Token(BaseModel):
    """令牌响应模型"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    token: Optional[str] = None  # 兼容字段，等同于access_token
    user: Optional[dict] = None


class TokenResponse(BaseModel):
    """统一响应格式的令牌响应"""
    success: bool = True
    code: int = 200
    message: str = "Login successful"
    data: Token


class TokenData(BaseModel):
    """令牌数据模型"""
    username: Optional[str] = None
    exp: Optional[datetime] = None


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱地址")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    department: Optional[str] = Field(None, max_length=50, description="部门")
    position: Optional[str] = Field(None, max_length=50, description="职位")


class UserCreate(UserBase):
    """用户创建模型"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    
    @validator('password')
    def validate_password(cls, v):
        """密码验证"""
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        # 可以添加更多密码强度验证
        return v


class UserRegister(UserCreate):
    """用户注册模型"""
    confirm_password: str = Field(..., description="确认密码")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        """验证密码是否匹配"""
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v


class UserLogin(BaseModel):
    """用户登录模型"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    """用户更新模型"""
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    department: Optional[str] = Field(None, max_length=50, description="部门")
    position: Optional[str] = Field(None, max_length=50, description="职位")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    phone: Optional[str] = Field(None, description="电话")


class UserResponse(UserBase):
    """用户响应模型"""
    id: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    avatar_url: Optional[str]
    phone: Optional[str]
    last_login: Optional[datetime]
    last_active: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    roles: List[str] = []
    permissions: List[str] = []
    
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象转换，处理roles和permissions字段"""
        # 先获取基础数据
        data = {
            "id": str(obj.id),
            "username": obj.username,
            "email": obj.email,
            "full_name": obj.full_name,
            "department": obj.department,
            "position": obj.position,
            "is_active": obj.is_active,
            "is_superuser": obj.is_superuser,
            "is_verified": obj.is_verified,
            "avatar_url": obj.avatar_url,
            "phone": obj.phone,
            "last_login": obj.last_login,
            "last_active": obj.last_active,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        
        # 处理roles字段
        if hasattr(obj, 'roles'):
            if obj.roles:
                # 如果是Role对象列表，提取name属性
                if hasattr(obj.roles[0], 'name'):
                    data["roles"] = [role.name for role in obj.roles]
                else:
                    data["roles"] = list(obj.roles)
            else:
                data["roles"] = []
        
        # 处理permissions字段
        if hasattr(obj, 'get_all_permissions'):
            data["permissions"] = obj.get_all_permissions()
        else:
            data["permissions"] = []
        
        return cls(**data)
    
    class Config:
        from_attributes = True


class PasswordChange(BaseModel):
    """密码修改模型"""
    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")
    confirm_password: str = Field(..., description="确认新密码")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        """验证新密码是否匹配"""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('New passwords do not match')
        return v
    
    @validator('new_password')
    def validate_new_password(cls, v, values):
        """验证新密码不能与当前密码相同"""
        if 'current_password' in values and v == values['current_password']:
            raise ValueError('New password must be different from current password')
        return v


class PasswordResetRequest(BaseModel):
    """密码重置请求模型"""
    email: EmailStr = Field(..., description="邮箱地址")


class PasswordResetConfirm(BaseModel):
    """密码重置确认模型"""
    token: str = Field(..., description="重置令牌")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")
    confirm_password: str = Field(..., description="确认新密码")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        """验证新密码是否匹配"""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


class RoleBase(BaseModel):
    """角色基础模型"""
    name: str = Field(..., min_length=2, max_length=50, description="角色名称")
    description: Optional[str] = Field(None, description="角色描述")
    is_default: bool = Field(False, description="是否默认角色")


class RoleCreate(RoleBase):
    """角色创建模型"""
    permission_codes: List[str] = Field(default=[], description="权限代码列表")


class RoleUpdate(BaseModel):
    """角色更新模型"""
    description: Optional[str] = Field(None, description="角色描述")
    is_default: Optional[bool] = Field(None, description="是否默认角色")
    permission_codes: Optional[List[str]] = Field(None, description="权限代码列表")


class RoleResponse(RoleBase):
    """角色响应模型"""
    id: str
    is_system: bool
    permissions: List[str] = []
    user_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PermissionBase(BaseModel):
    """权限基础模型"""
    code: str = Field(..., description="权限代码")
    name: str = Field(..., description="权限名称")
    description: Optional[str] = Field(None, description="权限描述")
    category: Optional[str] = Field(None, description="权限分类")
    module: Optional[str] = Field(None, description="所属模块")


class PermissionResponse(PermissionBase):
    """权限响应模型"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserRoleAssignment(BaseModel):
    """用户角色分配模型"""
    user_id: str = Field(..., description="用户ID")
    role_id: str = Field(..., description="角色ID")


class MenuItem(BaseModel):
    """菜单项模型"""
    id: str = Field(..., description="菜单ID")
    name: str = Field(..., description="菜单名称")
    icon: Optional[str] = Field(None, description="菜单图标")
    path: str = Field(..., description="路由路径")
    order: int = Field(0, description="排序")
    children: List['MenuItem'] = Field(default=[], description="子菜单")
    required_permission: Optional[str] = Field(None, description="所需权限")


class MenuResponse(BaseModel):
    """菜单响应模型"""
    menus: List[MenuItem] = Field(default=[], description="菜单列表")


class PagePermission(BaseModel):
    """页面权限模型"""
    page_path: str = Field(..., description="页面路径")
    buttons: dict = Field(default={}, description="按钮权限")
    row_actions: dict = Field(default={}, description="行操作权限")
    ui_config: dict = Field(default={}, description="UI配置")


# 解决循环引用
MenuItem.update_forward_refs()