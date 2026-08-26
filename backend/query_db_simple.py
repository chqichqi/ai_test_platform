#!/usr/bin/env python3
import sqlite3
import os

def query_functional_tests():
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'ai_agent_test.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return []
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query test cases
    cursor.execute("SELECT * FROM test_case")
    test_cases = cursor.fetchall()
    
    print(f"Found {len(test_cases)} test cases:")
    for tc in test_cases:
        print(f"\nID: {tc['id']}")
        print(f"Title: {tc['title']}")
        print(f"Description: {tc['description']}")
        print(f"Project ID: {tc['project_id']}")
        print(f"Created at: {tc['created_at']}")
        
        # Get test steps
        cursor.execute("SELECT * FROM test_step WHERE test_case_id = ? ORDER BY step_number", (tc['id'],))
        test_steps = cursor.fetchall()
        print(f"  Test steps: {len(test_steps)}")
        for ts in test_steps[:3]:  # Show first 3 steps
            print(f"    Step {ts['step_number']}: {ts['action']}")
    
    conn.close()
    return test_cases

if __name__ == "__main__":
    query_functional_tests()