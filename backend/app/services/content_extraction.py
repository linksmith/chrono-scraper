"""
Content extraction and processing service
"""
import re
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urljoin, urlparse
import logging
from dataclasses import dataclass

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
    from readability import Document
    import html2text
    from markdownify import markdownify
except ImportError:
    BeautifulSoup = None
    Document = None
    html2text = None
    markdownify = None

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    """Container for extracted content"""
    title: Optional[str] = None
    main_content: Optional[str] = None
    markdown_content: Optional[str] = None
    text_content: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    lang: Optional[str] = None
    canonical_url: Optional[str] = None
    links: List[Dict[str, str]] = None
    images: List[Dict[str, str]] = None
    headings: List[Dict[str, str]] = None
    word_count: int = 0
    char_count: int = 0
    reading_time_minutes: int = 0
    content_hash: Optional[str] = None
    extraction_method: str = "basic"
    structured_data: List[Dict[str, Any]] = None


class ContentExtractionService:
    """Service for extracting and processing web content"""
    
    def __init__(self):
        # Check if required libraries are available
        self.has_bs4 = BeautifulSoup is not None
        self.has_readability = Document is not None
        self.has_html2text = html2text is not None
        self.has_markdownify = markdownify is not None
        
        if not self.has_bs4:
            logger.warning("BeautifulSoup not available - content extraction will be limited")
    
    def extract_content(
        self,
        html: str,
        url: Optional[str] = None,
        method: str = "auto"
    ) -> ExtractedContent:
        """
        Extract content from HTML using specified method
        
        Args:
            html: HTML content to extract from
            url: Original URL for resolving relative links
            method: Extraction method (auto, readability, basic, manual)
        
        Returns:
            ExtractedContent object
        """
        if not self.has_bs4:
            return self._extract_basic_text(html, url)
        
        soup = BeautifulSoup(html, 'html.parser')
        
        if method == "auto":
            # Try readability first, fall back to manual extraction
            if self.has_readability:
                try:
                    return self._extract_with_readability(html, url, soup)
                except Exception as e:
                    logger.warning(f"Readability extraction failed: {str(e)}")
            
            return self._extract_manual(soup, url)
        
        elif method == "readability" and self.has_readability:
            return self._extract_with_readability(html, url, soup)
        
        elif method == "basic":
            return self._extract_basic(soup, url)
        
        elif method == "manual":
            return self._extract_manual(soup, url)
        
        else:
            # Fallback to basic extraction
            return self._extract_basic(soup, url)
    
    def _extract_with_readability(
        self,
        html: str,
        url: Optional[str],
        soup: BeautifulSoup
    ) -> ExtractedContent:
        """Extract content using readability library"""
        try:
            doc = Document(html)
            readable_html = doc.summary()
            
            # Parse the cleaned HTML
            clean_soup = BeautifulSoup(readable_html, 'html.parser')
            
            # Extract metadata from original soup
            metadata = self._extract_metadata(soup, url)
            
            # Convert to text and markdown
            text_content = self._html_to_text(clean_soup)
            markdown_content = self._html_to_markdown(clean_soup)
            
            # Calculate statistics
            word_count = len(text_content.split()) if text_content else 0
            char_count = len(text_content) if text_content else 0
            reading_time = max(1, word_count // 200)  # Assume 200 WPM
            
            # Generate content hash
            content_hash = self._generate_content_hash(text_content)
            
            return ExtractedContent(
                title=metadata.get("title") or doc.title(),
                main_content=readable_html,
                markdown_content=markdown_content,
                text_content=text_content,
                meta_description=metadata.get("description"),
                meta_keywords=metadata.get("keywords"),
                author=metadata.get("author"),
                published_date=metadata.get("published_date"),
                lang=metadata.get("lang"),
                canonical_url=metadata.get("canonical_url") or url,
                links=self._extract_links(clean_soup, url),
                images=self._extract_images(clean_soup, url),
                headings=self._extract_headings(clean_soup),
                word_count=word_count,
                char_count=char_count,
                reading_time_minutes=reading_time,
                content_hash=content_hash,
                extraction_method="readability",
                structured_data=self._extract_structured_data(soup)
            )
            
        except Exception as e:
            logger.error(f"Readability extraction failed: {str(e)}")
            return self._extract_manual(soup, url)
    
    def _extract_manual(
        self,
        soup: BeautifulSoup,
        url: Optional[str]
    ) -> ExtractedContent:
        """Manual content extraction using heuristics"""
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'advertisement']):
            element.decompose()
        
        # Extract metadata
        metadata = self._extract_metadata(soup, url)
        
        # Try to find main content area
        main_content_html = self._find_main_content(soup)
        
        # Convert to text and markdown
        text_content = self._html_to_text(main_content_html or soup)
        markdown_content = self._html_to_markdown(main_content_html or soup)
        
        # Calculate statistics
        word_count = len(text_content.split()) if text_content else 0
        char_count = len(text_content) if text_content else 0
        reading_time = max(1, word_count // 200)
        
        # Generate content hash
        content_hash = self._generate_content_hash(text_content)
        
        return ExtractedContent(
            title=metadata.get("title"),
            main_content=str(main_content_html) if main_content_html else str(soup),
            markdown_content=markdown_content,
            text_content=text_content,
            meta_description=metadata.get("description"),
            meta_keywords=metadata.get("keywords"),
            author=metadata.get("author"),
            published_date=metadata.get("published_date"),
            lang=metadata.get("lang"),
            canonical_url=metadata.get("canonical_url") or url,
            links=self._extract_links(soup, url),
            images=self._extract_images(soup, url),
            headings=self._extract_headings(soup),
            word_count=word_count,
            char_count=char_count,
            reading_time_minutes=reading_time,
            content_hash=content_hash,
            extraction_method="manual",
            structured_data=self._extract_structured_data(soup)
        )
    
    def _extract_basic(
        self,
        soup: BeautifulSoup,
        url: Optional[str]
    ) -> ExtractedContent:
        """Basic content extraction"""
        
        # Extract metadata
        metadata = self._extract_metadata(soup, url)
        
        # Get all text content
        text_content = soup.get_text(separator=' ', strip=True)
        
        # Calculate statistics
        word_count = len(text_content.split()) if text_content else 0
        char_count = len(text_content) if text_content else 0
        reading_time = max(1, word_count // 200)
        
        # Generate content hash
        content_hash = self._generate_content_hash(text_content)
        
        return ExtractedContent(
            title=metadata.get("title"),
            main_content=str(soup),
            text_content=text_content,
            meta_description=metadata.get("description"),
            meta_keywords=metadata.get("keywords"),
            author=metadata.get("author"),
            published_date=metadata.get("published_date"),
            lang=metadata.get("lang"),
            canonical_url=metadata.get("canonical_url") or url,
            links=self._extract_links(soup, url),
            images=self._extract_images(soup, url),
            headings=self._extract_headings(soup),
            word_count=word_count,
            char_count=char_count,
            reading_time_minutes=reading_time,
            content_hash=content_hash,
            extraction_method="basic",
            structured_data=self._extract_structured_data(soup)
        )
    
    def _extract_basic_text(
        self,
        html: str,
        url: Optional[str]
    ) -> ExtractedContent:
        """Fallback extraction when BeautifulSoup is not available"""
        
        # Remove HTML tags using regex (basic approach)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Extract title using regex
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        title = title_match.group(1) if title_match else None
        
        # Calculate statistics
        word_count = len(text.split()) if text else 0
        char_count = len(text) if text else 0
        reading_time = max(1, word_count // 200)
        
        # Generate content hash
        content_hash = self._generate_content_hash(text)
        
        return ExtractedContent(
            title=title,
            main_content=html,
            text_content=text,
            canonical_url=url,
            word_count=word_count,
            char_count=char_count,
            reading_time_minutes=reading_time,
            content_hash=content_hash,
            extraction_method="regex_fallback",
            links=[],
            images=[],
            headings=[],
            structured_data=[]
        )
    
    def _extract_metadata(
        self,
        soup: BeautifulSoup,
        url: Optional[str]
    ) -> Dict[str, Any]:
        """Extract metadata from HTML"""
        metadata = {}
        
        # Title
        title_tag = soup.find('title')
        if title_tag:
            metadata["title"] = title_tag.get_text().strip()
        
        # Meta description
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag and desc_tag.get('content'):
            metadata["description"] = desc_tag['content'].strip()
        
        # Meta keywords
        keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_tag and keywords_tag.get('content'):
            metadata["keywords"] = keywords_tag['content'].strip()
        
        # Author
        author_tag = soup.find('meta', attrs={'name': 'author'})
        if author_tag and author_tag.get('content'):
            metadata["author"] = author_tag['content'].strip()
        
        # Language
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            metadata["lang"] = html_tag['lang']
        
        # Canonical URL
        canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
        if canonical_tag and canonical_tag.get('href'):
            metadata["canonical_url"] = canonical_tag['href']
        
        # Published date (various formats)
        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'meta[name="publish_date"]',
            'time[datetime]',
            '.published',
            '.date'
        ]
        
        for selector in date_selectors:
            date_element = soup.select_one(selector)
            if date_element:
                date_text = date_element.get('content') or date_element.get('datetime') or date_element.get_text()
                if date_text:
                    try:
                        # Try to parse common date formats
                        from dateutil import parser
                        metadata["published_date"] = parser.parse(date_text)
                        break
                    except:
                        continue
        
        return metadata
    
    def _find_main_content(self, soup: BeautifulSoup) -> Optional[Tag]:
        """Find the main content area using heuristics"""
        
        # Try semantic HTML5 elements first
        for tag_name in ['main', 'article']:
            main_tag = soup.find(tag_name)
            if main_tag:
                return main_tag
        
        # Try common content class/id names
        content_selectors = [
            '#content', '.content',
            '#main', '.main',
            '#article', '.article',
            '#post', '.post',
            '.entry-content',
            '.post-content',
            '.article-content'
        ]
        
        for selector in content_selectors:
            content_element = soup.select_one(selector)
            if content_element:
                return content_element
        
        # Find the element with the most text content
        candidates = soup.find_all(['div', 'section'])
        if candidates:
            best_candidate = max(candidates, key=lambda x: len(x.get_text()))
            if len(best_candidate.get_text()) > 200:  # Minimum content threshold
                return best_candidate
        
        return None
    
    def _extract_links(
        self,
        soup: BeautifulSoup,
        base_url: Optional[str]
    ) -> List[Dict[str, str]]:
        """Extract all links from the content"""
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            text = link.get_text().strip()
            
            # Resolve relative URLs
            if base_url and href:
                try:
                    absolute_url = urljoin(base_url, href)
                except:
                    absolute_url = href
            else:
                absolute_url = href
            
            links.append({
                "url": absolute_url,
                "text": text,
                "title": link.get('title', ''),
                "rel": link.get('rel', [])
            })
        
        return links
    
    def _extract_images(
        self,
        soup: BeautifulSoup,
        base_url: Optional[str]
    ) -> List[Dict[str, str]]:
        """Extract all images from the content"""
        images = []
        
        for img in soup.find_all('img'):
            src = img.get('src', '').strip()
            if not src:
                continue
            
            # Resolve relative URLs
            if base_url and src:
                try:
                    absolute_url = urljoin(base_url, src)
                except:
                    absolute_url = src
            else:
                absolute_url = src
            
            images.append({
                "url": absolute_url,
                "alt": img.get('alt', ''),
                "title": img.get('title', ''),
                "width": img.get('width', ''),
                "height": img.get('height', '')
            })
        
        return images
    
    def _extract_headings(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract all headings from the content"""
        headings = []
        
        for i in range(1, 7):  # h1 through h6
            for heading in soup.find_all(f'h{i}'):
                text = heading.get_text().strip()
                if text:
                    headings.append({
                        "level": i,
                        "text": text,
                        "id": heading.get('id', '')
                    })
        
        return headings
    
    def _extract_structured_data(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract structured data (JSON-LD, microdata, etc.)"""
        structured_data = []
        
        # JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                import json
                data = json.loads(script.string)
                structured_data.append({
                    "type": "json-ld",
                    "data": data
                })
            except:
                continue
        
        # Microdata (basic extraction)
        for element in soup.find_all(attrs={"itemscope": True}):
            try:
                item_type = element.get('itemtype', '')
                props = {}
                
                for prop in element.find_all(attrs={"itemprop": True}):
                    prop_name = prop.get('itemprop')
                    prop_value = prop.get('content') or prop.get_text().strip()
                    props[prop_name] = prop_value
                
                if props:
                    structured_data.append({
                        "type": "microdata",
                        "itemtype": item_type,
                        "data": props
                    })
            except:
                continue
        
        return structured_data
    
    def _html_to_text(self, soup: BeautifulSoup) -> str:
        """Convert HTML to clean text"""
        if self.has_html2text:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            return h.handle(str(soup))
        else:
            # Fallback to simple text extraction
            return soup.get_text(separator=' ', strip=True)
    
    def _html_to_markdown(self, soup: BeautifulSoup) -> Optional[str]:
        """Convert HTML to markdown"""
        if self.has_markdownify:
            try:
                return markdownify(str(soup), heading_style="ATX")
            except:
                return None
        else:
            return None
    
    def _generate_content_hash(self, text: Optional[str]) -> Optional[str]:
        """Generate SHA-256 hash of content for deduplication"""
        if not text:
            return None
        
        # Normalize text for hashing
        normalized = re.sub(r'\s+', ' ', text.strip().lower())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    
    def extract_text_summary(
        self,
        text: str,
        max_length: int = 500,
        sentence_aware: bool = True
    ) -> str:
        """
        Extract a summary of the text content
        
        Args:
            text: Input text
            max_length: Maximum summary length
            sentence_aware: Whether to break at sentence boundaries
        
        Returns:
            Text summary
        """
        if len(text) <= max_length:
            return text
        
        if sentence_aware:
            # Try to break at sentence boundaries
            sentences = re.split(r'[.!?]+', text)
            summary = ""
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                if len(summary + sentence) + 1 <= max_length:
                    summary += sentence + ". "
                else:
                    break
            
            if summary:
                return summary.strip()
        
        # Fallback to character-based truncation
        return text[:max_length].strip() + "..."
    
    def detect_content_language(self, text: str) -> Optional[str]:
        """
        Detect the language of the content (placeholder)
        
        Args:
            text: Text content to analyze
        
        Returns:
            Language code (ISO 639-1) or None
        """
        # This is a placeholder - in a real implementation,
        # you would use a language detection library like langdetect
        # or polyglot
        
        # Simple heuristic based on common words
        english_words = set(['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'])
        words = set(text.lower().split()[:50])  # Check first 50 words
        
        english_matches = len(words.intersection(english_words))
        if english_matches > 3:
            return 'en'
        
        return None


# Global service instance
content_extraction_service = ContentExtractionService()