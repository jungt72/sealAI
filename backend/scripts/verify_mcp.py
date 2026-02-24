import requests
import json
import sys

url = "http://localhost:8000/api/v1/mcp/"
headers = {"Content-Type": "application/json"}

# 1. Test tools/list
print("Testing tools/list...")
payload_list = {
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1
}

try:
    response = requests.post(url, json=payload_list, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    if response.status_code == 200 and "result" in response.json():
        print("✅ tools/list passed")
    else:
        print("❌ tools/list failed")
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

# 2. Test tools/call
print("\nTesting tools/call...")
payload_call = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "example_tool",
        "arguments": {"query": "test query"}
    },
    "id": 2
}

try:
    response = requests.post(url, json=payload_call, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    if response.status_code == 200 and "result" in response.json():
        print("✅ tools/call passed")
    else:
        print("❌ tools/call failed")
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
