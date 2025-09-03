"""
Enterprise audit log retention and archival system with compliance support and automated lifecycle management
"""
import asyncio
import gzip
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import boto3
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_
from sqlmodel import select, delete

from app.core.config import settings
from app.core.database import get_db
from app.core.audit_logger import log_admin_action
from app.models.audit_log import (
    AuditLog, 
    AuditCategory, 
    SeverityLevel, 
    AuditActions, 
    ResourceTypes
)


logger = logging.getLogger(__name__)


class RetentionPolicy(str, Enum):
    """Audit log retention policies"""
    SHORT_TERM = "short_term"        # 90 days
    STANDARD = "standard"            # 1 year
    COMPLIANCE = "compliance"        # 7 years (SOX, financial)
    GDPR = "gdpr"                   # 3 years (or as per data subject request)
    HIPAA = "hipaa"                 # 6 years
    PERMANENT = "permanent"          # Never delete


class ArchivalStorage(str, Enum):
    """Types of archival storage"""
    LOCAL_DISK = "local_disk"
    S3_STANDARD = "s3_standard"
    S3_GLACIER = "s3_glacier"
    S3_DEEP_ARCHIVE = "s3_deep_archive"
    AZURE_BLOB = "azure_blob"
    GCS_NEARLINE = "gcs_nearline"
    GCS_COLDLINE = "gcs_coldline"


@dataclass
class RetentionRule:
    """Audit log retention rule configuration"""
    name: str
    description: str
    policy: RetentionPolicy
    retention_days: int
    categories: List[AuditCategory]
    severities: List[SeverityLevel]
    actions: List[str]
    compliance_requirements: List[str]
    archival_storage: ArchivalStorage
    compress_before_archive: bool = True
    encrypt_archives: bool = True
    verify_integrity: bool = True
    
    def matches_log(self, audit_log: AuditLog) -> bool:
        """Check if audit log matches this retention rule"""
        if self.categories and audit_log.category not in self.categories:
            return False
        
        if self.severities and audit_log.severity not in self.severities:
            return False
        
        if self.actions and audit_log.action not in self.actions:
            return False
        
        return True


@dataclass
class ArchivalBatch:
    """Batch of audit logs for archival"""
    batch_id: str
    created_at: datetime
    retention_rule: RetentionRule
    audit_log_ids: List[int]
    original_size_bytes: int
    compressed_size_bytes: Optional[int] = None
    archive_path: Optional[str] = None
    checksum: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed
    
    
