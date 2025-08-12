"""
Semantic search service using vector embeddings
"""
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Any
from sqlmodel import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sentence_transformers import SentenceTransformer
import asyncio
import json
from datetime import datetime

from app.models.project import Page, Domain, Project

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """Wrapper for sentence transformer model"""
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model_name = model_name
        self.model: Optional[SentenceTransformer] = None
        self.dimension = 384  # Default for all-MiniLM-L6-v2
    
    def load_model(self):
        """Load the embedding model"""
        if self.model is None:
            try:
                self.model = SentenceTransformer(self.model_name)
                self.dimension = self.model.get_sentence_embedding_dimension()
                logger.info(f"Loaded embedding model: {self.model_name} (dimension: {self.dimension})")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts to embeddings"""
        if self.model is None:
            self.load_model()
        
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings
        except Exception as e:
            logger.error(f"Failed to encode texts: {e}")
            raise
    
    def encode_single(self, text: str) -> np.ndarray:
        """Encode single text to embedding"""
        return self.encode([text])[0]


class SemanticSearchService:
    """Service for semantic search using vector embeddings"""
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.embedding_model = EmbeddingModel(model_name)
        self.similarity_threshold = 0.7
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        try:
            # Run embedding generation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, 
                self.embedding_model.encode_single, 
                text
            )
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        try:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, 
                self.embedding_model.encode, 
                texts
            )
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return []
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            a = np.array(vec1)
            b = np.array(vec2)
            
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            similarity = dot_product / (norm_a * norm_b)
            return float(similarity)
        except Exception as e:
            logger.error(f"Failed to calculate cosine similarity: {e}")
            return 0.0
    
    async def semantic_search(
        self,
        db: AsyncSession,
        query: str,
        project_id: Optional[int] = None,
        domain_ids: Optional[List[int]] = None,
        limit: int = 20,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search on page content
        """
        try:
            # Generate query embedding
            query_embedding = await self.generate_embedding(query)
            if not query_embedding:
                return []
            
            # Build base query
            base_query = select(
                Page.id,
                Page.original_url,
                Page.extracted_title,
                Page.extracted_text,
                Page.meta_description,
                Page.word_count,
                Page.scraped_at,
                Page.content_embedding,
                Domain.domain_name
            ).join(Domain, Page.domain_id == Domain.id)
            
            # Add filters
            if project_id:
                base_query = base_query.join(Project).where(Project.id == project_id)
            
            if domain_ids:
                base_query = base_query.where(Domain.id.in_(domain_ids))
            
            # Only search pages with embeddings
            base_query = base_query.where(Page.content_embedding.is_not(None))
            
            result = await db.execute(base_query)
            pages = result.all()
            
            # Calculate similarities
            search_results = []
            for page in pages:
                if page.content_embedding:
                    try:
                        # Parse embedding from JSON
                        page_embedding = json.loads(page.content_embedding)
                        similarity = self.cosine_similarity(query_embedding, page_embedding)
                        
                        if similarity >= min_similarity:
                            search_results.append({
                                'page_id': page.id,
                                'url': page.original_url,
                                'title': page.extracted_title,
                                'description': page.meta_description,
                                'content_preview': (page.extracted_text or '')[:300] + '...' if page.extracted_text else '',
                                'word_count': page.word_count,
                                'domain_name': page.domain_name,
                                'scraped_at': page.scraped_at.isoformat() if page.scraped_at else None,
                                'similarity_score': similarity
                            })
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse embedding for page {page.id}: {e}")
                        continue
            
            # Sort by similarity score
            search_results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return search_results[:limit]
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    async def find_similar_content(
        self,
        db: AsyncSession,
        page_id: int,
        limit: int = 10,
        min_similarity: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Find content similar to a specific page
        """
        try:
            # Get the target page and its embedding
            page_query = select(Page).where(Page.id == page_id)
            result = await db.execute(page_query)
            target_page = result.scalar_one_or_none()
            
            if not target_page or not target_page.content_embedding:
                return []
            
            target_embedding = json.loads(target_page.content_embedding)
            
            # Get all other pages with embeddings
            other_pages_query = select(
                Page.id,
                Page.original_url,
                Page.extracted_title,
                Page.extracted_text,
                Page.meta_description,
                Page.word_count,
                Page.scraped_at,
                Page.content_embedding,
                Domain.domain_name
            ).join(Domain, Page.domain_id == Domain.id).where(
                Page.id != page_id,
                Page.content_embedding.is_not(None)
            )
            
            result = await db.execute(other_pages_query)
            other_pages = result.all()
            
            # Calculate similarities
            similar_content = []
            for page in other_pages:
                if page.content_embedding:
                    try:
                        page_embedding = json.loads(page.content_embedding)
                        similarity = self.cosine_similarity(target_embedding, page_embedding)
                        
                        if similarity >= min_similarity:
                            similar_content.append({
                                'page_id': page.id,
                                'url': page.original_url,
                                'title': page.extracted_title,
                                'description': page.meta_description,
                                'content_preview': (page.extracted_text or '')[:300] + '...' if page.extracted_text else '',
                                'word_count': page.word_count,
                                'domain_name': page.domain_name,
                                'scraped_at': page.scraped_at.isoformat() if page.scraped_at else None,
                                'similarity_score': similarity
                            })
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse embedding for page {page.id}: {e}")
                        continue
            
            # Sort by similarity score
            similar_content.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return similar_content[:limit]
            
        except Exception as e:
            logger.error(f"Find similar content failed: {e}")
            return []
    
    async def update_page_embedding(
        self,
        db: AsyncSession,
        page_id: int,
        force_update: bool = False
    ) -> bool:
        """
        Update embedding for a specific page
        """
        try:
            # Get page
            page_query = select(Page).where(Page.id == page_id)
            result = await db.execute(page_query)
            page = result.scalar_one_or_none()
            
            if not page:
                return False
            
            # Skip if embedding already exists and not forcing update
            if page.content_embedding and not force_update:
                return True
            
            # Generate embedding text (combine title and content)
            embedding_text = ""
            if page.extracted_title:
                embedding_text += page.extracted_title + " "
            if page.extracted_text:
                embedding_text += page.extracted_text[:2000]  # Limit text length
            
            if not embedding_text.strip():
                logger.warning(f"No text content for page {page_id}")
                return False
            
            # Generate embedding
            embedding = await self.generate_embedding(embedding_text.strip())
            if not embedding:
                return False
            
            # Update page
            page.content_embedding = json.dumps(embedding)
            page.embedding_updated_at = datetime.utcnow()
            
            await db.commit()
            logger.info(f"Updated embedding for page {page_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update page embedding {page_id}: {e}")
            await db.rollback()
            return False
    
    async def batch_update_embeddings(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        batch_size: int = 50,
        force_update: bool = False
    ) -> Dict[str, int]:
        """
        Update embeddings for multiple pages in batches
        """
        stats = {
            'processed': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0
        }
        
        try:
            # Build query for pages needing embeddings
            base_query = select(Page.id)
            
            if not force_update:
                base_query = base_query.where(Page.content_embedding.is_(None))
            
            if project_id:
                base_query = base_query.join(Domain).join(Project).where(Project.id == project_id)
            elif domain_id:
                base_query = base_query.where(Page.domain_id == domain_id)
            
            result = await db.execute(base_query)
            page_ids = [row[0] for row in result.all()]
            
            logger.info(f"Found {len(page_ids)} pages to process for embeddings")
            
            # Process in batches
            for i in range(0, len(page_ids), batch_size):
                batch_ids = page_ids[i:i + batch_size]
                
                for page_id in batch_ids:
                    stats['processed'] += 1
                    
                    success = await self.update_page_embedding(
                        db, page_id, force_update
                    )
                    
                    if success:
                        stats['updated'] += 1
                    else:
                        stats['failed'] += 1
                
                logger.info(f"Processed batch {i // batch_size + 1}, updated {stats['updated']} pages")
            
            return stats
            
        except Exception as e:
            logger.error(f"Batch embedding update failed: {e}")
            stats['failed'] += stats['processed'] - stats['updated']
            return stats
    
    async def get_embedding_statistics(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about embedding coverage
        """
        try:
            base_query = select(func.count(Page.id))
            
            if project_id:
                base_query = base_query.join(Domain).join(Project).where(Project.id == project_id)
            
            # Total pages
            total_result = await db.execute(base_query)
            total_pages = total_result.scalar() or 0
            
            # Pages with embeddings
            with_embeddings_query = base_query.where(Page.content_embedding.is_not(None))
            with_embeddings_result = await db.execute(with_embeddings_query)
            pages_with_embeddings = with_embeddings_result.scalar() or 0
            
            # Recent updates
            recent_query = base_query.where(
                Page.embedding_updated_at.is_not(None),
                Page.embedding_updated_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
            )
            recent_result = await db.execute(recent_query)
            recent_updates = recent_result.scalar() or 0
            
            coverage_percentage = (pages_with_embeddings / total_pages * 100) if total_pages > 0 else 0
            
            return {
                'total_pages': total_pages,
                'pages_with_embeddings': pages_with_embeddings,
                'pages_without_embeddings': total_pages - pages_with_embeddings,
                'coverage_percentage': round(coverage_percentage, 2),
                'recent_updates_today': recent_updates,
                'model_name': self.embedding_model.model_name,
                'embedding_dimension': self.embedding_model.dimension
            }
            
        except Exception as e:
            logger.error(f"Failed to get embedding statistics: {e}")
            return {
                'total_pages': 0,
                'pages_with_embeddings': 0,
                'pages_without_embeddings': 0,
                'coverage_percentage': 0,
                'recent_updates_today': 0,
                'model_name': self.embedding_model.model_name,
                'embedding_dimension': self.embedding_model.dimension
            }


# Global instance
semantic_search_service = SemanticSearchService()