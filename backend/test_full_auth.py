#!/usr/bin/env python3
"""
完整测试认证API流程
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def print_step(step):
    """打印步骤标题"""
    print(f"\n{'='*60}")
    print(f"步骤: {step}")
    print(f"{'='*60}")

def test_register():
    """测试用户注册"""
    print_step("1. 测试用户注册")
    
    user_data = {
        "username": "fulltest",
        "email": "fulltest@example.com",
        "password": "fulltest123",
        "confirm_password": "fulltest123",
        "full_name": "Full Test User",
        "department": "测试部",
        "position": "高级测试工程师"
    }
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json=user_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 201:
        result = response.json()
        print(f"[OK] 注册成功")
        print(f"  用户ID: {result['data']['id']}")
        print(f"  用户名: {result['data']['username']}")
        print(f"  角色: {result['data']['roles']}")
        return True
    else:
        print(f"[FAIL] 注册失败: {response.text}")
        return False

def test_login():
    """测试用户登录"""
    print_step("2. 测试用户登录")
    
    # 使用表单数据格式
    login_data = {
        "username": "fulltest",
        "password": "fulltest123"
    }
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"[OK] 登录成功")
        print(f"  访问令牌: {result['data']['access_token'][:30]}...")
        print(f"  刷新令牌: {result['data']['refresh_token'][:30]}...")
        print(f"  用户: {result['data']['user']['username']}")
        
        # 保存令牌
        tokens = {
            'access_token': result['data']['access_token'],
            'refresh_token': result['data']['refresh_token']
        }
        return tokens
    else:
        print(f"[FAIL] 登录失败: {response.text}")
        return None

def test_get_current_user(access_token):
    """测试获取当前用户信息"""
    print_step("3. 测试获取当前用户信息")
    
    if not access_token:
        print("[FAIL] 跳过测试（无访问令牌）")
        return False
    
    response = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"[OK] 获取用户信息成功")
        print(f"  用户名: {result['data']['username']}")
        print(f"  邮箱: {result['data']['email']}")
        print(f"  角色: {result['data']['roles']}")
        print(f"  权限数量: {len(result['data']['permissions'])}")
        return True
    else:
        print(f"[FAIL] 获取用户信息失败: {response.text}")
        return False

def test_get_permissions(access_token):
    """测试获取用户权限"""
    print_step("4. 测试获取用户权限")
    
    if not access_token:
        print("[FAIL] 跳过测试（无访问令牌）")
        return False
    
    response = requests.get(
        f"{BASE_URL}/auth/permissions",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"[OK] 获取权限成功")
        print(f"  是否超级用户: {result['data']['is_superuser']}")
        print(f"  权限列表: {', '.join(result['data']['permissions'][:5])}...")
        return True
    else:
        print(f"[FAIL] 获取权限失败: {response.text}")
        return False

def test_refresh_token(refresh_token):
    """测试刷新令牌"""
    print_step("5. 测试刷新令牌")
    
    if not refresh_token:
        print("[FAIL] 跳过测试（无刷新令牌）")
        return None
    
    response = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"Content-Type": "application/json"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"[OK] 刷新令牌成功")
        print(f"  新访问令牌: {result['data']['access_token'][:30]}...")
        print(f"  新刷新令牌: {result['data']['refresh_token'][:30]}...")
        return result['data']['access_token']
    else:
        print(f"[FAIL] 刷新令牌失败: {response.text}")
        return None

def test_wrong_password():
    """测试错误密码"""
    print_step("6. 测试错误密码登录")
    
    login_data = {
        "username": "fulltest",
        "password": "wrongpassword"
    }
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 401:
        result = response.json()
        print(f"[OK] 错误密码被正确拒绝")
        print(f"  错误信息: {result['message']}")
        return True
    else:
        print(f"[FAIL] 错误密码测试失败: {response.text}")
        return False

def test_invalid_token():
    """测试无效令牌"""
    print_step("7. 测试无效令牌")
    
    invalid_token = "invalid.token.here"
    
    response = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {invalid_token}"}
    )
    
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 401:
        result = response.json()
        print(f"[OK] 无效令牌被正确拒绝")
        print(f"  错误信息: {result['message']}")
        return True
    else:
        print(f"[FAIL] 无效令牌测试失败: {response.text}")
        return False

def main():
    """主测试函数"""
    print("开始测试AI Agent Test Platform完整认证流程")
    print("="*60)
    
    success_count = 0
    total_tests = 7
    
    # 1. 测试注册
    if test_register():
        success_count += 1
    
    # 2. 测试登录
    tokens = test_login()
    if tokens:
        success_count += 1
    
    # 3. 测试获取当前用户
    if tokens and test_get_current_user(tokens['access_token']):
        success_count += 1
    
    # 4. 测试获取权限
    if tokens and test_get_permissions(tokens['access_token']):
        success_count += 1
    
    # 5. 测试刷新令牌
    if tokens and test_refresh_token(tokens['refresh_token']):
        success_count += 1
    
    # 6. 测试错误密码
    if test_wrong_password():
        success_count += 1
    
    # 7. 测试无效令牌
    if test_invalid_token():
        success_count += 1
    
    # 总结
    print_step("测试总结")
    print(f"测试完成: {success_count}/{total_tests} 通过")
    
    if success_count == total_tests:
        print("[OK] 所有测试通过！认证系统工作正常。")
    else:
        print(f"[WARN] {total_tests - success_count} 个测试失败，需要检查。")
    
    print(f"\nAPI文档: http://localhost:8000/docs")
    print(f"控制面板: http://localhost:8000/")

if __name__ == "__main__":
    main()