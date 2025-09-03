"""
Shared data models for content extraction
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class ContentExtractionException(Exception):
    """Base exception for content extraction errors"""
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
    source_url: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None
    word_count: int = 0
    character_count: int = 0
    extraction_method: str = "unknown"
    extraction_time: float = 0.0
    # CDX/URL metadata fields
    url: Optional[str] = None
    content_url: Optional[str] = None
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        """Calculate derived fields"""
        if self.text:
            self.word_count = len(self.text.split())
            self.character_count = len(self.text)