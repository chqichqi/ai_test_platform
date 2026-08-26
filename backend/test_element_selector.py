"""
Test element selector insertion
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.models.web_ui_test import WebUIElementSelector, WebUITestCase, BrowserType, ViewportSize
import uuid

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_insert():
    db = SessionLocal()
    try:
        # Always create a new test case to avoid enum issues with existing data
        print("Creating new test case...")
        from app.core.models.test_simple import TestCase
        test_case = TestCase(
            title="Test Case for Element Selector",
            description="Test",
            test_type="functional"
        )
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        
        web_ui_case = WebUITestCase(
            test_case_id=test_case.id,
            base_url="http://example.com",
            browser=BrowserType.CHROME,
            viewport_size=ViewportSize.DESKTOP_1920x1080
        )
        db.add(web_ui_case)
        db.commit()
        db.refresh(web_ui_case)
        web_ui_test_case_id = web_ui_case.id
        
        print(f"Using web_ui_test_case_id: {web_ui_test_case_id}")
        
        # Try to insert element selector with project_id=None
        selector = WebUIElementSelector(
            web_ui_test_case_id=web_ui_test_case_id,
            project_id=None,
            element_name="test_button",
            css_selector="button.test"
        )
        db.add(selector)
        db.commit()
        db.refresh(selector)
        print(f"Successfully inserted element selector with id: {selector.id}")
        print(f"project_id: {selector.project_id}")
        
        # Try with project_id as string (UUID)
        selector2 = WebUIElementSelector(
            web_ui_test_case_id=web_ui_test_case_id,
            project_id=str(uuid.uuid4()),
            element_name="test_button2",
            css_selector="button.test2"
        )
        db.add(selector2)
        db.commit()
        db.refresh(selector2)
        print(f"Successfully inserted element selector with project_id string: {selector2.id}")
        
        # Clean up
        db.delete(selector)
        db.delete(selector2)
        db.delete(web_ui_case)
        db.delete(test_case)
        db.commit()
        print("Test passed!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_insert()