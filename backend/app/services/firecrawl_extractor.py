"""
Firecrawl-only content extraction service for enhanced scraping quality
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

import httpx
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type
)

from ..core.config import settings
from .wayback_machine import CDXRecord
from ..models.extraction_data import ExtractedContent, ContentExtractionException

logger = logging.getLogger(__name__)


@dataclass
class FirecrawlConfig:
    """Configuration for Firecrawl content extraction"""
    firecrawl_url: str = "http://localhost:3002"
    api_key: str = "fc-test-key-for-local-development"
    timeout: int = 300  # 5 minutes for slow Wayback Machine
    wayback_timeout: int = 600  # 10 minutes for Wayback Machine URLs
    max_concurrent: int = 20  # Increased for parallel processing
    use_proxy: bool = False
    proxy_http: Optional[str] = None
    proxy_https: Optional[str] = None
    
    def __post_init__(self):
        # Override with settings if available
        if hasattr(settings, 'FIRECRAWL_LOCAL_URL') and settings.FIRECRAWL_LOCAL_URL:
            self.firecrawl_url = settings.FIRECRAWL_LOCAL_URL
        elif hasattr(settings, 'FIRECRAWL_BASE_URL') and settings.FIRECRAWL_BASE_URL:
            self.firecrawl_url = settings.FIRECRAWL_BASE_URL
            
        if hasattr(settings, 'FIRECRAWL_API_KEY') and settings.FIRECRAWL_API_KEY:
            self.api_key = settings.FIRECRAWL_API_KEY
            
        # For local development, don't use authentication if it's the test key
        if self.api_key == "fc-test-key-for-local-development":
            self.api_key = ""
            
        if hasattr(settings, 'USE_PROXY'):
            self.use_proxy = settings.USE_PROXY
        if hasattr(settings, 'PROXY_HTTP'):
            self.proxy_http = settings.PROXY_HTTP
        if hasattr(settings, 'PROXY_HTTPS'):
            self.proxy_https = settings.PROXY_HTTPS
        
        # Build proxy URLs from Decodo credentials if available
        if hasattr(settings, 'DECODO_USERNAME') and hasattr(settings, 'DECODO_PASSWORD'):
            proxy_auth = f"{settings.DECODO_USERNAME}:{settings.DECODO_PASSWORD}"
            proxy_host = getattr(settings, 'DECODO_ENDPOINT', 'gate.smartproxy.com')
            proxy_port = getattr(settings, 'DECODO_PORT_RESIDENTIAL', 10001)
            self.proxy_http = f"http://{proxy_auth}@{proxy_host}:{proxy_port}"
            self.proxy_https = f"http://{proxy_auth}@{proxy_host}:{proxy_port}"
            self.use_proxy = True


class FirecrawlExtractor:
    """
    Firecrawl-only content extractor for high-quality content processing
    """
    
    def __init__(self, config: Optional[FirecrawlConfig] = None):
        self.config = config or FirecrawlConfig()
        self.firecrawl_semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        # Metrics tracking
        self.metrics = {
            'total_requests': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'total_processing_time': 0.0,
            'quality_scores': []
        }
        
        logger.info(f"Initialized Firecrawl extractor with URL: {self.config.firecrawl_url}")
    
    async def extract_content(self, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Extract content using Firecrawl service
        
        Args:
            cdx_record: CDX record containing URL and metadata
            
        Returns:
            ExtractedContent with Firecrawl extraction
        """
        start_time = time.time()
        wayback_url = f"https://web.archive.org/web/{cdx_record.timestamp}/{cdx_record.original_url}"
        
        self.metrics['total_requests'] += 1
        
        try:
            async with self.firecrawl_semaphore:
                result = await self._call_firecrawl_api(wayback_url, cdx_record)
                
            # Track metrics
            processing_time = time.time() - start_time
            result.extraction_time = processing_time
            self.metrics['total_processing_time'] += processing_time
            
            if result.text and result.word_count > 50:
                self.metrics['successful_extractions'] += 1
                quality_score = self._calculate_quality_score(result)
                self.metrics['quality_scores'].append(quality_score)
            else:
                self.metrics['failed_extractions'] += 1
            
            return result
            
        except Exception as e:
            self.metrics['failed_extractions'] += 1
            logger.error(f"Firecrawl extraction failed for {cdx_record.original_url}: {e}")
            
            return ExtractedContent(
                title="",
                text="",
                markdown="",
                html="",
                word_count=0,
                extraction_method="firecrawl_error",
                extraction_time=time.time() - start_time
            )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
    )
    async def _call_firecrawl_api(self, wayback_url: str, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Make API call to Firecrawl service
        
        Args:
            wayback_url: Full Wayback Machine URL
            cdx_record: Original CDX record
            
        Returns:
            ExtractedContent from Firecrawl
        """
        try:
            # Use much longer timeout for Wayback Machine URLs
            timeout = self.config.wayback_timeout if 'web.archive.org' in wayback_url else self.config.timeout
            
            # Use simple httpx client without proxy support for now
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
            ) as client:
                # Use appropriate timeout for Firecrawl request
                firecrawl_timeout = timeout * 1000  # Convert to milliseconds for Firecrawl
                
                payload = {
                    "url": wayback_url,
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                    "includeMetadata": True,
                    "waitFor": 5000 if 'web.archive.org' in wayback_url else 2000,  # Longer wait for Wayback
                    "timeout": firecrawl_timeout,
                    "actions": [
                        {"type": "wait", "milliseconds": 3000}  # Additional wait for slow Wayback pages
                    ] if 'web.archive.org' in wayback_url else []
                }
                
                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                
                logger.debug(f"Calling Firecrawl for: {wayback_url}")
                
                response = await client.post(
                    f"{self.config.firecrawl_url}/v0/scrape",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("success") and "data" in data:
                        content_data = data["data"]
                        
                        # Extract content and metadata
                        title = content_data.get("metadata", {}).get("title", "") or ""
                        content = content_data.get("content", "") or ""
                        markdown = content_data.get("markdown", "") or content
                        html = content_data.get("html", "")
                        
                        # Extract metadata
                        metadata = content_data.get("metadata", {})
                        description = metadata.get("description")
                        author = metadata.get("author")
                        language = metadata.get("language")
                        source_url = metadata.get("sourceURL")
                        status_code = metadata.get("statusCode")
                        error = metadata.get("error")
                        
                        # Parse published date
                        published_date = None
                        if metadata.get("publishedTime"):
                            try:
                                published_date = datetime.fromisoformat(metadata["publishedTime"].replace('Z', '+00:00'))
                            except:
                                pass
                        
                        # Calculate word count
                        word_count = len(content.split()) if content else 0
                        
                        return ExtractedContent(
                            title=title,
                            text=content,
                            markdown=markdown,
                            html=html,
                            meta_description=description,
                            author=author,
                            language=language,
                            source_url=source_url,
                            status_code=status_code,
                            error=error,
                            published_date=published_date,
                            word_count=word_count,
                            extraction_method="firecrawl",
                            extraction_time=0.0  # Will be set by caller
                        )
                    else:
                        error_msg = data.get("error", "Unknown Firecrawl error")
                        logger.warning(f"Firecrawl processing failed: {error_msg}")
                        raise ContentExtractionException(f"Firecrawl processing failed: {error_msg}")
                else:
                    error_text = response.text[:200] if response.text else "No response text"
                    logger.error(f"Firecrawl API returned {response.status_code}: {error_text}")
                    raise ContentExtractionException(f"Firecrawl API returned {response.status_code}")
                    
        except httpx.TimeoutException as e:
            logger.error(f"Firecrawl timeout for {wayback_url}")
            raise ContentExtractionException(f"Firecrawl timeout: {e}")
        except httpx.ConnectError as e:
            logger.error(f"Firecrawl connection error for {wayback_url}")
            raise ContentExtractionException(f"Firecrawl connection error: {e}")
        except Exception as e:
            logger.error(f"Firecrawl extraction failed: {e}")
            raise ContentExtractionException(f"Firecrawl extraction failed: {e}")
    
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
        
        # Content length scoring (0-4 points)
        if result.word_count > 100:
            score += min(result.word_count / 300, 4.0)
        elif result.word_count > 50:
            score += 2.0
        elif result.word_count > 20:
            score += 1.0
        
        # Title quality (0-1 point)
        if result.title and len(result.title.strip()) > 5:
            score += 1.0
        
        # Metadata richness (0-2 points)  
        metadata_fields = ['meta_description', 'author', 'language', 'published_date']
        metadata_score = sum(0.5 for field in metadata_fields if getattr(result, field, None))
        score += min(metadata_score, 2.0)
        
        # Structured content (0-2 points)
        if result.markdown and len(result.markdown) > len(result.text) * 0.5:
            score += 2.0  # Good markdown structure
        elif result.markdown:
            score += 1.0
        
        # Success bonus for Firecrawl
        score += 1.0
        
        return min(score, 10.0)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics
        
        Returns:
            Dictionary with performance statistics
        """
        total_requests = self.metrics['total_requests']
        success_rate = (self.metrics['successful_extractions'] / max(total_requests, 1)) * 100
        avg_quality = sum(self.metrics['quality_scores']) / len(self.metrics['quality_scores']) if self.metrics['quality_scores'] else 0
        
        return {
            'total_requests': total_requests,
            'successful_extractions': self.metrics['successful_extractions'],
            'failed_extractions': self.metrics['failed_extractions'],
            'success_rate': round(success_rate, 2),
            'average_quality_score': round(avg_quality, 2),
            'average_processing_time': round(self.metrics['total_processing_time'] / max(total_requests, 1), 3)
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of Firecrawl extraction service
        
        Returns:
            Health check results
        """
        health = {
            'firecrawl_extractor': 'healthy',
            'firecrawl_service': 'unknown'
        }
        
        # Test Firecrawl connectivity
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.config.firecrawl_url}/")
                if response.status_code == 200:
                    health['firecrawl_service'] = 'healthy'
                else:
                    health['firecrawl_service'] = f'unhealthy (HTTP {response.status_code})'
        except Exception as e:
            health['firecrawl_service'] = f'unhealthy ({str(e)[:50]})'
        
        return health


# Global instance
_firecrawl_extractor = None

def get_firecrawl_extractor() -> FirecrawlExtractor:
    """Get global Firecrawl extractor instance"""
    global _firecrawl_extractor
    if _firecrawl_extractor is None:
        config = FirecrawlConfig()
        _firecrawl_extractor = FirecrawlExtractor(config)
    return _firecrawl_extractor


# Convenience function
async def extract_content_firecrawl(cdx_record: CDXRecord) -> ExtractedContent:
    """
    Extract content using Firecrawl approach
    
    Args:
        cdx_record: CDX record to process
        
    Returns:
        ExtractedContent with Firecrawl extraction
    """
    extractor = get_firecrawl_extractor()
    return await extractor.extract_content(cdx_record)