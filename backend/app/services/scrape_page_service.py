"""
Service layer for scrape page operations
"""
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlmodel import select, and_, or_, func, desc, asc, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scraping import ScrapePage, ScrapePageStatus
from app.models.project import Domain, Project
from app.models.scrape_page_api import (
    ScrapePageQueryParams,
    ScrapePageFilterBy,
    ScrapePageSortBy,
    SortOrder,
    ScrapePageSummary,
    ScrapePageDetail,
    ScrapePageListResponse,
    ScrapePageStatistics,
    FilterAnalysis,
    ScrapePageAnalytics,
    ManualProcessingRequest,
    ManualProcessingResponse,
    BulkManualProcessingRequest,
    BulkOperationResult,
    BulkOperationPreview,
    BulkScrapePageAction,
    BulkScrapePageOperationStatus
)
from app.services.websocket_service import websocket_manager
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


class ScrapePageService:
    """Service for scrape page operations"""
    
    @staticmethod
    async def get_project_scrape_pages(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        query_params: ScrapePageQueryParams
    ) -> ScrapePageListResponse:
        """
        Get paginated list of scrape pages for a project with advanced filtering
        """
        
        # Verify project ownership
        project_stmt = select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise ValueError("Project not found or access denied")
        
        # Build base query
        base_query = select(ScrapePage).join(Domain).where(
            Domain.project_id == project_id
        )
        
        # Apply filters
        base_query = ScrapePageService._apply_filters(base_query, query_params)
        
        # Get total count
        count_query = select(func.count()).select_from(
            base_query.subquery()
        )
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply sorting
        base_query = ScrapePageService._apply_sorting(base_query, query_params)
        
        # Apply pagination
        offset = (query_params.page - 1) * query_params.limit
        base_query = base_query.offset(offset).limit(query_params.limit)
        
        # Execute query
        result = await db.execute(base_query)
        scrape_pages = result.scalars().all()
        
        # Convert to summary models
        page_summaries = [
            ScrapePageSummary.model_validate(page) for page in scrape_pages
        ]
        
        # Calculate pagination info
        total_pages = (total + query_params.limit - 1) // query_params.limit
        has_next = query_params.page < total_pages
        has_previous = query_params.page > 1
        
        return ScrapePageListResponse(
            pages=page_summaries,
            total=total,
            page=query_params.page,
            limit=query_params.limit,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous
        )
    
    @staticmethod
    def _apply_filters(query, params: ScrapePageQueryParams):
        """Apply filters to the scrape page query"""
        
        # Status-based filters
        if params.filter_by == ScrapePageFilterBy.PENDING:
            query = query.where(ScrapePage.status == ScrapePageStatus.PENDING)
        elif params.filter_by == ScrapePageFilterBy.IN_PROGRESS:
            query = query.where(ScrapePage.status == ScrapePageStatus.IN_PROGRESS)
        elif params.filter_by == ScrapePageFilterBy.COMPLETED:
            query = query.where(ScrapePage.status == ScrapePageStatus.COMPLETED)
        elif params.filter_by == ScrapePageFilterBy.FAILED:
            query = query.where(ScrapePage.status == ScrapePageStatus.FAILED)
        elif params.filter_by == ScrapePageFilterBy.RETRY:
            query = query.where(ScrapePage.status == ScrapePageStatus.RETRY)
        elif params.filter_by == ScrapePageFilterBy.SKIPPED:
            query = query.where(ScrapePage.status == ScrapePageStatus.SKIPPED)
        elif params.filter_by == ScrapePageFilterBy.FILTERED:
            # All filtered statuses
            filtered_statuses = [
                ScrapePageStatus.FILTERED_LIST_PAGE,
                ScrapePageStatus.FILTERED_ALREADY_PROCESSED,
                ScrapePageStatus.FILTERED_ATTACHMENT_DISABLED,
                ScrapePageStatus.FILTERED_FILE_EXTENSION,
                ScrapePageStatus.FILTERED_SIZE_TOO_SMALL,
                ScrapePageStatus.FILTERED_SIZE_TOO_LARGE,
                ScrapePageStatus.FILTERED_LOW_PRIORITY,
                ScrapePageStatus.FILTERED_CUSTOM_RULE,
            ]
            query = query.where(ScrapePage.status.in_(filtered_statuses))
        elif params.filter_by == ScrapePageFilterBy.MANUAL_REVIEW:
            query = query.where(ScrapePage.status == ScrapePageStatus.AWAITING_MANUAL_REVIEW)
        elif params.filter_by == ScrapePageFilterBy.MANUALLY_OVERRIDDEN:
            query = query.where(ScrapePage.is_manually_overridden is True)
        
        # Domain filter
        if params.domain_id is not None:
            query = query.where(ScrapePage.domain_id == params.domain_id)
        
        # Session filter
        if params.scrape_session_id is not None:
            query = query.where(ScrapePage.scrape_session_id == params.scrape_session_id)
        
        # Priority filters
        if params.priority_min is not None:
            query = query.where(ScrapePage.priority_score >= params.priority_min)
        if params.priority_max is not None:
            query = query.where(ScrapePage.priority_score <= params.priority_max)
        
        # Confidence filters
        if params.confidence_min is not None:
            query = query.where(ScrapePage.filter_confidence >= params.confidence_min)
        if params.confidence_max is not None:
            query = query.where(ScrapePage.filter_confidence <= params.confidence_max)
        
        # Content filters
        if params.has_content is not None:
            if params.has_content:
                query = query.where(ScrapePage.extracted_text.isnot(None))
            else:
                query = query.where(ScrapePage.extracted_text.is_(None))
        
        if params.is_pdf is not None:
            query = query.where(ScrapePage.is_pdf == params.is_pdf)
        
        if params.is_duplicate is not None:
            query = query.where(ScrapePage.is_duplicate == params.is_duplicate)
        
        if params.is_list_page is not None:
            query = query.where(ScrapePage.is_list_page == params.is_list_page)
        
        # Date filters
        if params.created_after is not None:
            query = query.where(ScrapePage.created_at >= params.created_after)
        if params.created_before is not None:
            query = query.where(ScrapePage.created_at <= params.created_before)
        if params.completed_after is not None:
            query = query.where(ScrapePage.completed_at >= params.completed_after)
        if params.completed_before is not None:
            query = query.where(ScrapePage.completed_at <= params.completed_before)
        
        # Search query
        if params.search_query:
            search_term = f"%{params.search_query}%"
            query = query.where(
                or_(
                    ScrapePage.title.ilike(search_term),
                    ScrapePage.original_url.ilike(search_term),
                    ScrapePage.extracted_text.ilike(search_term)
                )
            )
        
        # Manual processing filters
        if params.can_be_manually_processed is not None:
            query = query.where(ScrapePage.can_be_manually_processed == params.can_be_manually_processed)
        
        if params.is_manually_overridden is not None:
            query = query.where(ScrapePage.is_manually_overridden == params.is_manually_overridden)
        
        return query
    
    @staticmethod
    def _apply_sorting(query, params: ScrapePageQueryParams):
        """Apply sorting to the scrape page query"""
        
        # Determine sort column
        if params.sort_by == ScrapePageSortBy.CREATED_AT:
            sort_column = ScrapePage.created_at
        elif params.sort_by == ScrapePageSortBy.UPDATED_AT:
            sort_column = ScrapePage.updated_at
        elif params.sort_by == ScrapePageSortBy.PRIORITY_SCORE:
            sort_column = ScrapePage.priority_score
        elif params.sort_by == ScrapePageSortBy.CONTENT_LENGTH:
            sort_column = ScrapePage.content_length
        elif params.sort_by == ScrapePageSortBy.RETRY_COUNT:
            sort_column = ScrapePage.retry_count
        elif params.sort_by == ScrapePageSortBy.STATUS:
            sort_column = ScrapePage.status
        elif params.sort_by == ScrapePageSortBy.FILTER_CONFIDENCE:
            sort_column = ScrapePage.filter_confidence
        else:
            sort_column = ScrapePage.created_at
        
        # Apply sort direction
        if params.order == SortOrder.DESC:
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Add secondary sort by ID for consistent pagination
        query = query.order_by(desc(ScrapePage.id))
        
        return query
    
    @staticmethod
    async def get_scrape_page_detail(
        db: AsyncSession,
        project_id: int,
        page_id: int,
        user_id: int
    ) -> Optional[ScrapePageDetail]:
        """
        Get detailed information for a specific scrape page
        """
        
        # Verify project ownership and get page
        query = select(ScrapePage).join(Domain).where(
            and_(
                ScrapePage.id == page_id,
                Domain.project_id == project_id,
                Domain.project.has(Project.user_id == user_id)
            )
        )
        
        result = await db.execute(query)
        scrape_page = result.scalar_one_or_none()
        
        if not scrape_page:
            return None
        
        return ScrapePageDetail.model_validate(scrape_page)
    
    @staticmethod
    async def mark_pages_for_manual_processing(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        request: ManualProcessingRequest
    ) -> ManualProcessingResponse:
        """
        Mark scrape pages for manual processing
        """
        
        # Verify project ownership
        project_stmt = select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise ValueError("Project not found or access denied")
        
        # Get pages that belong to this project
        pages_query = select(ScrapePage).join(Domain).where(
            and_(
                ScrapePage.id.in_(request.page_ids),
                Domain.project_id == project_id
            )
        )
        
        result = await db.execute(pages_query)
        pages = result.scalars().all()
        
        processed_count = 0
        failed_count = 0
        failed_page_ids = []
        
        for page in pages:
            try:
                # Check if page can be manually processed
                if not page.can_be_manually_processed:
                    failed_count += 1
                    failed_page_ids.append(page.id)
                    continue
                
                # Update page status
                page.status = ScrapePageStatus.AWAITING_MANUAL_REVIEW
                page.is_manually_overridden = True
                page.original_filter_decision = page.filter_reason
                page.updated_at = datetime.utcnow()
                
                # Apply priority override if provided
                if request.priority_override is not None:
                    page.priority_score = request.priority_override
                
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to mark page {page.id} for manual processing: {e}")
                failed_count += 1
                failed_page_ids.append(page.id)
        
        await db.commit()
        
        # Send WebSocket notification
        try:
            await websocket_manager.broadcast_to_project(
                project_id=project_id,
                message={
                    "type": "manual_processing_marked",
                    "processed_count": processed_count,
                    "failed_count": failed_count,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")
        
        success = failed_count == 0
        message = f"Marked {processed_count} pages for manual processing"
        if failed_count > 0:
            message += f" ({failed_count} failed)"
        
        return ManualProcessingResponse(
            success=success,
            message=message,
            processed_count=processed_count,
            failed_count=failed_count,
            failed_page_ids=failed_page_ids
        )
    
    @staticmethod
    async def process_manually_marked_pages(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        request: ManualProcessingRequest
    ) -> ManualProcessingResponse:
        """
        Process manually marked pages by queuing them for scraping
        """
        
        # Verify project ownership
        project_stmt = select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise ValueError("Project not found or access denied")
        
        # Get pages that are marked for manual review
        pages_query = select(ScrapePage).join(Domain).where(
            and_(
                ScrapePage.id.in_(request.page_ids),
                Domain.project_id == project_id,
                or_(
                    ScrapePage.status == ScrapePageStatus.AWAITING_MANUAL_REVIEW,
                    and_(request.force_reprocess, ScrapePage.is_manually_overridden is True)
                )
            )
        )
        
        result = await db.execute(pages_query)
        pages = result.scalars().all()
        
        processed_count = 0
        failed_count = 0
        failed_page_ids = []
        task_ids = []
        
        for page in pages:
            try:
                # Update page status to pending for reprocessing
                page.status = ScrapePageStatus.PENDING
                page.retry_count = 0
                page.error_message = None
                page.error_type = None
                page.last_attempt_at = None
                page.updated_at = datetime.utcnow()
                
                # Queue scraping task
                task_result = celery_app.send_task(
                    'app.tasks.firecrawl_scraping.process_single_scrape_page',
                    args=[page.id],
                    kwargs={'manual_processing': True}
                )
                task_ids.append(task_result.id)
                
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process page {page.id}: {e}")
                failed_count += 1
                failed_page_ids.append(page.id)
        
        await db.commit()
        
        # Send WebSocket notification
        try:
            await websocket_manager.broadcast_to_project(
                project_id=project_id,
                message={
                    "type": "manual_processing_started",
                    "processed_count": processed_count,
                    "failed_count": failed_count,
                    "task_ids": task_ids,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")
        
        success = failed_count == 0
        message = f"Started processing {processed_count} pages"
        if failed_count > 0:
            message += f" ({failed_count} failed)"
        
        return ManualProcessingResponse(
            success=success,
            message=message,
            processed_count=processed_count,
            failed_count=failed_count,
            failed_page_ids=failed_page_ids,
            task_id=task_ids[0] if task_ids else None  # Return first task ID
        )
    
    @staticmethod
    async def get_scrape_page_statistics(
        db: AsyncSession,
        project_id: int,
        user_id: int
    ) -> ScrapePageStatistics:
        """
        Get comprehensive statistics for scrape pages in a project
        """
        
        # Verify project ownership
        project_stmt = select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise ValueError("Project not found or access denied")
        
        # Base query for project pages
        base_query = select(ScrapePage).join(Domain).where(Domain.project_id == project_id)
        
        # Total count
        total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
        total_pages = total_result.scalar()
        
        # Status counts
        status_query = select(
            ScrapePage.status,
            func.count().label('count')
        ).join(Domain).where(Domain.project_id == project_id).group_by(ScrapePage.status)
        
        status_result = await db.execute(status_query)
        status_counts = {str(status): count for status, count in status_result.all()}
        
        # Filter category counts
        filter_category_query = select(
            ScrapePage.filter_category,
            func.count().label('count')
        ).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.filter_category.isnot(None))
        ).group_by(ScrapePage.filter_category)
        
        filter_result = await db.execute(filter_category_query)
        filter_category_counts = {category or 'unknown': count for category, count in filter_result.all()}
        
        # Priority distribution
        priority_query = select(
            ScrapePage.priority_score,
            func.count().label('count')
        ).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.priority_score.isnot(None))
        ).group_by(ScrapePage.priority_score)
        
        priority_result = await db.execute(priority_query)
        priority_distribution = {int(priority or 0): count for priority, count in priority_result.all()}
        
        # Performance metrics
        perf_query = select(
            func.avg(ScrapePage.total_processing_time).label('avg_processing_time'),
            func.avg(ScrapePage.content_length).label('avg_content_length')
        ).join(Domain).where(Domain.project_id == project_id)
        
        perf_result = await db.execute(perf_query)
        perf_data = perf_result.first()
        
        # Calculate quality metrics
        completed_count = status_counts.get('completed', 0)
        status_counts.get('failed', 0)
        retry_count = status_counts.get('retry', 0)
        
        # Count filtered statuses
        filtered_statuses = [
            'filtered_list_page', 'filtered_already_processed',
            'filtered_attachment_disabled', 'filtered_file_extension',
            'filtered_size_too_small', 'filtered_size_too_large',
            'filtered_low_priority', 'filtered_custom_rule'
        ]
        filtered_count = sum(status_counts.get(status, 0) for status in filtered_statuses)
        
        success_rate = (completed_count / max(total_pages, 1)) * 100
        retry_rate = (retry_count / max(total_pages, 1)) * 100
        filter_rate = (filtered_count / max(total_pages, 1)) * 100
        
        # Manual processing stats
        manual_review_count = status_counts.get('awaiting_manual_review', 0)
        
        manual_override_query = select(func.count()).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.is_manually_overridden is True)
        )
        manual_override_result = await db.execute(manual_override_query)
        manually_overridden = manual_override_result.scalar()
        
        can_process_query = select(func.count()).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.can_be_manually_processed is True)
        )
        can_process_result = await db.execute(can_process_query)
        can_be_manually_processed = can_process_result.scalar()
        
        # Time-based stats
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(weeks=1)
        month_ago = now - timedelta(days=30)
        
        pages_24h_query = select(func.count()).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.created_at >= day_ago)
        )
        pages_24h_result = await db.execute(pages_24h_query)
        pages_last_24h = pages_24h_result.scalar()
        
        pages_week_query = select(func.count()).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.created_at >= week_ago)
        )
        pages_week_result = await db.execute(pages_week_query)
        pages_last_week = pages_week_result.scalar()
        
        pages_month_query = select(func.count()).join(Domain).where(
            and_(Domain.project_id == project_id, ScrapePage.created_at >= month_ago)
        )
        pages_month_result = await db.execute(pages_month_query)
        pages_last_month = pages_month_result.scalar()
        
        return ScrapePageStatistics(
            total_pages=total_pages,
            status_counts=status_counts,
            filter_category_counts=filter_category_counts,
            priority_distribution=priority_distribution,
            average_processing_time=float(perf_data.avg_processing_time or 0),
            average_content_length=float(perf_data.avg_content_length or 0),
            success_rate=success_rate,
            retry_rate=retry_rate,
            filter_rate=filter_rate,
            manual_review_pending=manual_review_count,
            manually_overridden=manually_overridden,
            can_be_manually_processed=can_be_manually_processed,
            pages_last_24h=pages_last_24h,
            pages_last_week=pages_last_week,
            pages_last_month=pages_last_month
        )
    
    @staticmethod
    async def get_scrape_page_analytics(
        db: AsyncSession,
        project_id: int,
        user_id: int
    ) -> ScrapePageAnalytics:
        """
        Get comprehensive analytics for scrape pages in a project
        """
        
        # Get basic statistics
        basic_stats = await ScrapePageService.get_scrape_page_statistics(
            db, project_id, user_id
        )
        
        # Get filter analysis
        filter_analysis = await ScrapePageService._get_filter_analysis(
            db, project_id
        )
        
        # Get time series data (last 30 days)
        daily_stats = await ScrapePageService._get_daily_stats(
            db, project_id
        )
        
        # Get domain performance
        domain_performance = await ScrapePageService._get_domain_performance(
            db, project_id
        )
        
        return ScrapePageAnalytics(
            basic_stats=basic_stats,
            filter_analysis=filter_analysis,
            daily_stats=daily_stats,
            domain_performance=domain_performance
        )
    
    @staticmethod
    async def _get_filter_analysis(
        db: AsyncSession,
        project_id: int
    ) -> FilterAnalysis:
        """Get detailed filter analysis"""
        
        # Base filtered pages query
        filtered_query = select(ScrapePage).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                ScrapePage.filter_reason.isnot(None)
            )
        )
        
        # Total filtered count
        total_filtered_result = await db.execute(select(func.count()).select_from(filtered_query.subquery()))
        total_filtered = total_filtered_result.scalar()
        
        # Filter categories
        category_query = select(
            ScrapePage.filter_category,
            func.count().label('count')
        ).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                ScrapePage.filter_category.isnot(None)
            )
        ).group_by(ScrapePage.filter_category)
        
        category_result = await db.execute(category_query)
        filter_categories = {category: count for category, count in category_result.all()}
        
        # Filter reasons
        reason_query = select(
            ScrapePage.filter_reason,
            func.count().label('count')
        ).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                ScrapePage.filter_reason.isnot(None)
            )
        ).group_by(ScrapePage.filter_reason)
        
        reason_result = await db.execute(reason_query)
        filter_reasons = {reason: count for reason, count in reason_result.all()}
        
        # Confidence distribution
        confidence_query = select(
            case(
                (ScrapePage.filter_confidence < 0.2, '0.0-0.2'),
                (ScrapePage.filter_confidence < 0.4, '0.2-0.4'),
                (ScrapePage.filter_confidence < 0.6, '0.4-0.6'),
                (ScrapePage.filter_confidence < 0.8, '0.6-0.8'),
                else_='0.8-1.0'
            ).label('confidence_range'),
            func.count().label('count')
        ).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                ScrapePage.filter_confidence.isnot(None)
            )
        ).group_by(text('confidence_range'))
        
        confidence_result = await db.execute(confidence_query)
        confidence_distribution = {range_name: count for range_name, count in confidence_result.all()}
        
        # Manual overrides
        override_query = select(func.count()).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                ScrapePage.is_manually_overridden is True
            )
        )
        override_result = await db.execute(override_query)
        manual_overrides = override_result.scalar()
        
        # Override success rate
        override_success_query = select(func.count()).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                ScrapePage.is_manually_overridden is True,
                ScrapePage.status == ScrapePageStatus.COMPLETED
            )
        )
        override_success_result = await db.execute(override_success_query)
        override_successes = override_success_result.scalar()
        
        override_success_rate = (override_successes / max(manual_overrides, 1)) * 100
        
        return FilterAnalysis(
            total_filtered=total_filtered,
            filter_categories=filter_categories,
            filter_reasons=filter_reasons,
            confidence_distribution=confidence_distribution,
            manual_overrides=manual_overrides,
            override_success_rate=override_success_rate
        )
    
    @staticmethod
    async def _get_daily_stats(
        db: AsyncSession,
        project_id: int
    ) -> List[Dict[str, Any]]:
        """Get daily statistics for the last 30 days"""
        
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=30)
        
        # Daily stats query
        daily_query = select(
            func.date(ScrapePage.created_at).label('date'),
            func.count(case((ScrapePage.status == ScrapePageStatus.COMPLETED, 1))).label('completed'),
            func.count(case((ScrapePage.status == ScrapePageStatus.FAILED, 1))).label('failed'),
            func.count(case((ScrapePage.filter_reason.isnot(None), 1))).label('filtered')
        ).join(Domain).where(
            and_(
                Domain.project_id == project_id,
                func.date(ScrapePage.created_at) >= start_date,
                func.date(ScrapePage.created_at) <= end_date
            )
        ).group_by(func.date(ScrapePage.created_at))
        
        daily_result = await db.execute(daily_query)
        
        daily_stats = []
        for date, completed, failed, filtered in daily_result.all():
            daily_stats.append({
                "date": date.isoformat(),
                "completed": completed,
                "failed": failed,
                "filtered": filtered
            })
        
        return daily_stats
    
    @staticmethod
    async def _get_domain_performance(
        db: AsyncSession,
        project_id: int
    ) -> Dict[int, Dict[str, Any]]:
        """Get performance statistics by domain"""
        
        domain_query = select(
            Domain.id,
            func.count(ScrapePage.id).label('total_pages'),
            func.count(case((ScrapePage.status == ScrapePageStatus.COMPLETED, 1))).label('completed'),
            func.avg(ScrapePage.total_processing_time).label('avg_processing_time')
        ).join(ScrapePage).where(
            Domain.project_id == project_id
        ).group_by(Domain.id)
        
        domain_result = await db.execute(domain_query)
        
        domain_performance = {}
        for domain_id, total, completed, avg_time in domain_result.all():
            success_rate = (completed / max(total, 1)) * 100
            domain_performance[domain_id] = {
                "total_pages": total,
                "completed_pages": completed,
                "success_rate": success_rate,
                "avg_processing_time": float(avg_time or 0)
            }
        
        return domain_performance
    
    @staticmethod
    async def preview_bulk_operation(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        request: BulkManualProcessingRequest
    ) -> BulkOperationPreview:
        """
        Preview what a bulk operation would affect before executing it
        """
        # Verify project ownership
        project_stmt = select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise ValueError("Project not found or access denied")
        
        # Build query with filters to find affected pages
        base_query = select(ScrapePage).join(Domain).where(Domain.project_id == project_id)
        base_query = ScrapePageService._apply_filters(base_query, request.filters)
        
        # Apply max pages limit
        base_query = base_query.limit(request.max_pages)
        
        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total_pages_affected = total_result.scalar()
        
        # Get sample pages (first 10)
        sample_query = base_query.limit(10)
        sample_result = await db.execute(sample_query)
        sample_pages = [
            ScrapePageSummary.model_validate(page) for page in sample_result.scalars().all()
        ]
        
        # Get status distribution
        status_query = select(
            ScrapePage.status,
            func.count().label('count')
        ).select_from(base_query.subquery()).group_by(ScrapePage.status)
        status_result = await db.execute(status_query)
        pages_by_status = {str(status): count for status, count in status_result.all()}
        
        # Get domain distribution
        domain_query = select(
            ScrapePage.domain_id,
            func.count().label('count')
        ).select_from(base_query.subquery()).group_by(ScrapePage.domain_id)
        domain_result = await db.execute(domain_query)
        pages_by_domain = {domain_id: count for domain_id, count in domain_result.all()}
        
        # Calculate warnings and blocked pages
        warnings = []
        blocked_page_ids = []
        blocked_reasons = {}
        
        if total_pages_affected == 0:
            warnings.append("No pages match the specified filters")
        elif total_pages_affected > 5000:
            warnings.append(f"Large operation affecting {total_pages_affected} pages - consider more specific filters")
        
        # Check for destructive operations
        if request.action in [BulkScrapePageAction.DELETE]:
            warnings.append("This is a destructive operation that cannot be undone")
        
        # Estimate processing time (rough estimate)
        estimated_time = None
        if request.action in [BulkScrapePageAction.MARK_FOR_PROCESSING, BulkScrapePageAction.RETRY]:
            # Processing operations take longer
            estimated_time = max(0.1, total_pages_affected * 0.02)  # ~1.2 minutes per 1000 pages
        else:
            # Status updates are faster
            estimated_time = max(0.1, total_pages_affected * 0.001)  # ~0.06 minutes per 1000 pages
        
        return BulkOperationPreview(
            action=request.action,
            total_pages_affected=total_pages_affected,
            pages_by_status=pages_by_status,
            pages_by_domain=pages_by_domain,
            estimated_processing_time_minutes=estimated_time,
            sample_pages=sample_pages,
            warnings=warnings,
            blocked_page_ids=blocked_page_ids,
            blocked_reasons=blocked_reasons
        )
    
    @staticmethod
    async def execute_bulk_operation(
        db: AsyncSession,
        project_id: int,
        user_id: int,
        request: BulkManualProcessingRequest
    ) -> BulkOperationResult:
        """
        Execute bulk operations on scrape pages with progress tracking
        """
        # Verify project ownership
        project_stmt = select(Project).where(
            and_(Project.id == project_id, Project.user_id == user_id)
        )
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise ValueError("Project not found or access denied")
        
        # Generate operation ID
        operation_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        
        # Initialize result
        result = BulkOperationResult(
            operation_id=operation_id,
            action=request.action,
            status=BulkScrapePageOperationStatus.RUNNING,
            total_requested=0,
            total_processed=0,
            successful_count=0,
            failed_count=0,
            skipped_count=0,
            started_at=started_at,
            dry_run=request.dry_run,
            reason=request.reason,
            filters_used=request.filters.dict()
        )
        
        try:
            # Build query to find affected pages
            base_query = select(ScrapePage).join(Domain).where(Domain.project_id == project_id)
            base_query = ScrapePageService._apply_filters(base_query, request.filters)
            base_query = base_query.limit(request.max_pages)
            
            # Get all pages to process
            pages_result = await db.execute(base_query)
            pages = list(pages_result.scalars().all())
            
            result.total_requested = len(pages)
            
            if result.total_requested == 0:
                result.status = BulkScrapePageOperationStatus.COMPLETED
                result.completed_at = datetime.utcnow()
                result.duration_seconds = 0.0
                return result
            
            # If dry run, just return preview
            if request.dry_run:
                result.status = BulkScrapePageOperationStatus.COMPLETED
                result.completed_at = datetime.utcnow()
                result.duration_seconds = 0.0
                result.successful_page_ids = [page.id for page in pages]
                result.successful_count = len(pages)
                return result
            
            # Process in batches
            batch_size = min(request.batch_size, 500)
            task_ids = []
            
            for i in range(0, len(pages), batch_size):
                batch_pages = pages[i:i + batch_size]
                
                for page in batch_pages:
                    try:
                        success = await ScrapePageService._execute_single_page_action(
                            db, page, request.action, request
                        )
                        
                        if success:
                            result.successful_page_ids.append(page.id)
                            result.successful_count += 1
                            
                            # Queue task if needed
                            if request.action in [BulkScrapePageAction.MARK_FOR_PROCESSING, BulkScrapePageAction.RETRY]:
                                task_result = celery_app.send_task(
                                    'app.tasks.firecrawl_scraping.process_single_scrape_page',
                                    args=[page.id],
                                    kwargs={'manual_processing': True}
                                )
                                task_ids.append(task_result.id)
                        else:
                            result.failed_page_ids.append(page.id)
                            result.failed_count += 1
                            result.failed_reasons[page.id] = "Operation failed"
                            
                    except Exception as e:
                        logger.error(f"Failed to process page {page.id}: {e}")
                        result.failed_page_ids.append(page.id)
                        result.failed_count += 1
                        result.failed_reasons[page.id] = str(e)
                
                # Commit batch
                await db.commit()
            
            result.total_processed = result.successful_count + result.failed_count
            result.task_ids = task_ids
            result.status = (
                BulkScrapePageOperationStatus.COMPLETED if result.failed_count == 0
                else BulkScrapePageOperationStatus.PARTIALLY_COMPLETED
            )
            result.completed_at = datetime.utcnow()
            result.duration_seconds = (result.completed_at - started_at).total_seconds()
            
            # Send WebSocket notification
            try:
                await websocket_manager.broadcast_to_project(
                    project_id=project_id,
                    message={
                        "type": "bulk_operation_completed",
                        "operation_id": operation_id,
                        "action": request.action.value,
                        "successful_count": result.successful_count,
                        "failed_count": result.failed_count,
                        "task_ids": task_ids,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send WebSocket notification: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Bulk operation {operation_id} failed: {e}")
            result.status = BulkScrapePageOperationStatus.FAILED
            result.completed_at = datetime.utcnow()
            result.duration_seconds = (result.completed_at - started_at).total_seconds() if result.completed_at else 0
            raise
    
    @staticmethod
    async def _execute_single_page_action(
        db: AsyncSession,
        page: ScrapePage,
        action: BulkScrapePageAction,
        request: BulkManualProcessingRequest
    ) -> bool:
        """
        Execute a single action on a scrape page
        """
        try:
            if action == BulkScrapePageAction.MARK_FOR_PROCESSING:
                # Mark for manual processing
                if page.status in [ScrapePageStatus.FILTERED_LIST_PAGE, 
                                 ScrapePageStatus.FILTERED_ALREADY_PROCESSED,
                                 ScrapePageStatus.FILTERED_LOW_PRIORITY]:
                    page.status = ScrapePageStatus.AWAITING_MANUAL_REVIEW
                    page.is_manually_overridden = True
                    # Store reason in filter_details if provided
                    if request.reason:
                        if not page.filter_details:
                            page.filter_details = {}
                        page.filter_details['manual_review_reason'] = request.reason
                    if request.priority_override is not None:
                        page.priority_score = request.priority_override
                    page.updated_at = datetime.utcnow()
                    return True
                return False
            
            elif action == BulkScrapePageAction.APPROVE_ALL:
                # Approve pages for processing
                if page.status == ScrapePageStatus.AWAITING_MANUAL_REVIEW:
                    page.status = ScrapePageStatus.PENDING
                    page.is_manually_overridden = True
                    page.retry_count = 0
                    page.error_message = None
                    page.error_type = None
                    page.last_attempt_at = None
                    page.updated_at = datetime.utcnow()
                    return True
                return False
            
            elif action == BulkScrapePageAction.SKIP_ALL:
                # Skip pages
                if page.status in [ScrapePageStatus.PENDING, ScrapePageStatus.AWAITING_MANUAL_REVIEW]:
                    page.status = ScrapePageStatus.MANUALLY_SKIPPED
                    # Store reason in filter_details if provided
                    if request.reason:
                        if not page.filter_details:
                            page.filter_details = {}
                        page.filter_details['skip_reason'] = request.reason
                    else:
                        if not page.filter_details:
                            page.filter_details = {}
                        page.filter_details['skip_reason'] = "Bulk skip operation"
                    page.updated_at = datetime.utcnow()
                    return True
                return False
            
            elif action == BulkScrapePageAction.RETRY:
                # Retry failed pages
                if page.status in [ScrapePageStatus.FAILED, ScrapePageStatus.RETRY]:
                    page.status = ScrapePageStatus.PENDING
                    page.retry_count = 0
                    page.error_message = None
                    page.error_type = None
                    page.last_attempt_at = None
                    page.updated_at = datetime.utcnow()
                    return True
                return False
            
            elif action == BulkScrapePageAction.RESET_STATUS:
                # Reset to pending
                if request.new_status:
                    page.status = request.new_status
                else:
                    page.status = ScrapePageStatus.PENDING
                page.retry_count = 0
                page.error_message = None
                page.error_type = None
                page.last_attempt_at = None
                page.updated_at = datetime.utcnow()
                return True
            
            elif action == BulkScrapePageAction.UPDATE_PRIORITY:
                # Update priority
                if request.priority_override is not None:
                    page.priority_score = request.priority_override
                    page.updated_at = datetime.utcnow()
                    return True
                return False
            
            elif action == BulkScrapePageAction.DELETE:
                # Delete pages (this would need special handling)
                # Note: We might want to soft-delete or move to archive table
                await db.delete(page)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to execute action {action} on page {page.id}: {e}")
            return False