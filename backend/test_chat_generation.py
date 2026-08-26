#!/usr/bin/env python3
"""Test chat-based WEB UI test generation"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import requests
import json

BASE_URL = "http://localhost:8007/api/v1"

def login():
    """Login and get access token"""
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
    """Get headers with authorization"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def test_chat_generation(token: str):
    """Test chat-based WEB UI test generation"""
    url = f"{BASE_URL}/web-ui-tests/generate/chat"
    headers = get_headers(token)
    
    # Simple test case for login page
    chat_data = {
        "message": "Create a WEB UI test for login page with username and password fields and submit button",
        "project_name": "Test Project",
        "base_url": "http://localhost:3000",
        "browser": "CHROME",
        "viewport_size": "DESKTOP_1920x1080",
        "headless": True,
        "generate_element_selectors": True,
        "generate_test_script": True,
        "script_type": "playwright",
        "script_language": "python"
    }
    
    print(f"Sending chat generation request: {json.dumps(chat_data, indent=2)}")
    response = requests.post(url, json=chat_data, headers=headers)
    
    print(f"Response status: {response.status_code}")
    print(f"Response text: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Chat generation successful: {result}")
        return result
    else:
        print(f"Chat generation failed")
        return None

def main():
    print("=== Testing Chat-based WEB UI Generation ===")
    
    token = login()
    if not token:
        print("Failed to login, aborting")
        return False
    
    print("\n--- Testing chat generation ---")
    result = test_chat_generation(token)
    
    if result:
        print("\n[SUCCESS] Chat generation test PASSED")
        return True
    else:
        print("\n[FAILED] Chat generation test FAILED")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)