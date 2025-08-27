#!/usr/bin/env python3
"""
Database Maintenance and Operational Excellence Scripts
Comprehensive database administration toolkit for Chrono Scraper v2

This module provides essential database maintenance operations including:
- Automated backup management with retention policies
- Database performance monitoring and optimization
- User access management and security auditing
- Health checks and alerting integration
- Backup verification and disaster recovery testing

Usage:
    python db_maintenance.py backup --type=full --retention-days=30
    python db_maintenance.py vacuum --analyze --tables=scrape_pages,pages
    python db_maintenance.py monitor --alert-thresholds
    python db_maintenance.py users --audit --export-report
"""

import os
import sys
import argparse
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import subprocess
import json
import shutil
from dataclasses import dataclass
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Database connections
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import redis

# Configuration
BACKUP_DIR = Path("/app/backups")
BACKUP_DIR.mkdir(exist_ok=True)

LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'db_maintenance.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database configuration parameters"""
    host: str = os.getenv('POSTGRES_HOST', 'postgres')
    port: int = int(os.getenv('POSTGRES_PORT', '5432'))
    database: str = os.getenv('POSTGRES_DB', 'chrono_scraper')
    username: str = os.getenv('POSTGRES_USER', 'chrono_scraper')
    password: str = os.getenv('POSTGRES_PASSWORD', 'chrono_scraper_dev')
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class BackupConfig:
    """Backup configuration and policies"""
    retention_days: int = 30
    compression_level: int = 6
    verify_backups: bool = True
    encrypt_backups: bool = False
    max_parallel_backups: int = 2
    
