# DuckDB Integration Research for FastAPI + SQLModel Application

## Executive Summary

This research provides comprehensive DuckDB integration patterns for a production FastAPI application with SQLModel, focusing on hybrid OLTP (PostgreSQL) + OLAP (DuckDB) architecture for analytical workloads.

## 1. Connection Management & Async Integration

### 1.1 DuckDB Async Wrapper Pattern

```python
import asyncio
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import duckdb
from concurrent.futures import ThreadPoolExecutor

class AsyncDuckDBConnectionManager:
    """Async wrapper for DuckDB with connection pooling"""
    
    def __init__(self, database_path: str = ":memory:", max_workers: int = 4):
        self.database_path = database_path
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._local = threading.local()
        self._connection_count = 0
        
    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Thread-local connection management"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = duckdb.connect(self.database_path)
            # Load required extensions
            self._local.connection.execute("INSTALL httpfs")
            self._local.connection.execute("LOAD httpfs")
            self._connection_count += 1
        return self._local.connection
    
    async def execute(self, query: str, parameters=None):
        """Execute query asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self._get_connection().execute(query, parameters).fetchall()
        )
    
    async def fetch_df(self, query: str, parameters=None):
        """Fetch results as pandas DataFrame"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            lambda: self._get_connection().execute(query, parameters).df()
        )
    
    async def execute_many(self, queries: list[str]):
        """Execute multiple queries concurrently"""
        tasks = [self.execute(query) for query in queries]
        return await asyncio.gather(*tasks)
    
    def close(self):
        """Close all connections"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
        self.executor.shutdown(wait=True)
```

### 1.2 FastAPI Integration with Dependency Injection

```python
from fastapi import Depends, FastAPI
from contextlib import asynccontextmanager

# Global connection manager
duckdb_manager: Optional[AsyncDuckDBConnectionManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global duckdb_manager
    duckdb_manager = AsyncDuckDBConnectionManager(
        database_path="/data/analytics.duckdb",
        max_workers=8
    )
    
    # Initialize S3 credentials
    await duckdb_manager.execute("""
        CREATE SECRET analytics_s3 (
            TYPE S3,
            PROVIDER CREDENTIAL_CHAIN,
            CHAIN 'env;config',
            REGION 'us-east-1'
        )
    """)
    
    yield
    
    # Shutdown
    if duckdb_manager:
        duckdb_manager.close()

app = FastAPI(lifespan=lifespan)

async def get_duckdb() -> AsyncDuckDBConnectionManager:
    """Dependency for DuckDB connection manager"""
    if not duckdb_manager:
        raise RuntimeError("DuckDB not initialized")
    return duckdb_manager
```

## 2. Memory Optimization & Production Configuration

### 2.1 Memory Management Configuration

```python
class DuckDBConfig:
    """Production DuckDB configuration"""
    
    @staticmethod
    def get_memory_config(server_ram_gb: int) -> dict:
        """Calculate optimal memory settings based on server RAM"""
        # Use 60% of RAM for DuckDB (leaving room for OS and other processes)
        memory_limit = max(1, int(server_ram_gb * 0.6))
        threads = min(8, server_ram_gb // 2)  # 1-2GB per thread
        
        return {
            "memory_limit": f"{memory_limit}GB",
            "threads": threads,
            "temp_directory": "/tmp/duckdb",
            "max_memory": f"{memory_limit}GB",
            "preserve_insertion_order": "false",  # Better memory usage for large datasets
            "enable_progress_bar": "true",
            "enable_profiling": "true",
        }
    
    @staticmethod
    async def configure_connection(conn: AsyncDuckDBConnectionManager, server_ram_gb: int = 8):
        """Apply production configuration"""
        config = DuckDBConfig.get_memory_config(server_ram_gb)
        
        configuration_queries = [
            f"SET memory_limit = '{config['memory_limit']}'",
            f"SET threads TO {config['threads']}",
            f"SET temp_directory = '{config['temp_directory']}'",
            f"SET preserve_insertion_order = {config['preserve_insertion_order']}",
            "SET enable_progress_bar = true",
            "SET enable_profiling = true",
        ]
        
        await conn.execute_many(configuration_queries)
```

