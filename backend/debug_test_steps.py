import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.core.models.test_simple import TestCase

db = SessionLocal()
test_case = db.query(TestCase).filter(TestCase.id == "ef32c563-527d-4beb-93a4-4079add6d903").first()
if test_case:
    print(f"Test case ID: {test_case.id}")
    print(f"Title: {test_case.title}")
    print(f"Test type: {test_case.test_type}")
    print(f"Test steps: {test_case.test_steps}")
    if test_case.test_steps:
        for i, step in enumerate(test_case.test_steps):
            print(f"  Step {i+1}: {step}")
else:
    print("Test case not found")
db.close()