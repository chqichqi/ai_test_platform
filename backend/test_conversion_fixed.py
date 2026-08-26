import requests
import json

BASE_URL = "http://localhost:8009/api/v1"

def test_conversion_endpoint():
    functional_test_case_id = "ef32c563-527d-4beb-93a4-4079add6d903"
    
    conversion_data = {
        "functional_test_case_id": functional_test_case_id,
        "browser_type": "chrome",
        "viewport_size": "1920x1080",
        "timeout_seconds": 30
    }
    
    print(f"Testing conversion endpoint with test case ID: {functional_test_case_id}")
    print(f"Conversion data: {json.dumps(conversion_data, indent=2)}")
    
    response = requests.post(
        f"{BASE_URL}/web-ui-tests/convert-from-functional",
        json=conversion_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status code: {response.status_code}")
    print(f"Response body: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            print("✅ Conversion successful!")
            web_ui_test_case = result.get("web_ui_test_case")
            if web_ui_test_case:
                print(f"Generated WEB UI test case ID: {web_ui_test_case.get('id')}")
                print(f"Title: {web_ui_test_case.get('title')}")
                print(f"Test script: {web_ui_test_case.get('test_script')[:200]}...")
        else:
            print("❌ Conversion failed")
            errors = result.get("errors", [])
            for error in errors:
                print(f"  Error: {error}")
    else:
        print(f"❌ Unexpected status code: {response.status_code}")

if __name__ == "__main__":
    test_conversion_endpoint()