"""
Robust Content Extraction Service with Advanced Fallback Strategies

This service implements a comprehensive fallback system for content extraction with:
- Circuit breaker patterns
- Multi-tier fallback cascading
- Concurrent processing with result selection
- Dead letter queues
- Comprehensive retry mechanisms
- Quality scoring and selection
"""
import asyncio
import time
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from pybreaker import CircuitBreaker
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import redis

from ..core.config import settings
from .intelligent_content_extractor import get_intelligent_extractor, ContentExtractionResult
from .archive_org_client import get_archive_client
from ..models.extraction_data import ExtractedContent, ContentExtractionException

logger = logging.getLogger(__name__)

# Circuit Breaker Configurations
CIRCUIT_BREAKERS = {
    'wayback': CircuitBreaker(fail_max=5, reset_timeout=60, name='wayback_breaker'),
    'trafilatura': CircuitBreaker(fail_max=10, reset_timeout=30, name='trafilatura_breaker'),
    'newspaper': CircuitBreaker(fail_max=8, reset_timeout=45, name='newspaper_breaker'),
    'readability': CircuitBreaker(fail_max=6, reset_timeout=40, name='readability_breaker'),
    'beautifulsoup': CircuitBreaker(fail_max=3, reset_timeout=20, name='beautifulsoup_breaker'),
}

class ExtractionStrategy(Enum):
    """Content extraction strategies ordered by quality (F1 scores)"""
    TRAFILATURA = ("trafilatura", 0.945, 1.0)  # Best quality, highest weight
    READABILITY = ("readability", 0.922, 0.85)  # High predictability
    NEWSPAPER3K = ("newspaper3k", 0.912, 0.75)  # News specialization
    BEAUTIFULSOUP = ("beautifulsoup", 0.750, 0.50)  # Reliable fallback
    
    def __init__(self, method_name: str, f1_score: float, weight: float):
        self.method_name = method_name
        self.f1_score = f1_score
        self.weight = weight

@dataclass
class ExtractionAttempt:
    """Represents a single extraction attempt with metadata"""
    strategy: ExtractionStrategy
    success: bool
    content: Optional[ContentExtractionResult] = None
    error: Optional[str] = None
    duration: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    quality_score: float = 0.0

@dataclass
class ExtractionResult:
    """Complete extraction result with all attempt details"""
    primary_content: Optional[ExtractedContent] = None
    attempts: List[ExtractionAttempt] = field(default_factory=list)
    total_duration: float = 0.0
    success: bool = False
    fallback_used: bool = False
    strategy_used: Optional[ExtractionStrategy] = None
    cache_hit: bool = False

class DeadLetterQueue:
    """Redis-based Dead Letter Queue for failed extractions"""
    
    def __init__(self, redis_url: str = None):
        self.redis_client = redis.from_url(redis_url or settings.REDIS_URL)
        self.dlq_stream = "extraction_failures"
        self.retry_stream = "extraction_retries"
        
    async def add_failed_extraction(self, url: str, error: str, attempts: List[ExtractionAttempt]):
        """Add failed extraction to DLQ for later analysis"""
        try:
            failure_data = {
                'url': url,
                'error': error,
                'attempts': len(attempts),
                'timestamp': datetime.utcnow().isoformat(),
                'last_strategy': attempts[-1].strategy.method_name if attempts else 'none',
                'total_duration': sum(attempt.duration for attempt in attempts)
            }
            
            self.redis_client.xadd(self.dlq_stream, failure_data)
            logger.info(f"Added failed extraction to DLQ: {url}")
            
        except Exception as e:
            logger.error(f"Failed to add extraction to DLQ: {e}")
    
    async def get_failed_extractions(self, count: int = 10) -> List[Dict[str, Any]]:
        """Retrieve failed extractions for analysis"""
        try:
            entries = self.redis_client.xrevrange(self.dlq_stream, count=count)
            return [{'id': entry_id.decode(), **{k.decode(): v.decode() for k, v in fields.items()}} 
                   for entry_id, fields in entries]
        except Exception as e:
            logger.error(f"Failed to retrieve DLQ entries: {e}")
            return []

