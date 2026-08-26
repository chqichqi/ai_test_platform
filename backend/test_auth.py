#!/usr/bin/env python3
"""
测试认证API
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_health():
    """测试健康检查"""
    print("=== 测试健康检查 ===")
    response = requests.get("http://localhost:8000/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    print()

def test_register():
    """测试用户注册"""
    print("=== 测试用户注册 ===")
    
    # 测试数据
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "test123",
        "confirm_password": "test123",
        "full_name": "Test User",
        "department": "测试部",
        "position": "测试工程师"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json=user_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        if response.status_code == 200:
            print(f"注册成功: {response.json()}")
        else:
            print(f"注册失败: {response.text}")
            
    except Exception as e:
        print(f"请求异常: {str(e)}")
    
    print()

def test_login():
    """测试用户登录"""
    print("=== 测试用户登录 ===")
    
    # 使用OAuth2密码格式
    login_data = {
        "username": "testuser",
        "password": "test123"
    }
    
    try:
        # 使用表单数据格式（OAuth2兼容）
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"登录成功!")
            print(f"访问令牌: {result.get('access_token', '')[:30]}...")
            print(f"令牌类型: {result.get('token_type', '')}")
            print(f"过期时间: {result.get('expires_in', '')}秒")
            
            # 保存令牌用于后续测试
            if 'access_token' in result:
                return result['access_token']
        else:
            print(f"登录失败: {response.text}")
            
    except Exception as e:
        print(f"请求异常: {str(e)}")
    
    print()
    return None

def test_get_current_user(token):
    """测试获取当前用户信息"""
    if not token:
        print("=== 跳过获取用户信息测试（无令牌）===")
        return
    
    print("=== 测试获取当前用户信息 ===")
    
    try:
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            user_info = response.json()
            print(f"用户信息:")
            print(f"  用户名: {user_info.get('username', '')}")
            print(f"  邮箱: {user_info.get('email', '')}")
            print(f"  全名: {user_info.get('full_name', '')}")
            print(f"  角色: {user_info.get('roles', [])}")
            print(f"  权限: {user_info.get('permissions', [])[:5]}...")  # 只显示前5个
        else:
            print(f"获取失败: {response.text}")
            
    except Exception as e:
        print(f"请求异常: {str(e)}")
    
    print()

def test_get_permissions(token):
    """测试获取用户权限"""
    if not token:
        print("=== 跳过获取权限测试（无令牌）===")
        return
    
    print("=== 测试获取用户权限 ===")
    
    try:
        response = requests.get(
            f"{BASE_URL}/auth/permissions",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"权限信息:")
            print(f"  是否超级用户: {result.get('data', {}).get('is_superuser', False)}")
            print(f"  权限列表: {result.get('data', {}).get('permissions', [])[:10]}...")  # 只显示前10个
        else:
            print(f"获取失败: {response.text}")
            
    except Exception as e:
        print(f"请求异常: {str(e)}")
    
    print()

def main():
    """主测试函数"""
    print("开始测试AI Agent Test Platform认证API")
    print("=" * 50)
    
    # 测试健康检查
    test_health()
    
    # 测试用户注册
    test_register()
    
    # 测试用户登录
    token = test_login()
    
    # 测试获取用户信息
    test_get_current_user(token)
    
    # 测试获取权限
    test_get_permissions(token)
    
    print("测试完成!")
    print("=" * 50)

if __name__ == "__main__":
    main()