"""
Data transformation layer for converting PostgreSQL data to analytics-optimized formats.

This module provides specialized transformers for different data types:
- CDXTransformer: ScrapePage records to CDX analytics format
- ContentTransformer: Extraction results to content analytics format
- ProjectTransformer: Project metrics to project analytics format
- EventTransformer: System events to analytics format

Each transformer handles schema conversion, data validation, and optimization
for columnar storage in Parquet format.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import urlparse

import pandas as pd
import pyarrow as pa
from pydantic import BaseModel, Field, validator

from app.models.scraping import ScrapePage, ScrapePageStatus

logger = logging.getLogger(__name__)


@dataclass
class TransformationResult:
    """Result of data transformation operation."""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    warnings: List[str] = None
    record_count: int = 0
    transformation_time: float = 0.0


class BaseTransformer(ABC):
    """Base class for all data transformers."""
    
    def __init__(self):
        self.transformation_stats = {
            "total_processed": 0,
            "successful_transformations": 0,
            "failed_transformations": 0,
            "warnings": []
        }
    
    @abstractmethod
    def transform(self, data: List[Dict[str, Any]]) -> TransformationResult:
        """Transform input data to analytics format."""
        pass
    
    @abstractmethod
    def get_schema(self) -> pa.Schema:
        """Get PyArrow schema for the transformed data."""
        pass
    
    def validate_input(self, data: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """Validate input data structure."""
        errors = []
        
        if not isinstance(data, list):
            errors.append("Input data must be a list")
            return False, errors
        
        if not data:
            return True, []  # Empty data is valid
        
        # Check if all items are dictionaries
        for i, item in enumerate(data[:10]):  # Check first 10 items
            if not isinstance(item, dict):
                errors.append(f"Item {i} is not a dictionary")
        
        return len(errors) == 0, errors
    
    def get_stats(self) -> Dict[str, Any]:
        """Get transformation statistics."""
        return self.transformation_stats.copy()
    
    def reset_stats(self):
        """Reset transformation statistics."""
        self.transformation_stats = {
            "total_processed": 0,
            "successful_transformations": 0,
            "failed_transformations": 0,
            "warnings": []
        }


class CDXTransformer(BaseTransformer):
    """
    Transform ScrapePage records to CDX analytics format.
    
    Optimizes data for time-series analytics, URL pattern analysis,
    and scraping performance metrics.
    """
    
    def transform(self, data: List[Dict[str, Any]]) -> TransformationResult:
        """Transform ScrapePage data to CDX analytics format."""
        start_time = datetime.utcnow()
        
        try:
            # Validate input
            is_valid, errors = self.validate_input(data)
            if not is_valid:
                return TransformationResult(
                    success=False,
                    error=f"Input validation failed: {'; '.join(errors)}"
                )
            
            if not data:
                return TransformationResult(success=True, data=[], record_count=0)
            
            transformed_data = []
            warnings = []
            
            for record in data:
                try:
                    transformed_record = self._transform_single_record(record)
                    if transformed_record:
                        transformed_data.append(transformed_record)
                        self.transformation_stats["successful_transformations"] += 1
                    
                except Exception as e:
                    warning_msg = f"Failed to transform record {record.get('id', 'unknown')}: {str(e)}"
                    warnings.append(warning_msg)
                    logger.warning(warning_msg)
                    self.transformation_stats["failed_transformations"] += 1
                
                self.transformation_stats["total_processed"] += 1
            
            end_time = datetime.utcnow()
            transformation_time = (end_time - start_time).total_seconds()
            
            return TransformationResult(
                success=True,
                data=transformed_data,
                warnings=warnings,
                record_count=len(transformed_data),
                transformation_time=transformation_time
            )
            
        except Exception as e:
            logger.error(f"CDX transformation failed: {str(e)}")
            return TransformationResult(
                success=False,
                error=str(e)
            )
    
    def _transform_single_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform a single ScrapePage record."""
        try:
            # Parse URL components
            parsed_url = urlparse(record.get('original_url', ''))
            
            # Extract date components from unix_timestamp
            unix_ts = record.get('unix_timestamp', '')
            capture_date = None
            if unix_ts and len(unix_ts) >= 8:
                try:
                    year = int(unix_ts[:4])
                    month = int(unix_ts[4:6])
                    day = int(unix_ts[6:8])
                    capture_date = date(year, month, day)
                except (ValueError, TypeError):
                    capture_date = None
            
            # Calculate processing metrics
            total_time = record.get('total_processing_time', 0) or 0
            fetch_time = record.get('fetch_time', 0) or 0
            extraction_time = record.get('extraction_time', 0) or 0
            
            # Categorize status for analytics
            status = record.get('status', '')
            status_category = self._categorize_status(status)
            
            # Content analysis
            content_length = record.get('content_length') or 0
            has_content = bool(record.get('extracted_text'))
            
            return {
                # Core identifiers
                'id': record.get('id'),
                'domain_id': record.get('domain_id'),
                'scrape_session_id': record.get('scrape_session_id'),
                
                # URL analysis
                'original_url': record.get('original_url'),
                'content_url': record.get('content_url'),
                'url_domain': parsed_url.netloc,
                'url_path': parsed_url.path,
                'url_scheme': parsed_url.scheme,
                'url_depth': len([p for p in parsed_url.path.split('/') if p]),
                'url_has_params': bool(parsed_url.params or parsed_url.query),
                
                # Temporal analysis
                'unix_timestamp': unix_ts,
                'capture_date': capture_date.isoformat() if capture_date else None,
                'capture_year': capture_date.year if capture_date else None,
                'capture_month': capture_date.month if capture_date else None,
                'capture_day_of_week': capture_date.weekday() if capture_date else None,
                
                # Content metadata
                'mime_type': record.get('mime_type'),
                'status_code': record.get('status_code', 200),
                'content_length': content_length,
                'content_length_category': self._categorize_content_length(content_length),
                'digest_hash': record.get('digest_hash'),
                
                # Content analysis
                'title': record.get('title'),
                'title_length': len(record.get('title', '')),
                'has_extracted_content': has_content,
                'is_pdf': record.get('is_pdf', False),
                'is_duplicate': record.get('is_duplicate', False),
                'is_list_page': record.get('is_list_page', False),
                'extraction_method': record.get('extraction_method'),
                
                # Processing status and performance
                'status': status,
                'status_category': status_category,
                'retry_count': record.get('retry_count', 0),
                'max_retries': record.get('max_retries', 3),
                'error_type': record.get('error_type'),
                'has_error': bool(record.get('error_message')),
                
                # Performance metrics
                'total_processing_time': total_time,
                'fetch_time': fetch_time,
                'extraction_time': extraction_time,
                'processing_efficiency': self._calculate_efficiency(total_time, content_length),
                
                # Filtering analysis
                'filter_reason': record.get('filter_reason'),
                'filter_category': record.get('filter_category'),
                'priority_score': record.get('priority_score', 5),
                'is_manually_overridden': record.get('is_manually_overridden', False),
                'matched_pattern': record.get('matched_pattern'),
                'filter_confidence': record.get('filter_confidence'),
                
                # Timestamps for time-series analysis
                'first_seen_at': self._format_timestamp(record.get('first_seen_at')),
                'last_attempt_at': self._format_timestamp(record.get('last_attempt_at')),
                'completed_at': self._format_timestamp(record.get('completed_at')),
                'created_at': self._format_timestamp(record.get('created_at')),
                'updated_at': self._format_timestamp(record.get('updated_at')),
                
                # Computed analytics fields
                'processing_date': self._extract_date(record.get('created_at')),
                'success_indicator': 1 if status_category == 'completed' else 0,
                'failure_indicator': 1 if status_category == 'failed' else 0,
                'filtered_indicator': 1 if status_category == 'filtered' else 0,
                'retry_indicator': 1 if (record.get('retry_count', 0) > 0) else 0
            }
            
        except Exception as e:
            logger.error(f"Error transforming single CDX record: {str(e)}")
            return None
    
    def _categorize_status(self, status: str) -> str:
        """Categorize status for analytics."""
        if not status:
            return 'unknown'
        
        status_lower = status.lower()
        
        if 'completed' in status_lower:
            return 'completed'
        elif 'failed' in status_lower or 'error' in status_lower:
            return 'failed'
        elif 'filtered' in status_lower or 'skipped' in status_lower:
            return 'filtered'
        elif 'pending' in status_lower:
            return 'pending'
        elif 'progress' in status_lower:
            return 'in_progress'
        else:
            return 'other'
    
    def _categorize_content_length(self, content_length: Optional[int]) -> str:
        """Categorize content length for analytics."""
        if content_length is None or content_length <= 0:
            return 'empty'
        elif content_length < 1024:
            return 'tiny'      # < 1KB
        elif content_length < 10240:
            return 'small'     # 1KB - 10KB
        elif content_length < 102400:
            return 'medium'    # 10KB - 100KB
        elif content_length < 1048576:
            return 'large'     # 100KB - 1MB
        else:
            return 'xlarge'    # > 1MB
    
    def _calculate_efficiency(self, processing_time: Optional[float], content_length: Optional[int]) -> float:
        """Calculate processing efficiency (bytes per second)."""
        if not processing_time or not content_length or processing_time <= 0:
            return 0.0
        return float(content_length) / processing_time
    
    def _format_timestamp(self, timestamp: Any) -> Optional[str]:
        """Format timestamp to ISO string."""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        elif isinstance(timestamp, str):
            return timestamp
        else:
            return str(timestamp)
    
    def _extract_date(self, timestamp: Any) -> Optional[str]:
        """Extract date from timestamp."""
        if timestamp is None:
            return None
        
        try:
            if isinstance(timestamp, datetime):
                return timestamp.date().isoformat()
            elif isinstance(timestamp, str):
                # Try to parse ISO format
                parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return parsed.date().isoformat()
        except Exception:
            pass
        
        return None
    
    def get_schema(self) -> pa.Schema:
        """Get PyArrow schema for CDX analytics data."""
        return pa.schema([
            # Core identifiers
            ('id', pa.int64()),
            ('domain_id', pa.int64()),
            ('scrape_session_id', pa.int64()),
            
            # URL analysis
            ('original_url', pa.string()),
            ('content_url', pa.string()),
            ('url_domain', pa.string()),
            ('url_path', pa.string()),
            ('url_scheme', pa.string()),
            ('url_depth', pa.int32()),
            ('url_has_params', pa.bool_()),
            
            # Temporal analysis
            ('unix_timestamp', pa.string()),
            ('capture_date', pa.date32()),
            ('capture_year', pa.int32()),
            ('capture_month', pa.int32()),
            ('capture_day_of_week', pa.int32()),
            
            # Content metadata
            ('mime_type', pa.string()),
            ('status_code', pa.int32()),
            ('content_length', pa.int64()),
            ('content_length_category', pa.string()),
            ('digest_hash', pa.string()),
            
            # Content analysis
            ('title', pa.string()),
            ('title_length', pa.int32()),
            ('has_extracted_content', pa.bool_()),
            ('is_pdf', pa.bool_()),
            ('is_duplicate', pa.bool_()),
            ('is_list_page', pa.bool_()),
            ('extraction_method', pa.string()),
            
            # Processing status
            ('status', pa.string()),
            ('status_category', pa.string()),
            ('retry_count', pa.int32()),
            ('max_retries', pa.int32()),
            ('error_type', pa.string()),
            ('has_error', pa.bool_()),
            
            # Performance metrics
            ('total_processing_time', pa.float64()),
            ('fetch_time', pa.float64()),
            ('extraction_time', pa.float64()),
            ('processing_efficiency', pa.float64()),
            
            # Filtering analysis
            ('filter_reason', pa.string()),
            ('filter_category', pa.string()),
            ('priority_score', pa.int32()),
            ('is_manually_overridden', pa.bool_()),
            ('matched_pattern', pa.string()),
            ('filter_confidence', pa.float64()),
            
            # Timestamps
            ('first_seen_at', pa.timestamp('us')),
            ('last_attempt_at', pa.timestamp('us')),
            ('completed_at', pa.timestamp('us')),
            ('created_at', pa.timestamp('us')),
            ('updated_at', pa.timestamp('us')),
            
            # Analytics indicators
            ('processing_date', pa.date32()),
            ('success_indicator', pa.int8()),
            ('failure_indicator', pa.int8()),
            ('filtered_indicator', pa.int8()),
            ('retry_indicator', pa.int8())
        ])


