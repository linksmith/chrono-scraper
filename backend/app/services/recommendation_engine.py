"""
Content recommendation engine
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import Counter
from sqlmodel import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Domain, Project
from app.models.shared_pages import PageV2 as Page
from app.services.semantic_search import semantic_search_service

logger = logging.getLogger(__name__)


class UserProfile:
    """User interaction profile for recommendations"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.viewed_pages: List[int] = []
        self.search_queries: List[str] = []
        self.preferred_domains: List[str] = []
        self.preferred_topics: List[str] = []
        self.content_types: List[str] = []
        self.language_preferences: List[str] = []
        self.interaction_weights: Dict[str, float] = {
            'view': 1.0,
            'search': 2.0,
            'similar_content': 1.5,
            'export': 3.0
        }


class RecommendationEngine:
    """Content recommendation engine"""
    
    def __init__(self):
        self.user_profiles: Dict[int, UserProfile] = {}
        self.content_features_cache: Dict[int, Dict[str, Any]] = {}
        self.recommendation_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.cache_expiry_hours = 6
    
    def get_user_profile(self, user_id: int) -> UserProfile:
        """Get or create user profile"""
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = UserProfile(user_id)
        return self.user_profiles[user_id]
    
    async def track_user_interaction(
        self,
        db: AsyncSession,
        user_id: int,
        interaction_type: str,
        page_id: Optional[int] = None,
        query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Track user interaction for personalization"""
        try:
            profile = self.get_user_profile(user_id)
            
            if interaction_type == 'view' and page_id:
                profile.viewed_pages.append(page_id)
                # Keep only recent views (last 100)
                profile.viewed_pages = profile.viewed_pages[-100:]
                
                # Extract page features for profiling
                await self._update_user_preferences_from_page(db, profile, page_id)
            
            elif interaction_type == 'search' and query:
                profile.search_queries.append(query.lower())
                # Keep only recent searches
                profile.search_queries = profile.search_queries[-50:]
            
            # Invalidate recommendation cache for this user
            cache_key = f"recommendations_{user_id}"
            if cache_key in self.recommendation_cache:
                del self.recommendation_cache[cache_key]
                
            logger.debug(f"Tracked {interaction_type} interaction for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to track user interaction: {e}")
    
    async def _update_user_preferences_from_page(
        self,
        db: AsyncSession,
        profile: UserProfile,
        page_id: int
    ):
        """Update user preferences based on viewed page"""
        try:
            page_query = select(Page, Domain).join(Domain).where(Page.id == page_id)
            result = await db.execute(page_query)
            page_row = result.first()
            
            if not page_row:
                return
            
            page, domain = page_row
            
            # Update domain preferences
            if domain.domain_name not in profile.preferred_domains:
                profile.preferred_domains.append(domain.domain_name)
            
            # Update content type preferences
            if page.content_type and page.content_type not in profile.content_types:
                profile.content_types.append(page.content_type)
            
            # Update language preferences
            if page.language and page.language not in profile.language_preferences:
                profile.language_preferences.append(page.language)
            
            # Extract topics from content (simplified keyword extraction)
            if page.extracted_text:
                topics = self._extract_topics_from_text(page.extracted_text)
                for topic in topics:
                    if topic not in profile.preferred_topics:
                        profile.preferred_topics.append(topic)
                        
                # Keep only top 20 topics
                profile.preferred_topics = profile.preferred_topics[-20:]
                
        except Exception as e:
            logger.error(f"Failed to update user preferences: {e}")
    
    def _extract_topics_from_text(self, text: str) -> List[str]:
        """Extract topic keywords from text (simplified)"""
        try:
            # Simple keyword extraction based on word frequency
            words = text.lower().split()
            
            # Remove common stop words
            stop_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
                'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
                'may', 'might', 'can', 'this', 'that', 'these', 'those', 'i', 'you',
                'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
            }
            
            # Filter and count words
            filtered_words = [
                word for word in words 
                if len(word) > 3 and word not in stop_words and word.isalpha()
            ]
            
            # Get most common words as topics
            word_counts = Counter(filtered_words)
            topics = [word for word, count in word_counts.most_common(10) if count > 1]
            
            return topics
            
        except Exception as e:
            logger.error(f"Failed to extract topics: {e}")
            return []
    
    async def get_personalized_recommendations(
        self,
        db: AsyncSession,
        user_id: int,
        project_id: Optional[int] = None,
        limit: int = 20,
        exclude_viewed: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get personalized content recommendations for a user
        """
        try:
            # Check cache first
            cache_key = f"recommendations_{user_id}_{project_id}_{limit}"
            if cache_key in self.recommendation_cache:
                cached_result = self.recommendation_cache[cache_key]
                cache_time = cached_result.get('timestamp', 0)
                if datetime.utcnow().timestamp() - cache_time < (self.cache_expiry_hours * 3600):
                    return cached_result.get('recommendations', [])
            
            profile = self.get_user_profile(user_id)
            recommendations = []
            
            # Get content-based recommendations
            content_recs = await self._get_content_based_recommendations(
                db, profile, project_id, limit // 2, exclude_viewed
            )
            recommendations.extend(content_recs)
            
            # Get collaborative filtering recommendations
            collab_recs = await self._get_collaborative_recommendations(
                db, profile, project_id, limit // 2, exclude_viewed
            )
            recommendations.extend(collab_recs)
            
            # Get trending content recommendations
            trending_recs = await self._get_trending_recommendations(
                db, project_id, limit // 4, exclude_viewed, profile
            )
            recommendations.extend(trending_recs)
            
            # Remove duplicates and sort by score
            seen_pages = set()
            unique_recommendations = []
            for rec in recommendations:
                if rec['page_id'] not in seen_pages:
                    seen_pages.add(rec['page_id'])
                    unique_recommendations.append(rec)
            
            # Sort by recommendation score
            unique_recommendations.sort(key=lambda x: x.get('score', 0), reverse=True)
            
            # Limit results
            final_recommendations = unique_recommendations[:limit]
            
            # Cache results
            self.recommendation_cache[cache_key] = {
                'recommendations': final_recommendations,
                'timestamp': datetime.utcnow().timestamp()
            }
            
            return final_recommendations
            
        except Exception as e:
            logger.error(f"Failed to get personalized recommendations: {e}")
            return []
    
    async def _get_content_based_recommendations(
        self,
        db: AsyncSession,
        profile: UserProfile,
        project_id: Optional[int],
        limit: int,
        exclude_viewed: bool
    ) -> List[Dict[str, Any]]:
        """Get content-based recommendations using user preferences"""
        try:
            recommendations = []
            
            # Build query based on user preferences
            base_query = select(
                Page.id,
                Page.original_url,
                Page.extracted_title,
                Page.extracted_text,
                Page.meta_description,
                Page.word_count,
                Page.scraped_at,
                Page.language,
                Page.content_type,
                Domain.domain_name
            ).join(Domain, Page.domain_id == Domain.id)
            
            # Add project filter
            if project_id:
                base_query = base_query.join(Project).where(Project.id == project_id)
            
            # Exclude viewed pages
            if exclude_viewed and profile.viewed_pages:
                base_query = base_query.where(~Page.id.in_(profile.viewed_pages))
            
            # Filter by user preferences
            preference_filters = []
            
            # Domain preferences
            if profile.preferred_domains:
                preference_filters.append(Domain.domain_name.in_(profile.preferred_domains))
            
            # Language preferences
            if profile.language_preferences:
                preference_filters.append(Page.language.in_(profile.language_preferences))
            
            # Content type preferences
            if profile.content_types:
                preference_filters.append(Page.content_type.in_(profile.content_types))
            
            if preference_filters:
                base_query = base_query.where(or_(*preference_filters))
            
            # Only pages with content
            base_query = base_query.where(
                Page.extracted_text.is_not(None),
                func.length(Page.extracted_text) > 100
            )
            
            # Order by recency and limit
            base_query = base_query.order_by(Page.scraped_at.desc()).limit(limit * 2)
            
            result = await db.execute(base_query)
            pages = result.all()
            
            # Score pages based on topic overlap
            for page in pages:
                score = self._calculate_content_similarity_score(profile, page)
                
                if score > 0.1:  # Minimum relevance threshold
                    recommendations.append({
                        'page_id': page.id,
                        'url': page.original_url,
                        'title': page.extracted_title,
                        'description': page.meta_description,
                        'content_preview': (page.extracted_text or '')[:300] + '...' if page.extracted_text else '',
                        'word_count': page.word_count,
                        'domain_name': page.domain_name,
                        'scraped_at': page.scraped_at.isoformat() if page.scraped_at else None,
                        'score': score,
                        'recommendation_type': 'content_based'
                    })
            
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get content-based recommendations: {e}")
            return []
    
    def _calculate_content_similarity_score(
        self,
        profile: UserProfile,
        page: Any
    ) -> float:
        """Calculate content similarity score based on user preferences"""
        try:
            score = 0.0
            
            # Domain preference boost
            if page.domain_name in profile.preferred_domains:
                score += 0.3
            
            # Language preference boost
            if page.language in profile.language_preferences:
                score += 0.2
            
            # Content type preference boost
            if page.content_type in profile.content_types:
                score += 0.1
            
            # Topic similarity boost
            if page.extracted_text and profile.preferred_topics:
                page_topics = self._extract_topics_from_text(page.extracted_text)
                topic_overlap = len(set(page_topics) & set(profile.preferred_topics))
                if len(profile.preferred_topics) > 0:
                    topic_score = topic_overlap / len(profile.preferred_topics)
                    score += topic_score * 0.4
            
            # Quality boost (based on word count and title presence)
            if page.extracted_title:
                score += 0.1
            
            if page.word_count and page.word_count > 500:
                score += 0.1
            
            return min(score, 1.0)  # Cap at 1.0
            
        except Exception as e:
            logger.error(f"Failed to calculate content similarity score: {e}")
            return 0.0
    
    async def _get_collaborative_recommendations(
        self,
        db: AsyncSession,
        profile: UserProfile,
        project_id: Optional[int],
        limit: int,
        exclude_viewed: bool
    ) -> List[Dict[str, Any]]:
        """Get collaborative filtering recommendations (simplified)"""
        try:
            # In a full implementation, this would use user-item interaction matrix
            # For now, we'll recommend pages similar to user's viewed content
            recommendations = []
            
            if not profile.viewed_pages:
                return recommendations
            
            # Get a few recent viewed pages to find similar content
            recent_views = profile.viewed_pages[-5:]
            
            for page_id in recent_views:
                similar_content = await semantic_search_service.find_similar_content(
                    db=db,
                    page_id=page_id,
                    limit=5,
                    min_similarity=0.6
                )
                
                for similar in similar_content:
                    if exclude_viewed and similar['page_id'] in profile.viewed_pages:
                        continue
                    
                    similar['score'] = similar.get('similarity_score', 0.5) * 0.8
                    similar['recommendation_type'] = 'collaborative'
                    recommendations.append(similar)
            
            # Remove duplicates and sort
            seen_pages = set()
            unique_recommendations = []
            for rec in recommendations:
                if rec['page_id'] not in seen_pages:
                    seen_pages.add(rec['page_id'])
                    unique_recommendations.append(rec)
            
            unique_recommendations.sort(key=lambda x: x.get('score', 0), reverse=True)
            return unique_recommendations[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get collaborative recommendations: {e}")
            return []
    
    async def _get_trending_recommendations(
        self,
        db: AsyncSession,
        project_id: Optional[int],
        limit: int,
        exclude_viewed: bool,
        profile: UserProfile
    ) -> List[Dict[str, Any]]:
        """Get trending content recommendations"""
        try:
            # Get recently scraped popular content
            base_query = select(
                Page.id,
                Page.original_url,
                Page.extracted_title,
                Page.meta_description,
                Page.extracted_text,
                Page.word_count,
                Page.scraped_at,
                Domain.domain_name
            ).join(Domain, Page.domain_id == Domain.id)
            
            if project_id:
                base_query = base_query.join(Project).where(Project.id == project_id)
            
            if exclude_viewed and profile.viewed_pages:
                base_query = base_query.where(~Page.id.in_(profile.viewed_pages))
            
            # Recent content with good word count
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            base_query = base_query.where(
                Page.scraped_at >= recent_cutoff,
                Page.extracted_text.is_not(None),
                Page.word_count > 300
            ).order_by(Page.scraped_at.desc()).limit(limit)
            
            result = await db.execute(base_query)
            pages = result.all()
            
            recommendations = []
            for page in pages:
                recommendations.append({
                    'page_id': page.id,
                    'url': page.original_url,
                    'title': page.extracted_title,
                    'description': page.meta_description,
                    'content_preview': (page.extracted_text or '')[:300] + '...' if page.extracted_text else '',
                    'word_count': page.word_count,
                    'domain_name': page.domain_name,
                    'scraped_at': page.scraped_at.isoformat() if page.scraped_at else None,
                    'score': 0.6,  # Base trending score
                    'recommendation_type': 'trending'
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Failed to get trending recommendations: {e}")
            return []
    
    async def get_content_discovery_suggestions(
        self,
        db: AsyncSession,
        user_id: int,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get content discovery suggestions including new domains, topics, etc.
        """
        try:
            profile = self.get_user_profile(user_id)
            suggestions = {
                'new_domains': [],
                'new_topics': [],
                'similar_users': [],
                'content_gaps': []
            }
            
            # Find new domains not in user's preferences
            domain_query = select(Domain.domain_name, func.count(Page.id).label('page_count')).join(Page)
            if project_id:
                domain_query = domain_query.join(Project).where(Project.id == project_id)
            
            domain_query = domain_query.where(
                ~Domain.domain_name.in_(profile.preferred_domains or [''])
            ).group_by(Domain.domain_name).order_by(func.count(Page.id).desc()).limit(10)
            
            result = await db.execute(domain_query)
            new_domains = result.all()
            
            for domain_name, page_count in new_domains:
                suggestions['new_domains'].append({
                    'domain_name': domain_name,
                    'page_count': page_count,
                    'reason': 'Popular domain you haven\'t explored'
                })
            
            # Find content gaps (domains with topics user likes but hasn't viewed)
            if profile.preferred_topics:
                # This is a simplified implementation
                suggestions['content_gaps'] = [
                    {
                        'topic': topic,
                        'suggested_domains': [],
                        'reason': f'More content about {topic} available'
                    }
                    for topic in profile.preferred_topics[:5]
                ]
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to get content discovery suggestions: {e}")
            return {
                'new_domains': [],
                'new_topics': [],
                'similar_users': [],
                'content_gaps': []
            }


# Global instance
recommendation_engine = RecommendationEngine()