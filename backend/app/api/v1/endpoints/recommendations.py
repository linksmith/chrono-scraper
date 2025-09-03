"""
Content recommendation API endpoints
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.user import User
from app.services.recommendation_engine import recommendation_engine
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class UserInteractionRequest(BaseModel):
    """Request model for tracking user interactions"""
    interaction_type: str  # view, search, export, etc.
    page_id: Optional[int] = None
    query: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RecommendationResponse(BaseModel):
    """Response model for recommendations"""
    recommendations: List[Dict[str, Any]]
    total_count: int
    user_id: int
    recommendation_types: List[str]


@router.post("/track-interaction")
async def track_user_interaction(
    request: UserInteractionRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Track user interaction for personalization
    """
    try:
        await recommendation_engine.track_user_interaction(
            db=db,
            user_id=current_user.id,
            interaction_type=request.interaction_type,
            page_id=request.page_id,
            query=request.query,
            metadata=request.metadata
        )
        
        return {
            "message": "Interaction tracked successfully",
            "interaction_type": request.interaction_type
        }
        
    except Exception as e:
        logger.error(f"Failed to track user interaction: {e}")
        raise HTTPException(status_code=500, detail="Failed to track interaction")


@router.get("/personalized", response_model=RecommendationResponse)
async def get_personalized_recommendations(
    project_id: Optional[int] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    exclude_viewed: bool = Query(default=True),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get personalized content recommendations for the current user
    """
    try:
        recommendations = await recommendation_engine.get_personalized_recommendations(
            db=db,
            user_id=current_user.id,
            project_id=project_id,
            limit=limit,
            exclude_viewed=exclude_viewed
        )
        
        # Extract unique recommendation types
        recommendation_types = list(set(
            rec.get('recommendation_type', 'unknown') 
            for rec in recommendations
        ))
        
        return RecommendationResponse(
            recommendations=recommendations,
            total_count=len(recommendations),
            user_id=current_user.id,
            recommendation_types=recommendation_types
        )
        
    except Exception as e:
        logger.error(f"Failed to get personalized recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommendations")


@router.get("/discovery")
async def get_content_discovery_suggestions(
    project_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get content discovery suggestions for exploring new areas
    """
    try:
        suggestions = await recommendation_engine.get_content_discovery_suggestions(
            db=db,
            user_id=current_user.id,
            project_id=project_id
        )
        
        return {
            "user_id": current_user.id,
            "suggestions": suggestions
        }
        
    except Exception as e:
        logger.error(f"Failed to get discovery suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get discovery suggestions")


@router.get("/trending")
async def get_trending_content(
    project_id: Optional[int] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    days: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get trending content based on recent activity and popularity
    """
    try:
        # Use the recommendation engine's trending logic
        profile = recommendation_engine.get_user_profile(current_user.id)
        
        trending_recommendations = await recommendation_engine._get_trending_recommendations(
            db=db,
            project_id=project_id,
            limit=limit,
            exclude_viewed=False,
            profile=profile
        )
        
        return {
            "trending_content": trending_recommendations,
            "total_count": len(trending_recommendations),
            "time_period_days": days
        }
        
    except Exception as e:
        logger.error(f"Failed to get trending content: {e}")
        raise HTTPException(status_code=500, detail="Failed to get trending content")


@router.get("/similar-to/{page_id}")
async def get_similar_content_recommendations(
    page_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    min_similarity: float = Query(default=0.6, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get content recommendations similar to a specific page
    """
    try:
        # Track this as a user interaction
        await recommendation_engine.track_user_interaction(
            db=db,
            user_id=current_user.id,
            interaction_type='similar_content',
            page_id=page_id
        )
        
        from app.services.semantic_search import semantic_search_service
        
        similar_content = await semantic_search_service.find_similar_content(
            db=db,
            page_id=page_id,
            limit=limit,
            min_similarity=min_similarity
        )
        
        return {
            "source_page_id": page_id,
            "similar_content": similar_content,
            "total_count": len(similar_content),
            "min_similarity": min_similarity
        }
        
    except Exception as e:
        logger.error(f"Failed to get similar content recommendations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get similar content")


@router.get("/profile")
async def get_user_recommendation_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get the user's recommendation profile and preferences
    """
    try:
        profile = recommendation_engine.get_user_profile(current_user.id)
        
        return {
            "user_id": current_user.id,
            "profile": {
                "viewed_pages_count": len(profile.viewed_pages),
                "search_queries_count": len(profile.search_queries),
                "preferred_domains": profile.preferred_domains[:10],  # Top 10
                "preferred_topics": profile.preferred_topics[:10],    # Top 10
                "content_types": profile.content_types,
                "language_preferences": profile.language_preferences,
                "recent_searches": profile.search_queries[-10:] if profile.search_queries else []
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get user recommendation profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommendation profile")


@router.delete("/profile/reset")
async def reset_user_recommendation_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Reset the user's recommendation profile
    """
    try:
        if current_user.id in recommendation_engine.user_profiles:
            del recommendation_engine.user_profiles[current_user.id]
        
        # Clear user's recommendation cache
        cache_keys_to_remove = [
            key for key in recommendation_engine.recommendation_cache.keys()
            if key.startswith(f"recommendations_{current_user.id}_")
        ]
        
        for key in cache_keys_to_remove:
            del recommendation_engine.recommendation_cache[key]
        
        return {
            "message": "Recommendation profile reset successfully",
            "user_id": current_user.id
        }
        
    except Exception as e:
        logger.error(f"Failed to reset recommendation profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset profile")


@router.get("/stats")
async def get_recommendation_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get recommendation system statistics
    """
    try:
        total_profiles = len(recommendation_engine.user_profiles)
        cache_entries = len(recommendation_engine.recommendation_cache)
        
        user_profile = recommendation_engine.get_user_profile(current_user.id)
        
        return {
            "system_stats": {
                "total_user_profiles": total_profiles,
                "cache_entries": cache_entries,
                "cache_expiry_hours": recommendation_engine.cache_expiry_hours
            },
            "user_stats": {
                "viewed_pages": len(user_profile.viewed_pages),
                "search_queries": len(user_profile.search_queries),
                "preferred_domains": len(user_profile.preferred_domains),
                "preferred_topics": len(user_profile.preferred_topics)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get recommendation stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommendation stats")