# DataSync Service - Comprehensive Documentation

## Overview

The DataSync Service is a production-ready solution for maintaining data consistency between PostgreSQL (OLTP) and DuckDB (OLAP) databases in the Chrono Scraper application. It implements dual-write patterns, change data capture (CDC), consistency validation, and comprehensive monitoring to ensure reliable data synchronization.

## Architecture

### Core Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Application   │ -> │  DataSyncService │ -> │   PostgreSQL    │
│     Layer       │    │   (Dual-Write)   │    │     (OLTP)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                v
                       ┌──────────────────┐    ┌─────────────────┐
                       │ CDC & Validation │ -> │     DuckDB      │
                       │     System       │    │    (OLAP)       │
                       └──────────────────┘    └─────────────────┘
                                │
                                v
                       ┌──────────────────┐
                       │   Monitoring &   │
                       │    Alerting      │
                       └──────────────────┘
```

### Key Features

- **Dual-Write Patterns**: Synchronous and asynchronous dual-write operations
- **Change Data Capture**: PostgreSQL WAL-based CDC with logical replication
- **Consistency Validation**: Comprehensive data consistency checking
- **Circuit Breakers**: Service protection against cascading failures
- **Recovery Mechanisms**: Automatic retry and manual recovery options
- **Monitoring & Alerting**: Real-time monitoring with Prometheus metrics
- **API Management**: RESTful API for sync operations and monitoring

## Quick Start

### 1. Installation

The DataSync service is included with the Chrono Scraper backend. Ensure you have the required dependencies:

```bash
# Install additional dependencies for DuckDB and monitoring
pip install duckdb prometheus_client asyncpg
```

### 2. Configuration

Add the following configuration to your `.env` file:

```bash
# Core Data Sync Settings
DATA_SYNC_ENABLED=true
DATA_SYNC_STRATEGY=hybrid
DATA_SYNC_BATCH_SIZE=10000
DATA_SYNC_CONSISTENCY_LEVEL=eventual

# DuckDB Configuration
DUCKDB_DATABASE_PATH=/data/analytics.duckdb
DUCKDB_MEMORY_LIMIT=4GB
DUCKDB_WORKER_THREADS=4

# CDC Configuration
CDC_ENABLED=true
CDC_MONITORED_TABLES=users,projects,domains,pages_v2,project_pages
CDC_REPLICATION_SLOT_NAME=chrono_scraper_cdc

# Monitoring Configuration
ENABLE_SYNC_MONITORING=true
SYNC_LAG_ALERT_THRESHOLD_MINUTES=15
CONSISTENCY_SCORE_ALERT_THRESHOLD=90.0
```

### 3. Setup

Run the setup script to initialize the DataSync system:

```bash
# Run complete setup
python backend/scripts/setup_data_sync.py --all

# Or run individual steps
python backend/scripts/setup_data_sync.py --create-duckdb
python backend/scripts/setup_data_sync.py --setup-cdc
python backend/scripts/setup_data_sync.py --initialize-services
python backend/scripts/setup_data_sync.py --verify-setup
```

### 4. Start Services

The DataSync services are automatically initialized when starting the FastAPI application:

```bash
# Start with Docker Compose
make up

# Or start manually
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Service Components

### 1. DataSyncService

The core synchronization service that handles dual-write operations.

**Key Features:**
- Multiple consistency levels (Strong, Eventual, Weak)
- Various sync strategies (Real-time, Near-real-time, Batch, Recovery)
- Circuit breakers for service protection
- Dead letter queue for failed operations

**Usage:**
```python
from app.services.data_sync_service import data_sync_service, ConsistencyLevel, SyncStrategy

# Create with strong consistency
success, operation_id = await data_sync_service.dual_write_create(
    table_name="users",
    data={"id": "user_123", "name": "John Doe"},
    consistency_level=ConsistencyLevel.STRONG,
    strategy=SyncStrategy.REAL_TIME
)

# Update with eventual consistency
success, operation_id = await data_sync_service.dual_write_update(
    table_name="projects",
    primary_key="project_456",
    data={"status": "completed"},
    consistency_level=ConsistencyLevel.EVENTUAL
)
```

### 2. Change Data Capture (CDC)

Monitors PostgreSQL changes using logical replication and streams them to DuckDB.

**Features:**
- WAL-based change detection
- Logical replication slots
- Event filtering and transformation
- Batch processing for performance

**Configuration:**
```python
from app.services.change_data_capture import CDCConfiguration

config = CDCConfiguration()
config.monitored_tables = {"users", "projects", "pages_v2"}
config.excluded_tables = {"audit_logs", "system_logs"}
config.max_batch_size = 1000
```

### 3. Data Consistency Validator

Validates data consistency between PostgreSQL and DuckDB.

