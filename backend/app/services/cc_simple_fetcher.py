"""
Simplified Common Crawl fetcher aligned with the working Stoerwoud scripts.

- Uses direct index processing (cc-index/*.gz) to avoid CC index API outages
- Respects SmartProxy configuration for network access
"""
from typing import List, Tuple, Optional, Dict
import logging

from .wayback_machine import CDXRecord
from .common_crawl_direct_service import CommonCrawlDirectService

logger = logging.getLogger(__name__)


async def fetch_cc_cdx_records(
    domain_name: str,
    from_date: str,
    to_date: str,
    match_type: str = "domain",
    url_path: Optional[str] = None,
    page_size: int = 5000,
    max_pages: Optional[int] = None,
    include_attachments: bool = True,
) -> Tuple[List[CDXRecord], Dict[str, int]]:
    """
    Fetch CDX records for a domain using direct Common Crawl index processing (proxy-ready).
    Mirrors the approach used in the Stoerwoud scripts to avoid CC index API retries.
    """
    async with CommonCrawlDirectService() as service:
        records, stats = await service.fetch_cdx_records_simple(
            domain_name=domain_name,
            from_date=from_date,
            to_date=to_date,
            match_type=match_type,
            url_path=url_path,
            page_size=page_size,
            max_pages=max_pages,
            include_attachments=include_attachments,
        )
        logger.info(
            f"CC simple fetch complete for {domain_name}: {stats.get('final_count', len(records))} records"
        )
        return records, stats


__all__ = ["fetch_cc_cdx_records"]


