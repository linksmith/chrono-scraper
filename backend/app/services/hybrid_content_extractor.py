"""
Hybrid content extraction service combining BeautifulSoup and local Firecrawl
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from dataclasses import dataclass

import httpx
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type
)

from ..core.config import settings
from .content_extractor import ContentExtractor, ExtractedContent, ContentExtractionException
from .wayback_machine import CDXRecord

logger = logging.getLogger(__name__)


@dataclass
class HybridConfig:
    """Configuration for hybrid content extraction"""
    enabled: bool = True
    firecrawl_url: str = "http://localhost:3002"
    api_key: str = ""
    timeout: int = 30
    max_concurrent: int = 5
    fallback_enabled: bool = True
    
    # Smart routing criteria
    min_content_length: int = 1000  # Bytes
    high_value_domains: List[str] = None
    important_keywords: List[str] = None
    quality_boost_tlds: List[str] = None
    
    def __post_init__(self):
        if self.high_value_domains is None:
            self.high_value_domains = ['gov', 'edu', 'org', 'mil']
        if self.important_keywords is None:
            self.important_keywords = ['research', 'report', 'analysis', 'study', 'whitepaper']
        if self.quality_boost_tlds is None:
            self.quality_boost_tlds = ['.gov', '.edu', '.org', '.mil', '.ac.']


class HybridContentExtractor:
    """
    Hybrid content extractor that intelligently routes content processing
    between local Firecrawl (for high-value content) and BeautifulSoup (for standard content)
    """
    
    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig()
        
        # Initialize components
        self.beautifulsoup_extractor = ContentExtractor()
        self.firecrawl_semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        # Metrics tracking
        self.metrics = {
            'hybrid_requests': 0,
            'beautifulsoup_requests': 0,
            'hybrid_successes': 0,
            'hybrid_failures': 0,
            'fallback_uses': 0,
            'total_processing_time': 0.0,
            'quality_scores': []
        }
        
        # Configure from settings if available
        if hasattr(settings, 'FIRECRAWL_LOCAL_URL'):
            self.config.firecrawl_url = settings.FIRECRAWL_LOCAL_URL
        if hasattr(settings, 'FIRECRAWL_API_KEY'):
            self.config.api_key = settings.FIRECRAWL_API_KEY
            
        logger.info(f"Initialized hybrid content extractor with Firecrawl: {self.config.firecrawl_url}")
    
    async def extract_content(self, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Main extraction method with intelligent routing
        
        Args:
            cdx_record: CDX record containing URL and metadata
            
        Returns:
            ExtractedContent with best available extraction
        """
        start_time = time.time()
        
        try:
            # Decide routing strategy
            use_hybrid = self._should_use_hybrid_processing(cdx_record)
            
            if use_hybrid and self.config.enabled:
                logger.debug(f"Using hybrid processing for: {cdx_record.original_url}")
                result = await self._extract_with_firecrawl(cdx_record)
                
                # If hybrid fails and fallback is enabled, try BeautifulSoup
                if (not result.text or "error" in result.extraction_method) and self.config.fallback_enabled:
                    logger.warning(f"Hybrid processing failed, falling back to BeautifulSoup: {cdx_record.original_url}")
                    result = await self._extract_with_beautifulsoup(cdx_record)
                    result.extraction_method = "hybrid_fallback"
                    self.metrics['fallback_uses'] += 1
                    
                self.metrics['hybrid_requests'] += 1
                if result.text and "error" not in result.extraction_method:
                    self.metrics['hybrid_successes'] += 1
                else:
                    self.metrics['hybrid_failures'] += 1
            else:
                logger.debug(f"Using standard processing for: {cdx_record.original_url}")
                result = await self._extract_with_beautifulsoup(cdx_record)
                self.metrics['beautifulsoup_requests'] += 1
            
            # Track metrics
            processing_time = time.time() - start_time
            result.extraction_time = processing_time
            self.metrics['total_processing_time'] += processing_time
            
            # Calculate and track quality score
            quality_score = self._calculate_quality_score(result)
            self.metrics['quality_scores'].append(quality_score)
            
            return result
            
        except Exception as e:
            logger.error(f"Content extraction failed for {cdx_record.original_url}: {e}")
            return ExtractedContent(
                title="",
                text="",
                markdown="",
                html="",
                word_count=0,
                extraction_method="hybrid_error",
                extraction_time=time.time() - start_time
            )
    
    def _should_use_hybrid_processing(self, cdx_record: CDXRecord) -> bool:
        """
        Decide whether to use hybrid processing based on content characteristics
        
        Args:
            cdx_record: CDX record to evaluate
            
        Returns:
            True if should use hybrid processing (Firecrawl)
        """
        url = cdx_record.original_url.lower()
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        path = parsed_url.path.lower()
        
        # High-value domain TLDs (government, education, etc.)
        if any(tld in domain for tld in self.config.quality_boost_tlds):
            logger.debug(f"High-value TLD detected: {domain}")
            return True
        
        # High-value domain patterns
        if any(pattern in domain for pattern in self.config.high_value_domains):
            logger.debug(f"High-value domain pattern detected: {domain}")
            return True
        
        # Content size - larger content likely to be articles/documents
        if cdx_record.length and int(cdx_record.length) >= self.config.min_content_length:
            logger.debug(f"Large content detected: {cdx_record.length} bytes")
            return True
        
        # Important content keywords in URL path
        if any(keyword in path for keyword in self.config.important_keywords):
            logger.debug(f"Important keyword detected in path: {path}")
            return True
        
        # Specific high-value URL patterns
        high_value_patterns = [
            '/research/', '/report/', '/paper/', '/publication/', 
            '/document/', '/study/', '/analysis/', '/whitepaper/',
            '/press-release/', '/news/', '/article/', '/blog/'
        ]
        if any(pattern in path for pattern in high_value_patterns):
            logger.debug(f"High-value URL pattern detected: {path}")
            return True
        
        # PDF files - often documents worth enhanced extraction
        if cdx_record.mime_type and 'pdf' in cdx_record.mime_type.lower():
            logger.debug(f"PDF content detected: {cdx_record.mime_type}")
            return True
        
        return False
    
    async def _extract_with_firecrawl(self, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Extract content using local Firecrawl service
        
        Args:
            cdx_record: CDX record to process
            
        Returns:
            ExtractedContent from Firecrawl processing
        """
        wayback_url = f"https://web.archive.org/web/{cdx_record.timestamp}/{cdx_record.original_url}"
        
        async with self.firecrawl_semaphore:
            return await self._call_firecrawl_api(wayback_url, cdx_record)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def _call_firecrawl_api(self, wayback_url: str, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Make API call to local Firecrawl service
        
        Args:
            wayback_url: Full Wayback Machine URL
            cdx_record: Original CDX record
            
        Returns:
            ExtractedContent from Firecrawl
        """
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                payload = {
                    "url": wayback_url,
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                    "includeMetadata": True
                }
                
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                response = await client.post(
                    f"{self.config.firecrawl_url}/v0/scrape",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Parse Firecrawl response structure
                    if data.get("success") and "data" in data:
                        content_data = data["data"]
                        
                        # Extract content and metadata
                        title = content_data.get("metadata", {}).get("title", "") or ""
                        content = content_data.get("content", "") or ""
                        markdown = content_data.get("markdown", "") or content
                        metadata = content_data.get("metadata", {})
                        
                        # Calculate word count
                        word_count = len(content.split()) if content else 0
                        
                        return ExtractedContent(
                            title=title,
                            text=content,
                            markdown=markdown,
                            html="",  # Firecrawl doesn't return raw HTML
                            word_count=word_count,
                            extraction_method="hybrid_firecrawl",
                            extraction_time=0.0  # Will be set by caller
                        )
                    else:
                        error_msg = data.get("error", "Unknown Firecrawl error")
                        raise ContentExtractionException(f"Firecrawl processing failed: {error_msg}")
                else:
                    raise ContentExtractionException(f"Firecrawl API returned {response.status_code}: {response.text[:200]}")
                    
        except httpx.TimeoutException as e:
            raise ContentExtractionException(f"Firecrawl timeout: {e}")
        except httpx.ConnectError as e:
            raise ContentExtractionException(f"Firecrawl connection error: {e}")
        except Exception as e:
            raise ContentExtractionException(f"Firecrawl extraction failed: {e}")
    
    async def _extract_with_beautifulsoup(self, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Extract content using BeautifulSoup (fallback method)
        
        Args:
            cdx_record: CDX record to process
            
        Returns:
            ExtractedContent from BeautifulSoup processing
        """
        try:
            result = await self.beautifulsoup_extractor.extract_content_from_record(cdx_record)
            result.extraction_method = "hybrid_beautifulsoup"
            return result
        except Exception as e:
            logger.error(f"BeautifulSoup extraction failed: {e}")
            return ExtractedContent(
                title="",
                text="",
                markdown="", 
                html="",
                word_count=0,
                extraction_method="beautifulsoup_error",
                extraction_time=0.0
            )
    
    def _calculate_quality_score(self, result: ExtractedContent) -> float:
        """
        Calculate quality score for extraction result (0-10 scale)
        
        Args:
            result: ExtractedContent to score
            
        Returns:
            Quality score from 0-10
        """
        score = 0.0
        
        # Check if extraction was successful (has content)
        if not result.text or "error" in result.extraction_method:
            return 0.0
        
        # Content length scoring (0-3 points)
        if result.word_count > 50:
            score += min(result.word_count / 200, 3.0)
        
        # Title quality (0-1 point)
        if result.title and len(result.title.strip()) > 5:
            score += 1.0
        
        # Metadata richness (0-2 points)  
        metadata_fields = ['author', 'meta_description', 'meta_keywords', 'language', 'published_date']
        metadata_score = sum(0.4 for field in metadata_fields if getattr(result, field, None))
        score += min(metadata_score, 2.0)
        
        # Structured content (0-2 points)
        if result.markdown and len(result.markdown) > len(result.text) * 0.5:
            score += 1.0  # Good markdown structure
        
        # Processing method bonus
        if "firecrawl" in result.extraction_method:
            score += 1.0  # Firecrawl typically produces higher quality
        
        # Success bonus
        score += 1.0
        
        return min(score, 10.0)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics
        
        Returns:
            Dictionary with performance statistics
        """
        total_requests = self.metrics['hybrid_requests'] + self.metrics['beautifulsoup_requests']
        avg_quality = sum(self.metrics['quality_scores']) / len(self.metrics['quality_scores']) if self.metrics['quality_scores'] else 0
        
        return {
            'total_requests': total_requests,
            'hybrid_requests': self.metrics['hybrid_requests'],
            'beautifulsoup_requests': self.metrics['beautifulsoup_requests'],
            'hybrid_success_rate': (self.metrics['hybrid_successes'] / max(self.metrics['hybrid_requests'], 1)) * 100,
            'fallback_usage_rate': (self.metrics['fallback_uses'] / max(self.metrics['hybrid_requests'], 1)) * 100,
            'average_quality_score': round(avg_quality, 2),
            'average_processing_time': round(self.metrics['total_processing_time'] / max(total_requests, 1), 3),
            'hybrid_percentage': round((self.metrics['hybrid_requests'] / max(total_requests, 1)) * 100, 1)
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of hybrid extraction service
        
        Returns:
            Health check results
        """
        health = {
            'hybrid_extractor': 'healthy',
            'firecrawl_service': 'unknown',
            'beautifulsoup_extractor': 'healthy'
        }
        
        # Test Firecrawl connectivity
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.config.firecrawl_url}/")
                if response.status_code == 200:
                    health['firecrawl_service'] = 'healthy'
                else:
                    health['firecrawl_service'] = f'unhealthy (HTTP {response.status_code})'
        except Exception as e:
            health['firecrawl_service'] = f'unhealthy ({str(e)[:50]})'
        
        return health


# Global instance
_hybrid_extractor = None

def get_hybrid_extractor() -> HybridContentExtractor:
    """Get global hybrid extractor instance"""
    global _hybrid_extractor
    if _hybrid_extractor is None:
        config = HybridConfig(
            enabled=getattr(settings, 'HYBRID_PROCESSING_ENABLED', True),
            firecrawl_url=getattr(settings, 'FIRECRAWL_LOCAL_URL', 'http://localhost:3002'),
            api_key=getattr(settings, 'FIRECRAWL_API_KEY', ''),
            timeout=getattr(settings, 'HYBRID_TIMEOUT', 30),
            max_concurrent=getattr(settings, 'HYBRID_MAX_CONCURRENT', 5)
        )
        _hybrid_extractor = HybridContentExtractor(config)
    return _hybrid_extractor


# Convenience function for backward compatibility
async def extract_content_hybrid(cdx_record: CDXRecord) -> ExtractedContent:
    """
    Extract content using hybrid approach
    
    Args:
        cdx_record: CDX record to process
        
    Returns:
        ExtractedContent with best available extraction
    """
    extractor = get_hybrid_extractor()
    return await extractor.extract_content(cdx_record)