"""
测试版本创建API
"""
import sys
sys.path.insert(0, 'D:/test-programs/opencode/ai-agent-test-platform/backend')

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# 先登录获取token
login_data = {
    "username": "admin",
    "password": "admin123"
}

response = client.post("/api/v1/auth/login", data=login_data)
print(f"Login status: {response.status_code}")

if response.status_code == 200:
    token = response.json().get("data", {}).get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 测试创建版本
    version_data = {
        "project_id": 1,
        "version_number": "1.0.0",
        "version_name": "测试版本",
        "description": "这是一个测试版本"
    }
    
    print(f"\nCreating version: {version_data}")
    response = client.post("/api/v1/versions/", json=version_data, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
