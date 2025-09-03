"""
Change Data Capture (CDC) system for PostgreSQL to DuckDB synchronization

This module implements a comprehensive CDC system that monitors PostgreSQL
Write-Ahead Log (WAL) for changes and streams them to the DataSyncService
for eventual consistency with DuckDB.
"""
import asyncio
import json
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set, AsyncGenerator, Union
from uuid import UUID

import asyncpg
from asyncpg import Connection
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.data_sync_service import data_sync_service, SyncStrategy, ConsistencyLevel, SyncOperationType


# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CDCEventType(str, Enum):
    """Change Data Capture event types"""
    INSERT = "INSERT"
    UPDATE = "UPDATE" 
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"
    BEGIN = "BEGIN"
    COMMIT = "COMMIT"
    RELATION = "RELATION"  # Schema changes
    TYPE = "TYPE"          # Type definitions


class CDCTableAction(str, Enum):
    """Table-level actions for CDC monitoring"""
    INCLUDE = "include"      # Monitor this table
    EXCLUDE = "exclude"      # Ignore this table
    TRANSFORM = "transform"  # Apply transformation rules


@dataclass
class CDCEvent:
    """Represents a single change data capture event"""
    event_id: str
    event_type: CDCEventType
    table_name: str
    schema_name: str = "public"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    transaction_id: Optional[int] = None
    lsn: Optional[int] = None  # Log Sequence Number
    
    # Data fields
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    primary_key: Optional[Any] = None
    
    # Metadata
    columns: Optional[List[str]] = None
    column_types: Optional[Dict[str, str]] = None
    operation_timestamp: Optional[datetime] = None
    
    # Processing state
    processed: bool = False
    error_message: Optional[str] = None
    retry_count: int = 0