### 2.2 Docker Configuration

```yaml
# docker-compose.analytics.yml
version: '3.8'

services:
  analytics-service:
    build: 
      context: .
      dockerfile: Dockerfile.analytics
    environment:
      - DUCKDB_MEMORY_LIMIT=6GB
      - DUCKDB_THREADS=8
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
    volumes:
      - analytics_data:/data
      - /tmp/duckdb:/tmp/duckdb:rw
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4'
        reservations:
          memory: 4G
          cpus: '2'
    healthcheck:
      test: ["CMD", "python", "-c", "import duckdb; duckdb.connect('/data/analytics.duckdb').execute('SELECT 1')"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  analytics_data:
    driver: local
```

## 3. Extension Setup & S3 Integration

### 3.1 Required Extensions Initialization

```python
class DuckDBExtensionManager:
    """Manages DuckDB extensions and S3 configuration"""
    
    REQUIRED_EXTENSIONS = ["httpfs", "parquet", "json", "fts"]
    
    @staticmethod
    async def initialize_extensions(conn: AsyncDuckDBConnectionManager):
        """Install and load all required extensions"""
        for extension in DuckDBExtensionManager.REQUIRED_EXTENSIONS:
            await conn.execute(f"INSTALL {extension}")
            await conn.execute(f"LOAD {extension}")
    
    @staticmethod
    async def configure_s3_storage(conn: AsyncDuckDBConnectionManager, 
                                 bucket: str, region: str = "us-east-1"):
        """Configure S3 storage with credential chain"""
        await conn.execute(f"""
            CREATE OR REPLACE SECRET s3_storage (
                TYPE S3,
                PROVIDER CREDENTIAL_CHAIN,
                CHAIN 'env;config;instance',
                REGION '{region}'
            )
        """)
        
        # Test S3 connectivity
        try:
            await conn.execute(f"SELECT COUNT(*) FROM read_parquet('s3://{bucket}/*.parquet') LIMIT 1")
            print(f"✓ S3 bucket {bucket} accessible")
        except Exception as e:
            print(f"⚠ S3 bucket {bucket} test failed: {e}")
```

### 3.2 Parquet Data Management

```python
class ParquetDataManager:
    """Manages Parquet data operations with S3"""
    
    def __init__(self, conn: AsyncDuckDBConnectionManager):
        self.conn = conn
    
    async def export_to_s3_partitioned(self, table_name: str, s3_path: str, 
                                     partition_cols: list[str]):
        """Export table to S3 with partitioning"""
        partition_clause = ", ".join(partition_cols) if partition_cols else ""
        query = f"""
            COPY {table_name} TO '{s3_path}' (
                FORMAT parquet,
                PARTITION_BY ({partition_clause}),
                OVERWRITE_OR_IGNORE true
            )
        """
        await self.conn.execute(query)
    
    async def import_from_s3(self, s3_path: str, table_name: str, 
                           create_table: bool = True):
        """Import data from S3 Parquet files"""
        if create_table:
            query = f"""
                CREATE TABLE {table_name} AS 
                SELECT * FROM read_parquet('{s3_path}')
            """
        else:
            query = f"""
                INSERT INTO {table_name} 
                SELECT * FROM read_parquet('{s3_path}')
            """
        
        await self.conn.execute(query)
    
    async def optimize_parquet_storage(self, table_name: str, s3_path: str):
        """Optimize Parquet storage with compression and ordering"""
        query = f"""
            COPY (
                SELECT * FROM {table_name} 
                ORDER BY created_at DESC, id
            ) TO '{s3_path}' (
                FORMAT parquet,
                COMPRESSION 'zstd',
                ROW_GROUP_SIZE 100000
            )
        """
        await self.conn.execute(query)
```

## 4. Data Type Mapping: PostgreSQL ↔ DuckDB

### 4.1 Type Mapping Configuration

