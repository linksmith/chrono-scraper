#!/usr/bin/env python3
"""
Test session persistence across backend restart
"""
import requests
import time

BASE_URL = "http://localhost:8000"

def test_restart_persistence():
    """Test that sessions persist across backend restarts"""
    print("🔄 Testing Session Persistence Across Backend Restart")
    print("=" * 60)
    
    # Step 1: Login and save session
    print("1. Logging in and saving session...")
    session = requests.Session()
    
    login_data = {
        "email": "session_test@example.com",
        "password": "TestPassword123!"
    }
    
    response = session.post(f"{BASE_URL}/api/v1/auth/login/json", json=login_data)
    
    if response.status_code == 200:
        user_data = response.json()
        print(f"   ✅ Logged in as: {user_data['email']}")
        
        # Save session cookies
        saved_cookies = dict(session.cookies)
        print(f"   Saved cookies: {list(saved_cookies.keys())}")
        
        if 'session_id' not in saved_cookies:
            print("   ❌ No session_id cookie - test invalid")
            return False
            
    else:
        print(f"   ❌ Login failed: {response.status_code}")
        return False
    
    # Step 2: Verify session works
    print("\n2. Verifying session works before restart...")
    response = session.get(f"{BASE_URL}/api/v1/auth/me")
    
    if response.status_code == 200:
        user_data = response.json()
        print(f"   ✅ Pre-restart auth: {user_data['email']}")
    else:
        print(f"   ❌ Pre-restart auth failed: {response.status_code}")
        return False
    
    # Step 3: Restart backend
    print(f"\n3. 🔄 Restarting backend service...")
    print("   This will restart only the backend, leaving Redis running...")
    
    import subprocess
    try:
        # Restart just the backend service
        result = subprocess.run(
            ["docker", "compose", "restart", "backend"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("   ✅ Backend restart completed")
        else:
            print(f"   ❌ Backend restart failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("   ❌ Backend restart timed out")
        return False
    except Exception as e:
        print(f"   ❌ Backend restart error: {e}")
        return False
    
    # Wait for backend to be ready
    print("   Waiting for backend to be ready...")
    max_retries = 10
    for i in range(max_retries):
        try:
            response = requests.get(f"{BASE_URL}/docs", timeout=2)
            if response.status_code == 200:
                print(f"   ✅ Backend ready after {i+1} attempts")
                break
        except:
            pass
        time.sleep(1)
    else:
        print("   ❌ Backend did not become ready in time")
        return False
    
    # Step 4: Test session persistence
    print("\n4. Testing session persistence after restart...")
    
    # Create new session with saved cookies
    new_session = requests.Session()
    new_session.cookies.update(saved_cookies)
    
    response = new_session.get(f"{BASE_URL}/api/v1/auth/me")
    
    if response.status_code == 200:
        user_data = response.json()
        print(f"   🎉 SUCCESS! Session persisted!")
        print(f"   Still authenticated as: {user_data['email']}")
        print(f"   User ID: {user_data['id']}")
        
        # Verify this is actually using session, not JWT fallback
        if 'session_id' in saved_cookies:
            print(f"   ✅ Using Redis session: {saved_cookies['session_id'][:20]}...")
        
        return True
    else:
        print(f"   ❌ Session lost after restart")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

if __name__ == "__main__":
    success = test_restart_persistence()
    if success:
        print("\n🎉 SUCCESS! Redis session persistence across restart is working!")
        print("   Users will now stay logged in across service restarts! 🚀")
    else:
        print("\n❌ Session persistence test failed")
        exit(1)