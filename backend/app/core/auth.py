"""
Authentication dependencies for FastAPI routers
"""
from typing import Optional
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.user import User
from app.core.services.auth_service import AuthService, oauth2_scheme


async def get_current_user_model(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """获取当前用户（返回User模型）"""
    # 先获取用户字典
    user_dict = AuthService.get_current_user(token=token, db=db)
    
    # 从数据库获取完整的User模型
    user = db.query(User).filter(
        User.id == user_dict["id"],
        User.deleted_at.is_(None)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user_model),
) -> User:
    """获取当前活跃用户（返回User模型）"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Inactive user",
        )
    return current_user