#!/usr/bin/env python3
"""Test WEB UI conversion flow via API"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import requests
import json
import uuid
from typing import Dict, Any

BASE_URL = "http://localhost:8000/api/v1"
FRONTEND_URL = "http://localhost:3004"

def login():
    """Login and get access token"""
    url = f"{BASE_URL}/auth/login"
    data = {
        "username": "admin",
        "password": "admin123"
    }
    # Note: auth endpoint expects form data, not JSON
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
    """Get headers with authorization"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def list_functional_tests(token: str):
    """List functional tests"""
    url = f"{BASE_URL}/functional-tests/"
    headers = get_headers(token)
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        # Try without trailing slash
        url = f"{BASE_URL}/functional-tests"
        response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"List functional tests failed: {response.status_code} - {response.text}")
        return []
    
    result = response.json()
    print(f"Functional tests response: {result}")
    # Return empty list for now - endpoint returns mock message
    return []

def create_functional_test(token: str):
    """Create a sample functional test for conversion"""
    url = f"{BASE_URL}/tests"  # Assuming tests endpoint exists
    headers = get_headers(token)
    
    # First check if tests endpoint exists
    response = requests.get(f"{BASE_URL}/tests", headers=headers)
    print(f"Tests endpoint check: {response.status_code} - {response.text[:100]}")
    
    # Try to create via functional-tests/generate
    url = f"{BASE_URL}/functional-tests/generate"
    test_data = {
        "name": "Sample Functional Test for WEB UI Conversion",
        "description": "Test login flow for conversion to WEB UI test",
        "test_steps": [
            {
                "step": 1,
                "action": "打开登录页面",
                "target": "/auth/login",
                "value": "",
                "expected": "显示登录表单"
            },
            {
                "step": 2,
                "action": "输入用户名",
                "target": "input[name='username']",
                "value": "admin",
                "expected": "用户名输入框显示值"
            },
            {
                "step": 3,
                "action": "输入密码", 
                "target": "input[name='password']",
                "value": "admin123",
                "expected": "密码输入框显示值"
            },
            {
                "step": 4,
                "action": "点击登录按钮",
                "target": "button[type='submit']",
                "value": "",
                "expected": "登录成功，跳转到仪表板"
            }
        ],
        "test_type": "FUNCTIONAL",
        "project_id": None
    }
    
    response = requests.post(url, json=test_data, headers=headers)
    print(f"Create functional test: {response.status_code} - {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Created functional test: {result}")
        # Return test ID if available
        return result.get("data", {}).get("id")
    
    return None

def test_web_ui_conversion(token: str, functional_test_id: str = None):
    """Test converting functional test to WEB UI test"""
    url = f"{BASE_URL}/web-ui-tests/convert-from-functional"
    headers = get_headers(token)
    
    # If no functional test ID provided, use a mock UUID
    if not functional_test_id:
        functional_test_id = "00000000-0000-0000-0000-000000000001"
    
    conversion_data = {
        "functional_test_case_id": functional_test_id,
        "base_url": FRONTEND_URL,
        "browser": "chromium",
        "viewport_size": "1920x1080",
        "headless": True,
        "generate_element_selectors": True,
        "generate_test_script": True,
        "script_type": "playwright",
        "script_language": "python"
    }
    
    print(f"Sending conversion request: {conversion_data}")
    response = requests.post(url, json=conversion_data, headers=headers)
    
    print(f"Conversion response: {response.status_code}")
    print(f"Response text: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Conversion successful: {result}")
        return result
    
    return None

def list_web_ui_tests(token: str):
    """List WEB UI tests"""
    url = f"{BASE_URL}/web-ui-tests/test-cases"
    headers = get_headers(token)
    response = requests.get(url, headers=headers)
    
    print(f"WEB UI tests list: {response.status_code} - {response.text}")
    return response.json() if response.status_code == 200 else None

def main():
    """Main test flow"""
    print("=== Testing WEB UI Conversion Flow ===")
    
    # Step 1: Login
    token = login()
    if not token:
        print("Failed to login, aborting")
        return
    
    # Step 2: Check functional tests
    print("\n--- Checking functional tests ---")
    functional_tests = list_functional_tests(token)
    
    # Step 3: Create functional test if none exist
    print("\n--- Creating functional test ---")
    test_id = create_functional_test(token)
    
    # Step 4: Test conversion
    print("\n--- Testing WEB UI conversion ---")
    conversion_result = test_web_ui_conversion(token, test_id)
    
    # Step 5: List WEB UI tests
    print("\n--- Listing WEB UI tests ---")
    web_ui_tests = list_web_ui_tests(token)
    
    print("\n=== Test Complete ===")
    
    if conversion_result:
        print("✓ WEB UI conversion test PASSED")
        return True
    else:
        print("✗ WEB UI conversion test FAILED")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)