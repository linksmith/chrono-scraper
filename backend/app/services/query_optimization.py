"""
Database Query Optimization Service

This service provides intelligent query optimization, N+1 query detection,
and automated performance analysis for the admin system.
"""

import logging
import re
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from contextlib import asynccontextmanager

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class QueryPattern(str, Enum):
    """Common query patterns"""
    N_PLUS_ONE = "n_plus_one"
    FULL_TABLE_SCAN = "full_table_scan"
    MISSING_INDEX = "missing_index"
    CARTESIAN_PRODUCT = "cartesian_product"
    INEFFICIENT_JOIN = "inefficient_join"
    LARGE_OFFSET = "large_offset"
    UNNECESSARY_SORT = "unnecessary_sort"
    REDUNDANT_QUERY = "redundant_query"


class OptimizationLevel(str, Enum):
    """Optimization impact levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QueryAnalysis:
    """Analysis results for a database query"""
    query_hash: str
    original_query: str
    execution_plan: Dict[str, Any]
    estimated_cost: float
    actual_time_ms: Optional[float]
    rows_examined: int
    rows_returned: int
    tables_accessed: List[str]
    indexes_used: List[str]
    missing_indexes: List[str]
    performance_issues: List[str]
    optimization_suggestions: List[str]
    optimized_query: Optional[str]
    timestamp: datetime


class QueryOptimization(BaseModel):
    """Query optimization recommendation"""
    pattern: QueryPattern
    severity: OptimizationLevel
    description: str
    current_performance: Dict[str, Any]
    suggested_optimization: str
    optimized_query: Optional[str]
    expected_improvement: str
    implementation_effort: str


class NPlusOneDetection(BaseModel):
    """N+1 query detection results"""
    parent_query: str
    child_queries: List[str]
    repetition_count: int
    total_time_ms: float
    potential_savings_ms: float
    suggested_solution: str
    optimized_approach: str


class QueryOptimizationService:
    """
    Intelligent query optimization service for admin operations.
    
    Features:
    - Automatic query plan analysis
    - N+1 query detection
    - Missing index identification
    - Query rewriting suggestions
    - Performance regression detection
    - Bulk operation optimization
    """
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.query_cache: Dict[str, QueryAnalysis] = {}
        self.n_plus_one_patterns: Dict[str, NPlusOneDetection] = {}
        
        # Admin-specific optimization patterns
        self.admin_table_relationships = {
            'users': ['user_approval', 'user_sessions', 'audit_logs'],
            'audit_logs': ['users'],
            'security_events': ['users', 'ip_blocklist'],
            'backup_executions': ['backup_schedules'],
            'projects': ['users', 'domains'],
            'pages': ['projects', 'domains', 'users'],
            'domains': ['projects']
        }
        
        # Common problematic patterns in admin queries
        self.problematic_patterns = {
            'user_list_without_pagination': r'SELECT.*FROM users.*ORDER BY.*(?!LIMIT)',
            'audit_log_full_scan': r'SELECT.*FROM audit_logs.*WHERE.*created_at.*[^><=]',
            'security_events_no_index': r'SELECT.*FROM security_events.*WHERE ip_address.*[^=]',
            'backup_status_frequent': r'SELECT.*status.*FROM backup_executions.*WHERE.*id.*IN',
            'project_pages_n_plus_one': r'SELECT.*FROM pages.*WHERE project_id.*=',
        }
    
    async def analyze_query(
        self, 
        query: str,
        params: Optional[Dict[str, Any]] = None,
        execution_time_ms: Optional[float] = None
    ) -> QueryAnalysis:
        """
        Comprehensive query analysis with optimization suggestions.
        
        Args:
            query: SQL query to analyze
            params: Query parameters
            execution_time_ms: Actual execution time if available
        
        Returns:
            QueryAnalysis with optimization recommendations
        """
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        # Check cache first
        if query_hash in self.query_cache:
            cached_analysis = self.query_cache[query_hash]
            if cached_analysis.timestamp > datetime.now() - timedelta(hours=1):
                return cached_analysis
        
        async with self.db_session_factory() as session:
            try:
                # Get execution plan
                explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
                if params:
                    result = await session.execute(text(explain_query), params)
                else:
                    result = await session.execute(text(explain_query))
                
                execution_plan = result.scalar()
                
                # Parse execution plan
                plan_data = execution_plan[0] if execution_plan else {}
                
                # Extract metrics from plan
                estimated_cost = self._extract_cost(plan_data)
                actual_time = self._extract_actual_time(plan_data) or execution_time_ms
                rows_examined = self._extract_rows_examined(plan_data)
                rows_returned = self._extract_rows_returned(plan_data)
                tables_accessed = self._extract_tables(plan_data)
                indexes_used = self._extract_indexes_used(plan_data)
                
                # Identify performance issues
                performance_issues = self._identify_performance_issues(plan_data, query)
                
                # Generate optimization suggestions
                optimization_suggestions = self._generate_optimization_suggestions(
                    query, plan_data, performance_issues
                )
                
                # Identify missing indexes
                missing_indexes = self._identify_missing_indexes(query, plan_data)
                
                # Generate optimized query if possible
                optimized_query = self._generate_optimized_query(query, performance_issues)
                
                analysis = QueryAnalysis(
                    query_hash=query_hash,
                    original_query=query,
                    execution_plan=plan_data,
                    estimated_cost=estimated_cost,
                    actual_time_ms=actual_time,
                    rows_examined=rows_examined,
                    rows_returned=rows_returned,
                    tables_accessed=tables_accessed,
                    indexes_used=indexes_used,
                    missing_indexes=missing_indexes,
                    performance_issues=performance_issues,
                    optimization_suggestions=optimization_suggestions,
                    optimized_query=optimized_query,
                    timestamp=datetime.now()
                )
                
                # Cache the analysis
                self.query_cache[query_hash] = analysis
                
                return analysis
                
            except Exception as e:
                logger.error(f"Error analyzing query: {str(e)}")
                # Return minimal analysis on error
                return QueryAnalysis(
                    query_hash=query_hash,
                    original_query=query,
                    execution_plan={},
                    estimated_cost=0.0,
                    actual_time_ms=execution_time_ms,
                    rows_examined=0,
                    rows_returned=0,
                    tables_accessed=[],
                    indexes_used=[],
                    missing_indexes=[],
                    performance_issues=[f"Analysis failed: {str(e)}"],
                    optimization_suggestions=["Retry query analysis"],
                    optimized_query=None,
                    timestamp=datetime.now()
                )
    
    def _extract_cost(self, plan_data: Dict[str, Any]) -> float:
        """Extract estimated cost from execution plan"""
        if 'Plan' in plan_data:
            return plan_data['Plan'].get('Total Cost', 0.0)
        return 0.0
    
    def _extract_actual_time(self, plan_data: Dict[str, Any]) -> Optional[float]:
        """Extract actual execution time from plan"""
        if 'Plan' in plan_data and 'Actual Total Time' in plan_data['Plan']:
            return plan_data['Plan']['Actual Total Time']
        return None
    
    def _extract_rows_examined(self, plan_data: Dict[str, Any]) -> int:
        """Extract rows examined from execution plan"""
        if 'Plan' in plan_data:
            return plan_data['Plan'].get('Actual Rows', 0)
        return 0
    
    def _extract_rows_returned(self, plan_data: Dict[str, Any]) -> int:
        """Extract rows returned from execution plan"""
        if 'Plan' in plan_data:
            return plan_data['Plan'].get('Actual Rows', 0)
        return 0
    
    def _extract_tables(self, plan_data: Dict[str, Any]) -> List[str]:
        """Extract table names from execution plan"""
        tables = set()
        
        def extract_from_node(node):
            if isinstance(node, dict):
                if 'Relation Name' in node:
                    tables.add(node['Relation Name'])
                
                # Recursively check child plans
                for key, value in node.items():
                    if key == 'Plans' and isinstance(value, list):
                        for plan in value:
                            extract_from_node(plan)
                    elif isinstance(value, dict):
                        extract_from_node(value)
        
        if 'Plan' in plan_data:
            extract_from_node(plan_data['Plan'])
        
        return list(tables)
    
    def _extract_indexes_used(self, plan_data: Dict[str, Any]) -> List[str]:
        """Extract index names used from execution plan"""
        indexes = set()
        
        def extract_from_node(node):
            if isinstance(node, dict):
                if 'Index Name' in node:
                    indexes.add(node['Index Name'])
                
                if node.get('Node Type') == 'Index Scan':
                    index_name = node.get('Index Name', 'unnamed_index')
                    indexes.add(index_name)
                
                # Recursively check child plans
                for key, value in node.items():
                    if key == 'Plans' and isinstance(value, list):
                        for plan in value:
                            extract_from_node(plan)
                    elif isinstance(value, dict):
                        extract_from_node(value)
        
        if 'Plan' in plan_data:
            extract_from_node(plan_data['Plan'])
        
        return list(indexes)
    
    def _identify_performance_issues(
        self, 
        plan_data: Dict[str, Any], 
        query: str
    ) -> List[str]:
        """Identify performance issues from execution plan"""
        issues = []
        
        if 'Plan' in plan_data:
            plan = plan_data['Plan']
            
            # Check for sequential scans on large tables
            if plan.get('Node Type') == 'Seq Scan':
                table_name = plan.get('Relation Name', 'unknown')
                if table_name in ['users', 'audit_logs', 'pages', 'security_events']:
                    issues.append(f"Sequential scan on large table '{table_name}'")
            
            # Check for high cost operations
            if plan.get('Total Cost', 0) > 10000:
                issues.append(f"High cost operation (cost: {plan.get('Total Cost', 0)})")
            
            # Check for nested loop joins with high row counts
            if plan.get('Node Type') == 'Nested Loop':
                if plan.get('Actual Rows', 0) > 1000:
                    issues.append("Nested loop join with high row count")
            
            # Check for sorts without indexes
            if plan.get('Node Type') == 'Sort':
                if plan.get('Sort Method', '').startswith('external'):
                    issues.append("External sort operation (disk-based)")
            
            # Check for hash joins that spill to disk
            if plan.get('Node Type') == 'Hash Join':
                if 'Buckets' in plan and 'Batches' in plan:
                    if plan.get('Batches', 1) > 1:
                        issues.append("Hash join spilled to disk")
        
        # Check query patterns
        query_lower = query.lower()
        
        # Large OFFSET without proper indexing
        if 'offset' in query_lower and 'limit' in query_lower:
            offset_match = re.search(r'offset\s+(\d+)', query_lower)
            if offset_match and int(offset_match.group(1)) > 1000:
                issues.append("Large OFFSET value may cause performance issues")
        
        # SELECT * on large tables
        if 'select *' in query_lower:
            for table in ['users', 'audit_logs', 'pages', 'security_events']:
                if f'from {table}' in query_lower:
                    issues.append(f"SELECT * on large table '{table}'")
        
        # Missing WHERE clauses on time-series tables
        if any(table in query_lower for table in ['audit_logs', 'security_events']):
            if 'where' not in query_lower or 'created_at' not in query_lower:
                issues.append("Query on time-series table without time range filter")
        
        return issues
    
    def _generate_optimization_suggestions(
        self, 
        query: str, 
        plan_data: Dict[str, Any], 
        performance_issues: List[str]
    ) -> List[str]:
        """Generate specific optimization suggestions"""
        suggestions = []
        query_lower = query.lower()
        
        # Suggestions based on performance issues
        for issue in performance_issues:
            if "sequential scan" in issue.lower():
                table_name = re.search(r"'(\w+)'", issue)
                if table_name:
                    table = table_name.group(1)
                    suggestions.append(f"Add appropriate index on {table} table")
            
            elif "high cost operation" in issue.lower():
                suggestions.append("Consider query rewrite or additional indexes")
            
            elif "nested loop join" in issue.lower():
                suggestions.append("Consider adding indexes on join columns or using hash join")
            
            elif "external sort" in issue.lower():
                suggestions.append("Add index to support ORDER BY clause")
            
            elif "hash join spilled" in issue.lower():
                suggestions.append("Increase work_mem or optimize join conditions")
        
        # Admin-specific optimizations
        if 'users' in query_lower:
            if 'approval_status' in query_lower and 'is_active' in query_lower:
                suggestions.append("Use composite index on (approval_status, is_active)")
            
            if 'order by created_at' in query_lower:
                suggestions.append("Ensure index on created_at for user listing queries")
        
        if 'audit_logs' in query_lower:
            if 'created_at' in query_lower and 'category' in query_lower:
                suggestions.append("Use composite index on (created_at, category) for audit queries")
            
            if 'admin_user_id' in query_lower:
                suggestions.append("Consider index on admin_user_id for admin activity tracking")
        
        if 'security_events' in query_lower:
            if 'ip_address' in query_lower:
                suggestions.append("Ensure index on ip_address for security lookups")
            
            if 'event_type' in query_lower and 'created_at' in query_lower:
                suggestions.append("Use composite index on (event_type, created_at)")
        
        # General optimization suggestions
        if 'join' in query_lower:
            suggestions.append("Ensure all JOIN columns are properly indexed")
        
        if 'group by' in query_lower:
            suggestions.append("Consider covering indexes for GROUP BY operations")
        
        if 'order by' in query_lower and 'limit' in query_lower:
            suggestions.append("Use covering index to avoid filesort with LIMIT")
        
        return suggestions
    
    def _identify_missing_indexes(
        self, 
        query: str, 
        plan_data: Dict[str, Any]
    ) -> List[str]:
        """Identify potentially missing indexes"""
        missing_indexes = []
        query_lower = query.lower()
        
        # Parse WHERE conditions for potential index candidates
        where_patterns = [
            r'where\s+(\w+)\s*=',
            r'and\s+(\w+)\s*=',
            r'join\s+\w+\s+on\s+\w+\.(\w+)\s*=',
        ]
        
        potential_columns = set()
        for pattern in where_patterns:
            matches = re.findall(pattern, query_lower)
            potential_columns.update(matches)
        
        # Admin-specific missing index patterns
        admin_index_recommendations = {
            'users': {
                ('email', 'is_active'): 'Fast user login lookups',
                ('approval_status', 'created_at'): 'Admin user management',
                ('is_locked', 'last_login'): 'Security monitoring',
            },
            'audit_logs': {
                ('created_at', 'category'): 'Time-based audit queries',
                ('admin_user_id', 'created_at'): 'Admin activity tracking',
                ('ip_address', 'created_at'): 'IP-based audit analysis',
            },
            'security_events': {
                ('ip_address', 'event_type'): 'Security threat analysis',
                ('user_id', 'created_at'): 'User security timeline',
                ('risk_score', 'created_at'): 'Risk assessment queries',
            },
            'backup_executions': {
                ('schedule_id', 'created_at'): 'Backup history queries',
                ('status', 'created_at'): 'Backup monitoring',
            }
        }
        
        # Check if query involves tables with recommended indexes
        for table, indexes in admin_index_recommendations.items():
            if table in query_lower:
                for columns, purpose in indexes.items():
                    # Check if query would benefit from this index
                    if all(col in query_lower for col in columns):
                        index_name = f"idx_{table}_{'_'.join(columns)}"
                        missing_indexes.append(
                            f"CREATE INDEX CONCURRENTLY {index_name} ON {table} "
                            f"({', '.join(columns)}); -- {purpose}"
                        )
        
        return missing_indexes
    
    def _generate_optimized_query(
        self, 
        original_query: str, 
        performance_issues: List[str]
    ) -> Optional[str]:
        """Generate an optimized version of the query"""
        optimized = original_query
        query_lower = original_query.lower()
        
        # Replace SELECT * with specific columns for common admin queries
        if 'select *' in query_lower:
            if 'from users' in query_lower:
                optimized = re.sub(
                    r'select \*', 
                    'SELECT id, email, full_name, is_active, approval_status, created_at', 
                    optimized, 
                    flags=re.IGNORECASE
                )
            elif 'from audit_logs' in query_lower:
                optimized = re.sub(
                    r'select \*', 
                    'SELECT id, action, resource_type, created_at, user_id, admin_user_id', 
                    optimized, 
                    flags=re.IGNORECASE
                )
        
        # Add LIMIT to queries that don't have one
        if ('from users' in query_lower or 'from audit_logs' in query_lower) and \
           'limit' not in query_lower and 'count(' not in query_lower:
            optimized += ' LIMIT 1000'
        
        # Add time range filters to time-series queries
        if 'from audit_logs' in query_lower and 'created_at' not in query_lower:
            if 'where' in query_lower:
                optimized = optimized.replace(
                    ' WHERE ', 
                    " WHERE created_at >= NOW() - INTERVAL '30 days' AND ", 
                    1
                )
            else:
                optimized += " WHERE created_at >= NOW() - INTERVAL '30 days'"
        
        # Only return optimized query if it's different from original
        return optimized if optimized != original_query else None
    
    async def detect_n_plus_one_queries(
        self, 
        queries: List[Tuple[str, Dict[str, Any]]], 
        time_window_ms: int = 1000
    ) -> List[NPlusOneDetection]:
        """
        Detect N+1 query patterns in a sequence of queries.
        
        Args:
            queries: List of (query, params) tuples
            time_window_ms: Time window to consider queries as related
        
        Returns:
            List of detected N+1 patterns
        """
        n_plus_one_detections = []
        
        # Group queries by similarity
        query_groups = self._group_similar_queries(queries)
        
        for group_pattern, query_list in query_groups.items():
            if len(query_list) < 3:  # Need at least 3 similar queries for N+1
                continue
            
            # Check if queries fit N+1 pattern
            if self._is_n_plus_one_pattern(query_list):
                parent_query = self._identify_parent_query(query_list)
                child_queries = [q for q in query_list if q != parent_query]
                
                # Calculate potential savings
                child_query_times = [q.get('execution_time_ms', 0) for q in child_queries]
                total_time = sum(child_query_times)
                
                # Estimate time savings with optimized query
                potential_savings = total_time * 0.8  # Assume 80% savings with proper JOIN
                
                detection = NPlusOneDetection(
                    parent_query=parent_query.get('query', '') if parent_query else '',
                    child_queries=[q.get('query', '') for q in child_queries],
                    repetition_count=len(child_queries),
                    total_time_ms=total_time,
                    potential_savings_ms=potential_savings,
                    suggested_solution=self._generate_n_plus_one_solution(
                        parent_query, child_queries
                    ),
                    optimized_approach=self._generate_optimized_approach(
                        parent_query, child_queries
                    )
                )
                
                n_plus_one_detections.append(detection)
        
        return n_plus_one_detections
    
    def _group_similar_queries(
        self, 
        queries: List[Tuple[str, Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group similar queries together"""
        groups = {}
        
        for query, params in queries:
            # Create a pattern by replacing parameter values with placeholders
            pattern = re.sub(r'=\s*\$\d+', '= ?', query)
            pattern = re.sub(r'=\s*\'\w+\'', '= ?', pattern)
            pattern = re.sub(r'=\s*\d+', '= ?', pattern)
            
            if pattern not in groups:
                groups[pattern] = []
            
            groups[pattern].append({
                'query': query,
                'params': params,
                'pattern': pattern
            })
        
        return groups
    
    def _is_n_plus_one_pattern(self, query_list: List[Dict[str, Any]]) -> bool:
        """Check if queries represent an N+1 pattern"""
        # N+1 pattern characteristics:
        # 1. Multiple similar queries (same structure, different parameters)
        # 2. Usually involves ID-based lookups
        # 3. High repetition count
        
        if len(query_list) < 3:
            return False
        
        # Check if queries have similar structure but different parameters
        first_query = query_list[0]['query']
        
        # Look for ID-based WHERE clauses
        id_patterns = [r'where\s+\w*id\s*=', r'where\s+id\s*=', r'\.id\s*=']
        has_id_lookup = any(re.search(pattern, first_query, re.IGNORECASE) for pattern in id_patterns)
        
        return has_id_lookup and len(query_list) >= 3
    
    def _identify_parent_query(self, query_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Identify the parent query that likely triggered the N+1 pattern"""
        # Parent query is often different from the repetitive child queries
        # Look for queries that are structurally different
        
        patterns = {}
        for query_data in query_list:
            pattern = query_data['pattern']
            if pattern not in patterns:
                patterns[pattern] = []
            patterns[pattern].append(query_data)
        
        # The parent is likely the pattern with fewer occurrences
        sorted_patterns = sorted(patterns.items(), key=lambda x: len(x[1]))
        
        if len(sorted_patterns) > 1:
            return sorted_patterns[0][1][0]  # First query of the least common pattern
        
        return None
    
    def _generate_n_plus_one_solution(
        self, 
        parent_query: Optional[Dict[str, Any]], 
        child_queries: List[Dict[str, Any]]
    ) -> str:
        """Generate solution for N+1 query pattern"""
        if not child_queries:
            return "No child queries detected"
        
        child_query = child_queries[0]['query']
        
        # Generate JOIN-based solution
        if 'users' in child_query.lower():
            return (
                "Replace individual user lookups with a single JOIN query. "
                "Use SELECT ... FROM parent_table JOIN users ON parent_table.user_id = users.id"
            )
        elif 'projects' in child_query.lower():
            return (
                "Use a single query with JOIN to fetch project data. "
                "Consider using SELECT ... FROM main_table JOIN projects ON condition"
            )
        elif 'pages' in child_query.lower():
            return (
                "Batch page lookups using IN clause or JOIN. "
                "Example: SELECT * FROM pages WHERE project_id IN (list_of_ids)"
            )
        else:
            return (
                "Replace multiple individual queries with a single query using JOIN "
                "or IN clause to fetch related data in one database round trip"
            )
    
    def _generate_optimized_approach(
        self, 
        parent_query: Optional[Dict[str, Any]], 
        child_queries: List[Dict[str, Any]]
    ) -> str:
        """Generate specific optimized query approach"""
        if not child_queries:
            return ""
        
        child_query = child_queries[0]['query'].lower()
        
        # Extract table and column information
        table_match = re.search(r'from\s+(\w+)', child_query)
        table_name = table_match.group(1) if table_match else 'table'
        
        where_match = re.search(r'where\s+(\w+)\s*=', child_query)
        where_column = where_match.group(1) if where_match else 'id'
        
        # Generate optimized query template
        if len(child_queries) > 1:
            return (
                f"-- Optimized approach: Single query with IN clause\n"
                f"SELECT * FROM {table_name} \n"
                f"WHERE {where_column} IN (?, ?, ?) -- List all IDs at once\n\n"
                f"-- Or use JOIN if fetching from parent table:\n"
                f"SELECT parent.*, {table_name}.* \n"
                f"FROM parent_table parent\n"
                f"JOIN {table_name} ON parent.{where_column} = {table_name}.id"
            )
        
        return f"Consider batching {table_name} lookups"
    
    async def get_optimization_recommendations(
        self, 
        table_name: Optional[str] = None
    ) -> List[QueryOptimization]:
        """Get comprehensive optimization recommendations"""
        recommendations = []
        
        # Admin-specific optimization patterns
        admin_optimizations = [
            {
                'pattern': QueryPattern.MISSING_INDEX,
                'table': 'users',
                'description': 'User management queries lack proper indexing',
                'suggestion': 'CREATE INDEX CONCURRENTLY idx_users_admin_lookup ON users (approval_status, is_active, created_at)',
                'expected_improvement': '50-80% faster user listing and filtering'
            },
            {
                'pattern': QueryPattern.FULL_TABLE_SCAN,
                'table': 'audit_logs',
                'description': 'Audit log queries performing full table scans',
                'suggestion': 'Add time-based partitioning and composite indexes on (created_at, category)',
                'expected_improvement': '70-90% faster audit queries'
            },
            {
                'pattern': QueryPattern.N_PLUS_ONE,
                'table': 'security_events',
                'description': 'Multiple individual security event lookups',
                'suggestion': 'Use batch queries with IN clauses or JOIN operations',
                'expected_improvement': '60-85% reduction in database round trips'
            },
            {
                'pattern': QueryPattern.LARGE_OFFSET,
                'table': 'pages',
                'description': 'Page pagination using large OFFSET values',
                'suggestion': 'Implement cursor-based pagination using created_at timestamps',
                'expected_improvement': 'Consistent performance regardless of page number'
            }
        ]
        
        for opt_data in admin_optimizations:
            if table_name and opt_data['table'] != table_name:
                continue
            
            recommendation = QueryOptimization(
                pattern=opt_data['pattern'],
                severity=self._determine_severity(opt_data['pattern']),
                description=opt_data['description'],
                current_performance={'status': 'suboptimal', 'table': opt_data['table']},
                suggested_optimization=opt_data['suggestion'],
                optimized_query=None,
                expected_improvement=opt_data['expected_improvement'],
                implementation_effort=self._estimate_implementation_effort(opt_data['pattern'])
            )
            
            recommendations.append(recommendation)
        
        return recommendations
    
    def _determine_severity(self, pattern: QueryPattern) -> OptimizationLevel:
        """Determine severity level for optimization pattern"""
        severity_mapping = {
            QueryPattern.N_PLUS_ONE: OptimizationLevel.CRITICAL,
            QueryPattern.FULL_TABLE_SCAN: OptimizationLevel.HIGH,
            QueryPattern.MISSING_INDEX: OptimizationLevel.HIGH,
            QueryPattern.LARGE_OFFSET: OptimizationLevel.MEDIUM,
            QueryPattern.CARTESIAN_PRODUCT: OptimizationLevel.CRITICAL,
            QueryPattern.INEFFICIENT_JOIN: OptimizationLevel.HIGH,
            QueryPattern.UNNECESSARY_SORT: OptimizationLevel.MEDIUM,
            QueryPattern.REDUNDANT_QUERY: OptimizationLevel.LOW,
        }
        
        return severity_mapping.get(pattern, OptimizationLevel.MEDIUM)
    
    def _estimate_implementation_effort(self, pattern: QueryPattern) -> str:
        """Estimate implementation effort for optimization"""
        effort_mapping = {
            QueryPattern.MISSING_INDEX: "Low - Add database index",
            QueryPattern.N_PLUS_ONE: "Medium - Modify ORM queries or add eager loading",
            QueryPattern.FULL_TABLE_SCAN: "Medium - Add indexes and query optimization",
            QueryPattern.LARGE_OFFSET: "High - Implement cursor-based pagination",
            QueryPattern.CARTESIAN_PRODUCT: "Medium - Fix JOIN conditions",
            QueryPattern.INEFFICIENT_JOIN: "Medium - Optimize JOIN order and indexes",
            QueryPattern.UNNECESSARY_SORT: "Low - Add supporting index",
            QueryPattern.REDUNDANT_QUERY: "Low - Cache results or combine queries",
        }
        
        return effort_mapping.get(pattern, "Medium - Standard optimization work")
    
    async def cleanup_old_analyses(self, hours: int = 24):
        """Clean up old query analyses"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Clean query cache
        self.query_cache = {
            query_hash: analysis 
            for query_hash, analysis in self.query_cache.items()
            if analysis.timestamp > cutoff_time
        }
        
        # Clean N+1 detection cache
        self.n_plus_one_patterns = {
            pattern: detection 
            for pattern, detection in self.n_plus_one_patterns.items()
            # N+1 patterns don't have timestamps, so we keep them
        }
        
        logger.info(f"Cleaned up query analyses older than {hours} hours")


# Global query optimization service
query_optimizer: Optional[QueryOptimizationService] = None


def get_query_optimizer() -> Optional[QueryOptimizationService]:
    """Get the global query optimization service"""
    return query_optimizer


def init_query_optimizer(db_session_factory) -> QueryOptimizationService:
    """Initialize the global query optimization service"""
    global query_optimizer
    
    query_optimizer = QueryOptimizationService(db_session_factory)
    logger.info("Query optimization service initialized successfully")
    
    return query_optimizer