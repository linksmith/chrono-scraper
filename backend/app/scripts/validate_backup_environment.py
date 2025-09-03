"""
Backup environment validation script.

This script validates the backup system configuration and environment setup,
ensuring all required components are properly configured and accessible.

Usage:
    python validate_backup_environment.py [--fix] [--verbose]
    
Options:
    --fix: Attempt to fix issues automatically
    --verbose: Show detailed output
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path

# Add the backend directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from cryptography.fernet import Fernet


class BackupEnvironmentValidator:
    """Validates backup environment configuration."""
    
    def __init__(self, fix_issues=False, verbose=False):
        self.fix_issues = fix_issues
        self.verbose = verbose
        self.issues = []
        self.warnings = []
        self.fixes_applied = []
        
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
    
    async def validate_all(self) -> bool:
        """Run all validation checks."""
        self.logger.info("Starting backup environment validation...")
        
        checks = [
            ("Basic Configuration", self.validate_basic_config),
            ("Directory Permissions", self.validate_directories),
            ("Encryption Setup", self.validate_encryption),
            ("Storage Backends", self.validate_storage_backends),
            ("Database Connectivity", self.validate_database_access),
            ("Redis Connectivity", self.validate_redis_access),
            ("Notification Channels", self.validate_notifications),
            ("Backup Dependencies", self.validate_dependencies),
            ("Security Settings", self.validate_security),
            ("Performance Settings", self.validate_performance),
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            self.logger.info(f"Validating {check_name}...")
            try:
                passed = await check_func()
                if not passed:
                    all_passed = False
                    self.logger.error(f"❌ {check_name} validation failed")
                else:
                    self.logger.info(f"✅ {check_name} validation passed")
            except Exception as e:
                self.logger.error(f"❌ {check_name} validation error: {e}")
                all_passed = False
        
        # Summary
        self.print_summary()
        
        return all_passed
    
    async def validate_basic_config(self) -> bool:
        """Validate basic backup configuration."""
        checks_passed = True
        
        # Check if backup system is enabled
        if not getattr(settings, 'BACKUP_ENABLED', False):
            self.issues.append("BACKUP_ENABLED is not set to true")
            checks_passed = False
        
        # Check backup system version
        version = getattr(settings, 'BACKUP_SYSTEM_VERSION', None)
        if not version:
            self.warnings.append("BACKUP_SYSTEM_VERSION not set")
        elif self.verbose:
            self.logger.debug(f"Backup system version: {version}")
        
        # Check default backup type
        default_type = getattr(settings, 'BACKUP_DEFAULT_TYPE', 'full')
        valid_types = ['full', 'incremental', 'differential', 'database_only', 'files_only', 'configuration']
        if default_type not in valid_types:
            self.issues.append(f"Invalid BACKUP_DEFAULT_TYPE: {default_type}")
            checks_passed = False
        
        # Check compression settings
        compression_type = getattr(settings, 'BACKUP_COMPRESSION_TYPE', 'gzip')
        valid_compression = ['none', 'gzip', 'lz4', 'zstd']
        if compression_type not in valid_compression:
            self.issues.append(f"Invalid BACKUP_COMPRESSION_TYPE: {compression_type}")
            checks_passed = False
        
        return checks_passed
    
    async def validate_directories(self) -> bool:
        """Validate backup directories and permissions."""
        checks_passed = True
        
        # Check backup directory
        backup_path = Path(getattr(settings, 'BACKUP_LOCAL_PATH', '/app/backups'))
        
        if not backup_path.exists():
            if self.fix_issues:
                try:
                    backup_path.mkdir(parents=True, exist_ok=True)
                    self.fixes_applied.append(f"Created backup directory: {backup_path}")
                    self.logger.info(f"Created backup directory: {backup_path}")
                except Exception as e:
                    self.issues.append(f"Cannot create backup directory {backup_path}: {e}")
                    checks_passed = False
            else:
                self.issues.append(f"Backup directory does not exist: {backup_path}")
                checks_passed = False
        
        if backup_path.exists():
            # Check write permissions
            test_file = backup_path / "test_write"
            try:
                test_file.write_text("test")
                test_file.unlink()
                if self.verbose:
                    self.logger.debug(f"Backup directory writable: {backup_path}")
            except Exception as e:
                self.issues.append(f"Backup directory not writable: {backup_path} - {e}")
                checks_passed = False
        
        # Check log directory
        log_file = getattr(settings, 'BACKUP_LOG_FILE', '/app/logs/backup.log')
        log_dir = Path(log_file).parent
        
        if not log_dir.exists():
            if self.fix_issues:
                try:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    self.fixes_applied.append(f"Created log directory: {log_dir}")
                except Exception as e:
                    self.issues.append(f"Cannot create log directory {log_dir}: {e}")
                    checks_passed = False
            else:
                self.issues.append(f"Log directory does not exist: {log_dir}")
                checks_passed = False
        
        # Check temp directory
        temp_dir = Path(getattr(settings, 'BACKUP_TEMP_DIR', '/tmp/backup_temp'))
        if not temp_dir.exists():
            if self.fix_issues:
                try:
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    self.fixes_applied.append(f"Created temp directory: {temp_dir}")
                except Exception as e:
                    self.warnings.append(f"Cannot create temp directory {temp_dir}: {e}")
        
        return checks_passed
    
    async def validate_encryption(self) -> bool:
        """Validate encryption configuration."""
        checks_passed = True
        
        encryption_key = getattr(settings, 'BACKUP_ENCRYPTION_KEY', '')
        
        if not encryption_key:
            if self.fix_issues:
                # Generate new encryption key
                key = Fernet.generate_key()
                self.fixes_applied.append("Generated new encryption key (add to .env file)")
                self.logger.warning(f"Generated encryption key: {key.decode()}")
                self.logger.warning("Add this to your .env file: BACKUP_ENCRYPTION_KEY=" + key.decode())
            else:
                self.issues.append("BACKUP_ENCRYPTION_KEY not set")
                checks_passed = False
        else:
            # Validate encryption key format
            try:
                Fernet(encryption_key.encode())
                if self.verbose:
                    self.logger.debug("Encryption key format is valid")
            except Exception as e:
                self.issues.append(f"Invalid encryption key format: {e}")
                checks_passed = False
        
        # Check encryption algorithm
        algorithm = getattr(settings, 'BACKUP_ENCRYPTION_ALGORITHM', 'AES-256-GCM')
        if algorithm not in ['AES-256-GCM', 'AES-256-CBC']:
            self.warnings.append(f"Unusual encryption algorithm: {algorithm}")
        
        return checks_passed
    
    async def validate_storage_backends(self) -> bool:
        """Validate storage backend configurations."""
        checks_passed = True
        enabled_backends = []
        
        # Local storage (should always be available)
        if getattr(settings, 'BACKUP_LOCAL_ENABLED', True):
            enabled_backends.append("Local")
            
            local_path = getattr(settings, 'BACKUP_LOCAL_PATH', '/app/backups')
            max_size = getattr(settings, 'BACKUP_LOCAL_MAX_SIZE_GB', 100)
            
            # Check available disk space
            try:
                import shutil
                total, used, free = shutil.disk_usage(local_path)
                free_gb = free / (1024**3)
                
                if free_gb < max_size:
                    self.warnings.append(f"Local storage: only {free_gb:.1f}GB free, max configured: {max_size}GB")
                elif self.verbose:
                    self.logger.debug(f"Local storage: {free_gb:.1f}GB free")
            except Exception as e:
                self.warnings.append(f"Cannot check local disk space: {e}")
        
        # AWS S3
        if getattr(settings, 'BACKUP_AWS_ENABLED', False):
            enabled_backends.append("AWS S3")
            
            required_aws_settings = [
                'BACKUP_AWS_ACCESS_KEY_ID',
                'BACKUP_AWS_SECRET_ACCESS_KEY',
                'BACKUP_AWS_BUCKET_NAME'
            ]
            
            for setting in required_aws_settings:
                if not getattr(settings, setting, ''):
                    self.issues.append(f"AWS S3 enabled but {setting} not configured")
                    checks_passed = False
        
        # Google Cloud Storage
        if getattr(settings, 'BACKUP_GCS_ENABLED', False):
            enabled_backends.append("Google Cloud Storage")
            
            if not getattr(settings, 'BACKUP_GCS_PROJECT_ID', ''):
                self.issues.append("GCS enabled but BACKUP_GCS_PROJECT_ID not configured")
                checks_passed = False
            
            if not getattr(settings, 'BACKUP_GCS_BUCKET_NAME', ''):
                self.issues.append("GCS enabled but BACKUP_GCS_BUCKET_NAME not configured")
                checks_passed = False
            
            credentials_path = getattr(settings, 'BACKUP_GCS_CREDENTIALS_PATH', '')
            if credentials_path and not Path(credentials_path).exists():
                self.issues.append(f"GCS credentials file not found: {credentials_path}")
                checks_passed = False
        
        # Azure Blob Storage
        if getattr(settings, 'BACKUP_AZURE_ENABLED', False):
            enabled_backends.append("Azure Blob Storage")
            
            required_azure_settings = [
                'BACKUP_AZURE_ACCOUNT_NAME',
                'BACKUP_AZURE_ACCOUNT_KEY',
                'BACKUP_AZURE_CONTAINER_NAME'
            ]
            
            for setting in required_azure_settings:
                if not getattr(settings, setting, ''):
                    self.issues.append(f"Azure enabled but {setting} not configured")
                    checks_passed = False
        
        # SFTP
        if getattr(settings, 'BACKUP_SFTP_ENABLED', False):
            enabled_backends.append("SFTP")
            
            required_sftp_settings = [
                'BACKUP_SFTP_HOST',
                'BACKUP_SFTP_USERNAME'
            ]
            
            for setting in required_sftp_settings:
                if not getattr(settings, setting, ''):
                    self.issues.append(f"SFTP enabled but {setting} not configured")
                    checks_passed = False
            
            # Check authentication method
            password = getattr(settings, 'BACKUP_SFTP_PASSWORD', '')
            private_key_path = getattr(settings, 'BACKUP_SFTP_PRIVATE_KEY_PATH', '')
            
            if not password and not private_key_path:
                self.issues.append("SFTP enabled but no authentication method configured")
                checks_passed = False
            elif private_key_path and not Path(private_key_path).exists():
                self.issues.append(f"SFTP private key file not found: {private_key_path}")
                checks_passed = False
        
        if not enabled_backends:
            self.issues.append("No storage backends enabled")
            checks_passed = False
        else:
            self.logger.info(f"Enabled storage backends: {', '.join(enabled_backends)}")
        
        return checks_passed
    
    async def validate_database_access(self) -> bool:
        """Validate database connectivity for backups."""
        checks_passed = True
        
        # Check PostgreSQL configuration
        pg_settings = [
            'POSTGRES_SERVER',
            'POSTGRES_USER',
            'POSTGRES_PASSWORD',
            'POSTGRES_DB'
        ]
        
        for setting in pg_settings:
            if not getattr(settings, setting, ''):
                self.issues.append(f"Database setting not configured: {setting}")
                checks_passed = False
        
        # Test database connection
        try:
            import asyncpg
            
            conn_str = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:5432/{settings.POSTGRES_DB}"
            conn = await asyncpg.connect(conn_str)
            
            # Test basic query
            version = await conn.fetchval("SELECT version()")
            await conn.close()
            
            if self.verbose:
                self.logger.debug(f"Database connection successful: {version[:50]}...")
        
        except Exception as e:
            self.issues.append(f"Cannot connect to database: {e}")
            checks_passed = False
        
        return checks_passed
    
    async def validate_redis_access(self) -> bool:
        """Validate Redis connectivity."""
        checks_passed = True
        
        try:
            import redis.asyncio as redis
            
            client = redis.from_url(settings.REDIS_URL)
            await client.ping()
            info = await client.info()
            await client.close()
            
            if self.verbose:
                redis_version = info.get('redis_version', 'unknown')
                self.logger.debug(f"Redis connection successful: version {redis_version}")
        
        except Exception as e:
            self.issues.append(f"Cannot connect to Redis: {e}")
            checks_passed = False
        
        return checks_passed
    
    async def validate_notifications(self) -> bool:
        """Validate notification channel configurations."""
        checks_passed = True
        enabled_channels = []
        
        if not getattr(settings, 'BACKUP_NOTIFICATIONS_ENABLED', False):
            self.warnings.append("Backup notifications are disabled")
            return True
        
        # Email notifications
        if getattr(settings, 'BACKUP_EMAIL_ENABLED', False):
            enabled_channels.append("Email")
            
            required_email_settings = [
                'BACKUP_EMAIL_RECIPIENTS',
                'BACKUP_EMAIL_FROM',
                'BACKUP_EMAIL_SMTP_HOST'
            ]
            
            for setting in required_email_settings:
                if not getattr(settings, setting, ''):
                    self.issues.append(f"Email notifications enabled but {setting} not configured")
                    checks_passed = False
        
        # Slack notifications
        if getattr(settings, 'BACKUP_SLACK_ENABLED', False):
            enabled_channels.append("Slack")
            
            if not getattr(settings, 'BACKUP_SLACK_WEBHOOK_URL', ''):
                self.issues.append("Slack notifications enabled but webhook URL not configured")
                checks_passed = False
        
        # Discord notifications
        if getattr(settings, 'BACKUP_DISCORD_ENABLED', False):
            enabled_channels.append("Discord")
            
            if not getattr(settings, 'BACKUP_DISCORD_WEBHOOK_URL', ''):
                self.issues.append("Discord notifications enabled but webhook URL not configured")
                checks_passed = False
        
        # Custom webhook
        if getattr(settings, 'BACKUP_WEBHOOK_ENABLED', False):
            enabled_channels.append("Webhook")
            
            if not getattr(settings, 'BACKUP_WEBHOOK_URL', ''):
                self.issues.append("Webhook notifications enabled but URL not configured")
                checks_passed = False
        
        # PagerDuty
        if getattr(settings, 'BACKUP_PAGERDUTY_ENABLED', False):
            enabled_channels.append("PagerDuty")
            
            if not getattr(settings, 'BACKUP_PAGERDUTY_INTEGRATION_KEY', ''):
                self.issues.append("PagerDuty notifications enabled but integration key not configured")
                checks_passed = False
        
        if enabled_channels:
            self.logger.info(f"Enabled notification channels: {', '.join(enabled_channels)}")
        else:
            self.warnings.append("No notification channels configured")
        
        return checks_passed
    
    async def validate_dependencies(self) -> bool:
        """Validate backup system dependencies."""
        checks_passed = True
        
        # Check required packages
        required_packages = [
            'aiofiles',
            'cryptography',
            'lz4',
            'zstandard',
            'aiohttp',
            'asyncpg',
            'redis'
        ]
        
        for package in required_packages:
            try:
                __import__(package)
                if self.verbose:
                    self.logger.debug(f"Package available: {package}")
            except ImportError:
                self.issues.append(f"Required package not installed: {package}")
                checks_passed = False
        
        # Check optional packages for cloud storage
        optional_packages = {
            'boto3': 'AWS S3 support',
            'google.cloud.storage': 'Google Cloud Storage support',
            'azure.storage.blob': 'Azure Blob Storage support',
            'paramiko': 'SFTP support',
            'aiosmtplib': 'Email notifications'
        }
        
        for package, description in optional_packages.items():
            try:
                __import__(package)
                if self.verbose:
                    self.logger.debug(f"Optional package available: {package} ({description})")
            except ImportError:
                self.warnings.append(f"Optional package not installed: {package} ({description})")
        
        # Check system tools
        system_tools = ['pg_dump', 'tar', 'gzip']
        
        for tool in system_tools:
            import shutil
            if not shutil.which(tool):
                self.issues.append(f"Required system tool not found: {tool}")
                checks_passed = False
            elif self.verbose:
                self.logger.debug(f"System tool available: {tool}")
        
        return checks_passed
    
    async def validate_security(self) -> bool:
        """Validate security settings."""
        checks_passed = True
        
        # Check if integrity verification is enabled
        if not getattr(settings, 'BACKUP_VERIFY_INTEGRITY', True):
            self.warnings.append("Backup integrity verification is disabled")
        
        # Check if encryption is enabled
        if not getattr(settings, 'BACKUP_VERIFY_INTEGRITY', True):
            self.warnings.append("Backup encryption is disabled - not recommended for production")
        
        # Check file permissions
        permissions = getattr(settings, 'BACKUP_LOCAL_PERMISSIONS', '0755')
        try:
            perm_int = int(permissions, 8)
            if perm_int & 0o077:  # Check if group/other have write access
                self.warnings.append(f"Backup directory permissions may be too permissive: {permissions}")
        except ValueError:
            self.issues.append(f"Invalid backup permissions format: {permissions}")
            checks_passed = False
        
        # Check audit logging
        if not getattr(settings, 'BACKUP_AUDIT_ENABLED', True):
            self.warnings.append("Backup audit logging is disabled")
        
        return checks_passed
    
    async def validate_performance(self) -> bool:
        """Validate performance settings."""
        checks_passed = True
        
        # Check memory limit
        memory_limit = getattr(settings, 'BACKUP_MEMORY_LIMIT_GB', 2)
        if memory_limit < 1:
            self.warnings.append(f"Backup memory limit may be too low: {memory_limit}GB")
        elif memory_limit > 8:
            self.warnings.append(f"Backup memory limit is very high: {memory_limit}GB")
        
        # Check timeout settings
        timeout = getattr(settings, 'BACKUP_TIMEOUT_SECONDS', 3600)
        if timeout < 300:  # 5 minutes
            self.warnings.append(f"Backup timeout may be too short: {timeout} seconds")
        
        # Check parallel operations
        parallel_ops = getattr(settings, 'BACKUP_MAX_PARALLEL_OPERATIONS', 3)
        if parallel_ops < 1 or parallel_ops > 10:
            self.warnings.append(f"Unusual number of parallel operations: {parallel_ops}")
        
        return checks_passed
    
    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("BACKUP ENVIRONMENT VALIDATION SUMMARY")
        print("=" * 60)
        
        if not self.issues and not self.warnings:
            print("✅ All validations passed! Backup environment is properly configured.")
        else:
            if self.issues:
                print(f"\n❌ CRITICAL ISSUES ({len(self.issues)}):")
                for i, issue in enumerate(self.issues, 1):
                    print(f"  {i}. {issue}")
            
            if self.warnings:
                print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
                for i, warning in enumerate(self.warnings, 1):
                    print(f"  {i}. {warning}")
            
            if self.fixes_applied:
                print(f"\n🔧 FIXES APPLIED ({len(self.fixes_applied)}):")
                for i, fix in enumerate(self.fixes_applied, 1):
                    print(f"  {i}. {fix}")
        
        print("\n" + "=" * 60)
        
        if self.issues:
            print("❌ VALIDATION FAILED - Please fix critical issues before using the backup system")
            return False
        elif self.warnings:
            print("⚠️  VALIDATION PASSED WITH WARNINGS - Review warnings for optimal configuration")
            return True
        else:
            print("✅ VALIDATION PASSED - Backup environment is ready for use")
            return True


async def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description="Validate backup environment configuration")
    parser.add_argument('--fix', action='store_true', help='Attempt to fix issues automatically')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    
    args = parser.parse_args()
    
    validator = BackupEnvironmentValidator(fix_issues=args.fix, verbose=args.verbose)
    success = await validator.validate_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())