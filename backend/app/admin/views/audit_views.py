"""
Admin interface for audit log viewing and analysis with comprehensive security controls
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc, func, and_
from sqlalchemy import or_

from app.api.deps import get_current_admin_user, get_db
from app.core.audit_logger import log_admin_action
from app.models.user import User
from app.models.audit_log import (
    AuditLog, 
    AuditCategory, 
    SeverityLevel, 
    AuditActions, 
    ResourceTypes
)
from app.services.audit_analysis import audit_analysis_service


# Initialize templates
templates = Jinja2Templates(directory="app/admin/templates")

router = APIRouter()


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_dashboard(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=10, le=200, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    action: Optional[str] = Query(None, description="Filter by action"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search term"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Main audit logs dashboard with advanced filtering and real-time updates
    """
    
    try:
        # Log dashboard access
        await log_admin_action(
            action=AuditActions.ADMIN_DASHBOARD_VIEW,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            details={
                "dashboard": "audit_logs",
                "page": page,
                "filters": {
                    "category": category,
                    "severity": severity,
                    "action": action,
                    "user_id": user_id,
                    "ip_address": ip_address,
                    "success": success,
                    "date_range": f"{date_from} to {date_to}" if date_from or date_to else None
                }
            }
        )
        
        # Build query with filters
        query = select(AuditLog)
        count_query = select(func.count(AuditLog.id))
        
        # Apply filters
        conditions = []
        
        if category:
            conditions.append(AuditLog.category == category)
        
        if severity:
            conditions.append(AuditLog.severity == severity)
        
        if action:
            conditions.append(AuditLog.action == action)
        
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        
        if ip_address:
            conditions.append(AuditLog.ip_address == ip_address)
        
        if success is not None:
            conditions.append(AuditLog.success == success)
        
        # Date range filter
        if date_from:
            try:
                start_date = datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                conditions.append(AuditLog.created_at >= start_date)
            except ValueError:
                pass
        
        if date_to:
            try:
                end_date = datetime.strptime(date_to, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                # Include the entire day
                end_date = end_date.replace(hour=23, minute=59, second=59)
                conditions.append(AuditLog.created_at <= end_date)
            except ValueError:
                pass
        
        # Search filter
        if search:
            search_term = f"%{search}%"
            search_conditions = [
                AuditLog.action.contains(search_term),
                AuditLog.resource_type.contains(search_term),
                AuditLog.error_message.contains(search_term),
                AuditLog.ip_address.contains(search_term)
            ]
            conditions.append(or_(*search_conditions))
        
        # Apply all conditions
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))
        
        # Get total count
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Calculate pagination
        offset = (page - 1) * per_page
        total_pages = (total + per_page - 1) // per_page
        
        # Get audit logs
        query = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(per_page)
        result = await db.execute(query)
        audit_logs = result.scalars().all()
        
        # Get summary statistics
        stats = await _get_audit_statistics(db, conditions)
        
        # Get filter options
        filter_options = await _get_filter_options(db)
        
        # Prepare pagination info
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None
        }
        
        return templates.TemplateResponse("audit_logs_dashboard.html", {
            "request": request,
            "audit_logs": audit_logs,
            "pagination": pagination,
            "stats": stats,
            "filter_options": filter_options,
            "current_filters": {
                "category": category,
                "severity": severity,
                "action": action,
                "user_id": user_id,
                "ip_address": ip_address,
                "success": success,
                "date_from": date_from,
                "date_to": date_to,
                "search": search
            },
            "current_admin": current_admin,
            "severity_levels": [s.value for s in SeverityLevel],
            "categories": [c.value for c in AuditCategory]
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load audit logs: {str(e)}")


@router.get("/audit-logs/{audit_log_id}", response_class=HTMLResponse)
async def audit_log_detail(
    request: Request,
    audit_log_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Detailed view of individual audit log entry with integrity verification
    """
    
    try:
        # Get audit log
        result = await db.execute(
            select(AuditLog).where(AuditLog.id == audit_log_id)
        )
        audit_log = result.scalar_one_or_none()
        
        if not audit_log:
            raise HTTPException(status_code=404, detail="Audit log not found")
        
        # Verify data integrity
        from app.core.audit_logger import audit_logger
        is_valid = await audit_logger.verify_audit_integrity(audit_log_id, db)
        
        # Get related audit logs (same session or user)
        related_query = select(AuditLog).where(
            and_(
                AuditLog.id != audit_log_id,
                or_(
                    AuditLog.session_id == audit_log.session_id,
                    and_(
                        AuditLog.user_id == audit_log.user_id,
                        AuditLog.created_at >= audit_log.created_at - timedelta(minutes=30),
                        AuditLog.created_at <= audit_log.created_at + timedelta(minutes=30)
                    )
                )
            )
        ).order_by(desc(AuditLog.created_at)).limit(10)
        
        related_result = await db.execute(related_query)
        related_logs = related_result.scalars().all()
        
        # Log access to audit log detail
        await log_admin_action(
            action=AuditActions.ADMIN_DASHBOARD_VIEW,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            resource_id=str(audit_log_id),
            details={
                "accessed_detail": True,
                "integrity_valid": is_valid
            }
        )
        
        return templates.TemplateResponse("audit_log_detail.html", {
            "request": request,
            "audit_log": audit_log,
            "related_logs": related_logs,
            "integrity_valid": is_valid,
            "current_admin": current_admin
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load audit log detail: {str(e)}")


@router.get("/audit-analytics", response_class=HTMLResponse)
async def audit_analytics_dashboard(
    request: Request,
    period: str = Query("7d", description="Analysis period (1d, 7d, 30d, 90d)"),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Comprehensive audit analytics dashboard with charts and insights
    """
    
    try:
        # Parse period
        period_days = {
            "1d": 1,
            "7d": 7,
            "30d": 30,
            "90d": 90
        }.get(period, 7)
        
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=period_days)
        
        # Get comprehensive analytics
        analytics_data = await _get_comprehensive_analytics(
            start_date, end_date, db
        )
        
        # Get security analysis
        security_analysis = await audit_analysis_service.generate_security_analysis(
            start_date, end_date, db
        )
        
        # Get performance metrics
        performance_metrics = await audit_analysis_service.generate_performance_metrics(
            start_date, end_date, db
        )
        
        # Log analytics access
        await log_admin_action(
            action=AuditActions.ADMIN_REPORT_GENERATE,
            resource_type=ResourceTypes.AUDIT_LOG,
            admin_user_id=current_admin.id,
            details={
                "report_type": "audit_analytics",
                "period": period,
                "period_days": period_days
            }
        )
        
        return templates.TemplateResponse("audit_analytics.html", {
            "request": request,
            "analytics": analytics_data,
            "security_analysis": security_analysis,
            "performance_metrics": performance_metrics,
            "period": period,
            "period_days": period_days,
            "current_admin": current_admin
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load analytics: {str(e)}")


@router.get("/compliance-reports", response_class=HTMLResponse)
async def compliance_reports_dashboard(
    request: Request,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compliance reports dashboard for GDPR, SOX, HIPAA compliance monitoring
    """
    
    # Check super-admin access
    if not getattr(current_admin, 'is_super_admin', False):
        raise HTTPException(
            status_code=403,
            detail="Super-admin privileges required for compliance reports"
        )
    
    try:
        # Generate quick compliance summaries for the last 30 days
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        compliance_summaries = {}
        compliance_types = ['gdpr', 'sox', 'hipaa']
        
        for compliance_type in compliance_types:
            try:
                report = await audit_analysis_service.generate_compliance_report(
                    compliance_type, start_date, end_date, db
                )
                compliance_summaries[compliance_type] = {
                    'total_events': report.total_events,
                    'compliance_events': report.compliance_events,
                    'violations': len(report.violations),
                    'compliance_rate': report.summary.get('compliance_rate', 0)
                }
            except Exception as e:
                compliance_summaries[compliance_type] = {
                    'error': str(e)
                }
        
        # Log compliance dashboard access
        await log_admin_action(
            action=AuditActions.COMPLIANCE_AUDIT,
            resource_type=ResourceTypes.COMPLIANCE_REPORT,
            admin_user_id=current_admin.id,
            details={
                "dashboard": "compliance_reports",
                "period": "30d"
            }
        )
        
        return templates.TemplateResponse("compliance_reports.html", {
            "request": request,
            "compliance_summaries": compliance_summaries,
            "current_admin": current_admin
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load compliance dashboard: {str(e)}")


@router.get("/security-monitoring", response_class=HTMLResponse)
async def security_monitoring_dashboard(
    request: Request,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Real-time security monitoring dashboard with threat detection and alerts
    """
    
    try:
        # Get recent security events (last 24 hours)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(hours=24)
        
        # Get security analysis
        security_analysis = await audit_analysis_service.generate_security_analysis(
            start_date, end_date, db
        )
        
        # Get recent high-severity events
        high_severity_query = select(AuditLog).where(
            and_(
                AuditLog.created_at >= start_date,
                AuditLog.severity.in_([SeverityLevel.HIGH, SeverityLevel.CRITICAL])
            )
        ).order_by(desc(AuditLog.created_at)).limit(20)
        
        high_severity_result = await db.execute(high_severity_query)
        high_severity_events = high_severity_result.scalars().all()
        
        # Get failed login attempts
        failed_logins_query = select(AuditLog).where(
            and_(
                AuditLog.created_at >= start_date,
                AuditLog.action == AuditActions.USER_LOGIN_FAILED
            )
        ).order_by(desc(AuditLog.created_at)).limit(10)
        
        failed_logins_result = await db.execute(failed_logins_query)
        failed_logins = failed_logins_result.scalars().all()
        
        # Get security statistics
        security_stats = await _get_security_statistics(start_date, end_date, db)
        
        # Log security monitoring access
        await log_admin_action(
            action=AuditActions.SECURITY_SCAN,
            resource_type=ResourceTypes.SECURITY_POLICY,
            admin_user_id=current_admin.id,
            details={
                "dashboard": "security_monitoring",
                "threat_level": security_analysis.threat_level
            }
        )
        
        return templates.TemplateResponse("security_monitoring.html", {
            "request": request,
            "security_analysis": security_analysis,
            "high_severity_events": high_severity_events,
            "failed_logins": failed_logins,
            "security_stats": security_stats,
            "current_admin": current_admin
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load security monitoring: {str(e)}")


async def _get_audit_statistics(db: AsyncSession, conditions: List) -> Dict[str, Any]:
    """Get audit log summary statistics"""
    
    base_query_conditions = and_(*conditions) if conditions else None
    
    # Total count
    total_query = select(func.count(AuditLog.id))
    if base_query_conditions is not None:
        total_query = total_query.where(base_query_conditions)
    
    total_result = await db.execute(total_query)
    total = total_result.scalar()
    
    # Success/failure counts
    success_query = select(func.count(AuditLog.id)).where(AuditLog.success == True)
    if base_query_conditions is not None:
        success_query = success_query.where(base_query_conditions)
    
    success_result = await db.execute(success_query)
    successful = success_result.scalar()
    
    failed = total - successful
    success_rate = (successful / total * 100) if total > 0 else 0
    
    # Severity distribution
    severity_query = select(
        AuditLog.severity,
        func.count(AuditLog.id).label('count')
    ).group_by(AuditLog.severity)
    
    if base_query_conditions is not None:
        severity_query = severity_query.where(base_query_conditions)
    
    severity_result = await db.execute(severity_query)
    severity_counts = {row.severity: row.count for row in severity_result}
    
    return {
        'total': total,
        'successful': successful,
        'failed': failed,
        'success_rate': round(success_rate, 2),
        'severity_counts': severity_counts
    }


async def _get_filter_options(db: AsyncSession) -> Dict[str, List[str]]:
    """Get available filter options"""
    
    # Get unique actions
    action_query = select(AuditLog.action).distinct().order_by(AuditLog.action)
    action_result = await db.execute(action_query)
    actions = [row[0] for row in action_result if row[0]]
    
    # Get unique resource types
    resource_query = select(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type)
    resource_result = await db.execute(resource_query)
    resource_types = [row[0] for row in resource_result if row[0]]
    
    return {
        'actions': actions,
        'resource_types': resource_types
    }


async def _get_comprehensive_analytics(
    start_date: datetime,
    end_date: datetime,
    db: AsyncSession
) -> Dict[str, Any]:
    """Get comprehensive analytics data for the dashboard"""
    
    # Activity over time (daily breakdown)
    daily_query = select(
        func.date(AuditLog.created_at).label('date'),
        func.count(AuditLog.id).label('count')
    ).where(
        and_(
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date
        )
    ).group_by(func.date(AuditLog.created_at)).order_by('date')
    
    daily_result = await db.execute(daily_query)
    daily_activity = [{'date': str(row.date), 'count': row.count} for row in daily_result]
    
    # Top actions
    action_query = select(
        AuditLog.action,
        func.count(AuditLog.id).label('count')
    ).where(
        and_(
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date
        )
    ).group_by(AuditLog.action).order_by(desc('count')).limit(10)
    
    action_result = await db.execute(action_query)
    top_actions = [{'action': row.action, 'count': row.count} for row in action_result]
    
    # Category distribution
    category_query = select(
        AuditLog.category,
        func.count(AuditLog.id).label('count')
    ).where(
        and_(
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date
        )
    ).group_by(AuditLog.category).order_by(desc('count'))
    
    category_result = await db.execute(category_query)
    category_distribution = [{'category': row.category, 'count': row.count} for row in category_result]
    
    return {
        'daily_activity': daily_activity,
        'top_actions': top_actions,
        'category_distribution': category_distribution
    }


async def _get_security_statistics(
    start_date: datetime,
    end_date: datetime,
    db: AsyncSession
) -> Dict[str, Any]:
    """Get security-specific statistics"""
    
    # Security events count
    security_query = select(func.count(AuditLog.id)).where(
        and_(
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
            AuditLog.category == AuditCategory.SECURITY_EVENT
        )
    )
    
    security_result = await db.execute(security_query)
    security_events = security_result.scalar()
    
    # Failed login attempts
    failed_login_query = select(func.count(AuditLog.id)).where(
        and_(
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
            AuditLog.action == AuditActions.USER_LOGIN_FAILED
        )
    )
    
    failed_login_result = await db.execute(failed_login_query)
    failed_logins = failed_login_result.scalar()
    
    # Unique IP addresses
    ip_query = select(func.count(func.distinct(AuditLog.ip_address))).where(
        and_(
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
            AuditLog.ip_address.is_not(None)
        )
    )
    
    ip_result = await db.execute(ip_query)
    unique_ips = ip_result.scalar()
    
    return {
        'security_events': security_events,
        'failed_logins': failed_logins,
        'unique_ips': unique_ips
    }