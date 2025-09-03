"""
QueryAnalyzer - Advanced SQL Query Analysis Engine
=================================================

Provides sophisticated SQL query analysis, pattern recognition, performance
prediction, and optimization suggestions for the HybridQueryRouter system.

Features:
- SQL parsing and AST analysis
- Table and column dependency tracking
- Query complexity scoring
- Performance prediction modeling
- Cost-based routing decisions
- Query optimization suggestions
- Historical performance tracking
"""

import asyncio
import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# SQL parsing - using sqlparse for basic parsing (could be enhanced with more advanced parsers)
try:
    import sqlparse
    from sqlparse import sql, tokens
    SQL_PARSER_AVAILABLE = True
except ImportError:
    sqlparse = None
    SQL_PARSER_AVAILABLE = False

from ..core.config import settings

logger = logging.getLogger(__name__)


class QueryComplexity(str, Enum):
    """Query complexity levels"""
    SIMPLE = "simple"          # Single table, basic operations
    MODERATE = "moderate"      # Multiple tables, basic joins
    COMPLEX = "complex"        # Complex joins, subqueries, aggregations
    VERY_COMPLEX = "very_complex"  # Window functions, CTEs, multiple levels


class OptimizationHint(str, Enum):
    """Query optimization hints"""
    ADD_INDEX = "add_index"
    PARTITION_TABLE = "partition_table"
    REWRITE_SUBQUERY = "rewrite_subquery"
    USE_MATERIALIZED_VIEW = "use_materialized_view"
    LIMIT_RESULT_SIZE = "limit_result_size"
    OPTIMIZE_JOIN_ORDER = "optimize_join_order"
    USE_COVERING_INDEX = "use_covering_index"
    BATCH_PROCESSING = "batch_processing"


@dataclass
class TableStatistics:
    """Statistics for database tables"""
    table_name: str
    row_count: Optional[int] = None
    size_mb: Optional[float] = None
    last_analyzed: Optional[datetime] = None
    columns: Set[str] = field(default_factory=set)
    indexes: Set[str] = field(default_factory=set)
    
    # Performance characteristics
    avg_scan_time: float = 0.0
    avg_index_scan_time: float = 0.0
    selectivity_estimates: Dict[str, float] = field(default_factory=dict)


@dataclass
class QueryPlan:
    """Execution plan analysis"""
    estimated_cost: float
    estimated_rows: int
    estimated_duration: float
    memory_estimate_mb: int
    operations: List[str] = field(default_factory=list)
    join_order: List[str] = field(default_factory=list)
    index_usage: Dict[str, str] = field(default_factory=dict)
    scan_types: Dict[str, str] = field(default_factory=dict)


@dataclass 
class QueryAnalysis:
    """Complete query analysis result"""
    # Basic characteristics
    query_hash: str
    query_type: str
    complexity: QueryComplexity
    tables_involved: Set[str]
    columns_used: Set[str]
    operations: Set[str]
    
    # Structure analysis
    has_joins: bool = False
    has_subqueries: bool = False
    has_aggregations: bool = False
    has_window_functions: bool = False
    has_ctes: bool = False
    join_count: int = 0
    subquery_count: int = 0
    
    # Performance predictions
    estimated_plan: Optional[QueryPlan] = None
    recommended_database: str = "postgresql"
    confidence_score: float = 0.5
    
    # Optimization suggestions
    optimization_hints: List[OptimizationHint] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    
    # Historical data
    historical_performance: Dict[str, Any] = field(default_factory=dict)
    last_analyzed: datetime = field(default_factory=datetime.now)


