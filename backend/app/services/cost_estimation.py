"""
Cost estimation service for scraping operations
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Domain, Project, ScrapeSession
from .wayback_machine import get_cdx_page_count

logger = logging.getLogger(__name__)


@dataclass
class CostEstimate:
    """Cost estimation for scraping operation"""
    domain_name: str
    total_pages: int
    estimated_pages_after_filtering: int
    estimated_time_hours: float
    estimated_cost_usd: float
    confidence_level: str  # "high", "medium", "low"
    assumptions: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_name": self.domain_name,
            "total_pages": self.total_pages,
            "estimated_pages_after_filtering": self.estimated_pages_after_filtering,
            "estimated_time_hours": round(self.estimated_time_hours, 2),
            "estimated_cost_usd": round(self.estimated_cost_usd, 2),
            "confidence_level": self.confidence_level,
            "assumptions": self.assumptions
        }


class CostEstimationService:
    """Service for estimating scraping costs and time"""
    
    # Default cost assumptions (adjust based on your infrastructure)
    DEFAULT_COSTS = {
        "cpu_hour_cost": 0.05,  # $0.05 per CPU hour
        "bandwidth_gb_cost": 0.10,  # $0.10 per GB bandwidth
        "storage_gb_cost": 0.02,  # $0.02 per GB storage per month
        "avg_page_size_kb": 50,  # Average page size in KB
        "pages_per_hour": 1000,  # Pages processed per hour (conservative)
        "filtering_reduction": 0.7,  # 70% of pages filtered out
        "retry_overhead": 1.2,  # 20% overhead for retries
    }
    
    def __init__(self):
        self.costs = self.DEFAULT_COSTS.copy()
        logger.info("Initialized cost estimation service")
    
    async def estimate_domain_cost(self, domain_id: int) -> CostEstimate:
        """
        Estimate cost for scraping a single domain
        
        Args:
            domain_id: Domain to estimate
            
        Returns:
            CostEstimate object
        """
        with next(get_db()) as db:
            domain = db.query(Domain).filter(Domain.id == domain_id).first()
            if not domain:
                raise ValueError(f"Domain {domain_id} not found")
            
            # Get CDX page count
            from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "19900101"
            to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")
            
            try:
                total_pages = await get_cdx_page_count(
                    domain.domain_name, from_date, to_date,
                    domain.match_type.value, domain.url_path, domain.min_page_size
                )
            except Exception as e:
                logger.error(f"Failed to get CDX page count for {domain.domain_name}: {e}")
                total_pages = 0
            
            # Apply filtering reduction
            estimated_pages = int(total_pages * (1 - self.costs["filtering_reduction"]))
            
            # Apply max pages limit if set
            if domain.max_pages and estimated_pages > domain.max_pages:
                estimated_pages = domain.max_pages
            
            # Estimate time
            estimated_time_hours = (estimated_pages / self.costs["pages_per_hour"]) * self.costs["retry_overhead"]
            
            # Estimate costs
            cpu_cost = estimated_time_hours * self.costs["cpu_hour_cost"]
            
            # Bandwidth cost (download)
            total_data_gb = (estimated_pages * self.costs["avg_page_size_kb"]) / (1024 * 1024)
            bandwidth_cost = total_data_gb * self.costs["bandwidth_gb_cost"]
            
            # Storage cost (assume 1 month retention)
            storage_cost = total_data_gb * self.costs["storage_gb_cost"]
            
            total_cost = cpu_cost + bandwidth_cost + storage_cost
            
            # Determine confidence level
            confidence = self._determine_confidence(total_pages, domain)
            
            # Generate assumptions
            assumptions = [
                f"Average page size: {self.costs['avg_page_size_kb']}KB",
                f"Processing rate: {self.costs['pages_per_hour']} pages/hour",
                f"Filtering reduces pages by {int(self.costs['filtering_reduction'] * 100)}%",
                f"Retry overhead: {int((self.costs['retry_overhead'] - 1) * 100)}%",
                f"CPU cost: ${self.costs['cpu_hour_cost']}/hour",
                f"Bandwidth cost: ${self.costs['bandwidth_gb_cost']}/GB",
                f"Storage cost: ${self.costs['storage_gb_cost']}/GB/month"
            ]
            
            return CostEstimate(
                domain_name=domain.domain_name,
                total_pages=total_pages,
                estimated_pages_after_filtering=estimated_pages,
                estimated_time_hours=estimated_time_hours,
                estimated_cost_usd=total_cost,
                confidence_level=confidence,
                assumptions=assumptions
            )
    
    async def estimate_project_cost(self, project_id: int) -> Dict[str, Any]:
        """
        Estimate cost for scraping an entire project
        
        Args:
            project_id: Project to estimate
            
        Returns:
            Dictionary with project cost estimate
        """
        with next(get_db()) as db:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project {project_id} not found")
            
            domains = db.query(Domain).filter(
                Domain.project_id == project_id,
                Domain.active == True
            ).all()
            
            if not domains:
                return {
                    "project_id": project_id,
                    "project_name": project.name,
                    "domain_count": 0,
                    "total_cost": 0.0,
                    "total_time_hours": 0.0,
                    "domains": []
                }
            
            # Estimate each domain
            domain_estimates = []
            total_cost = 0.0
            total_time = 0.0
            total_pages = 0
            
            for domain in domains:
                try:
                    estimate = await self.estimate_domain_cost(domain.id)
                    domain_estimates.append(estimate.to_dict())
                    total_cost += estimate.estimated_cost_usd
                    total_time += estimate.estimated_time_hours
                    total_pages += estimate.estimated_pages_after_filtering
                except Exception as e:
                    logger.error(f"Failed to estimate domain {domain.id}: {e}")
                    # Add placeholder estimate
                    domain_estimates.append({
                        "domain_name": domain.domain_name,
                        "error": str(e),
                        "estimated_cost_usd": 0.0,
                        "estimated_time_hours": 0.0
                    })
            
            # Determine overall confidence
            confidences = [est.get("confidence_level", "low") for est in domain_estimates if "confidence_level" in est]
            if not confidences:
                overall_confidence = "low"
            elif all(c == "high" for c in confidences):
                overall_confidence = "high"
            elif all(c in ["high", "medium"] for c in confidences):
                overall_confidence = "medium"
            else:
                overall_confidence = "low"
            
            return {
                "project_id": project_id,
                "project_name": project.name,
                "domain_count": len(domains),
                "total_pages": total_pages,
                "total_cost_usd": round(total_cost, 2),
                "total_time_hours": round(total_time, 2),
                "confidence_level": overall_confidence,
                "estimated_completion": (datetime.now() + timedelta(hours=total_time)).isoformat(),
                "domains": domain_estimates
            }
    
    def _determine_confidence(self, total_pages: int, domain: Domain) -> str:
        """Determine confidence level for estimate"""
        if total_pages == 0:
            return "low"
        
        # High confidence for smaller, well-defined domains
        if total_pages < 1000 and domain.max_pages:
            return "high"
        
        # Medium confidence for medium-sized domains
        if total_pages < 10000:
            return "medium"
        
        # Low confidence for large or unlimited domains
        return "low"
    
    def update_costs(self, new_costs: Dict[str, float]):
        """Update cost assumptions"""
        for key, value in new_costs.items():
            if key in self.costs:
                old_value = self.costs[key]
                self.costs[key] = value
                logger.info(f"Updated cost assumption {key}: {old_value} -> {value}")
            else:
                logger.warning(f"Unknown cost key: {key}")
    
    def get_historical_performance(self, domain_id: int) -> Optional[Dict[str, float]]:
        """Get historical performance data for better estimates"""
        with next(get_db()) as db:
            # Get recent scrape sessions for this domain
            recent_sessions = db.query(ScrapeSession).join(
                Domain, Domain.project_id == ScrapeSession.project_id
            ).filter(
                Domain.id == domain_id,
                ScrapeSession.completed_at.isnot(None),
                ScrapeSession.started_at > datetime.now() - timedelta(days=30)
            ).all()
            
            if not recent_sessions:
                return None
            
            # Calculate average performance metrics
            total_time = 0.0
            total_pages = 0
            session_count = 0
            
            for session in recent_sessions:
                if session.started_at and session.completed_at:
                    duration = (session.completed_at - session.started_at).total_seconds() / 3600  # hours
                    total_time += duration
                    total_pages += session.completed_urls
                    session_count += 1
            
            if session_count == 0:
                return None
            
            avg_time = total_time / session_count
            avg_pages = total_pages / session_count
            pages_per_hour = avg_pages / avg_time if avg_time > 0 else 0
            
            return {
                "avg_time_hours": avg_time,
                "avg_pages": avg_pages,
                "pages_per_hour": pages_per_hour,
                "sample_size": session_count
            }


# Global service instance
cost_estimator = CostEstimationService()


# Convenience functions
async def estimate_domain_scraping_cost(domain_id: int) -> Dict[str, Any]:
    """Estimate cost for scraping a domain"""
    estimate = await cost_estimator.estimate_domain_cost(domain_id)
    return estimate.to_dict()


async def estimate_project_scraping_cost(project_id: int) -> Dict[str, Any]:
    """Estimate cost for scraping a project"""
    return await cost_estimator.estimate_project_cost(project_id)