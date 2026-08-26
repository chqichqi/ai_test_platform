"""
用户和权限模型定义
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, JSON,
    ForeignKey, Table, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, validates

from app.core.models.base import BaseModel
from app.core.config import settings


role_permission = Table(
    'role_permission',
    BaseModel.metadata,
    Column('role_id', String(36), ForeignKey('role.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', String(36), ForeignKey('permission.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow),
    Index('idx_role_permission_role_id', 'role_id'),
    Index('idx_role_permission_permission_id', 'permission_id'),
)

user_role = Table(
    'user_role',
    BaseModel.metadata,
    Column('user_id', String(36), ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', String(36), ForeignKey('role.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime, default=datetime.utcnow),
    Column('assigned_by', String(36), ForeignKey('user.id')),
    Index('idx_user_role_user_id', 'user_id'),
    Index('idx_user_role_role_id', 'role_id'),
)


class User(BaseModel):
    """用户模型"""
    
    __tablename__ = 'user'
    
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200))
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    avatar_url = Column(String(500))
    phone = Column(String(50))
    department = Column(String(100))
    position = Column(String(100))
    
    last_login = Column(DateTime)
    last_active = Column(DateTime)
    
    meta_data = Column("metadata", JSON, default=dict)
    
    roles = relationship(
        'Role', 
        secondary=user_role,
        primaryjoin="User.id == user_role.c.user_id",
        secondaryjoin="Role.id == user_role.c.role_id",
        back_populates='users',
        lazy='selectin'
    )
    
    owned_projects = relationship(
        'Project',
        back_populates='owner',
        foreign_keys='Project.owner_id',
        lazy='dynamic'
    )
    
    project_memberships = relationship(
        'ProjectMember',
        back_populates='user',
        foreign_keys='ProjectMember.user_id',
        lazy='dynamic'
    )
    
    @validates('email')
    def validate_email(self, key, email):
        """验证邮箱格式"""
        if '@' not in email:
            raise ValueError('Invalid email address')
        return email.lower()
    
    @validates('username')
    def validate_username(self, key, username):
        """验证用户名格式"""
        if not username or len(username) < 3:
            raise ValueError('Username must be at least 3 characters')
        return username.lower()
    
    def has_permission(self, permission_code: str) -> bool:
        """检查用户是否有指定权限"""
        if self.is_superuser:
            return True
        
        for role in self.roles:
            for permission in role.permissions:
                if permission.code == permission_code:
                    return True
        return False
    
    def has_role(self, role_name: str) -> bool:
        """检查用户是否有指定角色"""
        return any(role.name == role_name for role in self.roles)
    
    def get_all_permissions(self) -> List[str]:
        """获取用户所有权限代码"""
        permissions = set()
        
        for role in self.roles:
            for permission in role.permissions:
                permissions.add(permission.code)
        
        return list(permissions)
    
    def to_dict(self, exclude: Optional[list] = None):
        """转换为字典（排除敏感信息）"""
        exclude = exclude or []
        exclude.extend(['password_hash', 'meta_data'])
        
        data = super().to_dict(exclude)
        
        data['roles'] = [role.name for role in self.roles]
        data['permissions'] = self.get_all_permissions()
        
        return data


class Role(BaseModel):
    """角色模型"""
    
    __tablename__ = 'role'
    
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text)
    is_default = Column(Boolean, default=False, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    
    users = relationship(
        'User', 
        secondary=user_role,
        primaryjoin="Role.id == user_role.c.role_id",
        secondaryjoin="User.id == user_role.c.user_id",
        back_populates='roles',
        lazy='dynamic'
    )
    
    permissions = relationship(
        'Permission',
        secondary=role_permission,
        back_populates='roles',
        lazy='selectin'
    )
    
    @validates('name')
    def validate_name(self, key, name):
        """验证角色名格式"""
        if not name or len(name) < 2:
            raise ValueError('Role name must be at least 2 characters')
        return name.lower()
    
    def to_dict(self, exclude: Optional[list] = None):
        """转换为字典"""
        data = super().to_dict(exclude)
        
        data['permissions'] = [perm.code for perm in self.permissions]
        
        return data


class Permission(BaseModel):
    """权限模型"""
    
    __tablename__ = 'permission'
    
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50))
    module = Column(String(50))
    
    roles = relationship(
        'Role',
        secondary=role_permission,
        back_populates='permissions',
        lazy='dynamic'
    )
    
    @validates('code')
    def validate_code(self, key, code):
        """验证权限代码格式"""
        if ':' not in code:
            raise ValueError('Permission code must contain colon (e.g., "project:read")')
        return code
    
    def __repr__(self):
        return f"<Permission(code='{self.code}', name='{self.name}')>"