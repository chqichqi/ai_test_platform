import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.services.web_ui_test_service import WebUITestService
from app.core.schemas.web_ui_test import FunctionalToWebUITestConversion
from app.core.models.user import User
from uuid import uuid4

# Create a mock current user
current_user = User(
    id=str(uuid4()),
    username="admin",
    email="admin@example.com",
    full_name="Admin",
    is_active=True,
    is_superuser=True
)

db = SessionLocal()
service = WebUITestService(db)

# Build conversion data
conversion_data = FunctionalToWebUITestConversion(
    functional_test_case_id="ef32c563-527d-4beb-93a4-4079add6d903",
    base_url="https://example.com",
    browser="chrome",
    viewport_size="1920x1080",
    headless=True,
    generate_element_selectors=True,
    generate_test_script=True,
    script_type="playwright",
    script_language="python"
)

print("Testing conversion directly...")
try:
    result = service.convert_functional_to_web_ui(conversion_data, current_user)
    print(f"Result success: {result.success}")
    if result.success:
        print(f"Web UI test case ID: {result.web_ui_test_case_id}")
        print(f"Test script length: {len(result.test_script) if result.test_script else 0}")
    else:
        print(f"Errors: {result.errors}")
except Exception as e:
    print(f"Exception: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()