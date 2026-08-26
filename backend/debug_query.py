import sys
sys.path.append('.')
from app.core.database import SessionLocal
from app.core.models.test_simple import TestCase

db = SessionLocal()
test_case_id = "ef32c563-527d-4beb-93a4-4079add6d903"
print(f"Querying test case with ID: {test_case_id}")
test_case = db.query(TestCase).filter(
    TestCase.id == test_case_id,
    TestCase.deleted_at.is_(None)
).first()
if test_case:
    print(f"Found: {test_case.id} - {test_case.title}")
    print(f"Deleted at: {test_case.deleted_at}")
else:
    print("Not found")
    # Try without deleted_at filter
    test_case2 = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if test_case2:
        print(f"Found without deleted_at filter: {test_case2.id}")
        print(f"Deleted at: {test_case2.deleted_at}")
    else:
        print("Still not found - maybe ID mismatch")
        # List all IDs
        all_ids = db.query(TestCase.id).all()
        print(f"Total test cases: {len(all_ids)}")
        for id_tuple in all_ids[:5]:
            print(f"  {id_tuple[0]}")
db.close()