#!/usr/bin/env python3
"""
测试完整的认证流程
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000/api/v1/auth"

def print_response(response, label="Response"):
    """打印响应信息"""
    print(f"\n{'='*60}")
    print(f"{label}:")
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    try:
        data = response.json()
        print(f"Body: {json.dumps(data, indent=2, ensure_ascii=False)}")
    except:
        print(f"Body: {response.text}")
    print(f"{'='*60}")

def test_register():
    """测试用户注册"""
    print("\n1. 测试用户注册")
    
    # 测试数据
    user_data = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
        "department": "Testing",
        "position": "QA Engineer"
    }
    
    response = requests.post(f"{BASE_URL}/register", json=user_data)
    print_response(response, "注册响应")
    
    if response.status_code == 201:
        print("[SUCCESS] 注册成功")
        return user_data
    else:
        print("[FAILED] 注册失败")
        return None

def test_login(username, password):
    """测试用户登录"""
    print("\n2. 测试用户登录")
    
    # 使用表单数据格式
    form_data = {
        "username": username,
        "password": password
    }
    
    response = requests.post(
        f"{BASE_URL}/login",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    print_response(response, "登录响应")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("[SUCCESS] 登录成功")
            return data.get("data", {})
    else:
        print("[FAILED] 登录失败")
    
    return None

def test_get_current_user(access_token):
    """测试获取当前用户信息"""
    print("\n3. 测试获取当前用户信息")
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(f"{BASE_URL}/me", headers=headers)
    print_response(response, "当前用户信息")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("[SUCCESS] 获取当前用户信息成功")
            return data.get("data", {})
    else:
        print("[FAILED] 获取当前用户信息失败")
    
    return None

def test_get_permissions(access_token):
    """测试获取用户权限"""
    print("\n4. 测试获取用户权限")
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(f"{BASE_URL}/permissions", headers=headers)
    print_response(response, "用户权限")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("[SUCCESS] 获取用户权限成功")
            return data.get("data", {})
    else:
        print("[FAILED] 获取用户权限失败")
    
    return None

def test_refresh_token(refresh_token):
    """测试刷新令牌"""
    print("\n5. 测试刷新令牌")
    
    data = {
        "refresh_token": refresh_token
    }
    
    response = requests.post(f"{BASE_URL}/refresh", json=data)
    print_response(response, "刷新令牌响应")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("[SUCCESS] 刷新令牌成功")
            return data.get("data", {})
    else:
        print("[FAILED] 刷新令牌失败")
    
    return None

def test_logout(access_token):
    """测试用户登出"""
    print("\n6. 测试用户登出")
    
    data = {
        "token": access_token
    }
    
    response = requests.post(f"{BASE_URL}/logout", json=data)
    print_response(response, "登出响应")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("[SUCCESS] 登出成功")
            return True
    else:
        print("[FAILED] 登出失败")
    
    return False

def test_password_reset(email):
    """测试密码重置流程"""
    print("\n7. 测试密码重置请求")
    
    # 请求密码重置
    reset_request = {
        "email": email
    }
    
    response = requests.post(f"{BASE_URL}/password-reset/request", json=reset_request)
    print_response(response, "密码重置请求响应")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("[SUCCESS] 密码重置请求成功")
            return True
    else:
        print("[FAILED] 密码重置请求失败")
    
    return False

def main():
    """主测试函数"""
    print("开始测试完整的认证流程")
    print(f"Base URL: {BASE_URL}")
    
    # 1. 测试注册
    user_data = test_register()
    if not user_data:
        print("注册失败，退出测试")
        return
    
    # 2. 测试登录
    token_data = test_login(user_data["username"], user_data["password"])
    if not token_data:
        print("登录失败，退出测试")
        return
    
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    
    if not access_token or not refresh_token:
        print("未获取到令牌，退出测试")
        return
    
    # 3. 测试获取当前用户信息
    user_info = test_get_current_user(access_token)
    
    # 4. 测试获取用户权限
    permissions = test_get_permissions(access_token)
    
    # 5. 测试刷新令牌
    new_token_data = test_refresh_token(refresh_token)
    if new_token_data:
        new_access_token = new_token_data.get("access_token")
        new_refresh_token = new_token_data.get("refresh_token")
        
        # 使用新令牌测试获取用户信息
        if new_access_token:
            print("\n使用新令牌测试获取用户信息")
            test_get_current_user(new_access_token)
    
    # 6. 测试登出
    test_logout(access_token)
    
    # 7. 测试密码重置
    test_password_reset(user_data["email"])
    
    print("\n" + "="*60)
    print("认证流程测试完成")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("[ERROR] 无法连接到服务器，请确保服务器正在运行")
        print("运行命令: python run.py")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 测试过程中发生错误: {str(e)}")
        sys.exit(1)