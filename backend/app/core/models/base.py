"""
基础模型定义
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, String
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base

from app.core.database import Base
from app.core.config import settings


class TimestampMixin:
    """时间戳混合类"""
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )
    deleted_at = Column(DateTime, nullable=True)


class BaseModel(Base, TimestampMixin):
    """基础模型类"""
    
    __abstract__ = True
    
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    
    @declared_attr
    def __tablename__(cls):
        """自动生成表名（将类名转换为蛇形命名）"""
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        if name.endswith('_model'):
            name = name[:-6]
        return name
    
    def to_dict(self, exclude: Optional[list] = None):
        """将模型转换为字典"""
        result = {}
        exclude = exclude or []
        
        for column in self.__table__.columns:
            column_name = column.name
            if column_name in exclude:
                continue
                
            value = getattr(self, column_name)
            
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, uuid.UUID):
                value = str(value)
                
            result[column_name] = value
            
        return result
    
    def update(self, **kwargs):
        """更新模型属性"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def soft_delete(self):
        """软删除"""
        self.deleted_at = datetime.utcnow()
    
    def is_deleted(self) -> bool:
        """检查是否已删除"""
        return self.deleted_at is not None
    
    def __repr__(self):
        """友好的字符串表示"""
        return f"<{self.__class__.__name__}(id={self.id})>"