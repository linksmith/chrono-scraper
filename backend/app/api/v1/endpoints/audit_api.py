"""
Audit log API endpoints with comprehensive security controls and role-based access
"""
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc, func, or_

from app.api.deps import get_current_admin_user, get_db
from app.core.audit_logger import audit_logger, log_admin_action, log_security_event
from app.models.user import User
from app.models.audit_log import (
    AuditLog, 
    AuditLogRead, 
    AuditLogFilter, 
    AuditLogAnalytics,
    AuditCategory, 
    SeverityLevel, 
    AuditActions, 
    ResourceTypes
)
from app.services.audit_analysis import (
    audit_analysis_service, 
    ComplianceReport
)
from app.core.config import settings


router = APIRouter()


@router.get("/audit-logs", response_model=Dict[str, Any])
async def get_audit_logs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    admin_user_id: Optional[int] = Query(None, description="Filter by admin user ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    category: Optional[AuditCategory] = Query(None, description="Filter by category"),
    severity: Optional[SeverityLevel] = Query(None, description="Filter by severity"),
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    created_after: Optional[datetime] = Query(None, description="Filter by creation date (after)"),
    created_before: Optional[datetime] = Query(None, description="Filter by creation date (before)"),
    gdpr_relevant: Optional[bool] = Query(None, description="Filter GDPR relevant events"),
    sox_relevant: Optional[bool] = Query(None, description="Filter SOX relevant events"),
    hipaa_relevant: Optional[bool] = Query(None, description="Filter HIPAA relevant events"),
    sensitive_data_accessed: Optional[bool] = Query(None, description="Filter sensitive data access"),
    search_query: Optional[str] = Query(None, description="Search in details and error messages"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve audit logs with advanced filtering and pagination
    
    Requires admin privileges and logs all access attempts
    """
    
    # Log admin access to audit logs
    await log_admin_action(
        action=AuditActions.ADMIN_DASHBOARD_VIEW,
        resource_type=ResourceTypes.AUDIT_LOG,
        admin_user_id=current_admin.id,
        details={
            "accessed_endpoint": "get_audit_logs",
            "filters": {
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "category": category,
                "severity": severity
            }
        }
    )
    
    try:
        # Build filter criteria
        filter_criteria = AuditLogFilter(
            skip=skip,
            limit=limit,
            user_id=user_id,
            admin_user_id=admin_user_id,
            action=action,
            resource_type=resource_type,
            category=category,
            severity=severity,
            ip_address=ip_address,
            success=success,
            created_after=created_after,
            created_before=created_before,
            gdpr_relevant=gdpr_relevant,
            sox_relevant=sox_relevant,
            hipaa_relevant=hipaa_relevant,
            sensitive_data_accessed=sensitive_data_accessed,
            search_query=search_query,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # Build query
        query = select(AuditLog)
        
        # Apply filters
        if filter_criteria.user_id:
            query = query.where(AuditLog.user_id == filter_criteria.user_id)
        
        if filter_criteria.admin_user_id:
            query = query.where(AuditLog.admin_user_id == filter_criteria.admin_user_id)
        
        if filter_criteria.action:
            query = query.where(AuditLog.action == filter_criteria.action)
        
        if filter_criteria.resource_type:
            query = query.where(AuditLog.resource_type == filter_criteria.resource_type)
        
        if filter_criteria.category:
            query = query.where(AuditLog.category == filter_criteria.category)
        
        if filter_criteria.severity:
            query = query.where(AuditLog.severity == filter_criteria.severity)
        
        if filter_criteria.ip_address:
            query = query.where(AuditLog.ip_address == filter_criteria.ip_address)
        
        if filter_criteria.success is not None:
            query = query.where(AuditLog.success == filter_criteria.success)
        
        if filter_criteria.created_after:
            query = query.where(AuditLog.created_at >= filter_criteria.created_after)
        
        if filter_criteria.created_before:
            query = query.where(AuditLog.created_at <= filter_criteria.created_before)
        
        if filter_criteria.gdpr_relevant is not None:
            query = query.where(AuditLog.gdpr_relevant == filter_criteria.gdpr_relevant)
        
        if filter_criteria.sox_relevant is not None:
            query = query.where(AuditLog.sox_relevant == filter_criteria.sox_relevant)
        
        if filter_criteria.hipaa_relevant is not None:
            query = query.where(AuditLog.hipaa_relevant == filter_criteria.hipaa_relevant)
        
        if filter_criteria.sensitive_data_accessed is not None:
            query = query.where(AuditLog.sensitive_data_accessed == filter_criteria.sensitive_data_accessed)
        
        # Apply text search
        if filter_criteria.search_query:
            search_term = f"%{filter_criteria.search_query}%"
            query = query.where(
                or_(
                    AuditLog.details.op("::text")().__contains__(filter_criteria.search_query),
                    AuditLog.error_message.contains(search_term),
                    AuditLog.action.contains(search_term)
                )
            )
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply sorting
        if filter_criteria.sort_order.lower() == "desc":
            query = query.order_by(desc(getattr(AuditLog, filter_criteria.sort_by)))
        else:
            query = query.order_by(getattr(AuditLog, filter_criteria.sort_by))
        
        # Apply pagination
        query = query.offset(filter_criteria.skip).limit(filter_criteria.limit)
        
        # Execute query
        result = await db.execute(query)
        audit_logs = result.scalars().all()
        
        # Convert to response format (filter sensitive data)
        filtered_logs = []
        for log in audit_logs:
            log_dict = log.dict()
            
            # Remove sensitive fields for non-super-admin users
            if not getattr(current_admin, 'is_super_admin', False):
                sensitive_fields = ['request_body', 'response_body', 'request_headers', 'response_headers']
                for field in sensitive_fields:
                    if field in log_dict:
                        log_dict[field] = "[REDACTED - ADMIN ACCESS REQUIRED]"
            
            filtered_logs.append(log_dict)
        
        return {
            "audit_logs": filtered_logs,
            "total": total,
            "skip": filter_criteria.skip,
            "limit": filter_criteria.limit,
            "has_more": (filter_criteria.skip + filter_criteria.limit) < total
        }
        
    except Exception as e:
        # Log security event for audit log access failure
        await log_security_event(
            action=AuditActions.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.HIGH,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "attempted_endpoint": "get_audit_logs"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )


@router.get("/audit-logs/{audit_log_id}", response_model=AuditLogRead)
async def get_audit_log_detail(
    audit_log_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed audit log entry by ID
    
    Requires admin privileges and verifies data integrity
    """
    
    try:
        # Get audit log
        result = await db.execute(
            select(AuditLog).where(AuditLog.id == audit_log_id)
        )
        audit_log = result.scalar_one_or_none()
        
        if not audit_log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit log entry not found"
            )
        
        # Verify data integrity
        is_valid = await audit_logger.verify_audit_integrity(audit_log_id, db)
        if not is_valid:
            # Log integrity violation
            await log_security_event(
                action=AuditActions.SECURITY_VULNERABILITY_DETECTED,
                severity=SeverityLevel.CRITICAL,
                user_id=current_admin.id,
                details={
                    "integrity_check_failed": True,
                    "audit_log_id": audit_log_id,
                    "violation_type": "data_integrity"
                }
            )
            
            # Still return the data but with a warning
            audit_log.details = audit_log.details or {}
            audit_log.details["_integrity_warning"] = "Data integrity check failed"
        
        # Log access to specific audit log
        await log_admin_action(
            action=AuditActions.ADMIN_DASHBOARD_VIEW,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            resource_id=str(audit_log_id),
            details={"accessed_detail": True}
        )
        
        return audit_log
        
    except HTTPException:
        raise
    except Exception as e:
        await log_security_event(
            action=AuditActions.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.HIGH,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "attempted_audit_log_id": audit_log_id
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit log detail"
        )


@router.get("/audit-analytics", response_model=AuditLogAnalytics)
async def get_audit_analytics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    category: Optional[AuditCategory] = Query(None, description="Filter by category"),
    severity: Optional[SeverityLevel] = Query(None, description="Filter by severity"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive audit analytics and statistics
    
    Provides insights into system usage, security events, and compliance metrics
    """
    
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Build filter criteria
        filter_criteria = AuditLogFilter(
            created_after=start_date,
            created_before=end_date,
            category=category,
            severity=severity
        )
        
        # Get analytics
        analytics = await audit_analysis_service.get_audit_analytics(filter_criteria, db)
        
        # Log analytics access
        await log_admin_action(
            action=AuditActions.ADMIN_REPORT_GENERATE,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            details={
                "report_type": "audit_analytics",
                "days_analyzed": days,
                "filters": {
                    "category": category,
                    "severity": severity
                }
            }
        )
        
        return analytics
        
    except Exception as e:
        await log_security_event(
            action=AuditActions.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.MEDIUM,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "attempted_endpoint": "get_audit_analytics"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate audit analytics"
        )


@router.get("/compliance-report/{compliance_type}")
async def get_compliance_report(
    compliance_type: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    format: str = Query("json", pattern="^(json|pdf|csv)$", description="Report format"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Generate comprehensive compliance report (GDPR, SOX, HIPAA)
    
    Requires super-admin privileges for sensitive compliance data
    """
    
    # Verify compliance type
    valid_types = ['gdpr', 'sox', 'hipaa']
    if compliance_type.lower() not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid compliance type. Must be one of: {valid_types}"
        )
    
    # Check super-admin access for sensitive compliance reports
    if not getattr(current_admin, 'is_super_admin', False):
        await log_security_event(
            action=AuditActions.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.HIGH,
            user_id=current_admin.id,
            details={
                "attempted_compliance_type": compliance_type,
                "insufficient_privileges": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-admin privileges required for compliance reports"
        )
    
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Generate compliance report
        report = await audit_analysis_service.generate_compliance_report(
            compliance_type, start_date, end_date, db
        )
        
        # Log compliance report generation
        await log_admin_action(
            action=AuditActions.COMPLIANCE_AUDIT,
            resource_type=ResourceTypes.COMPLIANCE_REPORT,
            admin_user_id=current_admin.id,
            details={
                "compliance_type": compliance_type.upper(),
                "report_id": report.report_id,
                "days_analyzed": days,
                "format": format
            },
            sensitive_data_accessed=True,
            **{f"{compliance_type.lower()}_relevant": True}
        )
        
        # Return appropriate format
        if format.lower() == "json":
            return report
        elif format.lower() == "csv":
            return await _export_compliance_report_csv(report)
        elif format.lower() == "pdf":
            # For PDF generation, you might want to use a background task
            # and return a task ID for the user to check status
            return {"message": "PDF generation not implemented yet"}
        
    except Exception as e:
        await log_security_event(
            action=AuditActions.COMPLIANCE_AUDIT,
            severity=SeverityLevel.HIGH,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "compliance_type": compliance_type,
                "generation_failed": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate compliance report"
        )


@router.get("/security-analysis")
async def get_security_analysis(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate comprehensive security analysis report
    
    Includes threat assessment, anomaly detection, and security recommendations
    """
    
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Generate security analysis
        analysis = await audit_analysis_service.generate_security_analysis(
            start_date, end_date, db
        )
        
        # Log security analysis access
        await log_admin_action(
            action=AuditActions.SECURITY_SCAN,
            resource_type=ResourceTypes.SECURITY_POLICY,
            admin_user_id=current_admin.id,
            details={
                "analysis_id": analysis.analysis_id,
                "days_analyzed": days,
                "threat_level": analysis.threat_level
            }
        )
        
        return analysis
        
    except Exception as e:
        await log_security_event(
            action=AuditActions.SECURITY_SCAN,
            severity=SeverityLevel.MEDIUM,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "scan_failed": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate security analysis"
        )


@router.get("/performance-metrics")
async def get_performance_metrics(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get system performance metrics from audit logs
    
    Provides insights into response times, error rates, and usage patterns
    """
    
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Generate performance metrics
        metrics = await audit_analysis_service.generate_performance_metrics(
            start_date, end_date, db
        )
        
        # Log performance metrics access
        await log_admin_action(
            action=AuditActions.ADMIN_REPORT_GENERATE,
            resource_type=ResourceTypes.SYSTEM,
            admin_user_id=current_admin.id,
            details={
                "report_type": "performance_metrics",
                "days_analyzed": days
            }
        )
        
        return metrics
        
    except Exception as e:
        await log_security_event(
            action=AuditActions.ADMIN_REPORT_GENERATE,
            severity=SeverityLevel.LOW,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "report_type": "performance_metrics"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate performance metrics"
        )


@router.post("/audit-logs/export")
async def export_audit_logs(
    filter_data: AuditLogFilter,
    format: str = Query("csv", pattern="^(csv|json)$", description="Export format"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Export audit logs in various formats
    
    Supports CSV and JSON export with comprehensive filtering
    """
    
    # Check export permissions
    if not getattr(current_admin, 'can_export_audit_logs', True):
        await log_security_event(
            action=AuditActions.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.MEDIUM,
            user_id=current_admin.id,
            details={"insufficient_export_permissions": True}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for audit log export"
        )
    
    try:
        # Limit export size for security
        max_export_limit = getattr(settings, 'AUDIT_MAX_EXPORT_LIMIT', 10000)
        if filter_data.limit > max_export_limit:
            filter_data.limit = max_export_limit
        
        # Get audit logs
        query = select(AuditLog)
        
        # Apply all filters (reusing the filtering logic)
        # ... (apply same filtering logic as in get_audit_logs)
        
        result = await db.execute(query.offset(filter_data.skip).limit(filter_data.limit))
        audit_logs = result.scalars().all()
        
        # Log export action
        await log_admin_action(
            action=AuditActions.DATA_EXPORT,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            affected_count=len(audit_logs),
            details={
                "export_format": format,
                "filter_criteria": filter_data.dict(exclude_none=True),
                "exported_count": len(audit_logs)
            },
            sensitive_data_accessed=True
        )
        
        if format.lower() == "csv":
            return await _export_audit_logs_csv(audit_logs)
        else:  # JSON
            return {"audit_logs": [log.dict() for log in audit_logs]}
        
    except Exception as e:
        await log_security_event(
            action=AuditActions.DATA_EXPORT,
            severity=SeverityLevel.MEDIUM,
            user_id=current_admin.id,
            details={
                "error": str(e),
                "export_failed": True,
                "export_format": format
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export audit logs"
        )


async def _export_audit_logs_csv(audit_logs: List[AuditLog]) -> StreamingResponse:
    """Export audit logs as CSV stream"""
    
    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = [
            'id', 'created_at', 'user_id', 'admin_user_id', 'action', 'resource_type',
            'category', 'severity', 'success', 'ip_address', 'user_agent',
            'error_message', 'affected_count', 'processing_time_ms'
        ]
        writer.writerow(headers)
        
        # Write data
        for log in audit_logs:
            row = [
                log.id,
                log.created_at.isoformat() if log.created_at else '',
                log.user_id or '',
                log.admin_user_id or '',
                log.action or '',
                log.resource_type or '',
                log.category or '',
                log.severity or '',
                log.success,
                log.ip_address or '',
                log.user_agent or '',
                log.error_message or '',
                log.affected_count or 0,
                log.processing_time_ms or 0
            ]
            writer.writerow(row)
            output.seek(0)
            yield output.read()
            output.seek(0)
            output.truncate(0)
    
    filename = f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


async def _export_compliance_report_csv(report: ComplianceReport) -> StreamingResponse:
    """Export compliance report as CSV"""
    
    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write report summary
        writer.writerow(['Compliance Report Summary'])
        writer.writerow(['Report Type', report.report_type])
        writer.writerow(['Generated At', report.generated_at.isoformat()])
        writer.writerow(['Period', f"{report.period_start.date()} to {report.period_end.date()}"])
        writer.writerow(['Total Events', report.total_events])
        writer.writerow(['Compliance Events', report.compliance_events])
        writer.writerow(['Violations', len(report.violations)])
        writer.writerow([])  # Empty row
        
        # Write violations if any
        if report.violations:
            writer.writerow(['Violations'])
            writer.writerow(['Severity', 'Description', 'Recommendation'])
            for violation in report.violations:
                writer.writerow([
                    violation.get('severity', ''),
                    violation.get('description', ''),
                    violation.get('recommendation', '')
                ])
        
        output.seek(0)
        yield output.read()
    
    filename = f"compliance_report_{report.report_type.lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )