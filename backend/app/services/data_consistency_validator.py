"""
Data Consistency and Validation Framework

This module provides comprehensive data consistency validation between
PostgreSQL (OLTP) and DuckDB (OLAP) databases, including conflict resolution,
data integrity checks, and business rule validation.
"""
import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set, Tuple
from uuid import UUID

import duckdb
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, SQLModel

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.project import Project
from app.models.shared_pages import PageV2
from app.services.data_sync_service import data_sync_service


# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ConsistencyCheckType(str, Enum):
    """Types of consistency checks"""
    ROW_COUNT = "row_count"
    DATA_HASH = "data_hash"
    SCHEMA_VALIDATION = "schema_validation"
    BUSINESS_RULES = "business_rules"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    TEMPORAL_CONSISTENCY = "temporal_consistency"


class ValidationSeverity(str, Enum):
    """Severity levels for validation issues"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConflictResolutionStrategy(str, Enum):
    """Strategies for resolving data conflicts"""
    LAST_WRITE_WINS = "last_write_wins"
    FIRST_WRITE_WINS = "first_write_wins"
    POSTGRESQL_WINS = "postgresql_wins"
    DUCKDB_WINS = "duckdb_wins"
    MANUAL_RESOLUTION = "manual_resolution"
    MERGE_STRATEGY = "merge_strategy"
    BUSINESS_RULES = "business_rules"


@dataclass
class ValidationResult:
    """Result of a consistency validation check"""
    check_id: str
    check_type: ConsistencyCheckType
    table_name: str
    primary_key: Optional[Any] = None
    is_consistent: bool = False
    severity: ValidationSeverity = ValidationSeverity.INFO
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    postgresql_data: Optional[Dict[str, Any]] = None
    duckdb_data: Optional[Dict[str, Any]] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)
    resolution_strategy: Optional[ConflictResolutionStrategy] = None
    resolved: bool = False
    resolution_details: Optional[Dict[str, Any]] = None


@dataclass
class ConsistencyReport:
    """Comprehensive consistency report"""
    report_id: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warnings: int = 0
    errors: int = 0
    critical_issues: int = 0
    consistency_score: float = 100.0  # Percentage (0-100)
    validation_results: List[ValidationResult] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)


class ConsistencyValidator(ABC):
    """Abstract base class for consistency validators"""
    
    @abstractmethod
    async def validate(self, table_name: str, primary_key: Optional[Any] = None) -> List[ValidationResult]:
        """Perform consistency validation"""
        pass
    
    @abstractmethod
    def get_validator_info(self) -> Dict[str, Any]:
        """Get information about this validator"""
        pass


class RowCountValidator(ConsistencyValidator):
    """Validates row counts between PostgreSQL and DuckDB"""
    
    def __init__(self):
        self._duckdb_conn = None
    
    def _get_duckdb_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create DuckDB connection"""
        if not self._duckdb_conn:
            self._duckdb_conn = duckdb.connect(settings.DUCKDB_DATABASE_PATH)
            self._duckdb_conn.execute(f"SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}'")
        return self._duckdb_conn
    
    async def validate(self, table_name: str, primary_key: Optional[Any] = None) -> List[ValidationResult]:
        """Validate row counts between databases"""
        results = []
        check_id = f"row_count_{table_name}_{datetime.utcnow().timestamp()}"
        
        try:
            # Get PostgreSQL count
            async with AsyncSessionLocal() as session:
                pg_result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                pg_count = pg_result.scalar()
            
            # Get DuckDB count
            duckdb_conn = self._get_duckdb_connection()
            duckdb_result = duckdb_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            duckdb_count = duckdb_result[0] if duckdb_result else 0
            
            # Compare counts
            is_consistent = pg_count == duckdb_count
            severity = ValidationSeverity.INFO if is_consistent else ValidationSeverity.WARNING
            
            if not is_consistent and abs(pg_count - duckdb_count) > pg_count * 0.1:  # >10% difference
                severity = ValidationSeverity.ERROR
            
            result = ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.ROW_COUNT,
                table_name=table_name,
                is_consistent=is_consistent,
                severity=severity,
                message=f"Row count comparison - PostgreSQL: {pg_count}, DuckDB: {duckdb_count}",
                details={
                    "postgresql_count": pg_count,
                    "duckdb_count": duckdb_count,
                    "difference": pg_count - duckdb_count,
                    "difference_percentage": ((pg_count - duckdb_count) / max(pg_count, 1)) * 100
                }
            )
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"Row count validation failed for {table_name}: {str(e)}")
            results.append(ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.ROW_COUNT,
                table_name=table_name,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Row count validation error: {str(e)}"
            ))
        
        return results
    
    def get_validator_info(self) -> Dict[str, Any]:
        return {
            "name": "RowCountValidator",
            "description": "Validates row counts between PostgreSQL and DuckDB",
            "check_types": [ConsistencyCheckType.ROW_COUNT.value]
        }


