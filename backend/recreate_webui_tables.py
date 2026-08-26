"""
Recreate WEB UI tables to fix enum and foreign key issues
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.core.config import settings
from app.core.models.web_ui_test import WebUITestCase, WebUITestExecution, WebUIElementSelector
from app.core.models.test_simple import TestCase, TestExecution
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)

def recreate_tables():
    with engine.begin() as conn:
        # Drop tables in correct order (due to foreign keys)
        logger.info("Dropping WEB UI tables...")
        # Check if tables exist
        conn.execute(text("DROP TABLE IF EXISTS web_ui_element_selector"))
        conn.execute(text("DROP TABLE IF EXISTS web_ui_test_execution"))
        conn.execute(text("DROP TABLE IF EXISTS web_ui_test_case"))
        
        # Also drop enum types if they exist (PostgreSQL only)
        # For SQLite, nothing needed
        
        logger.info("Tables dropped")
    
    # Create tables using SQLAlchemy metadata
    logger.info("Creating WEB UI tables...")
    WebUITestCase.__table__.create(bind=engine, checkfirst=True)
    WebUITestExecution.__table__.create(bind=engine, checkfirst=True)
    WebUIElementSelector.__table__.create(bind=engine, checkfirst=True)
    logger.info("Tables created successfully")
    
    # Verify foreign keys
    inspector = engine.dialect.inspector(engine)
    for table_name in ['web_ui_test_case', 'web_ui_test_execution', 'web_ui_element_selector']:
        logger.info(f"\n--- {table_name} ---")
        columns = inspector.get_columns(table_name)
        for col in columns:
            logger.info(f"  {col['name']}: {col['type']}")
        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            logger.info(f"  FK: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")

if __name__ == "__main__":
    recreate_tables()