"""
Enhanced project creation service with intelligent page discovery and deduplication

This service implements the new shared pages architecture with:
- CDX discovery with intelligent deduplication
- Real-time progress updates via WebSocket
- Page sharing detection and reuse
- Optimized project setup
"""
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from sqlmodel import Session, select

from app.models.project import Project, Domain, ProjectCreate, DomainCreate
from app.models.shared_pages import ProcessingStats
from app.models.user import User
from app.services.cdx_deduplication_service import EnhancedCDXService, CDXRecord
from app.services.wayback_machine import CDXAPIClient
from app.services.intelligent_filter import IntelligentContentFilter
from app.services.websocket_service import WebSocketService
from app.services.page_access_control import PageAccessControl

logger = logging.getLogger(__name__)


class EnhancedProjectCreationService:
    """Enhanced project creation with shared pages support"""
    
    def __init__(
        self,
        db: Session,
        cdx_service: EnhancedCDXService,
        wayback_service: CDXAPIClient,
        websocket_service: WebSocketService,
        access_control: PageAccessControl
    ):
        self.db = db
        self.cdx_service = cdx_service
        self.wayback_service = wayback_service
        self.websocket_service = websocket_service
        self.access_control = access_control
        self.content_filter = IntelligentContentFilter()
    
    async def create_project_with_domains(
        self,
        user_id: int,
        project_data: ProjectCreate,
        domain_urls: List[str],
        discovery_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create project with intelligent page discovery and deduplication
        
        Args:
            user_id: User creating the project
            project_data: Project configuration
            domain_urls: List of domain URLs to scrape
            discovery_options: Optional CDX discovery settings
            
        Returns:
            Dictionary with project creation results and statistics
        """
        logger.info(f"Creating project for user {user_id} with {len(domain_urls)} domains")
        
        try:
            # Create project
            project = Project(
                user_id=user_id,
                name=project_data.name,
                description=project_data.description,
                process_documents=project_data.process_documents,
                enable_attachment_download=project_data.enable_attachment_download,
                langextract_enabled=project_data.langextract_enabled,
                langextract_provider=project_data.langextract_provider,
                langextract_model=project_data.langextract_model,
                langextract_estimated_cost_per_1k=project_data.langextract_estimated_cost_per_1k,
                config=project_data.config or {}
            )
            
            self.db.add(project)
            await self.db.flush()  # Get project ID
            
            logger.info(f"Created project {project.id}: {project.name}")
            
            # Send initial WebSocket update
            await self.websocket_service.send_project_update(
                user_id,
                {
                    "type": "project_created",
                    "project_id": project.id,
                    "project_name": project.name,
                    "domains_to_process": len(domain_urls),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            # Process each domain with intelligent discovery
            total_stats = ProcessingStats()
            domain_results = []
            
            for i, domain_url in enumerate(domain_urls):
                logger.info(f"Processing domain {i+1}/{len(domain_urls)}: {domain_url}")
                
                # Send progress update
                await self.websocket_service.send_project_update(
                    user_id,
                    {
                        "type": "domain_processing_started",
                        "project_id": project.id,
                        "domain_url": domain_url,
                        "progress": {
                            "current": i + 1,
                            "total": len(domain_urls)
                        }
                    }
                )
                
                try:
                    # Create domain
                    domain = Domain(
                        project_id=project.id,
                        domain_name=domain_url,
                        match_type="domain",  # Default match type
                        active=True
                    )
                    self.db.add(domain)
                    await self.db.flush()
                    
                    # Discover and process pages with deduplication
                    domain_stats = await self._process_domain_with_deduplication(
                        project.id, domain.id, domain_url, user_id, discovery_options
                    )
                    
                    total_stats.pages_linked += domain_stats.pages_linked
                    total_stats.pages_to_scrape += domain_stats.pages_to_scrape
                    total_stats.pages_already_processing += domain_stats.pages_already_processing
                    total_stats.total_processed += domain_stats.total_processed
                    
                    domain_results.append({
                        "domain_url": domain_url,
                        "domain_id": domain.id,
                        "stats": domain_stats.dict(),
                        "success": True
                    })
                    
                    # Send domain completion update
                    await self.websocket_service.send_project_update(
                        user_id,
                        {
                            "type": "domain_completed",
                            "project_id": project.id,
                            "domain_url": domain_url,
                            "domain_id": domain.id,
                            "stats": domain_stats.dict(),
                            "efficiency_improvement": self._calculate_efficiency_improvement(domain_stats)
                        }
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to process domain {domain_url}: {e}")
                    domain_results.append({
                        "domain_url": domain_url,
                        "domain_id": None,
                        "error": str(e),
                        "success": False
                    })
                    
                    # Send error update
                    await self.websocket_service.send_project_update(
                        user_id,
                        {
                            "type": "domain_error",
                            "project_id": project.id,
                            "domain_url": domain_url,
                            "error": str(e)
                        }
                    )
            
            await self.db.commit()
            
            # Send final completion update
            completion_summary = {
                "type": "project_creation_completed",
                "project_id": project.id,
                "project_name": project.name,
                "total_stats": total_stats.dict(),
                "domain_results": domain_results,
                "efficiency_metrics": self._calculate_project_efficiency_metrics(total_stats),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.websocket_service.send_project_update(user_id, completion_summary)
            
            # Log final summary
            logger.info(
                f"Project {project.id} creation completed: "
                f"{total_stats.pages_linked} existing pages linked, "
                f"{total_stats.pages_to_scrape} new pages queued for scraping, "
                f"{total_stats.pages_already_processing} pages already processing"
            )
            
            return {
                "success": True,
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "user_id": user_id
                },
                "stats": total_stats.dict(),
                "domain_results": domain_results,
                "efficiency_metrics": self._calculate_project_efficiency_metrics(total_stats)
            }
            
        except Exception as e:
            logger.error(f"Project creation failed: {e}")
            
            # Rollback database changes
            await self.db.rollback()
            
            # Send error notification
            await self.websocket_service.send_project_update(
                user_id,
                {
                    "type": "project_creation_failed",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            raise
    
    async def _process_domain_with_deduplication(
        self,
        project_id: int,
        domain_id: int,
        domain_url: str,
        user_id: int,
        discovery_options: Optional[Dict[str, Any]] = None
    ) -> ProcessingStats:
        """Process domain with CDX discovery and intelligent deduplication"""
        
        # Send discovery start notification
        await self.websocket_service.send_project_update(
            user_id,
            {
                "type": "cdx_discovery_started",
                "project_id": project_id,
                "domain_id": domain_id,
                "domain_url": domain_url
            }
        )
        
        # Configure CDX discovery options
        options = discovery_options or {}
        max_pages = options.get("max_pages", 10000)
        date_range = options.get("date_range")
        
        try:
            # Discover pages via CDX API
            logger.info(f"Discovering pages for domain {domain_url}")
            
            cdx_records = await self.wayback_service.fetch_cdx_records(
                domain_url,
                limit=max_pages,
                from_date=date_range.get("from") if date_range else None,
                to_date=date_range.get("to") if date_range else None
            )
            
            logger.info(f"CDX API returned {len(cdx_records)} records for {domain_url}")
            
            # Send discovery progress update
            await self.websocket_service.send_project_update(
                user_id,
                {
                    "type": "cdx_discovery_completed",
                    "project_id": project_id,
                    "domain_id": domain_id,
                    "domain_url": domain_url,
                    "raw_records_found": len(cdx_records)
                }
            )
            
            # Apply intelligent filtering
            if cdx_records:
                logger.info(f"Applying intelligent filtering to {len(cdx_records)} records")
                
                filtered_records, filter_stats = await self.content_filter.filter_records(
                    cdx_records,
                    project_id=project_id
                )
                
                logger.info(
                    f"Intelligent filtering: {len(cdx_records)} → {len(filtered_records)} records "
                    f"({filter_stats.get('filtered_count', 0)} filtered out)"
                )
                
                # Send filtering update
                await self.websocket_service.send_project_update(
                    user_id,
                    {
                        "type": "intelligent_filtering_completed",
                        "project_id": project_id,
                        "domain_id": domain_id,
                        "domain_url": domain_url,
                        "before_filtering": len(cdx_records),
                        "after_filtering": len(filtered_records),
                        "filter_stats": filter_stats
                    }
                )
                
                cdx_records = filtered_records
            
            # Convert to CDXRecord objects
            cdx_record_objects = [
                CDXRecord(
                    url=record.get("original_url") or record.get("url"),
                    timestamp=record.get("timestamp"),
                    wayback_url=record.get("wayback_url")
                )
                for record in cdx_records
            ]
            
            # Process with deduplication
            logger.info(f"Processing {len(cdx_record_objects)} records with deduplication")
            
            await self.websocket_service.send_project_update(
                user_id,
                {
                    "type": "deduplication_started",
                    "project_id": project_id,
                    "domain_id": domain_id,
                    "domain_url": domain_url,
                    "records_to_process": len(cdx_record_objects)
                }
            )
            
            stats = await self.cdx_service.process_cdx_results(
                cdx_record_objects,
                project_id,
                domain_id
            )
            
            # Send deduplication completion update
            await self.websocket_service.send_project_update(
                user_id,
                {
                    "type": "deduplication_completed",
                    "project_id": project_id,
                    "domain_id": domain_id,
                    "domain_url": domain_url,
                    "stats": stats.dict(),
                    "efficiency_improvement": self._calculate_efficiency_improvement(stats)
                }
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Domain processing failed for {domain_url}: {e}")
            
            # Send error update
            await self.websocket_service.send_project_update(
                user_id,
                {
                    "type": "domain_processing_error",
                    "project_id": project_id,
                    "domain_id": domain_id,
                    "domain_url": domain_url,
                    "error": str(e)
                }
            )
            
            raise
    
    def _calculate_efficiency_improvement(self, stats: ProcessingStats) -> Dict[str, Any]:
        """Calculate efficiency improvement metrics from deduplication"""
        total_would_scrape = stats.pages_linked + stats.pages_to_scrape
        
        if total_would_scrape == 0:
            return {
                "scraping_reduction_percentage": 0,
                "pages_saved": 0,
                "estimated_time_saved_hours": 0
            }
        
        scraping_reduction = (stats.pages_linked / total_would_scrape) * 100
        estimated_time_per_page = 10  # seconds
        time_saved_seconds = stats.pages_linked * estimated_time_per_page
        time_saved_hours = time_saved_seconds / 3600
        
        return {
            "scraping_reduction_percentage": round(scraping_reduction, 2),
            "pages_saved": stats.pages_linked,
            "estimated_time_saved_hours": round(time_saved_hours, 2),
            "api_calls_saved": stats.pages_linked,
            "storage_efficiency": "Shared across projects"
        }
    
    def _calculate_project_efficiency_metrics(self, total_stats: ProcessingStats) -> Dict[str, Any]:
        """Calculate overall project efficiency metrics"""
        total_pages = total_stats.total_processed
        
        if total_pages == 0:
            return {
                "overall_efficiency": 0,
                "sharing_potential": "No pages processed",
                "resource_optimization": 0
            }
        
        efficiency_score = (total_stats.pages_linked / total_pages) * 100
        
        return {
            "overall_efficiency_percentage": round(efficiency_score, 2),
            "total_pages_discovered": total_pages,
            "existing_pages_reused": total_stats.pages_linked,
            "new_pages_queued": total_stats.pages_to_scrape,
            "pages_already_processing": total_stats.pages_already_processing,
            "sharing_potential": "High" if efficiency_score > 50 else "Medium" if efficiency_score > 20 else "Low",
            "resource_optimization_level": "Excellent" if efficiency_score > 60 else "Good" if efficiency_score > 30 else "Standard"
        }
    
    async def get_project_creation_templates(self, user_id: int) -> List[Dict[str, Any]]:
        """Get project creation templates based on user history and common patterns"""
        
        # Get user's previous projects for pattern analysis
        user_projects = await self.db.execute(
            select(Project).where(Project.user_id == user_id).limit(10)
        )
        projects = user_projects.scalars().all()
        
        templates = [
            {
                "name": "News Monitoring",
                "description": "Monitor news sites for specific topics",
                "suggested_domains": ["reuters.com", "bbc.com", "cnn.com"],
                "config": {
                    "process_documents": True,
                    "enable_attachment_download": False,
                    "langextract_enabled": True
                },
                "discovery_options": {
                    "max_pages": 5000,
                    "date_range": {"days_back": 90}
                }
            },
            {
                "name": "Research Archive",
                "description": "Comprehensive academic and research content",
                "suggested_domains": ["arxiv.org", "scholar.google.com"],
                "config": {
                    "process_documents": True,
                    "enable_attachment_download": True,
                    "langextract_enabled": True
                },
                "discovery_options": {
                    "max_pages": 10000,
                    "date_range": {"days_back": 365}
                }
            },
            {
                "name": "Government Monitoring",
                "description": "Track government websites and policy documents",
                "suggested_domains": ["gov.uk", "whitehouse.gov", "europa.eu"],
                "config": {
                    "process_documents": True,
                    "enable_attachment_download": True,
                    "langextract_enabled": True
                },
                "discovery_options": {
                    "max_pages": 15000,
                    "date_range": {"days_back": 730}
                }
            }
        ]
        
        # Customize templates based on user history
        if projects:
            common_configs = self._analyze_user_preferences(projects)
            for template in templates:
                template["config"].update(common_configs)
        
        return templates
    
    def _analyze_user_preferences(self, projects: List[Project]) -> Dict[str, Any]:
        """Analyze user's project preferences to suggest better defaults"""
        
        if not projects:
            return {}
        
        # Analyze common settings
        langextract_usage = sum(1 for p in projects if p.langextract_enabled) / len(projects)
        attachment_usage = sum(1 for p in projects if p.enable_attachment_download) / len(projects)
        doc_processing = sum(1 for p in projects if p.process_documents) / len(projects)
        
        # Common LangExtract provider
        providers = [p.langextract_provider for p in projects if p.langextract_provider]
        common_provider = max(set(providers), key=providers.count) if providers else None
        
        return {
            "langextract_enabled": langextract_usage > 0.5,
            "langextract_provider": common_provider,
            "enable_attachment_download": attachment_usage > 0.5,
            "process_documents": doc_processing > 0.7
        }


async def get_enhanced_project_creation_service(
    db: Session,
    cdx_service: EnhancedCDXService,
    wayback_service: CDXAPIClient,
    websocket_service: WebSocketService,
    access_control: PageAccessControl
) -> EnhancedProjectCreationService:
    """Dependency injection for enhanced project creation service"""
    return EnhancedProjectCreationService(
        db, cdx_service, wayback_service, websocket_service, access_control
    )