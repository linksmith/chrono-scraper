#!/usr/bin/env python3
"""
Automated Scaling Decision Tool for Chrono Scraper v2
Analyzes current metrics and recommends scaling actions.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import psutil
import asyncpg
import redis
import requests
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ScalingMetrics:
    """Current system metrics for scaling decisions."""
    cpu_usage_7day_avg: float
    memory_usage_current: float
    memory_total: float
    active_users_30day: int
    concurrent_scrapes: int
    database_size_gb: float
    api_requests_per_minute: float
    revenue_monthly_eur: float
    response_time_p95_ms: float
    error_rate_percentage: float
    disk_usage_percentage: float
    celery_queue_length: int
    meilisearch_index_size_mb: float
    
    @property
    def memory_usage_percentage(self) -> float:
        return (self.memory_usage_current / self.memory_total) * 100

@dataclass
class ScalingRecommendation:
    """Scaling recommendation with justification."""
    current_phase: int
    recommended_phase: int
    trigger_score: float
    estimated_cost_eur: float
    migration_complexity: str  # "Low", "Medium", "High"
    estimated_downtime_minutes: int
    justification: List[str]
    action_plan: List[str]
    rollback_plan: List[str]
    
class ScalingDecisionTool:
    """Tool to analyze metrics and recommend scaling actions."""
    
    # Scaling trigger thresholds
    PHASE_TRIGGERS = {
        1: {  # Phase 1 -> 2
            "cpu_usage_7day_avg": 70.0,
            "memory_usage_percentage": 75.0,
            "active_users_30day": 100,
            "database_size_gb": 20.0,
            "revenue_monthly_eur": 500.0,
            "response_time_p95_ms": 2000.0,
            "error_rate_percentage": 1.0,
        },
        2: {  # Phase 2 -> 3
            "cpu_usage_7day_avg": 75.0,
            "memory_usage_percentage": 85.0,
            "active_users_30day": 500,
            "database_size_gb": 50.0,
            "revenue_monthly_eur": 2000.0,
            "response_time_p95_ms": 1500.0,
            "error_rate_percentage": 0.5,
        },
        3: {  # Phase 3 -> 4
            "cpu_usage_7day_avg": 80.0,
            "memory_usage_percentage": 85.0,
            "active_users_30day": 2000,
            "database_size_gb": 200.0,
            "revenue_monthly_eur": 5000.0,
            "response_time_p95_ms": 1000.0,
            "error_rate_percentage": 0.1,
        },
        4: {  # Phase 4 -> 5
            "cpu_usage_7day_avg": 85.0,
            "memory_usage_percentage": 90.0,
            "active_users_30day": 10000,
            "database_size_gb": 1000.0,
            "revenue_monthly_eur": 15000.0,
            "response_time_p95_ms": 500.0,
            "error_rate_percentage": 0.05,
        }
    }
    
    PHASE_COSTS = {
        1: 25.85,
        2: 31.90,
        3: 65.35,
        4: 175.00,
        5: 250.00
    }
    
    def __init__(self, config_path: str = ".env"):
        """Initialize with configuration."""
        self.config = self._load_config(config_path)
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from environment file."""
        config = {}
        try:
            with open(config_path) as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        config[key] = value.strip('"\'')
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
        return config
        
    async def collect_metrics(self) -> ScalingMetrics:
        """Collect current system metrics."""
        logger.info("Collecting system metrics...")
        
        # System metrics
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        
        # Database metrics
        db_size_gb = await self._get_database_size()
        active_users = await self._get_active_users()
        
        # Redis/Celery metrics
        redis_client = redis.Redis(
            host=self.config.get("REDIS_HOST", "localhost"),
            port=int(self.config.get("REDIS_PORT", 6379)),
            decode_responses=True
        )
        queue_length = redis_client.llen("celery")
        
        # API metrics (from application monitoring)
        api_metrics = await self._get_api_metrics()
        
        # Meilisearch metrics
        meilisearch_size = await self._get_meilisearch_size()
        
        return ScalingMetrics(
            cpu_usage_7day_avg=cpu_usage,  # Simplified for demo
            memory_usage_current=memory.used / (1024**3),  # GB
            memory_total=memory.total / (1024**3),  # GB
            active_users_30day=active_users,
            concurrent_scrapes=queue_length,
            database_size_gb=db_size_gb,
            api_requests_per_minute=api_metrics.get("requests_per_minute", 0),
            revenue_monthly_eur=float(self.config.get("MONTHLY_REVENUE", 0)),
            response_time_p95_ms=api_metrics.get("response_time_p95", 0),
            error_rate_percentage=api_metrics.get("error_rate", 0),
            disk_usage_percentage=(disk.used / disk.total) * 100,
            celery_queue_length=queue_length,
            meilisearch_index_size_mb=meilisearch_size
        )
    
    async def _get_database_size(self) -> float:
        """Get database size in GB."""
        try:
            conn = await asyncpg.connect(
                host=self.config.get("POSTGRES_HOST", "localhost"),
                port=int(self.config.get("POSTGRES_PORT", 5432)),
                user=self.config.get("POSTGRES_USER", "chrono_scraper"),
                password=self.config.get("POSTGRES_PASSWORD", "chrono_scraper_dev"),
                database=self.config.get("POSTGRES_DB", "chrono_scraper")
            )
            
            result = await conn.fetchval(
                "SELECT pg_database_size(current_database()) / (1024^3)::float"
            )
            await conn.close()
            return float(result)
        except Exception as e:
            logger.error(f"Failed to get database size: {e}")
            return 0.0
    
    async def _get_active_users(self) -> int:
        """Get active users count from database."""
        try:
            conn = await asyncpg.connect(
                host=self.config.get("POSTGRES_HOST", "localhost"),
                port=int(self.config.get("POSTGRES_PORT", 5432)),
                user=self.config.get("POSTGRES_USER", "chrono_scraper"),
                password=self.config.get("POSTGRES_PASSWORD", "chrono_scraper_dev"),
                database=self.config.get("POSTGRES_DB", "chrono_scraper")
            )
            
            # Count users active in last 30 days
            result = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT id) FROM users 
                WHERE last_login > NOW() - INTERVAL '30 days'
                AND is_active = true
                """
            )
            await conn.close()
            return int(result or 0)
        except Exception as e:
            logger.error(f"Failed to get active users: {e}")
            return 0
    
    async def _get_api_metrics(self) -> Dict:
        """Get API performance metrics."""
        # In production, this would query Prometheus/monitoring system
        # For now, return mock data
        return {
            "requests_per_minute": 50.0,
            "response_time_p95": 800.0,
            "error_rate": 0.2
        }
    
    async def _get_meilisearch_size(self) -> float:
        """Get Meilisearch index size in MB."""
        try:
            url = f"{self.config.get('MEILISEARCH_HOST', 'http://localhost:7700')}/stats"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                stats = response.json()
                return sum(idx.get("numberOfDocuments", 0) for idx in stats.get("indexes", {}).values()) * 0.001  # Rough estimate
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get Meilisearch size: {e}")
            return 0.0
    
    def calculate_trigger_score(self, metrics: ScalingMetrics, target_phase: int) -> Tuple[float, List[str]]:
        """Calculate scaling trigger score (0-1) and reasons."""
        if target_phase not in self.PHASE_TRIGGERS:
            return 0.0, []
            
        thresholds = self.PHASE_TRIGGERS[target_phase]
        triggered_metrics = []
        scores = []
        
        # Check each threshold
        for metric, threshold in thresholds.items():
            current_value = getattr(metrics, metric, 0)
            
            if metric == "memory_usage_percentage":
                current_value = metrics.memory_usage_percentage
                
            if current_value >= threshold:
                triggered_metrics.append(f"{metric}: {current_value:.1f} >= {threshold}")
                scores.append(1.0)
            else:
                # Partial score for values approaching threshold
                ratio = current_value / threshold
                scores.append(min(ratio, 1.0))
        
        # Average score across all metrics
        total_score = sum(scores) / len(scores) if scores else 0.0
        
        return total_score, triggered_metrics
    
    def generate_recommendation(self, metrics: ScalingMetrics, current_phase: int) -> ScalingRecommendation:
        """Generate scaling recommendation based on metrics."""
        
        # Check if we should scale up
        best_score = 0.0
        best_phase = current_phase
        best_triggers = []
        
        for next_phase in range(current_phase + 1, 6):  # Check phases 2-5
            score, triggers = self.calculate_trigger_score(metrics, next_phase)
            if score > best_score:
                best_score = score
                best_phase = next_phase
                best_triggers = triggers
        
        # Determine migration complexity
        phase_jump = best_phase - current_phase
        if phase_jump == 0:
            complexity = "None"
            downtime = 0
        elif phase_jump == 1:
            complexity = "Low" if best_phase <= 2 else "Medium"
            downtime = 15 if best_phase <= 2 else 30
        else:
            complexity = "High"
            downtime = 60
        
        # Generate justification
        justification = []
        if best_score >= 0.8:
            justification.append(f"Strong scaling signals detected (score: {best_score:.2f})")
        elif best_score >= 0.6:
            justification.append(f"Moderate scaling signals (score: {best_score:.2f})")
        elif best_score >= 0.4:
            justification.append(f"Early scaling indicators (score: {best_score:.2f})")
        else:
            justification.append(f"No immediate scaling needed (score: {best_score:.2f})")
            
        justification.extend(best_triggers[:3])  # Top 3 triggers
        
        # Generate action plan
        action_plan = self._generate_action_plan(current_phase, best_phase)
        rollback_plan = self._generate_rollback_plan(current_phase, best_phase)
        
        return ScalingRecommendation(
            current_phase=current_phase,
            recommended_phase=best_phase,
            trigger_score=best_score,
            estimated_cost_eur=self.PHASE_COSTS.get(best_phase, 0),
            migration_complexity=complexity,
            estimated_downtime_minutes=downtime,
            justification=justification,
            action_plan=action_plan,
            rollback_plan=rollback_plan
        )
    
    def _generate_action_plan(self, current: int, target: int) -> List[str]:
        """Generate step-by-step action plan."""
        if current == target:
            return ["No scaling action required at this time"]
            
        plans = {
            (1, 2): [
                "1. Provision second Hetzner CX22 server",
                "2. Set up PostgreSQL replication",
                "3. Configure service networking",
                "4. Execute data migration scripts",
                "5. Update DNS and load balancing",
                "6. Monitor performance post-migration"
            ],
            (2, 3): [
                "1. Provision load balancer (CPX21)",
                "2. Set up additional application servers",
                "3. Configure HAProxy load balancing",
                "4. Implement session management in Redis",
                "5. Deploy stateless application instances",
                "6. Test failover scenarios"
            ],
            (3, 4): [
                "1. Set up multi-region infrastructure",
                "2. Configure cross-region replication",
                "3. Implement CDN for static assets",
                "4. Set up global load balancing",
                "5. Test disaster recovery procedures",
                "6. Update monitoring and alerting"
            ]
        }
        
        return plans.get((current, target), [
            f"Custom migration plan needed for Phase {current} -> {target}",
            "Consult SCALING_STRATEGY.md for detailed procedures"
        ])
    
    def _generate_rollback_plan(self, current: int, target: int) -> List[str]:
        """Generate rollback procedures."""
        if current == target:
            return ["No rollback needed"]
            
        return [
            "1. Verify original infrastructure is still available",
            "2. Stop traffic to new infrastructure",
            "3. Restore database from backup if needed",
            "4. Update DNS to point to original servers",
            "5. Monitor application functionality",
            "6. Document issues for future migration attempts"
        ]
    
    async def analyze_and_recommend(self, current_phase: int = 1) -> ScalingRecommendation:
        """Main analysis function."""
        logger.info(f"Starting scaling analysis for current Phase {current_phase}")
        
        # Collect metrics
        metrics = await self.collect_metrics()
        
        # Generate recommendation
        recommendation = self.generate_recommendation(metrics, current_phase)
        
        logger.info(f"Analysis complete: Phase {current_phase} -> {recommendation.recommended_phase}")
        
        return recommendation
    
    def format_report(self, metrics: ScalingMetrics, recommendation: ScalingRecommendation) -> str:
        """Format analysis report."""
        report = f"""
