"""
测试RAG完整流程：上传 → 处理 → 搜索
"""

import os
import sys
import json
import requests
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试配置
BASE_URL = "http://localhost:8000/api/v1"
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin123"
TEST_FILE_PATH = "./test_document.txt"  # 创建一个简单的测试文档

# 创建测试文档
def create_test_document():
    """创建测试文档"""
    test_content = """
    AI Agent测试平台文档
    
    这是一个用于测试RAG功能的文档。
    
    平台功能包括：
    1. 用户认证和权限管理
    2. 文档上传和处理
    3. 向量化存储和搜索
    4. 测试用例管理
    
    技术栈：
    - 后端：FastAPI + Python 3.9
    - 前端：React
    - 数据库：PostgreSQL + Redis
    - 向量数据库：ChromaDB
    
    文档处理流程：
    1. 用户上传文档
    2. 系统验证文件格式和大小
    3. 文档被分割成小块
    4. 为每个块生成嵌入向量
    5. 向量存储到ChromaDB
    6. 用户可以通过自然语言查询搜索文档
    
    权限系统：
    - 菜单级权限控制
    - 按钮级权限控制
    - RBAC角色管理
    
    测试用例管理：
    - 创建测试用例
    - 执行测试
    - 生成测试报告
    - 历史记录追踪
    """
    
    with open(TEST_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print(f"测试文档已创建: {TEST_FILE_PATH}")
    return TEST_FILE_PATH

# 获取认证token
def get_auth_token():
    """获取认证token"""
    url = f"{BASE_URL}/auth/login"
    data = {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    }
    
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            token = result["data"]["access_token"]
            print(f"认证成功，获取到token")
            return token
        else:
            print(f"认证失败: {result.get('message')}")
            return None
    except Exception as e:
        print(f"认证请求失败: {str(e)}")
        return None

# 测试文档上传
def test_document_upload(token, file_path):
    """测试文档上传"""
    url = f"{BASE_URL}/rag/upload"
    headers = {"Authorization": f"Bearer {token}"}
    
    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "text/plain")}
        data = {
            "title": "AI Agent测试平台文档",
            "description": "RAG功能测试文档",
            "metadata": json.dumps({"category": "test", "version": "1.0"})
        }
        
        try:
            response = requests.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            result = response.json()
            
            if result.get("success"):
                document = result["data"]
                print(f"文档上传成功: {document['id']}")
                print(f"标题: {document['title']}")
                print(f"文件: {document['file_name']}")
                print(f"状态: {document['status']}")
                return document["id"]
            else:
                print(f"文档上传失败: {result.get('message')}")
                return None
        except Exception as e:
            print(f"文档上传请求失败: {str(e)}")
            return None

# 测试文档处理
def test_document_processing(token, document_id):
    """测试文档处理"""
    url = f"{BASE_URL}/rag/{document_id}/process"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            data = result["data"]
            print(f"文档处理成功")
            print(f"文档ID: {data['document_id']}")
            print(f"处理块数: {data['chunks_processed']}")
            print(f"状态: {data['status']}")
            return True
        else:
            print(f"文档处理失败: {result.get('message')}")
            return False
    except Exception as e:
        print(f"文档处理请求失败: {str(e)}")
        return False

# 测试文档搜索
def test_document_search(token, document_id):
    """测试文档搜索"""
    url = f"{BASE_URL}/rag/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 测试不同的查询
    test_queries = [
        "AI Agent测试平台有哪些功能？",
        "文档处理流程是什么？",
        "权限系统如何工作？",
        "技术栈包括哪些组件？"
    ]
    
    for query in test_queries:
        print(f"\n搜索查询: '{query}'")
        
        payload = {
            "query": query,
            "document_id": document_id,
            "top_k": 3
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            if result.get("success"):
                data = result["data"]
                print(f"找到 {data['total_results']} 个结果")
                
                for i, item in enumerate(data["results"], 1):
                    print(f"\n结果 {i}:")
                    print(f"  分数: {item['score']:.4f}")
                    print(f"  内容: {item['content'][:100]}...")
            else:
                print(f"搜索失败: {result.get('message')}")
                
        except Exception as e:
            print(f"搜索请求失败: {str(e)}")

# 测试获取文档列表
def test_get_documents(token):
    """测试获取文档列表"""
    url = f"{BASE_URL}/rag/"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get("success"):
            data = result["data"]
            print(f"\n文档列表:")
            print(f"总文档数: {data['total']}")
            
            for doc in data["data"]:
                print(f"\n文档ID: {doc['id']}")
                print(f"标题: {doc['title']}")
                print(f"状态: {doc['status']}")
                print(f"处理块数: {doc.get('processed_chunks', 0)}")
                print(f"创建时间: {doc['created_at']}")
        else:
            print(f"获取文档列表失败: {result.get('message')}")
            
    except Exception as e:
        print(f"获取文档列表请求失败: {str(e)}")

# 清理测试文件
def cleanup_test_files():
    """清理测试文件"""
    if os.path.exists(TEST_FILE_PATH):
        os.remove(TEST_FILE_PATH)
        print(f"\n测试文档已删除: {TEST_FILE_PATH}")

# 主测试函数
def main():
    """主测试函数"""
    print("=" * 60)
    print("RAG完整流程测试")
    print("=" * 60)
    
    # 创建测试文档
    print("\n1. 创建测试文档...")
    test_file = create_test_document()
    
    # 获取认证token
    print("\n2. 获取认证token...")
    token = get_auth_token()
    if not token:
        print("认证失败，测试终止")
        cleanup_test_files()
        return
    
    # 测试文档上传
    print("\n3. 测试文档上传...")
    document_id = test_document_upload(token, test_file)
    if not document_id:
        print("文档上传失败，测试终止")
        cleanup_test_files()
        return
    
    # 测试文档处理
    print("\n4. 测试文档处理...")
    if not test_document_processing(token, document_id):
        print("文档处理失败，继续测试其他功能...")
    
    # 测试文档搜索
    print("\n5. 测试文档搜索...")
    test_document_search(token, document_id)
    
    # 测试获取文档列表
    print("\n6. 测试获取文档列表...")
    test_get_documents(token)
    
    # 清理
    print("\n7. 清理测试文件...")
    cleanup_test_files()
    
    print("\n" + "=" * 60)
    print("RAG完整流程测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()