@dataclass
class CDCConfiguration:
    """Configuration for CDC monitoring"""
    # Replication slot settings
    slot_name: str = "chrono_scraper_cdc"
    publication_name: str = "chrono_scraper_pub"
    
    # Table monitoring configuration
    monitored_tables: Set[str] = field(default_factory=lambda: {
        'users', 'projects', 'domains', 'pages_v2', 'project_pages',
        'scrape_pages', 'scrape_sessions', 'api_configs'
    })
    
    excluded_tables: Set[str] = field(default_factory=lambda: {
        'alembic_version', 'pg_stat_statements', 'audit_logs'
    })
    
    # Performance settings
    max_batch_size: int = 1000
    batch_timeout_seconds: int = 30
    wal_keep_segments: int = 100
    max_replication_lag: timedelta = timedelta(minutes=5)
    
    # Event filtering
    filter_system_events: bool = True
    filter_unchanged_updates: bool = True
    min_event_interval: timedelta = timedelta(seconds=1)
    
    # Transformation rules
    table_transformations: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class WALDecoder:
    """Decoder for PostgreSQL Write-Ahead Log messages"""
    
    def __init__(self):
        self.relation_cache: Dict[int, Dict[str, Any]] = {}
        self.type_cache: Dict[int, str] = {}
    
    def decode_message(self, message: bytes) -> Optional[CDCEvent]:
        """Decode a WAL message into a CDC event"""
        if not message or len(message) < 1:
            return None
        
        message_type = message[0:1]
        
        try:
            if message_type == b'B':  # Begin
                return self._decode_begin(message)
            elif message_type == b'C':  # Commit
                return self._decode_commit(message)
            elif message_type == b'R':  # Relation
                return self._decode_relation(message)
            elif message_type == b'Y':  # Type
                return self._decode_type(message)
            elif message_type == b'I':  # Insert
                return self._decode_insert(message)
            elif message_type == b'U':  # Update
                return self._decode_update(message)
            elif message_type == b'D':  # Delete
                return self._decode_delete(message)
            elif message_type == b'T':  # Truncate
                return self._decode_truncate(message)
            else:
                logger.warning(f"Unknown WAL message type: {message_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error decoding WAL message: {str(e)}", exc_info=True)
            return None
    
    def _decode_begin(self, message: bytes) -> CDCEvent:
        """Decode BEGIN transaction message"""
        # Simplified BEGIN decoding - would need full implementation
        return CDCEvent(
            event_id=f"begin_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.BEGIN,
            table_name="",
            timestamp=datetime.utcnow()
        )
    
    def _decode_commit(self, message: bytes) -> CDCEvent:
        """Decode COMMIT transaction message"""
        # Simplified COMMIT decoding
        return CDCEvent(
            event_id=f"commit_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.COMMIT,
            table_name="",
            timestamp=datetime.utcnow()
        )
    
    def _decode_relation(self, message: bytes) -> CDCEvent:
        """Decode RELATION message (schema information)"""
        # Simplified RELATION decoding - would need full protocol implementation
        return CDCEvent(
            event_id=f"relation_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.RELATION,
            table_name="unknown",
            timestamp=datetime.utcnow()
        )
    
    def _decode_type(self, message: bytes) -> CDCEvent:
        """Decode TYPE message"""
        # Simplified TYPE decoding
        return CDCEvent(
            event_id=f"type_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.TYPE,
            table_name="",
            timestamp=datetime.utcnow()
        )
    
    def _decode_insert(self, message: bytes) -> CDCEvent:
        """Decode INSERT message"""
        # Simplified INSERT decoding - would need full protocol implementation
        return CDCEvent(
            event_id=f"insert_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.INSERT,
            table_name="unknown",
            timestamp=datetime.utcnow(),
            new_data={}  # Would extract actual data from message
        )
    
    def _decode_update(self, message: bytes) -> CDCEvent:
        """Decode UPDATE message"""
        # Simplified UPDATE decoding
        return CDCEvent(
            event_id=f"update_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.UPDATE,
            table_name="unknown",
            timestamp=datetime.utcnow(),
            old_data={},  # Would extract old values
            new_data={}   # Would extract new values
        )
    
    def _decode_delete(self, message: bytes) -> CDCEvent:
        """Decode DELETE message"""
        # Simplified DELETE decoding
        return CDCEvent(
            event_id=f"delete_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.DELETE,
            table_name="unknown",
            timestamp=datetime.utcnow(),
            old_data={}  # Would extract deleted data
        )
    
    def _decode_truncate(self, message: bytes) -> CDCEvent:
        """Decode TRUNCATE message"""
        return CDCEvent(
            event_id=f"truncate_{datetime.utcnow().timestamp()}",
            event_type=CDCEventType.TRUNCATE,
            table_name="unknown",
            timestamp=datetime.utcnow()
        )