```python
from typing import Dict, Type
from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

# PostgreSQL to DuckDB type mapping
POSTGRES_TO_DUCKDB_TYPE_MAPPING: Dict[str, str] = {
    "INTEGER": "INTEGER",
    "BIGINT": "BIGINT", 
    "SERIAL": "INTEGER",
    "BIGSERIAL": "BIGINT",
    "VARCHAR": "VARCHAR",
    "TEXT": "VARCHAR",
    "BOOLEAN": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMPTZ": "TIMESTAMPTZ",
    "DATE": "DATE",
    "DECIMAL": "DECIMAL",
    "NUMERIC": "DECIMAL",
    "FLOAT": "DOUBLE",
    "REAL": "REAL",
    "DOUBLE PRECISION": "DOUBLE",
    "UUID": "UUID",
    "JSONB": "JSON",
    "JSON": "JSON",
    "ARRAY": "LIST",
}

class AnalyticsModelMixin:
    """Mixin for models that will be replicated to DuckDB"""
    
    @classmethod
    def get_duckdb_schema(cls) -> str:
        """Generate DuckDB CREATE TABLE statement"""
        fields = []
        
        for field_name, field_info in cls.model_fields.items():
            postgres_type = cls._get_postgres_type(field_info)
            duckdb_type = POSTGRES_TO_DUCKDB_TYPE_MAPPING.get(postgres_type, "VARCHAR")
            
            nullable = "NULL" if field_info.default is None else "NOT NULL"
            fields.append(f"{field_name} {duckdb_type} {nullable}")
        
        return f"CREATE TABLE {cls.__tablename__} ({', '.join(fields)})"
    
    @classmethod  
    def _get_postgres_type(cls, field_info) -> str:
        """Map Python type to PostgreSQL type"""
        python_type = field_info.annotation
        
        if python_type == int:
            return "INTEGER"
        elif python_type == str:
            return "VARCHAR"
        elif python_type == bool:
            return "BOOLEAN"
        elif python_type == datetime:
            return "TIMESTAMP"
        elif python_type == uuid.UUID:
            return "UUID"
        else:
            return "VARCHAR"  # Default fallback
```

### 4.2 Model Synchronization

```python
class HybridDataSync:
    """Synchronizes data between PostgreSQL and DuckDB"""
    
    def __init__(self, postgres_session, duckdb_conn: AsyncDuckDBConnectionManager):
        self.postgres = postgres_session
        self.duckdb = duckdb_conn
    
    async def sync_model_to_analytics(self, model_class: Type[SQLModel], 
                                    incremental: bool = True):
        """Sync PostgreSQL model data to DuckDB"""
        table_name = model_class.__tablename__
        
        # Create or update DuckDB table schema
        create_query = model_class.get_duckdb_schema()
        await self.duckdb.execute(f"CREATE TABLE IF NOT EXISTS {table_name}_analytics AS {create_query}")
        
        # Get incremental sync timestamp if needed
        last_sync = None
        if incremental:
            try:
                result = await self.duckdb.execute(f"SELECT MAX(updated_at) FROM {table_name}_analytics")
                last_sync = result[0][0] if result and result[0][0] else None
            except:
                pass  # Table doesn't exist or no updated_at column
        
        # Extract data from PostgreSQL
        if last_sync and incremental:
            pg_query = f"SELECT * FROM {table_name} WHERE updated_at > %s"
            pg_data = await self.postgres.execute(text(pg_query), (last_sync,))
        else:
            pg_query = f"SELECT * FROM {table_name}"
            pg_data = await self.postgres.execute(text(pg_query))
        
        # Convert to format suitable for DuckDB
        if pg_data.rowcount > 0:
            # Clear existing data if full sync
            if not incremental:
                await self.duckdb.execute(f"DELETE FROM {table_name}_analytics")
            
            # Insert new data
            rows = [dict(row) for row in pg_data]
            await self._bulk_insert_duckdb(f"{table_name}_analytics", rows)
    
    async def _bulk_insert_duckdb(self, table_name: str, data: list[dict]):
        """Bulk insert data into DuckDB table"""
        if not data:
            return
            
        # Create temporary table from data
        temp_table = f"temp_{table_name}_{int(datetime.now().timestamp())}"
        
        # Use DuckDB's direct DataFrame insertion
        import pandas as pd
        df = pd.DataFrame(data)
        
        # This requires some adjustment based on your async wrapper
        await self.duckdb.execute(f"CREATE TABLE {temp_table} AS SELECT * FROM df")
        await self.duckdb.execute(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")
        await self.duckdb.execute(f"DROP TABLE {temp_table}")
```

