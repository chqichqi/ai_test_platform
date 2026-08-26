#!/usr/bin/env python3
"""
测试登出端点
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal

client = TestClient(app)

def test_logout():
    """测试登出"""
    # 首先登录获取访问令牌
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
        access_token = data.get('access_token')
        print(f"Got access token: {access_token[:50]}...")
        
        # 测试登出端点
        logout_response = client.post(
            "/api/v1/auth/logout",
            json={"token": access_token}
        )
        
        print(f"\nLogout response status: {logout_response.status_code}")
        print(f"Logout response: {logout_response.text}")

if __name__ == "__main__":
    # 创建数据库会话
    db = SessionLocal()
    try:
        test_logout()
    finally:
        db.close()