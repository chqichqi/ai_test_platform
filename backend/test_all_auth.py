#!/usr/bin/env python3
"""
测试所有认证端点
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal

client = TestClient(app)

def test_all_auth_endpoints():
    """测试所有认证端点"""
    print("=" * 60)
    print("测试所有认证端点")
    print("=" * 60)
    
    # 1. 测试登录
    print("\n1. 测试登录")
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    print(f"  状态码: {login_response.status_code}")
    print(f"  成功: {login_response.json().get('success')}")
    
    if login_response.status_code != 200:
        print("  登录失败，退出测试")
        return
    
    login_data = login_response.json()
    access_token = login_data.get('data', {}).get('access_token')
    refresh_token = login_data.get('data', {}).get('refresh_token')
    
    # 2. 测试获取当前用户信息
    print("\n2. 测试获取当前用户信息")
    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {me_response.status_code}")
    print(f"  成功: {me_response.json().get('success')}")
    
    # 3. 测试获取用户权限
    print("\n3. 测试获取用户权限")
    permissions_response = client.get(
        "/api/v1/auth/permissions",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {permissions_response.status_code}")
    print(f"  成功: {permissions_response.json().get('success')}")
    
    # 4. 测试刷新令牌
    print("\n4. 测试刷新令牌")
    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    print(f"  状态码: {refresh_response.status_code}")
    print(f"  成功: {refresh_response.json().get('success')}")
    
    if refresh_response.status_code == 200:
        new_tokens = refresh_response.json().get('data', {})
        new_access_token = new_tokens.get('access_token')
        new_refresh_token = new_tokens.get('refresh_token')
        
        # 使用新令牌测试
        print("\n5. 使用新令牌测试获取用户信息")
        me_response2 = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        print(f"  状态码: {me_response2.status_code}")
        print(f"  成功: {me_response2.json().get('success')}")
        
        # 使用新刷新令牌测试登出
        access_token_to_logout = new_access_token
    else:
        access_token_to_logout = access_token
    
    # 6. 测试登出
    print("\n6. 测试登出")
    logout_response = client.post(
        "/api/v1/auth/logout",
        json={"token": access_token_to_logout}
    )
    print(f"  状态码: {logout_response.status_code}")
    print(f"  成功: {logout_response.json().get('success')}")
    
    # 7. 测试密码重置请求
    print("\n7. 测试密码重置请求")
    reset_request_response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@ai-test-platform.com"}
    )
    print(f"  状态码: {reset_request_response.status_code}")
    print(f"  成功: {reset_request_response.json().get('success')}")
    
    # 8. 测试注册（需要新用户）
    print("\n8. 测试用户注册")
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser_new",
            "email": "testnew@example.com",
            "password": "Test123!",
            "confirm_password": "Test123!",
            "full_name": "Test User New",
            "department": "Testing",
            "position": "QA Engineer"
        }
    )
    print(f"  状态码: {register_response.status_code}")
    print(f"  成功: {register_response.json().get('success')}")
    
    print("\n" + "=" * 60)
    print("所有端点测试完成")
    print("=" * 60)

if __name__ == "__main__":
    # 创建数据库会话
    db = SessionLocal()
    try:
        test_all_auth_endpoints()
    finally:
        db.close()