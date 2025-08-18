#!/usr/bin/env python3
"""
Simple session test - just test if Redis sessions work
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_session():
    """Test basic session functionality"""
    print("🧪 Simple Redis Session Test")
    print("=" * 40)
    
    # Create session with cookies
    session = requests.Session()
    
    # Step 1: Login
    print("1. Testing login...")
    login_data = {
        "email": "session_test@example.com",
        "password": "TestPassword123!"
    }
    
    response = session.post(
        f"{BASE_URL}/api/v1/auth/login/json",
        json=login_data
    )
    
    print(f"   Login status: {response.status_code}")
    if response.status_code == 200:
        user_data = response.json()
        print(f"   ✅ Logged in as: {user_data['email']}")
        
        # Check cookies
        print(f"   Cookies received: {list(session.cookies.keys())}")
        
        if 'session_id' in session.cookies:
            session_id = session.cookies['session_id']
            print(f"   ✅ Session ID: {session_id[:20]}...")
        else:
            print("   ❌ No session_id cookie found")
            return False
            
    else:
        print(f"   ❌ Login failed: {response.text}")
        return False
    
    # Step 2: Test auth endpoint
    print("\n2. Testing authenticated endpoint...")
    response = session.get(f"{BASE_URL}/api/v1/auth/me")
    
    if response.status_code == 200:
        user_data = response.json()
        print(f"   ✅ Authenticated as: {user_data['email']}")
    else:
        print(f"   ❌ Auth check failed: {response.status_code} - {response.text}")
        return False
    
    # Step 3: Check Redis directly
    print("\n3. Checking Redis session storage...")
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # List session keys
        session_keys = r.keys("session:*")
        print(f"   Session keys in Redis: {len(session_keys)}")
        
        if session_keys:
            # Get one session
            sample_session = r.get(session_keys[0])
            if sample_session:
                session_data = json.loads(sample_session)
                print(f"   ✅ Session found for user: {session_data.get('email')}")
            else:
                print("   ❌ Session key exists but no data")
                return False
        else:
            print("   ❌ No sessions found in Redis")
            return False
            
    except Exception as e:
        print(f"   ❌ Redis check failed: {e}")
        return False
    
    print("\n🎉 All session tests passed!")
    return True

if __name__ == "__main__":
    success = test_session()
    if not success:
        print("\n❌ Session test failed")
        exit(1)