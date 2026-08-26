import requests
import json

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

def test_conversion_endpoint(token):
    functional_test_case_id = "ef32c563-527d-4beb-93a4-4079add6d903"
    
    conversion_data = {
        "functional_test_case_id": functional_test_case_id,
        "base_url": "https://example.com",
        "browser_type": "chrome",
        "viewport_size": "1920x1080",
        "timeout_seconds": 30
    }
    
    print(f"Testing conversion endpoint with test case ID: {functional_test_case_id}")
    print(f"Conversion data: {json.dumps(conversion_data, indent=2)}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.post(
        f"{BASE_URL}/web-ui-tests/convert-from-functional",
        json=conversion_data,
        headers=headers
    )
    
    print(f"Status code: {response.status_code}")
    response_json = response.json()
    print(f"Response body: {json.dumps(response_json, indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        result = response_json
        if result.get("success"):
            print("SUCCESS: Conversion successful!")
            web_ui_test_case = result.get("web_ui_test_case")
            if web_ui_test_case:
                print(f"Generated WEB UI test case ID: {web_ui_test_case.get('id')}")
                print(f"Title: {web_ui_test_case.get('title')}")
                script = web_ui_test_case.get('test_script', '')
                if script:
                    print(f"Test script preview: {script[:200]}...")
        else:
            print("FAILURE: Conversion failed")
            errors = result.get("errors", [])
            for error in errors:
                print(f"  Error: {error}")
    else:
        print(f"ERROR: Unexpected status code: {response.status_code}")

if __name__ == "__main__":
    token = login()
    if token:
        test_conversion_endpoint(token)
    else:
        print("Cannot proceed without authentication token")