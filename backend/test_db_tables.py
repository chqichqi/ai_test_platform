#!/usr/bin/env python
"""
检查数据库表
"""

from app.core.database import engine
from sqlalchemy import inspect

# 创建检查器
inspector = inspect(engine)

# 获取所有表名
table_names = inspector.get_table_names()
print("数据库中的表:")
for table_name in table_names:
    print(f"  - {table_name}")
    
    # 获取列信息
    columns = inspector.get_columns(table_name)
    print(f"    列: {[col['name'] for col in columns]}")