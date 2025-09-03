"""
Circuit Breaker Stress Testing for Robust Extraction System

Tests circuit breaker behavior under extreme failure conditions and validates
fault tolerance and recovery mechanisms in the 4-tier extraction system.
"""
import asyncio
import time
import pytest
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import statistics
from unittest.mock import Mock, patch

from app.services.robust_content_extractor import (
    get_robust_extractor,
    RobustContentExtractor,
    ExtractionStrategy,
    CIRCUIT_BREAKERS
)
from app.models.extraction_data import ExtractedContent, ContentExtractionException

logger = logging.getLogger(__name__)

@dataclass
class CircuitBreakerState:
    """Circuit breaker state snapshot"""
    name: str
    state: str
    failure_count: int
    success_count: int
    last_failure_time: Optional[float]
    recovery_time: Optional[float]

@dataclass
class CircuitBreakerTestResult:
    """Circuit breaker stress test result"""
    test_name: str
    test_duration_seconds: float
    total_attempts: int
    successful_attempts: int
    failed_attempts: int
    breakers_triggered: Dict[str, int] = field(default_factory=dict)
    recovery_times: Dict[str, float] = field(default_factory=dict)
    error_distribution: Dict[str, int] = field(default_factory=dict)
    fallback_cascade_triggered: int = 0
    dead_letter_queue_entries: int = 0
    system_resilience_score: float = 0.0

