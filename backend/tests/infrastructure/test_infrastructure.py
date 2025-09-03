"""
Test Infrastructure and Data Management Utilities for Phase 2 Performance Testing

This module provides comprehensive infrastructure utilities for the Phase 2 DuckDB analytics
performance testing suite, including database setup, test data generation, environment
management, and cleanup utilities.

Features:
- Database setup and teardown for isolated test environments
- Synthetic test data generation with realistic patterns
- Performance test environment configuration
- Resource monitoring and cleanup utilities
- Test data persistence and reuse capabilities
- Environment validation and health checks
"""

import asyncio
import json
import logging
import os
import random
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiofiles
import psutil
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, select

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.scraping import ScrapePage
from app.models.shared_pages import PageV2, ProjectPage
from app.models.user import User
from app.services.duckdb_service import DuckDBService
from app.services.parquet_pipeline import ParquetPipeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestEnvironment(Enum):
    """Test environment types"""
    UNIT = "unit"
    INTEGRATION = "integration"
    LOAD = "load"
    STRESS = "stress"
    PERFORMANCE = "performance"


class DataScale(Enum):
    """Test data scale options"""
    SMALL = "small"      # ~1K records
    MEDIUM = "medium"    # ~10K records
    LARGE = "large"      # ~100K records
    XLARGE = "xlarge"    # ~1M records


@dataclass
class TestDataConfig:
    """Configuration for test data generation"""
    scale: DataScale
    num_users: int
    num_projects: int
    num_domains: int
    num_pages: int
    num_scrape_pages: int
    date_range_days: int
    include_content: bool = True
    include_entities: bool = True
    include_metadata: bool = True
    
    @classmethod
    def for_scale(cls, scale: DataScale) -> 'TestDataConfig':
        """Create configuration for specific data scale"""
        configs = {
            DataScale.SMALL: cls(
                scale=scale, num_users=10, num_projects=5, num_domains=20,
                num_pages=1000, num_scrape_pages=2000, date_range_days=30
            ),
            DataScale.MEDIUM: cls(
                scale=scale, num_users=50, num_projects=25, num_domains=100,
                num_pages=10000, num_scrape_pages=20000, date_range_days=90
            ),
            DataScale.LARGE: cls(
                scale=scale, num_users=200, num_projects=100, num_domains=500,
                num_pages=100000, num_scrape_pages=200000, date_range_days=365
            ),
            DataScale.XLARGE: cls(
                scale=scale, num_users=1000, num_projects=500, num_domains=2000,
                num_pages=1000000, num_scrape_pages=2000000, date_range_days=730
            )
        }
        return configs[scale]


