#!/usr/bin/env python3
"""
Intelligent Content Extraction Performance Monitor
Monitors extraction performance and system health via API endpoints
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any

import httpx
import redis
from redis.exceptions import ConnectionError as RedisConnectionError

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ExtractionMonitor:
    """Monitors extraction performance and system health"""
    
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.backend_url = os.getenv("BACKEND_URL", "http://backend:8000")
        self.monitor_interval = int(os.getenv("MONITOR_INTERVAL", "60"))
        
        # Initialize Redis connection
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host, 
                port=self.redis_port,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info(f"✅ Connected to Redis at {self.redis_host}:{self.redis_port}")
        except RedisConnectionError:
            logger.error(f"❌ Failed to connect to Redis at {self.redis_host}:{self.redis_port}")
            self.redis_client = None
    
    async def check_backend_health(self) -> Dict[str, Any]:
        """Check backend API health"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.backend_url}/api/v1/health",
                    timeout=10.0
                )
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time": response.elapsed.total_seconds(),
                        "data": response.json()
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "status_code": response.status_code,
                        "response_time": response.elapsed.total_seconds()
                    }
        except Exception as e:
            logger.error(f"Backend health check failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def get_extraction_metrics(self) -> Dict[str, Any]:
        """Get extraction performance metrics from backend"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.backend_url}/api/v1/monitoring/extraction-metrics",
                    timeout=10.0
                )
                if response.status_code == 200:
                    return {
                        "status": "success",
                        "metrics": response.json()
                    }
                else:
                    return {
                        "status": "error",
                        "status_code": response.status_code
                    }
        except Exception as e:
            logger.warning(f"Failed to get extraction metrics: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_redis_metrics(self) -> Dict[str, Any]:
        """Get Redis performance metrics"""
        if not self.redis_client:
            return {"status": "error", "error": "Redis not connected"}
        
        try:
            info = self.redis_client.info()
            return {
                "status": "healthy",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands_processed": info.get("total_commands_processed", 0)
            }
        except Exception as e:
            logger.error(f"Redis metrics failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def run_monitoring_cycle(self):
        """Run a single monitoring cycle"""
        timestamp = datetime.now().isoformat()
        
        logger.info("🔍 Starting monitoring cycle...")
        
        # Collect metrics
        backend_health = await self.check_backend_health()
        extraction_metrics = await self.get_extraction_metrics()
        redis_metrics = self.get_redis_metrics()
        
        # Create monitoring report
        report = {
            "timestamp": timestamp,
            "backend_health": backend_health,
            "extraction_metrics": extraction_metrics,
            "redis_metrics": redis_metrics
        }
        
        # Log summary
        backend_status = backend_health.get("status", "unknown")
        redis_status = redis_metrics.get("status", "unknown")
        
        logger.info(f"📊 Monitor Report - Backend: {backend_status}, Redis: {redis_status}")
        
        if backend_health.get("status") == "healthy":
            response_time = backend_health.get("response_time", 0)
            logger.info(f"⚡ Backend response time: {response_time:.3f}s")
        
        if redis_metrics.get("status") == "healthy":
            memory = redis_metrics.get("used_memory_human", "0B")
            clients = redis_metrics.get("connected_clients", 0)
            logger.info(f"💾 Redis: {memory} memory, {clients} clients")
        
        # Store metrics in Redis if available
        if self.redis_client:
            try:
                self.redis_client.setex(
                    "extraction_monitor:latest_report",
                    3600,  # 1 hour expiry
                    json.dumps(report)
                )
            except Exception as e:
                logger.warning(f"Failed to store report in Redis: {e}")
        
        return report
    
    async def run_continuous_monitoring(self):
        """Run continuous monitoring"""
        logger.info(f"🚀 Starting continuous extraction monitoring (interval: {self.monitor_interval}s)")
        
        while True:
            try:
                await self.run_monitoring_cycle()
                await asyncio.sleep(self.monitor_interval)
            except KeyboardInterrupt:
                logger.info("⏹️ Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring cycle failed: {e}")
                await asyncio.sleep(self.monitor_interval)

async def main():
    """Main function"""
    monitor = ExtractionMonitor()
    await monitor.run_continuous_monitoring()

if __name__ == "__main__":
    asyncio.run(main())