#!/usr/bin/env python3
import sqlite3
import os
import json

def check_test_case_full(test_case_id: str):
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'ai_agent_test.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get test case with all columns
    cursor.execute("SELECT * FROM test_case WHERE id = ?", (test_case_id,))
    test_case = cursor.fetchone()
    
    if test_case:
        print(f"Test Case ID: {test_case['id']}")
        print(f"Title: {test_case['title']}")
        print(f"Test Type: {test_case['test_type']}")
        print(f"Deleted At: {test_case['deleted_at']}")
        print(f"Created At: {test_case['created_at']}")
        print(f"Updated At: {test_case['updated_at']}")
        
        # Check all columns
        print("\nAll columns:")
        for key in test_case.keys():
            value = test_case[key]
            if key in ['test_steps', 'tags', 'attachments', 'custom_fields', 'metadata']:
                if value:
                    try:
                        parsed = json.loads(value)
                        print(f"  {key}: {type(parsed)} length={len(parsed) if isinstance(parsed, list) else 'N/A'}")
                    except:
                        print(f"  {key}: {str(value)[:50]}...")
                else:
                    print(f"  {key}: {value}")
            else:
                print(f"  {key}: {value}")
    else:
        print(f"Test case with ID {test_case_id} not found in database")
    
    conn.close()

if __name__ == "__main__":
    test_case_id = "07a529cb-876e-42b0-a907-c4ad75067e55"
    check_test_case_full(test_case_id)