@dataclass
class EnvironmentMetrics:
    """Environment resource metrics"""
    cpu_cores: int
    total_memory_gb: float
    available_memory_gb: float
    disk_space_gb: float
    database_connections: int
    redis_memory_mb: float
    meilisearch_memory_mb: float
    duckdb_cache_mb: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TestSession:
    """Test session metadata"""
    session_id: str
    environment: TestEnvironment
    data_config: TestDataConfig
    start_time: datetime
    end_time: Optional[datetime] = None
    cleanup_completed: bool = False
    resources_used: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TestDataGenerator:
    """Generates realistic synthetic test data"""
    
    def __init__(self, config: TestDataConfig):
        self.config = config
        self.domains = [
            "example.com", "test.org", "sample.edu", "demo.gov", "mock.net",
            "research.ac.uk", "university.edu", "company.com", "news.org",
            "archive.org", "wikipedia.org", "github.com", "stackoverflow.com"
        ]
        self.url_patterns = [
            "/article/{id}", "/page/{slug}", "/post/{date}/{title}",
            "/research/{category}/{paper}", "/news/{year}/{month}/{article}",
            "/docs/{section}/{page}", "/blog/{author}/{post}"
        ]
        
    def generate_realistic_urls(self, count: int) -> List[str]:
        """Generate realistic URLs for test data"""
        urls = []
        for _ in range(count):
            domain = random.choice(self.domains)
            pattern = random.choice(self.url_patterns)
            
            # Generate pattern values
            url = pattern.format(
                id=random.randint(1, 100000),
                slug=f"test-slug-{random.randint(1, 1000)}",
                date=f"{random.randint(2020, 2024)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
                title=f"article-{random.randint(1, 10000)}",
                category=random.choice(["science", "tech", "politics", "health"]),
                paper=f"paper-{random.randint(1, 1000)}",
                year=random.randint(2020, 2024),
                month=random.randint(1, 12),
                article=f"story-{random.randint(1, 5000)}",
                section=random.choice(["api", "guides", "tutorials"]),
                page=f"page-{random.randint(1, 100)}",
                author=f"author{random.randint(1, 50)}",
                post=f"post-{random.randint(1, 2000)}"
            )
            urls.append(f"https://{domain}{url}")
        return urls
    
    def generate_realistic_content(self, url: str) -> Tuple[str, str]:
        """Generate realistic content for a URL"""
        # Simple content generation based on URL patterns
        if "/article/" in url or "/news/" in url:
            title = f"News Article: {url.split('/')[-1].replace('-', ' ').title()}"
            content = f"This is a news article about {title.lower()}. " * random.randint(10, 50)
        elif "/research/" in url or "/paper/" in url:
            title = f"Research Paper: {url.split('/')[-1].replace('-', ' ').title()}"
            content = f"Abstract: This research paper discusses {title.lower()}. " * random.randint(20, 100)
        elif "/blog/" in url:
            title = f"Blog Post: {url.split('/')[-1].replace('-', ' ').title()}"
            content = f"Blog content about {title.lower()}. " * random.randint(5, 30)
        else:
            title = f"Web Page: {url.split('/')[-1].replace('-', ' ').title()}"
            content = f"General web page content about {title.lower()}. " * random.randint(3, 20)
            
        return title, content
    
    def generate_entities(self, content: str) -> List[Dict[str, Any]]:
        """Generate realistic entities from content"""
        entities = []
        words = content.split()
        
        # Generate person entities
        for _ in range(random.randint(0, 3)):
            entities.append({
                "text": f"Person {random.randint(1, 1000)}",
                "label": "PERSON",
                "confidence": random.uniform(0.7, 0.95),
                "start_char": random.randint(0, len(content) - 10),
                "end_char": random.randint(0, len(content))
            })
        
        # Generate organization entities
        for _ in range(random.randint(0, 2)):
            entities.append({
                "text": f"Organization {random.randint(1, 500)}",
                "label": "ORG",
                "confidence": random.uniform(0.6, 0.9),
                "start_char": random.randint(0, len(content) - 10),
                "end_char": random.randint(0, len(content))
            })
            
        return entities


class TestDatabaseManager:
    """Manages test database setup, teardown, and isolation"""
    
    def __init__(self, environment: TestEnvironment):
        self.environment = environment
        self.test_db_name = f"test_chrono_{environment.value}_{uuid.uuid4().hex[:8]}"
        self.engine = None
        
    async def setup_isolated_database(self) -> str:
        """Create isolated test database"""
        logger.info(f"Setting up isolated database: {self.test_db_name}")
        
        # Create test database
        admin_engine = create_engine(
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/postgres"
        )
        
        with admin_engine.connect() as conn:
            conn.execute(text("COMMIT"))  # End any existing transaction
            conn.execute(text(f'CREATE DATABASE "{self.test_db_name}"'))
            
        # Create engine for test database
        self.engine = create_engine(
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{self.test_db_name}"
        )
        
        # Create all tables
        SQLModel.metadata.create_all(self.engine)
        
        logger.info(f"Test database ready: {self.test_db_name}")
        return self.test_db_name
    
    async def cleanup_database(self):
        """Clean up test database"""
        if self.engine:
            self.engine.dispose()
            
        admin_engine = create_engine(
            f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/postgres"
        )
        
        with admin_engine.connect() as conn:
            conn.execute(text("COMMIT"))
            # Terminate connections
            conn.execute(text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{self.test_db_name}'"
            ))
            conn.execute(text(f'DROP DATABASE IF EXISTS "{self.test_db_name}"'))
            
        logger.info(f"Cleaned up test database: {self.test_db_name}")


