#!/usr/bin/env python3
"""
DataSync Service Setup Script

This script sets up the comprehensive data synchronization system for 
maintaining consistency between PostgreSQL (OLTP) and DuckDB (OLAP).

Usage:
    python scripts/setup_data_sync.py [options]

Options:
    --initialize-services: Initialize all DataSync services
    --create-duckdb: Create DuckDB database and tables
    --setup-cdc: Setup CDC replication slots and publications
    --verify-setup: Verify the setup is working correctly
    --run-tests: Run comprehensive test suite
    --all: Run all setup steps
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

import click
import duckdb
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Add the parent directory to the path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.database import AsyncSessionLocal, sync_engine
from app.services.data_sync_service import data_sync_service
from app.services.change_data_capture import cdc_service, CDCConfiguration
from app.services.data_consistency_validator import data_consistency_service
from app.services.sync_monitoring_service import sync_monitoring_service


# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataSyncSetup:
    """Main setup class for DataSync services"""
    
    def __init__(self):
        self.setup_status = {
            'duckdb_created': False,
            'cdc_setup': False,
            'services_initialized': False,
            'verification_passed': False
        }
    
    async def create_duckdb_database(self) -> bool:
        """Create DuckDB database and required tables"""
        logger.info("Creating DuckDB database and tables...")
        
        try:
            # Ensure DuckDB directory exists
            db_path = Path(settings.DUCKDB_DATABASE_PATH)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create DuckDB connection
            conn = duckdb.connect(str(db_path))
            
            # Configure DuckDB settings
            conn.execute(f"SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}'")
            conn.execute(f"SET threads TO {settings.DUCKDB_WORKER_THREADS}")
            
            # Create directory for temporary files
            temp_dir = Path(settings.DUCKDB_TEMP_DIRECTORY)
            temp_dir.mkdir(parents=True, exist_ok=True)
            conn.execute(f"SET temp_directory='{temp_dir}'")
            
            # Install necessary extensions
            if settings.DUCKDB_ENABLE_S3:
                conn.execute("INSTALL httpfs")
                conn.execute("LOAD httpfs")
            
            # Create analytics tables based on PostgreSQL schema
            await self._create_analytics_tables(conn)
            
            conn.close()
            logger.info("✅ DuckDB database created successfully")
            self.setup_status['duckdb_created'] = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create DuckDB database: {str(e)}")
            return False
    
    async def _create_analytics_tables(self, conn: duckdb.DuckDBPyConnection):
        """Create analytics tables in DuckDB"""
        logger.info("Creating analytics tables in DuckDB...")
        
        # Get PostgreSQL table schemas
        async with AsyncSessionLocal() as session:
            # Get table information from PostgreSQL
            tables_info = await self._get_postgresql_table_schemas(session)
        
        for table_name, schema_info in tables_info.items():
            try:
                # Convert PostgreSQL schema to DuckDB schema
                duckdb_schema = self._convert_schema_to_duckdb(schema_info)
                
                # Create table
                create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({duckdb_schema})"
                conn.execute(create_sql)
                
                logger.info(f"Created table: {table_name}")
                
            except Exception as e:
                logger.warning(f"Failed to create table {table_name}: {str(e)}")
    
    async def _get_postgresql_table_schemas(self, session: AsyncSession) -> Dict[str, List[Dict]]:
        """Get PostgreSQL table schemas for analytics tables"""
        tables = ['users', 'projects', 'domains', 'pages_v2', 'project_pages', 'scrape_pages']
        schemas = {}
        
        for table_name in tables:
            try:
                # Get column information
                result = await session.execute(text(f"""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' AND table_schema = 'public'
                    ORDER BY ordinal_position
                """))
                
                columns = []
                for row in result:
                    columns.append({
                        'name': row.column_name,
                        'type': row.data_type,
                        'nullable': row.is_nullable == 'YES',
                        'default': row.column_default
                    })
                
                if columns:
                    schemas[table_name] = columns
                    
            except Exception as e:
                logger.warning(f"Failed to get schema for {table_name}: {str(e)}")
        
        return schemas
    
    def _convert_schema_to_duckdb(self, columns: List[Dict]) -> str:
        """Convert PostgreSQL column definitions to DuckDB format"""
        duckdb_columns = []
        
        type_mapping = {
            'integer': 'INTEGER',
            'bigint': 'BIGINT',
            'character varying': 'VARCHAR',
            'text': 'TEXT',
            'boolean': 'BOOLEAN',
            'timestamp with time zone': 'TIMESTAMPTZ',
            'timestamp without time zone': 'TIMESTAMP',
            'numeric': 'DECIMAL',
            'uuid': 'UUID',
            'jsonb': 'JSON',
            'json': 'JSON'
        }
        
        for col in columns:
            col_name = col['name']
            pg_type = col['type']
            nullable = col['nullable']
            
            # Map PostgreSQL type to DuckDB type
            duckdb_type = type_mapping.get(pg_type, 'VARCHAR')
            
            # Handle specific type variations
            if 'character varying' in pg_type:
                duckdb_type = 'VARCHAR'
            elif 'numeric' in pg_type:
                duckdb_type = 'DECIMAL'
            
            # Build column definition
            col_def = f"{col_name} {duckdb_type}"
            if not nullable and col_name != 'id':  # Usually allow NULL for non-primary keys
                col_def += " NOT NULL"
            
            duckdb_columns.append(col_def)
        
        return ", ".join(duckdb_columns)
    
    async def setup_cdc(self) -> bool:
        """Setup Change Data Capture infrastructure"""
        logger.info("Setting up CDC infrastructure...")
        
        try:
            # Configure CDC with monitored tables
            config = CDCConfiguration()
            config.monitored_tables = set(settings.CDC_MONITORED_TABLES.split(','))
            config.excluded_tables = set(settings.CDC_EXCLUDED_TABLES.split(','))
            
            # Initialize CDC service
            cdc_service_instance = cdc_service
            cdc_service_instance.config = config
            
            # Setup replication infrastructure
            await cdc_service_instance.initialize()
            
            logger.info("✅ CDC infrastructure setup completed")
            self.setup_status['cdc_setup'] = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to setup CDC: {str(e)}")
            return False
    
    async def initialize_services(self) -> bool:
        """Initialize all DataSync services"""
        logger.info("Initializing DataSync services...")
        
        try:
            # Initialize DataSyncService
            if settings.DATA_SYNC_ENABLED:
                await data_sync_service.initialize()
                logger.info("✅ DataSyncService initialized")
            
            # Initialize CDC Service
            if settings.CDC_ENABLED:
                await cdc_service.start()
                logger.info("✅ CDC Service started")
            
            # Initialize Monitoring Service
            if settings.ENABLE_SYNC_MONITORING:
                await sync_monitoring_service.initialize()
                logger.info("✅ Monitoring Service initialized")
            
            logger.info("✅ All services initialized successfully")
            self.setup_status['services_initialized'] = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {str(e)}")
            return False
    
    async def verify_setup(self) -> bool:
        """Verify the DataSync setup is working correctly"""
        logger.info("Verifying DataSync setup...")
        
        try:
            verification_results = {}
            
            # Test 1: Check DuckDB connection
            try:
                conn = duckdb.connect(settings.DUCKDB_DATABASE_PATH)
                conn.execute("SELECT 1")
                conn.close()
                verification_results['duckdb_connection'] = True
                logger.info("✅ DuckDB connection test passed")
            except Exception as e:
                verification_results['duckdb_connection'] = False
                logger.error(f"❌ DuckDB connection test failed: {str(e)}")
            
            # Test 2: Check PostgreSQL connection
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(text("SELECT 1"))
                verification_results['postgresql_connection'] = True
                logger.info("✅ PostgreSQL connection test passed")
            except Exception as e:
                verification_results['postgresql_connection'] = False
                logger.error(f"❌ PostgreSQL connection test failed: {str(e)}")
            
            # Test 3: Test dual-write operation
            try:
                if settings.DATA_SYNC_ENABLED:
                    success, op_id = await data_sync_service.dual_write_create(
                        table_name="test_verification",
                        data={"id": "verification_test", "name": "Setup Verification"},
                        consistency_level=data_sync_service.ConsistencyLevel.EVENTUAL
                    )
                    verification_results['dual_write'] = success
                    if success:
                        logger.info("✅ Dual-write test passed")
                    else:
                        logger.error("❌ Dual-write test failed")
                else:
                    verification_results['dual_write'] = True  # Skip if disabled
                    logger.info("ℹ️  Dual-write test skipped (disabled)")
            except Exception as e:
                verification_results['dual_write'] = False
                logger.error(f"❌ Dual-write test failed: {str(e)}")
            
            # Test 4: Check service status
            try:
                sync_status = await data_sync_service.get_sync_status()
                verification_results['sync_service'] = sync_status['service_status'] == 'running'
                if verification_results['sync_service']:
                    logger.info("✅ DataSync service status check passed")
                else:
                    logger.error("❌ DataSync service not running")
            except Exception as e:
                verification_results['sync_service'] = False
                logger.error(f"❌ Service status check failed: {str(e)}")
            
            # Test 5: Run consistency check
            try:
                if settings.CONSISTENCY_CHECK_ENABLED:
                    # Run a simple consistency check
                    report = await data_consistency_service.run_consistency_check(
                        tables=['users'],
                        check_types=[data_consistency_service.ConsistencyCheckType.ROW_COUNT]
                    )
                    verification_results['consistency_check'] = report.total_checks > 0
                    if verification_results['consistency_check']:
                        logger.info("✅ Consistency check test passed")
                    else:
                        logger.error("❌ Consistency check test failed")
                else:
                    verification_results['consistency_check'] = True  # Skip if disabled
                    logger.info("ℹ️  Consistency check test skipped (disabled)")
            except Exception as e:
                verification_results['consistency_check'] = False
                logger.error(f"❌ Consistency check test failed: {str(e)}")
            
            # Overall verification result
            all_passed = all(verification_results.values())
            
            if all_passed:
                logger.info("🎉 All verification tests passed!")
                self.setup_status['verification_passed'] = True
                return True
            else:
                failed_tests = [test for test, passed in verification_results.items() if not passed]
                logger.error(f"❌ Verification failed. Failed tests: {', '.join(failed_tests)}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Verification process failed: {str(e)}")
            return False
    
    async def run_comprehensive_tests(self) -> bool:
        """Run the comprehensive test suite"""
        logger.info("Running comprehensive DataSync tests...")
        
        try:
            import subprocess
            import sys
            
            # Run pytest on the comprehensive test suite
            result = subprocess.run([
                sys.executable, '-m', 'pytest',
                'tests/test_data_sync_comprehensive.py',
                '-v',
                '--tb=short',
                '--maxfail=5'
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
            
            if result.returncode == 0:
                logger.info("✅ All tests passed!")
                logger.info(f"Test output:\n{result.stdout}")
                return True
            else:
                logger.error("❌ Some tests failed!")
                logger.error(f"Test output:\n{result.stdout}")
                logger.error(f"Test errors:\n{result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to run tests: {str(e)}")
            return False
    
    def print_setup_summary(self):
        """Print setup summary"""
        print("\n" + "="*60)
        print("DATASYNC SETUP SUMMARY")
        print("="*60)
        
        for step, status in self.setup_status.items():
            status_icon = "✅" if status else "❌"
            print(f"{status_icon} {step.replace('_', ' ').title()}: {'COMPLETED' if status else 'FAILED'}")
        
        print("\nConfiguration:")
        print(f"  📁 DuckDB Path: {settings.DUCKDB_DATABASE_PATH}")
        print(f"  💾 DuckDB Memory Limit: {settings.DUCKDB_MEMORY_LIMIT}")
        print(f"  🔄 Data Sync Enabled: {settings.DATA_SYNC_ENABLED}")
        print(f"  📡 CDC Enabled: {settings.CDC_ENABLED}")
        print(f"  📊 Monitoring Enabled: {settings.ENABLE_SYNC_MONITORING}")
        print(f"  🔍 Consistency Checks Enabled: {settings.CONSISTENCY_CHECK_ENABLED}")
        
        if all(self.setup_status.values()):
            print(f"\n🎉 DataSync setup completed successfully!")
            print("\nNext steps:")
            print("  1. Start your application with the DataSync services")
            print("  2. Monitor sync status via the API endpoints")
            print("  3. Check logs for any issues")
            print("  4. Run periodic consistency checks")
        else:
            print(f"\n⚠️  Setup completed with some issues. Please review the logs above.")
        
        print("="*60)


# Click CLI interface
@click.command()
@click.option('--initialize-services', is_flag=True, help='Initialize all DataSync services')
@click.option('--create-duckdb', is_flag=True, help='Create DuckDB database and tables')
@click.option('--setup-cdc', is_flag=True, help='Setup CDC replication infrastructure')
@click.option('--verify-setup', is_flag=True, help='Verify the setup is working correctly')
@click.option('--run-tests', is_flag=True, help='Run comprehensive test suite')
@click.option('--all', is_flag=True, help='Run all setup steps')
def main(initialize_services, create_duckdb, setup_cdc, verify_setup, run_tests, all):
    """DataSync Service Setup Script"""
    
    # Print banner
    print("""
╔══════════════════════════════════════════════════════════╗
║                  CHRONO SCRAPER DATASYNC                 ║
║              Comprehensive Setup Script                  ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    setup = DataSyncSetup()
    
    async def run_setup():
        try:
            if all or create_duckdb:
                await setup.create_duckdb_database()
            
            if all or setup_cdc:
                await setup.setup_cdc()
            
            if all or initialize_services:
                await setup.initialize_services()
            
            if all or verify_setup:
                await setup.verify_setup()
            
            if all or run_tests:
                await setup.run_comprehensive_tests()
            
            # Print summary
            setup.print_setup_summary()
            
        except KeyboardInterrupt:
            logger.info("Setup interrupted by user")
        except Exception as e:
            logger.error(f"Setup failed with error: {str(e)}")
            raise
        finally:
            # Cleanup
            try:
                if settings.DATA_SYNC_ENABLED:
                    await data_sync_service.shutdown()
                if settings.CDC_ENABLED:
                    await cdc_service.stop()
                if settings.ENABLE_SYNC_MONITORING:
                    await sync_monitoring_service.shutdown()
            except:
                pass  # Ignore cleanup errors
    
    # Run the setup
    asyncio.run(run_setup())


if __name__ == "__main__":
    main()