#!/usr/bin/env python3
import sqlite3
import os
import json

def debug_test_case():
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'ai_agent_test.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get first test case
    cursor.execute("SELECT id, title, test_type, test_steps FROM test_case LIMIT 1")
    test_case = cursor.fetchone()
    
    if test_case:
        print(f"Test Case ID: {test_case['id']}")
        print(f"Title: {test_case['title']}")
        print(f"Test Type: {test_case['test_type']}")
        
        # Try to parse test_steps
        test_steps = test_case['test_steps']
        if test_steps:
            try:
                steps = json.loads(test_steps)
                print(f"Test steps type: {type(steps)}")
                print(f"Test steps length: {len(steps) if isinstance(steps, list) else 'not a list'}")
                if isinstance(steps, list) and len(steps) > 0:
                    print(f"First step: {json.dumps(steps[0], ensure_ascii=False)}")
            except json.JSONDecodeError as e:
                print(f"Failed to parse test_steps as JSON: {e}")
                print(f"Raw test_steps: {test_steps[:200]}...")
        else:
            print("test_steps is empty or None")
    
    conn.close()
    return test_case['id'] if test_case else None

if __name__ == "__main__":
    debug_test_case()