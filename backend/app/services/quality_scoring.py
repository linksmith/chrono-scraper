"""
Content quality scoring service
"""
import re
import math
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.project import Page, Domain, Project

logger = logging.getLogger(__name__)


class QualityMetrics:
    """Container for quality metrics"""
    
    def __init__(self):
        self.readability_score: float = 0.0
        self.content_completeness: float = 0.0
        self.metadata_richness: float = 0.0
        self.uniqueness_score: float = 0.0
        self.structural_quality: float = 0.0
        self.overall_score: float = 0.0
        self.quality_issues: List[str] = []
        self.quality_strengths: List[str] = []


class QualityScoringService:
    """Service for scoring content quality"""
    
    # Quality thresholds
    EXCELLENT_THRESHOLD = 85
    GOOD_THRESHOLD = 70
    FAIR_THRESHOLD = 50
    POOR_THRESHOLD = 30
    
    @staticmethod
    def calculate_readability_score(text: str) -> Tuple[float, List[str]]:
        """
        Calculate readability score using multiple metrics
        Returns score (0-100) and list of readability insights
        """
        if not text or len(text.strip()) == 0:
            return 0.0, ["No content to analyze"]
        
        issues = []
        strengths = []
        
        # Word and sentence counts
        words = text.split()
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) == 0:
            return 0.0, ["No sentences found"]
        
        avg_words_per_sentence = len(words) / len(sentences)
        
        # Flesch Reading Ease approximation
        # Formula: 206.835 - 1.015 * (avg_words_per_sentence) - 84.6 * (avg_syllables_per_word)
        # Simplified syllable counting
        syllable_count = sum(QualityScoringService._count_syllables(word) for word in words)
        avg_syllables_per_word = syllable_count / len(words) if words else 0
        
        flesch_score = 206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)
        flesch_score = max(0, min(100, flesch_score))  # Clamp between 0-100
        
        # Readability insights
        if avg_words_per_sentence > 25:
            issues.append("Very long sentences (average > 25 words)")
        elif avg_words_per_sentence < 8:
            issues.append("Very short sentences (average < 8 words)")
        else:
            strengths.append("Good sentence length balance")
        
        if avg_syllables_per_word > 2.0:
            issues.append("Complex vocabulary (high syllable count)")
        elif avg_syllables_per_word < 1.3:
            strengths.append("Simple, accessible vocabulary")
        
        # Paragraph structure (approximate)
        paragraphs = text.split('\n\n')
        avg_sentences_per_paragraph = len(sentences) / len(paragraphs) if paragraphs else 0
        
        if avg_sentences_per_paragraph > 8:
            issues.append("Very long paragraphs")
        elif 3 <= avg_sentences_per_paragraph <= 6:
            strengths.append("Well-structured paragraphs")
        
        all_insights = issues + strengths
        return flesch_score, all_insights
    
    @staticmethod
    def _count_syllables(word: str) -> int:
        """
        Simple syllable counting heuristic
        """
        word = word.lower()
        vowels = 'aeiouy'
        syllable_count = 0
        prev_char_was_vowel = False
        
        for char in word:
            if char in vowels:
                if not prev_char_was_vowel:
                    syllable_count += 1
                prev_char_was_vowel = True
            else:
                prev_char_was_vowel = False
        
        # Handle silent 'e'
        if word.endswith('e') and syllable_count > 1:
            syllable_count -= 1
        
        return max(1, syllable_count)  # Every word has at least 1 syllable
    
    @staticmethod
    def calculate_content_completeness(page_data: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Calculate how complete the content is based on various factors
        """
        score = 0
        max_score = 100
        issues = []
        strengths = []
        
        # Title presence and quality (20 points)
        title = page_data.get('extracted_title', '').strip()
        if title:
            score += 15
            if len(title) >= 30 and len(title) <= 60:
                score += 5
                strengths.append("Good title length (30-60 characters)")
            elif len(title) < 10:
                issues.append("Very short title")
            elif len(title) > 100:
                issues.append("Very long title")
        else:
            issues.append("Missing title")
        
        # Content length (25 points)
        word_count = page_data.get('word_count', 0)
        if word_count >= 300:
            score += 20
            if word_count >= 1000:
                score += 5
                strengths.append("Substantial content (1000+ words)")
        elif word_count >= 150:
            score += 10
            issues.append("Short content (150-300 words)")
        elif word_count > 0:
            score += 5
            issues.append("Very short content (<150 words)")
        else:
            issues.append("No content extracted")
        
        # Meta description (15 points)
        meta_desc = page_data.get('meta_description', '').strip()
        if meta_desc:
            score += 10
            if 120 <= len(meta_desc) <= 160:
                score += 5
                strengths.append("Optimal meta description length")
            elif len(meta_desc) < 50:
                issues.append("Short meta description")
        else:
            issues.append("Missing meta description")
        
        # Author information (10 points)
        if page_data.get('author'):
            score += 10
            strengths.append("Author information present")
        else:
            issues.append("Missing author information")
        
        # Publication date (10 points)
        if page_data.get('published_date'):
            score += 10
            strengths.append("Publication date available")
        else:
            issues.append("Missing publication date")
        
        # Language detection (5 points)
        if page_data.get('language'):
            score += 5
            strengths.append("Language detected")
        
        # Content structure indicators (15 points)
        extracted_content = page_data.get('extracted_content', '')
        if extracted_content:
            # Check for headings
            heading_indicators = ['<h1', '<h2', '<h3', '<h4', '<h5', '<h6']
            has_headings = any(indicator in extracted_content.lower() for indicator in heading_indicators)
            
            if has_headings:
                score += 8
                strengths.append("Well-structured with headings")
            else:
                issues.append("No clear heading structure")
            
            # Check for lists
            list_indicators = ['<ul', '<ol', '<li']
            has_lists = any(indicator in extracted_content.lower() for indicator in list_indicators)
            
            if has_lists:
                score += 4
                strengths.append("Contains organized lists")
            
            # Check for links
            if '<a href' in extracted_content.lower():
                score += 3
                strengths.append("Contains relevant links")
        
        return min(score, max_score), issues + strengths
    
    @staticmethod
    def calculate_metadata_richness(page_data: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Calculate richness of metadata
        """
        score = 0
        max_score = 100
        issues = []
        strengths = []
        
        metadata_fields = [
            ('extracted_title', 'title', 20),
            ('meta_description', 'meta description', 15),
            ('meta_keywords', 'keywords', 10),
            ('author', 'author', 15),
            ('published_date', 'publication date', 15),
            ('language', 'language', 10),
            ('content_type', 'content type', 5),
            ('status_code', 'HTTP status', 5),
            ('content_length', 'content size', 5)
        ]
        
        for field, label, points in metadata_fields:
            value = page_data.get(field)
            if value and str(value).strip():
                score += points
                strengths.append(f"{label.title()} present")
            else:
                issues.append(f"Missing {label}")
        
        return min(score, max_score), issues + strengths
    
    @staticmethod
    async def calculate_uniqueness_score(
        db: AsyncSession,
        page_id: int,
        content_hash: Optional[str],
        domain_id: int
    ) -> Tuple[float, List[str]]:
        """
        Calculate content uniqueness score
        """
        issues = []
        strengths = []
        
        if not content_hash:
            return 0.0, ["No content hash available for uniqueness check"]
        
        # Check for exact duplicates
        duplicate_query = (
            select(func.count(Page.id))
            .where(
                Page.content_hash == content_hash,
                Page.id != page_id
            )
        )
        
        duplicate_result = await db.execute(duplicate_query)
        duplicate_count = duplicate_result.scalar() or 0
        
        if duplicate_count == 0:
            strengths.append("Content is unique")
            uniqueness_score = 100.0
        elif duplicate_count <= 2:
            issues.append(f"Content duplicated in {duplicate_count} other pages")
            uniqueness_score = 70.0
        elif duplicate_count <= 5:
            issues.append(f"Content duplicated in {duplicate_count} other pages")
            uniqueness_score = 40.0
        else:
            issues.append(f"Content heavily duplicated ({duplicate_count} duplicates)")
            uniqueness_score = 10.0
        
        # Check for domain-specific duplicates
        domain_duplicate_query = (
            select(func.count(Page.id))
            .where(
                Page.content_hash == content_hash,
                Page.domain_id == domain_id,
                Page.id != page_id
            )
        )
        
        domain_duplicate_result = await db.execute(domain_duplicate_query)
        domain_duplicates = domain_duplicate_result.scalar() or 0
        
        if domain_duplicates > 0:
            issues.append(f"Content duplicated {domain_duplicates} times within same domain")
            uniqueness_score *= 0.8  # Reduce score for same-domain duplicates
        
        return uniqueness_score, issues + strengths
    
    @staticmethod
    def calculate_structural_quality(extracted_content: str, extracted_text: str) -> Tuple[float, List[str]]:
        """
        Calculate structural quality based on HTML structure
        """
        if not extracted_content:
            return 0.0, ["No HTML content available for structure analysis"]
        
        score = 0
        max_score = 100
        issues = []
        strengths = []
        
        content_lower = extracted_content.lower()
        
        # Heading hierarchy (25 points)
        headings = {
            'h1': len(re.findall(r'<h1[^>]*>', content_lower)),
            'h2': len(re.findall(r'<h2[^>]*>', content_lower)),
            'h3': len(re.findall(r'<h3[^>]*>', content_lower)),
            'h4': len(re.findall(r'<h4[^>]*>', content_lower))
        }
        
        if headings['h1'] == 1:
            score += 10
            strengths.append("Single H1 heading (good practice)")
        elif headings['h1'] > 1:
            issues.append("Multiple H1 headings")
        else:
            issues.append("No H1 heading")
        
        if headings['h2'] > 0:
            score += 10
            strengths.append("Contains section headings (H2)")
        
        if sum(headings.values()) >= 3:
            score += 5
            strengths.append("Good heading structure")
        
        # Paragraph structure (20 points)
        paragraphs = re.findall(r'<p[^>]*>.*?</p>', extracted_content, re.DOTALL)
        if len(paragraphs) >= 3:
            score += 15
            strengths.append("Well-paragraphed content")
            
            # Check paragraph lengths
            avg_paragraph_length = sum(len(p) for p in paragraphs) / len(paragraphs)
            if 100 <= avg_paragraph_length <= 500:
                score += 5
                strengths.append("Good paragraph length")
        else:
            issues.append("Poor paragraph structure")
        
        # Lists (15 points)
        lists = re.findall(r'<[uo]l[^>]*>.*?</[uo]l>', content_lower, re.DOTALL)
        if lists:
            score += 10
            strengths.append("Contains organized lists")
            
            # Check for nested lists
            if any('<ul' in lst or '<ol' in lst for lst in lists):
                score += 5
                strengths.append("Contains nested lists")
        
        # Links (15 points)
        internal_links = re.findall(r'<a[^>]+href=["\'][^"\']*["\'][^>]*>', content_lower)
        if internal_links:
            score += 10
            strengths.append("Contains links")
            
            if len(internal_links) <= 10:
                score += 5
                strengths.append("Appropriate number of links")
            else:
                issues.append("Too many links (potential spam)")
        
        # Images and media (10 points)
        images = re.findall(r'<img[^>]+>', content_lower)
        if images:
            score += 5
            strengths.append("Contains images")
            
            # Check for alt tags
            images_with_alt = [img for img in images if 'alt=' in img]
            if len(images_with_alt) == len(images):
                score += 5
                strengths.append("All images have alt text")
            elif images_with_alt:
                issues.append("Some images missing alt text")
            else:
                issues.append("Images missing alt text")
        
        # Content to markup ratio (15 points)
        if extracted_text:
            text_length = len(extracted_text)
            markup_length = len(extracted_content)
            
            if markup_length > 0:
                ratio = text_length / markup_length
                if ratio >= 0.25:  # At least 25% content
                    score += 15
                    strengths.append("Good content-to-markup ratio")
                elif ratio >= 0.15:
                    score += 10
                    issues.append("Moderate content-to-markup ratio")
                else:
                    issues.append("Poor content-to-markup ratio (too much markup)")
        
        return min(score, max_score), issues + strengths
    
    @staticmethod
    async def calculate_quality_score(
        db: AsyncSession,
        page_id: int
    ) -> Optional[QualityMetrics]:
        """
        Calculate overall quality score for a page
        """
        # Get page data
        page_query = (
            select(Page, Domain)
            .join(Domain, Page.domain_id == Domain.id)
            .where(Page.id == page_id)
        )
        
        result = await db.execute(page_query)
        page_row = result.first()
        
        if not page_row:
            return None
        
        page, domain = page_row
        
        # Prepare page data
        page_data = {
            'extracted_title': page.extracted_title,
            'extracted_text': page.extracted_text,
            # 'extracted_content' removed in schema optimization
            'meta_description': page.meta_description,
            'meta_keywords': page.meta_keywords,
            'author': page.author,
            'published_date': page.published_date,
            'language': page.language,
            'word_count': page.word_count,
            'character_count': page.character_count,
            'content_type': page.content_type,
            'status_code': page.status_code,
            'content_length': page.content_length
        }
        
        metrics = QualityMetrics()
        
        # Calculate individual scores
        if page.extracted_text:
            metrics.readability_score, readability_insights = (
                QualityScoringService.calculate_readability_score(page.extracted_text)
            )
        
        metrics.content_completeness, completeness_insights = (
            QualityScoringService.calculate_content_completeness(page_data)
        )
        
        metrics.metadata_richness, metadata_insights = (
            QualityScoringService.calculate_metadata_richness(page_data)
        )
        
        metrics.uniqueness_score, uniqueness_insights = await (
            QualityScoringService.calculate_uniqueness_score(
                db, page_id, page.content_hash, page.domain_id
            )
        )
        
        metrics.structural_quality, structural_insights = (
            QualityScoringService.calculate_structural_quality(
                page.extracted_text or '', page.extracted_text or ''  # Use extracted_text for both
            )
        )
        
        # Calculate weighted overall score
        weights = {
            'content_completeness': 0.30,
            'readability': 0.25,
            'metadata_richness': 0.20,
            'uniqueness': 0.15,
            'structural_quality': 0.10
        }
        
        metrics.overall_score = (
            metrics.content_completeness * weights['content_completeness'] +
            metrics.readability_score * weights['readability'] +
            metrics.metadata_richness * weights['metadata_richness'] +
            metrics.uniqueness_score * weights['uniqueness'] +
            metrics.structural_quality * weights['structural_quality']
        )
        
        # Collect all insights
        all_insights = (
            readability_insights + completeness_insights + 
            metadata_insights + uniqueness_insights + structural_insights
        )
        
        # Separate issues and strengths
        for insight in all_insights:
            if any(word in insight.lower() for word in ['missing', 'no', 'poor', 'short', 'long', 'failed']):
                metrics.quality_issues.append(insight)
            else:
                metrics.quality_strengths.append(insight)
        
        return metrics
    
    @staticmethod
    def get_quality_grade(score: float) -> str:
        """Get letter grade for quality score"""
        if score >= QualityScoringService.EXCELLENT_THRESHOLD:
            return 'A'
        elif score >= QualityScoringService.GOOD_THRESHOLD:
            return 'B'
        elif score >= QualityScoringService.FAIR_THRESHOLD:
            return 'C'
        elif score >= QualityScoringService.POOR_THRESHOLD:
            return 'D'
        else:
            return 'F'
    
    @staticmethod
    def get_quality_description(score: float) -> str:
        """Get quality description for score"""
        if score >= QualityScoringService.EXCELLENT_THRESHOLD:
            return 'Excellent'
        elif score >= QualityScoringService.GOOD_THRESHOLD:
            return 'Good'
        elif score >= QualityScoringService.FAIR_THRESHOLD:
            return 'Fair'
        elif score >= QualityScoringService.POOR_THRESHOLD:
            return 'Poor'
        else:
            return 'Very Poor'
    
    @staticmethod
    async def get_project_quality_overview(
        db: AsyncSession,
        project_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get quality overview for all pages in a project
        """
        # This would require quality scores to be stored in the database
        # For now, return a placeholder structure
        
        pages_query = (
            select(func.count(Page.id))
            .join(Domain)
            .join(Project)
            .where(Project.id == project_id)
        )
        
        if user_id:
            pages_query = pages_query.where(Project.user_id == user_id)
        
        total_pages_result = await db.execute(pages_query)
        total_pages = total_pages_result.scalar() or 0
        
        return {
            "project_id": project_id,
            "total_pages": total_pages,
            "quality_distribution": {
                "excellent": 0,  # Would calculate from stored scores
                "good": 0,
                "fair": 0,
                "poor": 0,
                "very_poor": 0
            },
            "average_score": 0.0,
            "top_issues": [],
            "improvement_suggestions": [],
            "last_analyzed": datetime.utcnow().isoformat()
        }