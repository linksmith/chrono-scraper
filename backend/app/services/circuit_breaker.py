"""
Circuit breaker pattern implementation for robust scraping operations
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5  # Number of failures before opening
    success_threshold: int = 3  # Successes needed to close from half-open
    timeout_seconds: int = 60   # Time to wait before trying half-open
    max_timeout_seconds: int = 300  # Maximum timeout (5 minutes)
    exponential_backoff: bool = True  # Use exponential backoff for timeout
    sliding_window_size: int = 10  # Size of sliding window for failure tracking


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    circuit_open_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    avg_response_time: float = 0.0
    
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0


class CircuitBreaker:
    """
    Circuit breaker implementation for handling service failures gracefully
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # State management
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.next_attempt_time: Optional[float] = None
        self.timeout_count = 0
        
        # Sliding window for recent failures
        self.recent_failures = deque(maxlen=self.config.sliding_window_size)
        
        # Metrics
        self.metrics = CircuitBreakerMetrics()
        
        # Response time tracking
        self.response_times = deque(maxlen=50)  # Keep last 50 response times
        
        logger.info(f"Initialized circuit breaker '{name}' with config: {self.config}")
    
    def can_execute(self) -> bool:
        """Check if execution is allowed based on current circuit state"""
        current_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
        
        elif self.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if self.next_attempt_time and current_time >= self.next_attempt_time:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                return True
            return False
        
        elif self.state == CircuitState.HALF_OPEN:
            return True
        
        return False
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenException: When circuit is open
            Original exception: When function fails
        """
        if not self.can_execute():
            self.metrics.total_requests += 1
            raise CircuitBreakerOpenException(f"Circuit breaker '{self.name}' is OPEN")
        
        start_time = time.time()
        self.metrics.total_requests += 1
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Record success
            execution_time = time.time() - start_time
            self._record_success(execution_time)
            
            return result
            
        except Exception as e:
            # Record failure
            execution_time = time.time() - start_time
            self._record_failure(e, execution_time)
            raise
    
    def _record_success(self, execution_time: float):
        """Record a successful execution"""
        current_time = time.time()
        
        self.metrics.successful_requests += 1
        self.metrics.last_success_time = datetime.fromtimestamp(current_time)
        
        # Update response time metrics
        self.response_times.append(execution_time)
        if self.response_times:
            self.metrics.avg_response_time = sum(self.response_times) / len(self.response_times)
        
        # State transition logic
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        
        elif self.state == CircuitState.CLOSED:
            # Gradually reduce failure count on success
            self.failure_count = max(0, self.failure_count - 1)
            
            # Remove old failures from sliding window
            cutoff_time = current_time - 300  # 5 minutes
            while self.recent_failures and self.recent_failures[0] < cutoff_time:
                self.recent_failures.popleft()
        
        logger.debug(f"Circuit breaker '{self.name}' recorded success "
                    f"(time: {execution_time:.2f}s, state: {self.state.value})")
    
    def _record_failure(self, exception: Exception, execution_time: float):
        """Record a failed execution"""
        current_time = time.time()
        
        self.metrics.failed_requests += 1
        self.metrics.last_failure_time = datetime.fromtimestamp(current_time)
        self.last_failure_time = current_time
        
        # Update response time metrics
        self.response_times.append(execution_time)
        if self.response_times:
            self.metrics.avg_response_time = sum(self.response_times) / len(self.response_times)
        
        # Add to sliding window
        self.recent_failures.append(current_time)
        
        # State transition logic
        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            
            # Check if we should open the circuit
            recent_failure_count = len(self.recent_failures)
            if (self.failure_count >= self.config.failure_threshold or 
                recent_failure_count >= self.config.failure_threshold):
                self._transition_to_open()
        
        elif self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state opens the circuit
            self._transition_to_open()
        
        logger.warning(f"Circuit breaker '{self.name}' recorded failure: {str(exception)} "
                      f"(time: {execution_time:.2f}s, state: {self.state.value}, "
                      f"failures: {self.failure_count})")
    
    def _transition_to_open(self):
        """Transition circuit to OPEN state"""
        self.state = CircuitState.OPEN
        self.metrics.circuit_open_count += 1
        
        # Calculate timeout with exponential backoff
        if self.config.exponential_backoff:
            timeout = min(
                self.config.timeout_seconds * (2 ** self.timeout_count),
                self.config.max_timeout_seconds
            )
            self.timeout_count += 1
        else:
            timeout = self.config.timeout_seconds
        
        self.next_attempt_time = time.time() + timeout
        
        logger.warning(f"Circuit breaker '{self.name}' OPENED "
                      f"(failures: {self.failure_count}, timeout: {timeout}s)")
    
    def _transition_to_closed(self):
        """Transition circuit to CLOSED state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.timeout_count = 0  # Reset exponential backoff
        self.recent_failures.clear()
        
        logger.info(f"Circuit breaker '{self.name}' CLOSED "
                   f"(successes: {self.config.success_threshold})")
    
    def force_open(self, reason: str = "Manual"):
        """Force circuit breaker to OPEN state"""
        self.state = CircuitState.OPEN
        self.next_attempt_time = time.time() + self.config.timeout_seconds
        logger.warning(f"Circuit breaker '{self.name}' manually OPENED: {reason}")
    
    def force_closed(self, reason: str = "Manual"):
        """Force circuit breaker to CLOSED state"""
        self._transition_to_closed()
        logger.info(f"Circuit breaker '{self.name}' manually CLOSED: {reason}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status"""
        current_time = time.time()
        
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "recent_failures": len(self.recent_failures),
            "next_attempt_time": self.next_attempt_time,
            "seconds_until_retry": max(0, self.next_attempt_time - current_time) if self.next_attempt_time else None,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds
            },
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "successful_requests": self.metrics.successful_requests,
                "failed_requests": self.metrics.failed_requests,
                "success_rate": round(self.metrics.success_rate(), 2),
                "circuit_open_count": self.metrics.circuit_open_count,
                "avg_response_time": round(self.metrics.avg_response_time, 3),
                "last_failure_time": self.metrics.last_failure_time.isoformat() if self.metrics.last_failure_time else None,
                "last_success_time": self.metrics.last_success_time.isoformat() if self.metrics.last_success_time else None
            }
        }


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers"""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        logger.info("Initialized circuit breaker registry")
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """
        Get or create a circuit breaker
        
        Args:
            name: Circuit breaker name
            config: Optional configuration (used only when creating new breaker)
            
        Returns:
            CircuitBreaker instance
        """
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)
        
        return self.breakers[name]
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers"""
        return {name: breaker.get_status() for name, breaker in self.breakers.items()}
    
    def cleanup_inactive_breakers(self, max_age_hours: int = 24):
        """Remove circuit breakers that haven't been used recently"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        inactive_breakers = []
        for name, breaker in self.breakers.items():
            last_activity = None
            
            if breaker.metrics.last_success_time:
                last_activity = breaker.metrics.last_success_time
            
            if breaker.metrics.last_failure_time:
                if last_activity is None or breaker.metrics.last_failure_time > last_activity:
                    last_activity = breaker.metrics.last_failure_time
            
            if last_activity is None or last_activity < cutoff_time:
                inactive_breakers.append(name)
        
        for name in inactive_breakers:
            del self.breakers[name]
            logger.info(f"Removed inactive circuit breaker: {name}")
        
        return len(inactive_breakers)


# Global registry instance
circuit_registry = CircuitBreakerRegistry()


# Specialized circuit breakers for different services
def get_wayback_machine_breaker() -> CircuitBreaker:
    """Get circuit breaker for Wayback Machine API"""
    config = CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=3,
        timeout_seconds=60,
        max_timeout_seconds=600,  # 10 minutes max
        exponential_backoff=True,
        sliding_window_size=10
    )
    return circuit_registry.get_breaker("wayback_machine", config)


def get_meilisearch_breaker() -> CircuitBreaker:
    """Get circuit breaker for Meilisearch"""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=30,
        max_timeout_seconds=180,  # 3 minutes max
        exponential_backoff=True,
        sliding_window_size=5
    )
    return circuit_registry.get_breaker("meilisearch", config)


def get_content_extraction_breaker() -> CircuitBreaker:
    """Get circuit breaker for content extraction"""
    config = CircuitBreakerConfig(
        failure_threshold=10,  # More tolerant of extraction failures
        success_threshold=3,
        timeout_seconds=30,
        max_timeout_seconds=300,  # 5 minutes max
        exponential_backoff=True,
        sliding_window_size=15
    )
    return circuit_registry.get_breaker("content_extraction", config)


# Decorator for easy circuit breaker usage
def with_circuit_breaker(breaker_name: str, config: Optional[CircuitBreakerConfig] = None):
    """
    Decorator to wrap functions with circuit breaker protection
    
    Args:
        breaker_name: Name of the circuit breaker
        config: Optional configuration for new breakers
        
    Returns:
        Decorated function
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            breaker = circuit_registry.get_breaker(breaker_name, config)
            return await breaker.execute(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            breaker = circuit_registry.get_breaker(breaker_name, config)
            
            # Create event loop if needed for sync execution
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(breaker.execute(func, *args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Health check function for monitoring
def get_circuit_breaker_health() -> Dict[str, Any]:
    """Get overall health status of all circuit breakers"""
    all_status = circuit_registry.get_all_status()
    
    total_breakers = len(all_status)
    open_breakers = sum(1 for status in all_status.values() if status["state"] == "open")
    half_open_breakers = sum(1 for status in all_status.values() if status["state"] == "half_open")
    
    overall_health = "healthy"
    if open_breakers > 0:
        overall_health = "degraded" if open_breakers < total_breakers else "unhealthy"
    elif half_open_breakers > 0:
        overall_health = "recovering"
    
    return {
        "overall_health": overall_health,
        "total_breakers": total_breakers,
        "open_breakers": open_breakers,
        "half_open_breakers": half_open_breakers,
        "closed_breakers": total_breakers - open_breakers - half_open_breakers,
        "breakers": all_status
    }


# Export public interface
__all__ = [
    'CircuitBreaker',
    'CircuitBreakerConfig',
    'CircuitBreakerRegistry',
    'CircuitBreakerOpenException',
    'circuit_registry',
    'get_wayback_machine_breaker',
    'get_meilisearch_breaker',
    'get_content_extraction_breaker',
    'with_circuit_breaker',
    'get_circuit_breaker_health'
]