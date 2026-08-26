#!/usr/bin/env python
"""
测试文档上传API
"""

import os
import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_document_upload():
    """测试文档上传流程"""
    print("=" * 60)
    print("测试文档上传API")
    print("=" * 60)
    
    # 1. 登录获取令牌
    print("\n1. 登录获取令牌")
    
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "admin",
            "password": "admin123"
        }
    )
    print(f"  状态码: {response.status_code}")
    
    if response.status_code != 200:
        print("  登录失败，无法继续测试")
        return
    
    login_result = response.json()
    access_token = login_result["data"]["access_token"]
    print("  获取访问令牌成功")
    
    # 2. 创建测试文件
    print("\n2. 创建测试文件")
    test_content = """这是一个测试文档的内容。
用于测试文档上传API的功能。
包含多行文本内容。
"""
    
    test_file_path = Path("test_document.txt")
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print(f"  创建测试文件: {test_file_path}")
    
    # 3. 上传文档
    print("\n3. 上传文档")
    with open(test_file_path, "rb") as f:
        files = {
            "file": ("test_document.txt", f, "text/plain")
        }
        data = {
            "title": "测试文档",
            "description": "这是一个用于测试的文档",
            "metadata": json.dumps({"category": "test", "language": "zh-CN"})
        }
        
        headers = {"Authorization": f"Bearer {access_token}"}
        response = client.post(
            "/api/v1/rag/upload",
            files=files,
            data=data,
            headers=headers
        )
    
    print(f"  状态码: {response.status_code}")
    
    if response.status_code == 201:
        upload_result = response.json()
        print("  文档上传成功")
        print(f"  文档ID: {upload_result['data']['id']}")
        print(f"  文档标题: {upload_result['data']['title']}")
        print(f"  文件大小: {upload_result['data']['file_size']} 字节")
        
        document_id = upload_result["data"]["id"]
        
        # 4. 获取文档列表
        print("\n4. 获取文档列表")
        response = client.get(
            "/api/v1/rag/",
            headers=headers,
            params={"skip": 0, "limit": 10}
        )
        
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            list_result = response.json()
            print(f"  获取到 {len(list_result['data']['data'])} 个文档")
            print(f"  总文档数: {list_result['data']['total']}")
        
        # 5. 获取特定文档
        print("\n5. 获取特定文档")
        response = client.get(
            f"/api/v1/rag/{document_id}",
            headers=headers
        )
        
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            doc_result = response.json()
            print(f"  文档状态: {doc_result['data']['status']}")
            print(f"  是否已向量化: {doc_result['data']['is_vectorized']}")
        
        # 6. 删除测试文档
        print("\n6. 删除测试文档")
        response = client.delete(
            f"/api/v1/rag/{document_id}",
            headers=headers
        )
        
        print(f"  状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("  文档删除成功")
    
    else:
        print("  文档上传失败")
        print(f"  错误信息: {response.text}")
    
    # 7. 清理测试文件
    print("\n7. 清理测试文件")
    if test_file_path.exists():
        test_file_path.unlink()
        print("  测试文件已删除")
    
    # 8. 测试无权限访问
    print("\n8. 测试无权限访问（无令牌）")
    response = client.get("/api/v1/rag/")
    print(f"  状态码: {response.status_code}")
    print(f"  成功: {response.status_code == 401} (预期)")
    
    print("\n" + "=" * 60)
    print("文档上传API测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_document_upload()