class TableStatsManager:
    """Manages table statistics and metadata"""
    
    def __init__(self):
        self.table_stats: Dict[str, TableStatistics] = {}
        self._stats_cache_ttl = timedelta(hours=1)
        self._last_refresh: Optional[datetime] = None
    
    async def get_table_stats(self, table_name: str) -> Optional[TableStatistics]:
        """Get statistics for a table"""
        # Check cache first
        if table_name in self.table_stats:
            stats = self.table_stats[table_name]
            if stats.last_analyzed and (datetime.now() - stats.last_analyzed) < self._stats_cache_ttl:
                return stats
        
        # Refresh stats if needed
        await self._refresh_table_stats(table_name)
        return self.table_stats.get(table_name)
    
    async def _refresh_table_stats(self, table_name: str):
        """Refresh table statistics from database"""
        try:
            # This would typically query the database for actual statistics
            # For now, we'll use estimates based on known table patterns
            stats = await self._estimate_table_stats(table_name)
            self.table_stats[table_name] = stats
            
        except Exception as e:
            logger.error(f"Failed to refresh stats for table {table_name}: {e}")
    
    async def _estimate_table_stats(self, table_name: str) -> TableStatistics:
        """Estimate table statistics based on patterns"""
        # Default estimates - in production, these would come from actual DB stats
        size_estimates = {
            "users": TableStatistics(
                table_name="users",
                row_count=10000,
                size_mb=50.0,
                columns={"id", "email", "full_name", "created_at", "is_active"}
            ),
            "projects": TableStatistics(
                table_name="projects", 
                row_count=50000,
                size_mb=200.0,
                columns={"id", "name", "owner_id", "created_at", "status"}
            ),
            "pages_v2": TableStatistics(
                table_name="pages_v2",
                row_count=5000000,
                size_mb=50000.0,
                columns={"id", "url", "title", "content", "timestamp", "domain"}
            ),
            "scrape_pages": TableStatistics(
                table_name="scrape_pages",
                row_count=10000000,
                size_mb=100000.0,
                columns={"id", "url", "status", "created_at", "domain_id"}
            )
        }
        
        stats = size_estimates.get(table_name)
        if stats:
            stats.last_analyzed = datetime.now()
            return stats
        
        # Default for unknown tables
        return TableStatistics(
            table_name=table_name,
            row_count=1000,
            size_mb=10.0,
            last_analyzed=datetime.now()
        )