class DataHashValidator(ConsistencyValidator):
    """Validates data integrity using hash comparisons"""
    
    def __init__(self):
        self._duckdb_conn = None
    
    def _get_duckdb_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create DuckDB connection"""
        if not self._duckdb_conn:
            self._duckdb_conn = duckdb.connect(settings.DUCKDB_DATABASE_PATH)
            self._duckdb_conn.execute(f"SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}'")
        return self._duckdb_conn
    
    def _compute_record_hash(self, data: Dict[str, Any]) -> str:
        """Compute hash for a record"""
        # Normalize data for consistent hashing
        normalized_data = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                normalized_data[key] = value.isoformat()
            elif isinstance(value, UUID):
                normalized_data[key] = str(value)
            else:
                normalized_data[key] = value
        
        # Create deterministic JSON and hash
        json_str = json.dumps(normalized_data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    async def validate(self, table_name: str, primary_key: Optional[Any] = None) -> List[ValidationResult]:
        """Validate data integrity using hash comparisons"""
        results = []
        
        if primary_key is None:
            # Validate random sample of records
            return await self._validate_sample_records(table_name)
        else:
            # Validate specific record
            return await self._validate_single_record(table_name, primary_key)
    
    async def _validate_single_record(self, table_name: str, primary_key: Any) -> List[ValidationResult]:
        """Validate a single record"""
        check_id = f"data_hash_{table_name}_{primary_key}_{datetime.utcnow().timestamp()}"
        
        try:
            # Get PostgreSQL record
            async with AsyncSessionLocal() as session:
                pg_result = await session.execute(
                    text(f"SELECT * FROM {table_name} WHERE id = :pk"),
                    {"pk": primary_key}
                )
                pg_record = pg_result.first()
            
            if not pg_record:
                return [ValidationResult(
                    check_id=check_id,
                    check_type=ConsistencyCheckType.DATA_HASH,
                    table_name=table_name,
                    primary_key=primary_key,
                    is_consistent=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Record not found in PostgreSQL: {primary_key}"
                )]
            
            # Get DuckDB record
            duckdb_conn = self._get_duckdb_connection()
            duckdb_result = duckdb_conn.execute(
                f"SELECT * FROM {table_name} WHERE id = ?", 
                [primary_key]
            ).fetchone()
            
            if not duckdb_result:
                return [ValidationResult(
                    check_id=check_id,
                    check_type=ConsistencyCheckType.DATA_HASH,
                    table_name=table_name,
                    primary_key=primary_key,
                    is_consistent=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Record not found in DuckDB: {primary_key}"
                )]
            
            # Convert to dictionaries
            pg_data = dict(pg_record._mapping)
            duckdb_columns = [desc[0] for desc in duckdb_conn.description]
            duckdb_data = dict(zip(duckdb_columns, duckdb_result))
            
            # Compute hashes
            pg_hash = self._compute_record_hash(pg_data)
            duckdb_hash = self._compute_record_hash(duckdb_data)
            
            is_consistent = pg_hash == duckdb_hash
            
            return [ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.DATA_HASH,
                table_name=table_name,
                primary_key=primary_key,
                is_consistent=is_consistent,
                severity=ValidationSeverity.INFO if is_consistent else ValidationSeverity.WARNING,
                message=f"Data hash comparison - {'Match' if is_consistent else 'Mismatch'}",
                details={
                    "postgresql_hash": pg_hash,
                    "duckdb_hash": duckdb_hash
                },
                postgresql_data=pg_data,
                duckdb_data=duckdb_data
            )]
            
        except Exception as e:
            logger.error(f"Data hash validation failed for {table_name}[{primary_key}]: {str(e)}")
            return [ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.DATA_HASH,
                table_name=table_name,
                primary_key=primary_key,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Data hash validation error: {str(e)}"
            )]
    
    async def _validate_sample_records(self, table_name: str, sample_size: int = 100) -> List[ValidationResult]:
        """Validate a random sample of records"""
        results = []
        
        try:
            # Get random sample from PostgreSQL
            async with AsyncSessionLocal() as session:
                pg_result = await session.execute(text(f"""
                    SELECT * FROM {table_name} 
                    ORDER BY RANDOM() 
                    LIMIT :limit
                """), {"limit": sample_size})
                pg_records = pg_result.fetchall()
            
            for pg_record in pg_records:
                pg_data = dict(pg_record._mapping)
                primary_key = pg_data.get('id')
                
                if primary_key:
                    record_results = await self._validate_single_record(table_name, primary_key)
                    results.extend(record_results)
            
        except Exception as e:
            logger.error(f"Sample validation failed for {table_name}: {str(e)}")
            check_id = f"data_hash_sample_{table_name}_{datetime.utcnow().timestamp()}"
            results.append(ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.DATA_HASH,
                table_name=table_name,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Sample validation error: {str(e)}"
            ))
        
        return results
    
    def get_validator_info(self) -> Dict[str, Any]:
        return {
            "name": "DataHashValidator",
            "description": "Validates data integrity using SHA256 hash comparisons",
            "check_types": [ConsistencyCheckType.DATA_HASH.value]
        }


class BusinessRuleValidator(ConsistencyValidator):
    """Validates business rules and constraints"""
    
    def __init__(self):
        self.business_rules = {
            'users': self._validate_user_rules,
            'projects': self._validate_project_rules,
            'pages_v2': self._validate_page_rules,
            'project_pages': self._validate_project_page_rules
        }
    
    async def validate(self, table_name: str, primary_key: Optional[Any] = None) -> List[ValidationResult]:
        """Validate business rules for a table"""
        if table_name not in self.business_rules:
            return []
        
        try:
            validator_func = self.business_rules[table_name]
            return await validator_func(primary_key)
        except Exception as e:
            logger.error(f"Business rule validation failed for {table_name}: {str(e)}")
            check_id = f"business_rules_{table_name}_{datetime.utcnow().timestamp()}"
            return [ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.BUSINESS_RULES,
                table_name=table_name,
                primary_key=primary_key,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Business rule validation error: {str(e)}"
            )]
    
    async def _validate_user_rules(self, user_id: Optional[int] = None) -> List[ValidationResult]:
        """Validate user business rules"""
        results = []
        check_id = f"user_rules_{user_id or 'all'}_{datetime.utcnow().timestamp()}"
        
        try:
            async with AsyncSessionLocal() as session:
                if user_id:
                    users_query = select(User).where(User.id == user_id)
                else:
                    users_query = select(User)
                
                users_result = await session.execute(users_query)
                users = users_result.scalars().all()
                
                for user in users:
                    # Rule 1: Verified users must have approval status
                    if user.is_verified and not user.approval_status:
                        results.append(ValidationResult(
                            check_id=f"{check_id}_approval",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="users",
                            primary_key=user.id,
                            is_consistent=False,
                            severity=ValidationSeverity.WARNING,
                            message=f"Verified user {user.id} missing approval status"
                        ))
                    
                    # Rule 2: Superusers must be verified and approved
                    if user.is_superuser and (not user.is_verified or user.approval_status != 'approved'):
                        results.append(ValidationResult(
                            check_id=f"{check_id}_superuser",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="users",
                            primary_key=user.id,
                            is_consistent=False,
                            severity=ValidationSeverity.CRITICAL,
                            message=f"Superuser {user.id} not properly verified/approved"
                        ))
                    
                    # Rule 3: Users with research purpose should have institutional details
                    if (user.research_purpose and 
                        not user.academic_affiliation and 
                        not user.institutional_email):
                        results.append(ValidationResult(
                            check_id=f"{check_id}_research_details",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="users",
                            primary_key=user.id,
                            is_consistent=False,
                            severity=ValidationSeverity.INFO,
                            message=f"Research user {user.id} missing institutional details"
                        ))
                
                # If no issues found, add success result
                if not results:
                    results.append(ValidationResult(
                        check_id=check_id,
                        check_type=ConsistencyCheckType.BUSINESS_RULES,
                        table_name="users",
                        primary_key=user_id,
                        is_consistent=True,
                        severity=ValidationSeverity.INFO,
                        message="All user business rules satisfied"
                    ))
                
        except Exception as e:
            logger.error(f"User rule validation failed: {str(e)}")
            results.append(ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.BUSINESS_RULES,
                table_name="users",
                primary_key=user_id,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"User validation error: {str(e)}"
            ))
        
        return results
    
    async def _validate_project_rules(self, project_id: Optional[int] = None) -> List[ValidationResult]:
        """Validate project business rules"""
        results = []
        check_id = f"project_rules_{project_id or 'all'}_{datetime.utcnow().timestamp()}"
        
        try:
            async with AsyncSessionLocal() as session:
                if project_id:
                    projects_query = select(Project).where(Project.id == project_id)
                else:
                    projects_query = select(Project)
                
                projects_result = await session.execute(projects_query)
                projects = projects_result.scalars().all()
                
                for project in projects:
                    # Rule 1: Active projects should have at least one domain
                    if project.status != 'paused' and not project.domains:
                        results.append(ValidationResult(
                            check_id=f"{check_id}_domains",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="projects",
                            primary_key=project.id,
                            is_consistent=False,
                            severity=ValidationSeverity.WARNING,
                            message=f"Active project {project.id} has no domains"
                        ))
                    
                    # Rule 2: Projects with end_date should not be before start_date
                    if (hasattr(project, 'start_date') and hasattr(project, 'end_date') and 
                        project.start_date and project.end_date and 
                        project.end_date < project.start_date):
                        results.append(ValidationResult(
                            check_id=f"{check_id}_dates",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="projects",
                            primary_key=project.id,
                            is_consistent=False,
                            severity=ValidationSeverity.ERROR,
                            message=f"Project {project.id} end_date before start_date"
                        ))
                
                if not results:
                    results.append(ValidationResult(
                        check_id=check_id,
                        check_type=ConsistencyCheckType.BUSINESS_RULES,
                        table_name="projects",
                        primary_key=project_id,
                        is_consistent=True,
                        severity=ValidationSeverity.INFO,
                        message="All project business rules satisfied"
                    ))
                
        except Exception as e:
            logger.error(f"Project rule validation failed: {str(e)}")
            results.append(ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.BUSINESS_RULES,
                table_name="projects",
                primary_key=project_id,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Project validation error: {str(e)}"
            ))
        
        return results
    
    async def _validate_page_rules(self, page_id: Optional[UUID] = None) -> List[ValidationResult]:
        """Validate page business rules"""
        results = []
        check_id = f"page_rules_{page_id or 'all'}_{datetime.utcnow().timestamp()}"
        
        try:
            async with AsyncSessionLocal() as session:
                if page_id:
                    pages_query = select(PageV2).where(PageV2.id == page_id)
                else:
                    pages_query = select(PageV2).limit(1000)  # Sample for bulk validation
                
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()
                
                for page in pages:
                    # Rule 1: Pages with content should have word count
                    if page.content and not page.word_count:
                        results.append(ValidationResult(
                            check_id=f"{check_id}_word_count",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="pages_v2",
                            primary_key=str(page.id),
                            is_consistent=False,
                            severity=ValidationSeverity.INFO,
                            message=f"Page {page.id} has content but no word count"
                        ))
                    
                    # Rule 2: Unix timestamp should be valid
                    if page.unix_timestamp <= 0:
                        results.append(ValidationResult(
                            check_id=f"{check_id}_timestamp",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="pages_v2",
                            primary_key=str(page.id),
                            is_consistent=False,
                            severity=ValidationSeverity.ERROR,
                            message=f"Page {page.id} has invalid unix timestamp"
                        ))
                    
                    # Rule 3: Quality score should be between 0 and 1
                    if page.quality_score is not None and (page.quality_score < 0 or page.quality_score > 1):
                        results.append(ValidationResult(
                            check_id=f"{check_id}_quality_score",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="pages_v2",
                            primary_key=str(page.id),
                            is_consistent=False,
                            severity=ValidationSeverity.WARNING,
                            message=f"Page {page.id} has invalid quality score: {page.quality_score}"
                        ))
                
                if not results:
                    results.append(ValidationResult(
                        check_id=check_id,
                        check_type=ConsistencyCheckType.BUSINESS_RULES,
                        table_name="pages_v2",
                        primary_key=str(page_id) if page_id else None,
                        is_consistent=True,
                        severity=ValidationSeverity.INFO,
                        message="All page business rules satisfied"
                    ))
                
        except Exception as e:
            logger.error(f"Page rule validation failed: {str(e)}")
            results.append(ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.BUSINESS_RULES,
                table_name="pages_v2",
                primary_key=str(page_id) if page_id else None,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Page validation error: {str(e)}"
            ))
        
        return results
    
    async def _validate_project_page_rules(self, project_page_id: Optional[int] = None) -> List[ValidationResult]:
        """Validate project page junction table business rules"""
        results = []
        check_id = f"project_page_rules_{project_page_id or 'all'}_{datetime.utcnow().timestamp()}"
        
        try:
            async with AsyncSessionLocal() as session:
                # Rule: All project_pages should reference valid projects and pages
                if project_page_id:
                    query = text("""
                        SELECT pp.id, pp.project_id, pp.page_id,
                               p.id as project_exists, pv.id as page_exists
                        FROM project_pages pp
                        LEFT JOIN projects p ON pp.project_id = p.id
                        LEFT JOIN pages_v2 pv ON pp.page_id = pv.id
                        WHERE pp.id = :project_page_id
                    """)
                    params = {"project_page_id": project_page_id}
                else:
                    query = text("""
                        SELECT pp.id, pp.project_id, pp.page_id,
                               p.id as project_exists, pv.id as page_exists
                        FROM project_pages pp
                        LEFT JOIN projects p ON pp.project_id = p.id
                        LEFT JOIN pages_v2 pv ON pp.page_id = pv.id
                        LIMIT 1000
                    """)
                    params = {}
                
                result = await session.execute(query, params)
                rows = result.fetchall()
                
                for row in rows:
                    if not row.project_exists:
                        results.append(ValidationResult(
                            check_id=f"{check_id}_project_ref",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="project_pages",
                            primary_key=row.id,
                            is_consistent=False,
                            severity=ValidationSeverity.ERROR,
                            message=f"ProjectPage {row.id} references non-existent project {row.project_id}"
                        ))
                    
                    if not row.page_exists:
                        results.append(ValidationResult(
                            check_id=f"{check_id}_page_ref",
                            check_type=ConsistencyCheckType.BUSINESS_RULES,
                            table_name="project_pages",
                            primary_key=row.id,
                            is_consistent=False,
                            severity=ValidationSeverity.ERROR,
                            message=f"ProjectPage {row.id} references non-existent page {row.page_id}"
                        ))
                
                if not results:
                    results.append(ValidationResult(
                        check_id=check_id,
                        check_type=ConsistencyCheckType.BUSINESS_RULES,
                        table_name="project_pages",
                        primary_key=project_page_id,
                        is_consistent=True,
                        severity=ValidationSeverity.INFO,
                        message="All project page business rules satisfied"
                    ))
                
        except Exception as e:
            logger.error(f"Project page rule validation failed: {str(e)}")
            results.append(ValidationResult(
                check_id=check_id,
                check_type=ConsistencyCheckType.BUSINESS_RULES,
                table_name="project_pages",
                primary_key=project_page_id,
                is_consistent=False,
                severity=ValidationSeverity.ERROR,
                message=f"Project page validation error: {str(e)}"
            ))
        
        return results
    
    def get_validator_info(self) -> Dict[str, Any]:
        return {
            "name": "BusinessRuleValidator",
            "description": "Validates business rules and domain constraints",
            "check_types": [ConsistencyCheckType.BUSINESS_RULES.value],
            "supported_tables": list(self.business_rules.keys())
        }


class ConflictResolver:
    """Resolves data conflicts between PostgreSQL and DuckDB"""
    
    def __init__(self):
        self.resolution_strategies = {
            ConflictResolutionStrategy.LAST_WRITE_WINS: self._resolve_last_write_wins,
            ConflictResolutionStrategy.FIRST_WRITE_WINS: self._resolve_first_write_wins,
            ConflictResolutionStrategy.POSTGRESQL_WINS: self._resolve_postgresql_wins,
            ConflictResolutionStrategy.DUCKDB_WINS: self._resolve_duckdb_wins,
            ConflictResolutionStrategy.MERGE_STRATEGY: self._resolve_merge_strategy,
            ConflictResolutionStrategy.BUSINESS_RULES: self._resolve_business_rules
        }
    
    async def resolve_conflict(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve a data conflict based on the configured strategy"""
        if validation_result.is_consistent:
            return {"status": "no_conflict", "message": "Data is already consistent"}
        
        strategy = validation_result.resolution_strategy or ConflictResolutionStrategy.LAST_WRITE_WINS
        
        if strategy not in self.resolution_strategies:
            return {
                "status": "error",
                "message": f"Unknown resolution strategy: {strategy}"
            }
        
        try:
            resolver_func = self.resolution_strategies[strategy]
            result = await resolver_func(validation_result)
            
            # Mark as resolved if successful
            if result.get("status") == "resolved":
                validation_result.resolved = True
                validation_result.resolution_details = result
            
            return result
            
        except Exception as e:
            logger.error(f"Conflict resolution failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Resolution failed: {str(e)}"
            }
    
    async def _resolve_last_write_wins(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve conflict using last write wins strategy"""
        # Determine which data is more recent
        pg_data = validation_result.postgresql_data or {}
        duckdb_data = validation_result.duckdb_data or {}
        
        # Compare timestamps (assuming updated_at field exists)
        pg_timestamp = pg_data.get('updated_at')
        duckdb_timestamp = duckdb_data.get('updated_at')
        
        if pg_timestamp and duckdb_timestamp:
            if isinstance(pg_timestamp, str):
                pg_timestamp = datetime.fromisoformat(pg_timestamp.replace('Z', '+00:00'))
            if isinstance(duckdb_timestamp, str):
                duckdb_timestamp = datetime.fromisoformat(duckdb_timestamp.replace('Z', '+00:00'))
            
            if pg_timestamp >= duckdb_timestamp:
                # PostgreSQL wins
                return await self._sync_to_duckdb(validation_result)
            else:
                # DuckDB wins
                return await self._sync_to_postgresql(validation_result)
        
        # Default to PostgreSQL if no timestamps
        return await self._sync_to_duckdb(validation_result)
    
    async def _resolve_first_write_wins(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve conflict using first write wins strategy"""
        # Determine which data was created first
        pg_data = validation_result.postgresql_data or {}
        duckdb_data = validation_result.duckdb_data or {}
        
        pg_created = pg_data.get('created_at')
        duckdb_created = duckdb_data.get('created_at')
        
        if pg_created and duckdb_created:
            if isinstance(pg_created, str):
                pg_created = datetime.fromisoformat(pg_created.replace('Z', '+00:00'))
            if isinstance(duckdb_created, str):
                duckdb_created = datetime.fromisoformat(duckdb_created.replace('Z', '+00:00'))
            
            if pg_created <= duckdb_created:
                # PostgreSQL was first
                return await self._sync_to_duckdb(validation_result)
            else:
                # DuckDB was first
                return await self._sync_to_postgresql(validation_result)
        
        # Default to PostgreSQL if no creation timestamps
        return await self._sync_to_duckdb(validation_result)
    
    async def _resolve_postgresql_wins(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve conflict by making PostgreSQL the source of truth"""
        return await self._sync_to_duckdb(validation_result)
    
    async def _resolve_duckdb_wins(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve conflict by making DuckDB the source of truth"""
        return await self._sync_to_postgresql(validation_result)
    
    async def _resolve_merge_strategy(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve conflict by merging data from both sources"""
        pg_data = validation_result.postgresql_data or {}
        duckdb_data = validation_result.duckdb_data or {}
        
        # Simple merge strategy: non-null values from either source
        merged_data = {}
        
        # Start with PostgreSQL data
        merged_data.update(pg_data)
        
        # Add non-null values from DuckDB
        for key, value in duckdb_data.items():
            if value is not None and (key not in merged_data or merged_data[key] is None):
                merged_data[key] = value
        
        # Sync merged data to both databases
        try:
            table_name = validation_result.table_name
            primary_key = validation_result.primary_key
            
            success, operation_id = await data_sync_service.dual_write_update(
                table_name=table_name,
                primary_key=primary_key,
                data=merged_data,
                consistency_level=data_sync_service.ConsistencyLevel.STRONG
            )
            
            if success:
                return {
                    "status": "resolved",
                    "strategy": "merge",
                    "message": "Data merged from both sources",
                    "operation_id": operation_id,
                    "merged_data": merged_data
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to sync merged data"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Merge resolution failed: {str(e)}"
            }
    
    async def _resolve_business_rules(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve conflict using business logic"""
        table_name = validation_result.table_name
        
        # Table-specific business rules for conflict resolution
        if table_name == 'users':
            return await self._resolve_user_conflicts(validation_result)
        elif table_name == 'projects':
            return await self._resolve_project_conflicts(validation_result)
        elif table_name == 'pages_v2':
            return await self._resolve_page_conflicts(validation_result)
        else:
            # Default to last write wins for unknown tables
            return await self._resolve_last_write_wins(validation_result)
    
    async def _resolve_user_conflicts(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve user-specific conflicts using business rules"""
        pg_data = validation_result.postgresql_data or {}
        duckdb_data = validation_result.duckdb_data or {}
        
        # Business rule: Always prefer verified status from PostgreSQL
        resolution_data = duckdb_data.copy()
        if 'is_verified' in pg_data:
            resolution_data['is_verified'] = pg_data['is_verified']
        if 'approval_status' in pg_data:
            resolution_data['approval_status'] = pg_data['approval_status']
        
        return await self._apply_resolution_data(validation_result, resolution_data)
    
    async def _resolve_project_conflicts(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve project-specific conflicts using business rules"""
        # For projects, prefer the most recent status from either source
        return await self._resolve_last_write_wins(validation_result)
    
    async def _resolve_page_conflicts(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Resolve page-specific conflicts using business rules"""
        pg_data = validation_result.postgresql_data or {}
        duckdb_data = validation_result.duckdb_data or {}
        
        # Business rule: Prefer content from PostgreSQL, metadata from latest source
        resolution_data = {}
        
        # Always use PostgreSQL for content fields
        content_fields = ['content', 'markdown_content', 'extracted_text', 'title']
        for field in content_fields:
            if field in pg_data:
                resolution_data[field] = pg_data[field]
        
        # Use latest for metadata fields
        metadata_fields = ['quality_score', 'word_count', 'character_count']
        pg_updated = pg_data.get('updated_at')
        duckdb_updated = duckdb_data.get('updated_at')
        
        if pg_updated and duckdb_updated:
            latest_data = pg_data if pg_updated >= duckdb_updated else duckdb_data
        else:
            latest_data = pg_data
        
        for field in metadata_fields:
            if field in latest_data:
                resolution_data[field] = latest_data[field]
        
        return await self._apply_resolution_data(validation_result, resolution_data)
    
    async def _apply_resolution_data(self, validation_result: ValidationResult, resolution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply resolved data to both databases"""
        try:
            success, operation_id = await data_sync_service.dual_write_update(
                table_name=validation_result.table_name,
                primary_key=validation_result.primary_key,
                data=resolution_data,
                consistency_level=data_sync_service.ConsistencyLevel.STRONG
            )
            
            if success:
                return {
                    "status": "resolved",
                    "strategy": "business_rules",
                    "message": "Conflict resolved using business rules",
                    "operation_id": operation_id,
                    "resolution_data": resolution_data
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to apply resolution data"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to apply resolution: {str(e)}"
            }
    
    async def _sync_to_duckdb(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Sync PostgreSQL data to DuckDB"""
        try:
            pg_data = validation_result.postgresql_data or {}
            
            success, operation_id = await data_sync_service.dual_write_update(
                table_name=validation_result.table_name,
                primary_key=validation_result.primary_key,
                data=pg_data,
                consistency_level=data_sync_service.ConsistencyLevel.STRONG
            )
            
            if success:
                return {
                    "status": "resolved",
                    "strategy": "postgresql_wins",
                    "message": "Synchronized PostgreSQL data to DuckDB",
                    "operation_id": operation_id
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to sync to DuckDB"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"DuckDB sync failed: {str(e)}"
            }
    
    async def _sync_to_postgresql(self, validation_result: ValidationResult) -> Dict[str, Any]:
        """Sync DuckDB data to PostgreSQL"""
        try:
            duckdb_data = validation_result.duckdb_data or {}
            
            # This would typically require special handling since we usually
            # don't sync from DuckDB back to PostgreSQL in normal operations
            # For now, return a placeholder
            return {
                "status": "manual_intervention_required",
                "message": "DuckDB to PostgreSQL sync requires manual intervention",
                "duckdb_data": duckdb_data
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"PostgreSQL sync failed: {str(e)}"
            }


class DataConsistencyService:
    """
    Main service for data consistency validation and conflict resolution
    """
    
    def __init__(self):
        self.validators = {
            ConsistencyCheckType.ROW_COUNT: RowCountValidator(),
            ConsistencyCheckType.DATA_HASH: DataHashValidator(),
            ConsistencyCheckType.BUSINESS_RULES: BusinessRuleValidator()
        }
        self.conflict_resolver = ConflictResolver()
        self.validation_history: List[ConsistencyReport] = []
    
    async def run_consistency_check(
        self,
        tables: Optional[List[str]] = None,
        check_types: Optional[List[ConsistencyCheckType]] = None,
        primary_key: Optional[Any] = None
    ) -> ConsistencyReport:
        """Run comprehensive consistency check"""
        report_id = f"consistency_check_{datetime.utcnow().timestamp()}"
        report = ConsistencyReport(report_id=report_id)
        
        # Default tables if not specified
        if not tables:
            tables = ['users', 'projects', 'pages_v2', 'project_pages', 'scrape_pages']
        
        # Default check types if not specified
        if not check_types:
            check_types = [ConsistencyCheckType.ROW_COUNT, ConsistencyCheckType.DATA_HASH, ConsistencyCheckType.BUSINESS_RULES]
        
        start_time = datetime.utcnow()
        
        try:
            all_results = []
            
            for table_name in tables:
                for check_type in check_types:
                    if check_type in self.validators:
                        validator = self.validators[check_type]
                        
                        try:
                            results = await validator.validate(table_name, primary_key)
                            all_results.extend(results)
                        except Exception as e:
                            logger.error(f"Validation failed for {table_name} with {check_type}: {str(e)}")
                            error_result = ValidationResult(
                                check_id=f"error_{table_name}_{check_type.value}",
                                check_type=check_type,
                                table_name=table_name,
                                is_consistent=False,
                                severity=ValidationSeverity.ERROR,
                                message=f"Validation error: {str(e)}"
                            )
                            all_results.append(error_result)
            
            # Compile report statistics
            report.validation_results = all_results
            report.total_checks = len(all_results)
            
            for result in all_results:
                if result.is_consistent:
                    report.passed_checks += 1
                else:
                    report.failed_checks += 1
                
                if result.severity == ValidationSeverity.WARNING:
                    report.warnings += 1
                elif result.severity == ValidationSeverity.ERROR:
                    report.errors += 1
                elif result.severity == ValidationSeverity.CRITICAL:
                    report.critical_issues += 1
            
            # Calculate consistency score
            if report.total_checks > 0:
                report.consistency_score = (report.passed_checks / report.total_checks) * 100
            
            # Generate recommendations
            report.recommendations = self._generate_recommendations(report)
            
            # Performance metrics
            end_time = datetime.utcnow()
            report.performance_metrics = {
                "duration_seconds": (end_time - start_time).total_seconds(),
                "checks_per_second": report.total_checks / max((end_time - start_time).total_seconds(), 0.001),
                "tables_checked": len(tables),
                "check_types_run": len(check_types)
            }
            
            # Store in history
            self.validation_history.append(report)
            
            logger.info(f"Consistency check completed: {report.passed_checks}/{report.total_checks} passed")
            
        except Exception as e:
            logger.error(f"Consistency check failed: {str(e)}", exc_info=True)
            report.errors += 1
            report.validation_results.append(ValidationResult(
                check_id="check_error",
                check_type=ConsistencyCheckType.SCHEMA_VALIDATION,
                table_name="",
                is_consistent=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Consistency check error: {str(e)}"
            ))
        
        return report
    
    def _generate_recommendations(self, report: ConsistencyReport) -> List[str]:
        """Generate recommendations based on validation results"""
        recommendations = []
        
        # Analyze patterns in validation failures
        table_issues = {}
        check_type_issues = {}
        
        for result in report.validation_results:
            if not result.is_consistent:
                # Count issues by table
                table_issues[result.table_name] = table_issues.get(result.table_name, 0) + 1
                
                # Count issues by check type
                check_type_issues[result.check_type] = check_type_issues.get(result.check_type, 0) + 1
        
        # Table-specific recommendations
        for table, count in table_issues.items():
            if count >= 5:
                recommendations.append(f"Consider full resynchronization for table '{table}' ({count} issues)")
            elif count >= 2:
                recommendations.append(f"Monitor table '{table}' closely ({count} consistency issues)")
        
        # Check type recommendations
        if ConsistencyCheckType.ROW_COUNT in check_type_issues:
            recommendations.append("Row count mismatches detected - check sync processes")
        
        if ConsistencyCheckType.DATA_HASH in check_type_issues:
            recommendations.append("Data integrity issues found - investigate data corruption")
        
        if ConsistencyCheckType.BUSINESS_RULES in check_type_issues:
            recommendations.append("Business rule violations found - review data quality processes")
        
        # Performance recommendations
        duration = report.performance_metrics.get("duration_seconds", 0)
        if duration > 300:  # 5 minutes
            recommendations.append("Consistency check taking too long - consider optimizing queries or reducing scope")
        
        # Critical issue recommendations
        if report.critical_issues > 0:
            recommendations.append("Critical issues detected - immediate attention required")
        
        # Overall consistency recommendations
        if report.consistency_score < 95:
            recommendations.append("Consistency score below 95% - investigate sync processes")
        elif report.consistency_score < 99:
            recommendations.append("Consider tuning sync parameters to improve consistency")
        
        return recommendations
    
    async def resolve_conflicts(self, validation_results: List[ValidationResult]) -> List[Dict[str, Any]]:
        """Resolve conflicts for a list of validation results"""
        resolution_results = []
        
        for result in validation_results:
            if not result.is_consistent:
                try:
                    resolution = await self.conflict_resolver.resolve_conflict(result)
                    resolution_results.append({
                        "validation_result": result,
                        "resolution": resolution
                    })
                except Exception as e:
                    logger.error(f"Conflict resolution failed: {str(e)}")
                    resolution_results.append({
                        "validation_result": result,
                        "resolution": {
                            "status": "error",
                            "message": f"Resolution failed: {str(e)}"
                        }
                    })
        
        return resolution_results
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get service status and statistics"""
        recent_reports = self.validation_history[-10:]  # Last 10 reports
        
        if recent_reports:
            avg_consistency = sum(r.consistency_score for r in recent_reports) / len(recent_reports)
            total_checks = sum(r.total_checks for r in recent_reports)
            total_failures = sum(r.failed_checks for r in recent_reports)
        else:
            avg_consistency = 100.0
            total_checks = 0
            total_failures = 0
        
        return {
            "service_status": "running",
            "available_validators": [v.get_validator_info() for v in self.validators.values()],
            "validation_history_count": len(self.validation_history),
            "recent_statistics": {
                "average_consistency_score": avg_consistency,
                "total_checks_run": total_checks,
                "total_failures": total_failures,
                "failure_rate_percent": (total_failures / max(total_checks, 1)) * 100
            },
            "conflict_resolution_strategies": [strategy.value for strategy in ConflictResolutionStrategy]
        }
    
    def get_validation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get validation history summary"""
        recent_reports = self.validation_history[-limit:]
        
        return [
            {
                "report_id": report.report_id,
                "generated_at": report.generated_at.isoformat(),
                "total_checks": report.total_checks,
                "consistency_score": report.consistency_score,
                "failed_checks": report.failed_checks,
                "critical_issues": report.critical_issues,
                "duration_seconds": report.performance_metrics.get("duration_seconds", 0)
            }
            for report in recent_reports
        ]


# Global service instance
data_consistency_service = DataConsistencyService()


async def run_consistency_check(
    tables: Optional[List[str]] = None,
    check_types: Optional[List[ConsistencyCheckType]] = None
) -> ConsistencyReport:
    """Convenience function to run consistency check"""
    return await data_consistency_service.run_consistency_check(tables, check_types)