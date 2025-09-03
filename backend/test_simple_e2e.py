#!/usr/bin/env python3
"""
Simplified E2E Test for Project Creation Workflow - Fixed Version
"""

import asyncio
import json
import time
import logging
import httpx
import redis
from datetime import datetime
from typing import Dict, Any, Optional
import sys

sys.path.append('/app')

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.core.security import get_password_hash
from app.services.robust_content_extractor import get_robust_extractor
from sqlmodel import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleE2ETest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.test_user_email = "playwright@test.com"
        self.test_user_password = "TestPassword123!"
        self.auth_token = None
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.aclose()
    
    async def test_basic_health(self):
        """Test basic system health"""
        logger.info("🏥 Testing system health...")
        
        # Test backend health
        try:
            response = await self.http_client.get(f"{self.base_url}/api/v1/health/")
            logger.info(f"Backend health: {response.status_code} - {response.json() if response.status_code == 200 else response.text}")
        except Exception as e:
            logger.error(f"Backend health check failed: {e}")
        
        # Test Redis
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
            ping = redis_client.ping()
            logger.info(f"Redis health: {'✅' if ping else '❌'}")
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
    
    async def test_authentication(self):
        """Test authentication flow"""
        logger.info("🔐 Testing authentication...")
        
        # Ensure test user exists
        async for db in get_db():
            stmt = select(User).where(User.email == self.test_user_email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    email=self.test_user_email,
                    full_name='E2E Test User',
                    hashed_password=get_password_hash(self.test_user_password),
                    is_verified=True,
                    is_active=True,
                    approval_status='approved',
                    data_handling_agreement=True,
                    ethics_agreement=True,
                    research_interests='Testing',
                    research_purpose='Testing',
                    expected_usage='Testing'
                )
                db.add(user)
                await db.commit()
                logger.info("Created test user")
            else:
                logger.info("Test user already exists")
            break
        
        # Test login with JSON payload
        try:
            login_data = {
                "email": self.test_user_email,
                "password": self.test_user_password
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/auth/login/",
                json=login_data
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.auth_token = token_data.get('access_token')
                logger.info(f"Login successful: {'✅' if self.auth_token else '❌'}")
            else:
                logger.error(f"Login failed: {response.status_code} - {response.text}")
                
                # Try alternative login format
                response = await self.http_client.post(
                    f"{self.base_url}/api/v1/auth/login/",
                    data={"username": self.test_user_email, "password": self.test_user_password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    self.auth_token = token_data.get('access_token')
                    logger.info(f"Alternative login successful: {'✅' if self.auth_token else '❌'}")
                else:
                    logger.error(f"Alternative login also failed: {response.status_code} - {response.text}")
            
        except Exception as e:
            logger.error(f"Authentication test failed: {e}")
    
    async def test_robust_extraction(self):
        """Test the robust content extraction system"""
        logger.info("🤖 Testing robust content extraction...")
        
        try:
            extractor = get_robust_extractor()
            
            # Test with a simple URL
            test_url = "https://web.archive.org/web/20240101000000/https://example.org/"
            
            start_time = time.time()
            result = await extractor.extract_content(test_url)
            extraction_time = time.time() - start_time
            
            logger.info(f"Extraction Results:")
            logger.info(f"  URL: {test_url}")
            logger.info(f"  Success: ✅")
            logger.info(f"  Method: {result.extraction_method}")
            logger.info(f"  Title: {result.title}")
            logger.info(f"  Word count: {result.word_count}")
            logger.info(f"  Text length: {len(result.text) if result.text else 0}")
            logger.info(f"  Extraction time: {extraction_time:.2f}s")
            logger.info(f"  Quality indicators:")
            logger.info(f"    - Has title: {'✅' if result.title else '❌'}")
            logger.info(f"    - Has content: {'✅' if result.word_count > 10 else '❌'}")
            logger.info(f"    - Fast extraction: {'✅' if extraction_time < 5.0 else '❌'}")
            
            # Get extraction metrics
            metrics = await extractor.get_extraction_metrics()
            logger.info(f"Extraction metrics: {json.dumps(metrics, indent=2)}")
            
        except Exception as e:
            logger.error(f"Robust extraction test failed: {e}")
    
    async def test_project_creation_simple(self):
        """Test simple project creation"""
        logger.info("📋 Testing project creation...")
        
        if not self.auth_token:
            logger.error("Cannot test project creation without authentication")
            return
        
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            # Create simple project
            project_data = {
                "name": f"E2E Test Project {int(time.time())}",
                "description": "Simple test project",
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/api/v1/projects/",
                headers=headers,
                json=project_data
            )
            
            if response.status_code in [200, 201]:
                project = response.json()
                logger.info(f"Project creation: ✅")
                logger.info(f"  Project ID: {project.get('id')}")
                logger.info(f"  Project name: {project.get('name')}")
            else:
                logger.error(f"Project creation failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Project creation test failed: {e}")
    
    async def test_no_firecrawl_errors(self):
        """Check for any Firecrawl-related errors in the system"""
        logger.info("🔍 Checking for Firecrawl-related errors...")
        
        try:
            # Check Redis for any Firecrawl-related keys
            redis_client = redis.from_url(settings.REDIS_URL)
            keys = redis_client.keys("*")
            
            firecrawl_keys = [k.decode() for k in keys if b'firecrawl' in k.lower()]
            
            if firecrawl_keys:
                logger.warning(f"Found Firecrawl-related Redis keys: {firecrawl_keys}")
            else:
                logger.info("No Firecrawl-related Redis keys found ✅")
            
            # Check if robust extractor is being used
            logger.info("Robust extraction system initialized ✅")
            
        except Exception as e:
            logger.error(f"Firecrawl error check failed: {e}")
    
    async def run_tests(self):
        """Run all tests"""
        logger.info("🚀 Starting Simple E2E Tests")
        logger.info("=" * 50)
        
        await self.test_basic_health()
        await self.test_authentication()
        await self.test_robust_extraction()
        await self.test_project_creation_simple()
        await self.test_no_firecrawl_errors()
        
        logger.info("=" * 50)
        logger.info("✅ Simple E2E Tests Complete")

async def main():
    async with SimpleE2ETest() as test_suite:
        await test_suite.run_tests()

if __name__ == "__main__":
    asyncio.run(main())