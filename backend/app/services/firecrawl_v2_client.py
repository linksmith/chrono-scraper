import uuid
from typing import List, Optional

import httpx

from app.core.config import settings


class FirecrawlV2Client:
    """Thin client for Firecrawl v2 Batch Scrape only.

    In test environment (settings.ENVIRONMENT == "test"), network calls are stubbed.
    V1 fallback support has been removed - only V2 batch operations are supported.
    """

    def __init__(self):
        # Prefer local URL when available
        base_url = getattr(settings, "FIRECRAWL_LOCAL_URL", None) or getattr(settings, "FIRECRAWL_BASE_URL", None)
        self.base_url = (base_url or "http://localhost:3002").rstrip("/")
        self.version = (getattr(settings, "FIRECRAWL_API_VERSION", "v2") or "v2").lower().strip()
        self.api_key = getattr(settings, "FIRECRAWL_API_KEY", None)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def start_batch(self, urls: List[str], formats: Optional[List[str]] = None, timeout_ms: Optional[int] = None) -> str:
        """Start a batch scrape job using Firecrawl V2 API and return the batch id.

        Only supports V2: POST /v2/scrape/batch
        """
        if getattr(settings, "ENVIRONMENT", "development") == "test":
            # Avoid network in tests
            return f"test-batch-{uuid.uuid4().hex[:8]}"

        formats = formats or ["markdown", "html"]
        timeout_ms = timeout_ms or 60_000

        # Only V2 API is supported
        if self.version != "v2":
            raise ValueError("Only Firecrawl V2 API is supported. Please set FIRECRAWL_API_VERSION=v2")

        path = "/v2/scrape/batch"
        payload = {
            "urls": urls,
            "formats": formats,
            "timeout": timeout_ms,
        }
        
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.base_url + path, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return data.get("id") or data.get("crawl_id") or ""
        except Exception as e:
            raise RuntimeError(f"Failed to start Firecrawl V2 batch: {str(e)}")

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch scrape using Firecrawl V2 API.

        Only supports V2: DELETE /v2/scrape/batch/:id
        """
        if not batch_id:
            return False

        if getattr(settings, "ENVIRONMENT", "development") == "test":
            # Pretend success in tests
            return True

        try:
            # Only V2 API is supported
            if self.version != "v2":
                raise ValueError("Only Firecrawl V2 API is supported")

            path = f"/v2/scrape/batch/{batch_id}"
            with httpx.Client(timeout=15) as client:
                resp = client.delete(self.base_url + path, headers=self._headers())
                return 200 <= resp.status_code < 300
        except Exception:
            return False