**Validation Types:**
- **Row Count**: Compare record counts between databases
- **Data Hash**: Validate data integrity using SHA256 hashes
- **Business Rules**: Check domain-specific business constraints
- **Referential Integrity**: Validate foreign key relationships

**Usage:**
```python
from app.services.data_consistency_validator import data_consistency_service

# Run comprehensive consistency check
report = await data_consistency_service.run_consistency_check(
    tables=["users", "projects"],
    check_types=["row_count", "data_hash", "business_rules"]
)

print(f"Consistency Score: {report.consistency_score}%")
```

### 4. Monitoring Service

Comprehensive monitoring and alerting for sync operations.

**Features:**
- Prometheus metrics
- Real-time alerts
- Performance tracking
- Health checks
- Dashboard data

## API Endpoints

### Sync Management

```bash
# Get sync status
GET /api/v1/data-sync/sync/status

# Create sync operation
POST /api/v1/data-sync/sync/operation
{
  "table_name": "users",
  "operation_type": "create",
  "data": {"id": "123", "name": "John"},
  "consistency_level": "strong",
  "strategy": "real_time"
}

# Trigger full table sync
POST /api/v1/data-sync/sync/table/users/full?batch_size=5000

# Get dead letter queue
GET /api/v1/data-sync/sync/dead-letter-queue
```

### Consistency Validation

```bash
# Run consistency check
POST /api/v1/data-sync/consistency/check
{
  "tables": ["users", "projects"],
  "check_types": ["row_count", "data_hash"]
}

# Get consistency status
GET /api/v1/data-sync/consistency/status

# Validate specific table
GET /api/v1/data-sync/consistency/validate/users?primary_key=123
```

### Monitoring

```bash
# Get monitoring dashboard
GET /api/v1/data-sync/monitoring/dashboard

# Get health status
GET /api/v1/data-sync/monitoring/health

# Get active alerts
GET /api/v1/data-sync/monitoring/alerts

# Get Prometheus metrics
GET /api/v1/data-sync/monitoring/metrics/prometheus
```

## Configuration Reference

### Core Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `DATA_SYNC_ENABLED` | `true` | Enable/disable data synchronization |
| `DATA_SYNC_STRATEGY` | `hybrid` | Sync strategy: real_time, near_real_time, batch, hybrid |
| `DATA_SYNC_BATCH_SIZE` | `10000` | Batch size for sync operations |
| `DATA_SYNC_CONSISTENCY_LEVEL` | `eventual` | Default consistency level |
| `ENABLE_DUAL_WRITE` | `true` | Enable dual-write mechanism |

### DuckDB Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `DUCKDB_DATABASE_PATH` | `/data/analytics.duckdb` | Path to DuckDB database file |
| `DUCKDB_MEMORY_LIMIT` | `2GB` | Memory limit for DuckDB operations |
| `DUCKDB_WORKER_THREADS` | `4` | Number of worker threads |
| `DUCKDB_ENABLE_S3` | `false` | Enable S3 extension |

### CDC Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `CDC_ENABLED` | `true` | Enable Change Data Capture |
| `CDC_REPLICATION_SLOT_NAME` | `chrono_scraper_cdc` | PostgreSQL replication slot name |
| `CDC_MONITORED_TABLES` | `users,projects,pages_v2` | Tables to monitor |
| `CDC_MAX_BATCH_SIZE` | `1000` | Maximum CDC batch size |

### Monitoring Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ENABLE_SYNC_MONITORING` | `true` | Enable monitoring service |
| `SYNC_LAG_ALERT_THRESHOLD_MINUTES` | `15` | Alert threshold for sync lag |
| `CONSISTENCY_SCORE_ALERT_THRESHOLD` | `90.0` | Alert threshold for consistency score |
| `DEAD_LETTER_QUEUE_ALERT_THRESHOLD` | `100` | Alert threshold for DLQ size |

## Performance Tuning

### Sync Performance

1. **Batch Size Optimization**
   ```bash
   # Adjust batch size based on your workload
   DATA_SYNC_BATCH_SIZE=5000  # Smaller for low latency
   DATA_SYNC_BATCH_SIZE=25000 # Larger for high throughput
   ```

2. **Concurrency Settings**
   ```bash
   MAX_CONCURRENT_SYNC_OPERATIONS=5   # Reduce for memory-constrained systems
   SYNC_WORKER_BATCH_SIZE=50          # Adjust based on record size
   ```

3. **Queue Management**
   ```bash
   REAL_TIME_QUEUE_SIZE=1000          # For low-latency operations
   BATCH_QUEUE_SIZE=50000             # For high-volume operations
   ```

### DuckDB Performance

1. **Memory Configuration**
   ```bash
   DUCKDB_MEMORY_LIMIT=8GB            # Adjust based on available RAM
   DUCKDB_WORKER_THREADS=8            # Match CPU cores
   ```

