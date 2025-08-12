"""
Wayback Machine CDX API integration service
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, AsyncGenerator
from urllib.parse import urljoin, urlparse
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class WaybackMachineService:
    """Service for interacting with the Wayback Machine CDX API"""
    
    CDX_API_URL = "https://web.archive.org/cdx/search/cdx"
    WAYBACK_BASE_URL = "https://web.archive.org/web/"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": "chrono-scraper/1.0 (research tool)"
                }
            )
        return self.session
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def search_snapshots(
        self,
        url: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        match_type: str = "prefix",
        collapse: Optional[str] = "timestamp:8",
        limit: Optional[int] = None,
        status_codes: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for snapshots of a URL in the Wayback Machine
        
        Args:
            url: URL to search for
            from_date: Start date for search (YYYYMMDD format internally)
            to_date: End date for search (YYYYMMDD format internally)
            match_type: Type of URL matching (exact, prefix, host, domain)
            collapse: Collapse duplicate captures (timestamp:8 recommended)
            limit: Maximum number of results
            status_codes: Filter by HTTP status codes (default: [200])
        
        Returns:
            List of snapshot dictionaries
        """
        session = await self.get_session()
        
        # Format dates
        from_str = from_date.strftime("%Y%m%d") if from_date else None
        to_str = to_date.strftime("%Y%m%d") if to_date else None
        
        # Default status codes
        if status_codes is None:
            status_codes = [200]
        
        params = {
            "url": url,
            "output": "json",
            "matchType": match_type,
            "fl": "timestamp,original,statuscode,mimetype,digest,length"
        }
        
        if from_str:
            params["from"] = from_str
        if to_str:
            params["to"] = to_str
        if collapse:
            params["collapse"] = collapse
        if limit:
            params["limit"] = str(limit)
        
        try:
            async with session.get(self.CDX_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Skip header row if present
                    if data and isinstance(data[0], list) and data[0][0] == "timestamp":
                        data = data[1:]
                    
                    snapshots = []
                    for row in data:
                        if len(row) >= 6:
                            timestamp, original, statuscode, mimetype, digest, length = row[:6]
                            
                            # Filter by status codes
                            try:
                                status_int = int(statuscode)
                                if status_int not in status_codes:
                                    continue
                            except (ValueError, TypeError):
                                continue
                            
                            # Parse timestamp
                            try:
                                capture_date = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                            except ValueError:
                                logger.warning(f"Invalid timestamp format: {timestamp}")
                                continue
                            
                            snapshots.append({
                                "timestamp": timestamp,
                                "original_url": original,
                                "status_code": status_int,
                                "mime_type": mimetype,
                                "digest": digest,
                                "length": int(length) if length and length.isdigit() else 0,
                                "capture_date": capture_date,
                                "wayback_url": f"{self.WAYBACK_BASE_URL}{timestamp}/{original}"
                            })
                    
                    return snapshots
                else:
                    logger.error(f"CDX API request failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error searching Wayback Machine: {str(e)}")
            return []
    
    async def get_domain_snapshots(
        self,
        domain: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: Optional[int] = 10000
    ) -> List[Dict[str, Any]]:
        """
        Get all snapshots for a domain
        
        Args:
            domain: Domain to search (e.g., "example.com")
            from_date: Start date for search
            to_date: End date for search
            limit: Maximum number of results
        
        Returns:
            List of snapshot dictionaries
        """
        # Ensure domain doesn't have protocol
        if domain.startswith(("http://", "https://")):
            domain = urlparse(domain).netloc
        
        return await self.search_snapshots(
            url=f"{domain}/*",
            from_date=from_date,
            to_date=to_date,
            match_type="domain",
            collapse="urlkey",  # Collapse by URL to get unique pages
            limit=limit
        )
    
    async def get_url_history(
        self,
        url: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: Optional[int] = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical snapshots of a specific URL
        
        Args:
            url: Specific URL to get history for
            from_date: Start date for search
            to_date: End date for search
            limit: Maximum number of results
        
        Returns:
            List of snapshot dictionaries sorted by capture date
        """
        snapshots = await self.search_snapshots(
            url=url,
            from_date=from_date,
            to_date=to_date,
            match_type="exact",
            collapse="timestamp:10",  # Collapse to daily snapshots
            limit=limit
        )
        
        # Sort by capture date
        snapshots.sort(key=lambda x: x["capture_date"])
        return snapshots
    
    async def fetch_wayback_content(
        self,
        wayback_url: str,
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch content from a Wayback Machine URL
        
        Args:
            wayback_url: Full Wayback Machine URL
            timeout: Request timeout in seconds
        
        Returns:
            Dictionary with content and metadata, or None if failed
        """
        session = await self.get_session()
        
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            async with session.get(wayback_url, timeout=timeout_obj) as response:
                if response.status == 200:
                    content = await response.text()
                    
                    return {
                        "content": content,
                        "status_code": response.status,
                        "content_type": response.headers.get("content-type", ""),
                        "content_length": len(content),
                        "wayback_url": wayback_url,
                        "fetched_at": datetime.utcnow()
                    }
                else:
                    logger.warning(f"Wayback content fetch failed: {response.status} for {wayback_url}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching Wayback content: {wayback_url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching Wayback content: {str(e)} for {wayback_url}")
            return None
    
    async def stream_domain_snapshots(
        self,
        domain: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        batch_size: int = 1000
    ) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """
        Stream snapshots for a domain in batches
        
        Args:
            domain: Domain to search
            from_date: Start date for search
            to_date: End date for search
            batch_size: Number of snapshots per batch
        
        Yields:
            Batches of snapshot dictionaries
        """
        offset = 0
        
        while True:
            # Get batch of snapshots
            snapshots = await self.search_snapshots(
                url=f"{domain}/*",
                from_date=from_date,
                to_date=to_date,
                match_type="domain",
                collapse="urlkey",
                limit=batch_size
            )
            
            if not snapshots:
                break
            
            yield snapshots
            
            # If we got fewer than batch_size, we're done
            if len(snapshots) < batch_size:
                break
            
            offset += batch_size
            
            # Add small delay to be respectful to the API
            await asyncio.sleep(0.1)
    
    def get_capture_years(
        self,
        snapshots: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Get unique years from a list of snapshots
        
        Args:
            snapshots: List of snapshot dictionaries
        
        Returns:
            Sorted list of unique years
        """
        years = set()
        for snapshot in snapshots:
            if "capture_date" in snapshot:
                years.add(snapshot["capture_date"].year)
        
        return sorted(list(years))
    
    def filter_snapshots_by_content_type(
        self,
        snapshots: List[Dict[str, Any]],
        content_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter snapshots by content type
        
        Args:
            snapshots: List of snapshot dictionaries
            content_types: List of MIME types to include (default: HTML types)
        
        Returns:
            Filtered list of snapshots
        """
        if content_types is None:
            content_types = ["text/html", "application/xhtml+xml"]
        
        filtered = []
        for snapshot in snapshots:
            mime_type = snapshot.get("mime_type", "").lower()
            if any(ct.lower() in mime_type for ct in content_types):
                filtered.append(snapshot)
        
        return filtered
    
    async def get_snapshot_availability(
        self,
        url: str,
        date_range_days: int = 30
    ) -> Dict[str, Any]:
        """
        Check snapshot availability for a URL over a date range
        
        Args:
            url: URL to check
            date_range_days: Number of days to check back from today
        
        Returns:
            Dictionary with availability information
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=date_range_days)
        
        snapshots = await self.search_snapshots(
            url=url,
            from_date=start_date,
            to_date=end_date,
            match_type="exact",
            limit=100
        )
        
        return {
            "url": url,
            "date_range_start": start_date,
            "date_range_end": end_date,
            "total_snapshots": len(snapshots),
            "first_snapshot": snapshots[0]["capture_date"] if snapshots else None,
            "last_snapshot": snapshots[-1]["capture_date"] if snapshots else None,
            "available": len(snapshots) > 0,
            "years_available": self.get_capture_years(snapshots)
        }


# Global service instance
wayback_service = WaybackMachineService()