class ContentTransformer(BaseTransformer):
    """Transform extracted content data for content analytics."""
    
    def transform(self, data: List[Dict[str, Any]]) -> TransformationResult:
        """Transform content data to content analytics format."""
        start_time = datetime.utcnow()
        
        try:
            is_valid, errors = self.validate_input(data)
            if not is_valid:
                return TransformationResult(
                    success=False,
                    error=f"Input validation failed: {'; '.join(errors)}"
                )
            
            if not data:
                return TransformationResult(success=True, data=[], record_count=0)
            
            transformed_data = []
            warnings = []
            
            for record in data:
                try:
                    transformed_record = self._transform_content_record(record)
                    if transformed_record:
                        transformed_data.append(transformed_record)
                        self.transformation_stats["successful_transformations"] += 1
                    
                except Exception as e:
                    warning_msg = f"Failed to transform content record {record.get('id', 'unknown')}: {str(e)}"
                    warnings.append(warning_msg)
                    logger.warning(warning_msg)
                    self.transformation_stats["failed_transformations"] += 1
                
                self.transformation_stats["total_processed"] += 1
            
            end_time = datetime.utcnow()
            transformation_time = (end_time - start_time).total_seconds()
            
            return TransformationResult(
                success=True,
                data=transformed_data,
                warnings=warnings,
                record_count=len(transformed_data),
                transformation_time=transformation_time
            )
            
        except Exception as e:
            logger.error(f"Content transformation failed: {str(e)}")
            return TransformationResult(
                success=False,
                error=str(e)
            )
    
    def _transform_content_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform a single content record."""
        try:
            # Text analysis
            extracted_text = record.get('extracted_text', '') or ''
            markdown_content = record.get('markdown_content', '') or ''
            title = record.get('title', '') or ''
            
            # Content metrics
            text_length = len(extracted_text)
            markdown_length = len(markdown_content)
            title_length = len(title)
            
            # Language detection (basic)
            language = self._detect_language_basic(extracted_text)
            
            # Content quality indicators
            has_meaningful_content = text_length > 100
            title_quality = self._assess_title_quality(title)
            content_density = self._calculate_content_density(extracted_text, record.get('content_length', 0))
            
            return {
                'id': record.get('id'),
                'domain_id': record.get('domain_id'),
                'original_url': record.get('original_url'),
                
                # Content analysis
                'title': title[:500],  # Truncate for analytics
                'title_length': title_length,
                'title_quality_score': title_quality,
                'has_title': bool(title),
                
                'extracted_text_length': text_length,
                'markdown_content_length': markdown_length,
                'content_ratio': markdown_length / max(text_length, 1),
                'has_meaningful_content': has_meaningful_content,
                'content_density': content_density,
                
                # Language and content type
                'detected_language': language,
                'extraction_method': record.get('extraction_method'),
                'mime_type': record.get('mime_type'),
                'is_pdf': record.get('is_pdf', False),
                
                # Processing metrics
                'fetch_time': record.get('fetch_time', 0) or 0,
                'extraction_time': record.get('extraction_time', 0) or 0,
                'total_processing_time': record.get('total_processing_time', 0) or 0,
                
                # Content quality metrics
                'word_count': self._estimate_word_count(extracted_text),
                'paragraph_count': self._count_paragraphs(extracted_text),
                'link_count': self._count_links(markdown_content),
                'image_count': self._count_images(markdown_content),
                
                # Timestamps
                'created_at': self._format_timestamp(record.get('created_at')),
                'extraction_date': self._extract_date(record.get('created_at')),
                
                # Success indicators
                'extraction_successful': bool(extracted_text),
                'high_quality_content': has_meaningful_content and title_quality > 0.5
            }
            
        except Exception as e:
            logger.error(f"Error transforming content record: {str(e)}")
            return None
    
    def _detect_language_basic(self, text: str) -> str:
        """Basic language detection (placeholder for more sophisticated detection)."""
        if not text:
            return 'unknown'
        
        # Simple heuristic - count common English words
        english_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        words = set(text.lower().split()[:100])  # Check first 100 words
        english_count = len(words.intersection(english_words))
        
        if english_count > 3:
            return 'en'
        else:
            return 'other'
    
    def _assess_title_quality(self, title: str) -> float:
        """Assess title quality (0.0 to 1.0)."""
        if not title:
            return 0.0
        
        score = 0.0
        
        # Length check (good titles are 10-100 characters)
        if 10 <= len(title) <= 100:
            score += 0.3
        elif 5 <= len(title) < 10:
            score += 0.1
        
        # Word count check (2-15 words is good)
        word_count = len(title.split())
        if 2 <= word_count <= 15:
            score += 0.3
        
        # Check for meaningful content (not just numbers/symbols)
        if re.search(r'[a-zA-Z]', title):
            score += 0.2
        
        # Avoid generic titles
        generic_patterns = ['untitled', 'document', 'page', 'default', 'index', 'home']
        if not any(pattern in title.lower() for pattern in generic_patterns):
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_content_density(self, text: str, original_length: int) -> float:
        """Calculate content density (useful content vs original size)."""
        if not text or not original_length:
            return 0.0
        
        return len(text) / max(original_length, 1)
    
    def _estimate_word_count(self, text: str) -> int:
        """Estimate word count in text."""
        if not text:
            return 0
        return len(text.split())
    
    def _count_paragraphs(self, text: str) -> int:
        """Count paragraphs in text."""
        if not text:
            return 0
        return len([p for p in text.split('\n\n') if p.strip()])
    
    def _count_links(self, markdown: str) -> int:
        """Count links in markdown content."""
        if not markdown:
            return 0
        return len(re.findall(r'\[([^\]]+)\]\(([^)]+)\)', markdown))
    
    def _count_images(self, markdown: str) -> int:
        """Count images in markdown content."""
        if not markdown:
            return 0
        return len(re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', markdown))
    
    def _format_timestamp(self, timestamp: Any) -> Optional[str]:
        """Format timestamp to ISO string."""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        elif isinstance(timestamp, str):
            return timestamp
        else:
            return str(timestamp)
    
    def _extract_date(self, timestamp: Any) -> Optional[str]:
        """Extract date from timestamp."""
        if timestamp is None:
            return None
        
        try:
            if isinstance(timestamp, datetime):
                return timestamp.date().isoformat()
            elif isinstance(timestamp, str):
                parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return parsed.date().isoformat()
        except Exception:
            pass
        
        return None
    
    def get_schema(self) -> pa.Schema:
        """Get PyArrow schema for content analytics data."""
        return pa.schema([
            ('id', pa.int64()),
            ('domain_id', pa.int64()),
            ('original_url', pa.string()),
            
            # Content analysis
            ('title', pa.string()),
            ('title_length', pa.int32()),
            ('title_quality_score', pa.float64()),
            ('has_title', pa.bool_()),
            
            ('extracted_text_length', pa.int64()),
            ('markdown_content_length', pa.int64()),
            ('content_ratio', pa.float64()),
            ('has_meaningful_content', pa.bool_()),
            ('content_density', pa.float64()),
            
            # Language and type
            ('detected_language', pa.string()),
            ('extraction_method', pa.string()),
            ('mime_type', pa.string()),
            ('is_pdf', pa.bool_()),
            
            # Processing metrics
            ('fetch_time', pa.float64()),
            ('extraction_time', pa.float64()),
            ('total_processing_time', pa.float64()),
            
            # Content quality metrics
            ('word_count', pa.int32()),
            ('paragraph_count', pa.int32()),
            ('link_count', pa.int32()),
            ('image_count', pa.int32()),
            
            # Timestamps
            ('created_at', pa.timestamp('us')),
            ('extraction_date', pa.date32()),
            
            # Quality indicators
            ('extraction_successful', pa.bool_()),
            ('high_quality_content', pa.bool_())
        ])


class ProjectTransformer(BaseTransformer):
    """Transform project data for project analytics."""
    
    def transform(self, data: List[Dict[str, Any]]) -> TransformationResult:
        """Transform project data to project analytics format."""
        start_time = datetime.utcnow()
        
        try:
            is_valid, errors = self.validate_input(data)
            if not is_valid:
                return TransformationResult(
                    success=False,
                    error=f"Input validation failed: {'; '.join(errors)}"
                )
            
            if not data:
                return TransformationResult(success=True, data=[], record_count=0)
            
            # Project data is already aggregated, so we just need to format it
            transformed_data = []
            warnings = []
            
            for record in data:
                try:
                    transformed_record = self._transform_project_record(record)
                    if transformed_record:
                        transformed_data.append(transformed_record)
                        self.transformation_stats["successful_transformations"] += 1
                    
                except Exception as e:
                    warning_msg = f"Failed to transform project record {record.get('id', 'unknown')}: {str(e)}"
                    warnings.append(warning_msg)
                    self.transformation_stats["failed_transformations"] += 1
                
                self.transformation_stats["total_processed"] += 1
            
            end_time = datetime.utcnow()
            transformation_time = (end_time - start_time).total_seconds()
            
            return TransformationResult(
                success=True,
                data=transformed_data,
                warnings=warnings,
                record_count=len(transformed_data),
                transformation_time=transformation_time
            )
            
        except Exception as e:
            logger.error(f"Project transformation failed: {str(e)}")
            return TransformationResult(
                success=False,
                error=str(e)
            )
    
    def _transform_project_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform a single project record."""
        try:
            total_pages = record.get('total_pages', 0)
            successful = record.get('successful_extractions', 0)
            failed = record.get('failed_extractions', 0)
            
            return {
                'id': record.get('id'),
                'name': record.get('name', ''),
                'created_at': self._format_timestamp(record.get('created_at')),
                'creation_date': self._extract_date(record.get('created_at')),
                
                # Core metrics
                'total_pages': total_pages,
                'successful_extractions': successful,
                'failed_extractions': failed,
                'success_rate': record.get('success_rate', 0.0),
                
                # Performance metrics
                'avg_processing_time': record.get('avg_processing_time', 0.0),
                'unique_domains': record.get('unique_domains', 0),
                'total_content_size': record.get('total_content_size', 0),
                
                # Activity metrics
                'last_activity': self._format_timestamp(record.get('last_activity')),
                'days_since_creation': self._calculate_days_since(record.get('created_at')),
                'days_since_activity': self._calculate_days_since(record.get('last_activity')),
                
                # Derived analytics
                'is_active': self._is_project_active(record.get('last_activity')),
                'size_category': self._categorize_project_size(total_pages),
                'performance_category': self._categorize_performance(record.get('success_rate', 0.0)),
                'content_per_page': (record.get('total_content_size', 0) / max(total_pages, 1)) if total_pages else 0
            }
            
        except Exception as e:
            logger.error(f"Error transforming project record: {str(e)}")
            return None
    
    def _is_project_active(self, last_activity: Any) -> bool:
        """Check if project is active (activity within last 30 days)."""
        if not last_activity:
            return False
        
        try:
            if isinstance(last_activity, str):
                last_activity = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
            elif not isinstance(last_activity, datetime):
                return False
            
            days_since = (datetime.utcnow() - last_activity).days
            return days_since <= 30
            
        except Exception:
            return False
    
    def _categorize_project_size(self, total_pages: int) -> str:
        """Categorize project by size."""
        if total_pages == 0:
            return 'empty'
        elif total_pages < 100:
            return 'small'
        elif total_pages < 1000:
            return 'medium'
        elif total_pages < 10000:
            return 'large'
        else:
            return 'xlarge'
    
    def _categorize_performance(self, success_rate: float) -> str:
        """Categorize project performance."""
        if success_rate >= 0.9:
            return 'excellent'
        elif success_rate >= 0.7:
            return 'good'
        elif success_rate >= 0.5:
            return 'fair'
        else:
            return 'poor'
    
    def _calculate_days_since(self, timestamp: Any) -> Optional[int]:
        """Calculate days since timestamp."""
        if not timestamp:
            return None
        
        try:
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            elif not isinstance(timestamp, datetime):
                return None
            
            return (datetime.utcnow() - timestamp).days
            
        except Exception:
            return None
    
    def _format_timestamp(self, timestamp: Any) -> Optional[str]:
        """Format timestamp to ISO string."""
        if timestamp is None:
            return None
        
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        elif isinstance(timestamp, str):
            return timestamp
        else:
            return str(timestamp)
    
    def _extract_date(self, timestamp: Any) -> Optional[str]:
        """Extract date from timestamp."""
        if timestamp is None:
            return None
        
        try:
            if isinstance(timestamp, datetime):
                return timestamp.date().isoformat()
            elif isinstance(timestamp, str):
                parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return parsed.date().isoformat()
        except Exception:
            pass
        
        return None
    
    def get_schema(self) -> pa.Schema:
        """Get PyArrow schema for project analytics data."""
        return pa.schema([
            ('id', pa.int64()),
            ('name', pa.string()),
            ('created_at', pa.timestamp('us')),
            ('creation_date', pa.date32()),
            
            # Core metrics
            ('total_pages', pa.int64()),
            ('successful_extractions', pa.int64()),
            ('failed_extractions', pa.int64()),
            ('success_rate', pa.float64()),
            
            # Performance metrics
            ('avg_processing_time', pa.float64()),
            ('unique_domains', pa.int32()),
            ('total_content_size', pa.int64()),
            
            # Activity metrics
            ('last_activity', pa.timestamp('us')),
            ('days_since_creation', pa.int32()),
            ('days_since_activity', pa.int32()),
            
            # Categories
            ('is_active', pa.bool_()),
            ('size_category', pa.string()),
            ('performance_category', pa.string()),
            ('content_per_page', pa.float64())
        ])


