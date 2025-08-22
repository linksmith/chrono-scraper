# Docker Compose Configuration Comparison Report

## Executive Summary
Both `docker-compose.yml` and `docker-compose.optimized.yml` successfully start all services without errors. The optimized version adds resource constraints and performance tuning parameters designed for an 8-core/16GB system.

## Key Differences

### 1. Resource Limits and Reservations

#### Regular Version (`docker-compose.yml`)
- **No resource limits** - containers can use all available system memory
- **No CPU constraints** - containers compete for CPU resources
- **Risk**: Memory leaks or high load can affect entire system

#### Optimized Version (`docker-compose.optimized.yml`)
- **Enforced memory limits** per service
- **CPU quotas** to prevent resource starvation
- **Reserved resources** to guarantee minimum performance

| Service | Memory Limit | CPU Limit | Reserved Memory | Reserved CPU |
|---------|-------------|-----------|-----------------|--------------|
| PostgreSQL | 1.5GB | 2.0 cores | 800MB | 1.0 core |
| Redis | 512MB | 1.0 core | 256MB | 0.5 core |
| Meilisearch | 1GB | 1.5 cores | 512MB | 1.0 core |
| Firecrawl Playwright | 3GB | 2.0 cores | 1.5GB | 1.0 core |
| Firecrawl API | 1GB | 1.5 cores | 512MB | 0.5 core |
| Firecrawl Worker | 1.5GB | 1.5 cores | 768MB | 1.0 core |
| Backend | 1GB | 1.5 cores | 512MB | 1.0 core |
| Celery Worker | 2GB | 2.5 cores | 1GB | 1.5 cores |
| Celery Beat | 256MB | 0.5 core | 128MB | 0.25 core |
| Frontend | 512MB | 1.0 core | 256MB | 0.5 core |
| Flower | 256MB | 0.5 core | 128MB | 0.25 core |
| Mailpit | 128MB | 0.25 core | 64MB | 0.1 core |

### 2. Performance Tuning Parameters

#### PostgreSQL (Optimized only)
```yaml
- POSTGRES_SHARED_BUFFERS=384MB
- POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
- POSTGRES_WORK_MEM=32MB
- POSTGRES_MAINTENANCE_WORK_MEM=128MB
- POSTGRES_CHECKPOINT_COMPLETION_TARGET=0.9
- POSTGRES_WAL_BUFFERS=16MB
- POSTGRES_DEFAULT_STATISTICS_TARGET=100
- POSTGRES_RANDOM_PAGE_COST=1.1  # SSD optimization
- POSTGRES_EFFECTIVE_IO_CONCURRENCY=200
```

#### Redis (Optimized only)
```yaml
--maxmemory 384mb
--maxmemory-policy allkeys-lru
--save 900 1
--save 300 10
--save 60 10000
--appendonly yes
--appendfsync everysec
```

#### Node.js Services (Optimized only)
- Backend: `NODE_OPTIONS=--max-old-space-size=768`
- Frontend: `NODE_OPTIONS=--max-old-space-size=384`
- Firecrawl API: `NODE_OPTIONS=--max-old-space-size=768`
- Firecrawl Worker: `NODE_OPTIONS=--max-old-space-size=1024`

#### Celery Worker (Optimized only)
```yaml
--concurrency=6
--prefetch-multiplier=2
--max-tasks-per-child=50
--max-memory-per-child=400000
```

### 3. Network Configuration

#### Regular Version
- Simple bridge network

#### Optimized Version
- Bridge network with explicit subnet: `172.20.0.0/16`
- Fixed IP addresses for better service discovery

### 4. Additional Optimizations

#### Optimized Version Only:
- **Shared memory for PostgreSQL**: `/dev/shm:/dev/shm:rw`
- **Health check start periods**: Added to prevent premature failures
- **Sysctls for Playwright**: Network tuning for browser automation
- **UV_THREADPOOL_SIZE**: Set to 16 for Firecrawl API
- **Browser pool limits**: MAX_CONCURRENT_SESSIONS=3, BROWSER_POOL_SIZE=2

## Test Results

### Regular Version
✅ All services start successfully
✅ No errors or warnings in logs
✅ Memory usage: Unrestricted (using ~1.5GB total)
✅ CPU usage: Low (<1% per service)

### Optimized Version
✅ All services start successfully
✅ No errors or warnings in logs
✅ Memory usage: Constrained within limits
⚠️ **Frontend near memory limit**: 463.9MiB / 512MiB (90% usage)
⚠️ **Celery Beat**: 115.7MiB / 256MiB (45% usage)
✅ CPU usage: Low (<2% per service)

## Potential Issues to Watch

### 1. Frontend Memory Pressure
The frontend is using 90% of its allocated 512MB. This could lead to:
- Out of memory errors during build processes
- Slower performance due to garbage collection
- Potential crashes under heavy development

**Recommendation**: Consider increasing frontend memory limit to 768MB or 1GB

### 2. Celery Beat Memory
Using 45% of allocated memory might be tight for complex scheduled tasks.

**Recommendation**: Monitor during production use

### 3. Database Connection Limits
Optimized version sets `max_connections=100` which should be sufficient but may need adjustment based on concurrent users.

## Recommendations

### For Development
Use **`docker-compose.yml`** (regular) because:
- Simpler configuration
- No resource constraints during debugging
- Faster container rebuilds
- Less likely to hit memory limits during development

### For Production/Staging
Use **`docker-compose.optimized.yml`** because:
- Prevents resource exhaustion
- Better performance with tuned parameters
- Predictable resource allocation
- Protection against memory leaks
- Optimized for 8-core/16GB systems

### Immediate Actions Recommended

1. **Increase Frontend Memory Limit** in optimized version:
   ```yaml
   frontend:
     deploy:
       resources:
         limits:
           memory: 768M  # or 1G
   ```

2. **Monitor these metrics** when using optimized version:
   - Frontend memory usage during builds
   - PostgreSQL connection pool usage
   - Redis memory eviction statistics
   - Celery worker task completion times

3. **Consider adding** to optimized version:
   - Restart policies with max retry counts
   - Log rotation limits
   - Prometheus/Grafana monitoring stack

## Command Reference

### Start with Regular Configuration
```bash
docker compose up -d
```

### Start with Optimized Configuration
```bash
docker compose -f docker-compose.optimized.yml up -d
```

### Monitor Resource Usage
```bash
# Real-time monitoring
docker stats

# Check specific service logs
docker compose -f docker-compose.optimized.yml logs -f [service_name]

# Check memory limits
docker inspect [container_name] | grep -i memory
```

## Conclusion

Both configurations work correctly. The optimized version provides better resource management and performance tuning at the cost of complexity and potential memory pressure on some services. The frontend service needs a memory limit increase for comfortable operation.

For your use case, I recommend:
1. **Start with the optimized version** for better resource management
2. **Increase the frontend memory limit** to 768MB or 1GB
3. **Monitor the services** for the first few hours of operation
4. **Fall back to regular version** if you encounter memory-related issues during development