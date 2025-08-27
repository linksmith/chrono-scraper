"""
Incremental Scraping Service

This service provides comprehensive incremental scraping functionality including:
- Date range determination for optimal incremental scraping
- Coverage gap detection and analysis
- Scraping statistics and monitoring
- Gap fill task generation and prioritization
"""

import logging
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Tuple, Set
from sqlmodel import select, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Domain, Page, IncrementalMode
from app.models.scraping import (
    IncrementalScrapingHistory,
    IncrementalScrapingHistoryCreate,
    IncrementalRunType,
    IncrementalRunStatus,
    ScrapePage,
    ScrapePageStatus
)

logger = logging.getLogger(__name__)


class DateRange:
    """Utility class for date range operations"""
    
    def __init__(self, start: date, end: date):
        self.start = start
        self.end = end
    
    def __contains__(self, other_date: date) -> bool:
        return self.start <= other_date <= self.end
    
    def overlaps(self, other: 'DateRange') -> bool:
        return self.start <= other.end and other.start <= self.end
    
    def merge(self, other: 'DateRange') -> 'DateRange':
        return DateRange(min(self.start, other.start), max(self.end, other.end))
    
    def gap_between(self, other: 'DateRange') -> Optional['DateRange']:
        """Return gap between two ranges if they don't overlap"""
        if self.overlaps(other):
            return None
        
        if self.end < other.start:
            return DateRange(self.end + timedelta(days=1), other.start - timedelta(days=1))
        else:
            return DateRange(other.end + timedelta(days=1), self.start - timedelta(days=1))
    
    def size_days(self) -> int:
        """Return size of range in days"""
        return (self.end - self.start).days + 1
    
    def __str__(self) -> str:
        return f"{self.start.isoformat()} to {self.end.isoformat()}"


