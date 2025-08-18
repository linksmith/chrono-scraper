#!/usr/bin/env python3
"""
Test session persistence across service restarts
"""
import asyncio
import aiohttp
import json
import time

BASE_URL = "http://localhost:8000"
TEST_USER = {
    "email": "session_test@example.com",
    "username": "sessiontest",
    "password": "TestPassword123!",
    "full_name": "Session Test User"
}

async def test_session_persistence():
    """Test that sessions persist across backend restarts"""
    
    async with aiohttp.ClientSession() as session:
        print("🧪 Testing Redis Session Persistence")
        print("=" * 50)
        
        # Step 1: Register test user (if not exists)
        print("1. Registering test user...")
        register_data = {
            "email": TEST_USER["email"],
            "password": TEST_USER["password"],
            "username": TEST_USER["username"],
            "full_name": TEST_USER["full_name"]
        }
        
        async with session.post(
            f"{BASE_URL}/api/v1/auth/register",
            json=register_data
        ) as resp:
            if resp.status in [200, 201]:
                print("✅ User registered successfully")
            elif resp.status in [400, 500]:
                error_text = await resp.text()
                if "already exists" in error_text.lower() or "duplicate key" in error_text.lower():
                    print("✅ User already exists, continuing...")
                else:
                    print(f"❌ Registration failed: {error_text}")
                    return False
            else:
                print(f"❌ Registration failed with status {resp.status}")
                return False
        
        # Step 2: Login and get session
        print("\n2. Logging in with JSON endpoint...")
        login_data = {
            "email": TEST_USER["email"],
            "password": TEST_USER["password"]
        }
        
        async with session.post(
            f"{BASE_URL}/api/v1/auth/login/json",
            json=login_data
        ) as resp:
            if resp.status == 200:
                user_data = await resp.json()
                print(f"✅ Logged in as: {user_data['email']}")
                
                # Extract session cookie
                session_cookie = None
                for cookie in resp.cookies:
                    if cookie.key == "session_id":
                        session_cookie = cookie.value
                        print(f"✅ Session ID received: {session_cookie[:20]}...")
                        break
                
                if not session_cookie:
                    print("❌ No session_id cookie found")
                    return False
                    
            else:
                error_text = await resp.text()
                print(f"❌ Login failed: {error_text}")
                return False
        
        # Step 3: Verify session works
        print("\n3. Verifying session authentication...")
        async with session.get(f"{BASE_URL}/api/v1/auth/me") as resp:
            if resp.status == 200:
                user_data = await resp.json()
                print(f"✅ Session authenticated: {user_data['email']}")
            else:
                print(f"❌ Session verification failed: {resp.status}")
                return False
        
        # Step 4: Store session for post-restart test
        session_cookies = {}
        for cookie in session.cookie_jar:
            session_cookies[cookie.key] = cookie.value
        
        print("\n4. Stored session cookies for restart test")
        print(f"   Session cookies: {list(session_cookies.keys())}")
        
        # Step 5: Wait for manual backend restart
        print("\n5. 🔄 Please restart the backend service now...")
        print("   Run: docker compose restart backend")
        print("   Press Enter when backend is restarted...")
        input()
        
        # Wait a moment for backend to fully start
        print("   Waiting 5 seconds for backend to fully start...")
        await asyncio.sleep(5)
        
        # Step 6: Test session persistence after restart
        print("\n6. Testing session after backend restart...")
        
        # Create new session with stored cookies
        new_session = aiohttp.ClientSession()
        for key, value in session_cookies.items():
            new_session.cookie_jar.update_cookies({key: value})
        
        try:
            async with new_session.get(f"{BASE_URL}/api/v1/auth/me") as resp:
                if resp.status == 200:
                    user_data = await resp.json()
                    print(f"🎉 SUCCESS! Session persisted across restart!")
                    print(f"   Still authenticated as: {user_data['email']}")
                    print(f"   User ID: {user_data['id']}")
                    return True
                else:
                    print(f"❌ Session lost after restart (status: {resp.status})")
                    error_text = await resp.text()
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Error testing post-restart session: {e}")
            return False
        finally:
            await new_session.close()

if __name__ == "__main__":
    success = asyncio.run(test_session_persistence())
    if success:
        print("\n🎉 All tests passed! Redis session persistence is working!")
    else:
        print("\n❌ Tests failed. Check the implementation.")