2. **Storage Optimization**
   ```bash
   PARQUET_COMPRESSION=ZSTD           # Best compression ratio
   PARQUET_ROW_GROUP_SIZE=1000000     # Optimize for query patterns
   ```

## Monitoring and Troubleshooting

### Key Metrics to Monitor

1. **Sync Lag**: Time difference between PostgreSQL and DuckDB
2. **Queue Depth**: Number of pending sync operations
3. **Success Rate**: Percentage of successful sync operations
4. **Consistency Score**: Overall data consistency percentage

### Common Issues and Solutions

#### High Sync Lag
```bash
# Check queue status
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/data-sync/sync/status

# Solutions:
# 1. Increase batch size
# 2. Add more worker threads
# 3. Check resource utilization
```

#### Consistency Issues
```bash
# Run consistency check
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"tables": ["users"], "check_types": ["row_count"]}' \
  http://localhost:8000/api/v1/data-sync/consistency/check

# Solutions:
# 1. Run full table resync
# 2. Check CDC configuration
# 3. Verify network connectivity
```

#### Dead Letter Queue Buildup
```bash
# Check dead letter queue
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/data-sync/sync/dead-letter-queue

# Retry failed operations
curl -X POST -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/data-sync/sync/dead-letter-queue/<operation_id>/retry
```

### Health Checks

```bash
# Overall health status
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/data-sync/monitoring/health

# Service-specific checks
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/data-sync/sync/status

curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/data-sync/cdc/status
```

## Testing

### Unit Tests

```bash
# Run all DataSync tests
python -m pytest tests/test_data_sync_comprehensive.py -v

# Run specific test categories
python -m pytest tests/test_data_sync_comprehensive.py::TestDataSyncService -v
python -m pytest tests/test_data_sync_comprehensive.py::TestCDCService -v
```

### Integration Tests

```bash
# Run integration tests with Docker
docker-compose -f docker-compose.test.yml up --build
python -m pytest tests/test_data_sync_comprehensive.py::TestDataSyncIntegration -v
```

### Load Testing

```bash
# Performance tests
python -m pytest tests/test_data_sync_comprehensive.py::TestDataSyncPerformance -v
```

## Disaster Recovery

### Backup Procedures

1. **PostgreSQL Backup**
   ```bash
   pg_dump -h localhost -p 5435 -U chrono_scraper chrono_scraper > backup.sql
   ```

2. **DuckDB Backup**
   ```bash
   cp /data/analytics.duckdb /backups/analytics_$(date +%Y%m%d).duckdb
   ```

### Recovery Procedures

1. **Full Resynchronization**
   ```bash
   # Reset and resync all tables
   python backend/scripts/setup_data_sync.py --create-duckdb
   
   # Trigger full sync for each table
   curl -X POST http://localhost:8000/api/v1/data-sync/sync/table/users/full
   ```

2. **Point-in-Time Recovery**
   ```bash
   # Restore from backup and sync since timestamp
   curl -X POST \
     -d '{"since": "2024-01-01T00:00:00Z"}' \
     http://localhost:8000/api/v1/data-sync/sync/table/users/incremental
   ```

## Best Practices

### Development

1. **Always test dual-write operations** in development environment
2. **Monitor consistency scores** regularly
3. **Use appropriate consistency levels** for different data types
4. **Implement proper error handling** for sync operations

### Production

1. **Set up monitoring alerts** for key metrics
2. **Regularly backup both databases**
3. **Monitor resource usage** (CPU, memory, disk I/O)
4. **Plan for capacity scaling** based on data growth

### Troubleshooting

1. **Check logs** for error messages and warnings
2. **Monitor queue depths** to identify bottlenecks
3. **Run consistency checks** after major operations
4. **Use dead letter queue** to handle persistent failures

## Support and Maintenance

### Regular Maintenance Tasks

1. **Weekly**: Review consistency reports and resolve conflicts
2. **Monthly**: Analyze performance metrics and tune configuration
3. **Quarterly**: Test disaster recovery procedures

### Scaling Considerations

1. **Horizontal Scaling**: Deploy multiple sync workers
2. **Vertical Scaling**: Increase memory and CPU resources
3. **Data Partitioning**: Consider partitioning large tables
4. **Index Optimization**: Optimize indexes for sync queries

## Changelog

### Version 2.0.0 (Current)
- Initial release of comprehensive DataSync system
- Dual-write patterns with multiple consistency levels
- Change Data Capture with PostgreSQL logical replication
- Comprehensive consistency validation framework
- Real-time monitoring and alerting system
- RESTful API for sync management
- Production-ready error handling and recovery mechanisms

## License

This DataSync service is part of the Chrono Scraper project and follows the same license terms.