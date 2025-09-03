"""
Intelligent HTML content extraction system using multiple strategies
Designed to provide high-quality content extraction when AI services fail

Based on research showing trafilatura achieves F1 score of 0.945,
with newspaper3k and ensemble methods for optimal results.
"""

import logging
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# Core HTML parsing
from bs4 import BeautifulSoup
from lxml import html

# Intelligent content extraction
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from newspaper import Article
    NEWSPAPER_AVAILABLE = True
except ImportError:
    NEWSPAPER_AVAILABLE = False

# Metadata extraction
try:
    import htmldate
    HTMLDATE_AVAILABLE = True
except ImportError:
    HTMLDATE_AVAILABLE = False

try:
    import extruct
    EXTRUCT_AVAILABLE = True
except ImportError:
    EXTRUCT_AVAILABLE = False

# Language detection
try:
    from langdetect import detect, LangDetectError
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ExtractedMetadata:
    """Structured metadata extracted from HTML"""
    title: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[datetime] = None
    language: Optional[str] = None
    description: Optional[str] = None
    keywords: List[str] = None
    canonical_url: Optional[str] = None
    image_url: Optional[str] = None
    site_name: Optional[str] = None
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


@dataclass 
class ContentExtractionResult:
    """Result of intelligent content extraction"""
    text: str
    html: str
    markdown: str
    title: str
    word_count: int
    metadata: ExtractedMetadata
    extraction_method: str
    confidence_score: float
    processing_time: float