class QualityScorer:
    """Advanced quality scoring for extraction results"""
    
    @staticmethod
    def calculate_quality_score(content: ContentExtractionResult, url: str) -> float:
        """Calculate comprehensive quality score (0.0 - 1.0)"""
        if not content or not content.text:
            return 0.0
            
        scores = {}
        
        # Length-based scoring (normalized)
        text_length = len(content.text.strip())
        scores['length'] = min(text_length / 2000, 1.0) * 0.25
        
        # Content structure scoring
        structure_score = 0.0
        if hasattr(content.metadata, 'title') and content.metadata.title:
            structure_score += 0.3
        if text_length > 100:  # Has substantial content
            structure_score += 0.4
        if hasattr(content.metadata, 'author') and content.metadata.author:
            structure_score += 0.15
        if hasattr(content.metadata, 'publication_date') and content.metadata.publication_date:
            structure_score += 0.15
        scores['structure'] = structure_score * 0.35
        
        # Content quality indicators
        sentences = content.text.count('.')
        paragraphs = content.text.count('\n\n')
        scores['readability'] = min((sentences + paragraphs) / 50, 1.0) * 0.20
        
        # Language detection confidence
        if hasattr(content.metadata, 'language') and content.metadata.language:
            scores['language'] = 0.15
        else:
            scores['language'] = 0.0
        
        # Noise detection (lower is better)
        noise_indicators = ['javascript:', 'document.', 'window.', 'function()', '<script', 'var ']
        noise_count = sum(content.text.lower().count(indicator) for indicator in noise_indicators)
        scores['noise'] = max(0, 0.05 - (noise_count / text_length * 10)) if text_length > 0 else 0
        
        total_score = sum(scores.values())
        logger.debug(f"Quality scores for {url}: {scores} = {total_score:.3f}")
        
        return min(total_score, 1.0)