# Chrono Scraper v2 Scaling Analysis Report
Generated: {datetime.now().isoformat()}

## Current Metrics
- CPU Usage (7-day avg): {metrics.cpu_usage_7day_avg:.1f}%
- Memory Usage: {metrics.memory_usage_current:.1f}GB / {metrics.memory_total:.1f}GB ({metrics.memory_usage_percentage:.1f}%)
- Active Users (30-day): {metrics.active_users_30day}
- Database Size: {metrics.database_size_gb:.1f}GB
- Monthly Revenue: €{metrics.revenue_monthly_eur:.2f}
- API Response Time (p95): {metrics.response_time_p95_ms:.0f}ms
- Error Rate: {metrics.error_rate_percentage:.2f}%
- Celery Queue Length: {metrics.celery_queue_length}

## Scaling Recommendation
- Current Phase: {recommendation.current_phase}
- Recommended Phase: {recommendation.recommended_phase}
- Trigger Score: {recommendation.trigger_score:.2f}/1.0
- Estimated Cost: €{recommendation.estimated_cost_eur:.2f}/month
- Migration Complexity: {recommendation.migration_complexity}
- Estimated Downtime: {recommendation.estimated_downtime_minutes} minutes

## Justification
"""
        for reason in recommendation.justification:
            report += f"- {reason}\n"
        
        report += "\n## Action Plan\n"
        for step in recommendation.action_plan:
            report += f"{step}\n"
        
        report += "\n## Rollback Plan\n"
        for step in recommendation.rollback_plan:
            report += f"{step}\n"
        
        report += f"""
