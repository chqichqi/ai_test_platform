import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.core.models.test_simple import TestCase, TestType

db = SessionLocal()
test_case = db.query(TestCase).filter(TestCase.id == 'ef32c563-527d-4beb-93a4-4079add6d903').first()
if test_case:
    print(f"ID: {test_case.id}")
    print(f"Title: {test_case.title}")
    print(f"Test type: {test_case.test_type}")
    print(f"Test type value: {test_case.test_type.value}")
    print(f"Is functional? {test_case.test_type == TestType.FUNCTIONAL}")
    print(f"Test steps: {test_case.test_steps}")
else:
    print("Test case not found")
db.close()