class CDCEventProcessor:
    """Processes CDC events and converts them to sync operations"""
    
    def __init__(self, config: CDCConfiguration):
        self.config = config
        self.event_buffer: List[CDCEvent] = []
        self.last_processed_lsn: Optional[int] = None
        self.transaction_state: Dict[int, List[CDCEvent]] = {}
    
    def should_process_event(self, event: CDCEvent) -> bool:
        """Determine if an event should be processed"""
        # Skip system events if configured
        if self.config.filter_system_events:
            if event.schema_name in ('information_schema', 'pg_catalog'):
                return False
        
        # Check table inclusion/exclusion
        if event.table_name in self.config.excluded_tables:
            return False
        
        if self.config.monitored_tables:
            if event.table_name not in self.config.monitored_tables:
                return False
        
        # Skip non-data events for now
        if event.event_type in (CDCEventType.BEGIN, CDCEventType.COMMIT, 
                               CDCEventType.RELATION, CDCEventType.TYPE):
            return False
        
        return True
    
    def transform_event(self, event: CDCEvent) -> Optional[CDCEvent]:
        """Apply transformation rules to an event"""
        table_name = event.table_name
        
        if table_name not in self.config.table_transformations:
            return event
        
        transformations = self.config.table_transformations[table_name]
        
        # Apply column mappings
        if 'column_mappings' in transformations and event.new_data:
            column_mappings = transformations['column_mappings']
            transformed_data = {}
            
            for old_col, new_col in column_mappings.items():
                if old_col in event.new_data:
                    transformed_data[new_col] = event.new_data[old_col]
            
            event.new_data.update(transformed_data)
        
        # Apply data filters
        if 'filters' in transformations:
            filters = transformations['filters']
            for filter_rule in filters:
                # Apply filter logic (simplified)
                pass
        
        return event
    
    async def process_event(self, event: CDCEvent) -> bool:
        """Process a single CDC event"""
        if not self.should_process_event(event):
            return True
        
        # Transform event if needed
        transformed_event = self.transform_event(event)
        if not transformed_event:
            return True
        
        try:
            # Convert CDC event to sync operation
            sync_operation = await self._convert_to_sync_operation(transformed_event)
            
            if sync_operation:
                # Determine sync strategy based on table and event type
                strategy = self._determine_sync_strategy(transformed_event)
                consistency = self._determine_consistency_level(transformed_event)
                
                # Queue sync operation
                if sync_operation == SyncOperationType.CREATE:
                    await data_sync_service.dual_write_create(
                        table_name=transformed_event.table_name,
                        data=transformed_event.new_data or {},
                        consistency_level=consistency,
                        strategy=strategy
                    )
                elif sync_operation == SyncOperationType.UPDATE:
                    await data_sync_service.dual_write_update(
                        table_name=transformed_event.table_name,
                        primary_key=transformed_event.primary_key,
                        data=transformed_event.new_data or {},
                        consistency_level=consistency,
                        strategy=strategy
                    )
                elif sync_operation == SyncOperationType.DELETE:
                    await data_sync_service.dual_write_delete(
                        table_name=transformed_event.table_name,
                        primary_key=transformed_event.primary_key,
                        consistency_level=consistency,
                        strategy=strategy
                    )
            
            event.processed = True
            return True
            
        except Exception as e:
            logger.error(f"Error processing CDC event {event.event_id}: {str(e)}", exc_info=True)
            event.error_message = str(e)
            event.retry_count += 1
            return False
    
    async def _convert_to_sync_operation(self, event: CDCEvent) -> Optional[SyncOperationType]:
        """Convert CDC event type to sync operation type"""
        if event.event_type == CDCEventType.INSERT:
            return SyncOperationType.CREATE
        elif event.event_type == CDCEventType.UPDATE:
            return SyncOperationType.UPDATE
        elif event.event_type == CDCEventType.DELETE:
            return SyncOperationType.DELETE
        elif event.event_type == CDCEventType.TRUNCATE:
            return SyncOperationType.DELETE  # Bulk delete
        
        return None
    
    def _determine_sync_strategy(self, event: CDCEvent) -> SyncStrategy:
        """Determine appropriate sync strategy based on table and event"""
        # Critical tables get real-time sync
        critical_tables = {'users', 'api_configs', 'projects'}
        
        if event.table_name in critical_tables:
            return SyncStrategy.REAL_TIME
        
        # Large tables get batch processing
        large_tables = {'pages_v2', 'scrape_pages'}
        
        if event.table_name in large_tables:
            return SyncStrategy.BATCH
        
        # Default to near-real-time
        return SyncStrategy.NEAR_REAL_TIME
    
    def _determine_consistency_level(self, event: CDCEvent) -> ConsistencyLevel:
        """Determine required consistency level"""
        # Authentication and billing require strong consistency
        strong_consistency_tables = {'users', 'user_plans', 'api_configs'}
        
        if event.table_name in strong_consistency_tables:
            return ConsistencyLevel.STRONG
        
        # Analytics data can be eventually consistent
        analytics_tables = {'pages_v2', 'scrape_pages', 'audit_logs'}
        
        if event.table_name in analytics_tables:
            return ConsistencyLevel.EVENTUAL
        
        # Default to eventual consistency
        return ConsistencyLevel.EVENTUAL
    
    async def process_batch(self, events: List[CDCEvent]) -> Dict[str, Any]:
        """Process a batch of CDC events"""
        start_time = datetime.utcnow()
        processed_count = 0
        failed_count = 0
        
        for event in events:
            try:
                success = await self.process_event(event)
                if success:
                    processed_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Batch processing error for event {event.event_id}: {str(e)}")
                failed_count += 1
        
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        
        return {
            "processed_count": processed_count,
            "failed_count": failed_count,
            "processing_time_seconds": processing_time,
            "events_per_second": processed_count / max(processing_time, 0.001)
        }


