#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import requests
import json
import uuid

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

def get_functional_tests(token: str):
    """Get list of functional test cases to convert"""
    url = f"{BASE_URL}/tests/test-cases"
    headers = get_headers(token)
    
    # Add query parameters
    params = {
        "page": 1,
        "size": 10
    }
    
    print(f"Fetching functional test cases from {url}")
    response = requests.get(url, headers=headers, params=params)
    
    print(f"Response status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Found {result.get('total', 0)} functional test cases")
        
        # Print first few test cases
        items = result.get('items', [])
        for i, item in enumerate(items[:3]):
            print(f"  {i+1}. ID: {item.get('id')}, Title: {item.get('title')}")
        
        return items
    else:
        print(f"Failed to get functional tests: {response.text}")
        return []

def test_conversion(token: str, functional_test_case_id: uuid.UUID):
    """Test converting a functional test case to WEB UI test"""
    url = f"{BASE_URL}/web-ui-tests/convert-from-functional"
    headers = get_headers(token)
    
    conversion_data = {
        "functional_test_case_id": str(functional_test_case_id),
        "base_url": "http://localhost:3000",
        "browser": "CHROME",
        "viewport_size": "DESKTOP_1920x1080",
        "headless": True,
        "generate_element_selectors": True,
        "generate_test_script": True,
        "script_type": "playwright",
        "script_language": "python"
    }
    
    print(f"\nSending conversion request for functional test case {functional_test_case_id}")
    print(f"Data: {json.dumps(conversion_data, indent=2)}")
    
    response = requests.post(url, json=conversion_data, headers=headers)
    
    print(f"Response status: {response.status_code}")
    print(f"Response text: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\nConversion result:")
        print(f"  Success: {result.get('success')}")
        print(f"  Message: {result.get('message')}")
        
        if result.get('data'):
            data = result['data']
            print(f"  Generated {len(data.get('web_ui_test_cases', []))} WEB UI test cases")
            print(f"  Generated {len(data.get('element_selectors', []))} element selectors")
            print(f"  Generated test script: {data.get('test_script', {}).get('filename', 'N/A')}")
        
        return result
    else:
        print(f"Conversion failed")
        return None

def main():
    print("=== Testing Functional Test to WEB UI Conversion ===")
    
    token = login()
    if not token:
        print("Failed to login, aborting")
        return False
    
    print("\n--- Step 1: Get functional test cases ---")
    functional_tests = get_functional_tests(token)
    
    if not functional_tests:
        print("\nNo functional test cases found. Creating a sample functional test first...")
        # We need to create a functional test case first
        # For now, just exit
        print("Please create at least one functional test case first")
        return False
    
    print("\n--- Step 2: Test conversion for first functional test case ---")
    first_test = functional_tests[0]
    functional_test_case_id = uuid.UUID(first_test['id'])
    
    result = test_conversion(token, functional_test_case_id)
    
    if result and result.get("success"):
        print("\n[SUCCESS] Conversion test PASSED")
        return True
    else:
        print("\n[FAILED] Conversion test FAILED")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)