class SQLParser:
    """SQL parsing and analysis utilities"""
    
    def __init__(self):
        self.sql_keywords = {
            'SELECT', 'FROM', 'WHERE', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'OUTER',
            'GROUP', 'BY', 'HAVING', 'ORDER', 'LIMIT', 'OFFSET', 'UNION', 'EXCEPT',
            'INTERSECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'ALTER', 'INDEX', 'VIEW', 'TRIGGER', 'FUNCTION', 'PROCEDURE'
        }
        
        self.aggregate_functions = {
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'STDDEV', 'VARIANCE'
        }
        
        self.window_functions = {
            'ROW_NUMBER', 'RANK', 'DENSE_RANK', 'NTILE', 'LAG', 'LEAD',
            'FIRST_VALUE', 'LAST_VALUE', 'NTH_VALUE'
        }
    
    def parse_query(self, query: str) -> Dict[str, Any]:
        """Parse SQL query and extract structural information"""
        if not SQL_PARSER_AVAILABLE:
            return self._fallback_parse(query)
        
        try:
            parsed = sqlparse.parse(query)[0]
            return self._analyze_parsed_query(parsed)
        except Exception as e:
            logger.warning(f"SQL parsing failed, using fallback: {e}")
            return self._fallback_parse(query)
    
    def _analyze_parsed_query(self, parsed) -> Dict[str, Any]:
        """Analyze parsed SQL query using sqlparse"""
        analysis = {
            'tables': set(),
            'columns': set(),
            'operations': set(),
            'joins': [],
            'subqueries': 0,
            'aggregations': set(),
            'window_functions': set(),
            'has_cte': False
        }
        
        # Recursive analysis of tokens
        self._analyze_tokens(parsed.tokens, analysis)
        
        return analysis
    
    def _analyze_tokens(self, tokens, analysis):
        """Recursively analyze SQL tokens"""
        for token in tokens:
            if token.ttype is tokens.Keyword:
                analysis['operations'].add(token.value.upper())
                
            elif token.ttype is tokens.Name:
                # Could be table or column name
                analysis['columns'].add(token.value.lower())
                
            elif hasattr(token, 'tokens'):
                # Recursively analyze sub-tokens
                self._analyze_tokens(token.tokens, analysis)
                
            # Check for specific patterns
            token_str = str(token).upper()
            
            # Detect tables in FROM clauses
            if 'FROM' in token_str:
                self._extract_from_tables(token_str, analysis)
                
            # Detect JOIN operations
            if 'JOIN' in token_str:
                analysis['joins'].append(token_str)
                
            # Detect subqueries
            if '(' in token_str and 'SELECT' in token_str:
                analysis['subqueries'] += token_str.count('SELECT') - 1
                
            # Detect CTEs
            if token_str.startswith('WITH'):
                analysis['has_cte'] = True
                
            # Detect aggregate functions
            for agg_func in self.aggregate_functions:
                if f"{agg_func}(" in token_str:
                    analysis['aggregations'].add(agg_func)
                    
            # Detect window functions
            for win_func in self.window_functions:
                if f"{win_func}(" in token_str:
                    analysis['window_functions'].add(win_func)
    
    def _extract_from_tables(self, from_clause: str, analysis):
        """Extract table names from FROM clause"""
        # Simple regex extraction (could be enhanced)
        table_pattern = r'FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(table_pattern, from_clause)
        analysis['tables'].update(match.lower() for match in matches)
    
    def _fallback_parse(self, query: str) -> Dict[str, Any]:
        """Fallback parsing using regex patterns"""
        query_upper = query.upper()
        
        analysis = {
            'tables': set(),
            'columns': set(),
            'operations': set(),
            'joins': [],
            'subqueries': 0,
            'aggregations': set(),
            'window_functions': set(),
            'has_cte': False
        }
        
        # Extract operations
        for keyword in self.sql_keywords:
            if keyword in query_upper:
                analysis['operations'].add(keyword)
        
        # Extract table names
        table_patterns = [
            r'FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'JOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'UPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        ]
        
        for pattern in table_patterns:
            matches = re.findall(pattern, query_upper)
            analysis['tables'].update(match.lower() for match in matches)
        
        # Count subqueries
        analysis['subqueries'] = query_upper.count('SELECT') - 1
        
        # Detect JOINs
        join_types = ['INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'OUTER JOIN', 'JOIN']
        for join_type in join_types:
            if join_type in query_upper:
                analysis['joins'].append(join_type)
        
        # Detect aggregations
        for agg_func in self.aggregate_functions:
            if f"{agg_func}(" in query_upper:
                analysis['aggregations'].add(agg_func)
        
        # Detect window functions
        for win_func in self.window_functions:
            if f"{win_func}(" in query_upper:
                analysis['window_functions'].add(win_func)
        
        # Detect CTEs
        analysis['has_cte'] = query_upper.strip().startswith('WITH')
        
        return analysis


class PerformancePredictor:
    """Predicts query performance characteristics"""
    
    def __init__(self, stats_manager: TableStatsManager):
        self.stats_manager = stats_manager
        self.historical_data: Dict[str, List[float]] = defaultdict(list)
    
    async def predict_performance(
        self,
        query_analysis: Dict[str, Any],
        query: str
    ) -> QueryPlan:
        """Predict query performance characteristics"""
        
        # Base cost estimation
        base_cost = 1.0
        estimated_rows = 100
        estimated_duration = 0.1
        memory_estimate = 10  # MB
        
        tables = query_analysis['tables']
        operations = query_analysis['operations']
        
        # Analyze table characteristics
        total_rows = 0
        for table in tables:
            stats = await self.stats_manager.get_table_stats(table)
            if stats and stats.row_count:
                total_rows += stats.row_count
                base_cost += stats.row_count / 1000  # Scale factor
        
        # Adjust for operations
        if 'SELECT' in operations:
            if query_analysis['joins']:
                # Join complexity
                join_factor = len(query_analysis['joins']) ** 1.5
                base_cost *= join_factor
                estimated_duration *= join_factor
                memory_estimate *= join_factor
                
                # Estimate join result size
                if total_rows > 0:
                    estimated_rows = min(total_rows * len(query_analysis['joins']), total_rows * 10)
        
        # Aggregation complexity
        if query_analysis['aggregations']:
            agg_factor = len(query_analysis['aggregations']) * 1.2
            base_cost *= agg_factor
            estimated_duration *= agg_factor
            estimated_rows = max(estimated_rows // 10, 1)  # Aggregations reduce row count
        
        # Window function complexity
        if query_analysis['window_functions']:
            window_factor = len(query_analysis['window_functions']) * 2
            base_cost *= window_factor
            estimated_duration *= window_factor
            memory_estimate *= window_factor
        
        # Subquery complexity
        if query_analysis['subqueries'] > 0:
            subquery_factor = query_analysis['subqueries'] * 1.5
            base_cost *= subquery_factor
            estimated_duration *= subquery_factor
        
        # CTE complexity
        if query_analysis['has_cte']:
            base_cost *= 1.3
            estimated_duration *= 1.3
            memory_estimate *= 1.5
        
        # Write operation overhead
        if any(op in operations for op in ['INSERT', 'UPDATE', 'DELETE']):
            base_cost *= 1.2
            estimated_duration *= 1.1
        
        return QueryPlan(
            estimated_cost=base_cost,
            estimated_rows=int(estimated_rows),
            estimated_duration=estimated_duration,
            memory_estimate_mb=int(memory_estimate),
            operations=list(operations),
            join_order=query_analysis['joins'],
            scan_types=self._predict_scan_types(tables, query_analysis)
        )
    
    def _predict_scan_types(self, tables: Set[str], analysis: Dict[str, Any]) -> Dict[str, str]:
        """Predict scan types for tables"""
        scan_types = {}
        
        for table in tables:
            # Simple heuristics for scan type prediction
            if analysis['joins'] and len(analysis['joins']) > 2:
                scan_types[table] = "nested_loop"
            elif analysis['aggregations']:
                scan_types[table] = "hash_aggregate"
            else:
                scan_types[table] = "sequential_scan"
        
        return scan_types
    
    def record_actual_performance(self, query_hash: str, execution_time: float):
        """Record actual query performance for learning"""
        self.historical_data[query_hash].append(execution_time)
        
        # Keep only recent history (last 100 executions)
        if len(self.historical_data[query_hash]) > 100:
            self.historical_data[query_hash] = self.historical_data[query_hash][-100:]


class OptimizationSuggester:
    """Suggests query optimizations"""
    
    def __init__(self, stats_manager: TableStatsManager):
        self.stats_manager = stats_manager
    
    async def suggest_optimizations(
        self,
        query: str,
        analysis: Dict[str, Any],
        predicted_plan: QueryPlan
    ) -> Tuple[List[OptimizationHint], List[str]]:
        """Suggest optimizations and identify risk factors"""
        
        hints = []
        risks = []
        
        # Performance-based suggestions
        if predicted_plan.estimated_duration > 10.0:
            risks.append("Query estimated to take >10 seconds")
            
            if analysis['joins']:
                hints.append(OptimizationHint.OPTIMIZE_JOIN_ORDER)
                hints.append(OptimizationHint.ADD_INDEX)
        
        if predicted_plan.memory_estimate_mb > 1000:
            risks.append("High memory usage predicted (>1GB)")
            hints.append(OptimizationHint.LIMIT_RESULT_SIZE)
        
        if predicted_plan.estimated_rows > 100000:
            risks.append("Large result set (>100k rows)")
            hints.append(OptimizationHint.LIMIT_RESULT_SIZE)
            
            if not any("LIMIT" in op for op in analysis['operations']):
                risks.append("No LIMIT clause for large result set")
        
        # Structure-based suggestions
        if len(analysis['joins']) > 3:
            hints.append(OptimizationHint.OPTIMIZE_JOIN_ORDER)
            risks.append("Complex join pattern detected")
        
        if analysis['subqueries'] > 2:
            hints.append(OptimizationHint.REWRITE_SUBQUERY)
            risks.append("Multiple subqueries may impact performance")
        
        if analysis['has_cte'] and analysis['aggregations']:
            hints.append(OptimizationHint.USE_MATERIALIZED_VIEW)
        
        # Table-specific suggestions
        for table in analysis['tables']:
            stats = await self.stats_manager.get_table_stats(table)
            if stats and stats.row_count and stats.row_count > 1000000:
                hints.append(OptimizationHint.PARTITION_TABLE)
                
                if not stats.indexes:
                    hints.append(OptimizationHint.ADD_INDEX)
        
        # Remove duplicates
        hints = list(set(hints))
        risks = list(set(risks))
        
        return hints, risks


class QueryAnalyzer:
    """
    Main query analyzer orchestrating all analysis components
    """
    
    def __init__(self):
        self.stats_manager = TableStatsManager()
        self.sql_parser = SQLParser()
        self.performance_predictor = PerformancePredictor(self.stats_manager)
        self.optimization_suggester = OptimizationSuggester(self.stats_manager)
        
        # Analysis cache
        self.analysis_cache: Dict[str, QueryAnalysis] = {}
        self.cache_ttl = timedelta(minutes=30)
        
        logger.info("QueryAnalyzer initialized")
    
    async def analyze_query(self, query: str, use_cache: bool = True) -> QueryAnalysis:
        """
        Perform comprehensive query analysis
        
        Args:
            query: SQL query string
            use_cache: Whether to use cached analysis
            
        Returns:
            Complete QueryAnalysis object
        """
        # Generate query hash
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        
        # Check cache
        if use_cache and query_hash in self.analysis_cache:
            cached_analysis = self.analysis_cache[query_hash]
            if datetime.now() - cached_analysis.last_analyzed < self.cache_ttl:
                return cached_analysis
        
        # Parse query structure
        parsed_info = self.sql_parser.parse_query(query)
        
        # Determine complexity
        complexity = self._determine_complexity(parsed_info)
        
        # Predict performance
        predicted_plan = await self.performance_predictor.predict_performance(
            parsed_info, query
        )
        
        # Get optimization suggestions
        hints, risks = await self.optimization_suggester.suggest_optimizations(
            query, parsed_info, predicted_plan
        )
        
        # Recommend database
        recommended_db, confidence = self._recommend_database(
            parsed_info, predicted_plan, complexity
        )
        
        # Get historical performance
        historical_perf = self._get_historical_performance(query_hash)
        
        # Create analysis result
        analysis = QueryAnalysis(
            query_hash=query_hash,
            query_type=self._classify_query_type(parsed_info),
            complexity=complexity,
            tables_involved=parsed_info['tables'],
            columns_used=parsed_info['columns'],
            operations=parsed_info['operations'],
            has_joins=bool(parsed_info['joins']),
            has_subqueries=parsed_info['subqueries'] > 0,
            has_aggregations=bool(parsed_info['aggregations']),
            has_window_functions=bool(parsed_info['window_functions']),
            has_ctes=parsed_info['has_cte'],
            join_count=len(parsed_info['joins']),
            subquery_count=parsed_info['subqueries'],
            estimated_plan=predicted_plan,
            recommended_database=recommended_db,
            confidence_score=confidence,
            optimization_hints=hints,
            risk_factors=risks,
            historical_performance=historical_perf
        )
        
        # Cache the result
        self.analysis_cache[query_hash] = analysis
        
        return analysis
    
    def _determine_complexity(self, parsed_info: Dict[str, Any]) -> QueryComplexity:
        """Determine query complexity level"""
        complexity_score = 0
        
        # Base complexity factors
        complexity_score += len(parsed_info['tables'])
        complexity_score += len(parsed_info['joins']) * 2
        complexity_score += parsed_info['subqueries'] * 3
        complexity_score += len(parsed_info['aggregations'])
        complexity_score += len(parsed_info['window_functions']) * 4
        
        if parsed_info['has_cte']:
            complexity_score += 3
        
        # Classify based on score
        if complexity_score <= 2:
            return QueryComplexity.SIMPLE
        elif complexity_score <= 6:
            return QueryComplexity.MODERATE
        elif complexity_score <= 12:
            return QueryComplexity.COMPLEX
        else:
            return QueryComplexity.VERY_COMPLEX
    
    def _classify_query_type(self, parsed_info: Dict[str, Any]) -> str:
        """Classify the main query type"""
        operations = parsed_info['operations']
        
        if 'INSERT' in operations:
            return "insert"
        elif 'UPDATE' in operations:
            return "update"
        elif 'DELETE' in operations:
            return "delete"
        elif parsed_info['aggregations']:
            return "analytics"
        elif parsed_info['window_functions']:
            return "advanced_analytics"
        elif len(parsed_info['joins']) > 2:
            return "complex_select"
        else:
            return "simple_select"
    
    def _recommend_database(
        self,
        parsed_info: Dict[str, Any],
        predicted_plan: QueryPlan,
        complexity: QueryComplexity
    ) -> Tuple[str, float]:
        """Recommend optimal database and confidence score"""
        
        # Scoring system for database recommendation
        postgresql_score = 0.5  # Default neutral
        duckdb_score = 0.5
        
        # OLTP indicators (favor PostgreSQL)
        if any(op in parsed_info['operations'] for op in ['INSERT', 'UPDATE', 'DELETE']):
            postgresql_score += 0.4
        
        if len(parsed_info['tables']) == 1 and not parsed_info['aggregations']:
            postgresql_score += 0.2
        
        if predicted_plan.estimated_duration < 1.0:
            postgresql_score += 0.1
        
        # OLAP indicators (favor DuckDB)
        if parsed_info['aggregations']:
            duckdb_score += 0.3
        
        if parsed_info['window_functions']:
            duckdb_score += 0.4
        
        if complexity in [QueryComplexity.COMPLEX, QueryComplexity.VERY_COMPLEX]:
            duckdb_score += 0.2
        
        if predicted_plan.estimated_rows > 10000:
            duckdb_score += 0.2
        
        if predicted_plan.estimated_duration > 5.0:
            duckdb_score += 0.3
        
        # Make decision
        if postgresql_score > duckdb_score:
            confidence = min(postgresql_score - duckdb_score, 0.9)
            return "postgresql", confidence
        else:
            confidence = min(duckdb_score - postgresql_score, 0.9)
            return "duckdb", confidence
    
    def _get_historical_performance(self, query_hash: str) -> Dict[str, Any]:
        """Get historical performance data for query"""
        historical_data = self.performance_predictor.historical_data.get(query_hash, [])
        
        if not historical_data:
            return {"executions": 0}
        
        return {
            "executions": len(historical_data),
            "avg_time": sum(historical_data) / len(historical_data),
            "min_time": min(historical_data),
            "max_time": max(historical_data),
            "recent_trend": "stable"  # Could implement trend analysis
        }
    
    def record_execution(self, query: str, execution_time: float, database_used: str):
        """Record actual query execution for learning"""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        self.performance_predictor.record_actual_performance(query_hash, execution_time)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "cached_analyses": len(self.analysis_cache),
            "table_stats": len(self.stats_manager.table_stats),
            "historical_queries": len(self.performance_predictor.historical_data),
            "sql_parser_available": SQL_PARSER_AVAILABLE
        }
    
    def clear_cache(self):
        """Clear analysis cache"""
        self.analysis_cache.clear()
        logger.info("Query analysis cache cleared")


# Global analyzer instance
query_analyzer = QueryAnalyzer()


# Export public interface
__all__ = [
    'QueryAnalyzer',
    'QueryAnalysis',
    'QueryComplexity',
    'OptimizationHint',
    'QueryPlan',
    'TableStatistics',
    'query_analyzer'
]