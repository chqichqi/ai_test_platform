#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import uuid
from app.core.database import SessionLocal
from app.services.web_ui_test_service import WebUITestService
from app.core.schemas.web_ui_test import FunctionalToWebUITestConversion, BrowserTypeEnum, ViewportSizeEnum
from app.core.models.user import User

def test_direct_conversion():
    db = SessionLocal()
    try:
        # Create a mock current user (admin)
        current_user = User(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            is_active=True,
            is_superuser=True
        )
        
        # Get first test case ID from database
        from app.core.models.test_simple import TestCase
        test_case = db.query(TestCase).filter(TestCase.deleted_at.is_(None)).first()
        if not test_case:
            print("No test case found")
            return False
        
        print(f"Test case ID: {test_case.id}")
        print(f"Test type: {test_case.test_type}")
        print(f"Test steps: {test_case.test_steps}")
        
        # Create conversion data
        conversion_data = FunctionalToWebUITestConversion(
            functional_test_case_id=uuid.UUID(test_case.id),
            base_url="http://localhost:3000",
            browser=BrowserTypeEnum.CHROME,
            viewport_size=ViewportSizeEnum.DESKTOP_1920x1080,
            headless=True,
            generate_element_selectors=True,
            generate_test_script=True,
            script_type="playwright",
            script_language="python"
        )
        
        # Create service
        service = WebUITestService(db)
        
        # Call conversion
        result = service.convert_functional_to_web_ui(conversion_data, current_user)
        
        print(f"Result success: {result.success}")
        print(f"Result errors: {result.errors}")
        print(f"Result warnings: {result.warnings}")
        print(f"Result web_ui_test_case_id: {result.web_ui_test_case_id}")
        
        if result.success:
            print("Conversion successful!")
            if result.element_selectors:
                print(f"Generated {len(result.element_selectors)} element selectors")
            if result.test_script:
                print(f"Generated test script: {result.test_script[:100]}...")
            return True
        else:
            print("Conversion failed")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = test_direct_conversion()
    sys.exit(0 if success else 1)