#!/usr/bin/env python
"""
初始化数据库，创建所有表
"""

from app.core.database import init_db
from app.core.logger import logger

if __name__ == "__main__":
    print("初始化数据库...")
    try:
        init_db()
        print("数据库初始化成功！")
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        print(f"数据库初始化失败: {str(e)}")