## Next Steps
1. Review this analysis with the team
2. Plan maintenance window if migration is recommended
3. Execute migration scripts from scripts/scaling/
4. Monitor post-migration performance

---
For detailed procedures, see SCALING_STRATEGY.md
"""
        
        return report

async def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chrono Scraper v2 Scaling Decision Tool")
    parser.add_argument("--current-phase", type=int, default=1, 
                       help="Current deployment phase (1-5)")
    parser.add_argument("--config", default=".env", 
                       help="Configuration file path")
    parser.add_argument("--output", help="Output file for report")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                       help="Output format")
    
    args = parser.parse_args()
    
    try:
        # Initialize tool
        tool = ScalingDecisionTool(args.config)
        
        # Run analysis
        metrics = await tool.collect_metrics()
        recommendation = await tool.analyze_and_recommend(args.current_phase)
        
        # Format output
        if args.format == "json":
            output = {
                "metrics": asdict(metrics),
                "recommendation": asdict(recommendation),
                "timestamp": datetime.now().isoformat()
            }
            result = json.dumps(output, indent=2)
        else:
            result = tool.format_report(metrics, recommendation)
        
        # Write output
        if args.output:
            with open(args.output, "w") as f:
                f.write(result)
            logger.info(f"Report written to {args.output}")
        else:
            print(result)
            
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())