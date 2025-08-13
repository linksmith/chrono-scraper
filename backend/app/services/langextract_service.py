"""
LangExtract service for AI-powered content extraction
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
import json

from app.core.config import settings
from app.models.project import Project, LangExtractProvider
from app.services.cdx_service import cdx_service

logger = logging.getLogger(__name__)


@dataclass
class OpenRouterModel:
    """OpenRouter model information with pricing"""
    id: str
    name: str
    description: str
    pricing_input: float  # Cost per 1M input tokens
    pricing_output: float  # Cost per 1M output tokens
    context_length: int
    provider: str


class LangExtractCostCalculator:
    """Calculate cost estimates for LangExtract processing"""
    
    # OpenRouter model pricing (cost per 1M tokens)
    OPENROUTER_MODELS = {
        "anthropic/claude-3.5-sonnet": OpenRouterModel(
            id="anthropic/claude-3.5-sonnet",
            name="Claude 3.5 Sonnet",
            description="Best balance of intelligence and speed",
            pricing_input=3.0,   # $3 per 1M input tokens
            pricing_output=15.0, # $15 per 1M output tokens
            context_length=200000,
            provider="Anthropic"
        ),
        "anthropic/claude-3-haiku": OpenRouterModel(
            id="anthropic/claude-3-haiku",
            name="Claude 3 Haiku",
            description="Fastest and most cost-effective",
            pricing_input=0.25,  # $0.25 per 1M input tokens
            pricing_output=1.25, # $1.25 per 1M output tokens
            context_length=200000,
            provider="Anthropic"
        ),
        "openai/gpt-4o": OpenRouterModel(
            id="openai/gpt-4o",
            name="GPT-4o",
            description="High intelligence with vision capabilities",
            pricing_input=2.5,   # $2.5 per 1M input tokens
            pricing_output=10.0, # $10 per 1M output tokens
            context_length=128000,
            provider="OpenAI"
        ),
        "openai/gpt-4o-mini": OpenRouterModel(
            id="openai/gpt-4o-mini",
            name="GPT-4o mini",
            description="Affordable and intelligent small model",
            pricing_input=0.15,  # $0.15 per 1M input tokens
            pricing_output=0.6,  # $0.6 per 1M output tokens
            context_length=128000,
            provider="OpenAI"
        ),
        "google/gemini-2.0-flash-exp": OpenRouterModel(
            id="google/gemini-2.0-flash-exp",
            name="Gemini 2.0 Flash",
            description="Google's latest fast model",
            pricing_input=0.075, # $0.075 per 1M input tokens
            pricing_output=0.3,  # $0.3 per 1M output tokens
            context_length=1000000,
            provider="Google"
        ),
        "meta-llama/llama-3.2-90b-vision-instruct": OpenRouterModel(
            id="meta-llama/llama-3.2-90b-vision-instruct",
            name="Llama 3.2 90B Vision",
            description="Open source vision-capable model",
            pricing_input=0.9,   # $0.9 per 1M input tokens
            pricing_output=0.9,  # $0.9 per 1M output tokens
            context_length=131072,
            provider="Meta"
        ),
        "qwen/qwen-2.5-72b-instruct": OpenRouterModel(
            id="qwen/qwen-2.5-72b-instruct",
            name="Qwen 2.5 72B",
            description="High-performance Chinese model",
            pricing_input=0.4,   # $0.4 per 1M input tokens
            pricing_output=0.4,  # $0.4 per 1M output tokens
            context_length=32768,
            provider="Alibaba"
        )
    }
    
    # Estimation constants
    AVG_PAGE_TOKENS = 2000      # Average tokens per page
    EXTRACTION_OVERHEAD = 1.5   # Multiplier for extraction complexity
    OUTPUT_TOKENS_RATIO = 0.1   # Output tokens as ratio of input tokens
    
    @classmethod
    def get_available_models(cls) -> List[OpenRouterModel]:
        """Get list of available OpenRouter models with pricing"""
        return list(cls.OPENROUTER_MODELS.values())
    
    @classmethod
    def get_model_info(cls, model_id: str) -> Optional[OpenRouterModel]:
        """Get model information by ID"""
        return cls.OPENROUTER_MODELS.get(model_id)
    
    @classmethod
    def calculate_cost_per_1k_pages(cls, model_id: str) -> Optional[float]:
        """Calculate estimated cost per 1000 pages for a model"""
        model = cls.get_model_info(model_id)
        if not model:
            return None
        
        # Calculate tokens for 1000 pages
        input_tokens = 1000 * cls.AVG_PAGE_TOKENS * cls.EXTRACTION_OVERHEAD
        output_tokens = input_tokens * cls.OUTPUT_TOKENS_RATIO
        
        # Calculate cost
        input_cost = (input_tokens / 1_000_000) * model.pricing_input
        output_cost = (output_tokens / 1_000_000) * model.pricing_output
        
        total_cost = input_cost + output_cost
        return round(total_cost, 3)
    
    @classmethod
    def calculate_project_cost_estimate(
        cls, 
        model_id: str, 
        estimated_pages: int
    ) -> Optional[Dict[str, Any]]:
        """Calculate cost estimate for a project"""
        model = cls.get_model_info(model_id)
        if not model:
            return None
        
        cost_per_1k = cls.calculate_cost_per_1k_pages(model_id)
        if not cost_per_1k:
            return None
        
        total_cost = (estimated_pages / 1000) * cost_per_1k
        
        return {
            "model": model,
            "estimated_pages": estimated_pages,
            "cost_per_1k_pages": cost_per_1k,
            "total_estimated_cost": round(total_cost, 2),
            "breakdown": {
                "input_tokens": estimated_pages * cls.AVG_PAGE_TOKENS * cls.EXTRACTION_OVERHEAD,
                "output_tokens": estimated_pages * cls.AVG_PAGE_TOKENS * cls.EXTRACTION_OVERHEAD * cls.OUTPUT_TOKENS_RATIO,
                "input_cost": round((estimated_pages * cls.AVG_PAGE_TOKENS * cls.EXTRACTION_OVERHEAD / 1_000_000) * model.pricing_input, 3),
                "output_cost": round((estimated_pages * cls.AVG_PAGE_TOKENS * cls.EXTRACTION_OVERHEAD * cls.OUTPUT_TOKENS_RATIO / 1_000_000) * model.pricing_output, 3)
            }
        }


class LangExtractService:
    """Service for LangExtract integration with OpenRouter and comprehensive cost estimation"""
    
    def __init__(self):
        self.calculator = LangExtractCostCalculator()
        self._redis_client = None
        
        # Cache settings (in seconds)
        self.CACHE_SETTINGS = {
            'cdx_page_count': 24 * 60 * 60,  # 24 hours
            'cost_estimates': 60 * 60,  # 1 hour
            'domain_validation': 6 * 60 * 60,  # 6 hours
        }
        
        # Processing time estimates (seconds)
        self.PROCESSING_TIME_ESTIMATES = {
            'cdx_discovery_per_domain': 3,
            'firecrawl_per_page_base': 4,
            'firecrawl_network_overhead': 1.5,
            'extraction_per_page': 1.2,
            'parallel_factor': 0.7,  # 30% reduction due to parallel processing
        }
    
    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client for caching"""
        if not self._redis_client:
            try:
                self._redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True
                )
                # Test connection
                await self._redis_client.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._redis_client = None
        
        return self._redis_client
    
    async def _cache_get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            redis_client = await self._get_redis_client()
            if redis_client:
                value = await redis_client.get(key)
                if value:
                    return json.loads(value)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        return None
    
    async def _cache_set(self, key: str, value: Any, timeout: int):
        """Set value in cache"""
        try:
            redis_client = await self._get_redis_client()
            if redis_client:
                await redis_client.setex(key, timeout, json.dumps(value, default=str))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available models with cost estimates"""
        models = []
        for model in self.calculator.get_available_models():
            cost_per_1k = self.calculator.calculate_cost_per_1k_pages(model.id)
            models.append({
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "provider": model.provider,
                "context_length": model.context_length,
                "pricing": {
                    "input_per_1m": model.pricing_input,
                    "output_per_1m": model.pricing_output,
                    "estimated_per_1k_pages": cost_per_1k
                }
            })
        
        # Sort by cost (cheapest first)
        return sorted(models, key=lambda x: x["pricing"]["estimated_per_1k_pages"])
    
    async def validate_model_selection(
        self, 
        provider: LangExtractProvider, 
        model_id: str
    ) -> bool:
        """Validate model selection for provider"""
        if provider == LangExtractProvider.DISABLED:
            return True
        
        if provider == LangExtractProvider.OPENROUTER:
            return model_id in self.calculator.OPENROUTER_MODELS
        
        # Add validation for other providers as needed
        return False
    
    async def calculate_project_cost(
        self, 
        model_id: str, 
        estimated_pages: int
    ) -> Optional[Dict[str, Any]]:
        """Calculate cost estimate for a project"""
        return self.calculator.calculate_project_cost_estimate(model_id, estimated_pages)
    
    async def estimate_project_costs(
        self,
        domain_name: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        extraction_enabled: bool = False,
        model_name: Optional[str] = None,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive project cost estimation with CDX integration
        
        Args:
            domain_name: Domain to scrape
            from_date: Start date in YYYYMMDD format (optional)
            to_date: End date in YYYYMMDD format (optional)
            extraction_enabled: Whether JSON metadata extraction is enabled
            model_name: OpenRouter model to use for extraction
            match_type: Type of matching ("domain" or "prefix")
            url_path: Optional URL path filter
            
        Returns:
            Dictionary with comprehensive cost breakdown and estimates
        """
        # Validate inputs
        if not domain_name:
            raise ValueError("Domain name is required")
        
        # Clean domain name
        domain_name = self._clean_domain_name(domain_name)
        
        # Set date defaults
        if not from_date:
            from_date = "19900101"
        if not to_date:
            to_date = datetime.now().strftime("%Y%m%d")
        
        # Set model default
        if not model_name:
            model_name = "anthropic/claude-3-haiku"
        
        # Create cache key
        cache_key = f"cost_estimate:{domain_name}:{from_date}:{to_date}:{extraction_enabled}:{model_name}:{match_type}:{url_path}"
        
        # Try to get from cache
        cached_result = await self._cache_get(cache_key)
        if cached_result:
            logger.info(f"Returning cached cost estimate for {domain_name}")
            return cached_result
        
        try:
            # Get page count estimate using CDX API
            async with cdx_service as cdx:
                page_count = await cdx.get_page_count(
                    domain=domain_name,
                    from_date=from_date,
                    to_date=to_date,
                    match_type=match_type,
                    url_path=url_path
                )
            
            if page_count == 0:
                return self._create_no_data_response(domain_name)
            
            # Calculate costs and time
            openrouter_cost = self.calculate_openrouter_costs(page_count, extraction_enabled, model_name)
            time_estimate = self.estimate_processing_time(page_count, extraction_enabled)
            
            # Create response
            result = {
                'domain_name': domain_name,
                'date_range': {
                    'from_date': from_date,
                    'to_date': to_date,
                    'formatted': self._format_date_range(from_date, to_date)
                },
                'match_type': match_type,
                'url_path': url_path,
                'page_count': page_count,
                'extraction_enabled': extraction_enabled,
                'model_name': model_name,
                'costs': {
                    'firecrawl_local': {
                        'amount': 0.0,
                        'currency': 'USD',
                        'description': 'Local Firecrawl (self-hosted)'
                    },
                    'openrouter_api': openrouter_cost,
                    'total': openrouter_cost['amount']
                },
                'time_estimate': time_estimate,
                'warnings': self._generate_warnings(page_count, time_estimate, openrouter_cost),
                'last_updated': datetime.now().isoformat()
            }
            
            # Cache the result
            await self._cache_set(cache_key, result, self.CACHE_SETTINGS['cost_estimates'])
            
            logger.info(f"Generated cost estimate for {domain_name}: {page_count} pages, ${result['costs']['total']:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Error estimating costs for {domain_name}: {str(e)}")
            return self._create_error_response(domain_name, str(e))
    
    async def get_cdx_page_count(
        self, 
        domain_name: str, 
        from_date: str, 
        to_date: str,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> int:
        """
        Get CDX page count with caching
        """
        cache_key = f"cdx_count:{domain_name}:{from_date}:{to_date}:{match_type}:{url_path}"
        
        # Try cache first
        cached_count = await self._cache_get(cache_key)
        if cached_count is not None:
            logger.debug(f"Using cached page count for {domain_name}: {cached_count}")
            return cached_count
        
        try:
            # Use CDX service to get page count
            async with cdx_service as cdx:
                page_count = await cdx.get_page_count(
                    domain=domain_name,
                    from_date=from_date,
                    to_date=to_date,
                    match_type=match_type,
                    url_path=url_path
                )
            
            # Cache the result
            await self._cache_set(cache_key, page_count, self.CACHE_SETTINGS['cdx_page_count'])
            
            logger.info(f"CDX page count for {domain_name}: {page_count} pages")
            return page_count
            
        except Exception as e:
            logger.error(f"Error getting CDX page count for {domain_name}: {str(e)}")
            return 0
    
    def calculate_openrouter_costs(
        self, 
        page_count: int, 
        extraction_enabled: bool, 
        model_name: str = None
    ) -> Dict[str, Any]:
        """
        Calculate OpenRouter API costs for extraction
        """
        if not extraction_enabled or page_count == 0:
            return {
                'amount': 0.0,
                'currency': 'USD',
                'description': 'No extraction enabled',
                'breakdown': {
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'input_cost': 0.0,
                    'output_cost': 0.0
                }
            }
        
        if not model_name:
            model_name = "anthropic/claude-3-haiku"
        
        # Get pricing info
        model_info = self.calculator.get_model_info(model_name)
        if not model_info:
            model_info = self.calculator.get_model_info("anthropic/claude-3-haiku")
        
        # Calculate token usage
        total_input_tokens = page_count * self.calculator.AVG_PAGE_TOKENS * self.calculator.EXTRACTION_OVERHEAD
        total_output_tokens = total_input_tokens * self.calculator.OUTPUT_TOKENS_RATIO
        
        # Calculate costs
        input_cost = (total_input_tokens / 1_000_000) * model_info.pricing_input
        output_cost = (total_output_tokens / 1_000_000) * model_info.pricing_output
        total_cost = input_cost + output_cost
        
        return {
            'amount': round(total_cost, 3),
            'currency': 'USD',
            'description': f'OpenRouter API ({model_info.name})',
            'breakdown': {
                'model': model_info.name,
                'input_tokens': int(total_input_tokens),
                'output_tokens': int(total_output_tokens),
                'input_cost': round(input_cost, 3),
                'output_cost': round(output_cost, 3),
                'pages_processed': page_count
            }
        }
    
    def estimate_processing_time(self, page_count: int, extraction_enabled: bool) -> Dict[str, Any]:
        """
        Estimate total processing time
        """
        if page_count == 0:
            return {
                'total_seconds': 0,
                'formatted': '0 seconds',
                'range': '0 seconds',
                'breakdown': {}
            }
        
        # Base time calculations
        cdx_time = self.PROCESSING_TIME_ESTIMATES['cdx_discovery_per_domain']
        firecrawl_base = page_count * self.PROCESSING_TIME_ESTIMATES['firecrawl_per_page_base']
        network_overhead = page_count * self.PROCESSING_TIME_ESTIMATES['firecrawl_network_overhead']
        extraction_time = page_count * self.PROCESSING_TIME_ESTIMATES['extraction_per_page'] if extraction_enabled else 0
        
        # Apply parallel processing factor
        processing_time = (firecrawl_base + network_overhead + extraction_time) * self.PROCESSING_TIME_ESTIMATES['parallel_factor']
        total_time = cdx_time + processing_time
        
        # Calculate range (±25%)
        min_time = total_time * 0.75
        max_time = total_time * 1.25
        
        return {
            'total_seconds': int(total_time),
            'formatted': self._format_duration(total_time),
            'range': f"{self._format_duration(min_time)} - {self._format_duration(max_time)}",
            'breakdown': {
                'cdx_discovery': int(cdx_time),
                'firecrawl_processing': int(firecrawl_base * self.PROCESSING_TIME_ESTIMATES['parallel_factor']),
                'network_overhead': int(network_overhead * self.PROCESSING_TIME_ESTIMATES['parallel_factor']),
                'extraction': int(extraction_time * self.PROCESSING_TIME_ESTIMATES['parallel_factor']) if extraction_enabled else 0,
                'parallel_efficiency': f"{int((1 - self.PROCESSING_TIME_ESTIMATES['parallel_factor']) * 100)}%"
            }
        }
    
    async def validate_domain(
        self,
        domain_name: str,
        quick_check: bool = True
    ) -> Dict[str, Any]:
        """
        Validate domain and check if it has archived data
        """
        domain_name = self._clean_domain_name(domain_name)
        
        # Create cache key
        cache_key = f"domain_validation:{domain_name}:{quick_check}"
        
        # Try cache first
        cached_result = await self._cache_get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # Use CDX service for validation
            async with cdx_service as cdx:
                result = await cdx.validate_domain(domain_name, quick_check)
            
            # Cache the result
            await self._cache_set(cache_key, result, self.CACHE_SETTINGS['domain_validation'])
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating domain {domain_name}: {str(e)}")
            return {
                'domain_name': domain_name,
                'is_valid': False,
                'has_archived_data': False,
                'page_count': 0,
                'error': str(e),
                'recommendation': 'Unable to validate domain'
            }
    
    async def extract_from_content(
        self, 
        content: str, 
        schema: Dict[str, Any],
        model_config: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Extract structured data from content using LangExtract
        
        Note: This is a placeholder for actual LangExtract integration
        which would require the langextract package to be installed
        """
        # TODO: Implement actual LangExtract integration
        # For now, return mock data
        return {
            "entities": [],
            "relationships": [],
            "summary": "LangExtract integration not yet implemented",
            "confidence": 0.0,
            "processing_time": 0.0,
            "token_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0
            }
        }
    
    async def estimate_pages_from_domains(
        self, 
        domains: List[str]
    ) -> int:
        """
        Estimate number of pages from domain list using CDX API
        """
        total_pages = 0
        
        for domain in domains:
            try:
                # Get page count for last year as estimate
                last_year = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
                current_date = datetime.now().strftime("%Y%m%d")
                
                page_count = await self.get_cdx_page_count(domain, last_year, current_date)
                total_pages += page_count
                
            except Exception as e:
                logger.warning(f"Could not estimate pages for domain {domain}: {e}")
                # Fallback to rough estimate
                total_pages += 500
        
        return max(100, total_pages)
    
    def _clean_domain_name(self, domain_name: str) -> str:
        """Clean and normalize domain name"""
        domain_name = domain_name.strip().lower()
        # Remove protocol if present
        if domain_name.startswith(('http://', 'https://')):
            domain_name = domain_name.split('://', 1)[1]
        # Remove www prefix
        if domain_name.startswith('www.'):
            domain_name = domain_name[4:]
        # Remove trailing slash
        domain_name = domain_name.rstrip('/')
        return domain_name
    
    def _format_date_range(self, from_date: str, to_date: str) -> str:
        """Format date range for display"""
        try:
            from_dt = datetime.strptime(from_date, "%Y%m%d").strftime("%Y-%m-%d")
            to_dt = datetime.strptime(to_date, "%Y%m%d").strftime("%Y-%m-%d")
            return f"{from_dt} to {to_dt}"
        except:
            return f"{from_date} to {to_date}"
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in a human-readable way"""
        seconds = int(seconds)
        
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}m {remaining_seconds}s"
            return f"{minutes} minutes"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            if remaining_minutes > 0:
                return f"{hours}h {remaining_minutes}m"
            return f"{hours} hours"
    
    def _generate_warnings(self, page_count: int, time_estimate: Dict, cost_estimate: Dict) -> List[str]:
        """Generate warnings based on estimates"""
        warnings = []
        
        # Large page count warning
        if page_count > 1000:
            warnings.append(f"Large domain with {page_count:,} pages - consider date range filtering")
        
        # Long processing time warning
        if time_estimate['total_seconds'] > 3600:  # > 1 hour
            warnings.append(f"Processing will take {time_estimate['formatted']} - consider running during off-hours")
        
        # High cost warning
        if cost_estimate['amount'] > 5.0:
            warnings.append(f"Extraction costs ${cost_estimate['amount']:.2f} - consider disabling for initial testing")
        
        # Very small domain warning
        if page_count < 10:
            warnings.append("Small domain - results may be limited")
        
        return warnings
    
    def _create_no_data_response(self, domain_name: str) -> Dict[str, Any]:
        """Create response for domains with no data"""
        return {
            'domain_name': domain_name,
            'page_count': 0,
            'costs': {
                'firecrawl_local': {'amount': 0.0, 'currency': 'USD', 'description': 'No pages to process'},
                'openrouter_api': {'amount': 0.0, 'currency': 'USD', 'description': 'No pages to process'},
                'total': 0.0
            },
            'time_estimate': {
                'total_seconds': 0,
                'formatted': '0 seconds',
                'range': '0 seconds'
            },
            'warnings': ['No archived pages found for this domain and date range'],
            'error': 'no_data',
            'last_updated': datetime.now().isoformat()
        }
    
    def _create_error_response(self, domain_name: str, error_message: str) -> Dict[str, Any]:
        """Create response for errors"""
        return {
            'domain_name': domain_name,
            'page_count': None,
            'costs': None,
            'time_estimate': None,
            'warnings': [],
            'error': error_message,
            'last_updated': datetime.now().isoformat()
        }


# Export the service instance
langextract_service = LangExtractService()