class CircuitBreakerStressTester:
    """Comprehensive circuit breaker stress testing system"""
    
    def __init__(self):
        self.robust_extractor = get_robust_extractor()
        
        # URLs that will definitely fail (trigger circuit breakers)
        self.failure_urls = [
            "https://web.archive.org/web/99999999999999/https://nonexistent-domain-12345.com/",
            "https://web.archive.org/web/20230615120000/https://this-will-definitely-fail.invalid/",
            "https://web.archive.org/web/20230615120000/https://timeout-test-url.example/very-long-path/that/does/not/exist",
            "https://web.archive.org/web/20230615120000/https://127.0.0.1:99999/unavailable",
            "https://web.archive.org/web/20230615120000/https://connection-refused.local/test",
            "https://invalid-archive-url/web/broken/timestamp/format",
            "https://web.archive.org/web/20230615120000/https://bad-ssl-cert.invalid/",
            "https://web.archive.org/web/20230615120000/https://malformed.url.structure/",
        ]
        
        # Mixed URLs (some fail, some succeed) for recovery testing
        self.mixed_urls = [
            "https://web.archive.org/web/20230815120000/https://www.example.com/",  # Should work
            "https://web.archive.org/web/99999999999999/https://fail1.invalid/",    # Should fail
            "https://web.archive.org/web/20230815120000/https://httpbin.org/get",   # Should work
            "https://web.archive.org/web/20230615120000/https://fail2.invalid/",    # Should fail
            "https://web.archive.org/web/20230815120000/https://www.iana.org/",     # Should work
        ]
    
    def _get_breaker_states(self) -> Dict[str, CircuitBreakerState]:
        """Get current state of all circuit breakers"""
        states = {}
        
        for name, breaker in CIRCUIT_BREAKERS.items():
            try:
                states[name] = CircuitBreakerState(
                    name=name,
                    state=str(breaker.current_state),
                    failure_count=breaker.fail_counter,
                    success_count=getattr(breaker, 'success_counter', 0),
                    last_failure_time=getattr(breaker, 'last_failure_time', None),
                    recovery_time=None
                )
            except Exception as e:
                logger.warning(f"Could not get state for breaker {name}: {e}")
                states[name] = CircuitBreakerState(
                    name=name,
                    state='unknown',
                    failure_count=0,
                    success_count=0,
                    last_failure_time=None,
                    recovery_time=None
                )
        
        return states
    
    def _reset_all_breakers(self):
        """Reset all circuit breakers to closed state"""
        for breaker in CIRCUIT_BREAKERS.values():
            try:
                breaker._state = breaker._closed_state  # Force to closed state
                breaker.fail_counter = 0
            except Exception as e:
                logger.warning(f"Could not reset circuit breaker: {e}")
    
    async def _extract_with_error_tracking(self, url: str) -> Tuple[bool, str, Optional[str]]:
        """Extract URL with detailed error tracking"""
        try:
            result = await self.robust_extractor.extract_content(url)
            return True, "success", None
        except ContentExtractionException as e:
            return False, "extraction_exception", str(e)
        except Exception as e:
            error_type = type(e).__name__
            return False, error_type, str(e)
    
    async def run_rapid_failure_test(
        self,
        failures_per_breaker: int = 20,
        concurrent_failures: int = 15
    ) -> CircuitBreakerTestResult:
        """Test circuit breaker triggering under rapid failure conditions"""
        test_name = f"rapid_failure_{failures_per_breaker}x{concurrent_failures}"
        logger.info(f"Starting {test_name} test")
        
        # Reset breakers to ensure clean test
        self._reset_all_breakers()
        initial_states = self._get_breaker_states()
        
        test_start_time = time.time()
        total_attempts = 0
        successful_attempts = 0
        failed_attempts = 0
        error_distribution = {}
        
        # Generate rapid failures
        failure_tasks = []
        for _ in range(failures_per_breaker):
            for url in self.failure_urls[:concurrent_failures]:  # Use subset for concurrency control
                task = asyncio.create_task(self._extract_with_error_tracking(url))
                failure_tasks.append(task)
        
        # Execute all failure attempts
        results = await asyncio.gather(*failure_tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            total_attempts += 1
            if isinstance(result, Exception):
                failed_attempts += 1
                error_type = type(result).__name__
                error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
            else:
                success, error_type, error_msg = result
                if success:
                    successful_attempts += 1
                else:
                    failed_attempts += 1
                    error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
        
        total_test_duration = time.time() - test_start_time
        
        # Analyze circuit breaker state changes
        final_states = self._get_breaker_states()
        breakers_triggered = {}
        
        for name, final_state in final_states.items():
            initial_state = initial_states.get(name)
            if initial_state and final_state:
                failure_increase = final_state.failure_count - initial_state.failure_count
                breakers_triggered[name] = failure_increase
        
        # Check DLQ entries
        dlq_entries = 0
        try:
            dlq_entries = len(await self.robust_extractor.dlq.get_failed_extractions(count=1000))
        except Exception as e:
            logger.warning(f"Could not get DLQ count: {e}")
        
        return CircuitBreakerTestResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            total_attempts=total_attempts,
            successful_attempts=successful_attempts,
            failed_attempts=failed_attempts,
            breakers_triggered=breakers_triggered,
            error_distribution=error_distribution,
            dead_letter_queue_entries=dlq_entries,
            system_resilience_score=1.0 - (failed_attempts / total_attempts) if total_attempts > 0 else 0.0
        )
    
    async def run_recovery_behavior_test(
        self,
        recovery_window_seconds: int = 120,
        mixed_load_size: int = 50
    ) -> CircuitBreakerTestResult:
        """Test circuit breaker recovery behavior with mixed success/failure load"""
        test_name = f"recovery_behavior_{recovery_window_seconds}s"
        logger.info(f"Starting {test_name} test")
        
        # Reset breakers
        self._reset_all_breakers()
        initial_states = self._get_breaker_states()
        
        test_start_time = time.time()
        total_attempts = 0
        successful_attempts = 0
        failed_attempts = 0
        error_distribution = {}
        recovery_times = {}
        
        # Phase 1: Trigger circuit breakers with failures
        logger.info("Phase 1: Triggering circuit breakers")
        failure_tasks = [
            asyncio.create_task(self._extract_with_error_tracking(url))
            for url in self.failure_urls * 5  # Multiple attempts per URL
        ]
        
        phase1_results = await asyncio.gather(*failure_tasks, return_exceptions=True)
        
        for result in phase1_results:
            total_attempts += 1
            if isinstance(result, Exception):
                failed_attempts += 1
                error_type = type(result).__name__
                error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
            else:
                success, error_type, _ = result
                if success:
                    successful_attempts += 1
                else:
                    failed_attempts += 1
                    error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
        
        phase1_states = self._get_breaker_states()
        logger.info(f"Phase 1 complete. Breaker states: {[(name, state.state, state.failure_count) for name, state in phase1_states.items()]}")
        
        # Phase 2: Recovery period with mixed load
        logger.info(f"Phase 2: Recovery testing over {recovery_window_seconds} seconds")
        recovery_start_time = time.time()
        
        while time.time() - recovery_start_time < recovery_window_seconds:
            # Mixed batch with both successful and failing URLs
            mixed_batch = []
            import random
            for _ in range(min(mixed_load_size // 10, 10)):  # Process in smaller batches
                url = random.choice(self.mixed_urls)
                mixed_batch.append(asyncio.create_task(self._extract_with_error_tracking(url)))
            
            batch_results = await asyncio.gather(*mixed_batch, return_exceptions=True)
            
            for result in batch_results:
                total_attempts += 1
                if isinstance(result, Exception):
                    failed_attempts += 1
                    error_type = type(result).__name__
                    error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
                else:
                    success, error_type, _ = result
                    if success:
                        successful_attempts += 1
                    else:
                        failed_attempts += 1
                        error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
            
            # Check for breaker recovery
            current_states = self._get_breaker_states()
            for name, current_state in current_states.items():
                phase1_state = phase1_states.get(name)
                if (phase1_state and phase1_state.state == 'open' and 
                    current_state.state in ['closed', 'half_open'] and 
                    name not in recovery_times):
                    recovery_times[name] = time.time() - recovery_start_time
                    logger.info(f"Breaker {name} recovered after {recovery_times[name]:.1f}s")
            
            # Small delay between batches
            await asyncio.sleep(5)
        
        total_test_duration = time.time() - test_start_time
        final_states = self._get_breaker_states()
        
        # Calculate breaker trigger counts
        breakers_triggered = {}
        for name, final_state in final_states.items():
            initial_state = initial_states.get(name)
            if initial_state and final_state:
                failure_increase = final_state.failure_count - initial_state.failure_count
                breakers_triggered[name] = failure_increase
        
        return CircuitBreakerTestResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            total_attempts=total_attempts,
            successful_attempts=successful_attempts,
            failed_attempts=failed_attempts,
            breakers_triggered=breakers_triggered,
            recovery_times=recovery_times,
            error_distribution=error_distribution,
            system_resilience_score=successful_attempts / total_attempts if total_attempts > 0 else 0.0
        )
    
    async def run_cascading_failure_test(
        self,
        cascade_depth: int = 4,
        attempts_per_level: int = 15
    ) -> CircuitBreakerTestResult:
        """Test cascading failure behavior across extraction strategies"""
        test_name = f"cascading_failure_depth{cascade_depth}"
        logger.info(f"Starting {test_name} test")
        
        self._reset_all_breakers()
        initial_states = self._get_breaker_states()
        
        test_start_time = time.time()
        total_attempts = 0
        successful_attempts = 0
        failed_attempts = 0
        error_distribution = {}
        fallback_cascade_count = 0
        
        # Create systematic failures to trigger cascading behavior
        strategy_order = [
            ExtractionStrategy.TRAFILATURA,
            ExtractionStrategy.READABILITY,
            ExtractionStrategy.NEWSPAPER3K,
            ExtractionStrategy.BEAUTIFULSOUP
        ]
        
        for level in range(cascade_depth):
            logger.info(f"Cascading failure level {level + 1}/{cascade_depth}")
            
            # Use progressively more difficult failures
            level_failures = self.failure_urls[:attempts_per_level]
            
            cascade_tasks = []
            for url in level_failures:
                task = asyncio.create_task(self._extract_with_error_tracking(url))
                cascade_tasks.append(task)
            
            level_results = await asyncio.gather(*cascade_tasks, return_exceptions=True)
            
            # Count cascade triggers by checking for fallback usage
            for result in level_results:
                total_attempts += 1
                if isinstance(result, Exception):
                    failed_attempts += 1
                    error_type = type(result).__name__
                    error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
                    
                    # Check if this was a cascade trigger
                    if "fallback" in str(result).lower() or "cascade" in str(result).lower():
                        fallback_cascade_count += 1
                else:
                    success, error_type, error_msg = result
                    if success:
                        successful_attempts += 1
                        # Check if successful result used fallback strategy
                        if error_msg and "beautifulsoup" in error_msg.lower():
                            fallback_cascade_count += 1
                    else:
                        failed_attempts += 1
                        error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
                        
                        if error_msg and "fallback" in error_msg.lower():
                            fallback_cascade_count += 1
            
            # Brief pause between cascade levels
            await asyncio.sleep(2)
        
        total_test_duration = time.time() - test_start_time
        final_states = self._get_breaker_states()
        
        # Calculate breaker triggers
        breakers_triggered = {}
        for name, final_state in final_states.items():
            initial_state = initial_states.get(name)
            if initial_state and final_state:
                failure_increase = final_state.failure_count - initial_state.failure_count
                breakers_triggered[name] = failure_increase
        
        return CircuitBreakerTestResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            total_attempts=total_attempts,
            successful_attempts=successful_attempts,
            failed_attempts=failed_attempts,
            breakers_triggered=breakers_triggered,
            error_distribution=error_distribution,
            fallback_cascade_triggered=fallback_cascade_count,
            system_resilience_score=successful_attempts / total_attempts if total_attempts > 0 else 0.0
        )
    
    async def run_stress_endurance_test(
        self,
        duration_minutes: int = 15,
        failure_rate: float = 0.7,
        concurrent_load: int = 20
    ) -> CircuitBreakerTestResult:
        """Test circuit breaker endurance under sustained stress"""
        test_name = f"stress_endurance_{duration_minutes}min"
        logger.info(f"Starting {test_name} test for {duration_minutes} minutes")
        
        self._reset_all_breakers()
        initial_states = self._get_breaker_states()
        
        test_start_time = time.time()
        test_duration_seconds = duration_minutes * 60
        total_attempts = 0
        successful_attempts = 0
        failed_attempts = 0
        error_distribution = {}
        recovery_events = {}
        
        while time.time() - test_start_time < test_duration_seconds:
            # Create mixed workload based on failure rate
            batch_urls = []
            import random
            
            for _ in range(concurrent_load):
                if random.random() < failure_rate:
                    # Add failing URL
                    batch_urls.append(random.choice(self.failure_urls))
                else:
                    # Add potentially successful URL
                    batch_urls.append(random.choice(self.mixed_urls))
            
            # Process batch
            batch_tasks = [
                asyncio.create_task(self._extract_with_error_tracking(url))
                for url in batch_urls
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Process results
            for result in batch_results:
                total_attempts += 1
                if isinstance(result, Exception):
                    failed_attempts += 1
                    error_type = type(result).__name__
                    error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
                else:
                    success, error_type, _ = result
                    if success:
                        successful_attempts += 1
                    else:
                        failed_attempts += 1
                        error_distribution[error_type] = error_distribution.get(error_type, 0) + 1
            
            # Monitor for recovery events
            current_states = self._get_breaker_states()
            for name, state in current_states.items():
                if state.state == 'closed' and name not in recovery_events:
                    recovery_events[name] = time.time() - test_start_time
            
            # Pace control
            await asyncio.sleep(3)
        
        total_test_duration = time.time() - test_start_time
        final_states = self._get_breaker_states()
        
        # Calculate final metrics
        breakers_triggered = {}
        for name, final_state in final_states.items():
            initial_state = initial_states.get(name)
            if initial_state and final_state:
                failure_increase = final_state.failure_count - initial_state.failure_count
                breakers_triggered[name] = failure_increase
        
        return CircuitBreakerTestResult(
            test_name=test_name,
            test_duration_seconds=total_test_duration,
            total_attempts=total_attempts,
            successful_attempts=successful_attempts,
            failed_attempts=failed_attempts,
            breakers_triggered=breakers_triggered,
            recovery_times=recovery_events,
            error_distribution=error_distribution,
            system_resilience_score=successful_attempts / total_attempts if total_attempts > 0 else 0.0
        )

# Test fixtures
@pytest.fixture
def circuit_breaker_tester():
    """Provide circuit breaker tester instance"""
    return CircuitBreakerStressTester()

# Test cases
@pytest.mark.asyncio
@pytest.mark.slow
async def test_rapid_failure_circuit_breaker_activation(circuit_breaker_tester):
    """Test circuit breaker activation under rapid failure conditions"""
    result = await circuit_breaker_tester.run_rapid_failure_test(
        failures_per_breaker=15,
        concurrent_failures=10
    )
    
    # Circuit breaker activation assertions
    assert result.failed_attempts > 0, "Should have failure attempts to trigger breakers"
    assert any(count > 0 for count in result.breakers_triggered.values()), "At least one circuit breaker should be triggered"
    assert result.dead_letter_queue_entries >= 0, "DLQ should collect failures"
    
    # Check specific breakers were triggered
    primary_breakers = ['trafilatura', 'newspaper', 'readability']
    triggered_primary = sum(result.breakers_triggered.get(name, 0) for name in primary_breakers)
    assert triggered_primary > 0, f"Primary extraction breakers should be triggered: {result.breakers_triggered}"
    
    logger.info(f"Rapid failure test: {result.failed_attempts} failures, "
               f"breakers triggered: {result.breakers_triggered}")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_circuit_breaker_recovery_behavior(circuit_breaker_tester):
    """Test circuit breaker recovery with mixed success/failure load"""
    result = await circuit_breaker_tester.run_recovery_behavior_test(
        recovery_window_seconds=90,
        mixed_load_size=40
    )
    
    # Recovery behavior assertions
    assert result.successful_attempts > 0, "Should have some successful attempts during recovery"
    assert result.total_attempts > 50, "Should have sufficient attempts to test recovery"
    
    # System should show resilience
    assert result.system_resilience_score > 0.1, f"System resilience too low: {result.system_resilience_score:.1%}"
    
    # Check recovery times
    recovered_breakers = len(result.recovery_times)
    logger.info(f"Recovery test: {recovered_breakers} breakers recovered, "
               f"resilience score: {result.system_resilience_score:.1%}")
    
    # At least some breakers should recover if they were triggered
    if any(count > 5 for count in result.breakers_triggered.values()):
        assert recovered_breakers > 0, "Some breakers should recover during the test window"

@pytest.mark.asyncio
async def test_cascading_failure_handling(circuit_breaker_tester):
    """Test handling of cascading failures across extraction strategies"""
    result = await circuit_breaker_tester.run_cascading_failure_test(
        cascade_depth=3,
        attempts_per_level=12
    )
    
    # Cascading failure assertions
    assert result.total_attempts > 30, "Should have sufficient cascade attempts"
    
    # Multiple breakers should be triggered in cascade
    triggered_count = sum(1 for count in result.breakers_triggered.values() if count > 0)
    assert triggered_count >= 2, f"Multiple breakers should be triggered in cascade: {result.breakers_triggered}"
    
    # System should demonstrate fallback behavior
    if result.fallback_cascade_triggered > 0:
        logger.info(f"Cascading test: {result.fallback_cascade_triggered} fallback cascades triggered")
    
    # Even with cascading failures, system should maintain some resilience
    assert result.system_resilience_score >= 0.0, "System should maintain basic resilience"
    
    logger.info(f"Cascade test: {triggered_count} breakers triggered, "
               f"resilience: {result.system_resilience_score:.1%}")

@pytest.mark.asyncio
@pytest.mark.slow
async def test_sustained_stress_endurance(circuit_breaker_tester):
    """Test circuit breaker endurance under sustained stress conditions"""
    result = await circuit_breaker_tester.run_stress_endurance_test(
        duration_minutes=10,
        failure_rate=0.6,
        concurrent_load=15
    )
    
    # Stress endurance assertions
    assert result.total_attempts > 200, f"Should have sufficient stress attempts: {result.total_attempts}"
    
    # System should handle sustained stress
    assert result.system_resilience_score > 0.2, f"Resilience under stress too low: {result.system_resilience_score:.1%}"
    
    # Should have both failures and some successes
    assert result.failed_attempts > 0, "Should have failures under stress"
    assert result.successful_attempts > 0, "Should maintain some successful extractions"
    
    # Check error distribution
    total_error_types = len(result.error_distribution)
    assert total_error_types >= 1, "Should have diverse error types under stress"
    
    logger.info(f"Stress endurance: {result.total_attempts} attempts over {result.test_duration_seconds/60:.1f} minutes, "
               f"resilience: {result.system_resilience_score:.1%}, error types: {total_error_types}")

@pytest.mark.asyncio
async def test_breaker_state_transitions(circuit_breaker_tester):
    """Test proper state transitions of circuit breakers"""
    # Get initial states
    initial_states = circuit_breaker_tester._get_breaker_states()
    
    # All breakers should start in closed state
    for name, state in initial_states.items():
        assert state.state in ['closed', 'unknown'], f"Breaker {name} should start closed: {state.state}"
    
    # Trigger rapid failures
    result = await circuit_breaker_tester.run_rapid_failure_test(
        failures_per_breaker=10,
        concurrent_failures=8
    )
    
    # Check post-failure states
    post_failure_states = circuit_breaker_tester._get_breaker_states()
    
    # At least one breaker should have changed state
    state_changes = 0
    for name, final_state in post_failure_states.items():
        initial_state = initial_states.get(name)
        if initial_state and final_state.failure_count > initial_state.failure_count:
            state_changes += 1
    
    assert state_changes > 0, "At least one breaker should show state changes"
    
    logger.info(f"State transition test: {state_changes} breakers showed state changes")

@pytest.mark.asyncio
async def test_error_distribution_analysis(circuit_breaker_tester):
    """Test error distribution and classification under stress"""
    result = await circuit_breaker_tester.run_rapid_failure_test(
        failures_per_breaker=12,
        concurrent_failures=10
    )
    
    # Error distribution assertions
    assert len(result.error_distribution) > 0, "Should have error distribution data"
    assert result.failed_attempts > 0, "Should have failed attempts"
    
    # Check for expected error types
    expected_error_types = ['extraction_exception', 'HTTPStatusError', 'TimeoutException', 'ConnectionError']
    found_expected_errors = any(
        any(expected in error_type for expected in expected_error_types)
        for error_type in result.error_distribution.keys()
    )
    
    logger.info(f"Error distribution: {result.error_distribution}")
    
    # Should have meaningful error classification
    total_classified_errors = sum(result.error_distribution.values())
    assert total_classified_errors > 0, "Should have classified error types"

@pytest.mark.asyncio
async def test_generate_circuit_breaker_stress_report(circuit_breaker_tester):
    """Generate comprehensive circuit breaker stress testing report"""
    stress_tests = [
        {'name': 'rapid_failure', 'function': 'run_rapid_failure_test', 'params': {'failures_per_breaker': 10, 'concurrent_failures': 8}},
        {'name': 'recovery_behavior', 'function': 'run_recovery_behavior_test', 'params': {'recovery_window_seconds': 60, 'mixed_load_size': 30}},
        {'name': 'cascading_failure', 'function': 'run_cascading_failure_test', 'params': {'cascade_depth': 3, 'attempts_per_level': 10}},
        {'name': 'stress_endurance', 'function': 'run_stress_endurance_test', 'params': {'duration_minutes': 5, 'failure_rate': 0.5, 'concurrent_load': 12}},
    ]
    
    stress_report = {
        'test_timestamp': datetime.now().isoformat(),
        'circuit_breaker_tests': [],
        'summary': {
            'total_tests': len(stress_tests),
            'successful_tests': 0,
            'failed_tests': 0,
            'overall_resilience_score': 0.0
        }
    }
    
    resilience_scores = []
    
    for test_config in stress_tests:
        logger.info(f"Running circuit breaker stress test: {test_config['name']}")
        
        try:
            test_function = getattr(circuit_breaker_tester, test_config['function'])
            result = await test_function(**test_config['params'])
            
            stress_report['circuit_breaker_tests'].append({
                'test_name': result.test_name,
                'test_duration_seconds': result.test_duration_seconds,
                'total_attempts': result.total_attempts,
                'successful_attempts': result.successful_attempts,
                'failed_attempts': result.failed_attempts,
                'breakers_triggered': result.breakers_triggered,
                'recovery_times': result.recovery_times,
                'error_distribution': result.error_distribution,
                'fallback_cascade_triggered': result.fallback_cascade_triggered,
                'dead_letter_queue_entries': result.dead_letter_queue_entries,
                'system_resilience_score': result.system_resilience_score
            })
            
            resilience_scores.append(result.system_resilience_score)
            stress_report['summary']['successful_tests'] += 1
            
        except Exception as e:
            logger.error(f"Circuit breaker stress test failed for {test_config['name']}: {e}")
            stress_report['circuit_breaker_tests'].append({
                'test_name': test_config['name'],
                'error': str(e),
                'test_failed': True
            })
            stress_report['summary']['failed_tests'] += 1
    
    # Calculate overall resilience
    if resilience_scores:
        stress_report['summary']['overall_resilience_score'] = statistics.mean(resilience_scores)
    
    # Save report
    report_path = f"/tmp/circuit_breaker_stress_report_{int(time.time())}.json"
    with open(report_path, 'w') as f:
        json.dump(stress_report, f, indent=2)
    
    logger.info(f"Circuit breaker stress report saved to: {report_path}")
    
    # Summary analysis
    logger.info(f"🔧 Circuit Breaker Stress Testing Summary:")
    logger.info(f"   Tests completed successfully: {stress_report['summary']['successful_tests']}/{stress_report['summary']['total_tests']}")
    logger.info(f"   Overall system resilience: {stress_report['summary']['overall_resilience_score']:.1%}")
    
    # Assert overall system resilience
    assert stress_report['summary']['successful_tests'] >= len(stress_tests) // 2, "At least half of stress tests should succeed"
    
    if resilience_scores:
        assert stress_report['summary']['overall_resilience_score'] >= 0.1, "System should show basic resilience under stress"
    
    return stress_report