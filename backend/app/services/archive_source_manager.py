"""
Archive Source Manager Service

This service provides high-level operations for managing archive source configurations,
including impact assessment, testing, metrics collection, and safe transitions between
archive sources for projects.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from fastapi import HTTPException, status

from ..core.config import settings
from ..models.project import (
    Project, Domain, ScrapeSession, ArchiveSource, ArchiveSourceChangeLog,
    ScrapeSessionStatus
)
from ..models.scraping import ScrapePage, ScrapePageStatus
from ..schemas.archive_source_schemas import (
    ArchiveSourceUpdateRequest, ArchiveSourceUpdateResponse, ArchiveSourceImpact,
    ArchiveSourceTestRequest, ArchiveSourceTestResponse, ArchiveSourceTestResult,
    ArchiveSourceMetricsResponse, ArchiveSourceStats, ImpactWarning, ImpactSeverity,
    PerformanceImpact, ConnectivityStatus, ArchiveConfig
)
from ..services.archive_service_router import (
    ArchiveServiceRouter, RoutingConfig, create_routing_config_from_project,
    ArchiveServiceRouterException, AllSourcesFailedException
)
from ..services.projects import ProjectService

logger = logging.getLogger(__name__)


class ArchiveSourceManagerException(Exception):
    """Base exception for archive source manager operations"""
    pass


class ArchiveSourceManager:
    """
    High-level service for managing archive source configurations and transitions.
    
    This service provides safe operations for changing archive sources, including
    impact assessment, connectivity testing, performance monitoring, and rollback
    capabilities.
    """
    
    def __init__(self):
        """Initialize the archive source manager"""
        self.router_cache: Dict[str, ArchiveServiceRouter] = {}
        self.test_timeout_seconds = 30
        self.rollback_window_hours = 24
    
    async def assess_archive_source_impact(
        self,
        db: AsyncSession,
        project_id: int,
        new_archive_source: ArchiveSource,
        user_id: int
    ) -> ArchiveSourceImpact:
        """
        Assess the impact of changing to a new archive source.
        
        Args:
            db: Database session
            project_id: ID of the project
            new_archive_source: Proposed new archive source
            user_id: ID of the user making the change
            
        Returns:
            Detailed impact assessment
            
        Raises:
            HTTPException: If project not found or access denied
        """
        # Get project
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        current_source = project.archive_source
        
        # If no change, return minimal impact
        if current_source == new_archive_source:
            return ArchiveSourceImpact(
                current_source=current_source,
                new_source=new_archive_source,
                estimated_coverage_change=0.0,
                coverage_explanation="No change in archive source",
                performance_impact=PerformanceImpact.NEUTRAL,
                ongoing_scraping_sessions=0,
                affected_domains=[],
                safe_to_switch=True,
                requires_confirmation=False,
                warnings=[],
                recommendations=["No action required - source unchanged"],
                estimated_migration_time=0
            )
        
        # Get ongoing scraping sessions
        ongoing_sessions_stmt = select(func.count(ScrapeSession.id)).where(
            and_(
                ScrapeSession.project_id == project_id,
                ScrapeSession.status.in_([
                    ScrapeSessionStatus.PENDING,
                    ScrapeSessionStatus.RUNNING
                ])
            )
        )
        ongoing_sessions_result = await db.execute(ongoing_sessions_stmt)
        ongoing_sessions = ongoing_sessions_result.scalar() or 0
        
        # Get affected domains
        domains_stmt = select(Domain.domain_name).where(
            and_(Domain.project_id == project_id, Domain.active == True)
        )
        domains_result = await db.execute(domains_stmt)
        affected_domains = [row[0] for row in domains_result]
        
        # Assess coverage impact
        coverage_change, coverage_explanation = self._assess_coverage_impact(
            current_source, new_archive_source
        )
        
        # Assess performance impact
        performance_impact, response_time_change = self._assess_performance_impact(
            current_source, new_archive_source
        )
        
        # Generate warnings
        warnings = self._generate_impact_warnings(
            current_source, new_archive_source, ongoing_sessions, coverage_change
        )
        
        # Determine safety
        safe_to_switch = (
            ongoing_sessions == 0 and
            coverage_change >= -0.1 and  # No more than 10% coverage loss
            not any(w.severity in [ImpactSeverity.HIGH, ImpactSeverity.CRITICAL] 
                   for w in warnings)
        )
        
        requires_confirmation = (
            ongoing_sessions > 0 or
            coverage_change < -0.05 or  # More than 5% coverage loss
            any(w.severity in [ImpactSeverity.MEDIUM, ImpactSeverity.HIGH, ImpactSeverity.CRITICAL] 
                for w in warnings)
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            current_source, new_archive_source, ongoing_sessions, coverage_change
        )
        
        # Estimate migration time
        estimated_migration_time = self._estimate_migration_time(
            ongoing_sessions, len(affected_domains)
        )
        
        return ArchiveSourceImpact(
            current_source=current_source,
            new_source=new_archive_source,
            estimated_coverage_change=coverage_change,
            coverage_explanation=coverage_explanation,
            performance_impact=performance_impact,
            response_time_change=response_time_change,
            ongoing_scraping_sessions=ongoing_sessions,
            affected_domains=affected_domains,
            safe_to_switch=safe_to_switch,
            requires_confirmation=requires_confirmation,
            warnings=warnings,
            recommendations=recommendations,
            estimated_migration_time=estimated_migration_time,
            rollback_window=self.rollback_window_hours * 3600
        )
    
    def _assess_coverage_impact(
        self, 
        current_source: ArchiveSource, 
        new_source: ArchiveSource
    ) -> Tuple[float, str]:
        """Assess the impact on data coverage when changing archive sources"""
        
        # Coverage estimates based on historical data and source characteristics
        coverage_matrix = {
            (ArchiveSource.WAYBACK_MACHINE, ArchiveSource.COMMON_CRAWL): (
                -0.15, "Common Crawl typically has less historical coverage than Wayback Machine"
            ),
            (ArchiveSource.WAYBACK_MACHINE, ArchiveSource.HYBRID): (
                0.25, "Hybrid mode will provide additional coverage from Common Crawl"
            ),
            (ArchiveSource.COMMON_CRAWL, ArchiveSource.WAYBACK_MACHINE): (
                0.20, "Wayback Machine typically has more comprehensive historical coverage"
            ),
            (ArchiveSource.COMMON_CRAWL, ArchiveSource.HYBRID): (
                0.15, "Hybrid mode will add Wayback Machine's historical coverage"
            ),
            (ArchiveSource.HYBRID, ArchiveSource.WAYBACK_MACHINE): (
                -0.20, "Switching to single source will lose Common Crawl coverage"
            ),
            (ArchiveSource.HYBRID, ArchiveSource.COMMON_CRAWL): (
                -0.25, "Switching to single source will lose Wayback Machine's historical coverage"
            )
        }
        
        return coverage_matrix.get(
            (current_source, new_source),
            (0.0, "Coverage impact unknown for this transition")
        )
    
    def _assess_performance_impact(
        self, 
        current_source: ArchiveSource, 
        new_source: ArchiveSource
    ) -> Tuple[PerformanceImpact, Optional[float]]:
        """Assess the performance impact of changing archive sources"""
        
        # Performance characteristics based on typical response times
        performance_matrix = {
            (ArchiveSource.WAYBACK_MACHINE, ArchiveSource.COMMON_CRAWL): (
                PerformanceImpact.POSITIVE, -0.5  # Common Crawl typically faster
            ),
            (ArchiveSource.WAYBACK_MACHINE, ArchiveSource.HYBRID): (
                PerformanceImpact.NEGATIVE, 0.8  # Hybrid mode has overhead
            ),
            (ArchiveSource.COMMON_CRAWL, ArchiveSource.WAYBACK_MACHINE): (
                PerformanceImpact.NEGATIVE, 0.5  # Wayback Machine typically slower
            ),
            (ArchiveSource.COMMON_CRAWL, ArchiveSource.HYBRID): (
                PerformanceImpact.NEGATIVE, 0.3  # Hybrid mode has some overhead
            ),
            (ArchiveSource.HYBRID, ArchiveSource.WAYBACK_MACHINE): (
                PerformanceImpact.POSITIVE, -0.3  # Single source is simpler
            ),
            (ArchiveSource.HYBRID, ArchiveSource.COMMON_CRAWL): (
                PerformanceImpact.POSITIVE, -0.8  # Common Crawl + no fallback overhead
            )
        }
        
        return performance_matrix.get(
            (current_source, new_source),
            (PerformanceImpact.NEUTRAL, None)
        )
    
    def _generate_impact_warnings(
        self,
        current_source: ArchiveSource,
        new_source: ArchiveSource,
        ongoing_sessions: int,
        coverage_change: float
    ) -> List[ImpactWarning]:
        """Generate warnings about the archive source change impact"""
        warnings = []
        
        # Active scraping warning
        if ongoing_sessions > 0:
            warnings.append(ImpactWarning(
                severity=ImpactSeverity.HIGH,
                category="active_operations",
                title="Active scraping sessions",
                description=f"There are {ongoing_sessions} active scraping sessions that will be affected",
                recommendation="Wait for current sessions to complete or cancel them before switching"
            ))
        
        # Coverage loss warning
        if coverage_change < -0.1:
            severity = ImpactSeverity.CRITICAL if coverage_change < -0.3 else ImpactSeverity.HIGH
            warnings.append(ImpactWarning(
                severity=severity,
                category="data_coverage",
                title="Significant coverage loss",
                description=f"Estimated {abs(coverage_change)*100:.1f}% reduction in data coverage",
                recommendation="Consider using hybrid mode to maintain broader coverage"
            ))
        elif coverage_change < -0.05:
            warnings.append(ImpactWarning(
                severity=ImpactSeverity.MEDIUM,
                category="data_coverage", 
                title="Minor coverage loss",
                description=f"Estimated {abs(coverage_change)*100:.1f}% reduction in data coverage",
                recommendation="Monitor results after migration to ensure acceptable coverage"
            ))
        
        # Source-specific warnings
        if new_source == ArchiveSource.COMMON_CRAWL:
            warnings.append(ImpactWarning(
                severity=ImpactSeverity.MEDIUM,
                category="historical_data",
                title="Limited historical coverage",
                description="Common Crawl has less historical coverage than Wayback Machine",
                recommendation="Consider hybrid mode if historical data is important"
            ))
        
        if current_source == ArchiveSource.HYBRID and new_source != ArchiveSource.HYBRID:
            warnings.append(ImpactWarning(
                severity=ImpactSeverity.MEDIUM,
                category="redundancy",
                title="Loss of redundancy",
                description="Switching from hybrid mode removes fallback protection",
                recommendation="Ensure the target source is reliable for your use case"
            ))
        
        return warnings
    
    def _generate_recommendations(
        self,
        current_source: ArchiveSource,
        new_source: ArchiveSource, 
        ongoing_sessions: int,
        coverage_change: float
    ) -> List[str]:
        """Generate recommendations for the archive source change"""
        recommendations = []
        
        if ongoing_sessions > 0:
            recommendations.append(
                "Wait for active scraping sessions to complete before switching sources"
            )
            recommendations.append(
                "Alternatively, cancel active sessions if the change is urgent"
            )
        
        if coverage_change < -0.1:
            recommendations.append(
                "Consider using hybrid mode instead to maintain coverage from both sources"
            )
        
        if new_source == ArchiveSource.HYBRID:
            recommendations.append(
                "Configure fallback strategy and delays in archive configuration for optimal performance"
            )
        
        if current_source != ArchiveSource.HYBRID and new_source != ArchiveSource.HYBRID:
            recommendations.append(
                "Test the new source with a few domains before fully migrating"
            )
        
        recommendations.append(
            "Monitor performance metrics after the change to ensure optimal operation"
        )
        
        recommendations.append(
            f"You can rollback this change within {self.rollback_window_hours} hours if needed"
        )
        
        return recommendations
    
    def _estimate_migration_time(self, ongoing_sessions: int, domain_count: int) -> int:
        """Estimate migration time in seconds"""
        base_time = 5  # Base migration time
        session_time = ongoing_sessions * 10  # Time to wait for sessions
        domain_time = domain_count * 2  # Time per domain to update
        return base_time + session_time + domain_time
    
    async def test_archive_source_connectivity(
        self,
        db: AsyncSession,
        project_id: int,
        request: ArchiveSourceTestRequest,
        user_id: int
    ) -> ArchiveSourceTestResponse:
        """
        Test connectivity and performance of an archive source.
        
        Args:
            db: Database session
            project_id: ID of the project
            request: Test configuration
            user_id: ID of the user requesting the test
            
        Returns:
            Detailed test results
            
        Raises:
            HTTPException: If project not found or access denied
        """
        # Get project
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        test_start = datetime.utcnow()
        
        # Get domains to test
        test_domains = request.test_domains
        if not test_domains:
            # Use project domains
            domains_stmt = select(Domain.domain_name).where(
                and_(Domain.project_id == project_id, Domain.active == True)
            ).limit(5)  # Limit to 5 domains for testing
            domains_result = await db.execute(domains_stmt)
            test_domains = [row[0] for row in domains_result]
        
        if not test_domains:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No domains available for testing"
            )
        
        # Initialize router for testing
        test_config = create_routing_config_from_project(
            archive_source=request.archive_source,
            fallback_enabled=False,  # Disable fallback for pure testing
            archive_config=project.archive_config
        )
        router = ArchiveServiceRouter(test_config)
        
        # Run tests
        test_results = []
        total_response_time = 0.0
        total_records = 0
        errors = []
        error_counts: Dict[str, int] = {}
        
        for domain in test_domains:
            result = await self._test_single_domain(
                router, domain, request.archive_source, request.timeout_seconds or 30
            )
            test_results.append(result)
            
            if result.success:
                total_response_time += result.response_time_ms or 0
                total_records += result.records_found or 0
            else:
                if result.error_message:
                    errors.append(f"{domain}: {result.error_message}")
                if result.error_type:
                    error_counts[result.error_type] = error_counts.get(result.error_type, 0) + 1
        
        # Calculate aggregate metrics
        tests_passed = sum(1 for r in test_results if r.success)
        success_rate = tests_passed / len(test_results) if test_results else 0.0
        avg_response_time = total_response_time / tests_passed if tests_passed > 0 else None
        
        # Determine overall status
        if success_rate >= 0.8:
            overall_status = ConnectivityStatus.HEALTHY
        elif success_rate >= 0.5:
            overall_status = ConnectivityStatus.DEGRADED
        else:
            overall_status = ConnectivityStatus.FAILED
        
        # Generate recommendations
        recommendations = self._generate_test_recommendations(
            overall_status, success_rate, test_results
        )
        
        test_end = datetime.utcnow()
        
        return ArchiveSourceTestResponse(
            archive_source=request.archive_source,
            overall_status=overall_status,
            tests_run=len(test_results),
            tests_passed=tests_passed,
            success_rate=success_rate,
            avg_response_time_ms=avg_response_time,
            total_records_found=total_records,
            test_results=test_results,
            errors=list(set(errors)),  # Deduplicate errors
            error_summary=error_counts,
            recommendations=recommendations,
            test_started_at=test_start,
            test_completed_at=test_end,
            test_duration_seconds=(test_end - test_start).total_seconds()
        )
    
    async def _test_single_domain(
        self,
        router: ArchiveServiceRouter,
        domain: str,
        archive_source: ArchiveSource,
        timeout_seconds: int
    ) -> ArchiveSourceTestResult:
        """Test a single domain against an archive source"""
        start_time = time.time()
        
        try:
            # Use a small date range for testing (last 30 days)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            # Query the archive
            records, stats = await asyncio.wait_for(
                router.query_archive(
                    domain=domain,
                    from_date=start_date.strftime("%Y%m%d"),
                    to_date=end_date.strftime("%Y%m%d"),
                    project_config={
                        'archive_source': archive_source,
                        'fallback_enabled': False
                    }
                ),
                timeout=timeout_seconds
            )
            
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            return ArchiveSourceTestResult(
                domain=domain,
                success=True,
                response_time_ms=response_time,
                records_found=len(records),
                error_message=None,
                error_type=None
            )
            
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return ArchiveSourceTestResult(
                domain=domain,
                success=False,
                response_time_ms=response_time,
                records_found=0,
                error_message="Test timed out",
                error_type="timeout"
            )
            
        except AllSourcesFailedException as e:
            response_time = (time.time() - start_time) * 1000
            return ArchiveSourceTestResult(
                domain=domain,
                success=False,
                response_time_ms=response_time,
                records_found=0,
                error_message=str(e),
                error_type="all_sources_failed"
            )
            
        except ArchiveServiceRouterException as e:
            response_time = (time.time() - start_time) * 1000
            return ArchiveSourceTestResult(
                domain=domain,
                success=False,
                response_time_ms=response_time,
                records_found=0,
                error_message=str(e),
                error_type="router_error"
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ArchiveSourceTestResult(
                domain=domain,
                success=False,
                response_time_ms=response_time,
                records_found=0,
                error_message=str(e),
                error_type="unknown_error"
            )
    
    def _generate_test_recommendations(
        self,
        overall_status: ConnectivityStatus,
        success_rate: float,
        test_results: List[ArchiveSourceTestResult]
    ) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        if overall_status == ConnectivityStatus.HEALTHY:
            recommendations.append("Archive source is performing well and ready for use")
        elif overall_status == ConnectivityStatus.DEGRADED:
            recommendations.append("Archive source has some issues but may still be usable")
            recommendations.append("Consider investigating failing domains or trying hybrid mode")
        else:
            recommendations.append("Archive source has significant issues and should not be used")
            recommendations.append("Check network connectivity and try again, or use a different source")
        
        # Check for consistent timeouts
        timeout_count = sum(1 for r in test_results if r.error_type == "timeout")
        if timeout_count > len(test_results) * 0.3:
            recommendations.append("Many tests timed out - consider increasing timeout settings")
        
        # Check for no records found
        no_records_count = sum(1 for r in test_results if r.success and (r.records_found or 0) == 0)
        if no_records_count > len(test_results) * 0.5:
            recommendations.append("Many domains returned no records - verify domain list and date ranges")
        
        return recommendations
    
    async def update_archive_source(
        self,
        db: AsyncSession,
        project_id: int,
        request: ArchiveSourceUpdateRequest,
        user_id: int,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> ArchiveSourceUpdateResponse:
        """
        Update the archive source configuration for a project.
        
        Args:
            db: Database session
            project_id: ID of the project to update
            request: Update request with new configuration
            user_id: ID of the user making the change
            session_id: Optional session ID for audit trail
            ip_address: Optional IP address for audit trail
            user_agent: Optional user agent for audit trail
            
        Returns:
            Update response with results
            
        Raises:
            HTTPException: If validation fails or update is unsafe
        """
        # Get project
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        old_archive_source = project.archive_source
        old_fallback_enabled = project.fallback_enabled
        old_config = project.archive_config.copy() if project.archive_config else {}
        
        # If no change, return success without doing anything
        if (old_archive_source == request.archive_source and
            old_fallback_enabled == request.fallback_enabled and
            old_config == (request.archive_config.model_dump() if request.archive_config else {})):
            
            return ArchiveSourceUpdateResponse(
                success=True,
                message="No changes to archive source configuration",
                project_id=project_id,
                old_archive_source=old_archive_source,
                new_archive_source=request.archive_source,
                old_config=old_config,
                new_config=request.archive_config.model_dump() if request.archive_config else {},
                warnings=[],
                updated_at=datetime.utcnow()
            )
        
        # Perform impact assessment if not confirmed
        if not request.confirm_impact:
            impact = await self.assess_archive_source_impact(
                db, project_id, request.archive_source, user_id
            )
            
            if not impact.safe_to_switch:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Archive source change is not safe without confirmation. "
                           "Please review the impact assessment and set confirm_impact=true"
                )
        
        warnings = []
        
        try:
            # Update the project
            project.archive_source = request.archive_source
            project.fallback_enabled = request.fallback_enabled
            project.archive_config = request.archive_config.model_dump() if request.archive_config else {}
            
            # Save changes
            await db.commit()
            await db.refresh(project)
            
            # Create audit log entry
            change_log = ArchiveSourceChangeLog(
                project_id=project_id,
                user_id=user_id,
                old_archive_source=old_archive_source,
                new_archive_source=request.archive_source,
                old_fallback_enabled=old_fallback_enabled,
                new_fallback_enabled=request.fallback_enabled,
                old_config=old_config,
                new_config=project.archive_config,
                change_reason=request.change_reason,
                impact_acknowledged=request.confirm_impact,
                success=True,
                rollback_deadline=datetime.utcnow() + timedelta(hours=self.rollback_window_hours),
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            db.add(change_log)
            await db.commit()
            
            logger.info(f"Successfully updated archive source for project {project_id} "
                       f"from {old_archive_source} to {request.archive_source}")
            
            return ArchiveSourceUpdateResponse(
                success=True,
                message=f"Successfully updated archive source to {request.archive_source.value}",
                project_id=project_id,
                old_archive_source=old_archive_source,
                new_archive_source=request.archive_source,
                old_config=old_config,
                new_config=project.archive_config,
                warnings=warnings,
                updated_at=datetime.utcnow()
            )
            
        except Exception as e:
            # Rollback the transaction
            await db.rollback()
            
            # Create failed audit log entry
            error_message = str(e)
            change_log = ArchiveSourceChangeLog(
                project_id=project_id,
                user_id=user_id,
                old_archive_source=old_archive_source,
                new_archive_source=request.archive_source,
                old_fallback_enabled=old_fallback_enabled,
                new_fallback_enabled=request.fallback_enabled,
                old_config=old_config,
                new_config=request.archive_config.model_dump() if request.archive_config else {},
                change_reason=request.change_reason,
                impact_acknowledged=request.confirm_impact,
                success=False,
                error_message=error_message,
                rollback_available=False,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            db.add(change_log)
            await db.commit()
            
            logger.error(f"Failed to update archive source for project {project_id}: {error_message}")
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update archive source: {error_message}"
            )
    
    async def get_archive_source_metrics(
        self,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        time_period: str = "24h"
    ) -> ArchiveSourceMetricsResponse:
        """
        Get performance metrics for archive sources used by a project.
        
        Args:
            db: Database session
            project_id: ID of the project
            user_id: ID of the user requesting metrics
            time_period: Time period for metrics ("24h", "7d", "30d")
            
        Returns:
            Comprehensive metrics response
        """
        # Get project
        project = await ProjectService.get_project_by_id(db, project_id, user_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Get project's archive router for metrics
        router_key = f"{project_id}_{project.archive_source.value}"
        if router_key not in self.router_cache:
            config = create_routing_config_from_project(
                archive_source=project.archive_source,
                fallback_enabled=project.fallback_enabled,
                archive_config=project.archive_config
            )
            self.router_cache[router_key] = ArchiveServiceRouter(config)
        
        router = self.router_cache[router_key]
        
        # Get performance metrics from router
        performance_metrics = router.get_performance_metrics()
        
        # Convert to response format
        archive_sources = {}
        for source_name, metrics in performance_metrics["sources"].items():
            archive_sources[source_name] = ArchiveSourceStats(
                source_name=source_name,
                total_requests=metrics["total_queries"],
                successful_requests=metrics["successful_queries"],
                failed_requests=metrics["failed_queries"],
                success_rate=metrics["success_rate"],
                average_response_time_ms=metrics["avg_response_time"] * 1000,  # Convert to ms
                total_records_retrieved=metrics["total_records"],
                error_rate=100.0 - metrics["success_rate"],
                error_breakdown=metrics["error_counts"],
                circuit_breaker_state="unknown",  # Will be filled from circuit breaker status
                circuit_breaker_failures=0,
                last_success_at=datetime.fromisoformat(metrics["last_success_time"]) if metrics["last_success_time"] else None,
                last_failure_at=datetime.fromisoformat(metrics["last_failure_time"]) if metrics["last_failure_time"] else None,
                last_used_at=None,  # Not tracked in current metrics
                is_healthy=metrics["is_healthy"],
                health_score=metrics["success_rate"]
            )
        
        # Update circuit breaker information
        circuit_breaker_status = performance_metrics["circuit_breakers"]
        for source_name in archive_sources:
            if source_name in circuit_breaker_status:
                cb_info = circuit_breaker_status[source_name]
                archive_sources[source_name].circuit_breaker_state = cb_info["state"]
                archive_sources[source_name].circuit_breaker_failures = cb_info.get("failures", 0)
        
        # Generate recommendations
        recommendations = []
        overall_success_rate = performance_metrics["overall"]["avg_success_rate"]
        if overall_success_rate < 80:
            recommendations.append("Consider switching to hybrid mode for better reliability")
        if overall_success_rate > 95:
            recommendations.append("Archive source performance is excellent")
        
        return ArchiveSourceMetricsResponse(
            project_id=project_id,
            time_period=time_period,
            archive_sources=archive_sources,
            hybrid_fallback_events=0,  # TODO: Track this in router
            primary_source_failures=0,  # TODO: Track this in router
            fallback_success_rate=100.0,  # TODO: Calculate this
            total_queries=performance_metrics["overall"]["total_queries"],
            overall_success_rate=overall_success_rate,
            avg_query_time_ms=0.0,  # TODO: Calculate weighted average
            recommendations=recommendations,
            circuit_breaker_status={k: v["state"] for k, v in circuit_breaker_status.items()},
            generated_at=datetime.utcnow(),
            data_freshness=f"Real-time ({performance_metrics['overall']['query_history_size']} recent queries)"
        )