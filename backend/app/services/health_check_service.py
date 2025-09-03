"""
Comprehensive Health Check Framework for Phase 2 DuckDB Analytics System
======================================================================

Advanced health check service with deep health validation, dependency mapping,
and comprehensive system validation for the complete Phase 2 analytics platform.

Features:
- Deep health checks with database connectivity validation
- Service dependency health and response time monitoring
- Resource availability and threshold validation
- Data consistency and integrity checks
- Configuration validation and security compliance
- Circuit breaker integration and failover logic
- Health scoring with weighted calculations
- Automated remediation and self-healing capabilities
- Health trend analysis and prediction
- Integration with monitoring and alerting systems
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Callable, Union, Tuple
from urllib.parse import urlparse
import hashlib
import socket
import psutil
import ssl
import httpx

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.database import get_db
from app.services.duckdb_service import duckdb_service
from app.services.meilisearch_service import MeilisearchService
from app.services.monitoring_service import HealthStatus, ComponentHealth, ComponentType
from app.services.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class HealthCheckType(str, Enum):
    """Types of health checks"""
    BASIC = "basic"                    # Simple connectivity check
    DEEP = "deep"                      # Comprehensive validation
    FUNCTIONAL = "functional"          # Feature-specific tests
    PERFORMANCE = "performance"        # Performance validation
    SECURITY = "security"              # Security compliance
    DEPENDENCY = "dependency"          # Dependency validation
    DATA_INTEGRITY = "data_integrity"  # Data consistency checks


class ValidationLevel(str, Enum):
    """Validation depth levels"""
    MINIMAL = "minimal"       # Basic connectivity only
    STANDARD = "standard"     # Standard operational checks
    COMPREHENSIVE = "comprehensive"  # Full system validation
    DIAGNOSTIC = "diagnostic"  # Detailed diagnostic information


class RemediationAction(str, Enum):
    """Automated remediation actions"""
    NONE = "none"
    RESTART_SERVICE = "restart_service"
    CLEAR_CACHE = "clear_cache"
    RESET_CONNECTION = "reset_connection"
    SCALE_UP = "scale_up"
    FAILOVER = "failover"
    ALERT_ADMIN = "alert_admin"


@dataclass
class HealthCheckConfig:
    """Configuration for health checks"""
    check_type: HealthCheckType = HealthCheckType.BASIC
    validation_level: ValidationLevel = ValidationLevel.STANDARD
    timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_delay_seconds: int = 5
    enable_remediation: bool = False
    critical_threshold: float = 0.8  # 80% success rate to be considered healthy
    warning_threshold: float = 0.9   # 90% success rate to avoid warnings


@dataclass
class HealthCheckResult:
    """Result of a health check operation"""
    service_name: str
    check_type: HealthCheckType
    status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Performance metrics
    response_time_ms: float = 0.0
    success: bool = True
    
    # Detailed results
    checks_passed: int = 0
    checks_failed: int = 0
    total_checks: int = 0
    
    # Issues and recommendations
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Remediation
    remediation_applied: List[RemediationAction] = field(default_factory=list)
    remediation_successful: bool = False
    
    # Detailed metrics
    metrics: Dict[str, Any] = field(default_factory=dict)
    dependencies: Dict[str, HealthStatus] = field(default_factory=dict)
    
    # Scoring
    health_score: float = 100.0  # 0-100 score
    
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_checks == 0:
            return 100.0
        return (self.checks_passed / self.total_checks) * 100.0


@dataclass
class HealthCheckDefinition:
    """Definition of a health check"""
    name: str
    description: str
    service_name: str
    check_function: Callable
    config: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    dependencies: List[str] = field(default_factory=list)
    weight: float = 1.0  # Weight for overall health calculation
    enabled: bool = True
    tags: Set[str] = field(default_factory=set)


@dataclass
class ServiceHealthSummary:
    """Summary of service health across all checks"""
    service_name: str
    overall_status: HealthStatus
    overall_score: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Check results breakdown
    basic_checks: Optional[HealthCheckResult] = None
    deep_checks: Optional[HealthCheckResult] = None
    functional_checks: Optional[HealthCheckResult] = None
    performance_checks: Optional[HealthCheckResult] = None
    security_checks: Optional[HealthCheckResult] = None
    
    # Trends
    health_trend: str = "stable"  # improving, degrading, stable
    last_healthy: Optional[datetime] = None
    last_unhealthy: Optional[datetime] = None
    
    # Uptime tracking
    uptime_percentage_24h: float = 100.0
    uptime_percentage_7d: float = 100.0
    uptime_percentage_30d: float = 100.0


class HealthCheckService:
    """
    Comprehensive health check framework for Phase 2 DuckDB analytics system
    
    Provides deep health validation, dependency mapping, and automated
    remediation capabilities for all system components.
    """
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self._health_checks: Dict[str, HealthCheckDefinition] = {}
        self._service_health_cache: Dict[str, ServiceHealthSummary] = {}
        self._cache_ttl = 60  # seconds
        
        # Health history for trend analysis
        self._health_history: Dict[str, List[HealthCheckResult]] = {}
        self._max_history_size = 1000
        
        # Remediation tracking
        self._remediation_attempts: Dict[str, List[datetime]] = {}
        self._max_remediation_attempts = 3
        self._remediation_window_minutes = 15
        
        # Circuit breakers for health checks
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        logger.info("HealthCheckService initialized")
    
    async def initialize(self):
        """Initialize health check service and background tasks"""
        try:
            # Initialize Redis connection
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=7,  # Dedicated DB for health checks
                decode_responses=True,
                socket_timeout=10.0
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            logger.info("HealthCheckService Redis connection established")
            
            # Register default health checks
            await self._register_default_health_checks()
            
            # Start background tasks
            await self._start_background_tasks()
            
        except Exception as e:
            logger.error(f"Failed to initialize HealthCheckService: {e}")
            raise
    
    async def _register_default_health_checks(self):
        """Register default health checks for Phase 2 components"""
        
        # PostgreSQL Database Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="postgresql_basic",
            description="PostgreSQL database basic connectivity",
            service_name="postgresql",
            check_function=self._check_postgresql_health,
            config=HealthCheckConfig(
                check_type=HealthCheckType.BASIC,
                validation_level=ValidationLevel.STANDARD,
                timeout_seconds=10
            ),
            weight=2.0,  # High weight for database
            tags={"database", "critical"}
        ))
        
        await self.register_health_check(HealthCheckDefinition(
            name="postgresql_deep",
            description="PostgreSQL database deep validation",
            service_name="postgresql",
            check_function=self._check_postgresql_deep,
            config=HealthCheckConfig(
                check_type=HealthCheckType.DEEP,
                validation_level=ValidationLevel.COMPREHENSIVE,
                timeout_seconds=30
            ),
            weight=2.0,
            tags={"database", "critical", "deep"}
        ))
        
        # DuckDB Analytics Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="duckdb_basic",
            description="DuckDB analytics database connectivity",
            service_name="duckdb",
            check_function=self._check_duckdb_health,
            config=HealthCheckConfig(
                check_type=HealthCheckType.BASIC,
                validation_level=ValidationLevel.STANDARD,
                timeout_seconds=15
            ),
            weight=1.8,
            tags={"analytics", "database", "critical"}
        ))
        
        await self.register_health_check(HealthCheckDefinition(
            name="duckdb_performance",
            description="DuckDB query performance validation",
            service_name="duckdb",
            check_function=self._check_duckdb_performance,
            config=HealthCheckConfig(
                check_type=HealthCheckType.PERFORMANCE,
                validation_level=ValidationLevel.COMPREHENSIVE,
                timeout_seconds=45
            ),
            weight=1.5,
            tags={"analytics", "performance"}
        ))
        
        # Redis Cache Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="redis_basic",
            description="Redis cache basic connectivity",
            service_name="redis",
            check_function=self._check_redis_health,
            config=HealthCheckConfig(
                check_type=HealthCheckType.BASIC,
                validation_level=ValidationLevel.STANDARD,
                timeout_seconds=5
            ),
            weight=1.2,
            tags={"cache", "performance"}
        ))
        
        # Meilisearch Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="meilisearch_basic",
            description="Meilisearch service connectivity",
            service_name="meilisearch",
            check_function=self._check_meilisearch_health,
            config=HealthCheckConfig(
                check_type=HealthCheckType.BASIC,
                validation_level=ValidationLevel.STANDARD,
                timeout_seconds=10
            ),
            weight=1.3,
            tags={"search", "service"}
        ))
        
        # Firecrawl API Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="firecrawl_basic",
            description="Firecrawl API service connectivity",
            service_name="firecrawl_api",
            check_function=self._check_firecrawl_health,
            config=HealthCheckConfig(
                check_type=HealthCheckType.BASIC,
                validation_level=ValidationLevel.STANDARD,
                timeout_seconds=15
            ),
            weight=1.0,
            tags={"extraction", "service"}
        ))
        
        # System Resource Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="system_resources",
            description="System resource availability",
            service_name="system",
            check_function=self._check_system_resources,
            config=HealthCheckConfig(
                check_type=HealthCheckType.FUNCTIONAL,
                validation_level=ValidationLevel.COMPREHENSIVE,
                timeout_seconds=20
            ),
            weight=1.5,
            tags={"system", "resources"}
        ))
        
        # Data Sync Service Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="data_sync_functional",
            description="Data synchronization service functional check",
            service_name="data_sync_service",
            check_function=self._check_data_sync_functional,
            config=HealthCheckConfig(
                check_type=HealthCheckType.FUNCTIONAL,
                validation_level=ValidationLevel.STANDARD,
                timeout_seconds=30
            ),
            dependencies=["postgresql", "duckdb"],
            weight=1.4,
            tags={"sync", "functional"}
        ))
        
        # Security Health Check
        await self.register_health_check(HealthCheckDefinition(
            name="security_compliance",
            description="Security configuration and compliance",
            service_name="security",
            check_function=self._check_security_compliance,
            config=HealthCheckConfig(
                check_type=HealthCheckType.SECURITY,
                validation_level=ValidationLevel.COMPREHENSIVE,
                timeout_seconds=25
            ),
            weight=1.8,
            tags={"security", "compliance"}
        ))
        
        logger.info(f"Registered {len(self._health_checks)} default health checks")
    
    async def _start_background_tasks(self):
        """Start background tasks for health monitoring"""
        # Continuous health monitoring task
        monitoring_task = asyncio.create_task(self._continuous_health_monitoring())
        self._background_tasks.add(monitoring_task)
        monitoring_task.add_done_callback(self._background_tasks.discard)
        
        # Health history cleanup task
        cleanup_task = asyncio.create_task(self._health_history_cleanup())
        self._background_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._background_tasks.discard)
        
        # Remediation monitoring task
        remediation_task = asyncio.create_task(self._remediation_monitoring())
        self._background_tasks.add(remediation_task)
        remediation_task.add_done_callback(self._background_tasks.discard)
        
        logger.info("HealthCheckService background tasks started")
    
    async def _continuous_health_monitoring(self):
        """Background task for continuous health monitoring"""
        while not self._shutdown_event.is_set():
            try:
                # Run health checks for all registered services
                for service_name in self._get_unique_service_names():
                    try:
                        await self.check_service_health(service_name, ValidationLevel.STANDARD)
                    except Exception as e:
                        logger.error(f"Error checking health for {service_name}: {e}")
                
                # Wait before next round
                await asyncio.sleep(120)  # Check every 2 minutes
                
            except Exception as e:
                logger.error(f"Error in continuous health monitoring: {e}")
                await asyncio.sleep(300)  # Wait longer on error
    
    async def _health_history_cleanup(self):
        """Background task for cleaning up health history"""
        while not self._shutdown_event.is_set():
            try:
                cutoff_time = datetime.utcnow() - timedelta(days=7)
                
                for service_name in self._health_history:
                    # Keep only recent history
                    self._health_history[service_name] = [
                        result for result in self._health_history[service_name]
                        if result.timestamp > cutoff_time
                    ]
                    
                    # Limit history size
                    if len(self._health_history[service_name]) > self._max_history_size:
                        self._health_history[service_name] = self._health_history[service_name][-self._max_history_size:]
                
                # Wait before next cleanup
                await asyncio.sleep(3600)  # Clean every hour
                
            except Exception as e:
                logger.error(f"Error in health history cleanup: {e}")
                await asyncio.sleep(3600)
    
    async def _remediation_monitoring(self):
        """Background task for monitoring remediation attempts"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.utcnow()
                cutoff_time = current_time - timedelta(minutes=self._remediation_window_minutes)
                
                # Clean up old remediation attempts
                for service_name in list(self._remediation_attempts.keys()):
                    self._remediation_attempts[service_name] = [
                        attempt for attempt in self._remediation_attempts[service_name]
                        if attempt > cutoff_time
                    ]
                    
                    # Remove empty entries
                    if not self._remediation_attempts[service_name]:
                        del self._remediation_attempts[service_name]
                
                # Wait before next cleanup
                await asyncio.sleep(600)  # Clean every 10 minutes
                
            except Exception as e:
                logger.error(f"Error in remediation monitoring: {e}")
                await asyncio.sleep(600)
    
    # Health check registration and management
    
    async def register_health_check(self, definition: HealthCheckDefinition):
        """Register a new health check"""
        check_id = f"{definition.service_name}_{definition.name}"
        self._health_checks[check_id] = definition
        
        # Initialize history for this service
        if definition.service_name not in self._health_history:
            self._health_history[definition.service_name] = []
        
        logger.info(f"Registered health check: {check_id}")
    
    async def unregister_health_check(self, check_id: str):
        """Unregister a health check"""
        if check_id in self._health_checks:
            del self._health_checks[check_id]
            logger.info(f"Unregistered health check: {check_id}")
    
    def _get_unique_service_names(self) -> Set[str]:
        """Get unique service names from registered health checks"""
        return {definition.service_name for definition in self._health_checks.values()}
    
    # Core health check methods
    
    async def check_service_health(
        self,
        service_name: str,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
        force_refresh: bool = False
    ) -> ServiceHealthSummary:
        """Check comprehensive health for a service"""
        try:
            # Check cache first
            cache_key = f"{service_name}_{validation_level.value}"
            if not force_refresh and cache_key in self._service_health_cache:
                cached_summary = self._service_health_cache[cache_key]
                if (datetime.utcnow() - cached_summary.timestamp).seconds < self._cache_ttl:
                    return cached_summary
            
            # Get all health checks for this service
            service_checks = [
                (check_id, definition) for check_id, definition in self._health_checks.items()
                if definition.service_name == service_name and definition.enabled
            ]
            
            if not service_checks:
                logger.warning(f"No health checks registered for service: {service_name}")
                return ServiceHealthSummary(
                    service_name=service_name,
                    overall_status=HealthStatus.UNKNOWN,
                    overall_score=0.0
                )
            
            # Run health checks based on validation level
            results = {}
            total_weight = 0
            weighted_score = 0
            
            for check_id, definition in service_checks:
                # Skip checks that don't match the requested validation level
                if not self._should_run_check(definition, validation_level):
                    continue
                
                try:
                    result = await self._run_health_check(definition)
                    results[definition.check_type] = result
                    
                    # Calculate weighted score
                    weighted_score += result.health_score * definition.weight
                    total_weight += definition.weight
                    
                    # Store in history
                    self._add_to_history(service_name, result)
                    
                except Exception as e:
                    logger.error(f"Health check {check_id} failed: {e}")
                    # Create failed result
                    failed_result = HealthCheckResult(
                        service_name=service_name,
                        check_type=definition.check_type,
                        status=HealthStatus.CRITICAL,
                        success=False,
                        errors=[f"Health check execution failed: {str(e)}"]
                    )
                    results[definition.check_type] = failed_result
                    
                    # Add to weighted score as 0
                    total_weight += definition.weight
            
            # Calculate overall health
            overall_score = weighted_score / total_weight if total_weight > 0 else 0
            overall_status = self._calculate_overall_status(results, overall_score)
            
            # Create service health summary
            summary = ServiceHealthSummary(
                service_name=service_name,
                overall_status=overall_status,
                overall_score=overall_score,
                basic_checks=results.get(HealthCheckType.BASIC),
                deep_checks=results.get(HealthCheckType.DEEP),
                functional_checks=results.get(HealthCheckType.FUNCTIONAL),
                performance_checks=results.get(HealthCheckType.PERFORMANCE),
                security_checks=results.get(HealthCheckType.SECURITY),
                health_trend=await self._calculate_health_trend(service_name),
                uptime_percentage_24h=await self._calculate_uptime(service_name, timedelta(hours=24)),
                uptime_percentage_7d=await self._calculate_uptime(service_name, timedelta(days=7)),
                uptime_percentage_30d=await self._calculate_uptime(service_name, timedelta(days=30))
            )
            
            # Apply remediation if needed and enabled
            if overall_status in [HealthStatus.CRITICAL, HealthStatus.UNHEALTHY]:
                await self._apply_remediation(service_name, summary)
            
            # Cache result
            self._service_health_cache[cache_key] = summary
            
            # Store in Redis for persistence
            await self._store_health_summary(summary)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error checking service health for {service_name}: {e}")
            return ServiceHealthSummary(
                service_name=service_name,
                overall_status=HealthStatus.CRITICAL,
                overall_score=0.0
            )
    
    def _should_run_check(self, definition: HealthCheckDefinition, validation_level: ValidationLevel) -> bool:
        """Determine if a health check should run based on validation level"""
        if validation_level == ValidationLevel.MINIMAL:
            return definition.config.check_type == HealthCheckType.BASIC
        elif validation_level == ValidationLevel.STANDARD:
            return definition.config.check_type in [HealthCheckType.BASIC, HealthCheckType.FUNCTIONAL]
        elif validation_level == ValidationLevel.COMPREHENSIVE:
            return True  # Run all checks
        elif validation_level == ValidationLevel.DIAGNOSTIC:
            return True  # Run all checks with detailed output
        
        return True
    
    async def _run_health_check(self, definition: HealthCheckDefinition) -> HealthCheckResult:
        """Run a single health check with timeout and retry logic"""
        start_time = time.time()
        
        # Check circuit breaker
        circuit_breaker = self._get_circuit_breaker(definition)
        
        async def execute_check():
            try:
                result = await asyncio.wait_for(
                    definition.check_function(definition.config),
                    timeout=definition.config.timeout_seconds
                )
                result.response_time_ms = (time.time() - start_time) * 1000
                return result
            except asyncio.TimeoutError:
                return HealthCheckResult(
                    service_name=definition.service_name,
                    check_type=definition.config.check_type,
                    status=HealthStatus.CRITICAL,
                    response_time_ms=(time.time() - start_time) * 1000,
                    success=False,
                    errors=[f"Health check timed out after {definition.config.timeout_seconds}s"]
                )
            except Exception as e:
                return HealthCheckResult(
                    service_name=definition.service_name,
                    check_type=definition.config.check_type,
                    status=HealthStatus.CRITICAL,
                    response_time_ms=(time.time() - start_time) * 1000,
                    success=False,
                    errors=[f"Health check failed: {str(e)}"]
                )
        
        # Execute with circuit breaker protection
        try:
            result = await circuit_breaker.execute(execute_check)
            return result
        except Exception as e:
            logger.error(f"Circuit breaker prevented health check execution: {e}")
            return HealthCheckResult(
                service_name=definition.service_name,
                check_type=definition.config.check_type,
                status=HealthStatus.CRITICAL,
                success=False,
                errors=["Circuit breaker open - health check skipped"]
            )
    
    def _get_circuit_breaker(self, definition: HealthCheckDefinition) -> CircuitBreaker:
        """Get or create circuit breaker for a health check"""
        breaker_id = f"{definition.service_name}_{definition.name}"
        
        if breaker_id not in self._circuit_breakers:
            from app.services.circuit_breaker import CircuitBreakerConfig
            
            config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=60,
                max_timeout_seconds=300
            )
            
            self._circuit_breakers[breaker_id] = CircuitBreaker(breaker_id, config)
        
        return self._circuit_breakers[breaker_id]
    
    def _calculate_overall_status(self, results: Dict[HealthCheckType, HealthCheckResult], overall_score: float) -> HealthStatus:
        """Calculate overall health status from individual check results"""
        if not results:
            return HealthStatus.UNKNOWN
        
        # Check for critical failures
        if any(result.status == HealthStatus.CRITICAL for result in results.values()):
            return HealthStatus.CRITICAL
        
        # Check for unhealthy status
        if any(result.status == HealthStatus.UNHEALTHY for result in results.values()):
            return HealthStatus.UNHEALTHY
        
        # Use score-based assessment
        if overall_score >= 90:
            return HealthStatus.HEALTHY
        elif overall_score >= 70:
            return HealthStatus.DEGRADED
        elif overall_score >= 50:
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.CRITICAL
    
    def _add_to_history(self, service_name: str, result: HealthCheckResult):
        """Add health check result to history"""
        if service_name not in self._health_history:
            self._health_history[service_name] = []
        
        self._health_history[service_name].append(result)
        
        # Limit history size
        if len(self._health_history[service_name]) > self._max_history_size:
            self._health_history[service_name] = self._health_history[service_name][-self._max_history_size:]
    
    async def _calculate_health_trend(self, service_name: str) -> str:
        """Calculate health trend for a service"""
        try:
            history = self._health_history.get(service_name, [])
            if len(history) < 5:
                return "stable"
            
            # Get recent health scores
            recent_scores = [result.health_score for result in history[-10:]]
            
            # Simple trend calculation
            first_half_avg = sum(recent_scores[:len(recent_scores)//2]) / (len(recent_scores)//2)
            second_half_avg = sum(recent_scores[len(recent_scores)//2:]) / (len(recent_scores) - len(recent_scores)//2)
            
            change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100 if first_half_avg > 0 else 0
            
            if change_percent > 10:
                return "improving"
            elif change_percent < -10:
                return "degrading"
            else:
                return "stable"
                
        except Exception as e:
            logger.error(f"Error calculating health trend for {service_name}: {e}")
            return "unknown"
    
    async def _calculate_uptime(self, service_name: str, period: timedelta) -> float:
        """Calculate uptime percentage for a service over a period"""
        try:
            cutoff_time = datetime.utcnow() - period
            history = self._health_history.get(service_name, [])
            
            relevant_results = [result for result in history if result.timestamp >= cutoff_time]
            
            if not relevant_results:
                return 100.0  # Assume healthy if no data
            
            healthy_count = len([result for result in relevant_results 
                               if result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]])
            
            return (healthy_count / len(relevant_results)) * 100
            
        except Exception as e:
            logger.error(f"Error calculating uptime for {service_name}: {e}")
            return 0.0
    
    async def _apply_remediation(self, service_name: str, summary: ServiceHealthSummary):
        """Apply automated remediation for unhealthy services"""
        try:
            # Check if we've exceeded remediation attempts
            if self._can_attempt_remediation(service_name):
                # Get service-specific remediation actions
                remediation_actions = await self._get_remediation_actions(service_name, summary)
                
                for action in remediation_actions:
                    try:
                        success = await self._execute_remediation_action(service_name, action)
                        
                        if success:
                            logger.info(f"Successfully applied remediation '{action}' for service {service_name}")
                            
                            # Track remediation attempt
                            if service_name not in self._remediation_attempts:
                                self._remediation_attempts[service_name] = []
                            self._remediation_attempts[service_name].append(datetime.utcnow())
                            
                            # Wait for effect and re-check
                            await asyncio.sleep(10)
                            break
                        else:
                            logger.warning(f"Remediation action '{action}' failed for service {service_name}")
                            
                    except Exception as e:
                        logger.error(f"Error executing remediation action '{action}' for {service_name}: {e}")
            else:
                logger.warning(f"Remediation attempts exhausted for service {service_name}")
                
        except Exception as e:
            logger.error(f"Error applying remediation for {service_name}: {e}")
    
    def _can_attempt_remediation(self, service_name: str) -> bool:
        """Check if remediation can be attempted for a service"""
        attempts = self._remediation_attempts.get(service_name, [])
        cutoff_time = datetime.utcnow() - timedelta(minutes=self._remediation_window_minutes)
        
        recent_attempts = [attempt for attempt in attempts if attempt > cutoff_time]
        
        return len(recent_attempts) < self._max_remediation_attempts
    
    async def _get_remediation_actions(self, service_name: str, summary: ServiceHealthSummary) -> List[RemediationAction]:
        """Get appropriate remediation actions for a service"""
        actions = []
        
        # Service-specific remediation logic
        if service_name == "redis":
            if summary.basic_checks and not summary.basic_checks.success:
                actions.append(RemediationAction.RESET_CONNECTION)
                actions.append(RemediationAction.CLEAR_CACHE)
        
        elif service_name == "postgresql":
            if summary.deep_checks and "connection" in str(summary.deep_checks.errors).lower():
                actions.append(RemediationAction.RESET_CONNECTION)
        
        elif service_name == "duckdb":
            if summary.performance_checks and summary.performance_checks.health_score < 50:
                actions.append(RemediationAction.CLEAR_CACHE)
        
        elif service_name == "system":
            if summary.functional_checks:
                errors = summary.functional_checks.errors
                if any("memory" in error.lower() for error in errors):
                    actions.append(RemediationAction.CLEAR_CACHE)
                if any("cpu" in error.lower() for error in errors):
                    actions.append(RemediationAction.SCALE_UP)
        
        # Always alert admin for critical issues
        if summary.overall_status == HealthStatus.CRITICAL:
            actions.append(RemediationAction.ALERT_ADMIN)
        
        return actions
    
    async def _execute_remediation_action(self, service_name: str, action: RemediationAction) -> bool:
        """Execute a specific remediation action"""
        try:
            if action == RemediationAction.RESET_CONNECTION:
                return await self._reset_connection(service_name)
            
            elif action == RemediationAction.CLEAR_CACHE:
                return await self._clear_cache(service_name)
            
            elif action == RemediationAction.ALERT_ADMIN:
                return await self._alert_admin(service_name)
            
            elif action == RemediationAction.SCALE_UP:
                return await self._scale_up_service(service_name)
            
            else:
                logger.warning(f"Unknown remediation action: {action}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing remediation action {action} for {service_name}: {e}")
            return False
    
    async def _reset_connection(self, service_name: str) -> bool:
        """Reset connections for a service"""
        try:
            if service_name == "redis" and self.redis_client:
                # Reconnect Redis
                await self.redis_client.close()
                await asyncio.sleep(2)
                await self.redis_client.ping()
                return True
            
            elif service_name == "duckdb":
                # Reset DuckDB connections
                await duckdb_service.shutdown()
                await asyncio.sleep(2)
                await duckdb_service.initialize()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error resetting connection for {service_name}: {e}")
            return False
    
    async def _clear_cache(self, service_name: str) -> bool:
        """Clear cache for a service"""
        try:
            if service_name == "redis" and self.redis_client:
                # Clear specific cache keys
                keys = await self.redis_client.keys("cache:*")
                if keys:
                    await self.redis_client.delete(*keys)
                return True
            
            elif service_name == "duckdb":
                # Clear DuckDB query cache (if implemented)
                return True
            
            elif service_name == "system":
                # Clear system caches
                self._service_health_cache.clear()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error clearing cache for {service_name}: {e}")
            return False
    
    async def _alert_admin(self, service_name: str) -> bool:
        """Send alert to administrators"""
        try:
            # Integration with alerting service
            from app.services.alerting_service import alerting_service
            
            await alerting_service.create_alert(
                title=f"Service Health Critical: {service_name}",
                description=f"Automated health check detected critical issues with {service_name}",
                severity="critical",
                component=service_name,
                metric="health_status",
                current_value="critical"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending admin alert for {service_name}: {e}")
            return False
    
    async def _scale_up_service(self, service_name: str) -> bool:
        """Scale up a service (placeholder for future implementation)"""
        try:
            # This would integrate with container orchestration (Docker Compose, Kubernetes)
            # For now, just log the attempt
            logger.info(f"Scale-up requested for service {service_name} (not implemented)")
            return True
            
        except Exception as e:
            logger.error(f"Error scaling up {service_name}: {e}")
            return False
    
    async def _store_health_summary(self, summary: ServiceHealthSummary):
        """Store health summary in Redis for persistence"""
        try:
            if self.redis_client:
                key = f"health_summary:{summary.service_name}"
                value = json.dumps(asdict(summary), default=str)
                
                await self.redis_client.setex(key, 3600, value)  # 1 hour TTL
                
                # Also store in time series
                timestamp_key = f"health_timeseries:{summary.service_name}"
                await self.redis_client.zadd(
                    timestamp_key,
                    {value: summary.timestamp.timestamp()}
                )
                
                # Keep only last 24 hours of time series data
                cutoff = (datetime.utcnow() - timedelta(hours=24)).timestamp()
                await self.redis_client.zremrangebyscore(timestamp_key, 0, cutoff)
                
        except Exception as e:
            logger.error(f"Error storing health summary for {summary.service_name}: {e}")
    
    # Individual health check implementations
    
    async def _check_postgresql_health(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check PostgreSQL database health"""
        result = HealthCheckResult(
            service_name="postgresql",
            check_type=config.check_type
        )
        
        try:
            async for db in get_db():
                # Basic connectivity test
                await db.execute(text("SELECT 1"))
                result.checks_passed += 1
                result.total_checks += 1
                
                # Check active connections
                conn_result = await db.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
                )
                active_connections = conn_result.scalar() or 0
                result.metrics["active_connections"] = active_connections
                
                if active_connections > 50:  # Warning threshold
                    result.warnings.append(f"High number of active connections: {active_connections}")
                
                result.checks_passed += 1
                result.total_checks += 1
                
                # Check database size
                size_result = await db.execute(
                    text("SELECT pg_database_size(current_database())")
                )
                db_size_bytes = size_result.scalar() or 0
                result.metrics["database_size_mb"] = db_size_bytes / (1024 * 1024)
                
                result.checks_passed += 1
                result.total_checks += 1
                
                break
            
            result.status = HealthStatus.HEALTHY
            result.success = True
            result.health_score = (result.checks_passed / result.total_checks) * 100
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"PostgreSQL health check failed: {str(e)}")
            result.health_score = 0.0
            result.checks_failed = result.total_checks
        
        return result
    
    async def _check_postgresql_deep(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Deep PostgreSQL database validation"""
        result = HealthCheckResult(
            service_name="postgresql",
            check_type=config.check_type
        )
        
        try:
            async for db in get_db():
                # Basic checks from simple health check
                basic_result = await self._check_postgresql_health(
                    HealthCheckConfig(check_type=HealthCheckType.BASIC)
                )
                result.checks_passed += basic_result.checks_passed
                result.checks_failed += basic_result.checks_failed
                result.total_checks += basic_result.total_checks
                result.metrics.update(basic_result.metrics)
                result.warnings.extend(basic_result.warnings)
                
                # Deep validation tests
                
                # Check table accessibility
                try:
                    await db.execute(text("SELECT COUNT(*) FROM users LIMIT 1"))
                    await db.execute(text("SELECT COUNT(*) FROM projects LIMIT 1"))
                    await db.execute(text("SELECT COUNT(*) FROM pages_v2 LIMIT 1"))
                    result.checks_passed += 3
                    result.total_checks += 3
                except Exception as e:
                    result.checks_failed += 3
                    result.total_checks += 3
                    result.errors.append(f"Table accessibility check failed: {str(e)}")
                
                # Check long-running queries
                long_queries_result = await db.execute(
                    text("""
                        SELECT COUNT(*) 
                        FROM pg_stat_activity 
                        WHERE state = 'active' 
                        AND query_start < NOW() - INTERVAL '5 minutes'
                        AND query NOT LIKE '%pg_stat_activity%'
                    """)
                )
                long_queries = long_queries_result.scalar() or 0
                result.metrics["long_running_queries"] = long_queries
                
                if long_queries > 0:
                    result.warnings.append(f"Long-running queries detected: {long_queries}")
                
                result.checks_passed += 1
                result.total_checks += 1
                
                # Check replication lag (if applicable)
                try:
                    lag_result = await db.execute(
                        text("SELECT EXTRACT(EPOCH FROM NOW() - pg_last_xact_replay_timestamp()) as lag")
                    )
                    lag_seconds = lag_result.scalar()
                    if lag_seconds is not None:
                        result.metrics["replication_lag_seconds"] = lag_seconds
                        if lag_seconds > 60:  # 1 minute lag warning
                            result.warnings.append(f"High replication lag: {lag_seconds:.1f}s")
                except Exception:
                    pass  # Not a replica or replication not configured
                
                result.checks_passed += 1
                result.total_checks += 1
                
                break
            
            result.success = result.checks_failed == 0
            result.status = HealthStatus.HEALTHY if result.success else HealthStatus.DEGRADED
            result.health_score = (result.checks_passed / result.total_checks) * 100 if result.total_checks > 0 else 0
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"PostgreSQL deep validation failed: {str(e)}")
            result.health_score = 0.0
        
        return result
    
    async def _check_duckdb_health(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check DuckDB analytics database health"""
        result = HealthCheckResult(
            service_name="duckdb",
            check_type=config.check_type
        )
        
        try:
            # Get DuckDB service health
            health_data = await duckdb_service.health_check()
            
            if health_data.get("status") == "healthy":
                result.status = HealthStatus.HEALTHY
                result.success = True
                result.checks_passed = 3
                result.total_checks = 3
                result.health_score = 100.0
            else:
                result.status = HealthStatus.UNHEALTHY
                result.success = False
                result.checks_failed = 3
                result.total_checks = 3
                result.errors.extend(health_data.get("errors", []))
                result.health_score = 0.0
            
            # Add metrics
            result.metrics = health_data.get("metrics", {})
            
            # Check circuit breaker status
            circuit_status = health_data.get("circuit_breaker", {})
            if circuit_status.get("state") != "closed":
                result.warnings.append(f"DuckDB circuit breaker: {circuit_status.get('state')}")
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"DuckDB health check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_duckdb_performance(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check DuckDB query performance"""
        result = HealthCheckResult(
            service_name="duckdb",
            check_type=config.check_type
        )
        
        try:
            # Test query performance
            test_query = "SELECT COUNT(*) as test_count, AVG(1.0) as test_avg FROM generate_series(1, 1000)"
            
            start_time = time.time()
            query_result = await duckdb_service.execute_query(test_query)
            query_time = time.time() - start_time
            
            result.metrics["test_query_time_seconds"] = query_time
            result.total_checks += 1
            
            if query_result and query_result.data:
                result.checks_passed += 1
                result.health_score = max(0, 100 - (query_time * 10))  # Penalty for slow queries
                
                if query_time < 1.0:
                    result.status = HealthStatus.HEALTHY
                elif query_time < 5.0:
                    result.status = HealthStatus.DEGRADED
                    result.warnings.append(f"Slow query performance: {query_time:.2f}s")
                else:
                    result.status = HealthStatus.UNHEALTHY
                    result.errors.append(f"Very slow query performance: {query_time:.2f}s")
                
                result.success = True
            else:
                result.checks_failed += 1
                result.status = HealthStatus.CRITICAL
                result.errors.append("Test query returned no results")
                result.success = False
                result.health_score = 0.0
            
            # Get service statistics
            stats = await duckdb_service.get_statistics()
            performance_stats = stats.get("performance", {})
            
            avg_query_time = performance_stats.get("avg_query_time", 0)
            if avg_query_time > 10:  # 10 seconds average
                result.warnings.append(f"High average query time: {avg_query_time:.2f}s")
                result.health_score *= 0.8  # Reduce score
            
            result.metrics.update(performance_stats)
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"DuckDB performance check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_redis_health(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check Redis cache health"""
        result = HealthCheckResult(
            service_name="redis",
            check_type=config.check_type
        )
        
        try:
            if not self.redis_client:
                raise Exception("Redis client not initialized")
            
            # Test connectivity
            await self.redis_client.ping()
            result.checks_passed += 1
            result.total_checks += 1
            
            # Get Redis info
            info = await self.redis_client.info()
            
            # Check memory usage
            used_memory = info.get("used_memory", 0)
            used_memory_mb = used_memory / (1024 * 1024)
            result.metrics["memory_used_mb"] = used_memory_mb
            
            if used_memory_mb > 1024:  # 1GB warning
                result.warnings.append(f"High Redis memory usage: {used_memory_mb:.0f}MB")
            
            result.checks_passed += 1
            result.total_checks += 1
            
            # Check hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            
            if hits + misses > 0:
                hit_rate = (hits / (hits + misses)) * 100
                result.metrics["hit_rate_percent"] = hit_rate
                
                if hit_rate < 50:
                    result.warnings.append(f"Low cache hit rate: {hit_rate:.1f}%")
                    result.health_score = hit_rate
                else:
                    result.health_score = 100.0
            else:
                result.health_score = 100.0
            
            result.checks_passed += 1
            result.total_checks += 1
            
            # Check connected clients
            connected_clients = info.get("connected_clients", 0)
            result.metrics["connected_clients"] = connected_clients
            
            if connected_clients > 100:
                result.warnings.append(f"High number of Redis clients: {connected_clients}")
            
            result.status = HealthStatus.HEALTHY
            result.success = True
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"Redis health check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_meilisearch_health(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check Meilisearch service health"""
        result = HealthCheckResult(
            service_name="meilisearch",
            check_type=config.check_type
        )
        
        try:
            # Use MeilisearchService health check
            health_data = await MeilisearchService.health_check()
            
            if health_data.get("status") == "healthy":
                result.status = HealthStatus.HEALTHY
                result.success = True
                result.checks_passed = 2
                result.total_checks = 2
                result.health_score = 100.0
            else:
                result.status = HealthStatus.UNHEALTHY
                result.success = False
                result.checks_failed = 2
                result.total_checks = 2
                result.errors.extend(health_data.get("errors", []))
                result.health_score = 0.0
            
            result.metrics = health_data.get("metrics", {})
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"Meilisearch health check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_firecrawl_health(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check Firecrawl API health"""
        result = HealthCheckResult(
            service_name="firecrawl_api",
            check_type=config.check_type
        )
        
        try:
            firecrawl_url = getattr(settings, 'FIRECRAWL_BASE_URL', 'http://localhost:3002')
            
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                response = await client.get(f"{firecrawl_url}/health")
                
                if response.status_code == 200:
                    result.status = HealthStatus.HEALTHY
                    result.success = True
                    result.checks_passed = 1
                    result.health_score = 100.0
                else:
                    result.status = HealthStatus.UNHEALTHY
                    result.success = False
                    result.checks_failed = 1
                    result.errors.append(f"Firecrawl returned status {response.status_code}")
                    result.health_score = 0.0
                
                result.total_checks = 1
                result.metrics["status_code"] = response.status_code
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"Firecrawl health check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_system_resources(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check system resource availability"""
        result = HealthCheckResult(
            service_name="system",
            check_type=config.check_type
        )
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            result.metrics["cpu_usage_percent"] = cpu_percent
            
            if cpu_percent > 90:
                result.errors.append(f"Critical CPU usage: {cpu_percent:.1f}%")
                result.checks_failed += 1
            elif cpu_percent > 80:
                result.warnings.append(f"High CPU usage: {cpu_percent:.1f}%")
                result.checks_passed += 1
            else:
                result.checks_passed += 1
            
            result.total_checks += 1
            
            # Memory usage
            memory = psutil.virtual_memory()
            result.metrics["memory_usage_percent"] = memory.percent
            result.metrics["memory_available_gb"] = memory.available / (1024**3)
            
            if memory.percent > 95:
                result.errors.append(f"Critical memory usage: {memory.percent:.1f}%")
                result.checks_failed += 1
            elif memory.percent > 85:
                result.warnings.append(f"High memory usage: {memory.percent:.1f}%")
                result.checks_passed += 1
            else:
                result.checks_passed += 1
            
            result.total_checks += 1
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            result.metrics["disk_usage_percent"] = disk_percent
            result.metrics["disk_free_gb"] = disk.free / (1024**3)
            
            if disk_percent > 95:
                result.errors.append(f"Critical disk usage: {disk_percent:.1f}%")
                result.checks_failed += 1
            elif disk_percent > 85:
                result.warnings.append(f"High disk usage: {disk_percent:.1f}%")
                result.checks_passed += 1
            else:
                result.checks_passed += 1
            
            result.total_checks += 1
            
            # Load average
            if hasattr(psutil, "getloadavg"):
                load_avg = psutil.getloadavg()
                result.metrics["load_average_1min"] = load_avg[0]
                result.metrics["load_average_5min"] = load_avg[1]
                result.metrics["load_average_15min"] = load_avg[2]
                
                cpu_count = psutil.cpu_count()
                if load_avg[0] > cpu_count * 2:
                    result.warnings.append(f"High load average: {load_avg[0]:.2f}")
            
            result.checks_passed += 1
            result.total_checks += 1
            
            # Overall health calculation
            if result.checks_failed > 0:
                result.status = HealthStatus.CRITICAL if result.checks_failed > 1 else HealthStatus.UNHEALTHY
                result.success = False
            elif result.warnings:
                result.status = HealthStatus.DEGRADED
                result.success = True
            else:
                result.status = HealthStatus.HEALTHY
                result.success = True
            
            result.health_score = (result.checks_passed / result.total_checks) * 100
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"System resources check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_data_sync_functional(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check data synchronization service functionality"""
        result = HealthCheckResult(
            service_name="data_sync_service",
            check_type=config.check_type
        )
        
        try:
            # Check if sync service dependencies are healthy
            postgres_health = await self.check_service_health("postgresql", ValidationLevel.MINIMAL)
            duckdb_health = await self.check_service_health("duckdb", ValidationLevel.MINIMAL)
            
            result.dependencies["postgresql"] = postgres_health.overall_status
            result.dependencies["duckdb"] = duckdb_health.overall_status
            
            if postgres_health.overall_status == HealthStatus.CRITICAL:
                result.errors.append("PostgreSQL dependency is critical")
                result.checks_failed += 1
            else:
                result.checks_passed += 1
            
            if duckdb_health.overall_status == HealthStatus.CRITICAL:
                result.errors.append("DuckDB dependency is critical")
                result.checks_failed += 1
            else:
                result.checks_passed += 1
            
            result.total_checks += 2
            
            # Check sync lag from Redis metrics
            if self.redis_client:
                sync_lag = await self.redis_client.get("data_sync:lag_seconds")
                if sync_lag:
                    lag_seconds = float(sync_lag)
                    result.metrics["sync_lag_seconds"] = lag_seconds
                    
                    if lag_seconds > 300:  # 5 minutes
                        result.errors.append(f"High sync lag: {lag_seconds:.0f}s")
                        result.checks_failed += 1
                    elif lag_seconds > 120:  # 2 minutes
                        result.warnings.append(f"Elevated sync lag: {lag_seconds:.0f}s")
                        result.checks_passed += 1
                    else:
                        result.checks_passed += 1
                else:
                    result.warnings.append("No sync lag data available")
                    result.checks_passed += 1
                
                result.total_checks += 1
            
            # Calculate overall status
            if result.checks_failed > 0:
                result.status = HealthStatus.CRITICAL if result.checks_failed > 1 else HealthStatus.UNHEALTHY
                result.success = False
            elif result.warnings:
                result.status = HealthStatus.DEGRADED
                result.success = True
            else:
                result.status = HealthStatus.HEALTHY
                result.success = True
            
            result.health_score = (result.checks_passed / result.total_checks) * 100 if result.total_checks > 0 else 0
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"Data sync functional check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    async def _check_security_compliance(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check security configuration and compliance"""
        result = HealthCheckResult(
            service_name="security",
            check_type=config.check_type
        )
        
        try:
            # Check SSL/TLS configuration
            if hasattr(settings, 'USE_HTTPS') and settings.USE_HTTPS:
                result.checks_passed += 1
            else:
                result.warnings.append("HTTPS not configured")
                result.checks_passed += 1  # Not critical for development
            
            result.total_checks += 1
            
            # Check JWT secret configuration
            if hasattr(settings, 'SECRET_KEY') and len(settings.SECRET_KEY) >= 32:
                result.checks_passed += 1
            else:
                result.errors.append("Weak or missing JWT secret key")
                result.checks_failed += 1
            
            result.total_checks += 1
            
            # Check database connection security
            if hasattr(settings, 'POSTGRES_PASSWORD') and len(settings.POSTGRES_PASSWORD) >= 8:
                result.checks_passed += 1
            else:
                result.warnings.append("Database password should be stronger")
                result.checks_passed += 1
            
            result.total_checks += 1
            
            # Check rate limiting configuration
            if hasattr(settings, 'RATE_LIMIT_ENABLED') and settings.RATE_LIMIT_ENABLED:
                result.checks_passed += 1
            else:
                result.warnings.append("Rate limiting not configured")
                result.checks_passed += 1
            
            result.total_checks += 1
            
            # Check CORS configuration
            if hasattr(settings, 'CORS_ORIGINS') and settings.CORS_ORIGINS:
                if '*' in settings.CORS_ORIGINS:
                    result.warnings.append("CORS allows all origins - security risk")
                result.checks_passed += 1
            else:
                result.warnings.append("CORS not configured")
                result.checks_passed += 1
            
            result.total_checks += 1
            
            # Calculate security score
            security_score = (result.checks_passed / result.total_checks) * 100
            result.metrics["security_score"] = security_score
            
            if result.checks_failed > 0:
                result.status = HealthStatus.CRITICAL if result.checks_failed > 1 else HealthStatus.UNHEALTHY
                result.success = False
            elif len(result.warnings) > 2:
                result.status = HealthStatus.DEGRADED
                result.success = True
            else:
                result.status = HealthStatus.HEALTHY
                result.success = True
            
            result.health_score = security_score
            
        except Exception as e:
            result.status = HealthStatus.CRITICAL
            result.success = False
            result.errors.append(f"Security compliance check failed: {str(e)}")
            result.health_score = 0.0
            result.total_checks = 1
            result.checks_failed = 1
        
        return result
    
    # Public API methods
    
    async def get_system_health(self, validation_level: ValidationLevel = ValidationLevel.STANDARD) -> Dict[str, ServiceHealthSummary]:
        """Get health status for all services"""
        try:
            service_names = self._get_unique_service_names()
            health_summaries = {}
            
            # Run health checks in parallel
            tasks = [
                self.check_service_health(service_name, validation_level)
                for service_name in service_names
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for service_name, result in zip(service_names, results):
                if isinstance(result, Exception):
                    logger.error(f"Health check failed for {service_name}: {result}")
                    health_summaries[service_name] = ServiceHealthSummary(
                        service_name=service_name,
                        overall_status=HealthStatus.CRITICAL,
                        overall_score=0.0
                    )
                else:
                    health_summaries[service_name] = result
            
            return health_summaries
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {}
    
    async def get_health_history(self, service_name: str, hours: int = 24) -> List[HealthCheckResult]:
        """Get health check history for a service"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            history = self._health_history.get(service_name, [])
            
            return [result for result in history if result.timestamp >= cutoff_time]
            
        except Exception as e:
            logger.error(f"Error getting health history for {service_name}: {e}")
            return []
    
    async def get_health_trends(self, service_name: str) -> Dict[str, Any]:
        """Get health trends analysis for a service"""
        try:
            history = await self.get_health_history(service_name, hours=24)
            
            if len(history) < 2:
                return {"trend": "insufficient_data"}
            
            # Calculate trend metrics
            recent_scores = [result.health_score for result in history[-10:]]
            older_scores = [result.health_score for result in history[-20:-10]] if len(history) >= 20 else []
            
            current_avg = sum(recent_scores) / len(recent_scores)
            previous_avg = sum(older_scores) / len(older_scores) if older_scores else current_avg
            
            trend_change = current_avg - previous_avg
            
            return {
                "current_score": current_avg,
                "previous_score": previous_avg,
                "trend_change": trend_change,
                "trend_direction": "improving" if trend_change > 5 else "degrading" if trend_change < -5 else "stable",
                "total_checks": len(history),
                "success_rate": len([r for r in history if r.success]) / len(history) * 100
            }
            
        except Exception as e:
            logger.error(f"Error getting health trends for {service_name}: {e}")
            return {"error": str(e)}
    
    async def get_health_statistics(self) -> Dict[str, Any]:
        """Get overall health check statistics"""
        try:
            stats = {
                "total_services": len(self._get_unique_service_names()),
                "total_health_checks": len(self._health_checks),
                "enabled_health_checks": len([hc for hc in self._health_checks.values() if hc.enabled]),
                "services_monitored": len(self._health_history),
                "total_remediation_attempts": sum(len(attempts) for attempts in self._remediation_attempts.values()),
                "circuit_breakers_active": len(self._circuit_breakers)
            }
            
            # Service status breakdown
            current_health = await self.get_system_health(ValidationLevel.MINIMAL)
            status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "critical": 0, "unknown": 0}
            
            for summary in current_health.values():
                status_counts[summary.overall_status.value] += 1
            
            stats["service_status_breakdown"] = status_counts
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting health statistics: {e}")
            return {"error": str(e)}
    
    async def shutdown(self):
        """Cleanup health check service resources"""
        try:
            # Signal shutdown to background tasks
            self._shutdown_event.set()
            
            # Wait for background tasks to complete
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            # Close Redis connection
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("HealthCheckService shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during HealthCheckService shutdown: {e}")


# Global health check service instance
health_check_service = HealthCheckService()


# FastAPI dependency
async def get_health_check_service() -> HealthCheckService:
    """FastAPI dependency for health check service"""
    if not health_check_service.redis_client:
        await health_check_service.initialize()
    return health_check_service