"""
诊断脚本 - 测试项目 API
"""
import sys
sys.path.insert(0, 'D:/test-programs/opencode/ai-agent-test-platform/backend')

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("Testing /api/v1/projects/ endpoint...")
print("=" * 50)

# 测试项目列表 API
try:
    response = client.get("/api/v1/projects/?page_size=100")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
print("Testing /api/v1/dashboard/stats endpoint...")
print("=" * 50)

# 测试 Dashboard API
try:
    response = client.get("/api/v1/dashboard/stats")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
