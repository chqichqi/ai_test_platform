"""
数据库迁移脚本
为api_test_cases表添加preconditions、test_steps、expected_result字段
"""

import os
import sys
from sqlalchemy import text

# 添加backend目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, SessionLocal
from app.core.logger import logger


def migrate_api_test_cases():
    """为api_test_cases表添加新字段"""
    
    db = SessionLocal()
    
    try:
        # 检查数据库类型
        db_url = str(engine.url)
        is_mysql = "mysql" in db_url.lower()
        is_sqlite = "sqlite" in db_url.lower()
        
        logger.info(f"Database type: {'MySQL' if is_mysql else 'SQLite' if is_sqlite else 'Unknown'}")
        
        # 新字段列表
        new_columns = [
            ("preconditions", "TEXT", "前置条件"),
            ("test_steps", "JSON", "测试步骤"),
            ("expected_result", "TEXT", "预期结果描述")
        ]
        
        for column_name, column_type, comment in new_columns:
            try:
                if is_mysql:
                    # MySQL语法
                    sql = text(f"""
                        ALTER TABLE api_test_cases 
                        ADD COLUMN {column_name} {column_type} COMMENT '{comment}'
                    """)
                elif is_sqlite:
                    # SQLite语法（不支持COMMENT）
                    sql = text(f"""
                        ALTER TABLE api_test_cases 
                        ADD COLUMN {column_name} {column_type}
                    """)
                else:
                    # PostgreSQL或其他
                    sql = text(f"""
                        ALTER TABLE api_test_cases 
                        ADD COLUMN {column_name} {column_type}
                    """)
                
                db.execute(sql)
                db.commit()
                logger.info(f"Added column {column_name} to api_test_cases table")
                
            except Exception as e:
                # 如果字段已存在，忽略错误
                if "Duplicate column name" in str(e) or "already exists" in str(e).lower():
                    logger.info(f"Column {column_name} already exists, skipping")
                else:
                    logger.error(f"Error adding column {column_name}: {str(e)}")
                    raise
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Starting database migration...")
    migrate_api_test_cases()
    logger.info("Migration script finished")