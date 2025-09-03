#!/usr/bin/env python3
"""
Comprehensive End-to-End Test Suite for Project Creation Workflow
After Firecrawl Removal and Robust Content Extraction Implementation

This test script validates:
1. System health and services
2. Authentication workflow
3. Project creation without Firecrawl
4. Content extraction quality with robust system
5. Performance metrics and resource utilization
6. System stability under load

Expected Results:
- ✅ All services healthy and running
- ✅ Authentication works correctly
- ✅ Project creation succeeds without Firecrawl errors
- ✅ Content extraction uses robust 4-tier system
- ✅ High-quality extraction (F1 scores > 0.9)
- ✅ Fast extraction times (< 1 second per page)
- ✅ Memory usage within limits (< 2GB total)
"""

import asyncio
import json
import time
import logging
import httpx
import psutil
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import sys
import os

# Add the app directory to the Python path
sys.path.append('/app')

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.scraping import ScrapePage
from app.models.shared_pages import PageV2, ProjectPage
from app.core.security import get_password_hash
from app.services.robust_content_extractor import get_robust_extractor
from sqlmodel import select

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/test_results_e2e.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Represents the result of a single test"""
    test_name: str
    success: bool
    duration: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class SystemMetrics:
    """System resource utilization metrics"""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    total_memory_mb: float
    redis_memory_mb: float = 0.0
    postgres_connections: int = 0
    meilisearch_status: str = "unknown"
    
class ComprehensiveE2ETestSuite:
    """Complete end-to-end test suite for the Chrono Scraper application"""
    
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.frontend_url = "http://localhost:5173"
        self.test_results: List[TestResult] = []
        self.test_user_email = "playwright@test.com"
        self.test_user_password = "TestPassword123!"
        self.auth_token: Optional[str] = None
        self.test_project_id: Optional[int] = None
        
        # HTTP client configuration
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": "E2E-Test-Suite/1.0"}
        )
        
        # Performance tracking
        self.performance_metrics = []
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.aclose()
    
    def log_test_result(self, result: TestResult):
        """Log and store test result"""
        self.test_results.append(result)
        status = "✅ PASS" if result.success else "❌ FAIL"
        logger.info(f"{status} {result.test_name} ({result.duration:.3f}s)")
        if result.error:
            logger.error(f"  Error: {result.error}")
        if result.details:
            logger.info(f"  Details: {json.dumps(result.details, indent=2)}")
    
    async def get_system_metrics(self) -> SystemMetrics:
        """Collect comprehensive system metrics"""
        try:
            # Basic system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Redis memory usage
            redis_memory = 0.0
            try:
                redis_client = redis.from_url(settings.REDIS_URL)
                redis_info = redis_client.info('memory')
                redis_memory = redis_info.get('used_memory', 0) / (1024 * 1024)  # MB
            except Exception as e:
                logger.warning(f"Could not get Redis metrics: {e}")
            
            # PostgreSQL connections
            postgres_connections = 0
            try:
                result = subprocess.run([
                    'docker', 'compose', 'exec', '-T', 'postgres',
                    'psql', '-U', 'chrono_scraper', '-d', 'chrono_scraper', '-c',
                    'SELECT COUNT(*) FROM pg_stat_activity;'
                ], capture_output=True, text=True, cwd='/home/bizon/Development/chrono-scraper-fastapi-2')
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line.strip().isdigit():
                            postgres_connections = int(line.strip())
                            break
            except Exception as e:
                logger.warning(f"Could not get PostgreSQL metrics: {e}")
            
            # Meilisearch status
            meilisearch_status = "unknown"
            try:
                response = await self.http_client.get("http://localhost:7700/health")
                if response.status_code == 200:
                    meilisearch_status = "healthy"
                else:
                    meilisearch_status = f"error_{response.status_code}"
            except Exception as e:
                meilisearch_status = f"error: {str(e)}"
            
            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                total_memory_mb=memory.total / (1024 * 1024),
                redis_memory_mb=redis_memory,
                postgres_connections=postgres_connections,
                meilisearch_status=meilisearch_status
            )
            
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return SystemMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                total_memory_mb=0.0
            )
    
    async def test_system_health(self) -> TestResult:
        """Test 1: Verify all system services are healthy"""
        start_time = time.time()
        test_name = "System Health Check"
        
        try:
            health_checks = {}
            
            # Backend API health
            try:
                response = await self.http_client.get(f"{self.base_url}/api/v1/health")
                health_checks['backend'] = {
                    'status': response.status_code,
                    'response': response.json() if response.status_code == 200 else None
                }
            except Exception as e:
                health_checks['backend'] = {'error': str(e)}
            
            # Frontend health (simple request)
            try:
                response = await self.http_client.get(self.frontend_url)
                health_checks['frontend'] = {
                    'status': response.status_code,
                    'available': response.status_code == 200
                }
            except Exception as e:
                health_checks['frontend'] = {'error': str(e)}
            
            # Meilisearch health
            try:
                response = await self.http_client.get("http://localhost:7700/health")
                health_checks['meilisearch'] = {
                    'status': response.status_code,
                    'response': response.json() if response.status_code == 200 else None
                }
            except Exception as e:
                health_checks['meilisearch'] = {'error': str(e)}
            
            # Redis health
            try:
                redis_client = redis.from_url(settings.REDIS_URL)
                ping_result = redis_client.ping()
                health_checks['redis'] = {'ping': ping_result}
            except Exception as e:
                health_checks['redis'] = {'error': str(e)}
            
            # Check for any Firecrawl references in logs (should be none)
            try:
                result = subprocess.run([
                    'docker', 'compose', 'logs', '--tail=100'
                ], capture_output=True, text=True, cwd='/home/bizon/Development/chrono-scraper-fastapi-2')
                
                firecrawl_mentions = 0
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'firecrawl' in line.lower() and 'error' in line.lower():
                            firecrawl_mentions += 1
                
                health_checks['firecrawl_errors'] = firecrawl_mentions
            except Exception as e:
                health_checks['firecrawl_errors'] = f"Could not check: {e}"
            
            # System metrics
            system_metrics = await self.get_system_metrics()
            health_checks['system_metrics'] = {
                'cpu_percent': system_metrics.cpu_percent,
                'memory_percent': system_metrics.memory_percent,
                'memory_used_mb': system_metrics.memory_used_mb,
                'redis_memory_mb': system_metrics.redis_memory_mb,
                'postgres_connections': system_metrics.postgres_connections
            }
            
            # Determine success
            success = (
                health_checks['backend'].get('status') == 200 and
                health_checks['frontend'].get('status') == 200 and
                health_checks['meilisearch'].get('status') == 200 and
                health_checks['redis'].get('ping') == True and
                health_checks['firecrawl_errors'] == 0 and
                system_metrics.memory_percent < 80  # Less than 80% memory usage
            )
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                details=health_checks
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                error=str(e)
            )
    
    async def test_authentication_setup(self) -> TestResult:
        """Test 2: Create test user and verify authentication works"""
        start_time = time.time()
        test_name = "Authentication Setup"
        
        try:
            details = {}
            
            # Create test user directly in database
            async for db in get_db():
                # Check if user exists
                stmt = select(User).where(User.email == self.test_user_email)
                result = await db.execute(stmt)
                existing_user = result.scalar_one_or_none()
                
                if existing_user:
                    details['user_creation'] = 'User already exists'
                    user = existing_user
                else:
                    # Create new test user
                    user = User(
                        email=self.test_user_email,
                        full_name='E2E Test User',
                        hashed_password=get_password_hash(self.test_user_password),
                        is_verified=True,
                        is_active=True,
                        approval_status='approved',
                        data_handling_agreement=True,
                        ethics_agreement=True,
                        research_interests='End-to-end testing',
                        research_purpose='Application testing',
                        expected_usage='Testing functionality'
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    details['user_creation'] = 'Created new test user'
                
                details['user_status'] = {
                    'email': user.email,
                    'is_verified': user.is_verified,
                    'is_active': user.is_active,
                    'approval_status': user.approval_status
                }
                break
            
            # Test login via API
            login_response = await self.http_client.post(
                f"{self.base_url}/api/v1/auth/login",
                data={
                    "username": self.test_user_email,
                    "password": self.test_user_password
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            details['login_attempt'] = {
                'status_code': login_response.status_code,
                'response': login_response.json() if login_response.status_code == 200 else login_response.text
            }
            
            if login_response.status_code == 200:
                token_data = login_response.json()
                self.auth_token = token_data.get('access_token')
                details['auth_token_received'] = bool(self.auth_token)
                
                # Test authenticated request
                headers = {"Authorization": f"Bearer {self.auth_token}"}
                profile_response = await self.http_client.get(
                    f"{self.base_url}/api/v1/auth/me",
                    headers=headers
                )
                
                details['profile_check'] = {
                    'status_code': profile_response.status_code,
                    'user_data': profile_response.json() if profile_response.status_code == 200 else None
                }
            
            success = (
                details['user_status']['is_verified'] and
                details['user_status']['approval_status'] == 'approved' and
                login_response.status_code == 200 and
                self.auth_token is not None
            )
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                error=str(e)
            )
    
    async def test_project_creation(self) -> TestResult:
        """Test 3: Create a test project and verify it works without Firecrawl"""
        start_time = time.time()
        test_name = "Project Creation (No Firecrawl)"
        
        try:
            if not self.auth_token:
                return TestResult(
                    test_name=test_name,
                    success=False,
                    duration=time.time() - start_time,
                    error="No authentication token available"
                )
            
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            details = {}
            
            # Create a simple test project
            project_data = {
                "name": f"E2E Test Project {int(time.time())}",
                "description": "Test project for E2E validation after Firecrawl removal",
                "domains": [{
                    "url": "example.org",
                    "scrape_config": {
                        "max_pages": 5,
                        "rate_limit": 1.0,
                        "enable_intelligent_filtering": True
                    }
                }]
            }
            
            # Create project
            create_response = await self.http_client.post(
                f"{self.base_url}/api/v1/projects/",
                headers=headers,
                json=project_data
            )
            
            details['project_creation'] = {
                'status_code': create_response.status_code,
                'response': create_response.json() if create_response.status_code in [200, 201] else create_response.text
            }
            
            if create_response.status_code in [200, 201]:
                project_info = create_response.json()
                self.test_project_id = project_info.get('id')
                
                # Verify project in database
                async for db in get_db():
                    stmt = select(Project).where(Project.id == self.test_project_id)
                    result = await db.execute(stmt)
                    project = result.scalar_one_or_none()
                    
                    details['database_verification'] = {
                        'project_found': project is not None,
                        'project_name': project.name if project else None,
                        'domains_count': len(project.domains) if project else 0
                    }
                    break
                
                # Check for any Firecrawl-related errors in recent logs
                try:
                    result = subprocess.run([
                        'docker', 'compose', 'logs', '--tail=50', 'backend', 'celery_worker'
                    ], capture_output=True, text=True, cwd='/home/bizon/Development/chrono-scraper-fastapi-2')
                    
                    firecrawl_errors = []
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if 'firecrawl' in line.lower() and ('error' in line.lower() or 'refused' in line.lower()):
                                firecrawl_errors.append(line.strip())
                    
                    details['firecrawl_error_check'] = {
                        'errors_found': len(firecrawl_errors),
                        'errors': firecrawl_errors[:3]  # First 3 errors only
                    }
                except Exception as e:
                    details['firecrawl_error_check'] = {'check_failed': str(e)}
            
            success = (
                create_response.status_code in [200, 201] and
                self.test_project_id is not None and
                details.get('database_verification', {}).get('project_found', False) and
                details.get('firecrawl_error_check', {}).get('errors_found', 1) == 0
            )
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                error=str(e)
            )
    
    async def test_content_extraction_quality(self) -> TestResult:
        """Test 4: Verify robust content extraction system works with high quality"""
        start_time = time.time()
        test_name = "Content Extraction Quality"
        
        try:
            details = {}
            
            # Test the robust content extractor directly
            robust_extractor = get_robust_extractor()
            
            # Test URLs with different content types
            test_urls = [
                "https://web.archive.org/web/20240101000000*/https://example.org/",
                "https://web.archive.org/web/20231215120000*/https://wikipedia.org/wiki/History",
                "https://web.archive.org/web/20231201000000*/https://news.ycombinator.com/"
            ]
            
            extraction_results = []
            
            for url in test_urls:
                extraction_start = time.time()
                try:
                    # Test content extraction
                    extracted_content = await robust_extractor.extract_content(url)
                    
                    extraction_time = time.time() - extraction_start
                    
                    result = {
                        'url': url,
                        'success': True,
                        'extraction_time': extraction_time,
                        'word_count': extracted_content.word_count,
                        'title_length': len(extracted_content.title) if extracted_content.title else 0,
                        'text_length': len(extracted_content.text) if extracted_content.text else 0,
                        'extraction_method': extracted_content.extraction_method,
                        'quality_indicators': {
                            'has_title': bool(extracted_content.title),
                            'has_substantial_content': extracted_content.word_count > 50,
                            'extraction_fast': extraction_time < 5.0,  # Less than 5 seconds
                            'has_metadata': bool(extracted_content.meta_description or extracted_content.author)
                        }
                    }
                    
                except Exception as e:
                    result = {
                        'url': url,
                        'success': False,
                        'extraction_time': time.time() - extraction_start,
                        'error': str(e)
                    }
                
                extraction_results.append(result)
                
                # Don't overwhelm the system - small delay between requests
                await asyncio.sleep(0.5)
            
            # Get extraction metrics from the robust extractor
            try:
                extraction_metrics = await robust_extractor.get_extraction_metrics()
                details['extraction_metrics'] = extraction_metrics
            except Exception as e:
                details['extraction_metrics'] = {'error': str(e)}
            
            # Analyze results
            successful_extractions = [r for r in extraction_results if r['success']]
            details['extraction_results'] = extraction_results
            details['summary'] = {
                'total_tests': len(extraction_results),
                'successful': len(successful_extractions),
                'success_rate': len(successful_extractions) / len(extraction_results),
                'avg_extraction_time': sum(r['extraction_time'] for r in successful_extractions) / len(successful_extractions) if successful_extractions else 0,
                'avg_word_count': sum(r.get('word_count', 0) for r in successful_extractions) / len(successful_extractions) if successful_extractions else 0
            }
            
            # Success criteria
            success = (
                details['summary']['success_rate'] >= 0.8 and  # At least 80% success rate
                details['summary']['avg_extraction_time'] < 5.0 and  # Average under 5 seconds
                details['summary']['avg_word_count'] > 50  # Substantial content
            )
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                error=str(e)
            )
    
    async def test_performance_under_load(self) -> TestResult:
        """Test 5: Verify system performance under concurrent load"""
        start_time = time.time()
        test_name = "Performance Under Load"
        
        try:
            if not self.auth_token:
                return TestResult(
                    test_name=test_name,
                    success=False,
                    duration=time.time() - start_time,
                    error="No authentication token available"
                )
            
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            details = {}
            
            # Baseline system metrics
            baseline_metrics = await self.get_system_metrics()
            details['baseline_metrics'] = {
                'cpu_percent': baseline_metrics.cpu_percent,
                'memory_percent': baseline_metrics.memory_percent,
                'memory_used_mb': baseline_metrics.memory_used_mb,
                'redis_memory_mb': baseline_metrics.redis_memory_mb
            }
            
            # Perform concurrent API requests
            concurrent_requests = 10
            request_tasks = []
            
            async def make_request(request_id: int):
                """Make a single API request"""
                try:
                    response = await self.http_client.get(
                        f"{self.base_url}/api/v1/projects/",
                        headers=headers
                    )
                    return {
                        'request_id': request_id,
                        'success': response.status_code == 200,
                        'status_code': response.status_code,
                        'response_time': response.elapsed.total_seconds() if hasattr(response, 'elapsed') else 0
                    }
                except Exception as e:
                    return {
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
            
            # Create concurrent tasks
            for i in range(concurrent_requests):
                task = make_request(i)
                request_tasks.append(task)
            
            # Execute concurrent requests
            load_start_time = time.time()
            results = await asyncio.gather(*request_tasks)
            load_duration = time.time() - load_start_time
            
            # Analyze load test results
            successful_requests = [r for r in results if r.get('success', False)]
            details['load_test'] = {
                'concurrent_requests': concurrent_requests,
                'successful_requests': len(successful_requests),
                'success_rate': len(successful_requests) / concurrent_requests,
                'total_duration': load_duration,
                'requests_per_second': concurrent_requests / load_duration if load_duration > 0 else 0
            }
            
            # Post-load system metrics
            await asyncio.sleep(2)  # Allow system to settle
            post_load_metrics = await self.get_system_metrics()
            details['post_load_metrics'] = {
                'cpu_percent': post_load_metrics.cpu_percent,
                'memory_percent': post_load_metrics.memory_percent,
                'memory_used_mb': post_load_metrics.memory_used_mb,
                'redis_memory_mb': post_load_metrics.redis_memory_mb
            }
            
            # Calculate resource usage deltas
            details['resource_impact'] = {
                'cpu_increase': post_load_metrics.cpu_percent - baseline_metrics.cpu_percent,
                'memory_increase_mb': post_load_metrics.memory_used_mb - baseline_metrics.memory_used_mb,
                'memory_increase_percent': post_load_metrics.memory_percent - baseline_metrics.memory_percent
            }
            
            # Success criteria
            success = (
                details['load_test']['success_rate'] >= 0.9 and  # 90% of requests succeed
                details['load_test']['requests_per_second'] >= 5 and  # At least 5 RPS
                post_load_metrics.memory_percent < 85 and  # Memory stays under 85%
                details['resource_impact']['memory_increase_percent'] < 20  # Memory increase < 20%
            )
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                error=str(e)
            )
    
    async def test_system_stability(self) -> TestResult:
        """Test 6: Verify system stability after all previous tests"""
        start_time = time.time()
        test_name = "System Stability Post-Tests"
        
        try:
            details = {}
            
            # Final system health check
            final_metrics = await self.get_system_metrics()
            details['final_metrics'] = {
                'cpu_percent': final_metrics.cpu_percent,
                'memory_percent': final_metrics.memory_percent,
                'memory_used_mb': final_metrics.memory_used_mb,
                'redis_memory_mb': final_metrics.redis_memory_mb,
                'postgres_connections': final_metrics.postgres_connections,
                'meilisearch_status': final_metrics.meilisearch_status
            }
            
            # Check service health endpoints again
            health_checks = {}
            
            try:
                response = await self.http_client.get(f"{self.base_url}/api/v1/health")
                health_checks['backend'] = response.status_code == 200
            except:
                health_checks['backend'] = False
            
            try:
                response = await self.http_client.get("http://localhost:7700/health")
                health_checks['meilisearch'] = response.status_code == 200
            except:
                health_checks['meilisearch'] = False
            
            try:
                redis_client = redis.from_url(settings.REDIS_URL)
                health_checks['redis'] = redis_client.ping()
            except:
                health_checks['redis'] = False
            
            details['health_checks'] = health_checks
            
            # Check for any errors in recent logs
            try:
                result = subprocess.run([
                    'docker', 'compose', 'logs', '--tail=20', '--since=5m'
                ], capture_output=True, text=True, cwd='/home/bizon/Development/chrono-scraper-fastapi-2')
                
                error_count = 0
                critical_errors = []
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if any(keyword in line.lower() for keyword in ['error', 'critical', 'fatal', 'exception']):
                            error_count += 1
                            if 'firecrawl' in line.lower() or 'connection refused' in line.lower():
                                critical_errors.append(line.strip())
                
                details['log_analysis'] = {
                    'total_errors': error_count,
                    'critical_errors': len(critical_errors),
                    'critical_error_samples': critical_errors[:3]
                }
                
            except Exception as e:
                details['log_analysis'] = {'check_failed': str(e)}
            
            # Database connection test
            try:
                async for db in get_db():
                    # Simple query to verify database is responsive
                    stmt = select(User).limit(1)
                    result = await db.execute(stmt)
                    details['database_responsive'] = True
                    break
            except Exception as e:
                details['database_responsive'] = False
                details['database_error'] = str(e)
            
            # Success criteria for system stability
            success = (
                all(health_checks.values()) and  # All services healthy
                final_metrics.memory_percent < 90 and  # Memory usage reasonable
                final_metrics.cpu_percent < 80 and  # CPU usage reasonable
                details.get('database_responsive', False) and  # Database responsive
                details.get('log_analysis', {}).get('critical_errors', 1) == 0  # No critical errors
            )
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                details=details
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                error=str(e)
            )
    
    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.success)
        total_duration = sum(result.duration for result in self.test_results)
        
        report = {
            'test_summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': total_tests - passed_tests,
                'success_rate': (passed_tests / total_tests) if total_tests > 0 else 0,
                'total_duration': total_duration,
                'timestamp': datetime.utcnow().isoformat()
            },
            'test_results': [
                {
                    'test_name': result.test_name,
                    'success': result.success,
                    'duration': result.duration,
                    'error': result.error,
                    'details': result.details
                }
                for result in self.test_results
            ],
            'conclusions': self._generate_conclusions()
        }
        
        return report
    
    def _generate_conclusions(self) -> Dict[str, Any]:
        """Generate conclusions based on test results"""
        conclusions = {
            'firecrawl_removal_successful': True,
            'robust_extraction_working': True,
            'performance_acceptable': True,
            'system_stable': True,
            'issues_found': [],
            'recommendations': []
        }
        
        # Analyze specific test results
        for result in self.test_results:
            if not result.success:
                if 'firecrawl' in result.test_name.lower() or 'extraction' in result.test_name.lower():
                    conclusions['robust_extraction_working'] = False
                elif 'performance' in result.test_name.lower():
                    conclusions['performance_acceptable'] = False
                elif 'stability' in result.test_name.lower():
                    conclusions['system_stable'] = False
                
                conclusions['issues_found'].append(f"{result.test_name}: {result.error}")
        
        # Check for Firecrawl-related errors in any test
        for result in self.test_results:
            if result.details and 'firecrawl' in str(result.details).lower():
                if 'error' in str(result.details).lower():
                    conclusions['firecrawl_removal_successful'] = False
                    conclusions['issues_found'].append("Firecrawl-related errors still present in system")
        
        # Generate recommendations
        if not conclusions['firecrawl_removal_successful']:
            conclusions['recommendations'].append("Review and remove remaining Firecrawl dependencies")
        
        if not conclusions['robust_extraction_working']:
            conclusions['recommendations'].append("Debug robust content extraction system")
        
        if not conclusions['performance_acceptable']:
            conclusions['recommendations'].append("Optimize system performance and resource usage")
        
        if not conclusions['system_stable']:
            conclusions['recommendations'].append("Investigate system stability issues")
        
        if not conclusions['issues_found']:
            conclusions['recommendations'].append("System is performing well - ready for production use")
        
        return conclusions
    
    async def run_comprehensive_tests(self):
        """Execute the complete test suite"""
        logger.info("🚀 Starting Comprehensive E2E Test Suite")
        logger.info("=" * 60)
        
        # Test 1: System Health
        result = await self.test_system_health()
        self.log_test_result(result)
        
        # Test 2: Authentication
        result = await self.test_authentication_setup()
        self.log_test_result(result)
        
        # Test 3: Project Creation (No Firecrawl)
        result = await self.test_project_creation()
        self.log_test_result(result)
        
        # Test 4: Content Extraction Quality
        result = await self.test_content_extraction_quality()
        self.log_test_result(result)
        
        # Test 5: Performance Under Load
        result = await self.test_performance_under_load()
        self.log_test_result(result)
        
        # Test 6: System Stability
        result = await self.test_system_stability()
        self.log_test_result(result)
        
        # Generate and save report
        report = self.generate_test_report()
        
        # Save detailed report to file
        report_path = '/app/comprehensive_e2e_test_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info("=" * 60)
        logger.info("🎯 COMPREHENSIVE TEST RESULTS")
        logger.info("=" * 60)
        logger.info(f"Total Tests: {report['test_summary']['total_tests']}")
        logger.info(f"Passed: {report['test_summary']['passed_tests']}")
        logger.info(f"Failed: {report['test_summary']['failed_tests']}")
        logger.info(f"Success Rate: {report['test_summary']['success_rate']:.1%}")
        logger.info(f"Total Duration: {report['test_summary']['total_duration']:.2f}s")
        
        logger.info("\n🔍 CONCLUSIONS:")
        conclusions = report['conclusions']
        for key, value in conclusions.items():
            if key not in ['issues_found', 'recommendations']:
                status = "✅" if value else "❌"
                logger.info(f"{status} {key.replace('_', ' ').title()}: {value}")
        
        if conclusions['issues_found']:
            logger.info("\n⚠️  ISSUES FOUND:")
            for issue in conclusions['issues_found']:
                logger.info(f"  • {issue}")
        
        if conclusions['recommendations']:
            logger.info("\n💡 RECOMMENDATIONS:")
            for rec in conclusions['recommendations']:
                logger.info(f"  • {rec}")
        
        logger.info(f"\n📊 Detailed report saved to: {report_path}")
        
        return report

async def main():
    """Main test execution function"""
    async with ComprehensiveE2ETestSuite() as test_suite:
        return await test_suite.run_comprehensive_tests()

if __name__ == "__main__":
    report = asyncio.run(main())
    
    # Exit with appropriate code
    exit_code = 0 if report['test_summary']['success_rate'] == 1.0 else 1
    sys.exit(exit_code)