"""
Content extraction service with BeautifulSoup and robust error handling
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from io import BytesIO
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup, Comment
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from ..core.config import settings
from .wayback_machine import CDXRecord

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("pdfplumber not available, PDF extraction disabled")


class ContentExtractionException(Exception):
    """Base exception for content extraction errors"""
    pass


class UnsupportedContentTypeException(ContentExtractionException):
    """Content type is not supported for extraction"""
    pass


class ContentTooLargeException(ContentExtractionException):
    """Content is too large to process"""
    pass


@dataclass
class ExtractedContent:
    """Container for extracted content data"""
    title: str
    text: str
    markdown: str
    html: str
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    language: Optional[str] = None
    word_count: int = 0
    character_count: int = 0
    extraction_method: str = "unknown"
    extraction_time: float = 0.0
    
    def __post_init__(self):
        """Calculate derived fields"""
        if self.text:
            self.word_count = len(self.text.split())
            self.character_count = len(self.text)


class PDFExtractor:
    """PDF content extraction using pdfplumber"""
    
    @staticmethod
    def extract_pdf_content(pdf_bytes: bytes) -> Tuple[str, str]:
        """
        Extract content from PDF bytes.
        
        Args:
            pdf_bytes: Raw PDF content as bytes
            
        Returns:
            Tuple of (title, text_content)
        """
        if not PDF_AVAILABLE:
            raise ContentExtractionException("PDF extraction not available (pdfplumber not installed)")
        
        title = "No Title"
        content = ""
        
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                # Extract text from all pages
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                
                content = "\n\n".join(text_parts)
                
                # Try to get title from metadata
                if pdf.metadata and "Title" in pdf.metadata:
                    title = pdf.metadata["Title"] or "No Title"
                
        except Exception as e:
            logger.error(f"PDF extraction failed: {str(e)}")
            raise ContentExtractionException(f"PDF extraction failed: {str(e)}")
        
        return title, content


class HTMLExtractor:
    """HTML content extraction using BeautifulSoup"""
    
    # Tags to remove completely (with content)
    REMOVE_TAGS = [
        'script', 'style', 'nav', 'header', 'footer', 'aside', 
        'menu', 'menuitem', 'noscript', 'object', 'embed', 
        'iframe', 'frame', 'frameset', 'canvas'
    ]
    
    # Tags that typically contain main content
    CONTENT_TAGS = [
        'article', 'main', 'section', 'div', 'p', 'h1', 'h2', 
        'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code'
    ]
    
    # Common class/id patterns for main content
    CONTENT_SELECTORS = [
        '[role="main"]',
        'main',
        'article',
        '#content', '#main', '#primary', '#post', '#article',
        '.content', '.main', '.primary', '.post', '.article',
        '.entry-content', '.post-content', '.article-content',
        '.content-body', '.main-content'
    ]
    
    # Patterns to exclude (ads, navigation, etc.)
    EXCLUDE_SELECTORS = [
        'nav', 'header', 'footer', 'aside',
        '.nav', '.navigation', '.menu', '.sidebar',
        '.ad', '.ads', '.advertisement', '.social', '.share',
        '.comments', '.comment', '.related', '.recommended'
    ]
    
    @classmethod
    def clean_html(cls, html: str) -> BeautifulSoup:
        """Clean and prepare HTML for extraction"""
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # Remove unwanted tags
        for tag_name in cls.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        return soup
    
    @classmethod
    def extract_metadata(cls, soup: BeautifulSoup) -> Dict[str, Optional[str]]:
        """Extract metadata from HTML"""
        metadata = {
            'title': None,
            'description': None,
            'keywords': None,
            'author': None,
            'published_date': None,
            'language': None
        }
        
        # Title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)
        
        # Meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            property_attr = meta.get('property', '').lower()
            content = meta.get('content', '').strip()
            
            if not content:
                continue
            
            # Description
            if name in ['description', 'og:description'] or property_attr == 'og:description':
                metadata['description'] = content
            
            # Keywords
            elif name == 'keywords':
                metadata['keywords'] = content
            
            # Author
            elif name in ['author', 'article:author'] or property_attr in ['article:author', 'og:author']:
                metadata['author'] = content
            
            # Published date
            elif name in ['date', 'published', 'article:published_time'] or property_attr == 'article:published_time':
                metadata['published_date'] = content
        
        # Language
        html_tag = soup.find('html')
        if html_tag:
            lang = html_tag.get('lang') or html_tag.get('xml:lang')
            if lang:
                metadata['language'] = lang.split('-')[0].lower()  # Extract primary language
        
        return metadata
    
    @classmethod
    def extract_main_content(cls, soup: BeautifulSoup) -> str:
        """Extract main content text from HTML"""
        content_parts = []
        
        # Try content selectors first
        main_content = None
        for selector in cls.CONTENT_SELECTORS:
            try:
                elements = soup.select(selector)
                if elements:
                    # Use the largest element
                    main_content = max(elements, key=lambda e: len(e.get_text()))
                    break
            except:
                continue
        
        if main_content:
            # Remove excluded elements from main content
            for selector in cls.EXCLUDE_SELECTORS:
                try:
                    for element in main_content.select(selector):
                        element.decompose()
                except:
                    continue
            
            text = main_content.get_text(separator=' ', strip=True)
            content_parts.append(text)
        else:
            # Fallback: extract from body or entire document
            body = soup.find('body') or soup
            
            # Remove excluded elements
            for selector in cls.EXCLUDE_SELECTORS:
                try:
                    for element in body.select(selector):
                        element.decompose()
                except:
                    continue
            
            # Extract text from content tags
            for tag_name in cls.CONTENT_TAGS:
                for element in body.find_all(tag_name):
                    text = element.get_text(separator=' ', strip=True)
                    if len(text) > 50:  # Only include substantial text blocks
                        content_parts.append(text)
        
        # Join and clean up
        full_text = ' '.join(content_parts)
        
        # Clean up whitespace
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        return full_text
    
    @classmethod
    def html_to_markdown(cls, soup: BeautifulSoup) -> str:
        """Convert HTML to basic Markdown"""
        # This is a simplified HTML to Markdown converter
        # For production, consider using a library like html2text
        
        markdown_parts = []
        
        # Find main content area
        main_content = None
        for selector in cls.CONTENT_SELECTORS:
            try:
                elements = soup.select(selector)
                if elements:
                    main_content = max(elements, key=lambda e: len(e.get_text()))
                    break
            except:
                continue
        
        if not main_content:
            main_content = soup.find('body') or soup
        
        # Convert common elements
        for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level = int(element.name[1])
            text = element.get_text(strip=True)
            if text:
                markdown_parts.append('#' * level + ' ' + text + '\n')
        
        for element in main_content.find_all('p'):
            text = element.get_text(strip=True)
            if text:
                markdown_parts.append(text + '\n')
        
        for element in main_content.find_all('blockquote'):
            text = element.get_text(strip=True)
            if text:
                lines = text.split('\n')
                quoted = ['> ' + line for line in lines]
                markdown_parts.append('\n'.join(quoted) + '\n')
        
        # Join with proper spacing
        markdown = '\n'.join(markdown_parts)
        
        # Clean up excessive newlines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown).strip()
        
        return markdown


class ContentFetcher:
    """HTTP client for fetching content from Wayback Machine URLs"""
    
    def __init__(self):
        self.timeout = settings.WAYBACK_MACHINE_TIMEOUT or 60
        self.max_content_size = settings.MAX_CONTENT_SIZE or 50 * 1024 * 1024  # 50MB
        
        # Create HTTP client
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ChronoScraper/2.0; +https://chronoscraper.com)'
            }
        )
        
        logger.info(f"Initialized ContentFetcher with {self.timeout}s timeout, {self.max_content_size} byte limit")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def fetch_content(self, url: str) -> Tuple[bytes, str]:
        """
        Fetch content from URL with retry logic.
        
        Args:
            url: URL to fetch
            
        Returns:
            Tuple of (content_bytes, content_type)
        """
        try:
            response = await self.client.get(url)
            
            # Check content size
            content_length = int(response.headers.get('content-length', 0))
            if content_length > self.max_content_size:
                raise ContentTooLargeException(f"Content too large: {content_length} bytes")
            
            # Handle HTTP errors
            if response.status_code >= 400:
                raise ContentExtractionException(f"HTTP {response.status_code}: {response.text}")
            
            content = response.content
            
            # Double-check actual content size
            if len(content) > self.max_content_size:
                raise ContentTooLargeException(f"Content too large: {len(content)} bytes")
            
            content_type = response.headers.get('content-type', 'text/html').lower()
            
            return content, content_type
            
        except httpx.TimeoutException:
            logger.error(f"Timeout fetching content from {url}")
            raise
        except httpx.ConnectError:
            logger.error(f"Connection error fetching content from {url}")
            raise


class ContentExtractor:
    """Main content extraction service"""
    
    def __init__(self):
        self.html_extractor = HTMLExtractor()
        self.pdf_extractor = PDFExtractor() if PDF_AVAILABLE else None
        
    async def extract_content(self, record: CDXRecord, use_content_url: bool = True) -> ExtractedContent:
        """
        Extract content from a CDX record.
        
        Args:
            record: CDX record with URL information
            use_content_url: Whether to use the raw content URL (if_) for extraction
            
        Returns:
            ExtractedContent object with extracted data
        """
        start_time = time.time()
        
        # Determine URL to fetch
        fetch_url = record.content_url if use_content_url else record.wayback_url
        
        logger.debug(f"Extracting content from {fetch_url}")
        
        try:
            async with ContentFetcher() as fetcher:
                content_bytes, content_type = await fetcher.fetch_content(fetch_url)
            
            # Determine extraction method based on MIME type
            if record.mime_type == 'application/pdf' or 'pdf' in content_type:
                if not self.pdf_extractor:
                    raise UnsupportedContentTypeException("PDF extraction not available")
                
                title, text = self.pdf_extractor.extract_pdf_content(content_bytes)
                
                return ExtractedContent(
                    title=title,
                    text=text,
                    markdown=text,  # PDF content is already plain text
                    html="",
                    word_count=len(text.split()),
                    character_count=len(text),
                    extraction_method="pdf",
                    extraction_time=time.time() - start_time
                )
            
            elif 'html' in record.mime_type or 'html' in content_type:
                return await self._extract_html_content(content_bytes, start_time)
            
            else:
                raise UnsupportedContentTypeException(f"Unsupported content type: {record.mime_type}")
                
        except Exception as e:
            logger.error(f"Content extraction failed for {fetch_url}: {str(e)}")
            raise ContentExtractionException(f"Extraction failed: {str(e)}")
    
    async def _extract_html_content(self, content_bytes: bytes, start_time: float) -> ExtractedContent:
        """Extract content from HTML bytes"""
        try:
            # Decode HTML
            html_content = content_bytes.decode('utf-8', errors='ignore')
            
            # Clean and parse HTML
            soup = self.html_extractor.clean_html(html_content)
            
            # Extract metadata
            metadata = self.html_extractor.extract_metadata(soup)
            
            # Extract main text content
            text_content = self.html_extractor.extract_main_content(soup)
            
            # Convert to markdown
            markdown_content = self.html_extractor.html_to_markdown(soup)
            
            # Parse published date if available
            published_date = None
            if metadata['published_date']:
                try:
                    # Try common date formats
                    date_formats = [
                        '%Y-%m-%d',
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%dT%H:%M:%S.%fZ',
                        '%Y-%m-%dT%H:%M:%SZ',
                    ]
                    
                    for fmt in date_formats:
                        try:
                            published_date = datetime.strptime(metadata['published_date'][:19], fmt)
                            break
                        except ValueError:
                            continue
                except:
                    logger.debug(f"Could not parse published date: {metadata['published_date']}")
            
            return ExtractedContent(
                title=metadata['title'] or "No Title",
                text=text_content,
                markdown=markdown_content,
                html=str(soup),
                meta_description=metadata['description'],
                meta_keywords=metadata['keywords'],
                author=metadata['author'],
                published_date=published_date,
                language=metadata['language'],
                extraction_method="beautifulsoup",
                extraction_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"HTML extraction failed: {str(e)}")
            raise ContentExtractionException(f"HTML extraction failed: {str(e)}")


# Global instance for reuse
content_extractor = ContentExtractor()


async def extract_content_from_record(record: CDXRecord, use_content_url: bool = True) -> ExtractedContent:
    """
    Convenience function for extracting content from a CDX record.
    
    Args:
        record: CDX record
        use_content_url: Whether to use raw content URL
        
    Returns:
        ExtractedContent object
    """
    return await content_extractor.extract_content(record, use_content_url)