class RobustContentExtractor:
    """
    Advanced content extraction service with comprehensive fallback strategies
    
    Features:
    - Circuit breaker pattern for resilience
    - Multi-tier fallback cascading
    - Concurrent processing with result selection
    - Quality scoring and best result selection
    - Dead letter queues for failed extractions
    - Comprehensive caching and retry mechanisms
    """
    
    def __init__(self):
        self.intelligent_extractor = get_intelligent_extractor()
        self.archive_client = get_archive_client()
        self.quality_scorer = QualityScorer()
        self.dlq = DeadLetterQueue()
        
        # Cache configuration
        self.redis_client = redis.from_url(settings.REDIS_URL)
        self.cache_prefix = "robust_extraction:"
        self.cache_ttl = 3600  # 1 hour
        
        # Concurrency configuration
        self.max_concurrent_extractions = getattr(settings, 'INTELLIGENT_EXTRACTION_CONCURRENCY', 10)
        self.extraction_timeout = 45  # seconds per extraction
        
        # Thread pool for concurrent processing
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.max_concurrent_extractions,
            thread_name_prefix="extraction_"
        )
        
        logger.info(f"Initialized RobustContentExtractor with {self.max_concurrent_extractions} max concurrent extractions")
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"{self.cache_prefix}{url_hash}"
    
    async def _get_cached_result(self, url: str) -> Optional[ExtractedContent]:
        """Retrieve cached extraction result"""
        try:
            cache_key = self._get_cache_key(url)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                logger.debug(f"Cache hit for {url}")
                return ExtractedContent(**data)
                
        except Exception as e:
            logger.warning(f"Cache retrieval failed for {url}: {e}")
        
        return None
    
    async def _cache_result(self, url: str, result: ExtractedContent):
        """Cache successful extraction result"""
        try:
            cache_key = self._get_cache_key(url)
            cache_data = json.dumps({
                'title': result.title,
                'text': result.text,
                'markdown': result.markdown,
                'html': result.html,
                'word_count': result.word_count,
                'extraction_method': result.extraction_method,
                'extraction_time': result.extraction_time,
                'meta_description': result.meta_description,
                'author': result.author,
                'language': result.language,
                'published_date': result.published_date.isoformat() if result.published_date else None,
                'source_url': result.source_url
            })
            
            self.redis_client.setex(cache_key, self.cache_ttl, cache_data)
            logger.debug(f"Cached result for {url}")
            
        except Exception as e:
            logger.warning(f"Failed to cache result for {url}: {e}")
    
    @CIRCUIT_BREAKERS['wayback']
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=60, multiplier=2),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    async def _fetch_content_with_fallback(self, url: str) -> str:
        """Fetch HTML content with robust error handling"""
        if 'web.archive.org' in url:
            return await self.archive_client.fetch_content(url)
        else:
            # Direct HTTP fetch for non-Archive.org URLs
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; chrono-scraper/2.0; research tool)'
                })
                response.raise_for_status()
                return response.text
    
    def _extract_with_strategy(self, html_content: str, url: str, strategy: ExtractionStrategy) -> ExtractionAttempt:
        """Extract content using a specific strategy with circuit breaker protection"""
        attempt = ExtractionAttempt(strategy=strategy, success=False)
        start_time = time.time()
        
        try:
            # Get the appropriate circuit breaker
            breaker = CIRCUIT_BREAKERS.get(strategy.method_name)
            if not breaker:
                breaker = CIRCUIT_BREAKERS['beautifulsoup']  # Default fallback
            
            @breaker
            def protected_extraction():
                return self.intelligent_extractor.extract_with_method(html_content, url, strategy.method_name)
            
            # Execute extraction with circuit breaker protection
            result = protected_extraction()
            
            if result and result.text and len(result.text.strip()) > 50:
                attempt.content = result
                attempt.success = True
                attempt.quality_score = self.quality_scorer.calculate_quality_score(result, url)
                logger.debug(f"Successful extraction with {strategy.method_name}: {len(result.text)} chars, quality: {attempt.quality_score:.3f}")
            else:
                attempt.error = f"Insufficient content from {strategy.method_name}"
                
        except Exception as e:
            attempt.error = f"{strategy.method_name} extraction failed: {str(e)}"
            logger.warning(attempt.error)
        finally:
            attempt.duration = time.time() - start_time
            
        return attempt
    
    async def _concurrent_extraction(self, html_content: str, url: str, strategies: List[ExtractionStrategy]) -> List[ExtractionAttempt]:
        """Run multiple extraction strategies concurrently"""
        attempts = []
        
        # Submit all extraction tasks to thread pool
        futures = {
            self.thread_pool.submit(self._extract_with_strategy, html_content, url, strategy): strategy 
            for strategy in strategies
        }
        
        # Collect results as they complete
        for future in as_completed(futures, timeout=self.extraction_timeout):
            try:
                attempt = future.result()
                attempts.append(attempt)
            except Exception as e:
                strategy = futures[future]
                failed_attempt = ExtractionAttempt(
                    strategy=strategy, 
                    success=False, 
                    error=f"Future execution failed: {str(e)}"
                )
                attempts.append(failed_attempt)
        
        # Sort by quality score (descending)
        attempts.sort(key=lambda a: a.quality_score, reverse=True)
        return attempts
    
    def _select_best_result(self, attempts: List[ExtractionAttempt], url: str) -> Tuple[Optional[ExtractedContent], Optional[ExtractionStrategy]]:
        """Select the best extraction result using weighted quality scoring"""
        if not attempts:
            return None, None
        
        successful_attempts = [a for a in attempts if a.success and a.content]
        if not successful_attempts:
            return None, None
        
        # Calculate weighted scores
        best_attempt = None
        best_weighted_score = 0.0
        
        for attempt in successful_attempts:
            # Weighted score = quality_score * strategy_weight * time_penalty
            time_penalty = max(0.5, 1.0 - (attempt.duration / self.extraction_timeout))
            weighted_score = attempt.quality_score * attempt.strategy.weight * time_penalty
            
            if weighted_score > best_weighted_score:
                best_weighted_score = weighted_score
                best_attempt = attempt
        
        if best_attempt:
            # Convert to ExtractedContent
            content = best_attempt.content
            extracted_content = ExtractedContent(
                title=content.metadata.title or "Untitled",
                text=content.text,
                markdown=content.markdown or content.text,
                html=content.html or "",
                word_count=content.word_count,
                extraction_method=f"robust_{best_attempt.strategy.method_name}",
                extraction_time=best_attempt.duration,
                meta_description=content.metadata.description,
                author=content.metadata.author,
                language=content.metadata.language,
                published_date=content.metadata.publication_date,
                source_url=url
            )
            
            return extracted_content, best_attempt.strategy
        
        return None, None
    
    async def extract_content(self, url: str) -> ExtractedContent:
        """
        Main extraction method with comprehensive fallback strategies
        
        Process:
        1. Check cache for existing result
        2. Fetch HTML content with retries
        3. Run concurrent extraction with multiple strategies
        4. Select best result using quality scoring
        5. Implement fallback cascade if needed
        6. Cache successful results
        7. Add failures to DLQ for analysis
        """
        start_time = time.time()
        extraction_result = ExtractionResult()
        
        try:
            # Step 1: Check cache
            cached_result = await self._get_cached_result(url)
            if cached_result:
                extraction_result.primary_content = cached_result
                extraction_result.success = True
                extraction_result.cache_hit = True
                extraction_result.total_duration = time.time() - start_time
                return cached_result
            
            # Step 2: Fetch HTML content
            logger.info(f"Starting robust extraction for: {url}")
            html_content = await self._fetch_content_with_fallback(url)
            
            if not html_content or len(html_content.strip()) < 100:
                raise ContentExtractionException(f"Insufficient HTML content from {url}")
            
            # Step 3: Primary concurrent extraction
            primary_strategies = [
                ExtractionStrategy.TRAFILATURA,
                ExtractionStrategy.READABILITY, 
                ExtractionStrategy.NEWSPAPER3K
            ]
            
            extraction_result.attempts = await self._concurrent_extraction(html_content, url, primary_strategies)
            best_content, best_strategy = self._select_best_result(extraction_result.attempts, url)
            
            if best_content:
                extraction_result.primary_content = best_content
                extraction_result.success = True
                extraction_result.strategy_used = best_strategy
                
                # Cache successful result
                await self._cache_result(url, best_content)
                
                extraction_result.total_duration = time.time() - start_time
                logger.info(f"Successful robust extraction: {url} using {best_strategy.method_name} "
                           f"({best_content.word_count} words in {extraction_result.total_duration:.3f}s)")
                return best_content
            
            # Step 4: Fallback cascade
            logger.warning(f"Primary extraction failed for {url}, trying fallback strategies")
            extraction_result.fallback_used = True
            
            fallback_strategies = [ExtractionStrategy.BEAUTIFULSOUP]
            fallback_attempts = await self._concurrent_extraction(html_content, url, fallback_strategies)
            extraction_result.attempts.extend(fallback_attempts)
            
            fallback_content, fallback_strategy = self._select_best_result(fallback_attempts, url)
            
            if fallback_content:
                extraction_result.primary_content = fallback_content
                extraction_result.success = True
                extraction_result.strategy_used = fallback_strategy
                
                extraction_result.total_duration = time.time() - start_time
                logger.info(f"Fallback extraction succeeded: {url} using {fallback_strategy.method_name}")
                return fallback_content
            
            # Step 5: Complete failure - add to DLQ
            extraction_result.total_duration = time.time() - start_time
            error_msg = f"All extraction strategies failed for {url}"
            await self.dlq.add_failed_extraction(url, error_msg, extraction_result.attempts)
            
            raise ContentExtractionException(error_msg)
            
        except Exception as e:
            extraction_result.total_duration = time.time() - start_time
            logger.error(f"Robust extraction completely failed for {url} after {extraction_result.total_duration:.3f}s: {e}")
            
            if extraction_result.attempts:
                await self.dlq.add_failed_extraction(url, str(e), extraction_result.attempts)
            
            raise ContentExtractionException(f"Robust extraction failed: {str(e)}")
    
    async def get_extraction_metrics(self) -> Dict[str, Any]:
        """Get comprehensive extraction performance metrics"""
        try:
            # Circuit breaker states
            breaker_states = {}
            for name, breaker in CIRCUIT_BREAKERS.items():
                try:
                    breaker_states[name] = {
                        'state': breaker.current_state,
                        'failure_count': breaker.fail_counter,
                        'last_failure': getattr(breaker, 'last_failure_time', None)
                    }
                except Exception as e:
                    breaker_states[name] = {
                        'state': 'unknown',
                        'failure_count': 0,
                        'error': str(e)
                    }
            
            # DLQ statistics
            failed_count = self.redis_client.xlen(self.dlq.dlq_stream)
            
            # Cache statistics
            cache_info = self.redis_client.info('memory')
            
            return {
                'circuit_breakers': breaker_states,
                'failed_extractions_count': failed_count,
                'cache_memory_usage': cache_info.get('used_memory_human', 'unknown'),
                'max_concurrent_extractions': self.max_concurrent_extractions,
                'extraction_timeout': self.extraction_timeout,
                'cache_ttl': self.cache_ttl
            }
            
        except Exception as e:
            logger.error(f"Failed to get extraction metrics: {e}")
            return {'error': str(e)}

# Global instance
_robust_extractor = None

def get_robust_extractor() -> RobustContentExtractor:
    """Get global robust content extractor instance"""
    global _robust_extractor
    if _robust_extractor is None:
        _robust_extractor = RobustContentExtractor()
    return _robust_extractor

# Enhanced extraction methods for the intelligent extractor
def enhance_intelligent_extractor():
    """Add robust extraction methods to the existing intelligent extractor"""
    from .intelligent_content_extractor import IntelligentContentExtractor
    
    def extract_with_method(self, html_content: str, url: str, method: str):
        """Extract content using a specific method"""
        if method == 'trafilatura':
            return self._extract_trafilatura(html_content, url)
        elif method == 'newspaper3k':
            return self._extract_newspaper(html_content, url)
        elif method == 'readability':
            return self._extract_readability(html_content, url)
        elif method == 'beautifulsoup':
            return self._extract_beautifulsoup(html_content, url)
        else:
            raise ValueError(f"Unknown extraction method: {method}")
    
    def _extract_readability(self, html_content: str, url: str):
        """Extract content using readability-lxml (high predictability F1: 0.922)"""
        try:
            from readability import Document
            from .intelligent_content_extractor import ExtractedMetadata, ContentExtractionResult
            
            doc = Document(html_content)
            title = doc.title()
            content = doc.summary()
            
            # Parse content with BeautifulSoup for text extraction
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text(strip=True, separator='\n')
            
            # Extract metadata
            soup_full = BeautifulSoup(html_content, 'html.parser')
            metadata = ExtractedMetadata()
            metadata.title = title
            
            # Meta tags
            if soup_full.find('meta', {'name': 'description'}):
                metadata.description = soup_full.find('meta', {'name': 'description'}).get('content', '')
            if soup_full.find('meta', {'name': 'author'}):
                metadata.author = soup_full.find('meta', {'name': 'author'}).get('content', '')
            
            return ContentExtractionResult(
                text=text,
                html=content,
                markdown=text,  # Simple markdown conversion
                title=title,
                word_count=len(text.split()),
                extraction_method='readability',
                metadata=metadata,
                confidence_score=0.8,  # Default confidence for readability
                processing_time=0.0    # Will be set by caller
            )
            
        except Exception as e:
            logger.warning(f"Readability extraction failed: {e}")
            raise
    
    # Monkey patch the intelligent extractor
    IntelligentContentExtractor.extract_with_method = extract_with_method
    IntelligentContentExtractor._extract_readability = _extract_readability

# Initialize enhanced extractor on module import
enhance_intelligent_extractor()