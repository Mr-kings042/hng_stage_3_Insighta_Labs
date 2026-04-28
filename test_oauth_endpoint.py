#!/usr/bin/env python
"""Test the OAuth endpoint to verify environment variables are loaded"""

import httpx
import json
import time

# Wait a moment for server to be ready
time.sleep(2)

try:
    response = httpx.get(
        "http://127.0.0.1:8000/auth/github?client_type=web",
        timeout=10
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
    
    # Check for success
    data = response.json()
    if response.status_code == 200 and data.get("status") == "success":
        print("\n✅ SUCCESS: OAuth endpoint is working!")
        print(f"   - authorization_url: {data.get('authorization_url')[:50]}...")
        print(f"   - state: {data.get('state')}")
        print(f"   - code_verifier: {data.get('code_verifier')[:20]}...")
    else:
        print("\n❌ FAILED: OAuth endpoint returned error")
        print(f"   - error: {data.get('message') or data.get('detail')}")
        
except Exception as e:
    print(f"❌ Connection Error: {e}")