class TestEnvironmentManager:
    """Manages test environment setup, monitoring, and cleanup"""
    
    def __init__(self, environment: TestEnvironment):
        self.environment = environment
        self.session_id = str(uuid.uuid4())
        self.db_manager = TestDatabaseManager(environment)
        self.temp_dirs: List[Path] = []
        self.background_tasks: List[asyncio.Task] = []
        
    @asynccontextmanager
    async def managed_environment(self, data_config: TestDataConfig) -> AsyncGenerator[TestSession, None]:
        """Context manager for complete test environment lifecycle"""
        session = TestSession(
            session_id=self.session_id,
            environment=self.environment,
            data_config=data_config,
            start_time=datetime.utcnow()
        )
        
        try:
            logger.info(f"Setting up test environment: {self.environment.value}")
            
            # Setup isolated database
            db_name = await self.db_manager.setup_isolated_database()
            session.resources_used["database"] = db_name
            
            # Setup temporary directories
            temp_dir = Path(tempfile.mkdtemp(prefix=f"test_{self.environment.value}_"))
            self.temp_dirs.append(temp_dir)
            session.resources_used["temp_directory"] = str(temp_dir)
            
            # Initialize DuckDB for analytics tests
            if self.environment in [TestEnvironment.PERFORMANCE, TestEnvironment.LOAD]:
                duckdb_path = temp_dir / "test.duckdb"
                session.resources_used["duckdb_path"] = str(duckdb_path)
            
            # Record initial metrics
            session.metadata["start_metrics"] = await self.get_environment_metrics()
            
            logger.info(f"Test environment ready: {session.session_id}")
            yield session
            
        finally:
            # Cleanup
            session.end_time = datetime.utcnow()
            session.metadata["end_metrics"] = await self.get_environment_metrics()
            await self.cleanup_environment()
            session.cleanup_completed = True
            
            logger.info(f"Test environment cleaned up: {session.session_id}")
    
    async def get_environment_metrics(self) -> EnvironmentMetrics:
        """Get current environment resource metrics"""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return EnvironmentMetrics(
            cpu_cores=psutil.cpu_count(),
            total_memory_gb=memory.total / (1024**3),
            available_memory_gb=memory.available / (1024**3),
            disk_space_gb=disk.free / (1024**3),
            database_connections=await self._get_db_connections(),
            redis_memory_mb=await self._get_redis_memory(),
            meilisearch_memory_mb=await self._get_meilisearch_memory(),
            duckdb_cache_mb=0  # TODO: Get from DuckDB service
        )
    
    async def _get_db_connections(self) -> int:
        """Get current database connection count"""
        try:
            async for db in get_db():
                result = await db.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
                )
                return result.scalar() or 0
        except Exception:
            return 0
    
    async def _get_redis_memory(self) -> float:
        """Get Redis memory usage in MB"""
        # TODO: Implement Redis memory monitoring
        return 0.0
    
    async def _get_meilisearch_memory(self) -> float:
        """Get Meilisearch memory usage in MB"""
        # TODO: Implement Meilisearch memory monitoring
        return 0.0
    
    async def cleanup_environment(self):
        """Clean up all test environment resources"""
        # Cancel background tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Clean up temporary directories
        import shutil
        for temp_dir in self.temp_dirs:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Clean up database
        await self.db_manager.cleanup_database()
        
        logger.info("Environment cleanup completed")


