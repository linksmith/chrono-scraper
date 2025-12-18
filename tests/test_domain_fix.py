#!/usr/bin/env python3
"""
Quick test to verify domain API fix
"""

import asyncio
import json
import uuid
import httpx

BASE_URL = "http://localhost:8000"

async def approve_user_directly(user_id: int):
    """Directly approve user in database using SQL"""
    import asyncpg
    
    try:
        conn = await asyncpg.connect("postgresql://chrono_scraper:chrono_scraper_dev@postgres:5432/chrono_scraper")
        
        await conn.execute("""
            UPDATE users 
            SET approval_status = 'approved', 
                is_verified = true,
                approval_date = NOW()
            WHERE id = $1
        """, user_id)
        
        # Get researcher role
        role_result = await conn.fetchrow("SELECT id FROM roles WHERE name = 'researcher'")
        if role_result:
            role_id = role_result['id']
            # Assign role to user
            await conn.execute("""
                INSERT INTO user_roles (user_id, role_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id, role_id) DO NOTHING
            """, user_id, role_id)
        
        await conn.close()
        return True
    except Exception as e:
        print(f"Database setup failed: {e}")
        return False

async def test_domain_creation():
    client = httpx.AsyncClient(base_url=BASE_URL, timeout=60.0)
    
    try:
        # Create and approve user
        user_data = {
            "email": f"domain.fix.test.{uuid.uuid4().hex[:8]}@example.com",
            "password": "ValidPassword123!",
            "full_name": "Domain Fix Test",
            "research_purpose": "Testing domain creation API fix",
            "data_handling_agreement": True,
            "ethics_agreement": True
        }
        
        signup_response = await client.post("/api/v1/auth/register", json=user_data)
        if signup_response.status_code != 200:
            print(f"❌ Signup failed: {signup_response.status_code}")
            return
        
        user = signup_response.json()
        await approve_user_directly(user["id"])
        
        # Login
        login_response = await client.post("/api/v1/auth/login", data={
            "username": user_data["email"],
            "password": user_data["password"]
        })
        
        token = login_response.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        
        # Create project
        project_response = await client.post("/api/v1/projects/", json={
            "name": "Domain Fix Test Project",
            "description": "Testing domain creation fix"
        })
        
        project_id = project_response.json()["id"]
        
        # Test domain creation with 'domain' field
        print("🔧 Testing domain creation with 'domain' field...")
        domain_data = {
            "domain": "example.com",
            "include_subdomains": True,
            "max_pages": 100
        }
        
        response = await client.post(f"/api/v1/projects/{project_id}/domains", json=domain_data)
        
        if response.status_code in [200, 201]:
            print("✅ Domain creation with 'domain' field successful!")
        else:
            print(f"❌ Domain creation failed: {response.status_code}")
            print(f"Response: {response.text}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_domain_creation())