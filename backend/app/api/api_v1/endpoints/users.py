"""
用户管理API端点（简化版）
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def get_users():
    """获取用户列表"""
    return {"message": "Users endpoint - under development"}


@router.get("/{user_id}")
async def get_user(user_id: str):
    """获取用户详情"""
    return {"message": f"Get user {user_id} - under development"}