class TestDataPopulator:
    """Populates test databases with realistic synthetic data"""
    
    def __init__(self, db_manager: TestDatabaseManager):
        self.db_manager = db_manager
        self.data_generator = None
        
    async def populate_test_data(self, config: TestDataConfig) -> Dict[str, int]:
        """Populate database with test data according to configuration"""
        self.data_generator = TestDataGenerator(config)
        
        logger.info(f"Populating test data: {config.scale.value}")
        
        stats = {
            "users": 0,
            "projects": 0,
            "pages": 0,
            "scrape_pages": 0,
            "project_pages": 0
        }
        
        async with self._get_db_session() as db:
            # Create users
            users = await self._create_test_users(db, config.num_users)
            stats["users"] = len(users)
            
            # Create projects
            projects = await self._create_test_projects(db, users, config.num_projects)
            stats["projects"] = len(projects)
            
            # Create pages and scrape pages
            pages = await self._create_test_pages(db, config.num_pages, config)
            stats["pages"] = len(pages)
            
            scrape_pages = await self._create_test_scrape_pages(db, config.num_scrape_pages, config)
            stats["scrape_pages"] = len(scrape_pages)
            
            # Create project-page associations
            project_pages = await self._create_project_page_associations(db, projects, pages, config)
            stats["project_pages"] = len(project_pages)
            
            await db.commit()
        
        logger.info(f"Test data population completed: {stats}")
        return stats
    
    @asynccontextmanager
    async def _get_db_session(self):
        """Get database session for test database"""
        from sqlmodel import Session
        with Session(self.db_manager.engine) as session:
            yield session
    
    async def _create_test_users(self, db, count: int) -> List[User]:
        """Create test users"""
        users = []
        for i in range(count):
            user = User(
                email=f"test_user_{i}@example.com",
                full_name=f"Test User {i}",
                hashed_password="fake_hash",
                is_verified=True,
                is_active=True,
                approval_status="approved"
            )
            db.add(user)
            users.append(user)
        
        await db.flush()  # Get IDs
        return users
    
    async def _create_test_projects(self, db, users: List[User], count: int) -> List[Project]:
        """Create test projects"""
        projects = []
        for i in range(count):
            project = Project(
                name=f"Test Project {i}",
                description=f"Test project description {i}",
                owner_id=random.choice(users).id,
                is_public=random.choice([True, False])
            )
            db.add(project)
            projects.append(project)
        
        await db.flush()
        return projects
    
    async def _create_test_pages(self, db, count: int, config: TestDataConfig) -> List[PageV2]:
        """Create test pages with realistic content"""
        urls = self.data_generator.generate_realistic_urls(count)
        pages = []
        
        for i, url in enumerate(urls):
            title, content = self.data_generator.generate_realistic_content(url)
            
            page = PageV2(
                url=url,
                title=title,
                content=content if config.include_content else None,
                content_length=len(content) if content else 0,
                scraped_at=datetime.utcnow() - timedelta(
                    days=random.randint(0, config.date_range_days)
                ),
                # Add entities if requested
                entities=self.data_generator.generate_entities(content) if config.include_entities else None,
                # Add metadata if requested
                metadata={
                    "language": "en",
                    "content_type": "text/html",
                    "word_count": len(content.split()) if content else 0,
                    "source": "test_data_generator"
                } if config.include_metadata else None
            )
            db.add(page)
            pages.append(page)
            
            # Batch commit every 1000 records for performance
            if (i + 1) % 1000 == 0:
                await db.flush()
                logger.info(f"Created {i + 1}/{count} pages")
        
        await db.flush()
        return pages
    
    async def _create_test_scrape_pages(self, db, count: int, config: TestDataConfig) -> List[ScrapePage]:
        """Create test scrape pages"""
        urls = self.data_generator.generate_realistic_urls(count)
        scrape_pages = []
        
        for i, url in enumerate(urls):
            scrape_page = ScrapePage(
                url=url,
                domain="example.com",
                status=random.choice(["completed", "failed", "pending"]),
                scraped_at=datetime.utcnow() - timedelta(
                    days=random.randint(0, config.date_range_days)
                ),
                content_length=random.randint(1000, 50000),
                processing_time_ms=random.randint(100, 5000)
            )
            db.add(scrape_page)
            scrape_pages.append(scrape_page)
            
            if (i + 1) % 1000 == 0:
                await db.flush()
                logger.info(f"Created {i + 1}/{count} scrape pages")
        
        await db.flush()
        return scrape_pages
    
    async def _create_project_page_associations(
        self, db, projects: List[Project], pages: List[PageV2], config: TestDataConfig
    ) -> List[ProjectPage]:
        """Create project-page associations"""
        associations = []
        
        # Each page associated with 1-3 random projects
        for page in pages:
            num_projects = random.randint(1, min(3, len(projects)))
            selected_projects = random.sample(projects, num_projects)
            
            for project in selected_projects:
                association = ProjectPage(
                    project_id=project.id,
                    page_id=page.id,
                    tags=random.choice([
                        ["test", "sample"],
                        ["research", "data"],
                        ["analysis", "report"],
                        []
                    ]),
                    review_status=random.choice(["pending", "approved", "rejected"]),
                    notes=f"Test association for project {project.name}"
                )
                db.add(association)
                associations.append(association)
        
        await db.flush()
        return associations


class TestResourceMonitor:
    """Monitors test execution resource usage"""
    
    def __init__(self):
        self.monitoring_active = False
        self.metrics_history: List[EnvironmentMetrics] = []
        self.monitor_task: Optional[asyncio.Task] = None
    
    async def start_monitoring(self, interval_seconds: int = 1):
        """Start continuous resource monitoring"""
        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(self._monitor_loop(interval_seconds))
    
    async def stop_monitoring(self) -> List[EnvironmentMetrics]:
        """Stop monitoring and return collected metrics"""
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        return self.metrics_history
    
    async def _monitor_loop(self, interval: int):
        """Resource monitoring loop"""
        env_manager = TestEnvironmentManager(TestEnvironment.PERFORMANCE)
        
        while self.monitoring_active:
            try:
                metrics = await env_manager.get_environment_metrics()
                self.metrics_history.append(metrics)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(interval)


