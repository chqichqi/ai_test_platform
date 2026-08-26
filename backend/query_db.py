#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.core.database import SessionLocal
from app.core.models.test import TestCase, TestStep

def query_functional_tests():
    db = SessionLocal()
    try:
        # Query test cases
        test_cases = db.query(TestCase).all()
        
        print(f"Found {len(test_cases)} test cases:")
        for tc in test_cases:
            print(f"\nID: {tc.id}")
            print(f"Title: {tc.title}")
            print(f"Description: {tc.description}")
            print(f"Project ID: {tc.project_id}")
            print(f"Created at: {tc.created_at}")
            
            # Get test steps
            test_steps = db.query(TestStep).filter(TestStep.test_case_id == tc.id).all()
            print(f"  Test steps: {len(test_steps)}")
            for ts in test_steps[:3]:  # Show first 3 steps
                print(f"    Step {ts.step_number}: {ts.action}")
                
        return test_cases
    finally:
        db.close()

if __name__ == "__main__":
    query_functional_tests()