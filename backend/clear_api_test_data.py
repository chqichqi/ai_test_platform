"""
清空API测试相关的所有数据
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.core.models.api_test import ApiDefinition, ApiEndpoint, ApiTestCase, ApiTestExecution, ApiEnvironment

def clear_api_test_data():
    """清空API测试相关数据"""
    db = SessionLocal()
    
    try:
        # 查看当前数据量
        print("=" * 50)
        print("清空前的数据统计:")
        print("=" * 50)
        api_def_count = db.query(ApiDefinition).count()
        api_endpoint_count = db.query(ApiEndpoint).count()
        api_case_count = db.query(ApiTestCase).count()
        api_exec_count = db.query(ApiTestExecution).count()
        api_env_count = db.query(ApiEnvironment).count()
        
        print(f"API定义数量: {api_def_count}")
        print(f"API端点数量: {api_endpoint_count}")
        print(f"API测试用例数量: {api_case_count}")
        print(f"API测试执行记录数量: {api_exec_count}")
        print(f"API环境配置数量: {api_env_count}")
        print()
        
        # 按顺序删除（先删除依赖数据，再删除主数据）
        # 1. 删除执行记录（依赖测试用例）
        if api_exec_count > 0:
            deleted_exec = db.query(ApiTestExecution).delete()
            print(f"已删除 {deleted_exec} 条执行记录")
        
        # 2. 删除测试用例（依赖端点）
        if api_case_count > 0:
            deleted_cases = db.query(ApiTestCase).delete()
            print(f"已删除 {deleted_cases} 个测试用例")
        
        # 3. 删除端点（依赖定义）
        if api_endpoint_count > 0:
            deleted_endpoints = db.query(ApiEndpoint).delete()
            print(f"已删除 {deleted_endpoints} 个API端点")
        
        # 4. 删除API定义
        if api_def_count > 0:
            deleted_defs = db.query(ApiDefinition).delete()
            print(f"已删除 {deleted_defs} 个API定义")
        
        # 5. 删除环境配置
        if api_env_count > 0:
            deleted_envs = db.query(ApiEnvironment).delete()
            print(f"已删除 {deleted_envs} 个环境配置")
        
        # 提交事务
        db.commit()
        
        print()
        print("=" * 50)
        print("清空后的数据统计:")
        print("=" * 50)
        print(f"API定义数量: {db.query(ApiDefinition).count()}")
        print(f"API端点数量: {db.query(ApiEndpoint).count()}")
        print(f"API测试用例数量: {db.query(ApiTestCase).count()}")
        print(f"API测试执行记录数量: {db.query(ApiTestExecution).count()}")
        print(f"API环境配置数量: {db.query(ApiEnvironment).count()}")
        print()
        print("✅ API测试数据已全部清空！")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 清空失败: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    clear_api_test_data()