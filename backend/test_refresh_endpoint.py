#!/usr/bin/env python3
"""
测试刷新令牌端点
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db, SessionLocal
from app.core.services.auth_service import AuthService

client = TestClient(app)

def test_refresh_token():
    """测试刷新令牌"""
    # 首先登录获取刷新令牌
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    
    print(f"Login response status: {login_response.status_code}")
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.text}")
        return
    
    login_data = login_response.json()
    print(f"Login success: {login_data.get('success')}")
    
    if login_data.get('success'):
        data = login_data.get('data', {})
        refresh_token = data.get('refresh_token')
        print(f"Got refresh token: {refresh_token[:50]}...")
        
        # 测试刷新令牌端点
        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        
        print(f"\nRefresh response status: {refresh_response.status_code}")
        print(f"Refresh response: {refresh_response.text}")

if __name__ == "__main__":
    # 创建数据库会话
    db = SessionLocal()
    try:
        test_refresh_token()
    finally:
        db.close()