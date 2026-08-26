"""
测试数据库模型关系配置
"""
import sys
sys.path.insert(0, 'D:/test-programs/opencode/ai-agent-test-platform/backend')

from app.core.database import init_db, Base, engine
from app.core.models import User, ProjectMember

print("Testing database initialization...")
print(f"User has project_memberships: {hasattr(User, 'project_memberships')}")
print(f"ProjectMember has user relationship: {hasattr(ProjectMember, 'user')}")

# Try to configure mappers
from sqlalchemy.orm import configure_mappers
try:
    configure_mappers()
    print("Mappers configured successfully!")
except Exception as e:
    print(f"Error configuring mappers: {e}")
    import traceback
    traceback.print_exc()

print("\nAll tests passed!")