class IncrementalScrapingService:
    """Service for managing incremental scraping operations"""
    
    @staticmethod
    async def determine_scraping_range(
        db: AsyncSession,
        domain_id: int,
        run_type: IncrementalRunType = IncrementalRunType.SCHEDULED
    ) -> Tuple[Optional[datetime], Optional[datetime], Dict[str, Any]]:
        """
        Determine optimal date range for incremental scraping.
        
        Args:
            db: Database session
            domain_id: Domain ID to analyze
            run_type: Type of incremental run being performed
            
        Returns:
            Tuple of (start_date, end_date, metadata)
        """
        logger.info(f"Determining scraping range for domain {domain_id}, run_type: {run_type}")
        
        try:
            # Get domain configuration
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                raise ValueError(f"Domain {domain_id} not found")
            
            if not domain.incremental_enabled:
                logger.warning(f"Incremental scraping disabled for domain {domain_id}")
                return None, None, {"reason": "incremental_disabled"}
            
            # Get last scraped date
            last_scraped = await IncrementalScrapingService.get_last_scraped_date(db, domain_id)
            
            # Calculate base range
            now = datetime.utcnow()
            metadata = {
                "domain_id": domain_id,
                "run_type": run_type.value,
                "incremental_mode": domain.incremental_mode.value if hasattr(domain.incremental_mode, 'value') else domain.incremental_mode,
                "overlap_days": domain.overlap_days,
                "last_scraped": last_scraped.isoformat() if last_scraped else None
            }
            
            if run_type == IncrementalRunType.BACKFILL:
                # For backfill, use domain's configured date range
                start_date = domain.from_date or (now - timedelta(days=365))
                end_date = domain.to_date or now
                metadata["strategy"] = "backfill_full_range"
                
            elif run_type == IncrementalRunType.GAP_FILL:
                # For gap fill, identify and prioritize critical gaps
                gaps = await IncrementalScrapingService.identify_critical_gaps(db, domain_id)
                if not gaps:
                    return None, None, {"reason": "no_critical_gaps"}
                
                # Use the highest priority gap
                priority_gap = gaps[0]
                start_date = datetime.fromisoformat(priority_gap["start_date"])
                end_date = datetime.fromisoformat(priority_gap["end_date"])
                metadata.update({
                    "strategy": "gap_fill",
                    "gap_priority": priority_gap["priority"],
                    "gap_size_days": priority_gap["size_days"]
                })
                
            else:
                # Regular incremental scraping
                if last_scraped:
                    # Start from overlap period before last scraped date
                    start_date = last_scraped - timedelta(days=domain.overlap_days)
                    metadata["strategy"] = "incremental_with_overlap"
                else:
                    # First time scraping - start from configured date or 30 days ago
                    start_date = domain.from_date or (now - timedelta(days=30))
                    metadata["strategy"] = "initial_scraping"
                
                end_date = now
                
                # Ensure we don't exceed domain's to_date if set
                if domain.to_date and end_date > domain.to_date:
                    end_date = domain.to_date
            
            # Apply content-based filtering if enabled
            if domain.incremental_mode in [IncrementalMode.CONTENT_BASED, IncrementalMode.HYBRID]:
                content_metadata = await IncrementalScrapingService._analyze_content_changes(
                    db, domain_id, start_date, end_date
                )
                metadata.update(content_metadata)
            
            logger.info(f"Determined range for domain {domain_id}: {start_date} to {end_date}")
            return start_date, end_date, metadata
            
        except Exception as e:
            logger.error(f"Error determining scraping range for domain {domain_id}: {e}")
            raise
    
    @staticmethod
    async def get_last_scraped_date(db: AsyncSession, domain_id: int) -> Optional[datetime]:
        """
        Get the most recent scraped date for a domain.
        
        Args:
            db: Database session
            domain_id: Domain ID
            
        Returns:
            Most recent scraped date or None
        """
        try:
            # Get most recent successful page scrape
            stmt = (
                select(func.max(Page.unix_timestamp))
                .where(
                    and_(
                        Page.domain_id == domain_id,
                        Page.unix_timestamp.is_not(None)
                    )
                )
            )
            
            result = await db.execute(stmt)
            max_timestamp = result.scalar()
            
            if max_timestamp:
                # Convert unix timestamp to datetime
                # Wayback timestamps are in format YYYYMMDDHHMMSS
                timestamp_str = str(max_timestamp)
                if len(timestamp_str) >= 14:
                    year = int(timestamp_str[0:4])
                    month = int(timestamp_str[4:6])
                    day = int(timestamp_str[6:8])
                    hour = int(timestamp_str[8:10]) if len(timestamp_str) > 8 else 0
                    minute = int(timestamp_str[10:12]) if len(timestamp_str) > 10 else 0
                    second = int(timestamp_str[12:14]) if len(timestamp_str) > 12 else 0
                    
                    return datetime(year, month, day, hour, minute, second)
            
            # Fallback: check domain's last_scraped field
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            return domain.last_scraped if domain else None
            
        except Exception as e:
            logger.error(f"Error getting last scraped date for domain {domain_id}: {e}")
            return None
    
    @staticmethod
    async def detect_coverage_gaps(
        db: AsyncSession, 
        domain_id: int, 
        min_gap_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Identify gaps in scraped date coverage.
        
        Args:
            db: Database session
            domain_id: Domain ID
            min_gap_days: Minimum gap size to report (days)
            
        Returns:
            List of gap information dictionaries
        """
        logger.info(f"Detecting coverage gaps for domain {domain_id}")
        
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return []
            
            # Get all scraped dates for the domain - ensure we pass domain_id, not domain object
            scraped_ranges = await IncrementalScrapingService._get_scraped_date_ranges(
                db, domain_id
            )
            
            if not scraped_ranges:
                # No scraped content - entire range is a gap
                start_date = domain.from_date or (datetime.utcnow() - timedelta(days=365))
                end_date = domain.to_date or datetime.utcnow()
                
                return [{
                    "start_date": start_date.date().isoformat(),
                    "end_date": end_date.date().isoformat(),
                    "size_days": (end_date.date() - start_date.date()).days + 1,
                    "priority": 10,  # Highest priority for completely unscraped domains
                    "type": "complete_gap"
                }]
            
            # Merge overlapping ranges and find gaps
            merged_ranges = IncrementalScrapingService.merge_date_ranges(scraped_ranges)
            gaps = []
            
            # Check for gap before first range
            domain_start = domain.from_date or (datetime.utcnow() - timedelta(days=365))
            first_range = merged_ranges[0]
            if domain_start.date() < first_range.start:
                gap_days = (first_range.start - domain_start.date()).days
                if gap_days >= min_gap_days:
                    gaps.append({
                        "start_date": domain_start.date().isoformat(),
                        "end_date": (first_range.start - timedelta(days=1)).isoformat(),
                        "size_days": gap_days,
                        "priority": IncrementalScrapingService._calculate_gap_priority(
                            gap_days, domain_start.date()
                        ),
                        "type": "pre_range_gap"
                    })
            
            # Check for gaps between ranges
            for i in range(len(merged_ranges) - 1):
                current_range = merged_ranges[i]
                next_range = merged_ranges[i + 1]
                
                gap = current_range.gap_between(next_range)
                if gap and gap.size_days() >= min_gap_days:
                    gaps.append({
                        "start_date": gap.start.isoformat(),
                        "end_date": gap.end.isoformat(),
                        "size_days": gap.size_days(),
                        "priority": IncrementalScrapingService._calculate_gap_priority(
                            gap.size_days(), gap.start
                        ),
                        "type": "inter_range_gap"
                    })
            
            # Check for gap after last range
            domain_end = domain.to_date or datetime.utcnow()
            last_range = merged_ranges[-1]
            if last_range.end < domain_end.date():
                gap_days = (domain_end.date() - last_range.end).days
                if gap_days >= min_gap_days:
                    gaps.append({
                        "start_date": (last_range.end + timedelta(days=1)).isoformat(),
                        "end_date": domain_end.date().isoformat(),
                        "size_days": gap_days,
                        "priority": IncrementalScrapingService._calculate_gap_priority(
                            gap_days, last_range.end + timedelta(days=1)
                        ),
                        "type": "post_range_gap"
                    })
            
            # Sort gaps by priority (highest first)
            gaps.sort(key=lambda g: g["priority"], reverse=True)
            
            logger.info(f"Found {len(gaps)} gaps for domain {domain_id}")
            return gaps
            
        except Exception as e:
            logger.error(f"Error detecting coverage gaps for domain {domain_id}: {e}")
            return []
    
    @staticmethod
    async def update_domain_coverage(
        db: AsyncSession,
        domain_id: int,
        scraping_session_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update domain coverage metadata after scraping.
        
        Args:
            db: Database session
            domain_id: Domain ID
            scraping_session_data: Optional session data for updates
            
        Returns:
            Success status
        """
        logger.info(f"Updating domain coverage for domain {domain_id}")
        
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return False
            
            # Recalculate scraped date ranges
            scraped_ranges = await IncrementalScrapingService._get_scraped_date_ranges(
                db, domain_id
            )
            
            # Update domain.scraped_date_ranges
            range_tuples = [
                (r.start.isoformat(), r.end.isoformat()) 
                for r in IncrementalScrapingService.merge_date_ranges(scraped_ranges)
            ]
            domain.scraped_date_ranges = range_tuples
            
            # Calculate coverage percentage
            domain.coverage_percentage = await IncrementalScrapingService.calculate_coverage_percentage(
                db, domain_id
            )
            
            # Update gap information
            gaps = await IncrementalScrapingService.detect_coverage_gaps(db, domain_id)
            domain.known_gaps = gaps
            
            # Update statistics
            if scraping_session_data:
                domain.new_content_discovered += scraping_session_data.get("new_content", 0)
                if scraping_session_data.get("gaps_filled", 0) > 0:
                    domain.gaps_filled += scraping_session_data["gaps_filled"]
            
            domain.last_incremental_check = datetime.utcnow()
            
            await db.commit()
            logger.info(f"Updated coverage for domain {domain_id}: {domain.coverage_percentage}%")
            return True
            
        except Exception as e:
            logger.error(f"Error updating domain coverage for domain {domain_id}: {e}")
            return False
    
    @staticmethod
    async def calculate_coverage_percentage(db: AsyncSession, domain_id: int) -> Optional[float]:
        """
        Calculate coverage percentage for a domain.
        
        Args:
            db: Database session
            domain_id: Domain ID
            
        Returns:
            Coverage percentage (0-100) or None
        """
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return None
            
            # Get domain's total date range
            total_start = domain.from_date or (datetime.utcnow() - timedelta(days=365))
            total_end = domain.to_date or datetime.utcnow()
            total_days = (total_end.date() - total_start.date()).days + 1
            
            if total_days <= 0:
                return 0.0
            
            # Get scraped ranges - ensure we pass domain_id, not domain object
            scraped_ranges = await IncrementalScrapingService._get_scraped_date_ranges(
                db, domain_id
            )
            
            if not scraped_ranges:
                return 0.0
            
            # Calculate total scraped days
            merged_ranges = IncrementalScrapingService.merge_date_ranges(scraped_ranges)
            scraped_days = sum(r.size_days() for r in merged_ranges)
            
            # Ensure scraped days don't exceed total days (due to overlaps)
            scraped_days = min(scraped_days, total_days)
            
            coverage = (scraped_days / total_days) * 100
            return round(coverage, 2)
            
        except Exception as e:
            logger.error(f"Error calculating coverage percentage for domain {domain_id}: {e}")
            return None
    
    @staticmethod
    def merge_date_ranges(date_ranges: List[DateRange]) -> List[DateRange]:
        """
        Merge overlapping date ranges.
        
        Args:
            date_ranges: List of DateRange objects
            
        Returns:
            List of merged DateRange objects
        """
        if not date_ranges:
            return []
        
        # Sort by start date
        sorted_ranges = sorted(date_ranges, key=lambda r: r.start)
        merged = [sorted_ranges[0]]
        
        for current in sorted_ranges[1:]:
            last_merged = merged[-1]
            
            # Check if current range overlaps with last merged range
            if current.start <= last_merged.end + timedelta(days=1):
                # Merge the ranges
                merged[-1] = last_merged.merge(current)
            else:
                # No overlap, add as separate range
                merged.append(current)
        
        return merged
    
    @staticmethod
    async def should_trigger_incremental(
        db: AsyncSession, 
        domain_id: int,
        force_check: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if incremental scraping should be triggered for a domain.
        
        Args:
            db: Database session
            domain_id: Domain ID
            force_check: Force check regardless of schedule
            
        Returns:
            Tuple of (should_trigger, metadata)
        """
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return False, {"reason": "domain_not_found"}
            
            if not domain.incremental_enabled:
                return False, {"reason": "incremental_disabled"}
            
            now = datetime.utcnow()
            metadata = {
                "domain_id": domain_id,
                "current_time": now.isoformat(),
                "force_check": force_check
            }
            
            # Check if forced
            if force_check:
                return True, {**metadata, "reason": "forced_check"}
            
            # Check scheduling
            if domain.next_incremental_check and now < domain.next_incremental_check:
                return False, {
                    **metadata, 
                    "reason": "not_scheduled",
                    "next_check": domain.next_incremental_check.isoformat()
                }
            
            # Check for critical gaps
            gaps = await IncrementalScrapingService.identify_critical_gaps(db, domain_id)
            if gaps:
                return True, {
                    **metadata, 
                    "reason": "critical_gaps_detected",
                    "gap_count": len(gaps)
                }
            
            # Check time since last incremental check
            if domain.last_incremental_check:
                time_since_check = now - domain.last_incremental_check
                # Default: check every 24 hours
                if time_since_check.total_seconds() < 24 * 3600:
                    return False, {
                        **metadata,
                        "reason": "recently_checked",
                        "last_check": domain.last_incremental_check.isoformat()
                    }
            
            # Check for new content availability (simplified check)
            last_scraped = await IncrementalScrapingService.get_last_scraped_date(db, domain_id)
            if last_scraped:
                time_since_scrape = now - last_scraped
                # If last scrape was less than 1 hour ago, likely no new content
                if time_since_scrape.total_seconds() < 3600:
                    return False, {
                        **metadata,
                        "reason": "recently_scraped",
                        "last_scraped": last_scraped.isoformat()
                    }
            
            return True, {**metadata, "reason": "scheduled_check"}
            
        except Exception as e:
            logger.error(f"Error checking incremental trigger for domain {domain_id}: {e}")
            return False, {"reason": "error", "error": str(e)}
    
    @staticmethod
    async def create_incremental_history(
        db: AsyncSession,
        domain_id: int,
        run_type: IncrementalRunType,
        date_range_start: datetime,
        date_range_end: datetime,
        config: Dict[str, Any],
        trigger_reason: Optional[str] = None
    ) -> Optional[int]:
        """
        Create history record for incremental scraping run.
        
        Args:
            db: Database session
            domain_id: Domain ID
            run_type: Type of incremental run
            date_range_start: Start date for scraping
            date_range_end: End date for scraping
            config: Configuration snapshot
            trigger_reason: Reason for triggering this run
            
        Returns:
            History record ID or None
        """
        try:
            history_data = IncrementalScrapingHistoryCreate(
                run_type=run_type,
                trigger_reason=trigger_reason,
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                incremental_config=config
            )
            
            history = IncrementalScrapingHistory(
                domain_id=domain_id,
                **history_data.model_dump()
            )
            
            db.add(history)
            await db.commit()
            await db.refresh(history)
            
            logger.info(f"Created incremental history record {history.id} for domain {domain_id}")
            return history.id
            
        except Exception as e:
            logger.error(f"Error creating incremental history for domain {domain_id}: {e}")
            return None
    
    @staticmethod
    async def update_incremental_statistics(
        db: AsyncSession,
        domain_id: int,
        history_id: Optional[int] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update incremental scraping run statistics.
        
        Args:
            db: Database session
            domain_id: Domain ID
            history_id: History record ID to update
            stats: Statistics to update
            
        Returns:
            Success status
        """
        try:
            if not stats:
                return True
            
            # Update domain statistics
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if domain:
                domain.total_incremental_runs += 1
                if stats.get("status") == "completed":
                    domain.successful_incremental_runs += 1
                elif stats.get("status") == "failed":
                    domain.failed_incremental_runs += 1
                
                if stats.get("runtime_seconds"):
                    if domain.avg_incremental_runtime:
                        # Calculate running average
                        total_runs = domain.successful_incremental_runs + domain.failed_incremental_runs
                        domain.avg_incremental_runtime = (
                            (domain.avg_incremental_runtime * (total_runs - 1) + 
                             stats["runtime_seconds"]) / total_runs
                        )
                    else:
                        domain.avg_incremental_runtime = stats["runtime_seconds"]
                    
                    domain.last_incremental_runtime = stats["runtime_seconds"]
                
                # Schedule next incremental check (default: 24 hours)
                domain.next_incremental_check = datetime.utcnow() + timedelta(hours=24)
            
            # Update history record if provided
            if history_id:
                stmt = select(IncrementalScrapingHistory).where(
                    IncrementalScrapingHistory.id == history_id
                )
                result = await db.execute(stmt)
                history = result.scalar_one_or_none()
                
                if history:
                    for key, value in stats.items():
                        if hasattr(history, key):
                            setattr(history, key, value)
                    
                    if stats.get("status") == "completed":
                        history.mark_completed(
                            pages_processed=stats.get("pages_processed", 0),
                            new_content=stats.get("new_content_found", 0)
                        )
                    elif stats.get("status") == "failed":
                        history.mark_failed(
                            error_message=stats.get("error_message", "Unknown error"),
                            error_details=stats.get("error_details")
                        )
            
            await db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating incremental statistics: {e}")
            return False
    
    @staticmethod
    async def identify_critical_gaps(
        db: AsyncSession, 
        domain_id: int,
        max_gap_days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find gaps that need immediate attention.
        
        Args:
            db: Database session
            domain_id: Domain ID
            max_gap_days: Maximum gap size to consider critical
            
        Returns:
            List of critical gaps ordered by priority
        """
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return []
            
            # Use domain's max_gap_days or default
            max_gap = max_gap_days or domain.max_gap_days
            
            # Get all gaps
            all_gaps = await IncrementalScrapingService.detect_coverage_gaps(
                db, domain_id, min_gap_days=1
            )
            
            # Filter for critical gaps
            critical_gaps = [
                gap for gap in all_gaps 
                if gap["size_days"] >= max_gap or gap["priority"] >= 8
            ]
            
            return critical_gaps
            
        except Exception as e:
            logger.error(f"Error identifying critical gaps for domain {domain_id}: {e}")
            return []
    
    @staticmethod
    async def prioritize_gaps(
        db: AsyncSession, 
        domain_id: int, 
        gaps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Rank gaps by importance for processing order.
        
        Args:
            db: Database session
            domain_id: Domain ID
            gaps: List of gap dictionaries
            
        Returns:
            Prioritized list of gaps
        """
        try:
            # Add additional priority factors
            for gap in gaps:
                # Recency factor - more recent gaps get higher priority
                gap_end = datetime.fromisoformat(gap["end_date"]).date()
                days_ago = (date.today() - gap_end).days
                recency_score = max(0, 10 - (days_ago / 30))  # Decline over 30 days
                
                # Size factor - larger gaps get higher priority (up to a point)
                size_score = min(5, gap["size_days"] / 10)  # Max 5 points for 50+ day gaps
                
                # Adjust priority based on additional factors
                gap["adjusted_priority"] = (
                    gap["priority"] + recency_score + size_score
                )
                
                # Add processing estimation
                gap["estimated_processing_time"] = IncrementalScrapingService._estimate_processing_time(
                    gap["size_days"]
                )
            
            # Sort by adjusted priority (highest first)
            prioritized_gaps = sorted(gaps, key=lambda g: g["adjusted_priority"], reverse=True)
            
            return prioritized_gaps
            
        except Exception as e:
            logger.error(f"Error prioritizing gaps for domain {domain_id}: {e}")
            return gaps  # Return original list on error
    
    @staticmethod
    async def generate_gap_fill_tasks(
        db: AsyncSession,
        domain_id: int,
        max_tasks: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Create tasks to fill identified gaps.
        
        Args:
            db: Database session
            domain_id: Domain ID
            max_tasks: Maximum number of tasks to generate
            
        Returns:
            List of task configurations
        """
        try:
            # Get critical gaps
            critical_gaps = await IncrementalScrapingService.identify_critical_gaps(db, domain_id)
            
            if not critical_gaps:
                return []
            
            # Prioritize gaps
            prioritized_gaps = await IncrementalScrapingService.prioritize_gaps(
                db, domain_id, critical_gaps
            )
            
            # Generate tasks for top gaps
            tasks = []
            for i, gap in enumerate(prioritized_gaps[:max_tasks]):
                task_config = {
                    "domain_id": domain_id,
                    "task_type": "gap_fill",
                    "priority": gap["adjusted_priority"],
                    "start_date": gap["start_date"],
                    "end_date": gap["end_date"],
                    "estimated_duration": gap["estimated_processing_time"],
                    "gap_info": {
                        "size_days": gap["size_days"],
                        "gap_type": gap["type"],
                        "original_priority": gap["priority"]
                    },
                    "task_order": i + 1
                }
                tasks.append(task_config)
            
            logger.info(f"Generated {len(tasks)} gap fill tasks for domain {domain_id}")
            return tasks
            
        except Exception as e:
            logger.error(f"Error generating gap fill tasks for domain {domain_id}: {e}")
            return []
    
    @staticmethod
    async def get_scraping_statistics(
        db: AsyncSession, 
        domain_id: int
    ) -> Dict[str, Any]:
        """
        Get comprehensive scraping statistics for a domain.
        
        Args:
            db: Database session
            domain_id: Domain ID
            
        Returns:
            Comprehensive statistics dictionary
        """
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return {}
            
            # Get coverage information
            coverage_percentage = await IncrementalScrapingService.calculate_coverage_percentage(
                db, domain_id
            )
            gaps = await IncrementalScrapingService.detect_coverage_gaps(db, domain_id)
            critical_gaps = await IncrementalScrapingService.identify_critical_gaps(db, domain_id)
            
            # Get incremental history summary
            history_stmt = select(IncrementalScrapingHistory).where(
                IncrementalScrapingHistory.domain_id == domain_id
            )
            history_result = await db.execute(history_stmt)
            history_records = history_result.scalars().all()
            
            # Calculate history statistics
            total_runs = len(history_records)
            successful_runs = sum(1 for h in history_records if h.status == IncrementalRunStatus.COMPLETED)
            failed_runs = sum(1 for h in history_records if h.status == IncrementalRunStatus.FAILED)
            total_new_content = sum(h.new_content_found for h in history_records if h.new_content_found)
            
            # Calculate average runtime
            completed_runs = [h for h in history_records if h.runtime_seconds]
            avg_runtime = (
                sum(h.runtime_seconds for h in completed_runs) / len(completed_runs)
                if completed_runs else None
            )
            
            return {
                "domain_id": domain_id,
                "domain_name": domain.domain_name,
                "incremental_enabled": domain.incremental_enabled,
                "incremental_mode": domain.incremental_mode.value if hasattr(domain.incremental_mode, 'value') else domain.incremental_mode,
                
                # Coverage statistics
                "coverage_percentage": coverage_percentage,
                "total_gaps": len(gaps),
                "critical_gaps": len(critical_gaps),
                "largest_gap_days": max([g["size_days"] for g in gaps], default=0),
                
                # Scraping statistics
                "total_pages": domain.total_pages,
                "scraped_pages": domain.scraped_pages,
                "failed_pages": domain.failed_pages,
                "success_rate": domain.success_rate,
                
                # Incremental statistics
                "total_incremental_runs": total_runs,
                "successful_incremental_runs": successful_runs,
                "failed_incremental_runs": failed_runs,
                "incremental_success_rate": (successful_runs / total_runs * 100) if total_runs > 0 else 0,
                "total_new_content_discovered": total_new_content,
                "avg_incremental_runtime": avg_runtime,
                
                # Timing information
                "last_scraped": await IncrementalScrapingService.get_last_scraped_date(db, domain_id),
                "last_incremental_check": domain.last_incremental_check,
                "next_incremental_check": domain.next_incremental_check,
                
                # Configuration
                "overlap_days": domain.overlap_days,
                "max_gap_days": domain.max_gap_days,
                "backfill_enabled": domain.backfill_enabled
            }
            
        except Exception as e:
            logger.error(f"Error getting scraping statistics for domain {domain_id}: {e}")
            return {"error": str(e)}
    
    @staticmethod
    async def estimate_incremental_duration(
        db: AsyncSession,
        domain_id: int,
        date_range_start: datetime,
        date_range_end: datetime
    ) -> Dict[str, Any]:
        """
        Estimate runtime for incremental scraping based on historical data.
        
        Args:
            db: Database session
            domain_id: Domain ID
            date_range_start: Start date for estimation
            date_range_end: End date for estimation
            
        Returns:
            Estimation metadata
        """
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return {"error": "Domain not found"}
            
            # Calculate range size
            range_days = (date_range_end.date() - date_range_start.date()).days + 1
            
            # Base estimation on historical data
            estimation = {}
            
            if domain.avg_incremental_runtime and domain.successful_incremental_runs > 0:
                # Use historical average
                estimated_seconds = domain.avg_incremental_runtime * (range_days / 7)  # Normalize to weekly
                estimation["estimated_duration_seconds"] = estimated_seconds
                estimation["estimated_duration_minutes"] = estimated_seconds / 60
                estimation["estimation_basis"] = "historical_data"
                estimation["confidence"] = min(0.9, domain.successful_incremental_runs / 10)
            else:
                # Use rule-based estimation
                estimated_seconds = range_days * 60  # 1 minute per day average
                estimation["estimated_duration_seconds"] = estimated_seconds
                estimation["estimated_duration_minutes"] = estimated_seconds / 60
                estimation["estimation_basis"] = "rule_based"
                estimation["confidence"] = 0.3
            
            # Add range information
            estimation.update({
                "range_days": range_days,
                "start_date": date_range_start.isoformat(),
                "end_date": date_range_end.isoformat(),
                "historical_runs": domain.successful_incremental_runs,
                "avg_historical_runtime": domain.avg_incremental_runtime
            })
            
            return estimation
            
        except Exception as e:
            logger.error(f"Error estimating incremental duration for domain {domain_id}: {e}")
            return {"error": str(e)}
    
    @staticmethod
    async def calculate_optimal_overlap(
        db: AsyncSession,
        domain_id: int
    ) -> Dict[str, Any]:
        """
        Calculate optimal overlap days based on content change patterns.
        
        Args:
            db: Database session
            domain_id: Domain ID
            
        Returns:
            Optimal overlap configuration
        """
        try:
            domain = await IncrementalScrapingService._get_domain(db, domain_id)
            if not domain:
                return {"error": "Domain not found"}
            
            # Analyze content change patterns
            # This is a simplified implementation - could be enhanced with ML
            
            current_overlap = domain.overlap_days
            recommended_overlap = current_overlap
            
            # Get recent incremental runs
            stmt = (
                select(IncrementalScrapingHistory)
                .where(IncrementalScrapingHistory.domain_id == domain_id)
                .order_by(desc(IncrementalScrapingHistory.started_at))
                .limit(10)
            )
            result = await db.execute(stmt)
            recent_runs = result.scalars().all()
            
            if recent_runs:
                # Analyze gap detection in recent runs
                gap_detection_rate = sum(
                    1 for run in recent_runs 
                    if run.gaps_detected and len(run.gaps_detected) > 0
                ) / len(recent_runs)
                
                # Adjust overlap based on gap detection rate
                if gap_detection_rate > 0.3:  # More than 30% of runs detect gaps
                    recommended_overlap = min(current_overlap + 3, 14)  # Increase overlap, max 14 days
                elif gap_detection_rate < 0.1:  # Less than 10% of runs detect gaps
                    recommended_overlap = max(current_overlap - 1, 3)  # Decrease overlap, min 3 days
            
            return {
                "current_overlap_days": current_overlap,
                "recommended_overlap_days": recommended_overlap,
                "change_needed": recommended_overlap != current_overlap,
                "analysis_basis": f"Based on {len(recent_runs)} recent runs",
                "gap_detection_rate": gap_detection_rate if recent_runs else None,
                "confidence": min(0.8, len(recent_runs) / 10) if recent_runs else 0.2
            }
            
        except Exception as e:
            logger.error(f"Error calculating optimal overlap for domain {domain_id}: {e}")
            return {"error": str(e)}
    
    # Private helper methods
    
    @staticmethod
    async def _get_domain(db: AsyncSession, domain_id: int) -> Optional[Domain]:
        """Get domain by ID"""
        stmt = select(Domain).where(Domain.id == domain_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def _get_scraped_date_ranges(
        db: AsyncSession, 
        domain_id: int
    ) -> List[DateRange]:
        """Get all scraped date ranges for a domain"""
        try:
            # Get unique dates from scraped pages - ensure domain_id is used properly
            stmt = (
                select(func.distinct(Page.unix_timestamp))
                .where(Page.domain_id == domain_id)
                .where(Page.unix_timestamp.is_not(None))
                .order_by(Page.unix_timestamp)
            )
            
            result = await db.execute(stmt)
            timestamps = result.scalars().all()
            
            if not timestamps:
                return []
            
            # Convert timestamps to dates and group into ranges
            dates = set()
            for timestamp in timestamps:
                timestamp_str = str(timestamp)
                if len(timestamp_str) >= 8:
                    try:
                        year = int(timestamp_str[0:4])
                        month = int(timestamp_str[4:6])
                        day = int(timestamp_str[6:8])
                        dates.add(date(year, month, day))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Invalid timestamp format: {timestamp_str}, error: {e}")
                        continue
            
            # Sort dates and create ranges
            sorted_dates = sorted(dates)
            if not sorted_dates:
                return []
            
            # Group consecutive dates into ranges
            ranges = []
            range_start = sorted_dates[0]
            range_end = sorted_dates[0]
            
            for current_date in sorted_dates[1:]:
                if current_date == range_end + timedelta(days=1):
                    # Extend current range
                    range_end = current_date
                else:
                    # Create new range
                    ranges.append(DateRange(range_start, range_end))
                    range_start = current_date
                    range_end = current_date
            
            # Add final range
            ranges.append(DateRange(range_start, range_end))
            
            return ranges
            
        except Exception as e:
            logger.error(f"Error getting scraped date ranges for domain {domain_id}: {e}")
            return []
    
    @staticmethod
    def _calculate_gap_priority(gap_days: int, gap_start: date) -> int:
        """Calculate priority score for a gap (1-10, higher is more urgent)"""
        # Base priority on gap size
        size_priority = min(8, gap_days // 7)  # 1 point per week, max 8
        
        # Recency bonus
        days_ago = (date.today() - gap_start).days
        if days_ago <= 30:
            recency_bonus = 2
        elif days_ago <= 90:
            recency_bonus = 1
        else:
            recency_bonus = 0
        
        return min(10, size_priority + recency_bonus)
    
    @staticmethod
    def _estimate_processing_time(gap_days: int) -> Dict[str, float]:
        """Estimate processing time for a gap"""
        # Rule-based estimation: ~1 minute per day for regular content
        base_minutes = gap_days * 1.5
        
        return {
            "estimated_minutes": base_minutes,
            "estimated_seconds": base_minutes * 60,
            "confidence": 0.4  # Low confidence for rule-based estimation
        }
    
    @staticmethod
    async def _analyze_content_changes(
        db: AsyncSession,
        domain_id: int,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Analyze content changes for content-based incremental scraping"""
        # This is a placeholder for more sophisticated content analysis
        # Could include:
        # - Checking for content updates in the date range
        # - Analyzing content change patterns
        # - Detecting high-activity periods
        
        return {
            "content_analysis": "placeholder",
            "change_indicators": [],
            "high_activity_periods": [],
            "analysis_confidence": 0.0
        }