class EventTransformer(BaseTransformer):
    """Transform system events for analytics."""
    
    def transform(self, data: List[Dict[str, Any]]) -> TransformationResult:
        """Transform event data to analytics format."""
        start_time = datetime.utcnow()
        
        try:
            is_valid, errors = self.validate_input(data)
            if not is_valid:
                return TransformationResult(
                    success=False,
                    error=f"Input validation failed: {'; '.join(errors)}"
                )
            
            if not data:
                return TransformationResult(success=True, data=[], record_count=0)
            
            # Events are typically already in good format
            transformed_data = []
            warnings = []
            
            for record in data:
                try:
                    transformed_record = self._ensure_event_format(record)
                    if transformed_record:
                        transformed_data.append(transformed_record)
                        self.transformation_stats["successful_transformations"] += 1
                    
                except Exception as e:
                    warning_msg = f"Failed to transform event record: {str(e)}"
                    warnings.append(warning_msg)
                    self.transformation_stats["failed_transformations"] += 1
                
                self.transformation_stats["total_processed"] += 1
            
            end_time = datetime.utcnow()
            transformation_time = (end_time - start_time).total_seconds()
            
            return TransformationResult(
                success=True,
                data=transformed_data,
                warnings=warnings,
                record_count=len(transformed_data),
                transformation_time=transformation_time
            )
            
        except Exception as e:
            logger.error(f"Event transformation failed: {str(e)}")
            return TransformationResult(
                success=False,
                error=str(e)
            )
    
    def _ensure_event_format(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure event record has proper format."""
        return {
            'event_id': record.get('event_id', self._generate_event_id()),
            'event_type': record.get('event_type', 'unknown'),
            'event_category': record.get('event_category', 'system'),
            'timestamp': self._format_timestamp(record.get('timestamp', datetime.utcnow())),
            'event_date': self._extract_date(record.get('timestamp', datetime.utcnow())),
            'user_id': record.get('user_id'),
            'session_id': record.get('session_id'),
            'project_id': record.get('project_id'),
            'domain_id': record.get('domain_id'),
            'message': record.get('message', ''),
            'level': record.get('level', 'info'),
            'details': json.dumps(record.get('details', {})) if record.get('details') else None,
            'source': record.get('source', 'system'),
            'ip_address': record.get('ip_address'),
            'user_agent': record.get('user_agent')
        }
    
    def _generate_event_id(self) -> str:
        """Generate a unique event ID."""
        timestamp = datetime.utcnow().isoformat()
        return hashlib.md5(timestamp.encode()).hexdigest()[:16]
    
    def _format_timestamp(self, timestamp: Any) -> str:
        """Format timestamp to ISO string."""
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        elif isinstance(timestamp, str):
            return timestamp
        else:
            return datetime.utcnow().isoformat()
    
    def _extract_date(self, timestamp: Any) -> Optional[str]:
        """Extract date from timestamp."""
        try:
            if isinstance(timestamp, datetime):
                return timestamp.date().isoformat()
            elif isinstance(timestamp, str):
                parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return parsed.date().isoformat()
            else:
                return datetime.utcnow().date().isoformat()
        except Exception:
            return datetime.utcnow().date().isoformat()
    
    def get_schema(self) -> pa.Schema:
        """Get PyArrow schema for event data."""
        return pa.schema([
            ('event_id', pa.string()),
            ('event_type', pa.string()),
            ('event_category', pa.string()),
            ('timestamp', pa.timestamp('us')),
            ('event_date', pa.date32()),
            ('user_id', pa.int64()),
            ('session_id', pa.string()),
            ('project_id', pa.int64()),
            ('domain_id', pa.int64()),
            ('message', pa.string()),
            ('level', pa.string()),
            ('details', pa.string()),  # JSON string
            ('source', pa.string()),
            ('ip_address', pa.string()),
            ('user_agent', pa.string())
        ])