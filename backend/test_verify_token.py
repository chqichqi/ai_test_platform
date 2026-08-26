#!/usr/bin/env python3
"""
直接测试令牌验证
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.services.auth_service import AuthService
from app.core.config import settings

# 测试刷新令牌
refresh_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc3NDE4MjQxMCwidHlwZSI6InJlZnJlc2gifQ.RFL0i3zeREJhsSOAjLNoSB3t9kyuK8dNC2-6pvvpfvE"

print(f"Testing token verification...")
print(f"Token: {refresh_token[:50]}...")

try:
    # 直接调用静态方法
    token_data = AuthService.verify_token(refresh_token, "refresh")
    print(f"Token data: {token_data}")
    if token_data:
        print(f"Username: {token_data.username}")
        print(f"Exp: {token_data.exp}")
    else:
        print("Token verification returned None")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()