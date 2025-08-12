"""
Topic modeling and content clustering service
"""
import json
import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation, NMF
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.manifold import TSNE
import re

from app.models.project import Page, Domain, Project

logger = logging.getLogger(__name__)


class TopicModel:
    """Container for topic model results"""
    
    def __init__(self):
        self.topics: List[Dict[str, Any]] = []
        self.document_topics: Dict[int, List[float]] = {}
        self.topic_words: Dict[int, List[Tuple[str, float]]] = {}
        self.model_type: str = ""
        self.created_at: datetime = datetime.utcnow()
        self.num_topics: int = 0


class ContentCluster:
    """Container for content clustering results"""
    
    def __init__(self):
        self.clusters: Dict[int, List[int]] = {}
        self.cluster_labels: Dict[int, str] = {}
        self.cluster_summaries: Dict[int, Dict[str, Any]] = {}
        self.page_clusters: Dict[int, int] = {}
        self.created_at: datetime = datetime.utcnow()
        self.num_clusters: int = 0


class TopicModelingService:
    """Service for topic modeling and content clustering"""
    
    def __init__(self):
        self.topic_models: Dict[str, TopicModel] = {}
        self.content_clusters: Dict[str, ContentCluster] = {}
        self.model_cache_hours = 24
        self.min_documents = 10
        self.max_features = 5000
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for topic modeling"""
        try:
            if not text:
                return ""
            
            # Convert to lowercase
            text = text.lower()
            
            # Remove URLs, email addresses, and special characters
            text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
            text = re.sub(r'\S+@\S+', '', text)
            text = re.sub(r'[^a-zA-Z\s]', ' ', text)
            
            # Remove extra whitespace
            text = ' '.join(text.split())
            
            return text
            
        except Exception as e:
            logger.error(f"Failed to preprocess text: {e}")
            return ""
    
    async def extract_topics_lda(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        num_topics: int = 10,
        max_documents: int = 1000
    ) -> TopicModel:
        """
        Extract topics using Latent Dirichlet Allocation (LDA)
        """
        try:
            cache_key = f"lda_{project_id}_{domain_id}_{num_topics}"
            
            # Check cache
            if cache_key in self.topic_models:
                cached_model = self.topic_models[cache_key]
                if (datetime.utcnow() - cached_model.created_at).total_seconds() < (self.model_cache_hours * 3600):
                    return cached_model
            
            # Get documents
            documents, page_ids = await self._get_documents_for_modeling(
                db, project_id, domain_id, max_documents
            )
            
            if len(documents) < self.min_documents:
                logger.warning(f"Not enough documents for topic modeling: {len(documents)}")
                return TopicModel()
            
            # Preprocess documents
            processed_docs = [self._preprocess_text(doc) for doc in documents]
            processed_docs = [doc for doc in processed_docs if len(doc.split()) > 10]  # Filter short docs
            
            if len(processed_docs) < self.min_documents:
                logger.warning(f"Not enough processed documents: {len(processed_docs)}")
                return TopicModel()
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            topic_model = await loop.run_in_executor(
                None,
                self._run_lda_modeling,
                processed_docs,
                page_ids[:len(processed_docs)],
                num_topics
            )
            
            # Cache results
            self.topic_models[cache_key] = topic_model
            
            return topic_model
            
        except Exception as e:
            logger.error(f"LDA topic extraction failed: {e}")
            return TopicModel()
    
    def _run_lda_modeling(
        self,
        documents: List[str],
        page_ids: List[int],
        num_topics: int
    ) -> TopicModel:
        """Run LDA modeling in thread"""
        try:
            # Create TF-IDF vectors
            vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8
            )
            
            doc_term_matrix = vectorizer.fit_transform(documents)
            feature_names = vectorizer.get_feature_names_out()
            
            # Train LDA model
            lda = LatentDirichletAllocation(
                n_components=num_topics,
                random_state=42,
                max_iter=20,
                learning_method='online',
                learning_offset=50.0
            )
            
            lda.fit(doc_term_matrix)
            
            # Extract topics
            topic_model = TopicModel()
            topic_model.model_type = "LDA"
            topic_model.num_topics = num_topics
            
            # Get topic words
            for topic_idx, topic in enumerate(lda.components_):
                top_words_idx = topic.argsort()[-20:][::-1]
                topic_words = [(feature_names[i], topic[i]) for i in top_words_idx]
                topic_model.topic_words[topic_idx] = topic_words
                
                # Create topic summary
                top_5_words = [word for word, _ in topic_words[:5]]
                topic_model.topics.append({
                    'id': topic_idx,
                    'label': f"Topic {topic_idx + 1}",
                    'keywords': top_5_words,
                    'top_words': topic_words,
                    'coherence_score': 0.0  # Would need additional calculation
                })
            
            # Get document-topic distributions
            doc_topic_dist = lda.transform(doc_term_matrix)
            
            for i, page_id in enumerate(page_ids):
                if i < len(doc_topic_dist):
                    topic_model.document_topics[page_id] = doc_topic_dist[i].tolist()
            
            logger.info(f"LDA modeling completed: {num_topics} topics, {len(documents)} documents")
            return topic_model
            
        except Exception as e:
            logger.error(f"LDA modeling failed: {e}")
            return TopicModel()
    
    async def extract_topics_nmf(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        num_topics: int = 10,
        max_documents: int = 1000
    ) -> TopicModel:
        """
        Extract topics using Non-negative Matrix Factorization (NMF)
        """
        try:
            cache_key = f"nmf_{project_id}_{domain_id}_{num_topics}"
            
            # Check cache
            if cache_key in self.topic_models:
                cached_model = self.topic_models[cache_key]
                if (datetime.utcnow() - cached_model.created_at).total_seconds() < (self.model_cache_hours * 3600):
                    return cached_model
            
            # Get documents
            documents, page_ids = await self._get_documents_for_modeling(
                db, project_id, domain_id, max_documents
            )
            
            if len(documents) < self.min_documents:
                return TopicModel()
            
            # Preprocess documents
            processed_docs = [self._preprocess_text(doc) for doc in documents]
            processed_docs = [doc for doc in processed_docs if len(doc.split()) > 10]
            
            if len(processed_docs) < self.min_documents:
                return TopicModel()
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            topic_model = await loop.run_in_executor(
                None,
                self._run_nmf_modeling,
                processed_docs,
                page_ids[:len(processed_docs)],
                num_topics
            )
            
            # Cache results
            self.topic_models[cache_key] = topic_model
            
            return topic_model
            
        except Exception as e:
            logger.error(f"NMF topic extraction failed: {e}")
            return TopicModel()
    
    def _run_nmf_modeling(
        self,
        documents: List[str],
        page_ids: List[int],
        num_topics: int
    ) -> TopicModel:
        """Run NMF modeling in thread"""
        try:
            # Create TF-IDF vectors
            vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8
            )
            
            doc_term_matrix = vectorizer.fit_transform(documents)
            feature_names = vectorizer.get_feature_names_out()
            
            # Train NMF model
            nmf = NMF(
                n_components=num_topics,
                random_state=42,
                init='nndsvd',
                max_iter=200
            )
            
            doc_topic_dist = nmf.fit_transform(doc_term_matrix)
            
            # Extract topics
            topic_model = TopicModel()
            topic_model.model_type = "NMF"
            topic_model.num_topics = num_topics
            
            # Get topic words
            for topic_idx, topic in enumerate(nmf.components_):
                top_words_idx = topic.argsort()[-20:][::-1]
                topic_words = [(feature_names[i], topic[i]) for i in top_words_idx]
                topic_model.topic_words[topic_idx] = topic_words
                
                # Create topic summary
                top_5_words = [word for word, _ in topic_words[:5]]
                topic_model.topics.append({
                    'id': topic_idx,
                    'label': f"Topic {topic_idx + 1}",
                    'keywords': top_5_words,
                    'top_words': topic_words,
                    'coherence_score': 0.0
                })
            
            # Get document-topic distributions
            for i, page_id in enumerate(page_ids):
                if i < len(doc_topic_dist):
                    topic_model.document_topics[page_id] = doc_topic_dist[i].tolist()
            
            logger.info(f"NMF modeling completed: {num_topics} topics, {len(documents)} documents")
            return topic_model
            
        except Exception as e:
            logger.error(f"NMF modeling failed: {e}")
            return TopicModel()
    
    async def cluster_content(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        domain_id: Optional[int] = None,
        num_clusters: int = 10,
        max_documents: int = 1000,
        method: str = "kmeans"
    ) -> ContentCluster:
        """
        Cluster content using various clustering algorithms
        """
        try:
            cache_key = f"cluster_{method}_{project_id}_{domain_id}_{num_clusters}"
            
            # Check cache
            if cache_key in self.content_clusters:
                cached_cluster = self.content_clusters[cache_key]
                if (datetime.utcnow() - cached_cluster.created_at).total_seconds() < (self.model_cache_hours * 3600):
                    return cached_cluster
            
            # Get documents
            documents, page_ids = await self._get_documents_for_modeling(
                db, project_id, domain_id, max_documents
            )
            
            if len(documents) < self.min_documents:
                return ContentCluster()
            
            # Preprocess documents
            processed_docs = [self._preprocess_text(doc) for doc in documents]
            processed_docs = [doc for doc in processed_docs if len(doc.split()) > 10]
            
            if len(processed_docs) < self.min_documents:
                return ContentCluster()
            
            # Run clustering in thread pool
            loop = asyncio.get_event_loop()
            content_cluster = await loop.run_in_executor(
                None,
                self._run_clustering,
                processed_docs,
                page_ids[:len(processed_docs)],
                num_clusters,
                method
            )
            
            # Cache results
            self.content_clusters[cache_key] = content_cluster
            
            return content_cluster
            
        except Exception as e:
            logger.error(f"Content clustering failed: {e}")
            return ContentCluster()
    
    def _run_clustering(
        self,
        documents: List[str],
        page_ids: List[int],
        num_clusters: int,
        method: str
    ) -> ContentCluster:
        """Run clustering in thread"""
        try:
            # Create TF-IDF vectors
            vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.8
            )
            
            doc_vectors = vectorizer.fit_transform(documents)
            feature_names = vectorizer.get_feature_names_out()
            
            # Choose clustering algorithm
            if method == "kmeans":
                clusterer = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
            elif method == "dbscan":
                clusterer = DBSCAN(eps=0.5, min_samples=3, metric='cosine')
            else:
                raise ValueError(f"Unknown clustering method: {method}")
            
            # Perform clustering
            if method == "dbscan":
                # Convert sparse matrix to dense for DBSCAN with cosine metric
                dense_vectors = doc_vectors.toarray()
                cluster_labels = clusterer.fit_predict(dense_vectors)
            else:
                cluster_labels = clusterer.fit_predict(doc_vectors)
            
            # Create content cluster object
            content_cluster = ContentCluster()
            content_cluster.num_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
            
            # Group documents by cluster
            cluster_docs = defaultdict(list)
            for i, label in enumerate(cluster_labels):
                if label != -1:  # Ignore noise points in DBSCAN
                    cluster_docs[label].append(i)
                    content_cluster.page_clusters[page_ids[i]] = label
            
            content_cluster.clusters = dict(cluster_docs)
            
            # Generate cluster summaries
            for cluster_id, doc_indices in cluster_docs.items():
                cluster_documents = [documents[i] for i in doc_indices]
                cluster_vectors = doc_vectors[doc_indices]
                
                # Find representative terms for cluster
                centroid = cluster_vectors.mean(axis=0).A1
                top_terms_idx = centroid.argsort()[-10:][::-1]
                top_terms = [feature_names[i] for i in top_terms_idx]
                
                # Calculate cluster cohesion (average pairwise similarity)
                if len(cluster_documents) > 1:
                    similarities = cosine_similarity(cluster_vectors)
                    cohesion = np.mean(similarities[np.triu_indices_from(similarities, k=1)])
                else:
                    cohesion = 1.0
                
                content_cluster.cluster_labels[cluster_id] = f"Cluster {cluster_id + 1}"
                content_cluster.cluster_summaries[cluster_id] = {
                    'document_count': len(cluster_documents),
                    'top_terms': top_terms,
                    'cohesion_score': float(cohesion),
                    'page_ids': [page_ids[i] for i in doc_indices]
                }
            
            logger.info(f"Clustering completed: {content_cluster.num_clusters} clusters, {len(documents)} documents")
            return content_cluster
            
        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return ContentCluster()
    
    async def _get_documents_for_modeling(
        self,
        db: AsyncSession,
        project_id: Optional[int],
        domain_id: Optional[int],
        max_documents: int
    ) -> Tuple[List[str], List[int]]:
        """Get documents for topic modeling or clustering"""
        try:
            # Build query
            base_query = select(Page.id, Page.extracted_text).where(
                Page.extracted_text.is_not(None),
                func.length(Page.extracted_text) > 100
            )
            
            if project_id:
                base_query = base_query.join(Domain).join(Project).where(Project.id == project_id)
            elif domain_id:
                base_query = base_query.where(Page.domain_id == domain_id)
            
            # Order by recency and limit
            base_query = base_query.order_by(Page.scraped_at.desc()).limit(max_documents)
            
            result = await db.execute(base_query)
            rows = result.all()
            
            documents = []
            page_ids = []
            
            for page_id, text in rows:
                if text and len(text.strip()) > 50:
                    documents.append(text)
                    page_ids.append(page_id)
            
            logger.info(f"Retrieved {len(documents)} documents for modeling")
            return documents, page_ids
            
        except Exception as e:
            logger.error(f"Failed to get documents for modeling: {e}")
            return [], []
    
    async def get_topic_trends(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze topic trends over time
        """
        try:
            # Get topic model
            topic_model = await self.extract_topics_lda(db, project_id, num_topics=10)
            
            if not topic_model.topics:
                return {"trends": [], "time_period_days": days}
            
            # Get documents from different time periods for trend analysis
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            recent_query = select(Page.id, Page.extracted_text, Page.scraped_at).where(
                Page.extracted_text.is_not(None),
                Page.scraped_at >= cutoff_date,
                func.length(Page.extracted_text) > 100
            )
            
            if project_id:
                recent_query = recent_query.join(Domain).join(Project).where(Project.id == project_id)
            
            result = await db.execute(recent_query)
            recent_pages = result.all()
            
            # Analyze topic distribution over time
            # This is a simplified implementation
            trends = []
            for topic in topic_model.topics:
                topic_trend = {
                    'topic_id': topic['id'],
                    'label': topic['label'],
                    'keywords': topic['keywords'],
                    'document_count': 0,
                    'growth_rate': 0.0,
                    'trend_direction': 'stable'
                }
                
                # Count documents matching this topic's keywords
                for page_id, text, scraped_at in recent_pages:
                    if any(keyword.lower() in text.lower() for keyword in topic['keywords']):
                        topic_trend['document_count'] += 1
                
                trends.append(topic_trend)
            
            return {
                "trends": trends,
                "time_period_days": days,
                "total_topics": len(topic_model.topics)
            }
            
        except Exception as e:
            logger.error(f"Failed to get topic trends: {e}")
            return {"trends": [], "time_period_days": days}
    
    async def get_content_clusters_summary(
        self,
        db: AsyncSession,
        project_id: Optional[int] = None,
        domain_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get summary of content clusters
        """
        try:
            content_cluster = await self.cluster_content(
                db, project_id, domain_id, num_clusters=8, method="kmeans"
            )
            
            if not content_cluster.clusters:
                return {"clusters": [], "total_clusters": 0}
            
            cluster_summary = []
            for cluster_id, summary in content_cluster.cluster_summaries.items():
                cluster_info = {
                    'cluster_id': cluster_id,
                    'label': content_cluster.cluster_labels.get(cluster_id, f"Cluster {cluster_id}"),
                    'document_count': summary['document_count'],
                    'top_terms': summary['top_terms'][:5],  # Top 5 terms
                    'cohesion_score': summary['cohesion_score'],
                    'sample_page_ids': summary['page_ids'][:3]  # Sample pages
                }
                cluster_summary.append(cluster_info)
            
            # Sort by document count
            cluster_summary.sort(key=lambda x: x['document_count'], reverse=True)
            
            return {
                "clusters": cluster_summary,
                "total_clusters": content_cluster.num_clusters,
                "total_documents": sum(summary['document_count'] for summary in content_cluster.cluster_summaries.values())
            }
            
        except Exception as e:
            logger.error(f"Failed to get content clusters summary: {e}")
            return {"clusters": [], "total_clusters": 0}


# Global instance
topic_modeling_service = TopicModelingService()