class IntelligentContentExtractor:
    """
    Multi-strategy content extraction system combining the best libraries
    
    Strategy hierarchy:
    1. Trafilatura (F1: 0.945) - Best overall performer
    2. Newspaper3k (F1: 0.912) - Good for news content  
    3. BeautifulSoup + heuristics - Reliable fallback
    """
    
    def __init__(self):
        self.extractors = []
        
        # Register available extractors in order of preference
        if TRAFILATURA_AVAILABLE:
            self.extractors.append(('trafilatura', self._extract_trafilatura))
            logger.info("Trafilatura extractor available (F1: 0.945)")
        
        if NEWSPAPER_AVAILABLE:
            self.extractors.append(('newspaper3k', self._extract_newspaper))
            logger.info("Newspaper3k extractor available (F1: 0.912)")
        
        # Always available fallback
        self.extractors.append(('beautifulsoup', self._extract_beautifulsoup))
        
        logger.info(f"Initialized with {len(self.extractors)} extraction strategies")
    
    def extract(self, html_content: str, url: Optional[str] = None) -> ContentExtractionResult:
        """
        Extract content using best available strategy
        
        Args:
            html_content: Raw HTML content
            url: Original URL for context (optional)
            
        Returns:
            ContentExtractionResult with extracted content and metadata
        """
        import time
        start_time = time.time()
        
        best_result = None
        best_confidence = 0.0
        
        for method_name, extractor_func in self.extractors:
            try:
                logger.debug(f"Attempting extraction with {method_name}")
                result = extractor_func(html_content, url)
                
                confidence = self._calculate_confidence(result, method_name)
                
                if confidence > best_confidence:
                    best_result = result
                    best_confidence = confidence
                    best_result.extraction_method = method_name
                    best_result.confidence_score = confidence
                
                # If we get high confidence result, use it
                if confidence > 0.8:
                    break
                    
            except Exception as e:
                logger.warning(f"Extractor {method_name} failed: {e}")
                continue
        
        if not best_result:
            # Final fallback to basic text extraction
            best_result = self._basic_text_extraction(html_content, url)
            best_result.extraction_method = 'basic_fallback'
            best_result.confidence_score = 0.1
        
        # Add processing time
        best_result.processing_time = time.time() - start_time
        
        # Enhance with metadata from multiple sources
        best_result.metadata = self._extract_comprehensive_metadata(
            html_content, url, best_result.text
        )
        
        logger.info(f"Content extracted using {best_result.extraction_method} "
                   f"(confidence: {best_result.confidence_score:.3f}, "
                   f"words: {best_result.word_count})")
        
        return best_result
    
    def _extract_trafilatura(self, html_content: str, url: Optional[str]) -> ContentExtractionResult:
        """Extract using Trafilatura (best F1 score: 0.945)"""
        
        # Configure trafilatura for maximum quality
        config = trafilatura.settings.use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")  # No timeout
        config.set("DEFAULT", "MIN_EXTRACTED_SIZE", "25")  # Minimum text length
        config.set("DEFAULT", "MIN_OUTPUT_SIZE", "10")     # Minimum output size
        
        # Extract with metadata
        metadata_result = trafilatura.extract_metadata(html_content)
        
        # Extract main content in multiple formats
        text = trafilatura.extract(
            html_content,
            config=config,
            include_comments=False,
            include_tables=True,
            url=url,
            favor_precision=True  # Prioritize precision over recall
        )
        
        xml_output = trafilatura.extract(
            html_content,
            config=config,
            output_format='xml',
            include_comments=False,
            include_tables=True,
            url=url
        )
        
        # Convert to markdown-style format
        markdown = self._xml_to_markdown(xml_output) if xml_output else text or ""
        
        # Get title from metadata or extract from content
        title = ""
        if metadata_result:
            title = metadata_result.title or ""
        
        if not title and text:
            # Try to extract title from first line if it looks like a title
            first_line = text.split('\n')[0].strip()
            if len(first_line) < 100 and len(first_line) > 5:
                title = first_line
        
        word_count = len(text.split()) if text else 0
        
        return ContentExtractionResult(
            text=text or "",
            html="",  # Trafilatura doesn't return HTML
            markdown=markdown,
            title=title,
            word_count=word_count,
            metadata=ExtractedMetadata(),  # Will be filled later
            extraction_method="trafilatura",
            confidence_score=0.0,  # Will be calculated
            processing_time=0.0
        )
    
    def _extract_newspaper(self, html_content: str, url: Optional[str]) -> ContentExtractionResult:
        """Extract using Newspaper3k (good for news content)"""
        
        article = Article('')
        article.set_html(html_content)
        article.parse()
        
        # Extract NLP features if possible
        try:
            article.nlp()
        except Exception:
            pass  # NLP processing optional
        
        # Convert to markdown-style formatting
        markdown = self._text_to_markdown(article.text)
        
        word_count = len(article.text.split()) if article.text else 0
        
        return ContentExtractionResult(
            text=article.text or "",
            html=article.html or "",
            markdown=markdown,
            title=article.title or "",
            word_count=word_count,
            metadata=ExtractedMetadata(),  # Will be filled later
            extraction_method="newspaper3k",
            confidence_score=0.0,
            processing_time=0.0
        )
    
    def _extract_beautifulsoup(self, html_content: str, url: Optional[str]) -> ContentExtractionResult:
        """Fallback extraction using BeautifulSoup with intelligent heuristics"""
        
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove noise elements
        self._remove_noise_elements(soup)
        
        # Extract title
        title = self._extract_title(soup)
        
        # Find main content using multiple strategies
        content = self._find_main_content(soup)
        
        if not content:
            # Fallback to body content
            body = soup.find('body')
            content = body if body else soup
        
        # Extract clean text
        text = self._extract_clean_text(content)
        
        # Convert to markdown
        markdown = self._html_to_markdown(content)
        
        word_count = len(text.split()) if text else 0
        
        return ContentExtractionResult(
            text=text,
            html=str(content) if content else "",
            markdown=markdown,
            title=title,
            word_count=word_count,
            metadata=ExtractedMetadata(),
            extraction_method="beautifulsoup",
            confidence_score=0.0,
            processing_time=0.0
        )
    
    def _remove_noise_elements(self, soup: BeautifulSoup):
        """Remove ads, navigation, and other noise from DOM"""
        
        # Remove script and style elements
        for element in soup(['script', 'style', 'meta', 'link']):
            element.decompose()
        
        # Remove common noise by tag
        noise_tags = ['nav', 'aside', 'footer', 'header']
        for tag in noise_tags:
            for element in soup.find_all(tag):
                element.decompose()
        
        # Remove by common class/id patterns (ads, navigation, etc.)
        noise_patterns = [
            # Navigation
            r'nav', r'menu', r'breadcrumb',
            # Ads
            r'ad[s]?', r'advertisement', r'sponsor', r'promo',
            # Social/sharing
            r'social', r'share', r'follow',
            # Comments
            r'comment', r'reply',
            # Footer/header content
            r'footer', r'header', r'sidebar', r'aside',
            # Pagination
            r'pag', r'next', r'prev',
            # Related content
            r'related', r'recommend', r'suggest'
        ]
        
        for pattern in noise_patterns:
            # Remove by class
            for element in soup.find_all(class_=re.compile(pattern, re.I)):
                element.decompose()
            
            # Remove by id
            for element in soup.find_all(id=re.compile(pattern, re.I)):
                element.decompose()
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title using multiple strategies"""
        
        # Strategy 1: HTML title tag
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            # Clean common suffixes
            title = re.sub(r'\s*[|\-–]\s*.+$', '', title)
            if len(title) > 5:
                return title
        
        # Strategy 2: Open Graph title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content'].strip()
        
        # Strategy 3: H1 tag
        h1 = soup.find('h1')
        if h1:
            title_text = h1.get_text().strip()
            if 5 < len(title_text) < 100:
                return title_text
        
        return ""
    
    def _find_main_content(self, soup: BeautifulSoup):
        """Find main content area using heuristics"""
        
        # Strategy 1: Look for semantic HTML5 elements
        for tag in ['main', 'article']:
            element = soup.find(tag)
            if element:
                return element
        
        # Strategy 2: Look for common content containers
        content_selectors = [
            {'class': re.compile(r'content', re.I)},
            {'class': re.compile(r'post', re.I)},
            {'class': re.compile(r'article', re.I)},
            {'class': re.compile(r'entry', re.I)},
            {'id': re.compile(r'content', re.I)},
            {'id': re.compile(r'main', re.I)},
        ]
        
        for selector in content_selectors:
            element = soup.find('div', selector)
            if element:
                return element
        
        # Strategy 3: Find div with most text content
        divs = soup.find_all('div')
        if divs:
            best_div = max(divs, key=lambda d: len(d.get_text()))
            if len(best_div.get_text()) > 100:  # Minimum content length
                return best_div
        
        return None
    
    def _extract_clean_text(self, element) -> str:
        """Extract clean text from HTML element"""
        if not element:
            return ""
        
        # Get text and clean whitespace
        text = element.get_text()
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    def _html_to_markdown(self, element) -> str:
        """Convert HTML element to basic markdown"""
        if not element:
            return ""
        
        # Create a copy to avoid modifying original
        html_str = str(element)
        
        # Convert headers
        for i in range(1, 7):
            pattern = rf'<h{i}[^>]*>([^<]+)</h{i}>'
            replacement = '#' * i + r' \1\n\n'
            html_str = re.sub(pattern, replacement, html_str, flags=re.I)
        
        # Convert paragraphs
        html_str = re.sub(r'<p[^>]*>([^<]+)</p>', r'\1\n\n', html_str, flags=re.I)
        
        # Convert links
        html_str = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>([^<]+)</a>', r'[\2](\1)', html_str, flags=re.I)
        
        # Convert bold and italic
        html_str = re.sub(r'<(strong|b)[^>]*>([^<]+)</\1>', r'**\2**', html_str, flags=re.I)
        html_str = re.sub(r'<(em|i)[^>]*>([^<]+)</\1>', r'*\2*', html_str, flags=re.I)
        
        # Remove remaining HTML tags
        html_str = re.sub(r'<[^>]+>', '', html_str)
        
        # Decode HTML entities
        from html import unescape
        html_str = unescape(html_str)
        
        # Clean up whitespace
        html_str = re.sub(r'\n\s*\n\s*\n', '\n\n', html_str)
        
        return html_str.strip()
    
    def _text_to_markdown(self, text: str) -> str:
        """Convert plain text to basic markdown formatting"""
        if not text:
            return ""
        
        lines = text.split('\n')
        markdown_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                markdown_lines.append('')
                continue
            
            # Detect titles (short lines that might be headers)
            if len(line) < 80 and not line.endswith('.') and not line.endswith(','):
                # Could be a header
                markdown_lines.append(f'# {line}\n')
            else:
                markdown_lines.append(line)
        
        return '\n'.join(markdown_lines)
    
    def _xml_to_markdown(self, xml_content: str) -> str:
        """Convert Trafilatura XML to markdown"""
        if not xml_content:
            return ""
        
        try:
            # Parse XML and convert to markdown-like format
            soup = BeautifulSoup(xml_content, 'xml')
            
            # Convert XML tags to markdown
            for p in soup.find_all('p'):
                p.string = p.get_text() + '\n\n'
                p.unwrap()
            
            for head in soup.find_all('head'):
                level = min(int(head.get('level', 1)), 6)
                head.string = '#' * level + ' ' + head.get_text() + '\n\n'
                head.unwrap()
            
            return soup.get_text()
            
        except Exception:
            # Fallback to simple text extraction
            return re.sub(r'<[^>]+>', '', xml_content)
    
    def _extract_comprehensive_metadata(self, html_content: str, url: Optional[str], 
                                      text: str) -> ExtractedMetadata:
        """Extract metadata using multiple specialized libraries"""
        
        metadata = ExtractedMetadata()
        
        # Parse with BeautifulSoup for basic metadata
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Extract publication date using htmldate (if available)
        if HTMLDATE_AVAILABLE:
            try:
                pub_date_str = htmldate.find_date(html_content, original_date=True)
                if pub_date_str:
                    metadata.publication_date = datetime.fromisoformat(pub_date_str)
            except Exception as e:
                logger.debug(f"htmldate extraction failed: {e}")
        
        # Extract structured data using extruct (if available)
        if EXTRUCT_AVAILABLE:
            try:
                structured_data = extruct.extract(html_content, base_url=url or "")
                
                # Extract from JSON-LD
                if 'json-ld' in structured_data:
                    for item in structured_data['json-ld']:
                        if isinstance(item, dict):
                            metadata.author = metadata.author or item.get('author', {}).get('name')
                            metadata.description = metadata.description or item.get('description')
                            if 'datePublished' in item:
                                try:
                                    metadata.publication_date = datetime.fromisoformat(
                                        item['datePublished'].replace('Z', '+00:00')
                                    )
                                except Exception:
                                    pass
                
                # Extract from OpenGraph
                if 'opengraph' in structured_data:
                    for item in structured_data['opengraph']:
                        if isinstance(item, dict) and 'properties' in item:
                            props = item['properties']
                            metadata.title = metadata.title or props.get('og:title', [None])[0]
                            metadata.description = metadata.description or props.get('og:description', [None])[0]
                            metadata.image_url = metadata.image_url or props.get('og:image', [None])[0]
                            metadata.site_name = metadata.site_name or props.get('og:site_name', [None])[0]
                
            except Exception as e:
                logger.debug(f"extruct extraction failed: {e}")
        
        # Extract basic metadata from HTML meta tags
        self._extract_html_metadata(soup, metadata)
        
        # Detect language
        if LANGDETECT_AVAILABLE and text:
            try:
                metadata.language = detect(text)
            except LangDetectError:
                # Try with first 1000 chars if full text fails
                try:
                    if len(text) > 1000:
                        metadata.language = detect(text[:1000])
                except LangDetectError:
                    pass
        
        # Extract keywords from meta tags
        keywords_meta = soup.find('meta', attrs={'name': re.compile(r'keywords', re.I)})
        if keywords_meta and keywords_meta.get('content'):
            keywords = [k.strip() for k in keywords_meta['content'].split(',')]
            metadata.keywords = [k for k in keywords if k]
        
        return metadata
    
    def _extract_html_metadata(self, soup: BeautifulSoup, metadata: ExtractedMetadata):
        """Extract metadata from HTML meta tags"""
        
        # Description
        desc_meta = soup.find('meta', attrs={'name': re.compile(r'description', re.I)})
        if desc_meta and desc_meta.get('content'):
            metadata.description = desc_meta['content']
        
        # Author
        author_meta = soup.find('meta', attrs={'name': re.compile(r'author', re.I)})
        if author_meta and author_meta.get('content'):
            metadata.author = author_meta['content']
        
        # Canonical URL
        canonical_link = soup.find('link', rel='canonical')
        if canonical_link and canonical_link.get('href'):
            metadata.canonical_url = canonical_link['href']
    
    def _calculate_confidence(self, result: ContentExtractionResult, method: str) -> float:
        """Calculate confidence score based on extracted content quality"""
        
        confidence = 0.0
        
        # Base confidence by method
        method_confidence = {
            'trafilatura': 0.8,    # Highest baseline (F1: 0.945)
            'newspaper3k': 0.7,    # Good baseline (F1: 0.912)
            'beautifulsoup': 0.5   # Lower baseline
        }
        
        confidence = method_confidence.get(method, 0.3)
        
        # Adjust based on content quality indicators
        
        # Word count bonus
        if result.word_count > 100:
            confidence += 0.1
        elif result.word_count > 50:
            confidence += 0.05
        
        # Title bonus
        if result.title and len(result.title) > 5:
            confidence += 0.05
        
        # Content structure bonus (has paragraphs)
        if result.text and '\n' in result.text:
            confidence += 0.05
        
        return min(confidence, 1.0)
    
    def _basic_text_extraction(self, html_content: str, url: Optional[str]) -> ContentExtractionResult:
        """Final fallback - basic text extraction"""
        
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script and style
        for element in soup(['script', 'style']):
            element.decompose()
        
        title = soup.find('title')
        title_text = title.get_text() if title else ""
        
        text = soup.get_text()
        text = re.sub(r'\s+', ' ', text).strip()
        
        word_count = len(text.split()) if text else 0
        
        return ContentExtractionResult(
            text=text,
            html="",
            markdown=text,  # No formatting for basic extraction
            title=title_text,
            word_count=word_count,
            metadata=ExtractedMetadata(),
            extraction_method="basic_fallback",
            confidence_score=0.1,
            processing_time=0.0
        )


# Global instance
_intelligent_extractor = None

def get_intelligent_extractor() -> IntelligentContentExtractor:
    """Get global intelligent content extractor instance"""
    global _intelligent_extractor
    if _intelligent_extractor is None:
        _intelligent_extractor = IntelligentContentExtractor()
    return _intelligent_extractor