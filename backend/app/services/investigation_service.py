"""
OSINT investigation management service
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, and_, or_, func
import difflib
import hashlib

from app.models.user import User
from app.models.shared_pages import PageV2 as Page
from app.models.investigations import (
    Investigation,
    Evidence,
    PageComparison,
    InvestigationTimeline,
    InvestigationFinding,
    InvestigationStatus,
    InvestigationPriority,
    EvidenceType,
    EvidenceStatus
)


class InvestigationService:
    """Service for managing OSINT investigations"""
    
    def __init__(self):
        pass
    
    # Investigation Management
    async def create_investigation(
        self,
        db: AsyncSession,
        user: User,
        title: str,
        description: str = None,
        investigation_type: str = None,
        priority: InvestigationPriority = InvestigationPriority.MEDIUM,
        target_entities: List[str] = None,
        target_domains: List[str] = None,
        target_keywords: List[str] = None,
        geographical_scope: List[str] = None,
        temporal_scope_start: datetime = None,
        temporal_scope_end: datetime = None,
        is_confidential: bool = False,
        is_collaborative: bool = False,
        tags: List[str] = None,
        custom_fields: Dict[str, Any] = None
    ) -> Investigation:
        """Create a new investigation"""
        
        # Generate case number if not provided
        case_number = await self._generate_case_number(db, user)
        
        investigation = Investigation(
            user_id=user.id,
            title=title,
            description=description,
            case_number=case_number,
            investigation_type=investigation_type,
            priority=priority,
            target_entities=target_entities or [],
            target_domains=target_domains or [],
            target_keywords=target_keywords or [],
            geographical_scope=geographical_scope or [],
            temporal_scope_start=temporal_scope_start,
            temporal_scope_end=temporal_scope_end,
            is_confidential=is_confidential,
            is_collaborative=is_collaborative,
            tags=tags or [],
            custom_fields=custom_fields or {},
            lead_investigator_id=user.id
        )
        
        db.add(investigation)
        await db.commit()
        await db.refresh(investigation)
        return investigation
    
    async def update_investigation(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        updates: Dict[str, Any]
    ) -> Optional[Investigation]:
        """Update an investigation"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(investigation, key):
                setattr(investigation, key, value)
        
        investigation.updated_at = datetime.utcnow()
        
        # Update status-specific fields
        if updates.get('status') == InvestigationStatus.ACTIVE and not investigation.started_at:
            investigation.started_at = datetime.utcnow()
        elif updates.get('status') == InvestigationStatus.COMPLETED and not investigation.completed_at:
            investigation.completed_at = datetime.utcnow()
            investigation.completion_percentage = 100.0
        
        await db.commit()
        await db.refresh(investigation)
        return investigation
    
    async def get_user_investigations(
        self,
        db: AsyncSession,
        user: User,
        status: Optional[InvestigationStatus] = None,
        priority: Optional[InvestigationPriority] = None,
        investigation_type: Optional[str] = None,
        search_query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Investigation]:
        """Get user's investigations with filtering"""
        
        query = select(Investigation).where(
            or_(
                Investigation.user_id == user.id,
                Investigation.lead_investigator_id == user.id,
                Investigation.assigned_users.contains([user.id])
            )
        )
        
        if status:
            query = query.where(Investigation.status == status)
        
        if priority:
            query = query.where(Investigation.priority == priority)
        
        if investigation_type:
            query = query.where(Investigation.investigation_type == investigation_type)
        
        if search_query:
            search_filter = or_(
                Investigation.title.contains(search_query),
                Investigation.description.contains(search_query),
                Investigation.case_number.contains(search_query)
            )
            query = query.where(search_filter)
        
        if tags:
            for tag in tags:
                query = query.where(Investigation.tags.contains([tag]))
        
        query = query.order_by(Investigation.updated_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    async def delete_investigation(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int
    ) -> bool:
        """Delete an investigation (soft delete by archiving)"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return False
        
        # Soft delete by archiving
        investigation.status = InvestigationStatus.ARCHIVED
        investigation.updated_at = datetime.utcnow()
        
        await db.commit()
        return True
    
    # Evidence Management
    async def add_evidence(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        title: str,
        description: str,
        evidence_type: EvidenceType,
        source_url: str = None,
        page_id: int = None,
        file_path: str = None,
        metadata: Dict[str, Any] = None,
        tags: List[str] = None,
        relevance_score: float = 0.5,
        importance_score: float = 0.5
    ) -> Optional[Evidence]:
        """Add evidence to an investigation"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return None
        
        # Calculate content hash if applicable
        content_hash = None
        if source_url:
            content_hash = hashlib.sha256(source_url.encode()).hexdigest()
        elif file_path:
            # In production, calculate hash of file content
            content_hash = hashlib.sha256(file_path.encode()).hexdigest()
        
        evidence = Evidence(
            investigation_id=investigation_id,
            user_id=user.id,
            page_id=page_id,
            title=title,
            description=description,
            evidence_type=evidence_type,
            source_url=source_url,
            file_path=file_path,
            content_hash=content_hash,
            metadata=metadata or {},
            tags=tags or [],
            relevance_score=relevance_score,
            importance_score=importance_score,
            discovery_method="manual_upload"
        )
        
        # Initialize custody log
        evidence.custody_log = [{
            "action": "created",
            "user_id": user.id,
            "timestamp": datetime.utcnow().isoformat(),
            "notes": "Evidence created and added to investigation"
        }]
        
        db.add(evidence)
        
        # Update investigation evidence count
        investigation.evidence_count += 1
        investigation.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(evidence)
        return evidence
    
    async def verify_evidence(
        self,
        db: AsyncSession,
        user: User,
        evidence_id: int,
        is_verified: bool = True,
        verification_notes: str = None
    ) -> Optional[Evidence]:
        """Verify or dispute evidence"""
        
        result = await db.execute(
            select(Evidence).where(Evidence.id == evidence_id)
        )
        evidence = result.scalar_one_or_none()
        
        if not evidence:
            return None
        
        # Check if user has access to the investigation
        investigation = await self._get_user_investigation(db, user, evidence.investigation_id)
        if not investigation:
            return None
        
        evidence.status = EvidenceStatus.VERIFIED if is_verified else EvidenceStatus.DISPUTED
        evidence.verified_by_user_id = user.id
        evidence.verified_at = datetime.utcnow()
        evidence.verification_notes = verification_notes
        
        # Update custody log
        evidence.custody_log.append({
            "action": "verified" if is_verified else "disputed",
            "user_id": user.id,
            "timestamp": datetime.utcnow().isoformat(),
            "notes": verification_notes or ""
        })
        
        await db.commit()
        await db.refresh(evidence)
        return evidence
    
    async def get_investigation_evidence(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        evidence_type: Optional[EvidenceType] = None,
        status: Optional[EvidenceStatus] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Evidence]:
        """Get evidence for an investigation"""
        
        # Check access to investigation
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return []
        
        query = select(Evidence).where(Evidence.investigation_id == investigation_id)
        
        if evidence_type:
            query = query.where(Evidence.evidence_type == evidence_type)
        
        if status:
            query = query.where(Evidence.status == status)
        
        if tags:
            for tag in tags:
                query = query.where(Evidence.tags.contains([tag]))
        
        query = query.order_by(Evidence.importance_score.desc(), Evidence.discovered_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    # Page Comparison
    async def create_page_comparison(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        baseline_page_id: int,
        target_page_id: int,
        comparison_title: str,
        description: str = None,
        comparison_fields: List[str] = None,
        ignore_fields: List[str] = None
    ) -> Optional[PageComparison]:
        """Create a page comparison for change detection"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return None
        
        # Get the pages
        baseline_result = await db.execute(select(Page).where(Page.id == baseline_page_id))
        baseline_page = baseline_result.scalar_one_or_none()
        
        target_result = await db.execute(select(Page).where(Page.id == target_page_id))
        target_page = target_result.scalar_one_or_none()
        
        if not baseline_page or not target_page:
            return None
        
        start_time = datetime.utcnow()
        
        # Perform comparison
        comparison_result = await self._compare_pages(
            baseline_page, target_page, comparison_fields or [], ignore_fields or []
        )
        
        end_time = datetime.utcnow()
        execution_time = int((end_time - start_time).total_seconds() * 1000)
        
        page_comparison = PageComparison(
            investigation_id=investigation_id,
            user_id=user.id,
            baseline_page_id=baseline_page_id,
            target_page_id=target_page_id,
            comparison_title=comparison_title,
            description=description,
            comparison_fields=comparison_fields or [],
            ignore_fields=ignore_fields or [],
            differences_found=comparison_result["differences_found"],
            similarity_score=comparison_result["similarity_score"],
            change_summary=comparison_result["change_summary"],
            detailed_diff=comparison_result["detailed_diff"],
            is_significant_change=comparison_result["is_significant"],
            significance_score=comparison_result["significance_score"],
            change_categories=comparison_result["change_categories"],
            execution_time_ms=execution_time
        )
        
        db.add(page_comparison)
        await db.commit()
        await db.refresh(page_comparison)
        return page_comparison
    
    async def _compare_pages(
        self,
        baseline_page: Page,
        target_page: Page,
        comparison_fields: List[str],
        ignore_fields: List[str]
    ) -> Dict[str, Any]:
        """Compare two pages and generate difference analysis"""
        
        # Define fields to compare if not specified
        if not comparison_fields:
            comparison_fields = [
                "title", "content", "extracted_text", "meta_description",
                "meta_keywords", "author", "published_date"
            ]
        
        changes = {}
        change_categories = []
        significance_scores = []
        
        for field in comparison_fields:
            if field in ignore_fields:
                continue
            
            baseline_value = getattr(baseline_page, field, "")
            target_value = getattr(target_page, field, "")
            
            # Convert None to empty string for comparison
            baseline_str = str(baseline_value) if baseline_value is not None else ""
            target_str = str(target_value) if target_value is not None else ""
            
            if baseline_str != target_str:
                # Calculate similarity ratio
                similarity = difflib.SequenceMatcher(None, baseline_str, target_str).ratio()
                
                # Generate detailed diff
                diff = list(difflib.unified_diff(
                    baseline_str.splitlines(keepends=True),
                    target_str.splitlines(keepends=True),
                    fromfile=f"baseline_{field}",
                    tofile=f"target_{field}",
                    n=3
                ))
                
                changes[field] = {
                    "baseline": baseline_str[:1000] if len(baseline_str) > 1000 else baseline_str,
                    "target": target_str[:1000] if len(target_str) > 1000 else target_str,
                    "similarity": similarity,
                    "diff": diff[:100],  # Limit diff size
                    "change_type": self._classify_change_type(field, baseline_str, target_str)
                }
                
                # Categorize changes
                if field in ["title", "extracted_title"]:
                    change_categories.append("title_change")
                    significance_scores.append(0.8)
                elif field in ["content", "extracted_text"]:
                    change_categories.append("content_change")
                    significance_scores.append(0.9)
                elif field in ["meta_description", "meta_keywords"]:
                    change_categories.append("metadata_change")
                    significance_scores.append(0.4)
                elif field == "author":
                    change_categories.append("authorship_change")
                    significance_scores.append(0.6)
                elif field == "published_date":
                    change_categories.append("temporal_change")
                    significance_scores.append(0.7)
        
        differences_found = len(changes) > 0
        overall_similarity = 1.0 - (len(changes) / len(comparison_fields)) if comparison_fields else 1.0
        significance_score = max(significance_scores) if significance_scores else 0.0
        is_significant = significance_score > 0.5
        
        change_summary = {
            "total_fields_compared": len(comparison_fields),
            "fields_changed": len(changes),
            "change_percentage": (len(changes) / len(comparison_fields)) * 100 if comparison_fields else 0,
            "most_significant_change": max(changes.keys(), key=lambda x: changes[x]["similarity"]) if changes else None
        }
        
        return {
            "differences_found": differences_found,
            "similarity_score": overall_similarity,
            "change_summary": change_summary,
            "detailed_diff": changes,
            "is_significant": is_significant,
            "significance_score": significance_score,
            "change_categories": list(set(change_categories))
        }
    
    def _classify_change_type(self, field: str, baseline: str, target: str) -> str:
        """Classify the type of change between two field values"""
        
        baseline_len = len(baseline.strip())
        target_len = len(target.strip())
        
        if baseline_len == 0 and target_len > 0:
            return "addition"
        elif baseline_len > 0 and target_len == 0:
            return "deletion"
        elif abs(baseline_len - target_len) / max(baseline_len, target_len, 1) > 0.5:
            return "major_modification"
        else:
            return "minor_modification"
    
    # Timeline Management
    async def add_timeline_event(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        event_title: str,
        event_description: str,
        event_date: datetime,
        event_type: str = None,
        event_category: str = None,
        significance_level: int = 3,
        location: str = None,
        source_urls: List[str] = None,
        evidence_ids: List[int] = None,
        tags: List[str] = None,
        is_milestone: bool = False
    ) -> Optional[InvestigationTimeline]:
        """Add a timeline event to an investigation"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return None
        
        # Get next sequence number
        max_seq_result = await db.execute(
            select(func.max(InvestigationTimeline.sequence_number)).where(
                InvestigationTimeline.investigation_id == investigation_id
            )
        )
        max_seq = max_seq_result.scalar() or 0
        
        timeline_event = InvestigationTimeline(
            investigation_id=investigation_id,
            user_id=user.id,
            event_title=event_title,
            event_description=event_description,
            event_date=event_date,
            event_type=event_type,
            event_category=event_category,
            significance_level=significance_level,
            location=location,
            source_urls=source_urls or [],
            evidence_ids=evidence_ids or [],
            tags=tags or [],
            is_milestone=is_milestone,
            sequence_number=max_seq + 1
        )
        
        db.add(timeline_event)
        
        # Update investigation timeline count
        investigation.timeline_events_count += 1
        investigation.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(timeline_event)
        return timeline_event
    
    async def get_investigation_timeline(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_type: Optional[str] = None,
        significance_level: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[InvestigationTimeline]:
        """Get timeline events for an investigation"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return []
        
        query = select(InvestigationTimeline).where(
            InvestigationTimeline.investigation_id == investigation_id
        )
        
        if start_date:
            query = query.where(InvestigationTimeline.event_date >= start_date)
        
        if end_date:
            query = query.where(InvestigationTimeline.event_date <= end_date)
        
        if event_type:
            query = query.where(InvestigationTimeline.event_type == event_type)
        
        if significance_level:
            query = query.where(InvestigationTimeline.significance_level >= significance_level)
        
        query = query.order_by(InvestigationTimeline.event_date.asc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    # Findings Management
    async def create_finding(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        finding_title: str,
        finding_description: str,
        finding_type: str = None,
        severity_level: int = 3,
        confidence_level: float = 0.5,
        key_points: List[str] = None,
        implications: str = None,
        recommendations: str = None,
        supporting_evidence_ids: List[int] = None,
        tags: List[str] = None
    ) -> Optional[InvestigationFinding]:
        """Create an investigation finding"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return None
        
        finding = InvestigationFinding(
            investigation_id=investigation_id,
            user_id=user.id,
            finding_title=finding_title,
            finding_description=finding_description,
            finding_type=finding_type,
            severity_level=severity_level,
            confidence_level=confidence_level,
            key_points=key_points or [],
            implications=implications,
            recommendations=recommendations,
            supporting_evidence_ids=supporting_evidence_ids or [],
            tags=tags or []
        )
        
        db.add(finding)
        
        # Update investigation findings count
        investigation.findings_count += 1
        investigation.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(finding)
        return finding
    
    async def get_investigation_findings(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int,
        finding_type: Optional[str] = None,
        severity_level: Optional[int] = None,
        is_validated: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[InvestigationFinding]:
        """Get findings for an investigation"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return []
        
        query = select(InvestigationFinding).where(
            InvestigationFinding.investigation_id == investigation_id
        )
        
        if finding_type:
            query = query.where(InvestigationFinding.finding_type == finding_type)
        
        if severity_level:
            query = query.where(InvestigationFinding.severity_level >= severity_level)
        
        if is_validated is not None:
            query = query.where(InvestigationFinding.is_validated == is_validated)
        
        query = query.order_by(
            InvestigationFinding.severity_level.desc(),
            InvestigationFinding.confidence_level.desc(),
            InvestigationFinding.created_at.desc()
        )
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    # Analytics and Reporting
    async def get_investigation_analytics(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int
    ) -> Dict[str, Any]:
        """Get comprehensive analytics for an investigation"""
        
        investigation = await self._get_user_investigation(db, user, investigation_id)
        if not investigation:
            return {}
        
        # Evidence analytics
        evidence_by_type = {}
        evidence_by_status = {}
        for evidence_type in EvidenceType:
            count_result = await db.execute(
                select(func.count()).where(
                    and_(
                        Evidence.investigation_id == investigation_id,
                        Evidence.evidence_type == evidence_type
                    )
                )
            )
            evidence_by_type[evidence_type.value] = count_result.scalar() or 0
        
        for status in EvidenceStatus:
            count_result = await db.execute(
                select(func.count()).where(
                    and_(
                        Evidence.investigation_id == investigation_id,
                        Evidence.status == status
                    )
                )
            )
            evidence_by_status[status.value] = count_result.scalar() or 0
        
        # Timeline analytics
        timeline_by_significance = {}
        for level in range(1, 6):
            count_result = await db.execute(
                select(func.count()).where(
                    and_(
                        InvestigationTimeline.investigation_id == investigation_id,
                        InvestigationTimeline.significance_level == level
                    )
                )
            )
            timeline_by_significance[f"level_{level}"] = count_result.scalar() or 0
        
        # Findings analytics
        findings_by_severity = {}
        for level in range(1, 6):
            count_result = await db.execute(
                select(func.count()).where(
                    and_(
                        InvestigationFinding.investigation_id == investigation_id,
                        InvestigationFinding.severity_level == level
                    )
                )
            )
            findings_by_severity[f"level_{level}"] = count_result.scalar() or 0
        
        # Time-based analytics
        days_active = 0
        if investigation.started_at:
            end_date = investigation.completed_at or datetime.utcnow()
            days_active = (end_date - investigation.started_at).days
        
        return {
            "investigation_id": investigation_id,
            "status": investigation.status,
            "priority": investigation.priority,
            "completion_percentage": investigation.completion_percentage,
            "days_active": days_active,
            "evidence_analytics": {
                "total_count": investigation.evidence_count,
                "by_type": evidence_by_type,
                "by_status": evidence_by_status
            },
            "timeline_analytics": {
                "total_events": investigation.timeline_events_count,
                "by_significance": timeline_by_significance
            },
            "findings_analytics": {
                "total_findings": investigation.findings_count,
                "by_severity": findings_by_severity
            },
            "productivity_metrics": {
                "evidence_per_day": investigation.evidence_count / max(days_active, 1),
                "timeline_events_per_day": investigation.timeline_events_count / max(days_active, 1),
                "findings_per_day": investigation.findings_count / max(days_active, 1)
            }
        }
    
    # Helper methods
    async def _get_user_investigation(
        self,
        db: AsyncSession,
        user: User,
        investigation_id: int
    ) -> Optional[Investigation]:
        """Get investigation if user has access to it"""
        
        result = await db.execute(
            select(Investigation).where(
                and_(
                    Investigation.id == investigation_id,
                    or_(
                        Investigation.user_id == user.id,
                        Investigation.lead_investigator_id == user.id,
                        Investigation.assigned_users.contains([user.id])
                    )
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def _generate_case_number(self, db: AsyncSession, user: User) -> str:
        """Generate a unique case number for the investigation"""
        
        # Get user's investigation count for today
        today = datetime.utcnow().date()
        count_result = await db.execute(
            select(func.count()).where(
                and_(
                    Investigation.user_id == user.id,
                    func.date(Investigation.created_at) == today
                )
            )
        )
        daily_count = (count_result.scalar() or 0) + 1
        
        # Format: YYYY-MM-DD-USER_ID-SEQUENCE
        return f"{today.strftime('%Y-%m-%d')}-{user.id:04d}-{daily_count:03d}"


# Create service instance
investigation_service = InvestigationService()