## 5. Performance Configuration & Query Optimization

### 5.1 Query Optimization Patterns

```python
class AnalyticsQueryOptimizer:
    """Optimizes analytical queries for DuckDB"""
    
    @staticmethod
    def build_optimized_query(base_query: str, filters: dict, 
                            order_by: str = None, limit: int = None) -> str:
        """Build optimized analytical query with proper indexing hints"""
        
        # Add filters early to reduce data scanning
        where_clauses = []
        for column, value in filters.items():
            if isinstance(value, (list, tuple)):
                where_clauses.append(f"{column} IN ({','.join(repr(v) for v in value)})")
            else:
                where_clauses.append(f"{column} = {repr(value)}")
        
        query = base_query
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        if order_by:
            query += f" ORDER BY {order_by}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return query
    
    @staticmethod
    def create_analytical_indexes(conn: AsyncDuckDBConnectionManager, 
                                table_name: str, columns: list[str]):
        """Create optimized indexes for analytical queries"""
        # DuckDB doesn't use traditional indexes, but we can optimize with:
        # 1. Sorted data for better compression
        # 2. Partitioned tables for pruning
        # 3. Proper column order
        
        # This is more about data organization than indexing
        return f"""
            CREATE TABLE {table_name}_optimized AS 
            SELECT * FROM {table_name} 
            ORDER BY {', '.join(columns)}
        """
```

### 5.2 Monitoring and Metrics

```python
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class QueryMetrics:
    query: str
    duration_ms: float
    rows_processed: int
    memory_used_mb: float
    error: Optional[str] = None

class DuckDBMonitor:
    """Monitors DuckDB performance metrics"""
    
    def __init__(self, conn: AsyncDuckDBConnectionManager):
        self.conn = conn
        self.metrics: list[QueryMetrics] = []
    
    async def execute_with_metrics(self, query: str, parameters=None) -> QueryMetrics:
        """Execute query and collect performance metrics"""
        start_time = time.time()
        error = None
        rows_processed = 0
        memory_used_mb = 0
        
        try:
            # Enable profiling
            await self.conn.execute("PRAGMA enable_profiling=json")
            
            # Execute query
            result = await self.conn.execute(query, parameters)
            rows_processed = len(result) if result else 0
            
            # Get profiling info
            profile_result = await self.conn.execute("PRAGMA show_profiles")
            if profile_result:
                # Parse memory usage from profile (simplified)
                memory_used_mb = self._parse_memory_usage(profile_result)
            
        except Exception as e:
            error = str(e)
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = QueryMetrics(
            query=query[:200] + "..." if len(query) > 200 else query,
            duration_ms=duration_ms,
            rows_processed=rows_processed,
            memory_used_mb=memory_used_mb,
            error=error
        )
        
        self.metrics.append(metrics)
        return metrics
    
    def _parse_memory_usage(self, profile_data) -> float:
        """Parse memory usage from DuckDB profiling output"""
        # This would need to be implemented based on actual profile format
        return 0.0  # Placeholder
    
    async def get_performance_summary(self) -> dict:
        """Get performance summary statistics"""
        if not self.metrics:
            return {}
        
        successful_metrics = [m for m in self.metrics if not m.error]
        
        return {
            "total_queries": len(self.metrics),
            "successful_queries": len(successful_metrics),
            "error_rate": (len(self.metrics) - len(successful_metrics)) / len(self.metrics),
            "avg_duration_ms": sum(m.duration_ms for m in successful_metrics) / len(successful_metrics) if successful_metrics else 0,
            "total_rows_processed": sum(m.rows_processed for m in successful_metrics),
            "avg_memory_mb": sum(m.memory_used_mb for m in successful_metrics) / len(successful_metrics) if successful_metrics else 0,
        }
```

