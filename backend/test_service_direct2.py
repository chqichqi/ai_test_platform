import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.services.web_ui_test_service import WebUITestService
from app.core.schemas.web_ui_test import FunctionalToWebUITestConversion
from app.core.models.user import User

db = SessionLocal()
service = WebUITestService(db)

# Create a mock current user (admin)
current_user = db.query(User).filter(User.username == 'admin').first()
if not current_user:
    print("Admin user not found")
    sys.exit(1)

conversion_data = FunctionalToWebUITestConversion(
    functional_test_case_id='ef32c563-527d-4beb-93a4-4079add6d903',
    base_url='https://example.com',
    browser_type='chrome',
    viewport_size='1920x1080',
    timeout_seconds=30
)

print(f"Calling service.convert_functional_to_web_ui with test case ID: {conversion_data.functional_test_case_id}")
result = service.convert_functional_to_web_ui(conversion_data, current_user)
print(f"Result success: {result.success}")
if result.errors:
    print(f"Errors: {result.errors}")
if result.web_ui_test_case:
    print(f"Generated WEB UI test case ID: {result.web_ui_test_case.id}")
db.close()