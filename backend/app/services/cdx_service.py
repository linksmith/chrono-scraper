"""
CDX API service for getting Wayback Machine page counts and data
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)


class CDXService:
    """Service for interacting with the Wayback Machine CDX API"""
    
    CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
    DEFAULT_TIMEOUT = 30
    DEFAULT_MIN_SIZE = 200
    MAX_RETRIES = 3
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def get_page_count(
        self,
        domain: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        min_size: int = DEFAULT_MIN_SIZE,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> int:
        """
        Get page count for a domain from CDX API
        
        Args:
            domain: Domain to query (e.g., "example.com")
            from_date: Start date in YYYYMMDD format
            to_date: End date in YYYYMMDD format  
            min_size: Minimum page size in bytes
            match_type: Type of matching ("domain" or "prefix")
            url_path: Optional URL path filter
            
        Returns:
            Number of pages available
        """
        # Clean domain
        domain = self._clean_domain(domain)
        
        # Set date defaults
        if not from_date:
            from_date = "19900101"
        if not to_date:
            to_date = datetime.now().strftime("%Y%m%d")
        
        # Build URL based on match type
        if match_type == "prefix" and url_path:
            url = f"{domain}{url_path}*"
        else:
            url = f"*.{domain}/*"
        
        params = {
            "url": url,
            "from": from_date,
            "to": to_date,
            "output": "json",
            "fl": "timestamp",
            "filter": [
                "!statuscode:[45]..",  # Exclude 4xx and 5xx errors
                "!mimetype:warc/revisit",  # Exclude revisit records
                f"length:{min_size}-",  # Minimum size filter
            ],
            "collapse": "urlkey",  # Collapse duplicate URLs
            "showNumPages": "true"
        }
        
        try:
            return await self._make_request(params)
            
        except Exception as e:
            logger.error(f"Error getting page count for {domain}: {e}")
            return 0
    
    async def get_page_samples(
        self,
        domain: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
        min_size: int = DEFAULT_MIN_SIZE,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get sample pages for a domain
        
        Returns:
            List of page records with metadata
        """
        # Clean domain
        domain = self._clean_domain(domain)
        
        # Set date defaults
        if not from_date:
            from_date = "19900101" 
        if not to_date:
            to_date = datetime.now().strftime("%Y%m%d")
        
        # Build URL based on match type
        if match_type == "prefix" and url_path:
            url = f"{domain}{url_path}*"
        else:
            url = f"*.{domain}/*"
        
        params = {
            "url": url,
            "from": from_date,
            "to": to_date,
            "output": "json",
            "fl": "timestamp,original,statuscode,length,mimetype",
            "filter": [
                "!statuscode:[45]..",
                "!mimetype:warc/revisit",
                f"length:{min_size}-",
            ],
            "collapse": "urlkey",
            "limit": limit
        }
        
        try:
            if not self.session:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
                ) as session:
                    return await self._get_sample_data(session, params)
            else:
                return await self._get_sample_data(self.session, params)
                
        except Exception as e:
            logger.error(f"Error getting page samples for {domain}: {e}")
            return []
    
    async def validate_domain(
        self,
        domain: str,
        quick_check: bool = True
    ) -> Dict[str, Any]:
        """
        Validate domain and check if it has archived data
        
        Args:
            domain: Domain to validate
            quick_check: If True, only check last year of data
            
        Returns:
            Validation result with metadata
        """
        domain = self._clean_domain(domain)
        
        if quick_check:
            # Quick validation - check last year
            last_year = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            current_date = datetime.now().strftime("%Y%m%d")
            from_date = last_year
            to_date = current_date
        else:
            # Full validation - check all time
            from_date = "19900101"
            to_date = datetime.now().strftime("%Y%m%d")
        
        try:
            page_count = await self.get_page_count(
                domain, from_date, to_date, min_size=100
            )
            
            # Get some sample pages for additional info
            samples = await self.get_page_samples(
                domain, from_date, to_date, limit=10
            )
            
            # Analyze sample data
            content_types = {}
            date_range = {"earliest": None, "latest": None}
            
            for sample in samples:
                # Count content types
                mime_type = sample.get("mimetype", "unknown")
                content_types[mime_type] = content_types.get(mime_type, 0) + 1
                
                # Track date range
                timestamp = sample.get("timestamp")
                if timestamp:
                    try:
                        date = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                        if not date_range["earliest"] or date < date_range["earliest"]:
                            date_range["earliest"] = date
                        if not date_range["latest"] or date > date_range["latest"]:
                            date_range["latest"] = date
                    except ValueError:
                        pass
            
            return {
                "domain": domain,
                "is_valid": True,
                "has_archived_data": page_count > 0,
                "page_count": page_count,
                "date_range_tested": f"{from_date} to {to_date}",
                "sample_count": len(samples),
                "content_types": content_types,
                "archive_date_range": {
                    "earliest": date_range["earliest"].isoformat() if date_range["earliest"] else None,
                    "latest": date_range["latest"].isoformat() if date_range["latest"] else None
                },
                "recommendation": (
                    "Valid domain with archived data" if page_count > 0 
                    else "Valid domain but no archived data found"
                )
            }
            
        except Exception as e:
            logger.error(f"Error validating domain {domain}: {e}")
            return {
                "domain": domain,
                "is_valid": False,
                "has_archived_data": False,
                "page_count": 0,
                "error": str(e),
                "recommendation": "Unable to validate domain"
            }
    
    async def _make_request(self, params: Dict[str, Any]) -> int:
        """Make CDX API request and parse page count"""
        if not self.session:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
            ) as session:
                return await self._execute_request(session, params)
        else:
            return await self._execute_request(self.session, params)
    
    async def _execute_request(self, session: aiohttp.ClientSession, params: Dict[str, Any]) -> int:
        """Execute CDX request with retry logic"""
        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.get(self.CDX_API_URL, params=params) as response:
                    if response.status == 200:
                        text = await response.text()
                        return self._parse_page_count(text)
                    elif response.status == 400:
                        # Bad request - likely invalid domain/parameters
                        logger.warning(f"CDX API bad request: {response.status}")
                        return 0
                    else:
                        logger.warning(f"CDX API returned status {response.status}")
                        if attempt < self.MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        
            except aiohttp.ClientError as e:
                logger.warning(f"CDX API request failed (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Unexpected error in CDX request: {e}")
                break
        
        return 0
    
    async def _get_sample_data(self, session: aiohttp.ClientSession, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get sample data from CDX API"""
        try:
            async with session.get(self.CDX_API_URL, params=params) as response:
                if response.status == 200:
                    text = await response.text()
                    return self._parse_sample_data(text)
                else:
                    logger.warning(f"CDX API returned status {response.status}")
                    
        except Exception as e:
            logger.error(f"Error getting sample data: {e}")
        
        return []
    
    def _parse_page_count(self, response_text: str) -> int:
        """Parse page count from CDX API response"""
        try:
            lines = response_text.strip().split('\n')
            if not lines:
                return 0
            
            # First line should contain the count
            first_line = lines[0]
            if first_line.startswith('["'):
                # JSON format response header, actual count is number of subsequent lines
                return len(lines) - 1
            else:
                # Try to parse as number
                try:
                    return int(first_line)
                except ValueError:
                    # Count non-empty lines
                    return len([line for line in lines if line.strip()])
                    
        except Exception as e:
            logger.error(f"Error parsing page count: {e}")
            return 0
    
    def _parse_sample_data(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse sample data from CDX API response"""
        try:
            import json
            lines = response_text.strip().split('\n')
            
            if not lines:
                return []
            
            # Check if first line is JSON header
            header = None
            data_lines = lines
            
            try:
                header = json.loads(lines[0])
                if isinstance(header, list):
                    data_lines = lines[1:]
                else:
                    header = None
            except json.JSONDecodeError:
                pass
            
            samples = []
            for line in data_lines:
                if not line.strip():
                    continue
                    
                try:
                    data = json.loads(line)
                    if isinstance(data, list) and len(data) >= 5:
                        sample = {
                            "timestamp": data[0],
                            "original": data[1], 
                            "statuscode": data[2],
                            "length": data[3],
                            "mimetype": data[4]
                        }
                        samples.append(sample)
                except json.JSONDecodeError:
                    # Try parsing as space-separated values
                    parts = line.split()
                    if len(parts) >= 5:
                        sample = {
                            "timestamp": parts[0],
                            "original": parts[1],
                            "statuscode": parts[2], 
                            "length": parts[3],
                            "mimetype": parts[4]
                        }
                        samples.append(sample)
            
            return samples
            
        except Exception as e:
            logger.error(f"Error parsing sample data: {e}")
            return []
    
    def _clean_domain(self, domain: str) -> str:
        """Clean and normalize domain name"""
        domain = domain.strip().lower()
        
        # Remove protocol if present
        if domain.startswith(('http://', 'https://')):
            domain = domain.split('://', 1)[1]
        
        # Remove www prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Remove trailing slash and path
        domain = domain.split('/')[0]
        
        return domain


# Global service instance
cdx_service = CDXService()