## 6. Error Handling & Circuit Breakers

### 6.1 DuckDB-Specific Error Handling

```python
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta

class DuckDBErrorType(Enum):
    MEMORY_ERROR = "memory_error"
    CONNECTION_ERROR = "connection_error"
    SYNTAX_ERROR = "syntax_error"
    IO_ERROR = "io_error"
    TIMEOUT_ERROR = "timeout_error"

@dataclass
class CircuitBreakerState:
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    state: str = "closed"  # closed, open, half_open
    failure_threshold: int = 5
    timeout_duration: timedelta = field(default_factory=lambda: timedelta(seconds=60))

class DuckDBCircuitBreaker:
    """Circuit breaker for DuckDB operations"""
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.state = CircuitBreakerState(
            failure_threshold=failure_threshold,
            timeout_duration=timedelta(seconds=timeout_seconds)
        )
    
    def _classify_error(self, error: Exception) -> DuckDBErrorType:
        """Classify DuckDB errors for appropriate handling"""
        error_msg = str(error).lower()
        
        if "memory" in error_msg or "out of memory" in error_msg:
            return DuckDBErrorType.MEMORY_ERROR
        elif "connection" in error_msg or "database" in error_msg:
            return DuckDBErrorType.CONNECTION_ERROR
        elif "syntax" in error_msg or "parser" in error_msg:
            return DuckDBErrorType.SYNTAX_ERROR
        elif "io" in error_msg or "file" in error_msg:
            return DuckDBErrorType.IO_ERROR
        else:
            return DuckDBErrorType.TIMEOUT_ERROR
    
    async def execute_with_circuit_breaker(self, operation, *args, **kwargs):
        """Execute operation with circuit breaker protection"""
        
        # Check circuit breaker state
        if self.state.state == "open":
            if datetime.now() - self.state.last_failure > self.state.timeout_duration:
                self.state.state = "half_open"
            else:
                raise RuntimeError("Circuit breaker is OPEN - DuckDB operations suspended")
        
        try:
            result = await operation(*args, **kwargs)
            
            # Reset on success
            if self.state.state == "half_open":
                self.state.state = "closed"
                self.state.failure_count = 0
            
            return result
            
        except Exception as e:
            error_type = self._classify_error(e)
            
            # Count failures
            self.state.failure_count += 1
            self.state.last_failure = datetime.now()
            
            # Open circuit breaker if threshold exceeded
            if self.state.failure_count >= self.state.failure_threshold:
                self.state.state = "open"
            
            # Handle different error types
            if error_type == DuckDBErrorType.MEMORY_ERROR:
                # Try to recover by reducing memory usage
                await self._handle_memory_error()
            elif error_type == DuckDBErrorType.CONNECTION_ERROR:
                # Try to reconnect
                await self._handle_connection_error()
            
            raise
    
    async def _handle_memory_error(self):
        """Handle memory-related errors"""
        # Could implement memory cleanup, temp file cleanup, etc.
        pass
    
    async def _handle_connection_error(self):
        """Handle connection-related errors"""
        # Could implement connection reset logic
        pass
```

## 7. Backup & Disaster Recovery

### 7.1 Backup Strategies