class DatabaseMaintenance:
    """Main database maintenance class"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.backup_config = BackupConfig()
        
    def get_connection(self) -> psycopg2.extensions.connection:
        """Get database connection with proper error handling"""
        try:
            conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                connect_timeout=10
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            return conn
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def create_backup(self, backup_type: str = "full", tables: Optional[List[str]] = None) -> str:
        """
        Create database backup with intelligent compression and verification
        
        Args:
            backup_type: 'full', 'schema', 'data', or 'incremental'
            tables: Specific tables to backup (None for all)
            
        Returns:
            Path to created backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"chrono_scraper_{backup_type}_{timestamp}"
        
        if backup_type == "incremental":
            backup_name += "_incremental"
            
        backup_path = BACKUP_DIR / f"{backup_name}.sql"
        compressed_path = BACKUP_DIR / f"{backup_name}.sql.gz"
        
        logger.info(f"Creating {backup_type} backup: {backup_name}")
        
        try:
            # Build pg_dump command
            cmd = [
                "pg_dump",
                "-h", self.config.host,
                "-p", str(self.config.port),
                "-U", self.config.username,
                "-d", self.config.database,
                "-v",  # Verbose output
                "-f", str(backup_path)
            ]
            
            # Add backup type specific flags
            if backup_type == "schema":
                cmd.extend(["-s", "--no-privileges", "--no-owner"])
            elif backup_type == "data":
                cmd.extend(["-a", "--no-privileges", "--no-owner"])
            elif backup_type == "full":
                cmd.extend(["-c", "-b", "--no-privileges", "--no-owner"])
                
            # Add table filters if specified
            if tables:
                for table in tables:
                    cmd.extend(["-t", table])
            
            # Set password via environment
            env = os.environ.copy()
            env["PGPASSWORD"] = self.config.password
            
            # Execute backup
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"pg_dump failed: {result.stderr}")
                raise RuntimeError(f"Backup failed: {result.stderr}")
            
            logger.info(f"Backup created successfully: {backup_path}")
            
            # Compress backup
            if self.backup_config.compression_level > 0:
                logger.info("Compressing backup...")
                compress_result = subprocess.run([
                    "gzip", f"-{self.backup_config.compression_level}", str(backup_path)
                ], capture_output=True, text=True)
                
                if compress_result.returncode == 0:
                    backup_path = compressed_path
                    logger.info(f"Backup compressed: {backup_path}")
                else:
                    logger.warning(f"Compression failed: {compress_result.stderr}")
            
            # Verify backup if enabled
            if self.backup_config.verify_backups:
                if self.verify_backup(backup_path):
                    logger.info("Backup verification successful")
                else:
                    logger.error("Backup verification failed")
                    raise RuntimeError("Backup verification failed")
            
            # Record backup in database
            self.record_backup_metadata(backup_path, backup_type, tables)
            
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            # Clean up partial backup
            if backup_path.exists():
                backup_path.unlink()
            if compressed_path.exists():
                compressed_path.unlink()
            raise
    
    def verify_backup(self, backup_path: Path) -> bool:
        """Verify backup integrity and content"""
        logger.info(f"Verifying backup: {backup_path}")
        
        try:
            # Check file exists and is readable
            if not backup_path.exists():
                logger.error("Backup file does not exist")
                return False
            
            file_size = backup_path.stat().st_size
            if file_size < 1024:  # Less than 1KB is suspicious
                logger.error(f"Backup file suspiciously small: {file_size} bytes")
                return False
            
            # Calculate checksum
            checksum = self.calculate_checksum(backup_path)
            logger.info(f"Backup checksum: {checksum}")
            
            # Test restore to temporary database (in real environment)
            # For now, we'll do a basic integrity check
            if str(backup_path).endswith('.gz'):
                # Verify gzip integrity
                result = subprocess.run(['gzip', '-t', str(backup_path)], 
                                      capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Compressed backup integrity check failed: {result.stderr}")
                    return False
            
            logger.info("Backup verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Backup verification error: {e}")
            return False
    
    def calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def record_backup_metadata(self, backup_path: str, backup_type: str, tables: Optional[List[str]]):
        """Record backup metadata in database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create backup metadata table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backup_metadata (
                    id SERIAL PRIMARY KEY,
                    backup_name VARCHAR(255) NOT NULL,
                    backup_path TEXT NOT NULL,
                    backup_type VARCHAR(50) NOT NULL,
                    file_size BIGINT,
                    checksum VARCHAR(64),
                    tables_included TEXT[],
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    verified BOOLEAN DEFAULT FALSE,
                    retention_until TIMESTAMP WITH TIME ZONE
                );
            """)
            
            file_size = Path(backup_path).stat().st_size
            checksum = self.calculate_checksum(Path(backup_path))
            retention_until = datetime.now() + timedelta(days=self.backup_config.retention_days)
            
            cursor.execute("""
                INSERT INTO backup_metadata 
                (backup_name, backup_path, backup_type, file_size, checksum, 
                 tables_included, verified, retention_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                Path(backup_path).stem,
                backup_path,
                backup_type,
                file_size,
                checksum,
                tables or [],
                self.backup_config.verify_backups,
                retention_until
            ))
            
            logger.info("Backup metadata recorded successfully")
            
        except Exception as e:
            logger.error(f"Failed to record backup metadata: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        logger.info("Starting backup cleanup process")
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Find expired backups
            cursor.execute("""
                SELECT backup_path FROM backup_metadata 
                WHERE retention_until < NOW()
            """)
            
            expired_backups = cursor.fetchall()
            
            for (backup_path,) in expired_backups:
                try:
                    if Path(backup_path).exists():
                        Path(backup_path).unlink()
                        logger.info(f"Deleted expired backup: {backup_path}")
                    
                    # Remove from metadata
                    cursor.execute("""
                        DELETE FROM backup_metadata 
                        WHERE backup_path = %s
                    """, (backup_path,))
                    
                except Exception as e:
                    logger.error(f"Failed to delete backup {backup_path}: {e}")
            
            logger.info(f"Cleanup completed. Removed {len(expired_backups)} expired backups")
            
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def vacuum_analyze(self, tables: Optional[List[str]] = None, full: bool = False):
        """Perform VACUUM and ANALYZE operations"""
        logger.info("Starting VACUUM ANALYZE operation")
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if tables:
                # VACUUM specific tables
                for table in tables:
                    vacuum_cmd = f"VACUUM {'FULL' if full else ''} ANALYZE {table}"
                    logger.info(f"Executing: {vacuum_cmd}")
                    cursor.execute(vacuum_cmd)
            else:
                # VACUUM entire database
                vacuum_cmd = f"VACUUM {'FULL' if full else ''} ANALYZE"
                logger.info(f"Executing: {vacuum_cmd}")
                cursor.execute(vacuum_cmd)
            
            logger.info("VACUUM ANALYZE completed successfully")
            
        except Exception as e:
            logger.error(f"VACUUM ANALYZE failed: {e}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            stats = {}
            
            # Database size
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as db_size,
                       pg_database_size(current_database()) as db_size_bytes
            """)
            db_size = cursor.fetchone()
            stats['database_size'] = {
                'formatted': db_size[0],
                'bytes': db_size[1]
            }
            
            # Table statistics
            cursor.execute("""
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes,
                    n_tup_ins as inserts,
                    n_tup_upd as updates,
                    n_tup_del as deletes,
                    n_live_tup as live_tuples,
                    n_dead_tup as dead_tuples,
                    last_vacuum,
                    last_autovacuum,
                    last_analyze,
                    last_autoanalyze
                FROM pg_stat_user_tables 
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 20
            """)
            
            table_stats = []
            for row in cursor.fetchall():
                table_stats.append({
                    'schema': row[0],
                    'table': row[1],
                    'size_formatted': row[2],
                    'size_bytes': row[3],
                    'inserts': row[4],
                    'updates': row[5],
                    'deletes': row[6],
                    'live_tuples': row[7],
                    'dead_tuples': row[8],
                    'last_vacuum': row[9],
                    'last_autovacuum': row[10],
                    'last_analyze': row[11],
                    'last_autoanalyze': row[12]
                })
            
            stats['tables'] = table_stats
            
            # Connection statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_connections,
                    COUNT(*) FILTER (WHERE state = 'active') as active_connections,
                    COUNT(*) FILTER (WHERE state = 'idle') as idle_connections,
                    COUNT(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)
            
            conn_stats = cursor.fetchone()
            stats['connections'] = {
                'total': conn_stats[0],
                'active': conn_stats[1],
                'idle': conn_stats[2],
                'idle_in_transaction': conn_stats[3]
            }
            
            # Slow queries (from pg_stat_statements if available)
            try:
                cursor.execute("""
                    SELECT 
                        query,
                        calls,
                        total_time,
                        mean_time,
                        rows
                    FROM pg_stat_statements
                    ORDER BY mean_time DESC
                    LIMIT 10
                """)
                
                slow_queries = []
                for row in cursor.fetchall():
                    slow_queries.append({
                        'query': row[0][:200] + '...' if len(row[0]) > 200 else row[0],
                        'calls': row[1],
                        'total_time': row[2],
                        'mean_time': row[3],
                        'rows': row[4]
                    })
                
                stats['slow_queries'] = slow_queries
                
            except psycopg2.Error:
                # pg_stat_statements not available
                stats['slow_queries'] = []
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get database statistics: {e}")
            return {}
        finally:
            if 'conn' in locals():
                conn.close()
    
    def monitor_replication(self) -> Dict[str, Any]:
        """Monitor replication status and lag"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            replication_stats = {}
            
            # Check if this is a primary or replica
            cursor.execute("SELECT pg_is_in_recovery()")
            is_replica = cursor.fetchone()[0]
            
            replication_stats['is_replica'] = is_replica
            
            if is_replica:
                # Replica-specific monitoring
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() 
                            THEN 0 
                            ELSE EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::int 
                        END as lag_seconds,
                        pg_last_wal_receive_lsn() as receive_lsn,
                        pg_last_wal_replay_lsn() as replay_lsn
                """)
                
                replica_stats = cursor.fetchone()
                replication_stats.update({
                    'lag_seconds': replica_stats[0],
                    'receive_lsn': str(replica_stats[1]),
                    'replay_lsn': str(replica_stats[2])
                })
                
            else:
                # Primary-specific monitoring
                cursor.execute("""
                    SELECT 
                        client_addr,
                        state,
                        sent_lsn,
                        write_lsn,
                        flush_lsn,
                        replay_lsn,
                        write_lag,
                        flush_lag,
                        replay_lag,
                        sync_state
                    FROM pg_stat_replication
                """)
                
                replicas = []
                for row in cursor.fetchall():
                    replicas.append({
                        'client_addr': row[0],
                        'state': row[1],
                        'sent_lsn': str(row[2]),
                        'write_lsn': str(row[3]),
                        'flush_lsn': str(row[4]),
                        'replay_lsn': str(row[5]),
                        'write_lag': str(row[6]) if row[6] else None,
                        'flush_lag': str(row[7]) if row[7] else None,
                        'replay_lag': str(row[8]) if row[8] else None,
                        'sync_state': row[9]
                    })
                
                replication_stats['replicas'] = replicas
            
            return replication_stats
            
        except Exception as e:
            logger.error(f"Failed to monitor replication: {e}")
            return {}
        finally:
            if 'conn' in locals():
                conn.close()
    
    def audit_users(self) -> Dict[str, Any]:
        """Comprehensive user access audit"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            audit_report = {}
            
            # Get all database users and roles
            cursor.execute("""
                SELECT 
                    rolname,
                    rolsuper,
                    rolcreaterole,
                    rolcreatedb,
                    rolcanlogin,
                    rolreplication,
                    rolconnlimit,
                    rolvaliduntil
                FROM pg_roles
                ORDER BY rolname
            """)
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'username': row[0],
                    'is_superuser': row[1],
                    'can_create_roles': row[2],
                    'can_create_databases': row[3],
                    'can_login': row[4],
                    'can_replicate': row[5],
                    'connection_limit': row[6],
                    'valid_until': row[7]
                })
            
            audit_report['users'] = users
            
            # Get current active sessions
            cursor.execute("""
                SELECT 
                    usename,
                    client_addr,
                    state,
                    backend_start,
                    query_start,
                    state_change,
                    application_name
                FROM pg_stat_activity
                WHERE state != 'idle' AND usename IS NOT NULL
                ORDER BY backend_start
            """)
            
            active_sessions = []
            for row in cursor.fetchall():
                active_sessions.append({
                    'username': row[0],
                    'client_addr': str(row[1]) if row[1] else 'local',
                    'state': row[2],
                    'backend_start': row[3],
                    'query_start': row[4],
                    'state_change': row[5],
                    'application_name': row[6]
                })
            
            audit_report['active_sessions'] = active_sessions
            
            # Check for suspicious activity patterns
            cursor.execute("""
                SELECT 
                    usename,
                    COUNT(*) as connection_count,
                    COUNT(DISTINCT client_addr) as unique_ips,
                    MAX(backend_start) as latest_connection
                FROM pg_stat_activity
                WHERE usename IS NOT NULL
                GROUP BY usename
                ORDER BY connection_count DESC
            """)
            
            connection_patterns = []
            for row in cursor.fetchall():
                connection_patterns.append({
                    'username': row[0],
                    'connection_count': row[1],
                    'unique_ips': row[2],
                    'latest_connection': row[3]
                })
            
            audit_report['connection_patterns'] = connection_patterns
            
            return audit_report
            
        except Exception as e:
            logger.error(f"User audit failed: {e}")
            return {}
        finally:
            if 'conn' in locals():
                conn.close()
    
    def generate_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive database health report"""
        logger.info("Generating database health report")
        
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'database': self.config.database,
            'host': self.config.host
        }
        
        try:
            # Basic connectivity test
            conn = self.get_connection()
            health_report['connectivity'] = 'OK'
            conn.close()
            
            # Database statistics
            health_report['statistics'] = self.get_database_stats()
            
            # Replication status
            health_report['replication'] = self.monitor_replication()
            
            # User audit
            health_report['users'] = self.audit_users()
            
            # Check disk space
            disk_usage = shutil.disk_usage(BACKUP_DIR)
            health_report['disk_space'] = {
                'total_gb': round(disk_usage.total / (1024**3), 2),
                'used_gb': round(disk_usage.used / (1024**3), 2),
                'free_gb': round(disk_usage.free / (1024**3), 2),
                'used_percentage': round((disk_usage.used / disk_usage.total) * 100, 2)
            }
            
            # Redis health (if available)
            try:
                redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'redis'), port=6379, db=0)
                redis_info = redis_client.info()
                health_report['redis'] = {
                    'status': 'OK',
                    'used_memory_human': redis_info.get('used_memory_human'),
                    'connected_clients': redis_info.get('connected_clients'),
                    'uptime_in_seconds': redis_info.get('uptime_in_seconds')
                }
            except Exception as e:
                health_report['redis'] = {'status': 'ERROR', 'error': str(e)}
            
            # Overall health status
            issues = []
            
            # Check for high disk usage
            if health_report['disk_space']['used_percentage'] > 85:
                issues.append('High disk usage detected')
            
            # Check for replication lag
            if health_report['replication'].get('lag_seconds', 0) > 60:
                issues.append('High replication lag detected')
            
            # Check for too many connections
            if health_report['statistics'].get('connections', {}).get('total', 0) > 80:
                issues.append('High connection count')
            
            health_report['overall_status'] = 'CRITICAL' if len(issues) > 2 else 'WARNING' if issues else 'OK'
            health_report['issues'] = issues
            
            return health_report
            
        except Exception as e:
            logger.error(f"Health report generation failed: {e}")
            health_report['connectivity'] = 'ERROR'
            health_report['overall_status'] = 'CRITICAL'
            health_report['error'] = str(e)
            return health_report


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Database Maintenance and Operations')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Create database backup')
    backup_parser.add_argument('--type', choices=['full', 'schema', 'data', 'incremental'], 
                              default='full', help='Backup type')
    backup_parser.add_argument('--tables', nargs='+', help='Specific tables to backup')
    backup_parser.add_argument('--retention-days', type=int, default=30, 
                              help='Backup retention in days')
    
    # Vacuum command
    vacuum_parser = subparsers.add_parser('vacuum', help='VACUUM and ANALYZE tables')
    vacuum_parser.add_argument('--tables', nargs='+', help='Specific tables to vacuum')
    vacuum_parser.add_argument('--full', action='store_true', help='Perform VACUUM FULL')
    vacuum_parser.add_argument('--analyze', action='store_true', help='Include ANALYZE')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Database monitoring')
    monitor_parser.add_argument('--stats', action='store_true', help='Show database statistics')
    monitor_parser.add_argument('--replication', action='store_true', help='Show replication status')
    monitor_parser.add_argument('--health', action='store_true', help='Generate health report')
    monitor_parser.add_argument('--export', help='Export report to file')
    
    # Users command
    users_parser = subparsers.add_parser('users', help='User management and auditing')
    users_parser.add_argument('--audit', action='store_true', help='Perform user audit')
    users_parser.add_argument('--export-report', help='Export audit report to file')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup old backups')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize maintenance system
    config = DatabaseConfig()
    maintenance = DatabaseMaintenance(config)
    
    try:
        if args.command == 'backup':
            backup_path = maintenance.create_backup(
                backup_type=args.type,
                tables=args.tables
            )
            print(f"Backup created: {backup_path}")
            
        elif args.command == 'vacuum':
            maintenance.vacuum_analyze(
                tables=args.tables,
                full=args.full
            )
            print("VACUUM ANALYZE completed")
            
        elif args.command == 'monitor':
            if args.health:
                report = maintenance.generate_health_report()
            elif args.replication:
                report = maintenance.monitor_replication()
            else:
                report = maintenance.get_database_stats()
            
            if args.export:
                with open(args.export, 'w') as f:
                    json.dump(report, f, indent=2, default=str)
                print(f"Report exported to: {args.export}")
            else:
                print(json.dumps(report, indent=2, default=str))
                
        elif args.command == 'users':
            if args.audit:
                report = maintenance.audit_users()
                
                if args.export_report:
                    with open(args.export_report, 'w') as f:
                        json.dump(report, f, indent=2, default=str)
                    print(f"Audit report exported to: {args.export_report}")
                else:
                    print(json.dumps(report, indent=2, default=str))
                    
        elif args.command == 'cleanup':
            maintenance.cleanup_old_backups()
            print("Backup cleanup completed")
            
    except Exception as e:
        logger.error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()