"""
诊断脚本 - 测试项目 API（带认证）
"""
import sys
sys.path.insert(0, 'D:/test-programs/opencode/ai-agent-test-platform/backend')

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("Step 1: Login to get token...")
print("=" * 50)

# 尝试登录
login_data = {
    "username": "admin",
    "password": "admin123"
}

try:
    response = client.post("/api/v1/auth/login", data=login_data)
    print(f"Login Status: {response.status_code}")
    
    if response.status_code == 200:
        token = response.json().get("data", {}).get("access_token")
        print(f"Got token: {token[:50]}..." if token else "No token")
        
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            
            print("\nStep 2: Test /api/v1/projects/ with auth...")
            print("=" * 50)
            response = client.get("/api/v1/projects/?page_size=100", headers=headers)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:1000]}")
            
            print("\nStep 3: Test /api/v1/dashboard/stats with auth...")
            print("=" * 50)
            response = client.get("/api/v1/dashboard/stats", headers=headers)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:1000]}")
    else:
        print(f"Login failed: {response.text}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
