"""
User library service for saved searches, starred items, and collections
"""
import logging
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlmodel import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import (
    StarredItem, SavedSearch, SearchHistory, SearchSuggestion, 
    UserCollection, ItemType, AlertFrequency
)
from app.models.user import User
from app.models.project import Project, Page

logger = logging.getLogger(__name__)


class LibraryService:
    """Service for managing user library features"""
    
    @staticmethod
    async def toggle_star(
        db: AsyncSession,
        user_id: int,
        item_type: ItemType,
        item_id: int,
        page_id: Optional[int] = None,
        project_id: Optional[int] = None,
        tags: List[str] = None,
        personal_note: str = "",
        folder: str = ""
    ) -> Optional[StarredItem]:
        """Toggle star status for an item"""
        # Check if already starred
        result = await db.execute(
            select(StarredItem).where(
                StarredItem.user_id == user_id,
                StarredItem.item_type == item_type,
                StarredItem.item_id == item_id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # Remove star
            await db.delete(existing)
            await db.commit()
            return None
        else:
            # Add star
            starred_item = StarredItem(
                user_id=user_id,
                item_type=item_type,
                item_id=item_id,
                page_id=page_id,
                project_id=project_id,
                personal_note=personal_note,
                tags=tags or [],
                folder=folder
            )
            db.add(starred_item)
            await db.commit()
            await db.refresh(starred_item)
            return starred_item
    
    @staticmethod
    async def get_starred_items(
        db: AsyncSession,
        user_id: int,
        item_type: Optional[ItemType] = None,
        tags: Optional[List[str]] = None,
        folder: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get starred items with filtering"""
        query = select(StarredItem).where(StarredItem.user_id == user_id)
        
        if item_type:
            query = query.where(StarredItem.item_type == item_type)
        
        if folder:
            query = query.where(StarredItem.folder == folder)
        
        if tags:
            # Filter by tags (items that have any of the specified tags)
            tag_conditions = [StarredItem.tags.contains(tag) for tag in tags]
            query = query.where(or_(*tag_conditions))
        
        # Get total count
        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar()
        
        # Apply pagination and order
        query = query.order_by(StarredItem.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        starred_items = result.scalars().all()
        
        return {
            "items": [
                {
                    "id": item.id,
                    "item_type": item.item_type,
                    "item_id": item.item_id,
                    "page_id": item.page_id,
                    "project_id": item.project_id,
                    "personal_note": item.personal_note,
                    "tags": item.tags,
                    "folder": item.folder,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at
                }
                for item in starred_items
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    
    async def star_item(
        self, 
        db: AsyncSession,
        user: User,
        item_type: ItemType,
        item_id: int,
        note: str = "",
        tags: List[str] = None,
        folder: str = ""
    ) -> StarredItem:
        """Star an item for the user"""
        try:
            # Check if already starred
            result = await db.execute(
                select(StarredItem).where(
                    StarredItem.user_id == user.id,
                    StarredItem.item_type == item_type,
                    StarredItem.item_id == item_id
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing starred item
                existing.personal_note = note
                existing.tags = tags or []
                existing.folder = folder
                existing.updated_at = datetime.utcnow()
                await db.commit()
                return existing
            
            # Create new starred item
            starred_item = StarredItem(
                user_id=user.id,
                item_type=item_type,
                item_id=item_id,
                personal_note=note,
                tags=tags or [],
                folder=folder
            )
            
            # Set specific foreign key based on item type
            if item_type == ItemType.PAGE:
                starred_item.page_id = item_id
            elif item_type == ItemType.PROJECT:
                starred_item.project_id = item_id
            
            db.add(starred_item)
            await db.commit()
            await db.refresh(starred_item)
            
            logger.info(f"User {user.id} starred {item_type} {item_id}")
            return starred_item
            
        except Exception as e:
            logger.error(f"Failed to star item: {e}")
            await db.rollback()
            raise
    
    async def unstar_item(
        self, 
        db: AsyncSession,
        user: User,
        item_type: ItemType,
        item_id: int
    ) -> bool:
        """Remove star from an item"""
        try:
            result = await db.execute(
                select(StarredItem).where(
                    StarredItem.user_id == user.id,
                    StarredItem.item_type == item_type,
                    StarredItem.item_id == item_id
                )
            )
            starred_item = result.scalar_one_or_none()
            
            if starred_item:
                await db.delete(starred_item)
                await db.commit()
                logger.info(f"User {user.id} unstarred {item_type} {item_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to unstar item: {e}")
            await db.rollback()
            return False
    
    async def get_starred_items(
        self, 
        db: AsyncSession,
        user: User,
        item_type: Optional[ItemType] = None,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user's starred items with filtering"""
        try:
            query = select(StarredItem).where(StarredItem.user_id == user.id)
            
            if item_type:
                query = query.where(StarredItem.item_type == item_type)
            
            if folder is not None:
                query = query.where(StarredItem.folder == folder)
            
            if tags:
                # Filter by tags (items that have any of the specified tags)
                tag_filters = [StarredItem.tags.contains([tag]) for tag in tags]
                query = query.where(or_(*tag_filters))
            
            query = query.order_by(StarredItem.created_at.desc()).limit(limit).offset(offset)
            
            result = await db.execute(query)
            starred_items = result.scalars().all()
            
            # Enrich with item details
            enriched_items = []
            for item in starred_items:
                item_data = {
                    "id": item.id,
                    "item_type": item.item_type,
                    "item_id": item.item_id,
                    "personal_note": item.personal_note,
                    "tags": item.tags,
                    "folder": item.folder,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "last_accessed_at": item.last_accessed_at,
                }
                
                # Add item details based on type
                if item.item_type == ItemType.PAGE and item.page_id:
                    page_result = await db.execute(
                        select(Page).where(Page.id == item.page_id)
                    )
                    page = page_result.scalar_one_or_none()
                    if page:
                        item_data["item_details"] = {
                            "url": page.url,
                            "title": page.title,
                            "scraped_at": page.scraped_at,
                        }
                
                elif item.item_type == ItemType.PROJECT and item.project_id:
                    project_result = await db.execute(
                        select(Project).where(Project.id == item.project_id)
                    )
                    project = project_result.scalar_one_or_none()
                    if project:
                        item_data["item_details"] = {
                            "name": project.name,
                            "description": project.description,
                            "created_at": project.created_at,
                        }
                
                enriched_items.append(item_data)
            
            return enriched_items
            
        except Exception as e:
            logger.error(f"Failed to get starred items: {e}")
            return []
    
    async def save_search(
        self, 
        db: AsyncSession,
        user: User,
        name: str,
        query_text: str,
        filters: Dict[str, Any] = None,
        sort_options: Dict[str, Any] = None,
        description: str = "",
        folder: str = "",
        tags: List[str] = None,
        enable_alerts: bool = False,
        alert_frequency: AlertFrequency = AlertFrequency.DAILY
    ) -> SavedSearch:
        """Save a search query for the user"""
        try:
            saved_search = SavedSearch(
                user_id=user.id,
                name=name,
                description=description,
                query_text=query_text,
                filters=filters or {},
                sort_options=sort_options or {},
                folder=folder,
                tags=tags or [],
                enable_alerts=enable_alerts,
                alert_frequency=alert_frequency,
                share_token=secrets.token_urlsafe(16)
            )
            
            db.add(saved_search)
            await db.commit()
            await db.refresh(saved_search)
            
            logger.info(f"User {user.id} saved search '{name}'")
            return saved_search
            
        except Exception as e:
            logger.error(f"Failed to save search: {e}")
            await db.rollback()
            raise
    
    async def get_saved_searches(
        self, 
        db: AsyncSession,
        user: User,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[SavedSearch]:
        """Get user's saved searches"""
        try:
            query = select(SavedSearch).where(SavedSearch.user_id == user.id)
            
            if folder is not None:
                query = query.where(SavedSearch.folder == folder)
            
            if tags:
                tag_filters = [SavedSearch.tags.contains([tag]) for tag in tags]
                query = query.where(or_(*tag_filters))
            
            query = query.order_by(SavedSearch.last_executed.desc().nullslast(), SavedSearch.created_at.desc())
            query = query.limit(limit).offset(offset)
            
            result = await db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get saved searches: {e}")
            return []
    
    async def execute_saved_search(
        self, 
        db: AsyncSession,
        user: User,
        search_id: int,
        result_count: int = 0
    ) -> Optional[SavedSearch]:
        """Record execution of a saved search"""
        try:
            result = await db.execute(
                select(SavedSearch).where(
                    SavedSearch.id == search_id,
                    SavedSearch.user_id == user.id
                )
            )
            saved_search = result.scalar_one_or_none()
            
            if saved_search:
                saved_search.record_execution(result_count)
                await db.commit()
                
                # Record in search history
                await self.record_search_history(
                    db, user, saved_search.query_text, saved_search.filters,
                    result_count, saved_search_id=search_id
                )
            
            return saved_search
            
        except Exception as e:
            logger.error(f"Failed to execute saved search: {e}")
            return None
    
    async def record_search_history(
        self, 
        db: AsyncSession,
        user: User,
        query_text: str,
        filters: Dict[str, Any] = None,
        result_count: int = 0,
        project_id: Optional[int] = None,
        saved_search_id: Optional[int] = None,
        execution_time_ms: Optional[int] = None,
        session_id: Optional[str] = None
    ) -> SearchHistory:
        """Record a search in user's search history"""
        try:
            search_history = SearchHistory(
                user_id=user.id,
                project_id=project_id,
                saved_search_id=saved_search_id,
                query_text=query_text,
                filters=filters or {},
                result_count=result_count,
                execution_time_ms=execution_time_ms,
                session_id=session_id
            )
            
            db.add(search_history)
            await db.commit()
            
            # Update search suggestions based on this search
            await self._update_search_suggestions(db, user, query_text)
            
            return search_history
            
        except Exception as e:
            logger.error(f"Failed to record search history: {e}")
            await db.rollback()
            raise
    
    async def _update_search_suggestions(
        self, 
        db: AsyncSession,
        user: User,
        query_text: str
    ):
        """Update search suggestions based on search history"""
        try:
            # Clean query text
            query_text = query_text.strip().lower()
            if len(query_text) < 3:  # Skip very short queries
                return
            
            # Check if suggestion already exists
            result = await db.execute(
                select(SearchSuggestion).where(
                    SearchSuggestion.user_id == user.id,
                    SearchSuggestion.suggestion_text == query_text
                )
            )
            suggestion = result.scalar_one_or_none()
            
            if suggestion:
                # Update existing suggestion
                suggestion.frequency += 1
                suggestion.last_used = datetime.utcnow()
                suggestion.score = min(1.0, suggestion.frequency * 0.1)
            else:
                # Create new suggestion
                suggestion = SearchSuggestion(
                    user_id=user.id,
                    suggestion_text=query_text,
                    suggestion_type="query",
                    display_text=query_text.title(),
                    score=0.1,
                    frequency=1,
                    last_used=datetime.utcnow()
                )
                db.add(suggestion)
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Failed to update search suggestions: {e}")
    
    async def get_search_suggestions(
        self, 
        db: AsyncSession,
        user: User,
        query_prefix: str = "",
        limit: int = 10
    ) -> List[SearchSuggestion]:
        """Get search suggestions for user"""
        try:
            query = select(SearchSuggestion).where(SearchSuggestion.user_id == user.id)
            
            if query_prefix:
                query = query.where(
                    SearchSuggestion.suggestion_text.contains(query_prefix.lower())
                )
            
            query = query.order_by(SearchSuggestion.score.desc(), SearchSuggestion.frequency.desc())
            query = query.limit(limit)
            
            result = await db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get search suggestions: {e}")
            return []
    
    async def get_search_history(
        self, 
        db: AsyncSession,
        user: User,
        project_id: Optional[int] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[SearchHistory]:
        """Get user's search history"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            query = select(SearchHistory).where(
                SearchHistory.user_id == user.id,
                SearchHistory.created_at >= start_date
            )
            
            if project_id:
                query = query.where(SearchHistory.project_id == project_id)
            
            query = query.order_by(SearchHistory.created_at.desc()).limit(limit)
            
            result = await db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get search history: {e}")
            return []
    
    async def create_collection(
        self, 
        db: AsyncSession,
        user: User,
        name: str,
        description: str = "",
        collection_type: str = "general",
        parent_collection_id: Optional[int] = None
    ) -> UserCollection:
        """Create a new collection for the user"""
        try:
            collection = UserCollection(
                user_id=user.id,
                name=name,
                description=description,
                collection_type=collection_type,
                parent_collection_id=parent_collection_id,
                share_token=secrets.token_urlsafe(16)
            )
            
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            
            logger.info(f"User {user.id} created collection '{name}'")
            return collection
            
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            await db.rollback()
            raise
    
    async def add_item_to_collection(
        self, 
        db: AsyncSession,
        user: User,
        collection_id: int,
        item_type: ItemType,
        item_id: int
    ) -> bool:
        """Add an item to a collection"""
        try:
            # Get collection
            result = await db.execute(
                select(UserCollection).where(
                    UserCollection.id == collection_id,
                    UserCollection.user_id == user.id
                )
            )
            collection = result.scalar_one_or_none()
            
            if not collection:
                return False
            
            # Add item to collection
            item_type_str = item_type.value
            if item_type_str not in collection.items:
                collection.items[item_type_str] = []
            
            if item_id not in collection.items[item_type_str]:
                collection.items[item_type_str].append(item_id)
                collection.item_count += 1
                collection.updated_at = datetime.utcnow()
                await db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add item to collection: {e}")
            await db.rollback()
            return False
    
    async def get_user_collections(
        self, 
        db: AsyncSession,
        user: User,
        collection_type: Optional[str] = None
    ) -> List[UserCollection]:
        """Get user's collections"""
        try:
            query = select(UserCollection).where(UserCollection.user_id == user.id)
            
            if collection_type:
                query = query.where(UserCollection.collection_type == collection_type)
            
            query = query.order_by(UserCollection.sort_order, UserCollection.name)
            
            result = await db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get user collections: {e}")
            return []
    
    async def get_library_stats(
        self, 
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """Get library statistics for user"""
        try:
            # Count starred items by type
            starred_counts = {}
            for item_type in ItemType:
                result = await db.execute(
                    select(func.count()).where(
                        StarredItem.user_id == user.id,
                        StarredItem.item_type == item_type
                    )
                )
                starred_counts[item_type.value] = result.scalar() or 0
            
            # Count saved searches
            result = await db.execute(
                select(func.count()).where(SavedSearch.user_id == user.id)
            )
            saved_searches_count = result.scalar() or 0
            
            # Count collections
            result = await db.execute(
                select(func.count()).where(UserCollection.user_id == user.id)
            )
            collections_count = result.scalar() or 0
            
            # Recent activity
            recent_searches = await self.get_search_history(db, user, days=7, limit=5)
            
            return {
                "starred_items": starred_counts,
                "total_starred": sum(starred_counts.values()),
                "saved_searches": saved_searches_count,
                "collections": collections_count,
                "recent_searches": len(recent_searches),
                "last_activity": recent_searches[0].created_at if recent_searches else None,
            }
            
        except Exception as e:
            logger.error(f"Failed to get library stats: {e}")
            return {}


# Global service instance
library_service = LibraryService()