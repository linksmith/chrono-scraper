#!/usr/bin/env python3
"""
Cost Optimization Tool for Chrono Scraper v2
Analyzes resource usage and provides cost optimization recommendations
"""

import asyncio
import json
import math
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import psutil
import docker
import requests

@dataclass
class ResourceUsage:
    """Resource usage metrics."""
    service_name: str
    cpu_percent: float
    memory_mb: float
    memory_limit_mb: float
    disk_mb: float
    network_rx_mb: float
    network_tx_mb: float
    uptime_hours: float
    restart_count: int

@dataclass
class CostOptimization:
    """Cost optimization recommendation."""
    service_name: str
    current_cost_eur: float
    optimized_cost_eur: float
    savings_eur: float
    savings_percent: float
    recommendation: str
    complexity: str  # "Low", "Medium", "High"
    risk_level: str  # "Low", "Medium", "High"
    implementation_steps: List[str]

class CostOptimizer:
    """Analyzes resource usage and provides cost optimization recommendations."""
    
    # Hetzner Cloud pricing (EUR/month)
    SERVER_COSTS = {
        "cx11": 3.29,   # 1 vCPU, 4GB RAM
        "cx22": 5.83,   # 2 vCPU, 8GB RAM  
        "cx32": 10.69,  # 4 vCPU, 16GB RAM
        "cx42": 21.31,  # 8 vCPU, 32GB RAM
        "cx52": 42.70,  # 16 vCPU, 64GB RAM
        "cpx11": 4.51,  # 2 vCPU, 4GB RAM, dedicated
        "cpx21": 8.21,  # 3 vCPU, 8GB RAM, dedicated
        "cpx31": 15.12, # 4 vCPU, 16GB RAM, dedicated
        "cpx41": 26.73, # 8 vCPU, 32GB RAM, dedicated
        "cpx51": 49.89, # 16 vCPU, 64GB RAM, dedicated
    }
    
    # Service resource profiles (baseline estimates)
    SERVICE_PROFILES = {
        "backend": {"cpu_cores": 1.0, "memory_gb": 1.0, "baseline_cost": 5.0},
        "frontend": {"cpu_cores": 0.5, "memory_gb": 0.5, "baseline_cost": 2.5},
        "postgres": {"cpu_cores": 1.0, "memory_gb": 2.0, "baseline_cost": 8.0},
        "redis": {"cpu_cores": 0.25, "memory_gb": 0.5, "baseline_cost": 1.5},
        "meilisearch": {"cpu_cores": 0.5, "memory_gb": 1.0, "baseline_cost": 4.0},
        "celery-worker": {"cpu_cores": 0.5, "memory_gb": 0.5, "baseline_cost": 2.5},
        "celery-beat": {"cpu_cores": 0.1, "memory_gb": 0.1, "baseline_cost": 0.5},
        "firecrawl-api": {"cpu_cores": 0.5, "memory_gb": 0.5, "baseline_cost": 2.5},
        "firecrawl-worker": {"cpu_cores": 1.0, "memory_gb": 1.5, "baseline_cost": 6.0},
        "nginx": {"cpu_cores": 0.25, "memory_gb": 0.25, "baseline_cost": 1.0}
    }
    
    def __init__(self):
        """Initialize cost optimizer."""
        self.docker_client = docker.from_env()
        
    async def collect_resource_usage(self, hours: int = 24) -> List[ResourceUsage]:
        """Collect resource usage for all services."""
        usage_data = []
        
        try:
            containers = self.docker_client.containers.list()
            
            for container in containers:
                if "chrono-scraper" not in container.name:
                    continue
                    
                # Get container stats
                stats = container.stats(stream=False)
                
                # Calculate CPU percentage
                cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                           stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                              stats['precpu_stats']['system_cpu_usage']
                cpu_percent = (cpu_delta / system_delta) * 100.0 if system_delta > 0 else 0.0
                
                # Memory usage
                memory_usage = stats['memory_stats'].get('usage', 0)
                memory_limit = stats['memory_stats'].get('limit', 0)
                
                # Network I/O
                networks = stats.get('networks', {})
                rx_bytes = sum(net.get('rx_bytes', 0) for net in networks.values())
                tx_bytes = sum(net.get('tx_bytes', 0) for net in networks.values())
                
                # Container info
                container_info = container.attrs
                created_time = datetime.fromisoformat(
                    container_info['Created'].replace('Z', '+00:00')
                )
                uptime = (datetime.now(created_time.tzinfo) - created_time).total_seconds() / 3600
                
                # Service name from container name
                service_name = self._extract_service_name(container.name)
                
                usage = ResourceUsage(
                    service_name=service_name,
                    cpu_percent=cpu_percent,
                    memory_mb=memory_usage / (1024 * 1024),
                    memory_limit_mb=memory_limit / (1024 * 1024),
                    disk_mb=0,  # Would need additional Docker API calls
                    network_rx_mb=rx_bytes / (1024 * 1024),
                    network_tx_mb=tx_bytes / (1024 * 1024),
                    uptime_hours=uptime,
                    restart_count=container_info['RestartCount']
                )
                
                usage_data.append(usage)
                
        except Exception as e:
            print(f"Error collecting resource usage: {e}")
            
        return usage_data
    
    def _extract_service_name(self, container_name: str) -> str:
        """Extract service name from container name."""
        # Remove project prefix and suffix numbers
        parts = container_name.split('-')
        if len(parts) >= 3:
            # Typically: chrono-scraper-fastapi-2-backend-1
            service_parts = parts[4:]  # Skip "chrono-scraper-fastapi-2"
            if service_parts:
                return '-'.join(service_parts[:-1])  # Remove trailing number
        return container_name
    
    def analyze_cost_optimizations(self, usage_data: List[ResourceUsage]) -> List[CostOptimization]:
        """Analyze resource usage and generate optimization recommendations."""
        optimizations = []
        
        for usage in usage_data:
            optimization = self._analyze_service_optimization(usage)
            if optimization:
                optimizations.append(optimization)
        
        # Add infrastructure-level optimizations
        infra_optimizations = self._analyze_infrastructure_optimizations(usage_data)
        optimizations.extend(infra_optimizations)
        
        return sorted(optimizations, key=lambda x: x.savings_eur, reverse=True)
    
    def _analyze_service_optimization(self, usage: ResourceUsage) -> Optional[CostOptimization]:
        """Analyze optimization opportunities for a single service."""
        service_profile = self.SERVICE_PROFILES.get(usage.service_name, {})
        if not service_profile:
            return None
            
        current_cost = service_profile.get("baseline_cost", 0)
        memory_gb = usage.memory_mb / 1024
        
        # Analyze resource efficiency
        recommendations = []
        optimized_cost = current_cost
        
        # Memory optimization
        if usage.memory_limit_mb > 0:
            memory_utilization = usage.memory_mb / usage.memory_limit_mb
            if memory_utilization < 0.3:  # Less than 30% utilization
                new_limit_mb = usage.memory_mb * 1.5  # 50% headroom
                savings = self._calculate_memory_savings(
                    usage.memory_limit_mb, new_limit_mb
                )
                optimized_cost -= savings
                recommendations.append(
                    f"Reduce memory limit from {usage.memory_limit_mb:.0f}MB to {new_limit_mb:.0f}MB"
                )
            elif memory_utilization > 0.85:  # Over 85% utilization
                recommendations.append(
                    f"Consider increasing memory limit (currently {memory_utilization:.1%} utilized)"
                )
        
        # CPU optimization
        if usage.cpu_percent < 20:  # Low CPU usage
            recommendations.append(
                f"Low CPU usage ({usage.cpu_percent:.1f}%) - consider consolidating services"
            )
        elif usage.cpu_percent > 80:  # High CPU usage
            recommendations.append(
                f"High CPU usage ({usage.cpu_percent:.1f}%) - consider scaling out"
            )
        
        # Restart analysis
        if usage.restart_count > 5:
            recommendations.append(
                f"Frequent restarts ({usage.restart_count}) indicate instability"
            )
        
        if not recommendations:
            return None
            
        savings = current_cost - optimized_cost
        
        return CostOptimization(
            service_name=usage.service_name,
            current_cost_eur=current_cost,
            optimized_cost_eur=optimized_cost,
            savings_eur=savings,
            savings_percent=(savings / current_cost) * 100 if current_cost > 0 else 0,
            recommendation="; ".join(recommendations[:2]),  # Top 2 recommendations
            complexity="Low" if len(recommendations) == 1 else "Medium",
            risk_level="Low" if usage.restart_count == 0 else "Medium",
            implementation_steps=self._generate_implementation_steps(usage.service_name, recommendations)
        )
    
    def _calculate_memory_savings(self, current_mb: float, optimized_mb: float) -> float:
        """Calculate cost savings from memory optimization."""
        # Rough estimate: €0.02 per GB per month
        gb_saved = (current_mb - optimized_mb) / 1024
        return gb_saved * 0.02
    
    def _analyze_infrastructure_optimizations(self, usage_data: List[ResourceUsage]) -> List[CostOptimization]:
        """Analyze infrastructure-level optimization opportunities."""
        optimizations = []
        
        # Calculate total resource usage
        total_memory_mb = sum(u.memory_mb for u in usage_data)
        total_cpu_percent = sum(u.cpu_percent for u in usage_data)
        avg_cpu_percent = total_cpu_percent / len(usage_data) if usage_data else 0
        
        # Server consolidation opportunities
        if avg_cpu_percent < 40 and total_memory_mb < 6 * 1024:  # Less than 6GB total
            optimizations.append(CostOptimization(
                service_name="infrastructure",
                current_cost_eur=25.85,  # CX32 cost
                optimized_cost_eur=10.69,  # CX22 cost
                savings_eur=15.16,
                savings_percent=58.6,
                recommendation="Downgrade from CX32 to CX22 server due to low resource usage",
                complexity="Medium",
                risk_level="Medium",
                implementation_steps=[
                    "Create CX22 server backup",
                    "Provision new CX22 server",
                    "Migrate data and applications", 
                    "Update DNS and monitoring",
                    "Decommission CX32 server"
                ]
            ))
        
        # Reserved instance opportunities
        if len(usage_data) > 0:  # If services are running consistently
            optimizations.append(CostOptimization(
                service_name="infrastructure",
                current_cost_eur=25.85,
                optimized_cost_eur=20.68,  # ~20% discount for reserved
                savings_eur=5.17,
                savings_percent=20.0,
                recommendation="Consider reserved instances for 20% cost savings",
                complexity="Low",
                risk_level="Low",
                implementation_steps=[
                    "Analyze usage patterns over 3+ months",
                    "Purchase 1-year reserved instance",
                    "Monitor and adjust as needed"
                ]
            ))
        
        # Scheduling optimizations
        batch_services = [u for u in usage_data if 'celery' in u.service_name.lower()]
        if batch_services:
            total_batch_cost = sum(
                self.SERVICE_PROFILES.get(s.service_name, {}).get("baseline_cost", 0)
                for s in batch_services
            )
            optimizations.append(CostOptimization(
                service_name="batch-processing",
                current_cost_eur=total_batch_cost,
                optimized_cost_eur=total_batch_cost * 0.6,  # 40% savings with spot instances
                savings_eur=total_batch_cost * 0.4,
                savings_percent=40.0,
                recommendation="Use spot instances for batch processing workloads",
                complexity="High",
                risk_level="Medium",
                implementation_steps=[
                    "Implement graceful shutdown for Celery workers",
                    "Add spot instance request logic",
                    "Configure automatic failover to on-demand",
                    "Monitor cost savings and reliability"
                ]
            ))
        
        return optimizations
    
    def _generate_implementation_steps(self, service_name: str, recommendations: List[str]) -> List[str]:
        """Generate implementation steps for service optimizations."""
        steps = []
        
        if any("memory limit" in rec for rec in recommendations):
            steps.extend([
                f"Update docker-compose.yml memory limits for {service_name}",
                "Test service with reduced memory allocation",
                "Monitor memory usage for 24 hours",
                "Apply changes to production"
            ])
        
        if any("CPU usage" in rec for rec in recommendations):
            steps.extend([
                f"Analyze {service_name} CPU usage patterns",
                "Consider service consolidation or scaling",
                "Test changes in staging environment"
            ])
            
        if any("restart" in rec for rec in recommendations):
            steps.extend([
                f"Investigate {service_name} restart causes",
                "Fix underlying stability issues",
                "Implement health checks and monitoring"
            ])
        
        return steps if steps else ["Monitor service performance", "Apply optimizations gradually"]
    
    def generate_cost_report(self, optimizations: List[CostOptimization]) -> str:
        """Generate comprehensive cost optimization report."""
        total_current_cost = sum(opt.current_cost_eur for opt in optimizations)
        total_savings = sum(opt.savings_eur for opt in optimizations)
        total_optimized_cost = total_current_cost - total_savings
        
        report = f"""
# Chrono Scraper v2 Cost Optimization Report
Generated: {datetime.now().isoformat()}

## Executive Summary
- **Current Monthly Cost**: €{total_current_cost:.2f}
- **Potential Savings**: €{total_savings:.2f} ({(total_savings/total_current_cost)*100:.1f}%)
- **Optimized Monthly Cost**: €{total_optimized_cost:.2f}
- **Annual Savings Potential**: €{total_savings * 12:.2f}

## Top Optimization Opportunities

"""
        
        for i, opt in enumerate(optimizations[:5], 1):
            report += f"""
### {i}. {opt.service_name.title()} Optimization
- **Potential Savings**: €{opt.savings_eur:.2f}/month ({opt.savings_percent:.1f}%)
- **Complexity**: {opt.complexity}
- **Risk Level**: {opt.risk_level}
- **Recommendation**: {opt.recommendation}

**Implementation Steps:**
"""
            for step in opt.implementation_steps:
                report += f"   1. {step}\n"
        
        report += f"""

## Cost Optimization Roadmap

### Phase 1: Low-Risk Optimizations (Month 1)
- Implement memory limit adjustments
- Set up resource monitoring alerts
- Apply container right-sizing

### Phase 2: Medium-Risk Optimizations (Month 2-3)
- Consider server consolidation
- Implement reserved instance strategy
- Optimize batch processing schedules

### Phase 3: High-Impact Optimizations (Month 4-6)
- Implement spot instances for batch workloads
- Consider multi-region cost optimization
- Implement auto-scaling based on demand

## Monitoring Recommendations

### Key Metrics to Track
- Monthly infrastructure costs vs. revenue
- Cost per active user
- Resource utilization trends
- Service reliability after optimizations

### Cost Alerts
- Set up billing alerts at 80% and 100% of budget
- Monitor cost increase trends (>20% month-over-month)
- Track cost per user metrics

## Risk Mitigation

### Before Implementation
1. **Backup Strategy**: Ensure complete backups before changes
2. **Testing**: Validate optimizations in staging environment
3. **Monitoring**: Set up detailed monitoring for affected services
4. **Rollback Plan**: Prepare quick rollback procedures

### During Implementation
1. **Gradual Rollout**: Apply changes to non-critical services first
2. **Performance Monitoring**: Watch key performance metrics closely
3. **User Communication**: Inform users of potential maintenance windows

### After Implementation
1. **Performance Validation**: Confirm no degradation in user experience
2. **Cost Tracking**: Monitor actual savings vs. projections
3. **Documentation**: Update operational procedures

## Conclusion

The identified optimizations can reduce monthly infrastructure costs by up to 
€{total_savings:.2f} ({(total_savings/total_current_cost)*100:.1f}%) while maintaining service quality. 

Priority should be given to low-risk optimizations first, followed by 
infrastructure-level changes as the application scales.

Next review recommended in 30 days to assess optimization impact and 
identify new opportunities.
"""
        
        return report
    
    async def run_analysis(self) -> Dict:
        """Run complete cost optimization analysis."""
        print("🔍 Collecting resource usage data...")
        usage_data = await self.collect_resource_usage()
        
        print(f"📊 Analyzing {len(usage_data)} services...")
        optimizations = self.analyze_cost_optimizations(usage_data)
        
        print("📋 Generating cost optimization report...")
        report = self.generate_cost_report(optimizations)
        
        return {
            "usage_data": [
                {
                    "service_name": u.service_name,
                    "cpu_percent": u.cpu_percent,
                    "memory_mb": u.memory_mb,
                    "memory_utilization": u.memory_mb / u.memory_limit_mb if u.memory_limit_mb > 0 else 0
                }
                for u in usage_data
            ],
            "optimizations": [
                {
                    "service_name": o.service_name,
                    "savings_eur": o.savings_eur,
                    "savings_percent": o.savings_percent,
                    "recommendation": o.recommendation,
                    "complexity": o.complexity,
                    "risk_level": o.risk_level
                }
                for o in optimizations
            ],
            "report": report,
            "summary": {
                "total_services": len(usage_data),
                "total_optimizations": len(optimizations),
                "total_savings": sum(o.savings_eur for o in optimizations),
                "low_risk_savings": sum(o.savings_eur for o in optimizations if o.risk_level == "Low"),
                "medium_risk_savings": sum(o.savings_eur for o in optimizations if o.risk_level == "Medium"),
                "high_risk_savings": sum(o.savings_eur for o in optimizations if o.risk_level == "High")
            }
        }

async def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chrono Scraper v2 Cost Optimizer")
    parser.add_argument("--output", help="Output file for report")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                       help="Output format")
    parser.add_argument("--hours", type=int, default=24,
                       help="Hours of data to analyze")
    
    args = parser.parse_args()
    
    try:
        optimizer = CostOptimizer()
        results = await optimizer.run_analysis()
        
        if args.format == "json":
            output = json.dumps(results, indent=2)
        else:
            output = results["report"]
        
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"✅ Report saved to {args.output}")
        else:
            print(output)
            
        # Print summary
        summary = results["summary"]
        print(f"\n💰 Cost Optimization Summary:")
        print(f"   Services analyzed: {summary['total_services']}")
        print(f"   Optimization opportunities: {summary['total_optimizations']}")
        print(f"   Total potential savings: €{summary['total_savings']:.2f}/month")
        print(f"   Low-risk savings: €{summary['low_risk_savings']:.2f}/month")
        print(f"   Medium-risk savings: €{summary['medium_risk_savings']:.2f}/month")
        print(f"   High-risk savings: €{summary['high_risk_savings']:.2f}/month")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))