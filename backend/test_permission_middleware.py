#!/usr/bin/env python3
"""
测试权限中间件
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal

client = TestClient(app)

def test_permission_middleware():
    """测试权限中间件"""
    print("=" * 60)
    print("测试权限中间件")
    print("=" * 60)
    
    # 1. 首先登录获取访问令牌
    print("\n1. 登录获取访问令牌")
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
    print(f"  获取到访问令牌")
    
    # 2. 测试公开端点（不需要认证）
    print("\n2. 测试公开端点")
    public_response = client.get("/api/v1/test/public")
    print(f"  状态码: {public_response.status_code}")
    print(f"  成功: {public_response.json().get('success')}")
    
    # 3. 测试只需要认证的端点
    print("\n3. 测试只需要认证的端点")
    auth_only_response = client.get(
        "/api/v1/test/auth-only",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {auth_only_response.status_code}")
    print(f"  成功: {auth_only_response.json().get('success')}")
    
    # 4. 测试需要项目读取权限的端点（admin用户应该有这个权限）
    print("\n4. 测试需要项目读取权限的端点")
    project_read_response = client.get(
        "/api/v1/test/project-read",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {project_read_response.status_code}")
    print(f"  成功: {project_read_response.json().get('success')}")
    
    # 5. 测试需要项目创建权限的端点（admin用户应该有这个权限）
    print("\n5. 测试需要项目创建权限的端点")
    project_create_response = client.get(
        "/api/v1/test/project-create",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {project_create_response.status_code}")
    print(f"  成功: {project_create_response.json().get('success')}")
    
    # 6. 测试需要多个权限的端点
    print("\n6. 测试需要多个权限的端点")
    multiple_perms_response = client.get(
        "/api/v1/test/multiple-permissions",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {multiple_perms_response.status_code}")
    print(f"  成功: {multiple_perms_response.json().get('success')}")
    
    # 7. 测试需要管理员权限的端点
    print("\n7. 测试需要管理员权限的端点")
    admin_only_response = client.get(
        "/api/v1/test/admin-only",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    print(f"  状态码: {admin_only_response.status_code}")
    print(f"  成功: {admin_only_response.json().get('success')}")
    
    # 8. 测试没有令牌的情况
    print("\n8. 测试没有令牌的情况")
    no_token_response = client.get("/api/v1/test/auth-only")
    print(f"  状态码: {no_token_response.status_code}")
    print(f"  成功: {no_token_response.json().get('success') if no_token_response.status_code == 200 else '失败（预期）'}")
    
    # 9. 测试无效令牌的情况
    print("\n9. 测试无效令牌的情况")
    invalid_token_response = client.get(
        "/api/v1/test/auth-only",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    print(f"  状态码: {invalid_token_response.status_code}")
    print(f"  成功: {invalid_token_response.json().get('success') if invalid_token_response.status_code == 200 else '失败（预期）'}")
    
    # 10. 测试新注册的用户（只有默认权限）
    print("\n10. 测试新注册的用户")
    # 先注册一个新用户
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "test_permission_user",
            "email": "test_permission@example.com",
            "password": "Test123!",
            "confirm_password": "Test123!",
            "full_name": "Test Permission User",
            "department": "Testing",
            "position": "Tester"
        }
    )
    
    if register_response.status_code == 201:
        print("  新用户注册成功")
        # 新用户登录
        new_user_login = client.post(
            "/api/v1/auth/login",
            data={"username": "test_permission_user", "password": "Test123!"}
        )
        
        if new_user_login.status_code == 200:
            new_user_token = new_user_login.json().get('data', {}).get('access_token')
            print("  新用户登录成功")
            
            # 测试新用户访问需要项目创建权限的端点（应该失败）
            print("  测试新用户访问需要项目创建权限的端点")
            new_user_project_create = client.get(
                "/api/v1/test/project-create",
                headers={"Authorization": f"Bearer {new_user_token}"}
            )
            print(f"    状态码: {new_user_project_create.status_code}")
            print(f"    成功: {new_user_project_create.json().get('success') if new_user_project_create.status_code == 200 else '失败（预期）'}")
            
            # 测试新用户访问只需要认证的端点（应该成功）
            print("  测试新用户访问只需要认证的端点")
            new_user_auth_only = client.get(
                "/api/v1/test/auth-only",
                headers={"Authorization": f"Bearer {new_user_token}"}
            )
            print(f"    状态码: {new_user_auth_only.status_code}")
            print(f"    成功: {new_user_auth_only.json().get('success')}")
    else:
        print(f"  新用户注册失败: {register_response.text}")
    
    print("\n" + "=" * 60)
    print("权限中间件测试完成")
    print("=" * 60)

if __name__ == "__main__":
    # 创建数据库会话
    db = SessionLocal()
    try:
        test_permission_middleware()
    finally:
        db.close()