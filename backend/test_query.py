#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import uuid
from app.core.database import SessionLocal
from app.core.models.test_simple import TestCase

def test_query():
    db = SessionLocal()
    try:
        test_case_id_str = "07a529cb-876e-42b0-a907-c4ad75067e55"
        test_case_id_uuid = uuid.UUID(test_case_id_str)
        
        print(f"Querying with string: {test_case_id_str}")
        test_case_str = db.query(TestCase).filter(
            TestCase.id == test_case_id_str,
            TestCase.deleted_at.is_(None)
        ).first()
        
        print(f"Result with string: {'Found' if test_case_str else 'Not found'}")
        
        print(f"\nQuerying with UUID: {test_case_id_uuid}")
        test_case_uuid = db.query(TestCase).filter(
            TestCase.id == test_case_id_uuid,
            TestCase.deleted_at.is_(None)
        ).first()
        
        print(f"Result with UUID: {'Found' if test_case_uuid else 'Not found'}")
        
        # Also try direct SQL
        from sqlalchemy import text
        result = db.execute(text("SELECT id FROM test_case WHERE id = :id"), {"id": test_case_id_str}).fetchone()
        print(f"\nDirect SQL query: {'Found' if result else 'Not found'}")
        
        # Check if test_type is functional
        if test_case_str:
            print(f"\nTest case test_type: {test_case_str.test_type}")
            print(f"Test case test_steps: {test_case_str.test_steps}")
            print(f"Test case test_steps type: {type(test_case_str.test_steps)}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_query()