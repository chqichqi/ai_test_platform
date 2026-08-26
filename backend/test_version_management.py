"""
项目管理优化功能测试脚本

测试功能:
1. 创建版本时需求文档必填
2. 创建版本时自动生成测试用例和 XMind
3. 版本删除操作
4. 需求文档更新并重新生成测试用例
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8008/api/v1"

# 测试配置
TEST_PROJECT_ID = 1
TEST_VERSION_NUMBER = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"


def test_create_version_with_requirement():
    """测试 1: 创建版本时需求文档必填"""
    print("\n=== 测试 1: 创建版本时需求文档必填 ===")
    
    # 测试用例 1.1: 不提供需求文档，应该失败
    print("\n1.1 测试不提供需求文档（应失败）")
    payload = {
        "project_id": TEST_PROJECT_ID,
        "version_number": TEST_VERSION_NUMBER + "_no_req",
        "version_name": "测试版本-无需求",
        "description": "测试不提供需求文档"
        # 故意不提供 requirement_doc
    }
    
    response = requests.post(f"{BASE_URL}/versions/", json=payload)
    print(f"状态码：{response.status_code}")
    print(f"响应：{response.json()}")
    
    if response.status_code == 422:
        print("✓ 测试通过：缺少必填字段时返回验证错误")
    else:
        print("✗ 测试失败：应该返回验证错误")
    
    # 测试用例 1.2: 提供需求文档，应该成功
    print("\n1.2 测试提供需求文档（应成功）")
    payload = {
        "project_id": TEST_PROJECT_ID,
        "version_number": TEST_VERSION_NUMBER,
        "version_name": "测试版本-有需求",
        "description": "测试提供需求文档",
        "requirement_doc": """
# 用户管理模块需求文档

## 1. 用户注册
- 支持邮箱注册
- 支持手机号注册
- 用户名长度 3-20 字符
- 密码长度至少 8 位，包含字母和数字

## 2. 用户登录
- 支持账号密码登录
- 支持短信验证码登录
- 支持第三方登录（微信、QQ）
- 登录失败 5 次后锁定 30 分钟

## 3. 个人信息
- 查看个人资料
- 修改头像
- 修改昵称
- 修改绑定邮箱
- 修改绑定手机

## 4. 权限管理
- 角色分配
- 权限控制
- 菜单权限
- 按钮权限
"""
    }
    
    response = requests.post(f"{BASE_URL}/versions/", json=payload)
    print(f"状态码：{response.status_code}")
    
    if response.status_code == 201:
        version_data = response.json()
        version_id = version_data.get("id")
        print(f"✓ 测试通过：版本创建成功，ID={version_id}")
        return version_id
    else:
        print(f"✗ 测试失败：{response.json()}")
        return None


def test_auto_generate_assets(version_id: int):
    """测试 2: 自动生成测试用例和 XMind"""
    print("\n=== 测试 2: 自动生成测试用例和 XMind ===")
    
    print(f"\n2.1 手动触发资产生成 (version_id={version_id})")
    response = requests.post(f"{BASE_URL}/versions/{version_id}/generate-assets")
    print(f"状态码：{response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 测试通过：资产生成成功")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        data = result.get("data", {})
        tc_count = data.get("test_cases_count", 0)
        print(f"生成结果：{tc_count} 个测试用例")
        return True
    else:
        print(f"✗ 测试失败：{response.json()}")
        return False


def test_version_delete(version_id: int):
    """测试 3: 版本删除操作"""
    print("\n=== 测试 3: 版本删除操作 ===")
    
    print(f"\n3.1 测试删除版本 (version_id={version_id})")
    response = requests.delete(f"{BASE_URL}/versions/{version_id}")
    print(f"状态码：{response.status_code}")
    
    if response.status_code == 204:
        print("✓ 测试通过：版本删除成功")
        return True
    elif response.status_code == 400:
        print(f"⚠ 注意：{response.json().get('detail', '未知错误')}")
        print("  只有规划中状态的版本可以删除")
        return False
    else:
        print(f"✗ 测试失败：{response.json()}")
        return False


def test_requirement_update_and_regenerate():
    """测试 4: 需求文档更新并重新生成测试用例"""
    print("\n=== 测试 4: 需求文档更新并重新生成 ===")
    
    # 先创建一个新版本用于测试
    print("\n4.1 创建测试版本")
    payload = {
        "project_id": TEST_PROJECT_ID,
        "version_number": f"{TEST_VERSION_NUMBER}_update_test",
        "version_name": "测试版本-更新测试",
        "description": "测试需求文档更新功能",
        "requirement_doc": "# 初始需求\n\n功能 1: 用户登录"
    }
    
    response = requests.post(f"{BASE_URL}/versions/", json=payload, params={"auto_generate": False})
    if response.status_code != 201:
        print(f"✗ 创建版本失败：{response.json()}")
        return
    
    version = response.json()
    version_id = version.get("id")
    print(f"版本创建成功，ID={version_id}")
    
    # 获取版本的需求文档 ID
    print("\n4.2 获取需求文档列表")
    response = requests.get(f"{BASE_URL}/requirements/", params={"version_id": version_id})
    if response.status_code == 200:
        docs = response.json().get("items", [])
        if docs:
            doc_id = docs[0].get("id")
            print(f"找到需求文档，ID={doc_id}")
            
            # 更新需求文档并重新生成测试用例
            print("\n4.3 更新需求文档并重新生成测试用例")
            update_payload = {
                "content": """
# 用户管理模块需求文档（更新版）

## 1. 用户注册
- 支持邮箱注册
- 支持手机号注册
- 用户名长度 3-20 字符
- 密码长度至少 8 位，包含字母和数字和特殊字符

## 2. 用户登录
- 支持账号密码登录
- 支持短信验证码登录
- 支持第三方登录（微信、QQ、微博）
- 登录失败 5 次后锁定 30 分钟
- 支持扫码登录

## 3. 个人信息管理
- 查看个人资料
- 修改头像（支持 JPG、PNG 格式）
- 修改昵称
- 修改绑定邮箱
- 修改绑定手机
- 注销账号

## 4. 权限管理
- 角色分配
- 权限控制
- 菜单权限
- 按钮权限
- 数据权限
"""
            }
            
            response = requests.post(
                f"{BASE_URL}/requirements/{doc_id}/update-and-regenerate",
                json=update_payload,
                params={"regenerate": True}
            )
            
            print(f"状态码：{response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"✓ 测试通过：需求文档更新并重新生成成功")
                print(json.dumps(result, ensure_ascii=False, indent=2))
                
                data = result.get("data", {})
                tc_count = data.get("test_cases_count", 0)
                print(f"生成结果：{tc_count} 个测试用例")
            else:
                print(f"✗ 测试失败：{response.json()}")
        else:
            print("✗ 未找到需求文档")
    else:
        print(f"✗ 获取需求文档失败：{response.json()}")


def main():
    """主测试函数"""
    print("=" * 60)
    print("项目管理优化功能测试")
    print("=" * 60)
    
    # 测试 1: 创建版本时需求文档必填
    version_id = test_create_version_with_requirement()
    
    if version_id:
        # 测试 2: 自动生成资产（如果创建时没有自动生成）
        test_auto_generate_assets(version_id)
        
        # 测试 3: 删除版本
        test_version_delete(version_id)
    
    # 测试 4: 需求文档更新并重新生成
    test_requirement_update_and_regenerate()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
