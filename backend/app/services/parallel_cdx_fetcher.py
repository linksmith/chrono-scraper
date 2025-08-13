"""
Parallel CDX fetching system for high-performance Wayback Machine data retrieval
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from .wayback_machine import CDXAPIClient, CDXRecord, WaybackMachineException

logger = logging.getLogger(__name__)


@dataclass
class CDXFetchJob:
    """Individual CDX fetch job for parallel processing"""
    domain_name: str
    from_date: str
    to_date: str
    page_num: int
    page_size: int
    match_type: str = "domain"
    url_path: Optional[str] = None
    min_size: int = 200
    resume_key: Optional[str] = None


@dataclass
class CDXFetchResult:
    """Result from a CDX fetch operation"""
    job: CDXFetchJob
    success: bool
    records: List[CDXRecord] = None
    error: Optional[str] = None
    fetch_time: float = 0.0
    record_count: int = 0
    resume_key: Optional[str] = None
    
    def __post_init__(self):
        if self.records is None:
            self.records = []
        self.record_count = len(self.records)


class ParallelCDXFetcher:
    """High-performance parallel CDX fetching with intelligent batching"""
    
    def __init__(self, max_workers: int = 8, batch_size: int = 10):
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.domain_performance = {}  # Domain -> performance stats
        
        logger.info(f"Initialized ParallelCDXFetcher with {max_workers} workers, batch size {batch_size}")
    
    async def fetch_cdx_records_parallel(
        self, 
        domain_name: str, 
        from_date: str, 
        to_date: str,
        match_type: str = "domain", 
        url_path: Optional[str] = None,
        min_size: int = 200, 
        max_size: Optional[int] = None,
        page_size: int = 3000,
        max_pages: Optional[int] = None,
        existing_digests: Optional[Set[str]] = None,
        filter_list_pages: bool = True,
        resume_from_page: int = 0
    ) -> Tuple[List[CDXRecord], Dict[str, Any]]:
        """
        Fetch CDX records using parallel requests for maximum throughput.
        
        Args:
            domain_name: Domain name to query
            from_date: Start date in YYYYMMDD format
            to_date: End date in YYYYMMDD format
            match_type: CDX match type ('domain' or 'prefix')
            url_path: Optional URL path for prefix matching
            min_size: Minimum content size filter
            max_size: Maximum content size filter
            page_size: CDX pagination page size
            max_pages: Maximum pages to fetch
            existing_digests: Set of already processed digest hashes
            filter_list_pages: Whether to filter out list pages
            resume_from_page: Page number to resume from
            
        Returns:
            Tuple of (filtered_records, statistics)
        """
        start_time = time.time()
        
        logger.info(f"Starting parallel CDX fetch for {domain_name} from {from_date} to {to_date}")
        
        # First, determine total number of pages available
        async with CDXAPIClient() as client:
            total_pages = await client.get_page_count(
                domain_name, from_date, to_date, match_type, url_path, min_size
            )
        
        if total_pages == 0:
            logger.info(f"No CDX pages found for {domain_name}")
            return [], {
                "total_pages": 0,
                "fetched_pages": 0,
                "successful_batches": 0,
                "failed_batches": 0,
                "total_time": time.time() - start_time
            }
        
        # Respect max_pages limit and resume point
        pages_to_fetch = min(max_pages or total_pages, total_pages)
        start_page = max(0, resume_from_page)
        actual_pages = pages_to_fetch - start_page
        
        if actual_pages <= 0:
            logger.warning(f"No pages to fetch for {domain_name} (start: {start_page}, total: {pages_to_fetch})")
            return [], {"total_pages": total_pages, "fetched_pages": 0}
        
        logger.info(f"Fetching {actual_pages} CDX pages for {domain_name} (total: {total_pages}, starting from: {start_page})")
        
        # Create fetch jobs for parallel execution
        fetch_jobs = []
        for page_num in range(start_page, pages_to_fetch):
            job = CDXFetchJob(
                domain_name=domain_name,
                from_date=from_date,
                to_date=to_date,
                page_num=page_num,
                page_size=page_size,
                match_type=match_type,
                url_path=url_path,
                min_size=min_size
            )
            fetch_jobs.append(job)
        
        # Execute jobs in parallel batches
        all_records, batch_stats = await self._execute_parallel_fetches(fetch_jobs)
        
        # Apply comprehensive filtering
        filtered_records, filter_stats = await self._apply_filters(
            all_records, min_size, max_size, existing_digests, filter_list_pages
        )
        
        total_time = time.time() - start_time
        
        # Compile final statistics
        final_stats = {
            "total_pages": total_pages,
            "pages_to_fetch": actual_pages,
            "fetched_pages": batch_stats["successful_batches"],
            "failed_pages": batch_stats["failed_batches"],
            "total_records": len(all_records),
            "filtered_records": len(filtered_records),
            "total_time": total_time,
            "records_per_second": len(all_records) / total_time if total_time > 0 else 0,
            **filter_stats
        }
        
        # Record performance for optimization
        self._record_domain_performance(domain_name, final_stats)
        
        logger.info(f"Parallel CDX fetch complete for {domain_name}: "
                   f"{len(filtered_records)} final records in {total_time:.2f}s "
                   f"({final_stats['records_per_second']:.1f} records/s)")
        
        return filtered_records, final_stats
    
    async def _execute_parallel_fetches(self, fetch_jobs: List[CDXFetchJob]) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Execute CDX fetch jobs in parallel batches"""
        all_records = []
        successful_batches = 0
        failed_batches = 0
        
        # Process jobs in batches to avoid overwhelming the API
        for i in range(0, len(fetch_jobs), self.batch_size):
            batch = fetch_jobs[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (len(fetch_jobs) + self.batch_size - 1) // self.batch_size
            
            logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch)} jobs)")
            
            # Execute batch concurrently
            batch_results = await self._execute_batch(batch)
            
            # Collect results
            for result in batch_results:
                if result.success:
                    all_records.extend(result.records)
                    successful_batches += 1
                    logger.debug(f"Batch job succeeded: page {result.job.page_num}, "
                               f"{result.record_count} records in {result.fetch_time:.2f}s")
                else:
                    failed_batches += 1
                    logger.error(f"Batch job failed: page {result.job.page_num}, error: {result.error}")
            
            # Brief pause between batches to be respectful to the API
            if i + self.batch_size < len(fetch_jobs):
                await asyncio.sleep(0.5)
        
        stats = {
            "successful_batches": successful_batches,
            "failed_batches": failed_batches,
            "total_batches": successful_batches + failed_batches
        }
        
        logger.info(f"Parallel fetch completed: {successful_batches} successful, "
                   f"{failed_batches} failed, {len(all_records)} total records")
        
        return all_records, stats
    
    async def _execute_batch(self, batch: List[CDXFetchJob]) -> List[CDXFetchResult]:
        """Execute a single batch of CDX fetch jobs concurrently"""
        tasks = []
        
        for job in batch:
            task = asyncio.create_task(self._fetch_single_page(job))
            tasks.append(task)
        
        # Wait for all tasks in the batch to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results, handling exceptions
        batch_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create a failed result for the exception
                batch_results.append(CDXFetchResult(
                    job=batch[i],
                    success=False,
                    error=str(result)
                ))
            else:
                batch_results.append(result)
        
        return batch_results
    
    async def _fetch_single_page(self, job: CDXFetchJob) -> CDXFetchResult:
        """Fetch a single CDX page"""
        start_time = time.time()
        
        try:
            async with CDXAPIClient() as client:
                url = client._build_cdx_url(
                    job.domain_name, job.from_date, job.to_date,
                    job.match_type, job.url_path, job.min_size,
                    job.page_size, job.page_num, job.resume_key
                )
                
                response_text = await client._make_request(url)
                records = client._parse_cdx_response(response_text)
                
                fetch_time = time.time() - start_time
                
                return CDXFetchResult(
                    job=job,
                    success=True,
                    records=records,
                    fetch_time=fetch_time
                )
        
        except Exception as e:
            fetch_time = time.time() - start_time
            error_msg = f"Page {job.page_num} fetch failed: {str(e)}"
            
            return CDXFetchResult(
                job=job,
                success=False,
                error=error_msg,
                fetch_time=fetch_time
            )
    
    async def _apply_filters(
        self, 
        records: List[CDXRecord], 
        min_size: int, 
        max_size: Optional[int],
        existing_digests: Optional[Set[str]], 
        filter_list_pages: bool
    ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Apply comprehensive filtering to records"""
        from .wayback_machine import ContentSizeFilter, ListPageFilter, DuplicateFilter
        
        filter_stats = {
            "size_filtered": 0,
            "list_filtered": 0,
            "duplicate_filtered": 0,
            "initial_count": len(records)
        }
        
        filtered_records = records
        
        # 1. Size filtering
        if min_size > 0 or max_size:
            filtered_records, size_filtered = ContentSizeFilter.filter_by_size(
                filtered_records, min_size, max_size
            )
            filter_stats["size_filtered"] = size_filtered
        
        # 2. List page filtering
        if filter_list_pages:
            filtered_records, list_filtered = ListPageFilter.filter_records(filtered_records)
            filter_stats["list_filtered"] = list_filtered
        
        # 3. Duplicate filtering
        if existing_digests:
            filtered_records, duplicate_filtered = DuplicateFilter.filter_duplicates(
                filtered_records, existing_digests
            )
            filter_stats["duplicate_filtered"] = duplicate_filtered
        
        filter_stats["final_count"] = len(filtered_records)
        
        logger.info(f"Filtering complete: {filter_stats['initial_count']} -> {filter_stats['final_count']} "
                   f"(size: -{filter_stats['size_filtered']}, "
                   f"list: -{filter_stats['list_filtered']}, "
                   f"duplicates: -{filter_stats['duplicate_filtered']})")
        
        return filtered_records, filter_stats
    
    def _record_domain_performance(self, domain_name: str, stats: Dict[str, Any]):
        """Record performance statistics for domain optimization"""
        if domain_name not in self.domain_performance:
            self.domain_performance[domain_name] = {
                "total_fetches": 0,
                "total_records": 0,
                "total_time": 0,
                "avg_records_per_second": 0,
                "success_rates": []
            }
        
        perf = self.domain_performance[domain_name]
        perf["total_fetches"] += 1
        perf["total_records"] += stats["total_records"]
        perf["total_time"] += stats["total_time"]
        
        # Calculate success rate
        success_rate = stats["fetched_pages"] / max(1, stats["pages_to_fetch"]) * 100
        perf["success_rates"].append(success_rate)
        
        # Keep only recent success rates (last 10)
        if len(perf["success_rates"]) > 10:
            perf["success_rates"] = perf["success_rates"][-10:]
        
        # Update average
        perf["avg_records_per_second"] = perf["total_records"] / perf["total_time"] if perf["total_time"] > 0 else 0
    
    def get_domain_performance(self, domain_name: str) -> Optional[Dict[str, Any]]:
        """Get performance statistics for a domain"""
        return self.domain_performance.get(domain_name)
    
    def get_optimal_settings(self, domain_name: str) -> Dict[str, Any]:
        """Get optimal settings for a domain based on historical performance"""
        perf = self.domain_performance.get(domain_name)
        
        if not perf:
            # Default settings for new domains
            return {
                "page_size": 3000,
                "max_workers": 8,
                "batch_size": 10,
                "max_pages": 20
            }
        
        avg_success_rate = sum(perf["success_rates"]) / len(perf["success_rates"])
        avg_rps = perf["avg_records_per_second"]
        
        # Optimize based on performance
        if avg_success_rate > 95 and avg_rps > 50:
            # Excellent performance - aggressive settings
            return {
                "page_size": 5000,
                "max_workers": 12,
                "batch_size": 15,
                "max_pages": 100
            }
        elif avg_success_rate > 80 and avg_rps > 20:
            # Good performance - standard settings
            return {
                "page_size": 3000,
                "max_workers": 8,
                "batch_size": 10,
                "max_pages": 50
            }
        else:
            # Poor performance - conservative settings
            return {
                "page_size": 1000,
                "max_workers": 4,
                "batch_size": 5,
                "max_pages": 20
            }


# Global instance for reuse
parallel_fetcher = ParallelCDXFetcher()


async def fetch_cdx_records_parallel(
    domain_name: str,
    from_date: str, 
    to_date: str,
    match_type: str = "domain",
    url_path: Optional[str] = None,
    min_size: int = 200,
    max_pages: Optional[int] = None,
    existing_digests: Optional[Set[str]] = None,
    **kwargs
) -> Tuple[List[CDXRecord], Dict[str, Any]]:
    """
    High-level function for optimized parallel CDX fetching.
    
    Returns:
        Tuple of (filtered_records, statistics)
    """
    # Get optimal settings for this domain
    optimal_settings = parallel_fetcher.get_optimal_settings(domain_name)
    
    # Override with provided kwargs
    settings = {**optimal_settings, **kwargs}
    
    logger.info(f"Using optimized settings for {domain_name}: {settings}")
    
    return await parallel_fetcher.fetch_cdx_records_parallel(
        domain_name=domain_name,
        from_date=from_date,
        to_date=to_date,
        match_type=match_type,
        url_path=url_path,
        min_size=min_size,
        max_pages=max_pages,
        existing_digests=existing_digests,
        page_size=settings.get("page_size", 3000)
    )