import requests
import json
import time

BASE_URL = "http://localhost:8010/api/v1"

def login():
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if response.status_code != 200:
        print(f"Login failed: {response.status_code}")
        print(response.json())
        return None
    result = response.json()
    token = result.get("data", {}).get("access_token")
    if not token:
        print("No access token in response")
        print(result)
        return None
    print("Login successful")
    return token

def test_execution_endpoint(token, web_ui_test_case_id):
    execution_data = {
        "web_ui_test_case_id": web_ui_test_case_id,
        "environment": "development",
        "browser": "chrome",
        "headless": True,
        "timeout": 60000
    }
    
    print(f"Testing execution endpoint with WEB UI test case ID: {web_ui_test_case_id}")
    print(f"Execution data: {json.dumps(execution_data, indent=2)}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.post(
        f"{BASE_URL}/web-ui-tests/execute",
        json=execution_data,
        headers=headers
    )
    
    print(f"Status code: {response.status_code}")
    response_json = response.json()
    print(f"Response body: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        result = response_json
        print("Execution initiated")
        print(f"Execution ID: {result.get('execution_id')}")
        print(f"Status: {result.get('status')}")
        print(f"Duration: {result.get('duration')}")
    else:
        print(f"ERROR: Unexpected status code: {response.status_code}")

if __name__ == "__main__":
    token = login()
    if token:
        # Use the web_ui_test_case_id from conversion test
        web_ui_test_case_id = "daa422f7-ac38-4ef2-950d-9eca9bfdbba2"
        test_execution_endpoint(token, web_ui_test_case_id)
    else:
        print("Cannot proceed without authentication token")