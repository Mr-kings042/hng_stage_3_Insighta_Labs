#!/usr/bin/env python
"""Test all main API endpoints to verify system is working"""

import httpx
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_endpoints():
    """Test various API endpoints"""
    
    tests = [
        ("OAuth Start", "GET", "/auth/github?client_type=web", None, 200),
        ("Profile List", "GET", "/api/profiles?limit=5", None, None),  # May require auth
        ("Health Check (root)", "GET", "/", None, None),
    ]
    
    print("=" * 70)
    print("SYSTEM ENDPOINT VERIFICATION")
    print("=" * 70)
    
    for name, method, endpoint, body, expected_status in tests:
        try:
            url = f"{BASE_URL}{endpoint}"
            if method == "GET":
                response = httpx.get(url, timeout=5)
            else:
                response = httpx.post(url, json=body, timeout=5)
            
            status = response.status_code
            success = "✅" if (expected_status is None or status == expected_status) else "❌"
            
            try:
                data = response.json()
                resp_status = data.get("status", "N/A")
                print(f"\n{success} {name}")
                print(f"   Status: {status}")
                print(f"   Response Status: {resp_status}")
                if "total" in data:
                    print(f"   Total items: {data.get('total')}")
                if "authorization_url" in data:
                    print(f"   OAuth URL: {data.get('authorization_url')[:50]}...")
            except:
                print(f"\n{success} {name}")
                print(f"   Status: {status}")
                print(f"   Response: {response.text[:100]}")
        
        except Exception as e:
            print(f"\n❌ {name}")
            print(f"   Error: {str(e)}")
    
    print("\n" + "=" * 70)
    print("ENVIRONMENT VARIABLES CHECK")
    print("=" * 70)
    
    import os
    from dotenv import load_dotenv
    
    # Check if .env is loaded
    test_var = os.getenv("GITHUB_CLIENT_ID")
    if test_var:
        print(f"✅ GITHUB_CLIENT_ID is loaded: {test_var}")
    else:
        print(f"❌ GITHUB_CLIENT_ID is NOT loaded")
    
    test_var = os.getenv("GITHUB_CLIENT_SECRET")
    if test_var:
        print(f"✅ GITHUB_CLIENT_SECRET is loaded: {test_var[:10]}...")
    else:
        print(f"❌ GITHUB_CLIENT_SECRET is NOT loaded")

if __name__ == "__main__":
    test_endpoints()
