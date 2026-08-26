"""
直接测试RAG功能（不通过HTTP API）
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, init_db
from app.core.models.document import Document
from app.core.services.document_service import DocumentService
from app.core.services.vector_service import VectorService

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
    
    test_file = "./test_document.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print(f"测试文档已创建: {test_file}")
    return test_file

# 测试向量服务
def test_vector_service():
    """测试向量服务"""
    print("\n1. 测试向量服务初始化...")
    try:
        vector_service = VectorService()
        print(f"  向量服务初始化成功")
        print(f"  集合名称: {vector_service.collection.name}")
        print(f"  向量数据库路径: {vector_service.vector_db_path}")
        return vector_service
    except Exception as e:
        print(f"  向量服务初始化失败: {str(e)}")
        return None

# 测试文档处理
def test_document_processing(vector_service, file_path):
    """测试文档处理"""
    print("\n2. 测试文档处理...")
    try:
        # 测试文档加载
        print("  a. 测试文档加载...")
        documents = vector_service.load_document(file_path)
        print(f"    加载了 {len(documents)} 个文档")
        
        # 测试文档分割
        print("  b. 测试文档分割...")
        chunks = vector_service.split_documents(documents)
        print(f"    分割为 {len(chunks)} 个块")
        
        # 显示一些块的内容
        print("  c. 块内容示例:")
        for i, chunk in enumerate(chunks[:3]):  # 只显示前3个块
            print(f"    块 {i}: {chunk.page_content[:100]}...")
        
        return chunks
    except Exception as e:
        print(f"  文档处理失败: {str(e)}")
        return None

# 测试向量存储和搜索
def test_vector_storage_and_search(vector_service, file_path, document_id="test_doc_001"):
    """测试向量存储和搜索"""
    print("\n3. 测试向量存储和搜索...")
    try:
        # 处理并存储文档
        print("  a. 处理并存储文档...")
        chunks_count = vector_service.process_and_store_document(
            file_path=file_path,
            document_id=document_id,
            metadata={
                "title": "AI Agent测试平台文档",
                "description": "RAG功能测试文档",
                "category": "test"
            }
        )
        print(f"    存储了 {chunks_count} 个块")
        
        # 测试搜索
        print("  b. 测试搜索功能...")
        test_queries = [
            "AI Agent测试平台有哪些功能？",
            "文档处理流程是什么？",
            "权限系统如何工作？",
            "技术栈包括哪些组件？"
        ]
        
        for query in test_queries:
            print(f"\n    查询: '{query}'")
            results = vector_service.search_similar(query, document_id, top_k=2)
            print(f"    找到 {len(results)} 个结果")
            
            for i, result in enumerate(results):
                print(f"      结果 {i+1}:")
                print(f"        分数: {result['score']:.4f}")
                print(f"        内容: {result['content'][:80]}...")
        
        return chunks_count
    except Exception as e:
        print(f"  向量存储和搜索失败: {str(e)}")
        return 0

# 清理测试数据
def cleanup_test_data(vector_service, document_id="test_doc_001"):
    """清理测试数据"""
    print("\n4. 清理测试数据...")
    try:
        # 从向量数据库中删除文档
        success = vector_service.delete_document_chunks(document_id)
        if success:
            print(f"  已从向量数据库中删除文档 {document_id}")
        
        # 清空集合
        success = vector_service.clear_collection()
        if success:
            print("  已清空集合")
        
        # 删除测试文件
        test_file = "./test_document.txt"
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"  已删除测试文件: {test_file}")
            
    except Exception as e:
        print(f"  清理失败: {str(e)}")

# 主测试函数
def main():
    """主测试函数"""
    print("=" * 60)
    print("RAG功能直接测试")
    print("=" * 60)
    
    # 创建测试文档
    test_file = create_test_document()
    
    # 测试向量服务
    vector_service = test_vector_service()
    if not vector_service:
        print("向量服务测试失败，终止测试")
        cleanup_test_data(None)
        return
    
    # 测试文档处理
    chunks = test_document_processing(vector_service, test_file)
    if not chunks:
        print("文档处理测试失败，继续测试其他功能...")
    
    # 测试向量存储和搜索
    chunks_count = test_vector_storage_and_search(vector_service, test_file)
    if chunks_count == 0:
        print("向量存储和搜索测试失败")
    
    # 清理测试数据
    cleanup_test_data(vector_service)
    
    print("\n" + "=" * 60)
    print("RAG功能直接测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()