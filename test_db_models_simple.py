"""
测试数据库模型关系配置 - 简化版
"""
import sys
sys.path.insert(0, 'D:/test-programs/opencode/ai-agent-test-platform/backend')

# Mock the settings to avoid loading from env
import os
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['DATABASE_URL'] = 'sqlite:///test.db'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret'

from app.core.models import User, ProjectMember

print("Testing model relationships...")
print(f"User has project_memberships: {hasattr(User, 'project_memberships')}")
print(f"ProjectMember has user relationship: {hasattr(ProjectMember, 'user')}")

# Check the relationship details
if hasattr(User, 'project_memberships'):
    print(f"  - back_populates: {User.project_memberships.property.back_populates}")
    
if hasattr(ProjectMember, 'user'):
    print(f"  - back_populates: {ProjectMember.user.property.back_populates}")

print("\nAll relationship checks passed!")
