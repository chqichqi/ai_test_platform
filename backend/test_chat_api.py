"""
测试聊天API是否正常工作
"""
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# 测试健康检查
print("Testing health endpoint...")
response = client.get("/health")
print(f"Health status: {response.status_code}")

# 测试登录获取token
print("\nTesting login...")
login_data = {
    "username": "admin",
    "password": "admin123"
}
response = client.post("/api/v1/auth/login", data=login_data)
print(f"Login status: {response.status_code}")

if response.status_code == 200:
    token = response.json().get("data", {}).get("access_token")
    print(f"Got token: {token[:50]}...")
    
    # 测试聊天API
    print("\nTesting chat/stream endpoint...")
    headers = {"Authorization": f"Bearer {token}"}
    chat_data = {
        "message": "什么是边界值分析法？",
        "base_url": "http://localhost:3000",
        "browser": "chromium",
        "viewport_size": "1920x1080",
        "headless": True,
        "script_type": "playwright",
        "script_language": "python",
        "generate_element_selectors": True,
        "generate_test_script": True
    }
    
    try:
        response = client.post("/api/v1/web-ui-tests/chat/stream", 
                              json=chat_data, 
                              headers=headers,
                              timeout=30)
        print(f"Chat status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Response preview: {response.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")
else:
    print(f"Login failed: {response.text}")