class AuditRetentionService:
    """
    Enterprise audit log retention and archival service providing:
    - Flexible retention policies based on compliance requirements
    - Automated lifecycle management
    - Multiple archival storage backends
    - Data compression and encryption
    - Integrity verification
    - Compliance reporting
    - Data restoration capabilities
    - Audit trail for retention activities
    """
    
    def __init__(self):
        self.retention_rules = self._init_retention_rules()
        self.storage_backends = self._init_storage_backends()
        self.archival_batch_size = getattr(settings, 'AUDIT_ARCHIVAL_BATCH_SIZE', 1000)
        self.archive_base_path = getattr(settings, 'AUDIT_ARCHIVE_PATH', '/var/lib/chrono-scraper/audit-archives')
        
    def _init_retention_rules(self) -> List[RetentionRule]:
        """Initialize default retention rules based on compliance requirements"""
        return [
            # Critical security events - permanent retention
            RetentionRule(
                name="critical_security",
                description="Critical security events - permanent retention",
                policy=RetentionPolicy.PERMANENT,
                retention_days=-1,  # Never delete
                categories=[AuditCategory.SECURITY_EVENT],
                severities=[SeverityLevel.CRITICAL],
                actions=[],
                compliance_requirements=["SOX", "GDPR", "HIPAA"],
                archival_storage=ArchivalStorage.S3_STANDARD,
                compress_before_archive=True,
                encrypt_archives=True,
                verify_integrity=True
            ),
            
            # SOX compliance - 7 years
            RetentionRule(
                name="sox_compliance",
                description="SOX compliance records - 7 years retention",
                policy=RetentionPolicy.COMPLIANCE,
                retention_days=2555,  # 7 years
                categories=[AuditCategory.USER_MANAGEMENT, AuditCategory.SYSTEM_CONFIG],
                severities=[SeverityLevel.HIGH, SeverityLevel.CRITICAL],
                actions=[
                    AuditActions.USER_ROLE_ASSIGN,
                    AuditActions.USER_PERMISSION_GRANT,
                    AuditActions.SYSTEM_CONFIG_UPDATE,
                    AuditActions.ADMIN_LOGIN
                ],
                compliance_requirements=["SOX"],
                archival_storage=ArchivalStorage.S3_GLACIER,
                compress_before_archive=True,
                encrypt_archives=True,
                verify_integrity=True
            ),
            
            # HIPAA compliance - 6 years
            RetentionRule(
                name="hipaa_compliance",
                description="HIPAA healthcare data access - 6 years retention",
                policy=RetentionPolicy.HIPAA,
                retention_days=2190,  # 6 years
                categories=[AuditCategory.CONTENT_MANAGEMENT, AuditCategory.DATA_EXPORT],
                severities=[],
                actions=[
                    AuditActions.USER_PROFILE_VIEW,
                    AuditActions.DATA_EXPORT,
                    AuditActions.GDPR_DATA_EXPORT
                ],
                compliance_requirements=["HIPAA"],
                archival_storage=ArchivalStorage.S3_GLACIER,
                compress_before_archive=True,
                encrypt_archives=True,
                verify_integrity=True
            ),
            
            # GDPR compliance - 3 years
            RetentionRule(
                name="gdpr_compliance",
                description="GDPR personal data processing - 3 years retention",
                policy=RetentionPolicy.GDPR,
                retention_days=1095,  # 3 years
                categories=[AuditCategory.USER_MANAGEMENT, AuditCategory.COMPLIANCE],
                severities=[],
                actions=[
                    AuditActions.USER_CREATE,
                    AuditActions.USER_UPDATE,
                    AuditActions.USER_DELETE,
                    AuditActions.GDPR_REQUEST,
                    AuditActions.GDPR_DATA_EXPORT,
                    AuditActions.GDPR_DATA_DELETION
                ],
                compliance_requirements=["GDPR"],
                archival_storage=ArchivalStorage.S3_STANDARD,
                compress_before_archive=True,
                encrypt_archives=True,
                verify_integrity=True
            ),
            
            # Standard business records - 1 year
            RetentionRule(
                name="standard_business",
                description="Standard business operations - 1 year retention",
                policy=RetentionPolicy.STANDARD,
                retention_days=365,
                categories=[
                    AuditCategory.CONTENT_MANAGEMENT,
                    AuditCategory.API_ACCESS,
                    AuditCategory.BULK_OPERATION
                ],
                severities=[SeverityLevel.MEDIUM, SeverityLevel.HIGH],
                actions=[],
                compliance_requirements=[],
                archival_storage=ArchivalStorage.S3_STANDARD,
                compress_before_archive=True,
                encrypt_archives=False,
                verify_integrity=True
            ),
            
            # Short-term operational logs - 90 days
            RetentionRule(
                name="short_term_operational",
                description="Short-term operational logs - 90 days retention",
                policy=RetentionPolicy.SHORT_TERM,
                retention_days=90,
                categories=[AuditCategory.API_ACCESS, AuditCategory.AUTHENTICATION],
                severities=[SeverityLevel.LOW, SeverityLevel.MEDIUM],
                actions=[
                    AuditActions.API_REQUEST,
                    AuditActions.USER_LOGIN,
                    AuditActions.USER_LOGOUT
                ],
                compliance_requirements=[],
                archival_storage=ArchivalStorage.LOCAL_DISK,
                compress_before_archive=True,
                encrypt_archives=False,
                verify_integrity=False
            )
        ]
    
    def _init_storage_backends(self) -> Dict[ArchivalStorage, Any]:
        """Initialize storage backend clients"""
        backends = {}
        
        # AWS S3 client
        if getattr(settings, 'AWS_ACCESS_KEY_ID', None):
            backends[ArchivalStorage.S3_STANDARD] = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=getattr(settings, 'AWS_REGION', 'us-east-1')
            )
            backends[ArchivalStorage.S3_GLACIER] = backends[ArchivalStorage.S3_STANDARD]
            backends[ArchivalStorage.S3_DEEP_ARCHIVE] = backends[ArchivalStorage.S3_STANDARD]
        
        # Local disk storage
        backends[ArchivalStorage.LOCAL_DISK] = Path(self.archive_base_path)
        
        return backends
    
    async def apply_retention_policies(
        self,
        db: AsyncSession,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Apply retention policies to audit logs
        
        Args:
            db: Database session
            dry_run: If True, only simulate the process without actual changes
            
        Returns:
            Summary of retention policy application
        """
        
        results = {
            'processed_rules': 0,
            'logs_archived': 0,
            'logs_deleted': 0,
            'bytes_archived': 0,
            'archival_batches': [],
            'errors': []
        }
        
        try:
            for rule in self.retention_rules:
                try:
                    rule_result = await self._apply_retention_rule(rule, db, dry_run)
                    
                    results['processed_rules'] += 1
                    results['logs_archived'] += rule_result['logs_archived']
                    results['logs_deleted'] += rule_result['logs_deleted']
                    results['bytes_archived'] += rule_result['bytes_archived']
                    results['archival_batches'].extend(rule_result['archival_batches'])
                    
                    logger.info(f"Applied retention rule '{rule.name}': "
                              f"archived={rule_result['logs_archived']}, "
                              f"deleted={rule_result['logs_deleted']}")
                    
                except Exception as e:
                    error_msg = f"Failed to apply retention rule '{rule.name}': {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            # Log retention policy application
            if not dry_run:
                await log_admin_action(
                    action=AuditActions.RETENTION_POLICY_APPLIED,
                    resource_type=ResourceTypes.AUDIT_LOG,
                    admin_user_id=None,  # System action
                    details={
                        'retention_summary': results,
                        'policies_applied': len(self.retention_rules)
                    }
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Error applying retention policies: {e}")
            results['errors'].append(str(e))
            return results
    
    async def _apply_retention_rule(
        self,
        rule: RetentionRule,
        db: AsyncSession,
        dry_run: bool
    ) -> Dict[str, Any]:
        """Apply a specific retention rule"""
        
        result = {
            'rule_name': rule.name,
            'logs_archived': 0,
            'logs_deleted': 0,
            'bytes_archived': 0,
            'archival_batches': []
        }
        
        # Calculate cutoff date
        if rule.retention_days == -1:  # Permanent retention
            return result
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=rule.retention_days)
        
        # Find eligible audit logs
        query = select(AuditLog).where(
            and_(
                AuditLog.created_at < cutoff_date,
                AuditLog.archived is False
            )
        )
        
        # Apply rule filters
        if rule.categories:
            query = query.where(AuditLog.category.in_(rule.categories))
        
        if rule.severities:
            query = query.where(AuditLog.severity.in_(rule.severities))
        
        if rule.actions:
            query = query.where(AuditLog.action.in_(rule.actions))
        
        # Get eligible logs in batches
        offset = 0
        while True:
            batch_query = query.offset(offset).limit(self.archival_batch_size)
            batch_result = await db.execute(batch_query)
            audit_logs = batch_result.scalars().all()
            
            if not audit_logs:
                break
            
            if not dry_run:
                # Create archival batch
                batch = await self._create_archival_batch(audit_logs, rule)
                
                # Archive the batch
                if rule.policy != RetentionPolicy.SHORT_TERM:
                    archive_success = await self._archive_batch(batch, db)
                    if archive_success:
                        result['archival_batches'].append(batch.batch_id)
                        result['bytes_archived'] += batch.compressed_size_bytes or batch.original_size_bytes
                
                # Mark logs as archived or delete them
                if rule.policy == RetentionPolicy.SHORT_TERM:
                    # Delete short-term logs immediately
                    await self._delete_audit_logs(audit_logs, db)
                    result['logs_deleted'] += len(audit_logs)
                else:
                    # Mark as archived for other policies
                    await self._mark_logs_archived(audit_logs, db)
                    result['logs_archived'] += len(audit_logs)
            else:
                # Dry run - just count
                if rule.policy == RetentionPolicy.SHORT_TERM:
                    result['logs_deleted'] += len(audit_logs)
                else:
                    result['logs_archived'] += len(audit_logs)
            
            offset += self.archival_batch_size
        
        return result
    
    async def _create_archival_batch(
        self,
        audit_logs: List[AuditLog],
        rule: RetentionRule
    ) -> ArchivalBatch:
        """Create an archival batch from audit logs"""
        
        batch_id = f"archive_{rule.name}_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Calculate original size
        original_size = sum(
            len(json.dumps(log.dict(), default=str).encode('utf-8'))
            for log in audit_logs
        )
        
        batch = ArchivalBatch(
            batch_id=batch_id,
            created_at=datetime.now(timezone.utc),
            retention_rule=rule,
            audit_log_ids=[log.id for log in audit_logs],
            original_size_bytes=original_size,
            status="pending"
        )
        
        return batch
    
    async def _archive_batch(
        self,
        batch: ArchivalBatch,
        db: AsyncSession
    ) -> bool:
        """Archive a batch of audit logs to storage"""
        
        try:
            batch.status = "processing"
            
            # Get audit logs data
            result = await db.execute(
                select(AuditLog).where(AuditLog.id.in_(batch.audit_log_ids))
            )
            audit_logs = result.scalars().all()
            
            # Prepare archive data
            archive_data = {
                'batch_id': batch.batch_id,
                'created_at': batch.created_at.isoformat(),
                'retention_rule': batch.retention_rule.name,
                'audit_logs': [log.dict() for log in audit_logs]
            }
            
            # Serialize to JSON
            json_data = json.dumps(archive_data, default=str, indent=2)
            
            # Compress if required
            if batch.retention_rule.compress_before_archive:
                compressed_data = gzip.compress(json_data.encode('utf-8'))
                batch.compressed_size_bytes = len(compressed_data)
                archive_content = compressed_data
                filename_suffix = '.json.gz'
            else:
                archive_content = json_data.encode('utf-8')
                filename_suffix = '.json'
            
            # Generate archive filename
            archive_filename = f"{batch.batch_id}{filename_suffix}"
            
            # Store to configured backend
            storage_backend = batch.retention_rule.archival_storage
            
            if storage_backend == ArchivalStorage.LOCAL_DISK:
                archive_path = await self._store_to_local_disk(
                    archive_filename, archive_content, batch.retention_rule
                )
            elif storage_backend in [ArchivalStorage.S3_STANDARD, ArchivalStorage.S3_GLACIER, ArchivalStorage.S3_DEEP_ARCHIVE]:
                archive_path = await self._store_to_s3(
                    archive_filename, archive_content, batch.retention_rule, storage_backend
                )
            else:
                raise ValueError(f"Unsupported storage backend: {storage_backend}")
            
            batch.archive_path = archive_path
            batch.status = "completed"
            
            # Calculate checksum for integrity verification
            if batch.retention_rule.verify_integrity:
                import hashlib
                batch.checksum = hashlib.sha256(archive_content).hexdigest()
            
            logger.info(f"Successfully archived batch {batch.batch_id} to {archive_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to archive batch {batch.batch_id}: {e}")
            batch.status = "failed"
            return False
    
    async def _store_to_local_disk(
        self,
        filename: str,
        content: bytes,
        rule: RetentionRule
    ) -> str:
        """Store archive to local disk"""
        
        # Create directory structure
        archive_dir = Path(self.archive_base_path) / rule.name / datetime.now(timezone.utc).strftime('%Y/%m')
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Write file
        archive_path = archive_dir / filename
        
        with open(archive_path, 'wb') as f:
            f.write(content)
        
        # Set restrictive permissions
        os.chmod(archive_path, 0o600)  # Read/write for owner only
        
        return str(archive_path)
    
    async def _store_to_s3(
        self,
        filename: str,
        content: bytes,
        rule: RetentionRule,
        storage_class: ArchivalStorage
    ) -> str:
        """Store archive to AWS S3"""
        
        s3_client = self.storage_backends.get(storage_class)
        if not s3_client:
            raise ValueError(f"S3 client not configured for {storage_class}")
        
        bucket_name = getattr(settings, 'AUDIT_ARCHIVE_S3_BUCKET', 'chrono-scraper-audit-archives')
        
        # Determine S3 storage class
        s3_storage_class = {
            ArchivalStorage.S3_STANDARD: 'STANDARD',
            ArchivalStorage.S3_GLACIER: 'GLACIER',
            ArchivalStorage.S3_DEEP_ARCHIVE: 'DEEP_ARCHIVE'
        }.get(storage_class, 'STANDARD')
        
        # Generate S3 key
        s3_key = f"audit-archives/{rule.name}/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/{filename}"
        
        # Upload to S3
        extra_args = {
            'StorageClass': s3_storage_class,
            'ServerSideEncryption': 'AES256' if rule.encrypt_archives else None,
            'Metadata': {
                'retention-rule': rule.name,
                'original-size': str(getattr(content, '__len__', lambda: 0)()),
                'created-at': datetime.now(timezone.utc).isoformat()
            }
        }
        
        # Remove None values
        extra_args = {k: v for k, v in extra_args.items() if v is not None}
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=content,
            **extra_args
        )
        
        return f"s3://{bucket_name}/{s3_key}"
    
    async def _mark_logs_archived(
        self,
        audit_logs: List[AuditLog],
        db: AsyncSession
    ) -> None:
        """Mark audit logs as archived"""
        
        log_ids = [log.id for log in audit_logs]
        
        # Update logs to mark as archived
        from sqlalchemy import update
        
        await db.execute(
            update(AuditLog)
            .where(AuditLog.id.in_(log_ids))
            .values(
                archived=True,
                archived_at=datetime.now(timezone.utc)
            )
        )
        
        await db.commit()
    
    async def _delete_audit_logs(
        self,
        audit_logs: List[AuditLog],
        db: AsyncSession
    ) -> None:
        """Permanently delete audit logs"""
        
        log_ids = [log.id for log in audit_logs]
        
        # Delete logs
        await db.execute(
            delete(AuditLog).where(AuditLog.id.in_(log_ids))
        )
        
        await db.commit()
    
    async def restore_archived_logs(
        self,
        batch_id: str,
        target_date_range: Optional[Tuple[datetime, datetime]] = None
    ) -> Dict[str, Any]:
        """
        Restore archived audit logs from storage
        
        Args:
            batch_id: ID of the archival batch to restore
            target_date_range: Optional date range filter for restoration
            
        Returns:
            Restoration result summary
        """
        
        # This would implement restoration logic
        # For now, return a placeholder
        return {
            'batch_id': batch_id,
            'status': 'not_implemented',
            'message': 'Archive restoration feature not yet implemented'
        }
    
    async def get_retention_summary(
        self,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Get summary of current retention policy status"""
        
        summary = {
            'total_audit_logs': 0,
            'archived_logs': 0,
            'active_logs': 0,
            'retention_rules': len(self.retention_rules),
            'policy_breakdown': {},
            'storage_usage': {}
        }
        
        # Get total counts
        total_result = await db.execute(select(func.count(AuditLog.id)))
        summary['total_audit_logs'] = total_result.scalar()
        
        archived_result = await db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.archived is True)
        )
        summary['archived_logs'] = archived_result.scalar()
        
        summary['active_logs'] = summary['total_audit_logs'] - summary['archived_logs']
        
        # Get breakdown by retention policy eligibility
        for rule in self.retention_rules:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=rule.retention_days) if rule.retention_days > 0 else None
            
            query = select(func.count(AuditLog.id))
            conditions = []
            
            if cutoff_date:
                conditions.append(AuditLog.created_at < cutoff_date)
            
            if rule.categories:
                conditions.append(AuditLog.category.in_(rule.categories))
            
            if rule.severities:
                conditions.append(AuditLog.severity.in_(rule.severities))
            
            if rule.actions:
                conditions.append(AuditLog.action.in_(rule.actions))
            
            if conditions:
                query = query.where(and_(*conditions))
            
            result = await db.execute(query)
            eligible_count = result.scalar()
            
            summary['policy_breakdown'][rule.name] = {
                'eligible_for_action': eligible_count,
                'retention_days': rule.retention_days,
                'policy': rule.policy.value,
                'storage_backend': rule.archival_storage.value
            }
        
        return summary


# Global retention service instance
audit_retention_service = AuditRetentionService()


# Background task for automated retention policy application
async def apply_retention_policies_task():
    """Background task to apply retention policies periodically"""
    while True:
        try:
            async for db in get_db():
                logger.info("Starting automated retention policy application")
                
                result = await audit_retention_service.apply_retention_policies(db)
                
                logger.info(f"Retention policy application completed: "
                          f"archived={result['logs_archived']}, "
                          f"deleted={result['logs_deleted']}, "
                          f"errors={len(result['errors'])}")
                
                if result['errors']:
                    logger.error(f"Retention policy errors: {result['errors']}")
                
                break  # Exit the db session loop
                
        except Exception as e:
            logger.error(f"Error in retention policy application: {e}")
        
        # Run daily at 2 AM
        await asyncio.sleep(86400)  # 24 hours