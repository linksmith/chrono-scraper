"""
Bulk operations service for admin user management
"""
import asyncio
import csv
import io
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlmodel import Session

from app.models.user import User
from app.models.audit_log import AuditLog, create_audit_log, AuditActions, ResourceTypes
from app.models.bulk_operations import (
    BulkOperationType, BulkOperationStatus, BulkOperationResult, 
    BulkOperationProgress, UserAnalyticsResponse, UserActivitySummary,
    ExportFormat, UserExportRequest, UserImportRequest, BulkEmailRequest,
    InvitationBulkRequest
)
from app.models.invitation import InvitationToken
from app.core.security import get_password_hash
import secrets
from app.core.config import settings
from app.core.email_service import EmailService
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BulkOperationsService:
    """Service for handling bulk operations on users and other resources"""
    
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.email_service = EmailService()
        self.rate_limiter = RateLimiter()
        
        # Operation tracking
        self._active_operations: Dict[str, BulkOperationProgress] = {}
        
    async def perform_bulk_user_operation(
        self,
        user_ids: List[int],
        operation: BulkOperationType,
        reason: Optional[str] = None,
        **kwargs
    ) -> BulkOperationResult:
        """Perform bulk operations on users with comprehensive error handling and logging"""
        
        # Validate operation permissions
        await self._validate_bulk_operation_permissions(operation, len(user_ids))
        
        # Generate operation ID
        operation_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        
        # Initialize progress tracking
        progress = BulkOperationProgress(
            operation_id=operation_id,
            status=BulkOperationStatus.RUNNING,
            current_step="Initializing",
            total_steps=3,  # validate, process, finalize
            completed_steps=0,
            items_total=len(user_ids),
            items_processed=0,
            total_batches=max(1, len(user_ids) // 50),  # Process in batches of 50
            current_batch=0
        )
        self._active_operations[operation_id] = progress
        
        try:
            # Step 1: Validate users exist and are eligible for operation
            progress.current_step = "Validating users"
            progress.completed_steps = 1
            
            valid_users, invalid_ids, validation_errors = await self._validate_users_for_operation(
                user_ids, operation
            )
            
            if not valid_users:
                raise ValueError("No valid users found for operation")
            
            # Step 2: Process users in batches
            progress.current_step = "Processing users"
            progress.completed_steps = 2
            progress.total_batches = max(1, len(valid_users) // 50)
            
            successful_ids = []
            failed_ids = list(invalid_ids)  # Start with validation failures
            failed_reasons = validation_errors.copy()
            
            # Process in batches to avoid overwhelming the database
            batch_size = 50
            for i in range(0, len(valid_users), batch_size):
                batch = valid_users[i:i + batch_size]
                progress.current_batch = (i // batch_size) + 1
                
                batch_results = await self._process_user_batch(batch, operation, **kwargs)
                
                successful_ids.extend(batch_results['successful'])
                failed_ids.extend(batch_results['failed'])
                failed_reasons.update(batch_results['errors'])
                
                progress.items_processed = len(successful_ids) + len(failed_ids) - len(invalid_ids)
                progress.progress_percentage = (progress.items_processed / len(user_ids)) * 100
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
            
            # Step 3: Create audit logs and finalize
            progress.current_step = "Finalizing and logging"
            progress.completed_steps = 3
            
            # Create audit log
            audit_log = await self._create_bulk_audit_log(
                operation, successful_ids, failed_ids, reason, started_at
            )
            
            completed_at = datetime.utcnow()
            duration_seconds = (completed_at - started_at).total_seconds()
            
            # Determine final status
            if len(successful_ids) == len(user_ids):
                final_status = BulkOperationStatus.COMPLETED
            elif len(successful_ids) > 0:
                final_status = BulkOperationStatus.PARTIALLY_COMPLETED
            else:
                final_status = BulkOperationStatus.FAILED
            
            progress.status = final_status
            progress.progress_percentage = 100.0
            
            result = BulkOperationResult(
                operation_id=operation_id,
                operation_type=operation,
                status=final_status,
                total_requested=len(user_ids),
                total_processed=len(successful_ids) + len(failed_ids),
                total_successful=len(successful_ids),
                total_failed=len(failed_ids),
                successful_ids=successful_ids,
                failed_ids=failed_ids,
                failed_reasons=failed_reasons,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration_seconds,
                performed_by=self.current_user.id,
                reason=reason,
                audit_log_ids=[audit_log.id] if audit_log else []
            )
            
            logger.info(f"Bulk operation {operation_id} completed: {len(successful_ids)} successful, {len(failed_ids)} failed")
            return result
            
        except Exception as e:
            # Handle operation failure
            progress.status = BulkOperationStatus.FAILED
            progress.last_error = str(e)
            
            logger.error(f"Bulk operation {operation_id} failed: {str(e)}")
            
            # Still try to create audit log for the failure
            try:
                await self._create_bulk_audit_log(
                    operation, [], user_ids, reason, started_at, 
                    success=False, error_message=str(e)
                )
            except Exception as audit_error:
                logger.error(f"Failed to create audit log: {str(audit_error)}")
            
            raise
        
        finally:
            # Clean up operation tracking after a delay
            asyncio.create_task(self._cleanup_operation_tracking(operation_id, delay=300))
    
    async def get_operation_progress(self, operation_id: str) -> Optional[BulkOperationProgress]:
        """Get the progress of a bulk operation"""
        return self._active_operations.get(operation_id)
    
    async def _validate_bulk_operation_permissions(self, operation: BulkOperationType, count: int):
        """Validate that the current user can perform the bulk operation"""
        if not self.current_user.is_superuser:
            raise PermissionError("Only superusers can perform bulk operations")
        
        # Rate limiting for bulk operations
        await self.rate_limiter.check_rate_limit(
            f"bulk_operation:{self.current_user.id}",
            max_requests=10,  # 10 bulk operations per hour
            window_seconds=3600
        )
        
        # Additional validation for destructive operations
        destructive_ops = [BulkOperationType.DELETE]
        if operation in destructive_ops and count > 100:
            raise ValueError(f"Cannot perform {operation} on more than 100 users at once")
    
    async def _validate_users_for_operation(
        self, user_ids: List[int], operation: BulkOperationType
    ) -> Tuple[List[User], List[int], Dict[int, str]]:
        """Validate users exist and are eligible for the operation"""
        stmt = select(User).where(User.id.in_(user_ids))
        result = await self.db.execute(stmt)
        existing_users = list(result.scalars().all())
        
        existing_ids = {user.id for user in existing_users}
        missing_ids = [uid for uid in user_ids if uid not in existing_ids]
        
        valid_users = []
        invalid_ids = list(missing_ids)
        validation_errors = {uid: "User not found" for uid in missing_ids}
        
        for user in existing_users:
            # Prevent self-modification for dangerous operations
            if user.id == self.current_user.id and operation in [
                BulkOperationType.DELETE, 
                BulkOperationType.DEACTIVATE,
                BulkOperationType.DENY
            ]:
                invalid_ids.append(user.id)
                validation_errors[user.id] = "Cannot perform this operation on your own account"
                continue
            
            # Additional operation-specific validation
            if operation == BulkOperationType.APPROVE and user.approval_status == "approved":
                invalid_ids.append(user.id)
                validation_errors[user.id] = "User is already approved"
                continue
            
            if operation == BulkOperationType.DENY and user.approval_status == "rejected":
                invalid_ids.append(user.id)
                validation_errors[user.id] = "User is already rejected"
                continue
            
            if operation == BulkOperationType.ACTIVATE and user.is_active:
                invalid_ids.append(user.id)
                validation_errors[user.id] = "User is already active"
                continue
            
            if operation == BulkOperationType.DEACTIVATE and not user.is_active:
                invalid_ids.append(user.id)
                validation_errors[user.id] = "User is already inactive"
                continue
            
            valid_users.append(user)
        
        return valid_users, invalid_ids, validation_errors
    
    async def _process_user_batch(
        self, users: List[User], operation: BulkOperationType, **kwargs
    ) -> Dict[str, Any]:
        """Process a batch of users for the given operation"""
        successful = []
        failed = []
        errors = {}
        
        try:
            if operation == BulkOperationType.APPROVE:
                await self._bulk_approve_users(users)
            elif operation == BulkOperationType.DENY:
                await self._bulk_deny_users(users, kwargs.get('reason'))
            elif operation == BulkOperationType.ACTIVATE:
                await self._bulk_activate_users(users)
            elif operation == BulkOperationType.DEACTIVATE:
                await self._bulk_deactivate_users(users)
            elif operation == BulkOperationType.DELETE:
                await self._bulk_delete_users(users)
            elif operation == BulkOperationType.ASSIGN_ROLE:
                await self._bulk_assign_role(users, kwargs.get('role', 'user'))
            elif operation == BulkOperationType.VERIFY_EMAIL:
                await self._bulk_verify_emails(users)
            elif operation == BulkOperationType.UNVERIFY_EMAIL:
                await self._bulk_unverify_emails(users)
            else:
                raise ValueError(f"Unsupported operation: {operation}")
            
            # If we get here, all users in batch were successful
            successful = [user.id for user in users]
            
        except Exception as e:
            # If batch processing fails, mark all as failed
            failed = [user.id for user in users]
            for user in users:
                errors[user.id] = str(e)
            logger.error(f"Batch processing failed for operation {operation}: {str(e)}")
        
        return {
            'successful': successful,
            'failed': failed,
            'errors': errors
        }
    
    async def _bulk_approve_users(self, users: List[User]):
        """Approve multiple users"""
        user_ids = [user.id for user in users]
        approval_date = datetime.utcnow()
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(
                approval_status="approved",
                approval_date=approval_date,
                approved_by_id=self.current_user.id
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_deny_users(self, users: List[User], reason: Optional[str] = None):
        """Deny multiple users"""
        user_ids = [user.id for user in users]
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(
                approval_status="rejected",
                approval_date=datetime.utcnow(),
                approved_by_id=self.current_user.id
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_activate_users(self, users: List[User]):
        """Activate multiple users"""
        user_ids = [user.id for user in users]
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_active=True)
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_deactivate_users(self, users: List[User]):
        """Deactivate multiple users"""
        user_ids = [user.id for user in users]
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_active=False)
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_delete_users(self, users: List[User]):
        """Delete multiple users (with cascade handling)"""
        user_ids = [user.id for user in users]
        
        # Note: In production, consider soft delete or archiving instead
        # For now, we rely on database CASCADE settings
        stmt = delete(User).where(User.id.in_(user_ids))
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_assign_role(self, users: List[User], role: str):
        """Assign role to multiple users"""
        user_ids = [user.id for user in users]
        is_superuser = role == "superuser"
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_superuser=is_superuser)
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_verify_emails(self, users: List[User]):
        """Verify emails for multiple users"""
        user_ids = [user.id for user in users]
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_verified=True, email_verification_token=None)
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _bulk_unverify_emails(self, users: List[User]):
        """Unverify emails for multiple users"""
        user_ids = [user.id for user in users]
        
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_verified=False)
        )
        await self.db.execute(stmt)
        await self.db.commit()
    
    async def _create_bulk_audit_log(
        self,
        operation: BulkOperationType,
        successful_ids: List[int],
        failed_ids: List[int],
        reason: Optional[str],
        started_at: datetime,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> Optional[AuditLog]:
        """Create audit log entry for bulk operation"""
        try:
            action_map = {
                BulkOperationType.APPROVE: AuditActions.BULK_USER_APPROVE,
                BulkOperationType.DENY: AuditActions.BULK_USER_DENY,
                BulkOperationType.ACTIVATE: AuditActions.BULK_USER_ACTIVATE,
                BulkOperationType.DEACTIVATE: AuditActions.BULK_USER_DEACTIVATE,
                BulkOperationType.DELETE: AuditActions.BULK_USER_DELETE,
                BulkOperationType.ASSIGN_ROLE: AuditActions.BULK_USER_ROLE_ASSIGN,
                BulkOperationType.VERIFY_EMAIL: AuditActions.BULK_EMAIL_VERIFY,
            }
            
            audit_log = AuditLog(
                admin_user_id=self.current_user.id,
                action=action_map.get(operation, f"bulk_{operation}"),
                resource_type=ResourceTypes.BULK_OPERATION,
                resource_id=",".join(map(str, successful_ids + failed_ids)),
                details={
                    "operation": operation,
                    "reason": reason,
                    "successful_count": len(successful_ids),
                    "failed_count": len(failed_ids),
                    "successful_ids": successful_ids,
                    "failed_ids": failed_ids,
                    "started_at": started_at.isoformat(),
                    "duration_seconds": (datetime.utcnow() - started_at).total_seconds()
                },
                success=success,
                error_message=error_message,
                affected_count=len(successful_ids)
            )
            
            self.db.add(audit_log)
            await self.db.commit()
            await self.db.refresh(audit_log)
            
            return audit_log
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {str(e)}")
            return None
    
    async def _cleanup_operation_tracking(self, operation_id: str, delay: int = 300):
        """Clean up operation tracking after a delay"""
        await asyncio.sleep(delay)
        self._active_operations.pop(operation_id, None)
    
    async def export_users(self, export_request: UserExportRequest) -> Dict[str, Any]:
        """Export user data in specified format"""
        # Build query with filters
        stmt = select(User)
        
        if export_request.user_ids:
            stmt = stmt.where(User.id.in_(export_request.user_ids))
        
        if not export_request.include_inactive:
            stmt = stmt.where(User.is_active == True)
        
        if not export_request.include_unverified:
            stmt = stmt.where(User.is_verified == True)
        
        if export_request.date_range_start:
            stmt = stmt.where(User.created_at >= export_request.date_range_start)
        
        if export_request.date_range_end:
            stmt = stmt.where(User.created_at <= export_request.date_range_end)
        
        # Apply additional filters
        if export_request.filters:
            for key, value in export_request.filters.items():
                if hasattr(User, key):
                    stmt = stmt.where(getattr(User, key) == value)
        
        stmt = stmt.order_by(User.created_at.desc())
        
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())
        
        # Determine fields to include
        if export_request.include_fields:
            fields = export_request.include_fields
        else:
            fields = [
                'id', 'email', 'full_name', 'is_active', 'is_verified', 'is_superuser',
                'approval_status', 'created_at', 'last_login', 'login_count',
                'research_interests', 'academic_affiliation', 'professional_title'
            ]
        
        # Convert to export format
        if export_request.format == ExportFormat.CSV:
            return await self._export_to_csv(users, fields)
        elif export_request.format == ExportFormat.JSON:
            return await self._export_to_json(users, fields)
        else:
            raise ValueError(f"Unsupported export format: {export_request.format}")
    
    async def _export_to_csv(self, users: List[User], fields: List[str]) -> Dict[str, Any]:
        """Export users to CSV format"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(fields)
        
        # Write data
        for user in users:
            row = []
            for field in fields:
                value = getattr(user, field, None)
                if isinstance(value, datetime):
                    value = value.isoformat() if value else None
                row.append(value)
            writer.writerow(row)
        
        csv_content = output.getvalue()
        output.close()
        
        return {
            "format": "csv",
            "content": csv_content,
            "filename": f"users_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            "count": len(users)
        }
    
    async def _export_to_json(self, users: List[User], fields: List[str]) -> Dict[str, Any]:
        """Export users to JSON format"""
        data = []
        for user in users:
            user_data = {}
            for field in fields:
                value = getattr(user, field, None)
                if isinstance(value, datetime):
                    value = value.isoformat() if value else None
                user_data[field] = value
            data.append(user_data)
        
        return {
            "format": "json",
            "content": json.dumps(data, indent=2, default=str),
            "filename": f"users_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
            "count": len(users)
        }
    
    async def send_bulk_emails(self, email_request: BulkEmailRequest) -> BulkOperationResult:
        """Send bulk emails to users"""
        # This would integrate with your email service
        # Implementation depends on your email service setup
        raise NotImplementedError("Bulk email sending not yet implemented")
    
    async def generate_bulk_invitations(self, invitation_request: InvitationBulkRequest) -> Dict[str, Any]:
        """Generate bulk invitation tokens"""
        invitations = []
        
        for i in range(invitation_request.count):
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=invitation_request.expires_in_days)
            
            invitation = InvitationToken(
                token=token,
                created_by=self.current_user.id,
                expires_at=expires_at,
                max_uses=invitation_request.max_uses,
                notes=invitation_request.notes,
                default_approval_status=invitation_request.default_approval_status
            )
            
            self.db.add(invitation)
            invitations.append(invitation)
        
        await self.db.commit()
        
        # Create audit log
        await self._create_bulk_audit_log(
            BulkOperationType.EXPORT,  # Using as placeholder for invitation generation
            [inv.id for inv in invitations],
            [],
            f"Generated {len(invitations)} invitation tokens",
            datetime.utcnow()
        )
        
        return {
            "count": len(invitations),
            "invitations": [
                {
                    "id": inv.id,
                    "token": inv.token,
                    "expires_at": inv.expires_at.isoformat(),
                    "max_uses": inv.max_uses,
                    "invitation_url": f"{settings.FRONTEND_URL}/auth/register?invitation={inv.token}"
                }
                for inv in invitations
            ]
        }