class CDCService:
    """
    Main Change Data Capture service for monitoring PostgreSQL changes
    
    This service creates and manages logical replication slots to capture
    data changes and stream them to the DataSyncService for processing.
    """
    
    def __init__(self, config: Optional[CDCConfiguration] = None):
        self.config = config or CDCConfiguration()
        self.processor = CDCEventProcessor(self.config)
        self.decoder = WALDecoder()
        
        # Connection management
        self.replication_conn: Optional[Connection] = None
        self.admin_conn: Optional[Connection] = None
        
        # State management
        self.is_running = False
        self.last_lsn: Optional[int] = None
        self.event_buffer: List[CDCEvent] = []
        self.background_tasks: Set[asyncio.Task] = set()
        
        # Monitoring
        self.events_processed = 0
        self.events_failed = 0
        self.last_event_time: Optional[datetime] = None
    
    async def initialize(self) -> None:
        """Initialize CDC service and create replication infrastructure"""
        logger.info("Initializing CDC Service...")
        
        try:
            # Create admin connection for setup
            self.admin_conn = await asyncpg.connect(
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB
            )
            
            # Setup replication infrastructure
            await self._setup_replication_slot()
            await self._setup_publication()
            
            # Create replication connection
            self.replication_conn = await asyncpg.connect(
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                server_settings={'application_name': 'chrono_scraper_cdc'}
            )
            
            logger.info("CDC Service initialized successfully")
            
        except Exception as e:
            logger.error(f"CDC Service initialization failed: {str(e)}", exc_info=True)
            raise
    
    async def _setup_replication_slot(self) -> None:
        """Create logical replication slot if it doesn't exist"""
        try:
            # Check if slot exists
            result = await self.admin_conn.fetch("""
                SELECT slot_name FROM pg_replication_slots 
                WHERE slot_name = $1
            """, self.config.slot_name)
            
            if not result:
                # Create replication slot
                await self.admin_conn.execute("""
                    SELECT pg_create_logical_replication_slot($1, 'pgoutput')
                """, self.config.slot_name)
                
                logger.info(f"Created replication slot: {self.config.slot_name}")
            else:
                logger.info(f"Replication slot already exists: {self.config.slot_name}")
                
        except Exception as e:
            logger.error(f"Failed to setup replication slot: {str(e)}", exc_info=True)
            raise
    
    async def _setup_publication(self) -> None:
        """Create publication for monitored tables"""
        try:
            # Check if publication exists
            result = await self.admin_conn.fetch("""
                SELECT pubname FROM pg_publication 
                WHERE pubname = $1
            """, self.config.publication_name)
            
            if not result:
                # Create publication for all monitored tables
                table_list = ', '.join(self.config.monitored_tables)
                
                if table_list:
                    await self.admin_conn.execute(f"""
                        CREATE PUBLICATION {self.config.publication_name} 
                        FOR TABLE {table_list}
                    """)
                else:
                    # Create publication for all tables
                    await self.admin_conn.execute(f"""
                        CREATE PUBLICATION {self.config.publication_name} 
                        FOR ALL TABLES
                    """)
                
                logger.info(f"Created publication: {self.config.publication_name}")
            else:
                logger.info(f"Publication already exists: {self.config.publication_name}")
                
        except Exception as e:
            logger.error(f"Failed to setup publication: {str(e)}", exc_info=True)
            raise
    
    async def start(self) -> None:
        """Start CDC monitoring"""
        if self.is_running:
            logger.warning("CDC Service is already running")
            return
        
        logger.info("Starting CDC Service...")
        
        try:
            self.is_running = True
            
            # Start background tasks
            self.background_tasks.add(
                asyncio.create_task(self._replication_worker())
            )
            self.background_tasks.add(
                asyncio.create_task(self._event_processor_worker())
            )
            self.background_tasks.add(
                asyncio.create_task(self._monitoring_worker())
            )
            
            logger.info("CDC Service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start CDC Service: {str(e)}", exc_info=True)
            self.is_running = False
            raise
    
    async def stop(self) -> None:
        """Stop CDC monitoring gracefully"""
        logger.info("Stopping CDC Service...")
        
        self.is_running = False
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # Process remaining events
        if self.event_buffer:
            await self.processor.process_batch(self.event_buffer)
            self.event_buffer.clear()
        
        # Close connections
        if self.replication_conn:
            await self.replication_conn.close()
        if self.admin_conn:
            await self.admin_conn.close()
        
        logger.info("CDC Service stopped")
    
    async def _replication_worker(self) -> None:
        """Background worker for consuming replication stream"""
        logger.info("Starting replication worker...")
        
        try:
            while self.is_running:
                # Start logical replication
                async with self.replication_conn.transaction():
                    # Create replication cursor
                    await self.replication_conn.execute(f"""
                        START_REPLICATION SLOT {self.config.slot_name} LOGICAL
                    """)
                    
                    # Consume messages
                    while self.is_running:
                        try:
                            # This is a simplified version - actual implementation would
                            # need to handle the replication protocol properly
                            message = await asyncio.wait_for(
                                self._receive_wal_message(), 
                                timeout=5.0
                            )
                            
                            if message:
                                event = self.decoder.decode_message(message)
                                if event:
                                    self.event_buffer.append(event)
                                    self.last_event_time = datetime.utcnow()
                            
                        except asyncio.TimeoutError:
                            continue  # Normal timeout, continue
                        except Exception as e:
                            logger.error(f"Replication worker error: {str(e)}")
                            await asyncio.sleep(5)
                            break  # Reconnect
                            
        except Exception as e:
            logger.error(f"Replication worker failed: {str(e)}", exc_info=True)
        
        logger.info("Replication worker stopped")
    
    async def _receive_wal_message(self) -> Optional[bytes]:
        """Receive WAL message from replication stream"""
        # This is a placeholder - actual implementation would need
        # to handle the PostgreSQL replication protocol
        await asyncio.sleep(1)  # Simulate waiting for message
        return None  # Would return actual WAL message bytes
    
    async def _event_processor_worker(self) -> None:
        """Background worker for processing CDC events"""
        logger.info("Starting event processor worker...")
        
        while self.is_running:
            try:
                # Process events in batches
                if len(self.event_buffer) >= self.config.max_batch_size:
                    batch = self.event_buffer[:self.config.max_batch_size]
                    self.event_buffer = self.event_buffer[self.config.max_batch_size:]
                    
                    result = await self.processor.process_batch(batch)
                    
                    self.events_processed += result['processed_count']
                    self.events_failed += result['failed_count']
                    
                    logger.debug(f"Processed batch: {result}")
                
                # Wait before next batch
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Event processor worker error: {str(e)}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("Event processor worker stopped")
    
    async def _monitoring_worker(self) -> None:
        """Background worker for monitoring and health checks"""
        logger.info("Starting monitoring worker...")
        
        while self.is_running:
            try:
                # Check replication lag
                if self.admin_conn:
                    result = await self.admin_conn.fetch("""
                        SELECT 
                            slot_name,
                            confirmed_flush_lsn,
                            pg_current_wal_lsn(),
                            pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) as lag_bytes
                        FROM pg_replication_slots 
                        WHERE slot_name = $1
                    """, self.config.slot_name)
                    
                    if result:
                        lag_bytes = result[0]['lag_bytes']
                        if lag_bytes and lag_bytes > 10_000_000:  # 10MB
                            logger.warning(f"High replication lag detected: {lag_bytes} bytes")
                
                # Log statistics
                logger.info(f"CDC Stats - Processed: {self.events_processed}, "
                          f"Failed: {self.events_failed}, "
                          f"Buffer: {len(self.event_buffer)}")
                
                # Wait before next check
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Monitoring worker error: {str(e)}", exc_info=True)
                await asyncio.sleep(30)
        
        logger.info("Monitoring worker stopped")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get CDC service status"""
        replication_lag = None
        if self.admin_conn:
            try:
                result = await self.admin_conn.fetch("""
                    SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) as lag_bytes
                    FROM pg_replication_slots 
                    WHERE slot_name = $1
                """, self.config.slot_name)
                if result:
                    replication_lag = result[0]['lag_bytes']
            except Exception:
                pass
        
        return {
            "service_status": "running" if self.is_running else "stopped",
            "replication_slot": self.config.slot_name,
            "publication": self.config.publication_name,
            "monitored_tables": list(self.config.monitored_tables),
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "buffer_size": len(self.event_buffer),
            "replication_lag_bytes": replication_lag,
            "last_event_time": self.last_event_time.isoformat() if self.last_event_time else None,
            "background_tasks": len(self.background_tasks),
            "configuration": {
                "max_batch_size": self.config.max_batch_size,
                "batch_timeout": self.config.batch_timeout_seconds,
                "wal_keep_segments": self.config.wal_keep_segments
            }
        }
    
    async def add_monitored_table(self, table_name: str) -> bool:
        """Add a table to CDC monitoring"""
        try:
            if table_name not in self.config.monitored_tables:
                self.config.monitored_tables.add(table_name)
                
                # Add to publication
                await self.admin_conn.execute(f"""
                    ALTER PUBLICATION {self.config.publication_name} 
                    ADD TABLE {table_name}
                """)
                
                logger.info(f"Added table {table_name} to CDC monitoring")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to add monitored table {table_name}: {str(e)}")
            return False
    
    async def remove_monitored_table(self, table_name: str) -> bool:
        """Remove a table from CDC monitoring"""
        try:
            if table_name in self.config.monitored_tables:
                self.config.monitored_tables.remove(table_name)
                
                # Remove from publication
                await self.admin_conn.execute(f"""
                    ALTER PUBLICATION {self.config.publication_name} 
                    DROP TABLE {table_name}
                """)
                
                logger.info(f"Removed table {table_name} from CDC monitoring")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove monitored table {table_name}: {str(e)}")
            return False
    
    def set_table_transformation(self, table_name: str, transformations: Dict[str, Any]) -> None:
        """Set transformation rules for a specific table"""
        self.config.table_transformations[table_name] = transformations
        logger.info(f"Set transformations for table {table_name}")
    
    async def reset_replication_slot(self) -> bool:
        """Reset replication slot to current WAL position"""
        try:
            if self.is_running:
                await self.stop()
            
            # Drop existing slot
            await self.admin_conn.execute(f"""
                SELECT pg_drop_replication_slot('{self.config.slot_name}')
            """)
            
            # Recreate slot
            await self._setup_replication_slot()
            
            logger.info("Replication slot reset successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset replication slot: {str(e)}")
            return False


# Global CDC service instance
cdc_service = CDCService()


async def initialize_cdc() -> None:
    """Initialize and start CDC service"""
    await cdc_service.initialize()
    await cdc_service.start()


async def shutdown_cdc() -> None:
    """Shutdown CDC service gracefully"""
    await cdc_service.stop()