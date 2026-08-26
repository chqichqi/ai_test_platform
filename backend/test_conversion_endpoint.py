#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import requests
import json
import sqlite3

BASE_URL = "http://localhost:8009/api/v1"

def login():
    url = f"{BASE_URL}/auth/login"
    data = {
        "username": "admin",
        "password": "admin123"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=data, headers=headers)
    if response.status_code != 200:
        print(f"Login failed: {response.status_code} - {response.text}")
        return None
    
    result = response.json()
    if not result.get("success"):
        print(f"Login failed: {result}")
        return None
    
    token = result["data"]["access_token"]
    print(f"Login successful, token: {token[:20]}...")
    return token

def get_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_test_case_id_from_db():
    """Get first test case ID from database"""
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'ai_agent_test.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return None
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM test_case LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    
    if result:
        test_case_id = result[0]
        print(f"Found test case ID: {test_case_id}")
        return test_case_id
    else:
        print("No test cases found in database")
        return None

def test_conversion(token: str, test_case_id: str):
    """Test converting a functional test case to WEB UI test"""
    url = f"{BASE_URL}/web-ui-tests/convert-from-functional"
    headers = get_headers(token)
    
    conversion_data = {
        "functional_test_case_id": test_case_id,
        "base_url": "http://localhost:3000",
        "browser": "CHROME",
        "viewport_size": "DESKTOP_1920x1080",
        "headless": True,
        "generate_element_selectors": True,
        "generate_test_script": True,
        "script_type": "playwright",
        "script_language": "python"
    }
    
    print(f"\nSending conversion request for test case {test_case_id}")
    print(f"Data: {json.dumps(conversion_data, indent=2)}")
    
    response = requests.post(url, json=conversion_data, headers=headers)
    
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\nConversion result:")
        print(f"  Success: {result.get('success')}")
        print(f"  Message: {result.get('message')}")
        
        if result.get('data'):
            data = result['data']
            web_ui_cases = data.get('web_ui_test_cases', [])
            print(f"  Generated {len(web_ui_cases)} WEB UI test cases")
            for i, case in enumerate(web_ui_cases[:2]):
                print(f"    Case {i+1}: {case.get('title')}")
            
            selectors = data.get('element_selectors', [])
            print(f"  Generated {len(selectors)} element selectors")
            for i, selector in enumerate(selectors[:2]):
                print(f"    Selector {i+1}: {selector.get('element_name')} -> {selector.get('css_selector')}")
            
            test_script = data.get('test_script', {})
            if test_script:
                print(f"  Generated test script: {test_script.get('filename')}")
        
        return result
    else:
        print(f"Response text: {response.text}")
        return None

def main():
    print("=== Testing Functional Test to WEB UI Conversion Endpoint ===")
    
    token = login()
    if not token:
        print("Failed to login, aborting")
        return False
    
    print("\n--- Step 1: Get test case ID from database ---")
    test_case_id = get_test_case_id_from_db()
    if not test_case_id:
        print("No test case found, aborting")
        return False
    
    print("\n--- Step 2: Test conversion ---")
    result = test_conversion(token, test_case_id)
    
    if result and result.get("success"):
        print("\n[SUCCESS] Conversion endpoint test PASSED")
        return True
    else:
        print("\n[FAILED] Conversion endpoint test FAILED")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)