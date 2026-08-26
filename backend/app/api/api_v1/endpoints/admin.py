"""
系统管理API端点（简化版）
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def admin_dashboard():
    """管理员仪表盘"""
    return {"message": "Admin dashboard - under development"}