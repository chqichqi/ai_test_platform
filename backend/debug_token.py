#!/usr/bin/env python3
"""
调试令牌验证问题
"""

from jose import jwt
from app.core.config import settings

# 测试刷新令牌
refresh_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc3NDE4MTU3MywidHlwZSI6InJlZnJlc2gifQ.hLhAI5m49yrYP0_anSFfWSfBbdJdwUYBh_ut2bBJ6E4"

print(f"JWT Secret Key: {settings.JWT_SECRET_KEY}")
print(f"JWT Algorithm: {settings.JWT_ALGORITHM}")

try:
    # 尝试解码令牌
    payload = jwt.decode(refresh_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    print(f"Payload: {payload}")
    print(f"Token type in payload: {payload.get('type')}")
    print(f"Subject in payload: {payload.get('sub')}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)}")