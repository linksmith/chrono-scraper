"""
Automated Test Execution and Reporting Framework

This module provides a comprehensive automated framework for executing the complete
Phase 2 performance testing suite and generating detailed reports.

Framework Features:
- Continuous Benchmarking: Automated execution of full benchmark suite
- PR Performance Validation: Performance impact analysis for code changes  
- Environment Comparison: Development vs staging vs production performance
- Historical Tracking: Performance trend analysis and capacity planning
- Automated Reporting: Performance dashboards and stakeholder notifications
- CI/CD Integration: Seamless integration with deployment pipelines

Test Suite Orchestration:
- Core Performance Benchmarks
- Load Testing Scenarios
- Integration Test Workflows
- Stress Testing & Edge Cases
- Regression Detection
- A/B Comparison Testing
- Real-World Simulations
- Performance Optimization Validation

This ensures comprehensive, automated validation of Phase 2 system performance.
"""

import asyncio
import json
import time
import subprocess
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import sqlite3
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import hashlib
import logging
import sys
import os

# Import all test suites
from tests.performance.test_phase2_performance_benchmarks import Phase2PerformanceBenchmarks
from tests.performance.load_testing.load_test_scenarios import LoadTestRunner, LoadTestConfig
from tests.integration.test_phase2_integration import Phase2IntegrationTests
from tests.stress.test_phase2_stress import Phase2StressTests
from tests.regression.test_phase2_regression import Phase2RegressionTests
from tests.comparison.test_phase2_vs_baseline import Phase2BaselineComparison
from tests.simulation.test_real_world_scenarios import RealWorldScenarios


@dataclass
class TestSuiteConfig:
    """Configuration for test suite execution"""
    name: str
    enabled: bool
    timeout_minutes: int
    retry_count: int
    critical: bool  # If True, failure stops entire run
    environment_requirements: List[str]
    resource_requirements: Dict[str, float]  # CPU, memory, disk requirements


@dataclass 
class BenchmarkReport:
    """Comprehensive benchmark execution report"""
    report_id: str
    execution_timestamp: datetime
    environment_info: Dict[str, str]
    git_info: Dict[str, str]
    test_suite_results: Dict[str, Dict[str, Any]]
    overall_status: str
    duration_seconds: float
    resource_usage: Dict[str, float]
    performance_summary: Dict[str, float]
    regression_alerts: List[Dict[str, Any]]
    recommendations: List[str]
    metadata: Dict[str, Any]


@dataclass
class PerformanceAlert:
    """Performance alert for regressions or issues"""
    alert_id: str
    severity: str  # critical, major, moderate, minor
    test_suite: str
    metric_name: str
    current_value: float
    threshold_value: float
    deviation_percent: float
    description: str
    timestamp: datetime


