"""
Entity extraction and linking service
"""
import logging
import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import (
    CanonicalEntity, ExtractedEntity, EntityRelationship, 
    EntityMention, EntityResolution, EntityType, EntityStatus
)
from app.models.project import Page, Project
from app.models.user import User

logger = logging.getLogger(__name__)


class EntityExtractionService:
    """Service for extracting and linking entities from content"""
    
    def __init__(self):
        self.nlp_model = None
        self.extraction_patterns = self._initialize_patterns()
        self.confidence_threshold = 0.7
        self.similarity_threshold = 0.8
    
    def _initialize_patterns(self) -> Dict[str, Any]:
        """Initialize regex patterns for entity extraction"""
        return {
            EntityType.EMAIL: re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            EntityType.PHONE: re.compile(r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'),
            EntityType.URL: re.compile(r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'),
            EntityType.HASHTAG: re.compile(r'#\w+'),
            EntityType.MENTION: re.compile(r'@\w+'),
            EntityType.MONEY: re.compile(r'\$[\d,]+(?:\.\d{2})?|\$?\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP|CAD)'),
        }
    
    async def _get_nlp_model(self):
        """Initialize NLP model for entity extraction (lazy loading)"""
        if self.nlp_model is None:
            try:
                import spacy
                # Download model if not present
                try:
                    self.nlp_model = spacy.load("en_core_web_sm")
                except OSError:
                    logger.warning("spaCy model 'en_core_web_sm' not found. Using pattern-based extraction only.")
                    self.nlp_model = False  # Mark as unavailable
            except ImportError:
                logger.warning("spaCy not installed. Using pattern-based extraction only.")
                self.nlp_model = False
        
        return self.nlp_model if self.nlp_model else None
    
    async def extract_entities_from_text(
        self, 
        text: str,
        extraction_method: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """Extract entities from text using various methods"""
        try:
            entities = []
            
            if extraction_method in ["hybrid", "nlp"]:
                # Try NLP-based extraction
                nlp_entities = await self._extract_with_nlp(text)
                entities.extend(nlp_entities)
            
            if extraction_method in ["hybrid", "pattern"]:
                # Pattern-based extraction
                pattern_entities = await self._extract_with_patterns(text)
                entities.extend(pattern_entities)
            
            # Deduplicate and merge entities
            entities = await self._deduplicate_entities(entities)
            
            return entities
            
        except Exception as e:
            logger.error(f"Failed to extract entities from text: {e}")
            return []
    
    async def _extract_with_nlp(self, text: str) -> List[Dict[str, Any]]:
        """Extract entities using spaCy NLP model"""
        try:
            nlp = await self._get_nlp_model()
            if not nlp:
                return []
            
            # Run NLP processing in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, nlp, text)
            
            entities = []
            for ent in doc.ents:
                entity_type = self._map_spacy_label_to_type(ent.label_)
                if entity_type:
                    entities.append({
                        "text": ent.text,
                        "normalized_text": ent.text.lower().strip(),
                        "entity_type": entity_type,
                        "start_position": ent.start_char,
                        "end_position": ent.end_char,
                        "confidence": ent._.get("confidence", 0.8),
                        "extraction_method": "nlp",
                        "context": text[max(0, ent.start_char-50):ent.end_char+50],
                        "attributes": {
                            "label": ent.label_,
                            "sentiment": getattr(ent, "sentiment", None),
                        }
                    })
            
            return entities
            
        except Exception as e:
            logger.error(f"NLP entity extraction failed: {e}")
            return []
    
    async def _extract_with_patterns(self, text: str) -> List[Dict[str, Any]]:
        """Extract entities using regex patterns"""
        try:
            entities = []
            
            for entity_type, pattern in self.extraction_patterns.items():
                matches = pattern.finditer(text)
                for match in matches:
                    entities.append({
                        "text": match.group(),
                        "normalized_text": match.group().lower().strip(),
                        "entity_type": entity_type,
                        "start_position": match.start(),
                        "end_position": match.end(),
                        "confidence": 0.9,  # High confidence for pattern matches
                        "extraction_method": "pattern",
                        "context": text[max(0, match.start()-50):match.end()+50],
                        "attributes": {}
                    })
            
            return entities
            
        except Exception as e:
            logger.error(f"Pattern entity extraction failed: {e}")
            return []
    
    def _map_spacy_label_to_type(self, spacy_label: str) -> Optional[EntityType]:
        """Map spaCy entity labels to our EntityType enum"""
        mapping = {
            "PERSON": EntityType.PERSON,
            "ORG": EntityType.ORGANIZATION,
            "GPE": EntityType.LOCATION,  # Geopolitical entity
            "LOC": EntityType.LOCATION,
            "EVENT": EntityType.EVENT,
            "PRODUCT": EntityType.PRODUCT,
            "DATE": EntityType.DATE,
            "TIME": EntityType.DATE,
            "MONEY": EntityType.MONEY,
        }
        return mapping.get(spacy_label)
    
    async def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate entities and merge overlapping ones"""
        try:
            if not entities:
                return []
            
            # Sort by position
            entities.sort(key=lambda x: (x["start_position"], x["end_position"]))
            
            deduplicated = []
            for entity in entities:
                # Check for overlap with existing entities
                merged = False
                for existing in deduplicated:
                    if (entity["entity_type"] == existing["entity_type"] and
                        self._entities_overlap(entity, existing)):
                        # Merge entities, keeping the one with higher confidence
                        if entity["confidence"] > existing["confidence"]:
                            deduplicated.remove(existing)
                            deduplicated.append(entity)
                        merged = True
                        break
                
                if not merged:
                    deduplicated.append(entity)
            
            return deduplicated
            
        except Exception as e:
            logger.error(f"Entity deduplication failed: {e}")
            return entities
    
    def _entities_overlap(self, entity1: Dict[str, Any], entity2: Dict[str, Any]) -> bool:
        """Check if two entities overlap in position"""
        return not (entity1["end_position"] <= entity2["start_position"] or 
                   entity2["end_position"] <= entity1["start_position"])
    
    async def extract_and_store_entities(
        self, 
        db: AsyncSession,
        page: Page,
        text: str,
        user: User
    ) -> List[ExtractedEntity]:
        """Extract entities from text and store them in database"""
        try:
            # Extract entities from text
            extracted_data = await self.extract_entities_from_text(text)
            
            stored_entities = []
            for entity_data in extracted_data:
                # Create extracted entity
                extracted_entity = ExtractedEntity(
                    page_id=page.id,
                    project_id=page.domain.project_id if hasattr(page, 'domain') else None,
                    entity_type=entity_data["entity_type"],
                    text=entity_data["text"],
                    normalized_text=entity_data["normalized_text"],
                    start_position=entity_data.get("start_position"),
                    end_position=entity_data.get("end_position"),
                    context=entity_data.get("context"),
                    extraction_method=entity_data["extraction_method"],
                    extraction_confidence=entity_data["confidence"],
                    extractor_version="1.0"
                )
                
                # Try to link to canonical entity
                canonical_entity = await self._find_or_create_canonical_entity(
                    db, entity_data
                )
                
                if canonical_entity:
                    extracted_entity.canonical_entity_id = canonical_entity.id
                    extracted_entity.linking_confidence = self._calculate_linking_confidence(
                        entity_data, canonical_entity
                    )
                    extracted_entity.linking_method = "automatic"
                    
                    # Update canonical entity stats
                    canonical_entity.occurrence_count += 1
                    canonical_entity.last_seen = datetime.utcnow()
                
                db.add(extracted_entity)
                stored_entities.append(extracted_entity)
            
            await db.commit()
            
            # Record usage
            from app.services.plan_service import plan_service
            await plan_service.record_usage(
                db, user, "entity_extracted", count=len(stored_entities)
            )
            
            logger.info(f"Extracted and stored {len(stored_entities)} entities from page {page.id}")
            return stored_entities
            
        except Exception as e:
            logger.error(f"Failed to extract and store entities: {e}")
            await db.rollback()
            return []
    
    async def _find_or_create_canonical_entity(
        self, 
        db: AsyncSession,
        entity_data: Dict[str, Any]
    ) -> Optional[CanonicalEntity]:
        """Find existing canonical entity or create new one"""
        try:
            entity_type = entity_data["entity_type"]
            normalized_text = entity_data["normalized_text"]
            
            # Look for exact match first
            result = await db.execute(
                select(CanonicalEntity).where(
                    CanonicalEntity.entity_type == entity_type,
                    CanonicalEntity.normalized_name == normalized_text
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                return existing
            
            # Look for similar entities (fuzzy matching)
            similar_entity = await self._find_similar_canonical_entity(
                db, entity_type, normalized_text
            )
            
            if similar_entity:
                # Add as alias to existing entity
                if normalized_text not in similar_entity.aliases:
                    similar_entity.aliases.append(normalized_text)
                    similar_entity.updated_at = datetime.utcnow()
                return similar_entity
            
            # Create new canonical entity
            canonical_entity = CanonicalEntity(
                entity_type=entity_type,
                primary_name=entity_data["text"],
                normalized_name=normalized_text,
                attributes=entity_data.get("attributes", {}),
                confidence_score=entity_data["confidence"],
                status=EntityStatus.UNVERIFIED
            )
            
            db.add(canonical_entity)
            await db.commit()
            await db.refresh(canonical_entity)
            
            return canonical_entity
            
        except Exception as e:
            logger.error(f"Failed to find or create canonical entity: {e}")
            return None
    
    async def _find_similar_canonical_entity(
        self, 
        db: AsyncSession,
        entity_type: EntityType,
        normalized_text: str
    ) -> Optional[CanonicalEntity]:
        """Find similar canonical entities using fuzzy matching"""
        try:
            # Get entities of the same type
            result = await db.execute(
                select(CanonicalEntity).where(
                    CanonicalEntity.entity_type == entity_type
                ).limit(100)  # Limit for performance
            )
            entities = result.scalars().all()
            
            # Simple similarity check
            for entity in entities:
                if self._calculate_text_similarity(normalized_text, entity.normalized_name) > self.similarity_threshold:
                    return entity
                
                # Check aliases
                for alias in entity.aliases:
                    if self._calculate_text_similarity(normalized_text, alias.lower()) > self.similarity_threshold:
                        return entity
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find similar canonical entity: {e}")
            return None
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using simple metrics"""
        try:
            # Exact match
            if text1 == text2:
                return 1.0
            
            # Length difference check
            if abs(len(text1) - len(text2)) > max(len(text1), len(text2)) * 0.3:
                return 0.0
            
            # Simple character overlap ratio
            set1, set2 = set(text1), set(text2)
            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))
            
            return intersection / union if union > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Text similarity calculation failed: {e}")
            return 0.0
    
    def _calculate_linking_confidence(
        self, 
        entity_data: Dict[str, Any],
        canonical_entity: CanonicalEntity
    ) -> float:
        """Calculate confidence score for entity linking"""
        try:
            # Start with extraction confidence
            confidence = entity_data["confidence"]
            
            # Boost for exact matches
            if entity_data["normalized_text"] == canonical_entity.normalized_name:
                confidence = min(1.0, confidence + 0.2)
            
            # Consider canonical entity's confidence
            confidence = (confidence + canonical_entity.confidence_score) / 2
            
            return confidence
            
        except Exception as e:
            logger.error(f"Linking confidence calculation failed: {e}")
            return 0.5
    
    async def get_entity_mentions(
        self, 
        db: AsyncSession,
        entity_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get mentions of a specific entity"""
        try:
            result = await db.execute(
                select(ExtractedEntity).where(
                    ExtractedEntity.canonical_entity_id == entity_id
                ).order_by(ExtractedEntity.extracted_at.desc()).limit(limit)
            )
            mentions = result.scalars().all()
            
            mention_data = []
            for mention in mentions:
                mention_data.append({
                    "id": mention.id,
                    "text": mention.text,
                    "context": mention.context,
                    "page_id": mention.page_id,
                    "extracted_at": mention.extracted_at,
                    "confidence": mention.extraction_confidence,
                })
            
            return mention_data
            
        except Exception as e:
            logger.error(f"Failed to get entity mentions: {e}")
            return []
    
    async def get_entity_relationships(
        self, 
        db: AsyncSession,
        entity_id: int
    ) -> List[Dict[str, Any]]:
        """Get relationships for a specific entity"""
        try:
            # Get relationships where entity is source
            result = await db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == entity_id
                )
            )
            source_relationships = result.scalars().all()
            
            # Get relationships where entity is target
            result = await db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.target_entity_id == entity_id
                )
            )
            target_relationships = result.scalars().all()
            
            relationships = []
            
            for rel in source_relationships:
                relationships.append({
                    "id": rel.id,
                    "type": rel.relationship_type,
                    "direction": "outgoing",
                    "target_entity_id": rel.target_entity_id,
                    "confidence": rel.confidence_score,
                    "properties": rel.properties,
                })
            
            for rel in target_relationships:
                relationships.append({
                    "id": rel.id,
                    "type": rel.relationship_type,
                    "direction": "incoming",
                    "source_entity_id": rel.source_entity_id,
                    "confidence": rel.confidence_score,
                    "properties": rel.properties,
                })
            
            return relationships
            
        except Exception as e:
            logger.error(f"Failed to get entity relationships: {e}")
            return []


# Global service instance
entity_extraction_service = EntityExtractionService()