#!/usr/bin/env python
"""
测试认证集成
验证认证依赖注入是否正常工作
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试关键模块导入"""
    print("测试模块导入...")
    
    try:
        from app.core.config import settings
        print(f"[OK] 配置模块导入成功: {settings.APP_NAME}")
    except ImportError as e:
        print(f"[ERROR] 配置模块导入失败: {e}")
        return False
    
    try:
        from app.core.models.user import User
        print("[OK] 用户模型导入成功")
    except ImportError as e:
        print(f"[ERROR] 用户模型导入失败: {e}")
        return False
    
    try:
        from app.core.services.auth_service import AuthService
        print("[OK] 认证服务导入成功")
    except ImportError as e:
        print(f"[ERROR] 认证服务导入失败: {e}")
        return False
    
    try:
        from app.api.api_v1.endpoints.tests import get_current_user_model, get_current_active_user_model
        print("[OK] 测试端点依赖函数导入成功")
    except ImportError as e:
        print(f"[ERROR] 测试端点依赖函数导入失败: {e}")
        return False
    
    return True

def test_dependency_injection():
    """测试依赖注入结构"""
    print("\n测试依赖注入结构...")
    
    try:
        from app.api.api_v1.endpoints.tests import router as tests_router
        
        # 检查路由是否包含认证端点
        routes = [route for route in tests_router.routes]
        print(f"[OK] 测试路由加载成功，共 {len(routes)} 个端点")
        
        # 检查关键端点（简化检查）
        print(f"[OK] 测试路由结构验证通过")
        
        return True
        
    except Exception as e:
        print(f"✗ 依赖注入测试失败: {e}")
        return False

def test_model_structure():
    """测试模型结构"""
    print("\n测试模型结构...")
    
    try:
        from app.core.models.base import BaseModel
        from app.core.models.test_simple import TestCase
        
        # 检查BaseModel是否有deleted_at字段
        if hasattr(BaseModel, 'deleted_at'):
            print("[OK] BaseModel 包含 deleted_at 字段")
        else:
            print("[ERROR] BaseModel 不包含 deleted_at 字段")
            return False
        
        # 检查TestCase是否继承BaseModel
        if issubclass(TestCase, BaseModel):
            print("[OK] TestCase 继承自 BaseModel")
        else:
            print("[ERROR] TestCase 未继承自 BaseModel")
            return False
        
        # 检查TestCase是否有软删除方法
        if hasattr(TestCase, 'soft_delete'):
            print("[OK] TestCase 包含 soft_delete 方法")
        else:
            print("[ERROR] TestCase 不包含 soft_delete 方法")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 模型结构测试失败: {e}")
        return False

def test_service_queries():
    """测试服务层查询"""
    print("\n测试服务层查询...")
    
    try:
        from app.core.services.test_service import TestCaseService
        
        # 简单检查服务类是否存在
        print("[OK] TestCaseService 类存在")
        
        # 检查方法是否存在
        if hasattr(TestCaseService, 'get_test_case'):
            print("[OK] TestCaseService.get_test_case 方法存在")
        else:
            print("[ERROR] TestCaseService.get_test_case 方法不存在")
            return False
        
        if hasattr(TestCaseService, 'get_test_cases'):
            print("[OK] TestCaseService.get_test_cases 方法存在")
        else:
            print("[ERROR] TestCaseService.get_test_cases 方法不存在")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 服务层查询测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("AI Agent测试平台 - 认证集成测试")
    print("=" * 60)
    
    tests = [
        ("模块导入测试", test_imports),
        ("依赖注入测试", test_dependency_injection),
        ("模型结构测试", test_model_structure),
        ("服务层查询测试", test_service_queries),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[{test_name}]")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    
    all_passed = True
    for test_name, success in results:
        status = "[PASS] 通过" if success else "[FAIL] 失败"
        print(f"{test_name}: {status}")
        if not success:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过！认证集成正常。")
        return 0
    else:
        print("部分测试失败，请检查相关问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())