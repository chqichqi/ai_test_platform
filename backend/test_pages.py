#!/usr/bin/env python3
"""测试所有可访问的页面"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoint(url, method="GET", data=None):
    """测试单个端点"""
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        elif method == "POST":
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, json=data, headers=headers, timeout=5)
        
        print(f"\n{'='*60}")
        print(f"测试: {method} {url}")
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("响应 (JSON):")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            except:
                print("响应 (HTML/Text):")
                print(response.text[:500])
        else:
            print(f"错误: {response.text[:200]}")
            
        return response.status_code == 200
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"测试失败: {method} {url}")
        print(f"错误: {e}")
        return False

def main():
    print("测试 AI Agent Test Platform 所有页面")
    print("=" * 60)
    
    endpoints = [
        # 主要页面
        ("/", "GET"),
        ("/dashboard", "GET"),
        ("/health", "GET"),
        ("/info", "GET"),
        ("/api/status", "GET"),
        ("/ping", "GET"),
        ("/version", "GET"),
        
        # API文档
        ("/docs", "GET"),
        ("/redoc", "GET"),
        ("/openapi.json", "GET"),
        
        # API端点
        ("/api/v1/auth/test", "GET"),
        
        # 静态文件
        ("/static/index.html", "GET"),
    ]
    
    success_count = 0
    total_count = len(endpoints)
    
    for endpoint, method in endpoints:
        url = BASE_URL + endpoint
        if test_endpoint(url, method):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"测试完成: {success_count}/{total_count} 个端点成功")
    
    if success_count == total_count:
        print("✅ 所有页面均可正常访问！")
    else:
        print("⚠️  部分页面访问失败")
    
    print("\n可访问的页面:")
    print("1. 控制面板: http://localhost:8000/")
    print("2. API文档: http://localhost:8000/docs")
    print("3. 健康检查: http://localhost:8000/health")
    print("4. 应用信息: http://localhost:8000/info")
    print("5. API状态: http://localhost:8000/api/status")
    print("6. 认证测试: http://localhost:8000/api/v1/auth/test")

if __name__ == "__main__":
    main()