```python
import shutil
import gzip
import boto3
from pathlib import Path
from datetime import datetime

class DuckDBBackupManager:
    """Manages DuckDB backup and disaster recovery"""
    
    def __init__(self, database_path: str, backup_location: str, s3_bucket: str = None):
        self.database_path = Path(database_path)
        self.backup_location = Path(backup_location)
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3') if s3_bucket else None
    
    async def create_backup(self, compress: bool = True) -> str:
        """Create a backup of the DuckDB database"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"duckdb_backup_{timestamp}.db"
        
        if compress:
            backup_filename += ".gz"
        
        backup_path = self.backup_location / backup_filename
        self.backup_location.mkdir(parents=True, exist_ok=True)
        
        if compress:
            with open(self.database_path, 'rb') as f_in:
                with gzip.open(backup_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(self.database_path, backup_path)
        
        # Upload to S3 if configured
        if self.s3_client:
            await self._upload_to_s3(backup_path, f"backups/{backup_filename}")
        
        return str(backup_path)
    
    async def restore_from_backup(self, backup_path: str) -> bool:
        """Restore database from backup"""
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            return False
        
        # Stop any active connections first
        # This would need coordination with your connection manager
        
        if backup_path.endswith('.gz'):
            with gzip.open(backup_file, 'rb') as f_in:
                with open(self.database_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_file, self.database_path)
        
        return True
    
    async def _upload_to_s3(self, local_path: Path, s3_key: str):
        """Upload backup to S3"""
        if self.s3_client:
            self.s3_client.upload_file(str(local_path), self.s3_bucket, s3_key)
    
    async def cleanup_old_backups(self, retention_days: int = 30):
        """Clean up backups older than retention period"""
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        
        for backup_file in self.backup_location.glob("duckdb_backup_*.db*"):
            if backup_file.stat().st_mtime < cutoff_time.timestamp():
                backup_file.unlink()
    
    async def validate_backup(self, backup_path: str) -> bool:
        """Validate that a backup file is not corrupted"""
        try:
            # Test database integrity
            test_conn = duckdb.connect(backup_path, read_only=True)
            test_conn.execute("SELECT COUNT(*) FROM information_schema.tables")
            test_conn.close()
            return True
        except Exception:
            return False
```

### 7.2 Disaster Recovery Automation

```python
class DuckDBDisasterRecovery:
    """Automated disaster recovery for DuckDB"""
    
    def __init__(self, backup_manager: DuckDBBackupManager):
        self.backup_manager = backup_manager
    
    async def automated_backup_schedule(self):
        """Run automated backups on schedule"""
        # Daily full backup
        try:
            backup_path = await self.backup_manager.create_backup(compress=True)
            
            # Validate backup
            if await self.backup_manager.validate_backup(backup_path):
                print(f"✓ Backup successful: {backup_path}")
                
                # Cleanup old backups
                await self.backup_manager.cleanup_old_backups(retention_days=30)
            else:
                print(f"⚠ Backup validation failed: {backup_path}")
                
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            # Could send alerts here
    
    async def health_check(self, conn: AsyncDuckDBConnectionManager) -> dict:
        """Comprehensive health check"""
        health_status = {
            "database_accessible": False,
            "memory_usage": None,
            "table_count": None,
            "last_backup": None,
            "disk_space_mb": None,
        }
        
        try:
            # Test basic connectivity
            await conn.execute("SELECT 1")
            health_status["database_accessible"] = True
            
            # Check table count
            result = await conn.execute("SELECT COUNT(*) FROM information_schema.tables")
            health_status["table_count"] = result[0][0] if result else 0
            
            # Check memory usage
            memory_result = await conn.execute("SELECT current_setting('memory_limit')")
            health_status["memory_usage"] = memory_result[0][0] if memory_result else None
            
            # Check disk space
            db_size = self.backup_manager.database_path.stat().st_size / (1024 * 1024)
            health_status["disk_space_mb"] = db_size
            
        except Exception as e:
            health_status["error"] = str(e)
        
        return health_status
```

## 8. Production Deployment Example

