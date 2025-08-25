#!/usr/bin/env python3
"""
Comprehensive admin system testing script
Executes all admin tests and generates detailed reports
"""
import asyncio
import subprocess
import sys
import time
import json
import os
from pathlib import Path
from typing import Dict, List, Any
import logging


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('admin_test_results.log')
    ]
)
logger = logging.getLogger(__name__)


class AdminTestRunner:
    """Comprehensive admin test runner and reporter"""
    
    def __init__(self):
        self.backend_path = Path(__file__).parent.parent
        self.test_results = {
            'start_time': None,
            'end_time': None,
            'duration': None,
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'skipped_tests': 0,
            'test_suites': {},
            'performance_metrics': {},
            'coverage_report': None,
            'issues_found': [],
            'recommendations': []
        }
    
    def run_comprehensive_tests(self):
        """Run all admin tests and generate comprehensive report"""
        logger.info("Starting comprehensive admin system testing...")
        self.test_results['start_time'] = time.time()
        
        try:
            # 1. Environment setup and validation
            self._validate_test_environment()
            
            # 2. Run unit tests
            self._run_unit_tests()
            
            # 3. Run integration tests
            self._run_integration_tests()
            
            # 4. Run performance tests
            self._run_performance_tests()
            
            # 5. Run security tests
            self._run_security_tests()
            
            # 6. Generate coverage report
            self._generate_coverage_report()
            
            # 7. Analyze results and generate recommendations
            self._analyze_results()
            
            # 8. Generate final report
            self._generate_final_report()
            
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            self.test_results['issues_found'].append({
                'type': 'execution_error',
                'message': str(e),
                'severity': 'critical'
            })
        finally:
            self.test_results['end_time'] = time.time()
            self.test_results['duration'] = self.test_results['end_time'] - self.test_results['start_time']
            logger.info(f"Testing completed in {self.test_results['duration']:.2f} seconds")
    
    def _validate_test_environment(self):
        """Validate test environment setup"""
        logger.info("Validating test environment...")
        
        # Check if required files exist
        required_files = [
            'tests/test_admin_comprehensive.py',
            'tests/test_admin_performance.py',
            'tests/fixtures/admin_fixtures.py',
            'tests/conftest.py'
        ]
        
        for file_path in required_files:
            full_path = self.backend_path / file_path
            if not full_path.exists():
                raise FileNotFoundError(f"Required test file not found: {file_path}")
        
        # Check if test database can be created
        test_db_path = self.backend_path / "test.db"
        if test_db_path.exists():
            test_db_path.unlink()  # Remove existing test db
        
        logger.info("Test environment validation passed")
    
    def _run_unit_tests(self):
        """Run unit tests"""
        logger.info("Running admin unit tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_admin_comprehensive.py::TestUserManagement",
            "tests/test_admin_comprehensive.py::TestSessionManagement",
            "tests/test_admin_comprehensive.py::TestAuditLogging",
            "-v", "--tb=short",
            "--json-report", "--json-report-file=unit_test_report.json"
        ]
        
        result = self._run_pytest_command(cmd, "unit_tests")
        self.test_results['test_suites']['unit_tests'] = result
    
    def _run_integration_tests(self):
        """Run integration tests"""
        logger.info("Running admin integration tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_admin_comprehensive.py::TestIntegrationScenarios",
            "tests/test_admin_comprehensive.py::TestSystemMonitoring",
            "tests/test_admin_comprehensive.py::TestConfiguration",
            "-v", "--tb=short",
            "--json-report", "--json-report-file=integration_test_report.json"
        ]
        
        result = self._run_pytest_command(cmd, "integration_tests")
        self.test_results['test_suites']['integration_tests'] = result
    
    def _run_performance_tests(self):
        """Run performance tests"""
        logger.info("Running admin performance tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_admin_performance.py",
            "-v", "--tb=short", "-m", "slow",
            "--json-report", "--json-report-file=performance_test_report.json"
        ]
        
        result = self._run_pytest_command(cmd, "performance_tests")
        self.test_results['test_suites']['performance_tests'] = result
        
        # Extract performance metrics if available
        self._extract_performance_metrics()
    
    def _run_security_tests(self):
        """Run security-related tests"""
        logger.info("Running admin security tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/test_admin_comprehensive.py::TestSecurityAndValidation",
            "tests/test_admin_comprehensive.py::TestErrorHandling",
            "-v", "--tb=short",
            "--json-report", "--json-report-file=security_test_report.json"
        ]
        
        result = self._run_pytest_command(cmd, "security_tests")
        self.test_results['test_suites']['security_tests'] = result
    
    def _generate_coverage_report(self):
        """Generate test coverage report"""
        logger.info("Generating coverage report...")
        
        try:
            cmd = [
                sys.executable, "-m", "pytest",
                "tests/test_admin_comprehensive.py",
                "--cov=app.api.v1.endpoints.admin_api",
                "--cov=app.core.admin_auth",
                "--cov=app.schemas.admin_schemas",
                "--cov-report=html:htmlcov_admin",
                "--cov-report=json:coverage_admin.json",
                "--cov-report=term"
            ]
            
            result = subprocess.run(
                cmd, 
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # Load coverage data if available
            coverage_file = self.backend_path / "coverage_admin.json"
            if coverage_file.exists():
                with open(coverage_file, 'r') as f:
                    self.test_results['coverage_report'] = json.load(f)
            
            logger.info("Coverage report generated successfully")
            
        except Exception as e:
            logger.warning(f"Coverage generation failed: {e}")
    
    def _run_pytest_command(self, cmd: List[str], test_type: str) -> Dict[str, Any]:
        """Run a pytest command and return results"""
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd, 
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            end_time = time.time()
            
            # Parse JSON report if available
            json_report_file = self.backend_path / f"{test_type.replace('_tests', '_test_report.json')}"
            test_data = None
            if json_report_file.exists():
                try:
                    with open(json_report_file, 'r') as f:
                        test_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to parse JSON report for {test_type}: {e}")
            
            return {
                'return_code': result.returncode,
                'duration': end_time - start_time,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0,
                'test_data': test_data
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"{test_type} timed out after 10 minutes")
            return {
                'return_code': -1,
                'duration': 600,
                'stdout': '',
                'stderr': 'Test timed out',
                'success': False,
                'test_data': None
            }
        except Exception as e:
            logger.error(f"Failed to run {test_type}: {e}")
            return {
                'return_code': -1,
                'duration': 0,
                'stdout': '',
                'stderr': str(e),
                'success': False,
                'test_data': None
            }
    
    def _extract_performance_metrics(self):
        """Extract performance metrics from test output"""
        perf_suite = self.test_results['test_suites'].get('performance_tests', {})
        
        if perf_suite.get('success') and perf_suite.get('stdout'):
            stdout = perf_suite['stdout']
            
            # Extract timing information from output
            metrics = {}
            
            # Look for performance timing outputs
            for line in stdout.split('\n'):
                if 'Page size' in line and ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        timing = parts[1].strip()
                        if 's,' in timing:
                            time_str = timing.split('s,')[0]
                            try:
                                metrics[f"page_size_{line.split()[2]}"] = float(time_str)
                            except (ValueError, IndexError):
                                pass
                
                elif 'Search' in line and ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        timing = parts[1].strip()
                        if 's' in timing:
                            time_str = timing.replace('s', '')
                            try:
                                search_term = line.split("'")[1]
                                metrics[f"search_{search_term}"] = float(time_str)
                            except (ValueError, IndexError):
                                pass
            
            self.test_results['performance_metrics'] = metrics
    
    def _analyze_results(self):
        """Analyze test results and generate recommendations"""
        logger.info("Analyzing test results...")
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        skipped_tests = 0
        
        for suite_name, suite_data in self.test_results['test_suites'].items():
            if suite_data.get('test_data') and 'summary' in suite_data['test_data']:
                summary = suite_data['test_data']['summary']
                total_tests += summary.get('total', 0)
                passed_tests += summary.get('passed', 0)
                failed_tests += summary.get('failed', 0)
                skipped_tests += summary.get('skipped', 0)
            
            # Check for failures
            if not suite_data.get('success', False):
                self.test_results['issues_found'].append({
                    'type': 'test_failure',
                    'suite': suite_name,
                    'message': f"{suite_name} failed",
                    'severity': 'high' if 'security' in suite_name else 'medium'
                })
        
        self.test_results['total_tests'] = total_tests
        self.test_results['passed_tests'] = passed_tests
        self.test_results['failed_tests'] = failed_tests
        self.test_results['skipped_tests'] = skipped_tests
        
        # Generate recommendations
        self._generate_recommendations()
    
    def _generate_recommendations(self):
        """Generate recommendations based on test results"""
        recommendations = []
        
        # Check test coverage
        if self.test_results.get('coverage_report'):
            coverage = self.test_results['coverage_report']
            if 'totals' in coverage:
                percent_covered = coverage['totals'].get('percent_covered', 0)
                if percent_covered < 80:
                    recommendations.append({
                        'type': 'coverage',
                        'message': f"Test coverage is {percent_covered:.1f}%, below recommended 80%",
                        'action': "Add more unit tests to increase coverage",
                        'priority': 'high'
                    })
        
        # Check performance metrics
        perf_metrics = self.test_results.get('performance_metrics', {})
        for metric_name, value in perf_metrics.items():
            if value > 3.0:  # Response time > 3 seconds
                recommendations.append({
                    'type': 'performance',
                    'message': f"{metric_name} response time is {value:.2f}s",
                    'action': "Investigate and optimize slow operations",
                    'priority': 'medium'
                })
        
        # Check for failed tests
        if self.test_results['failed_tests'] > 0:
            recommendations.append({
                'type': 'reliability',
                'message': f"{self.test_results['failed_tests']} tests failed",
                'action': "Fix failing tests before deployment",
                'priority': 'critical'
            })
        
        # Check test suite completeness
        expected_suites = ['unit_tests', 'integration_tests', 'security_tests']
        missing_suites = [s for s in expected_suites if s not in self.test_results['test_suites']]
        if missing_suites:
            recommendations.append({
                'type': 'completeness',
                'message': f"Missing test suites: {', '.join(missing_suites)}",
                'action': "Implement missing test categories",
                'priority': 'medium'
            })
        
        self.test_results['recommendations'] = recommendations
    
    def _generate_final_report(self):
        """Generate final comprehensive report"""
        logger.info("Generating final test report...")
        
        # Generate markdown report
        report_content = self._generate_markdown_report()
        
        report_file = self.backend_path / "ADMIN_TEST_REPORT.md"
        with open(report_file, 'w') as f:
            f.write(report_content)
        
        # Generate JSON report
        json_report_file = self.backend_path / "admin_test_results.json"
        with open(json_report_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        
        # Print summary to console
        self._print_summary()
        
        logger.info(f"Reports generated: {report_file} and {json_report_file}")
    
    def _generate_markdown_report(self) -> str:
        """Generate markdown test report"""
        duration = self.test_results.get('duration', 0)
        
        report = f"""# Admin System Test Report

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {duration:.2f} seconds

## Summary

- **Total Tests**: {self.test_results['total_tests']}
- **Passed**: {self.test_results['passed_tests']} ✅
- **Failed**: {self.test_results['failed_tests']} ❌
- **Skipped**: {self.test_results['skipped_tests']} ⏭️
- **Success Rate**: {(self.test_results['passed_tests'] / max(self.test_results['total_tests'], 1)) * 100:.1f}%

## Test Suites

"""
        
        for suite_name, suite_data in self.test_results['test_suites'].items():
            status = "✅ PASSED" if suite_data.get('success') else "❌ FAILED"
            duration = suite_data.get('duration', 0)
            
            report += f"""### {suite_name.replace('_', ' ').title()}

- **Status**: {status}
- **Duration**: {duration:.2f}s

"""
        
        # Coverage section
        if self.test_results.get('coverage_report'):
            coverage = self.test_results['coverage_report']
            if 'totals' in coverage:
                percent = coverage['totals'].get('percent_covered', 0)
                report += f"""## Test Coverage

- **Overall Coverage**: {percent:.1f}%
- **Lines Covered**: {coverage['totals'].get('covered_lines', 0)}
- **Total Lines**: {coverage['totals'].get('num_statements', 0)}

"""
        
        # Performance metrics
        if self.test_results.get('performance_metrics'):
            report += "## Performance Metrics\n\n"
            for metric, value in self.test_results['performance_metrics'].items():
                report += f"- **{metric}**: {value:.3f}s\n"
            report += "\n"
        
        # Issues found
        if self.test_results.get('issues_found'):
            report += "## Issues Found\n\n"
            for issue in self.test_results['issues_found']:
                severity = issue.get('severity', 'medium').upper()
                report += f"- **[{severity}]** {issue['message']}\n"
            report += "\n"
        
        # Recommendations
        if self.test_results.get('recommendations'):
            report += "## Recommendations\n\n"
            for rec in self.test_results['recommendations']:
                priority = rec.get('priority', 'medium').upper()
                report += f"### [{priority}] {rec['message']}\n\n"
                report += f"**Action**: {rec['action']}\n\n"
        
        return report
    
    def _print_summary(self):
        """Print test summary to console"""
        print("\n" + "="*60)
        print("ADMIN SYSTEM TEST SUMMARY")
        print("="*60)
        print(f"Duration: {self.test_results['duration']:.2f} seconds")
        print(f"Total Tests: {self.test_results['total_tests']}")
        print(f"Passed: {self.test_results['passed_tests']} ✅")
        print(f"Failed: {self.test_results['failed_tests']} ❌")
        print(f"Skipped: {self.test_results['skipped_tests']} ⏭️")
        
        if self.test_results['total_tests'] > 0:
            success_rate = (self.test_results['passed_tests'] / self.test_results['total_tests']) * 100
            print(f"Success Rate: {success_rate:.1f}%")
        
        if self.test_results.get('coverage_report') and 'totals' in self.test_results['coverage_report']:
            coverage = self.test_results['coverage_report']['totals']['percent_covered']
            print(f"Test Coverage: {coverage:.1f}%")
        
        print("\nTest Suites:")
        for suite_name, suite_data in self.test_results['test_suites'].items():
            status = "PASSED" if suite_data.get('success') else "FAILED"
            print(f"  - {suite_name}: {status}")
        
        if self.test_results.get('issues_found'):
            print(f"\nIssues Found: {len(self.test_results['issues_found'])}")
            for issue in self.test_results['issues_found']:
                print(f"  - [{issue.get('severity', 'medium').upper()}] {issue['message']}")
        
        print("="*60)


def main():
    """Main execution function"""
    runner = AdminTestRunner()
    runner.run_comprehensive_tests()


if __name__ == "__main__":
    main()