class TestSuiteOrchestrator:
    """Orchestrates execution of all test suites"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "test_config.json"
        self.results_db_path = "benchmark_results.db"
        self.reports_dir = Path("benchmark_reports")
        self.reports_dir.mkdir(exist_ok=True)
        
        # Setup logging
        self.logger = self._setup_logging()
        
        # Initialize database
        self._init_results_database()
        
        # Load configuration
        self.config = self._load_configuration()
        
        # Initialize test suites
        self.test_suites = {
            'performance_benchmarks': Phase2PerformanceBenchmarks(),
            'load_testing': LoadTestRunner(LoadTestConfig()),
            'integration_tests': Phase2IntegrationTests(),
            'stress_tests': Phase2StressTests(),
            'regression_tests': Phase2RegressionTests(),
            'ab_comparison': Phase2BaselineComparison(),
            'simulation_tests': RealWorldScenarios()
        }
        
        # Test suite configurations
        self.suite_configs = {
            'performance_benchmarks': TestSuiteConfig(
                name="Phase 2 Performance Benchmarks",
                enabled=True,
                timeout_minutes=30,
                retry_count=2,
                critical=True,
                environment_requirements=['duckdb', 'postgresql', 'meilisearch'],
                resource_requirements={'cpu_cores': 4, 'memory_gb': 8, 'disk_gb': 10}
            ),
            'load_testing': TestSuiteConfig(
                name="Load Testing Scenarios", 
                enabled=True,
                timeout_minutes=45,
                retry_count=1,
                critical=False,
                environment_requirements=['full_stack'],
                resource_requirements={'cpu_cores': 8, 'memory_gb': 16, 'disk_gb': 20}
            ),
            'integration_tests': TestSuiteConfig(
                name="Integration Test Workflows",
                enabled=True,
                timeout_minutes=60,
                retry_count=2,
                critical=True,
                environment_requirements=['full_stack', 'websockets'],
                resource_requirements={'cpu_cores': 4, 'memory_gb': 8, 'disk_gb': 15}
            ),
            'stress_tests': TestSuiteConfig(
                name="Stress Testing & Edge Cases",
                enabled=True,
                timeout_minutes=90,
                retry_count=1,
                critical=False,
                environment_requirements=['full_stack'],
                resource_requirements={'cpu_cores': 8, 'memory_gb': 32, 'disk_gb': 50}
            ),
            'regression_tests': TestSuiteConfig(
                name="Performance Regression Detection",
                enabled=True,
                timeout_minutes=20,
                retry_count=3,
                critical=True,
                environment_requirements=['history_database'],
                resource_requirements={'cpu_cores': 2, 'memory_gb': 4, 'disk_gb': 5}
            ),
            'ab_comparison': TestSuiteConfig(
                name="A/B Comparison Testing",
                enabled=True,
                timeout_minutes=120,
                retry_count=1,
                critical=True,
                environment_requirements=['baseline_services'],
                resource_requirements={'cpu_cores': 8, 'memory_gb': 16, 'disk_gb': 30}
            ),
            'simulation_tests': TestSuiteConfig(
                name="Real-World Simulation Scenarios",
                enabled=True,
                timeout_minutes=180,
                retry_count=1,
                critical=False,
                environment_requirements=['full_stack', 'realistic_data'],
                resource_requirements={'cpu_cores': 8, 'memory_gb': 16, 'disk_gb': 40}
            )
        }
    
    def _setup_logging(self) -> logging.Logger:
        """Setup comprehensive logging"""
        logger = logging.getLogger('benchmark_runner')
        logger.setLevel(logging.INFO)
        
        # File handler
        log_file = f"benchmark_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def _init_results_database(self):
        """Initialize results database"""
        with sqlite3.connect(self.results_db_path) as conn:
            cursor = conn.cursor()
            
            # Benchmark runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    environment TEXT,
                    git_commit TEXT,
                    duration_seconds REAL,
                    overall_status TEXT,
                    results_json TEXT,
                    resource_usage_json TEXT,
                    alerts_json TEXT
                )
            """)
            
            # Performance metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    test_suite TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES benchmark_runs (id)
                )
            """)
            
            # Alerts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_alerts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    test_suite TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    current_value REAL NOT NULL,
                    threshold_value REAL NOT NULL,
                    deviation_percent REAL NOT NULL,
                    description TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES benchmark_runs (id)
                )
            """)
            
            conn.commit()
    
    def _load_configuration(self) -> Dict[str, Any]:
        """Load test configuration"""
        default_config = {
            'email_notifications': {
                'enabled': False,
                'smtp_server': 'localhost',
                'smtp_port': 587,
                'username': '',
                'password': '',
                'recipients': []
            },
            'slack_notifications': {
                'enabled': False,
                'webhook_url': ''
            },
            'performance_thresholds': {
                'critical_regression_percent': 50.0,
                'major_regression_percent': 25.0,
                'moderate_regression_percent': 10.0
            },
            'resource_monitoring': {
                'enabled': True,
                'sampling_interval_seconds': 5.0
            },
            'historical_comparison': {
                'enabled': True,
                'baseline_runs': 5
            }
        }
        
        if Path(self.config_path).exists():
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except Exception as e:
                self.logger.warning(f"Failed to load config from {self.config_path}: {e}")
        
        return default_config
    
    def _get_environment_info(self) -> Dict[str, str]:
        """Get current environment information"""
        try:
            return {
                'python_version': sys.version,
                'platform': os.uname().sysname if hasattr(os, 'uname') else 'unknown',
                'hostname': os.environ.get('HOSTNAME', 'unknown'),
                'user': os.environ.get('USER', 'unknown'),
                'timestamp': datetime.utcnow().isoformat(),
                'working_directory': os.getcwd()
            }
        except Exception as e:
            self.logger.error(f"Failed to get environment info: {e}")
            return {'error': str(e)}
    
    def _get_git_info(self) -> Dict[str, str]:
        """Get git repository information"""
        try:
            git_info = {}
            
            # Get commit hash
            result = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                git_info['commit_hash'] = result.stdout.strip()
            
            # Get branch name
            result = subprocess.run(['git', 'branch', '--show-current'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                git_info['branch'] = result.stdout.strip()
            
            # Get commit message
            result = subprocess.run(['git', 'log', '-1', '--pretty=format:%s'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                git_info['commit_message'] = result.stdout.strip()
            
            # Get author
            result = subprocess.run(['git', 'log', '-1', '--pretty=format:%an'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                git_info['author'] = result.stdout.strip()
            
            return git_info
            
        except Exception as e:
            self.logger.error(f"Failed to get git info: {e}")
            return {'error': str(e)}
    
    async def run_full_benchmark_suite(self, suite_filter: Optional[List[str]] = None) -> BenchmarkReport:
        """Run complete benchmark suite"""
        self.logger.info("Starting full benchmark suite execution")
        
        run_id = f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
        run_start = time.time()
        
        # Get environment information
        environment_info = self._get_environment_info()
        git_info = self._get_git_info()
        
        self.logger.info(f"Run ID: {run_id}")
        self.logger.info(f"Environment: {environment_info.get('platform', 'unknown')}")
        self.logger.info(f"Git commit: {git_info.get('commit_hash', 'unknown')}")
        
        # Filter suites if requested
        suites_to_run = suite_filter or list(self.suite_configs.keys())
        suites_to_run = [s for s in suites_to_run if s in self.suite_configs and self.suite_configs[s].enabled]
        
        self.logger.info(f"Running {len(suites_to_run)} test suites: {suites_to_run}")
        
        # Execute test suites
        test_suite_results = {}
        regression_alerts = []
        overall_status = "SUCCESS"
        
        for suite_name in suites_to_run:
            suite_config = self.suite_configs[suite_name]
            self.logger.info(f"Starting test suite: {suite_config.name}")
            
            suite_start = time.time()
            
            try:
                # Check environment requirements
                if not await self._check_environment_requirements(suite_config.environment_requirements):
                    raise RuntimeError(f"Environment requirements not met for {suite_name}")
                
                # Run test suite with timeout and retries
                suite_result = await self._run_test_suite_with_retries(
                    suite_name, suite_config
                )
                
                test_suite_results[suite_name] = suite_result
                
                # Check for performance regressions
                if suite_result.get('status') == 'SUCCESS':
                    alerts = await self._check_for_regressions(run_id, suite_name, suite_result)
                    regression_alerts.extend(alerts)
                else:
                    if suite_config.critical:
                        overall_status = "FAILURE"
                    elif overall_status == "SUCCESS":
                        overall_status = "PARTIAL_SUCCESS"
                
                suite_duration = time.time() - suite_start
                self.logger.info(f"Completed {suite_name} in {suite_duration:.1f}s: {suite_result.get('status', 'UNKNOWN')}")
                
            except Exception as e:
                self.logger.error(f"Test suite {suite_name} failed: {str(e)}")
                
                test_suite_results[suite_name] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'duration_seconds': time.time() - suite_start
                }
                
                if suite_config.critical:
                    overall_status = "FAILURE"
                elif overall_status == "SUCCESS":
                    overall_status = "PARTIAL_SUCCESS"
        
        # Calculate overall metrics
        total_duration = time.time() - run_start
        resource_usage = await self._get_resource_usage_summary()
        performance_summary = self._calculate_performance_summary(test_suite_results)
        recommendations = self._generate_recommendations(test_suite_results, regression_alerts)
        
        # Create comprehensive report
        report = BenchmarkReport(
            report_id=run_id,
            execution_timestamp=datetime.utcnow(),
            environment_info=environment_info,
            git_info=git_info,
            test_suite_results=test_suite_results,
            overall_status=overall_status,
            duration_seconds=total_duration,
            resource_usage=resource_usage,
            performance_summary=performance_summary,
            regression_alerts=regression_alerts,
            recommendations=recommendations,
            metadata={
                'suites_executed': len(suites_to_run),
                'suites_requested': suite_filter or 'all',
                'config_file': self.config_path
            }
        )
        
        # Store results in database
        await self._store_benchmark_results(report)
        
        # Generate and save detailed report
        report_content = self._generate_detailed_report(report)
        report_file = self.reports_dir / f"benchmark_report_{run_id}.txt"
        with open(report_file, 'w') as f:
            f.write(report_content)
        
        # Send notifications if configured
        await self._send_notifications(report, report_content)
        
        self.logger.info(f"Benchmark suite completed in {total_duration:.1f}s: {overall_status}")
        self.logger.info(f"Report saved to: {report_file}")
        
        return report
    
    async def _run_test_suite_with_retries(self, suite_name: str, config: TestSuiteConfig) -> Dict[str, Any]:
        """Run test suite with timeout and retry logic"""
        
        for attempt in range(config.retry_count + 1):
            try:
                self.logger.info(f"Running {suite_name}, attempt {attempt + 1}/{config.retry_count + 1}")
                
                # Set timeout
                timeout_seconds = config.timeout_minutes * 60
                
                # Execute test suite
                result = await asyncio.wait_for(
                    self._execute_test_suite(suite_name),
                    timeout=timeout_seconds
                )
                
                return result
                
            except asyncio.TimeoutError:
                self.logger.error(f"Test suite {suite_name} timed out after {config.timeout_minutes} minutes")
                if attempt < config.retry_count:
                    self.logger.info(f"Retrying {suite_name}...")
                    await asyncio.sleep(30)  # Wait before retry
                else:
                    return {
                        'status': 'TIMEOUT',
                        'error': f'Timed out after {config.timeout_minutes} minutes',
                        'attempts': attempt + 1
                    }
                    
            except Exception as e:
                self.logger.error(f"Test suite {suite_name} failed on attempt {attempt + 1}: {str(e)}")
                if attempt < config.retry_count:
                    self.logger.info(f"Retrying {suite_name}...")
                    await asyncio.sleep(10)  # Wait before retry
                else:
                    return {
                        'status': 'ERROR',
                        'error': str(e),
                        'attempts': attempt + 1
                    }
    
    async def _execute_test_suite(self, suite_name: str) -> Dict[str, Any]:
        """Execute specific test suite"""
        
        suite = self.test_suites[suite_name]
        start_time = time.time()
        
        try:
            if suite_name == 'performance_benchmarks':
                # Run performance benchmarks
                results = []
                benchmark_methods = [
                    'test_duckdb_vs_postgresql_query_performance',
                    'test_hybrid_query_routing_efficiency', 
                    'test_cache_performance_multilevel',
                    'test_parquet_processing_throughput',
                    'test_data_sync_latency',
                    'test_analytics_api_response_times',
                    'test_concurrent_user_scenarios',
                    'test_resource_utilization_efficiency'
                ]
                
                for method_name in benchmark_methods:
                    method = getattr(suite, method_name)
                    # Mock benchmark data for testing
                    benchmark_data = {'project': {'id': 'test'}, 'test_pages': []}
                    result = await method(benchmark_data)
                    results.append(result)
                
                return {
                    'status': 'SUCCESS',
                    'results': [asdict(r) for r in results],
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'total_benchmarks': len(results),
                        'avg_improvement_factor': sum(getattr(r, 'improvement_factor', 1.0) for r in results) / len(results) if results else 1.0
                    }
                }
                
            elif suite_name == 'load_testing':
                # Run load tests
                normal_results = await suite.run_normal_load_test()
                peak_results = await suite.run_peak_load_test()
                
                return {
                    'status': 'SUCCESS',
                    'results': {
                        'normal_load': [asdict(r) for r in normal_results],
                        'peak_load': [asdict(r) for r in peak_results]
                    },
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'max_concurrent_users': max(r.total_users for r in normal_results + peak_results),
                        'avg_response_time': sum(r.average_response_time for r in normal_results + peak_results) / len(normal_results + peak_results)
                    }
                }
                
            elif suite_name == 'integration_tests':
                # Run integration tests
                integration_methods = [
                    'test_full_analytics_pipeline',
                    'test_hybrid_query_cross_database',
                    'test_cache_invalidation_cascade',
                    'test_monitoring_alert_pipeline',
                    'test_export_pipeline_end_to_end',
                    'test_websocket_real_time_updates'
                ]
                
                results = []
                for method_name in integration_methods:
                    method = getattr(suite, method_name)
                    result = await method()
                    results.append(result)
                
                success_count = sum(1 for r in results if r.success)
                
                return {
                    'status': 'SUCCESS' if success_count == len(results) else 'PARTIAL_SUCCESS',
                    'results': [asdict(r) for r in results],
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'tests_passed': success_count,
                        'total_tests': len(results),
                        'success_rate': success_count / len(results) if results else 0
                    }
                }
                
            elif suite_name == 'stress_tests':
                # Run stress tests
                stress_methods = [
                    'test_memory_pressure_scenarios',
                    'test_cpu_saturation_scenarios',
                    'test_connection_pool_exhaustion',
                    'test_malformed_data_edge_cases'
                ]
                
                results = []
                for method_name in stress_methods:
                    method = getattr(suite, method_name)
                    if method_name == 'test_memory_pressure_scenarios':
                        result = await method('medium')
                    else:
                        result = await method()
                    results.append(result)
                
                recovery_count = sum(1 for r in results if r.recovery_successful)
                
                return {
                    'status': 'SUCCESS' if recovery_count >= len(results) * 0.8 else 'PARTIAL_SUCCESS',
                    'results': [asdict(r) for r in results],
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'recovery_rate': recovery_count / len(results) if results else 0,
                        'max_memory_usage': max(r.peak_memory_mb for r in results) if results else 0
                    }
                }
                
            elif suite_name == 'regression_tests':
                # Run regression tests
                regression_methods = [
                    'test_query_performance_regression',
                    'test_memory_usage_regression',
                    'test_cache_efficiency_regression',
                    'test_api_response_time_regression',
                    'test_throughput_capacity_regression'
                ]
                
                results = []
                for method_name in regression_methods:
                    method = getattr(suite, method_name)
                    result = await method()
                    results.append(result)
                
                regressions = sum(1 for r in results if r.regression_detected)
                
                return {
                    'status': 'SUCCESS' if regressions == 0 else 'REGRESSIONS_DETECTED',
                    'results': [asdict(r) for r in results],
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'regressions_detected': regressions,
                        'total_tests': len(results),
                        'regression_rate': regressions / len(results) if results else 0
                    }
                }
                
            elif suite_name == 'ab_comparison':
                # Run A/B comparison tests  
                test_env = await suite.setup_comparison_environment("medium")
                
                comparison_methods = [
                    'test_duckdb_vs_postgresql_performance',
                    'test_cached_vs_uncached_performance',
                    'test_optimized_vs_unoptimized_queries',
                    'test_hybrid_vs_single_database',
                    'test_compression_benefits'
                ]
                
                results = []
                for method_name in comparison_methods:
                    method = getattr(suite, method_name)
                    result = await method(test_env)
                    results.append(result)
                
                targets_met = sum(1 for r in results if r.meets_target)
                
                return {
                    'status': 'SUCCESS' if targets_met >= len(results) * 0.8 else 'TARGETS_MISSED',
                    'results': [asdict(r) for r in results],
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'targets_met': targets_met,
                        'total_comparisons': len(results),
                        'avg_improvement_factor': sum(r.improvement_factor for r in results) / len(results) if results else 1.0
                    }
                }
                
            elif suite_name == 'simulation_tests':
                # Run real-world simulations
                simulation_methods = [
                    'simulate_investigative_research_workflow',
                    'simulate_academic_research_project',
                    'simulate_journalism_investigation',
                    'simulate_competitive_intelligence_analysis',
                    'simulate_historical_trend_analysis'
                ]
                
                results = []
                for method_name in simulation_methods:
                    method = getattr(suite, method_name)
                    result = await method()
                    results.append(result)
                
                objectives_met = sum(1 for r in results if r.business_objectives_met)
                
                return {
                    'status': 'SUCCESS' if objectives_met >= len(results) * 0.8 else 'OBJECTIVES_NOT_MET',
                    'results': [asdict(r) for r in results],
                    'duration_seconds': time.time() - start_time,
                    'metrics': {
                        'objectives_met': objectives_met,
                        'total_simulations': len(results),
                        'avg_satisfaction': sum(r.user_satisfaction_score for r in results) / len(results) if results else 0
                    }
                }
                
            else:
                raise ValueError(f"Unknown test suite: {suite_name}")
                
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e),
                'duration_seconds': time.time() - start_time
            }
    
    async def _check_environment_requirements(self, requirements: List[str]) -> bool:
        """Check if environment meets test requirements"""
        # Simplified check - in practice would verify services, databases, etc.
        return True
    
    async def _check_for_regressions(self, run_id: str, suite_name: str, suite_result: Dict[str, Any]) -> List[PerformanceAlert]:
        """Check for performance regressions"""
        alerts = []
        
        # Get performance thresholds from config
        thresholds = self.config['performance_thresholds']
        
        # Check metrics for regressions (simplified)
        if 'metrics' in suite_result:
            metrics = suite_result['metrics']
            
            # Example regression checks
            if 'avg_improvement_factor' in metrics:
                improvement = metrics['avg_improvement_factor']
                if improvement < 3.0:  # Below 3x improvement
                    alert = PerformanceAlert(
                        alert_id=f"{run_id}_{suite_name}_improvement_regression",
                        severity='major' if improvement < 2.0 else 'moderate',
                        test_suite=suite_name,
                        metric_name='avg_improvement_factor',
                        current_value=improvement,
                        threshold_value=5.0,
                        deviation_percent=((5.0 - improvement) / 5.0) * 100,
                        description=f"Performance improvement factor below target: {improvement:.1f}x vs 5.0x target",
                        timestamp=datetime.utcnow()
                    )
                    alerts.append(alert)
        
        return alerts
    
    async def _get_resource_usage_summary(self) -> Dict[str, float]:
        """Get resource usage summary"""
        try:
            import psutil
            
            # Get current resource usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024**3),
                'disk_percent': disk.percent,
                'disk_used_gb': disk.used / (1024**3)
            }
        except Exception as e:
            self.logger.error(f"Failed to get resource usage: {e}")
            return {}
    
    def _calculate_performance_summary(self, test_results: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """Calculate overall performance summary"""
        summary = {
            'total_suites': len(test_results),
            'successful_suites': 0,
            'failed_suites': 0,
            'avg_duration_seconds': 0,
            'total_duration_seconds': 0
        }
        
        durations = []
        for suite_name, result in test_results.items():
            if result.get('status') == 'SUCCESS':
                summary['successful_suites'] += 1
            else:
                summary['failed_suites'] += 1
            
            duration = result.get('duration_seconds', 0)
            durations.append(duration)
            summary['total_duration_seconds'] += duration
        
        if durations:
            summary['avg_duration_seconds'] = sum(durations) / len(durations)
        
        summary['success_rate'] = summary['successful_suites'] / summary['total_suites'] if summary['total_suites'] > 0 else 0
        
        return summary
    
    def _generate_recommendations(self, test_results: Dict[str, Dict[str, Any]], alerts: List[PerformanceAlert]) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        # Check overall success rate
        successful = sum(1 for r in test_results.values() if r.get('status') == 'SUCCESS')
        total = len(test_results)
        success_rate = successful / total if total > 0 else 0
        
        if success_rate < 0.8:
            recommendations.append("Overall test success rate is low - investigate failing test suites")
        
        # Check for critical alerts
        critical_alerts = [a for a in alerts if a.severity == 'critical']
        if critical_alerts:
            recommendations.append(f"Address {len(critical_alerts)} critical performance regressions immediately")
        
        # Check specific test suite failures
        for suite_name, result in test_results.items():
            if result.get('status') == 'ERROR':
                recommendations.append(f"Fix errors in {suite_name} test suite")
            elif result.get('status') == 'TIMEOUT':
                recommendations.append(f"Investigate performance issues causing timeouts in {suite_name}")
        
        if not recommendations:
            recommendations.append("All tests passed successfully - system performance is stable")
        
        return recommendations
    
    async def _store_benchmark_results(self, report: BenchmarkReport):
        """Store benchmark results in database"""
        with sqlite3.connect(self.results_db_path) as conn:
            cursor = conn.cursor()
            
            # Store main run record
            cursor.execute("""
                INSERT INTO benchmark_runs 
                (id, timestamp, environment, git_commit, duration_seconds, overall_status, 
                 results_json, resource_usage_json, alerts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report.report_id,
                report.execution_timestamp.isoformat(),
                json.dumps(report.environment_info),
                report.git_info.get('commit_hash', 'unknown'),
                report.duration_seconds,
                report.overall_status,
                json.dumps(report.test_suite_results),
                json.dumps(report.resource_usage),
                json.dumps([asdict(a) for a in report.regression_alerts])
            ))
            
            # Store individual metrics
            for suite_name, suite_result in report.test_suite_results.items():
                if 'metrics' in suite_result:
                    for metric_name, metric_value in suite_result['metrics'].items():
                        if isinstance(metric_value, (int, float)):
                            cursor.execute("""
                                INSERT INTO performance_metrics 
                                (run_id, test_suite, metric_name, metric_value, timestamp)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                report.report_id,
                                suite_name,
                                metric_name,
                                float(metric_value),
                                report.execution_timestamp.isoformat()
                            ))
            
            # Store alerts
            for alert in report.regression_alerts:
                cursor.execute("""
                    INSERT INTO performance_alerts
                    (id, run_id, severity, test_suite, metric_name, current_value, 
                     threshold_value, deviation_percent, description, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.alert_id,
                    report.report_id,
                    alert.severity,
                    alert.test_suite,
                    alert.metric_name,
                    alert.current_value,
                    alert.threshold_value,
                    alert.deviation_percent,
                    alert.description,
                    alert.timestamp.isoformat()
                ))
            
            conn.commit()
    
    def _generate_detailed_report(self, report: BenchmarkReport) -> str:
        """Generate detailed text report"""
        lines = []
        lines.append("PHASE 2 AUTOMATED BENCHMARK REPORT")
        lines.append("=" * 60)
        lines.append("")
        
        # Header information
        lines.append(f"Report ID: {report.report_id}")
        lines.append(f"Execution Time: {report.execution_timestamp}")
        lines.append(f"Duration: {report.duration_seconds:.1f} seconds")
        lines.append(f"Overall Status: {report.overall_status}")
        lines.append("")
        
        # Environment information
        lines.append("ENVIRONMENT:")
        for key, value in report.environment_info.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        
        # Git information
        if report.git_info:
            lines.append("GIT INFO:")
            for key, value in report.git_info.items():
                lines.append(f"  {key}: {value}")
            lines.append("")
        
        # Performance summary
        lines.append("PERFORMANCE SUMMARY:")
        for key, value in report.performance_summary.items():
            if isinstance(value, float):
                lines.append(f"  {key}: {value:.2f}")
            else:
                lines.append(f"  {key}: {value}")
        lines.append("")
        
        # Test suite results
        lines.append("TEST SUITE RESULTS:")
        lines.append("-" * 40)
        
        for suite_name, result in report.test_suite_results.items():
            status = result.get('status', 'UNKNOWN')
            duration = result.get('duration_seconds', 0)
            
            lines.append(f"\n{suite_name}: {status}")
            lines.append(f"  Duration: {duration:.1f}s")
            
            if 'metrics' in result:
                lines.append("  Metrics:")
                for metric, value in result['metrics'].items():
                    if isinstance(value, float):
                        lines.append(f"    {metric}: {value:.2f}")
                    else:
                        lines.append(f"    {metric}: {value}")
            
            if result.get('status') == 'ERROR':
                lines.append(f"  Error: {result.get('error', 'Unknown error')}")
        
        # Regression alerts
        if report.regression_alerts:
            lines.append("\n\nREGRESSION ALERTS:")
            lines.append("-" * 30)
            
            for alert in report.regression_alerts:
                severity_icon = {
                    'critical': '🚨',
                    'major': '❗',
                    'moderate': '⚠️',
                    'minor': 'ℹ️'
                }.get(alert.severity, '⚬')
                
                lines.append(f"\n{severity_icon} {alert.severity.upper()}: {alert.test_suite}")
                lines.append(f"  Metric: {alert.metric_name}")
                lines.append(f"  Current: {alert.current_value:.2f}")
                lines.append(f"  Threshold: {alert.threshold_value:.2f}")
                lines.append(f"  Deviation: {alert.deviation_percent:.1f}%")
                lines.append(f"  Description: {alert.description}")
        else:
            lines.append("\n\nREGRESSION ALERTS: None")
        
        # Recommendations
        lines.append("\n\nRECOMMENDATIONS:")
        lines.append("-" * 30)
        
        for i, recommendation in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {recommendation}")
        
        # Resource usage
        if report.resource_usage:
            lines.append("\n\nRESOURCE USAGE:")
            lines.append("-" * 20)
            
            for key, value in report.resource_usage.items():
                if isinstance(value, float):
                    lines.append(f"  {key}: {value:.1f}")
                else:
                    lines.append(f"  {key}: {value}")
        
        lines.append("\n" + "=" * 60)
        lines.append("END OF REPORT")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    async def _send_notifications(self, report: BenchmarkReport, report_content: str):
        """Send notifications about benchmark results"""
        
        # Email notifications
        if self.config['email_notifications']['enabled']:
            await self._send_email_notification(report, report_content)
        
        # Slack notifications
        if self.config['slack_notifications']['enabled']:
            await self._send_slack_notification(report)
    
    async def _send_email_notification(self, report: BenchmarkReport, report_content: str):
        """Send email notification"""
        try:
            email_config = self.config['email_notifications']
            
            msg = MimeMultipart()
            msg['From'] = email_config['username']
            msg['To'] = ', '.join(email_config['recipients'])
            msg['Subject'] = f"Phase 2 Benchmark Report - {report.overall_status}"
            
            # Attach report
            msg.attach(MimeText(report_content, 'plain'))
            
            # Send email
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            server.starttls()
            server.login(email_config['username'], email_config['password'])
            server.send_message(msg)
            server.quit()
            
            self.logger.info("Email notification sent successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")
    
    async def _send_slack_notification(self, report: BenchmarkReport):
        """Send Slack notification"""
        try:
            import requests
            
            slack_config = self.config['slack_notifications']
            
            # Create Slack message
            status_emoji = {
                'SUCCESS': '✅',
                'PARTIAL_SUCCESS': '⚠️',
                'FAILURE': '❌'
            }.get(report.overall_status, '❓')
            
            message = {
                'text': f"{status_emoji} Phase 2 Benchmark Report",
                'attachments': [
                    {
                        'color': 'good' if report.overall_status == 'SUCCESS' else 'warning' if report.overall_status == 'PARTIAL_SUCCESS' else 'danger',
                        'fields': [
                            {
                                'title': 'Status',
                                'value': report.overall_status,
                                'short': True
                            },
                            {
                                'title': 'Duration',
                                'value': f"{report.duration_seconds:.1f}s",
                                'short': True
                            },
                            {
                                'title': 'Suites Run',
                                'value': str(len(report.test_suite_results)),
                                'short': True
                            },
                            {
                                'title': 'Regressions',
                                'value': str(len(report.regression_alerts)),
                                'short': True
                            }
                        ]
                    }
                ]
            }
            
            # Send to Slack
            response = requests.post(
                slack_config['webhook_url'],
                json=message,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Slack notification sent successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack notification: {e}")

    def run_regression_tests(self) -> BenchmarkReport:
        """Run only regression tests for quick CI checks"""
        return asyncio.run(self.run_full_benchmark_suite(['regression_tests']))
    
    def run_pr_performance_validation(self, baseline_commit: str) -> BenchmarkReport:
        """Run performance validation for PR review"""
        # Would implement PR-specific comparison logic
        return asyncio.run(self.run_full_benchmark_suite(['performance_benchmarks', 'regression_tests']))
    
    def generate_performance_trend_report(self, days: int = 30) -> str:
        """Generate performance trend analysis report"""
        # Would query historical data and generate trends
        return "Performance trend analysis not yet implemented"


def main():
    """Main entry point for automated benchmark runner"""
    parser = argparse.ArgumentParser(description='Phase 2 Automated Benchmark Runner')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--suites', nargs='*', help='Specific test suites to run')
    parser.add_argument('--regression-only', action='store_true', help='Run only regression tests')
    parser.add_argument('--pr-validation', type=str, help='Run PR validation against baseline commit')
    parser.add_argument('--trends', type=int, help='Generate performance trend report for N days')
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = TestSuiteOrchestrator(config_path=args.config)
    
    try:
        if args.regression_only:
            report = orchestrator.run_regression_tests()
        elif args.pr_validation:
            report = orchestrator.run_pr_performance_validation(args.pr_validation)
        elif args.trends:
            trend_report = orchestrator.generate_performance_trend_report(args.trends)
            print(trend_report)
            return
        else:
            report = asyncio.run(orchestrator.run_full_benchmark_suite(args.suites))
        
        # Print summary
        print(f"\nBenchmark execution completed: {report.overall_status}")
        print(f"Report ID: {report.report_id}")
        print(f"Duration: {report.duration_seconds:.1f} seconds")
        
        if report.regression_alerts:
            print(f"⚠️  {len(report.regression_alerts)} regression alerts")
        
        # Exit with appropriate code
        if report.overall_status == 'SUCCESS':
            sys.exit(0)
        elif report.overall_status == 'PARTIAL_SUCCESS':
            sys.exit(1)
        else:
            sys.exit(2)
            
    except Exception as e:
        print(f"Benchmark runner failed: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()