class TestConfigurationValidator:
    """Validates test environment configuration and readiness"""
    
    @staticmethod
    async def validate_test_environment() -> Dict[str, bool]:
        """Validate that test environment is properly configured"""
        checks = {
            "database_connection": False,
            "redis_connection": False,
            "meilisearch_connection": False,
            "disk_space": False,
            "memory_available": False,
            "required_services": False
        }
        
        try:
            # Database check
            async for db in get_db():
                await db.execute(text("SELECT 1"))
                checks["database_connection"] = True
                break
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
        
        # Resource checks
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        checks["memory_available"] = memory.available > 1024**3  # 1GB available
        checks["disk_space"] = disk.free > 5 * 1024**3  # 5GB free
        
        # TODO: Add Redis, Meilisearch, and service checks
        
        return checks
    
    @staticmethod
    async def get_test_recommendations(data_scale: DataScale) -> Dict[str, Any]:
        """Get recommendations for test configuration based on scale"""
        recommendations = {
            DataScale.SMALL: {
                "min_memory_gb": 2,
                "min_disk_gb": 1,
                "recommended_workers": 2,
                "timeout_multiplier": 1.0
            },
            DataScale.MEDIUM: {
                "min_memory_gb": 4,
                "min_disk_gb": 5,
                "recommended_workers": 4,
                "timeout_multiplier": 2.0
            },
            DataScale.LARGE: {
                "min_memory_gb": 8,
                "min_disk_gb": 20,
                "recommended_workers": 8,
                "timeout_multiplier": 5.0
            },
            DataScale.XLARGE: {
                "min_memory_gb": 16,
                "min_disk_gb": 50,
                "recommended_workers": 16,
                "timeout_multiplier": 10.0
            }
        }
        
        return recommendations[data_scale]


# Utility functions for test data persistence and reuse

async def save_test_session_metadata(session: TestSession, filepath: Path):
    """Save test session metadata to file"""
    async with aiofiles.open(filepath, 'w') as f:
        await f.write(json.dumps({
            "session_id": session.session_id,
            "environment": session.environment.value,
            "data_config": {
                "scale": session.data_config.scale.value,
                "num_users": session.data_config.num_users,
                "num_projects": session.data_config.num_projects,
                "num_pages": session.data_config.num_pages
            },
            "start_time": session.start_time.isoformat(),
            "end_time": session.end_time.isoformat() if session.end_time else None,
            "resources_used": session.resources_used,
            "metadata": {
                k: v for k, v in session.metadata.items() 
                if k not in ["start_metrics", "end_metrics"]  # Skip complex objects
            }
        }, indent=2))


async def load_test_session_metadata(filepath: Path) -> Optional[Dict[str, Any]]:
    """Load test session metadata from file"""
    try:
        async with aiofiles.open(filepath, 'r') as f:
            return json.loads(await f.read())
    except Exception as e:
        logger.error(f"Failed to load test session metadata: {e}")
        return None


# Context managers for common test scenarios

@asynccontextmanager
async def performance_test_environment(data_scale: DataScale = DataScale.MEDIUM) -> AsyncGenerator[Tuple[TestSession, TestDataPopulator], None]:
    """Context manager for performance testing environment"""
    env_manager = TestEnvironmentManager(TestEnvironment.PERFORMANCE)
    data_config = TestDataConfig.for_scale(data_scale)
    
    async with env_manager.managed_environment(data_config) as session:
        populator = TestDataPopulator(env_manager.db_manager)
        await populator.populate_test_data(data_config)
        yield session, populator


@asynccontextmanager 
async def load_test_environment(data_scale: DataScale = DataScale.LARGE) -> AsyncGenerator[Tuple[TestSession, TestDataPopulator], None]:
    """Context manager for load testing environment"""
    env_manager = TestEnvironmentManager(TestEnvironment.LOAD)
    data_config = TestDataConfig.for_scale(data_scale)
    
    async with env_manager.managed_environment(data_config) as session:
        populator = TestDataPopulator(env_manager.db_manager)
        await populator.populate_test_data(data_config)
        yield session, populator


if __name__ == "__main__":
    # Example usage and validation
    async def test_infrastructure():
        """Test the infrastructure utilities"""
        logger.info("Testing infrastructure utilities...")
        
        # Validate environment
        validation_results = await TestConfigurationValidator.validate_test_environment()
        logger.info(f"Environment validation: {validation_results}")
        
        # Test small-scale environment
        async with performance_test_environment(DataScale.SMALL) as (session, populator):
            logger.info(f"Test session: {session.session_id}")
            logger.info(f"Environment metrics: {session.metadata.get('start_metrics')}")
        
        logger.info("Infrastructure test completed successfully")
    
    # Run test if executed directly
    asyncio.run(test_infrastructure())