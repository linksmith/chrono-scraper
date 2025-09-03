import logging
import uuid
from typing import Dict, List, Optional, Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class FirecrawlV2Error(Exception):
    """Enhanced error class for Firecrawl v2 API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}
        
    def __str__(self):
        if self.status_code:
            return f"FirecrawlV2Error({self.status_code}): {self.args[0]}"
        return f"FirecrawlV2Error: {self.args[0]}"


class FirecrawlV2Client:
    """Enhanced client for Firecrawl v2 Batch Scrape with caching, summary format, and improved error handling.

    Features:
    - v2 caching support with maxAge parameter (defaults to 2 days)
    - Summary format extraction option
    - Enhanced error handling with structured error responses
    - Proper v2 batch endpoints
    
    In test environment (settings.ENVIRONMENT == "test"), network calls are stubbed.
    """

    def __init__(self):
        # Use FIRECRAWL_BASE_URL for both local and cloud deployments
        base_url = getattr(settings, "FIRECRAWL_BASE_URL", None)
        self.base_url = (base_url or "http://localhost:3002").rstrip("/")
        self.version = (getattr(settings, "FIRECRAWL_API_VERSION", "v2") or "v2").lower().strip()
        self.api_key = getattr(settings, "FIRECRAWL_API_KEY", None)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def start_batch(
        self, 
        urls: List[str], 
        formats: Optional[List[str]] = None, 
        timeout_ms: Optional[int] = None,
        max_age_hours: Optional[int] = None,
        extract_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Start a batch scrape job using Firecrawl V2 API and return the batch id.

        Args:
            urls: List of URLs to scrape
            formats: Output formats (markdown, html, summary, etc.)
            timeout_ms: Request timeout in milliseconds
            max_age_hours: Cache max age in hours (defaults to 48 hours)
            extract_options: Additional extraction options for v2
            
        Returns:
            Batch ID for tracking the job
            
        Raises:
            FirecrawlV2Error: On API errors with structured error information
            
        Firecrawl v2: POST /v2/batch/scrape
        """
        if getattr(settings, "ENVIRONMENT", "development") == "test":
            # Avoid network in tests
            return f"test-batch-{uuid.uuid4().hex[:8]}"

        formats = formats or ["markdown", "html"]
        timeout_ms = timeout_ms or 60_000
        max_age_hours = max_age_hours if max_age_hours is not None else 48  # v2 default: 2 days
        extract_options = extract_options or {}

        # Use proper v2 API endpoints now that service is updated
        if self.version != "v2":
            logger.warning(f"Using v2 endpoints regardless of configured version: {self.version}")

        path = "/v2/batch/scrape"
        
        # Build v2 payload with caching and enhanced options
        payload = {
            "urls": urls,
            "formats": formats,
            "timeout": timeout_ms,
            "maxAge": max_age_hours * 3600,  # Convert hours to seconds for v2 API
        }
        
        # Add extraction options if provided
        if extract_options:
            payload.update(extract_options)
            
        logger.info(f"Starting Firecrawl v2 batch with {len(urls)} URLs, formats: {formats}, cache: {max_age_hours}h")
        
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.base_url + path, json=payload, headers=self._headers())
                
                # Enhanced error handling for v2
                if not resp.is_success:
                    error_data = {}
                    try:
                        error_data = resp.json()
                    except:
                        pass
                    
                    error_msg = error_data.get("error", f"HTTP {resp.status_code}: {resp.reason_phrase}")
                    raise FirecrawlV2Error(
                        message=error_msg,
                        status_code=resp.status_code,
                        response_data=error_data
                    )
                
                data = resp.json()
                batch_id = data.get("id") or data.get("crawl_id") or ""
                
                if not batch_id:
                    raise FirecrawlV2Error("No batch ID returned from API", response_data=data)
                    
                logger.info(f"Successfully started batch {batch_id}")
                return batch_id
                
        except FirecrawlV2Error:
            raise
        except Exception as e:
            raise FirecrawlV2Error(f"Failed to start Firecrawl V2 batch: {str(e)}")

    def get_batch_status(self, batch_id: str, next_token: Optional[str] = None) -> Dict[str, Any]:
        """Get the status of a batch scrape job.
        
        Args:
            batch_id: The batch ID to check
            next_token: Optional pagination token returned by the API to fetch the next page of results
            
        Returns:
            Dictionary with batch status information
            
        Raises:
            FirecrawlV2Error: On API errors
            
        Firecrawl v2: GET /v2/batch/scrape/:id
        """
        if not batch_id:
            raise FirecrawlV2Error("Batch ID is required")
            
        if getattr(settings, "ENVIRONMENT", "development") == "test":
            return {
                "success": True,
                "status": "completed",
                "total": 1,
                "completed": 1,
                "creditsUsed": 1,
                "data": []
            }
            
        try:
            path = f"/v2/batch/scrape/{batch_id}"
            if next_token:
                path += f"?next={httpx.QueryParams({'next': next_token})['next']}"
            with httpx.Client(timeout=15) as client:
                resp = client.get(self.base_url + path, headers=self._headers())
                
                if not resp.is_success:
                    error_data = {}
                    try:
                        error_data = resp.json()
                    except:
                        pass
                    
                    error_msg = error_data.get("error", f"HTTP {resp.status_code}: Failed to get batch status")
                    raise FirecrawlV2Error(
                        message=error_msg,
                        status_code=resp.status_code,
                        response_data=error_data
                    )
                
                return resp.json()
                
        except FirecrawlV2Error:
            raise
        except Exception as e:
            raise FirecrawlV2Error(f"Failed to get batch status: {str(e)}")
    
    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch scrape using Firecrawl V2 API.
        
        Args:
            batch_id: The batch ID to cancel
            
        Returns:
            True if successfully cancelled, False otherwise
            
        Raises:
            FirecrawlV2Error: On API errors (only in strict mode)
            
        Firecrawl v2: DELETE /v2/batch/scrape/:id
        """
        if not batch_id:
            return False

        if getattr(settings, "ENVIRONMENT", "development") == "test":
            # Pretend success in tests
            return True

        try:
            path = f"/v2/batch/scrape/{batch_id}"
            with httpx.Client(timeout=15) as client:
                resp = client.delete(self.base_url + path, headers=self._headers())
                
                success = 200 <= resp.status_code < 300
                if success:
                    logger.info(f"Successfully cancelled batch {batch_id}")
                else:
                    logger.warning(f"Failed to cancel batch {batch_id}: HTTP {resp.status_code}")
                    
                return success
        except Exception as e:
            logger.error(f"Error cancelling batch {batch_id}: {str(e)}")
            return False
            
    def scrape_with_summary(
        self,
        urls: List[str],
        summary_prompt: Optional[str] = None,
        max_age_hours: Optional[int] = None
    ) -> str:
        """Convenience method to scrape URLs with summary format.
        
        Args:
            urls: URLs to scrape
            summary_prompt: Custom prompt for summary generation (optional)
            max_age_hours: Cache duration in hours
            
        Returns:
            Batch ID for the summary scraping job
            
        Raises:
            FirecrawlV2Error: On API errors
        """
        # For now, let's keep it simple without extract options
        # as the local Firecrawl might not support all v2 extract features yet
        return self.start_batch(
            urls=urls,
            formats=["summary", "markdown"],  # Include both summary and markdown
            max_age_hours=max_age_hours
        )