### 8.1 Complete FastAPI Integration

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Initialize FastAPI app with DuckDB
app = FastAPI(
    title="Analytics API with DuckDB",
    version="1.0.0",
    lifespan=lifespan  # From earlier example
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Analytics endpoints
@app.get("/analytics/query")
async def execute_analytics_query(
    query: str,
    duckdb: AsyncDuckDBConnectionManager = Depends(get_duckdb)
):
    """Execute analytical query"""
    try:
        # Add safety checks for query
        if not query.strip().upper().startswith('SELECT'):
            raise HTTPException(status_code=400, detail="Only SELECT queries allowed")
        
        result = await duckdb.fetch_df(query)
        return {
            "data": result.to_dict('records'),
            "row_count": len(result),
            "columns": list(result.columns)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")

@app.get("/analytics/health")
async def analytics_health_check(
    duckdb: AsyncDuckDBConnectionManager = Depends(get_duckdb)
):
    """Health check for analytics system"""
    disaster_recovery = DuckDBDisasterRecovery(
        DuckDBBackupManager("/data/analytics.duckdb", "/backups")
    )
    
    health = await disaster_recovery.health_check(duckdb)
    return health

@app.post("/analytics/sync/{model_name}")
async def sync_model_data(
    model_name: str,
    incremental: bool = True,
    duckdb: AsyncDuckDBConnectionManager = Depends(get_duckdb)
):
    """Sync data from PostgreSQL to DuckDB"""
    # This would need your actual PostgreSQL session
    # sync_manager = HybridDataSync(postgres_session, duckdb)
    # await sync_manager.sync_model_to_analytics(model_class, incremental)
    return {"status": "sync_completed", "model": model_name}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        workers=1  # DuckDB works best with single worker
    )
```

### 8.2 Kubernetes Deployment

```yaml
# kubernetes/duckdb-analytics.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: analytics-api
spec:
  replicas: 1  # DuckDB single-writer limitation
  selector:
    matchLabels:
      app: analytics-api
  template:
    metadata:
      labels:
        app: analytics-api
    spec:
      containers:
      - name: analytics-api
        image: your-registry/analytics-api:latest
        ports:
        - containerPort: 8001
        env:
        - name: DUCKDB_MEMORY_LIMIT
          value: "6GB"
        - name: DUCKDB_THREADS
          value: "8"
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
        volumeMounts:
        - name: analytics-storage
          mountPath: /data
        - name: backup-storage
          mountPath: /backups
      volumes:
      - name: analytics-storage
        persistentVolumeClaim:
          claimName: analytics-pvc
      - name: backup-storage
        persistentVolumeClaim:
          claimName: backup-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: analytics-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: fast-ssd
```

## 9. Common Pitfalls & Gotchas

### 9.1 Critical Considerations

1. **Single Writer Limitation**: DuckDB only supports one writer at a time. Design your architecture accordingly.

2. **Memory Management**: Default 80% RAM usage can cause OOM. Always set explicit memory limits.

3. **Docker Temp Files**: In containers, temp files can fill up disk. Mount dedicated temp directory.

4. **Connection Pooling**: Thread-local connections work better than traditional pooling.

5. **Async Overhead**: DuckDB is synchronous. Use thread pools judiciously.

6. **S3 Credentials**: Use credential chains, not hardcoded keys.

7. **Backup Validation**: Always validate backups - corruption can occur silently.

8. **Version Compatibility**: Stick to stable releases for production.

### 9.2 Performance Optimization Checklist

- [ ] Set appropriate memory limits (60-80% of available RAM)
- [ ] Configure optimal thread count (1-4GB per thread)
- [ ] Use SSD storage for database files
- [ ] Enable compression for Parquet exports
- [ ] Implement connection reuse patterns
- [ ] Monitor query performance and memory usage
- [ ] Set up automated backups with validation
- [ ] Configure circuit breakers for reliability
- [ ] Use partitioned Parquet files for large datasets
- [ ] Implement proper error handling and retry logic

## 10. Integration Timeline & Migration Strategy

### Phase 1: Foundation (Week 1-2)
1. Set up async DuckDB connection manager
2. Configure Docker environment with proper resources
3. Implement basic health checks and monitoring

### Phase 2: Data Integration (Week 3-4) 
1. Create PostgreSQL → DuckDB sync processes
2. Set up S3 integration for Parquet storage
3. Implement basic analytical endpoints

### Phase 3: Production Readiness (Week 5-6)
1. Add circuit breakers and error handling
2. Implement backup and disaster recovery
3. Performance optimization and monitoring

### Phase 4: Advanced Features (Week 7-8)
1. Advanced analytics endpoints
2. Real-time sync mechanisms
3. Monitoring dashboards and alerting

This comprehensive integration approach provides a production-ready DuckDB solution that complements your existing PostgreSQL infrastructure while enabling powerful analytical capabilities.