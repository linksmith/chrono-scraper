"""
Entity extraction backend implementations with pluggable architecture
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json

from ..models.entities import EntityType, ExtractedEntity

logger = logging.getLogger(__name__)


class EntityExtractionBackend(ABC):
    """Abstract base class for entity extraction backends"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.is_available = False
        self._initialize()
    
    @abstractmethod
    async def _initialize(self):
        """Initialize the backend (load models, check connections, etc.)"""
        pass
    
    @abstractmethod
    async def extract_entities(self, text: str, language: str = 'en') -> List[Dict[str, Any]]:
        """
        Extract entities from text
        
        Args:
            text: Input text to process
            language: Language code (en, nl, etc.)
            
        Returns:
            List of extracted entities with structure:
            {
                'text': str,
                'normalized_text': str,
                'entity_type': EntityType,
                'start_position': int,
                'end_position': int,
                'confidence': float,
                'extraction_method': str,
                'context': str,
                'attributes': dict
            }
        """
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """Check backend health and availability"""
        return {
            'backend': self.name,
            'available': self.is_available,
            'config': self.config,
            'timestamp': datetime.utcnow().isoformat()
        }


class EnhancedSpacyBackend(EntityExtractionBackend):
    """Enhanced spaCy backend with Dutch support and improved similarity matching"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.nlp_models = {}
        self.model_configs = {
            'en': 'en_core_web_trf',    # Transformer-based English
            'nl': 'nl_core_news_lg',    # Large Dutch model
            'xx': 'xx_ent_wiki_sm'      # Multilingual fallback
        }
        super().__init__('enhanced_spacy', config)
    
    async def _initialize(self):
        """Initialize spaCy models"""
        try:
            import spacy
            from spacy.lang.en import English
            from spacy.lang.nl import Dutch
            
            # Load available models
            for lang, model_name in self.model_configs.items():
                try:
                    nlp = spacy.load(model_name)
                    self.nlp_models[lang] = nlp
                    logger.info(f"Loaded {model_name} for {lang}")
                except OSError:
                    logger.warning(f"Model {model_name} not found for {lang}")
                    # Fallback to basic model
                    if lang == 'en':
                        try:
                            nlp = spacy.load('en_core_web_sm')
                            self.nlp_models[lang] = nlp
                            logger.info(f"Loaded fallback en_core_web_sm for {lang}")
                        except OSError:
                            logger.error(f"No English model available")
                    elif lang == 'nl':
                        try:
                            nlp = spacy.load('nl_core_news_sm')
                            self.nlp_models[lang] = nlp
                            logger.info(f"Loaded fallback nl_core_news_sm for {lang}")
                        except OSError:
                            logger.error(f"No Dutch model available")
            
            self.is_available = len(self.nlp_models) > 0
            logger.info(f"Enhanced spaCy backend initialized with {len(self.nlp_models)} models")
            
        except ImportError:
            logger.error("spaCy not installed")
            self.is_available = False
    
    async def extract_entities(self, text: str, language: str = 'en') -> List[Dict[str, Any]]:
        """Extract entities using enhanced spaCy processing"""
        if not self.is_available:
            logger.warning("Enhanced spaCy backend not available")
            return []
        
        # Select appropriate model
        nlp = self.nlp_models.get(language)
        if not nlp:
            # Fallback to multilingual or English
            nlp = self.nlp_models.get('xx') or self.nlp_models.get('en')
            if not nlp:
                logger.error(f"No suitable model found for language {language}")
                return []
        
        try:
            # Process text in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, nlp, text)
            
            entities = []
            for ent in doc.ents:
                entity_type = self._map_spacy_label_to_type(ent.label_)
                if entity_type:  # Only include recognized entity types
                    entities.append({
                        'text': ent.text,
                        'normalized_text': ent.text.lower().strip(),
                        'entity_type': entity_type,
                        'start_position': ent.start_char,
                        'end_position': ent.end_char,
                        'confidence': self._calculate_confidence(ent),
                        'extraction_method': 'enhanced_spacy',
                        'context': self._extract_context(text, ent.start_char, ent.end_char),
                        'attributes': {
                            'spacy_label': ent.label_,
                            'language': language,
                            'model': str(nlp.meta.get('name', 'unknown')),
                            'lemma': ent.lemma_ if hasattr(ent, 'lemma_') else None,
                            'pos': ent.root.pos_ if hasattr(ent, 'root') else None
                        }
                    })
            
            logger.debug(f"Extracted {len(entities)} entities using enhanced spaCy ({language})")
            return entities
            
        except Exception as e:
            logger.error(f"Enhanced spaCy extraction failed: {e}")
            return []
    
    def _map_spacy_label_to_type(self, spacy_label: str) -> Optional[EntityType]:
        """Map spaCy entity labels to our EntityType enum"""
        mapping = {
            'PERSON': EntityType.PERSON,
            'PER': EntityType.PERSON,
            'ORG': EntityType.ORGANIZATION,
            'GPE': EntityType.LOCATION,  # Geopolitical entity
            'LOC': EntityType.LOCATION,
            'EVENT': EntityType.EVENT,
            'PRODUCT': EntityType.PRODUCT,
            'DATE': EntityType.DATE,
            'TIME': EntityType.DATE,
            'MONEY': EntityType.MONEY,
            'EMAIL': EntityType.EMAIL,
            'URL': EntityType.URL,
        }
        return mapping.get(spacy_label)
    
    def _calculate_confidence(self, ent) -> float:
        """Calculate confidence score for spaCy entities"""
        # Base confidence on entity characteristics
        base_confidence = 0.8
        
        # Adjust based on entity properties
        if len(ent.text) < 2:
            base_confidence -= 0.3  # Very short entities are less reliable
        elif len(ent.text.split()) > 3:
            base_confidence -= 0.1  # Very long entities might be noisy
        
        # Title case entities are often more reliable
        if ent.text.istitle():
            base_confidence += 0.1
        
        # All caps might be acronyms (good) or noise (bad)
        if ent.text.isupper() and len(ent.text) <= 5:
            base_confidence += 0.05
        elif ent.text.isupper():
            base_confidence -= 0.1
        
        return max(0.1, min(1.0, base_confidence))
    
    def _extract_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        """Extract context around entity"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        context = text[context_start:context_end].strip()
        
        # Add ellipsis indicators
        if context_start > 0:
            context = '...' + context
        if context_end < len(text):
            context = context + '...'
        
        return context


class FirecrawlExtractionBackend(EntityExtractionBackend):
    """Firecrawl-based entity extraction using custom schemas"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.firecrawl_url = config.get('firecrawl_url', 'http://localhost:3002') if config else 'http://localhost:3002'
        self.api_key = config.get('api_key') if config else None
        self.extraction_schemas = self._create_default_schemas()
        super().__init__('firecrawl_extraction', config)
    
    async def _initialize(self):
        """Initialize Firecrawl connection"""
        try:
            import requests
            
            # Test Firecrawl availability
            response = requests.get(f"{self.firecrawl_url}/", timeout=10)
            self.is_available = response.status_code == 200
            
            if self.is_available:
                logger.info(f"Firecrawl extraction backend connected to {self.firecrawl_url}")
            else:
                logger.warning(f"Firecrawl not available at {self.firecrawl_url}")
                
        except Exception as e:
            logger.error(f"Failed to connect to Firecrawl: {e}")
            self.is_available = False
    
    def _create_default_schemas(self) -> Dict[str, Any]:
        """Create default extraction schemas for entity types"""
        return {
            'entities': {
                'type': 'object',
                'properties': {
                    'persons': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'string'},
                                'title': {'type': 'string'},
                                'organization': {'type': 'string'},
                                'context': {'type': 'string'}
                            }
                        }
                    },
                    'organizations': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'string'},
                                'type': {'type': 'string'},
                                'industry': {'type': 'string'},
                                'location': {'type': 'string'},
                                'context': {'type': 'string'}
                            }
                        }
                    },
                    'locations': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'string'},
                                'type': {'type': 'string'},  # city, country, etc.
                                'country': {'type': 'string'},
                                'region': {'type': 'string'},
                                'context': {'type': 'string'}
                            }
                        }
                    },
                    'events': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'string'},
                                'type': {'type': 'string'},
                                'date': {'type': 'string'},
                                'location': {'type': 'string'},
                                'participants': {'type': 'array', 'items': {'type': 'string'}},
                                'context': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        }
    
    async def extract_entities(self, text: str, language: str = 'en') -> List[Dict[str, Any]]:
        """Extract entities using Firecrawl's structured extraction"""
        if not self.is_available:
            logger.warning("Firecrawl extraction backend not available")
            return []
        
        try:
            import requests
            
            # Create extraction prompt based on language
            prompt = self._create_extraction_prompt(language)
            
            # Make request to Firecrawl extract endpoint
            payload = {
                'data': [{'text': text}],  # Firecrawl expects data array
                'prompt': prompt,
                'schema': self.extraction_schemas
            }
            
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            response = requests.post(
                f"{self.firecrawl_url}/v0/extract",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Firecrawl extraction failed: {response.status_code} {response.text}")
                return []
            
            result = response.json()
            
            # Convert Firecrawl result to our entity format
            entities = self._process_firecrawl_result(result, text)
            
            logger.info(f"Extracted {len(entities)} entities using Firecrawl")
            return entities
            
        except Exception as e:
            logger.error(f"Firecrawl extraction failed: {e}")
            return []
    
    def _create_extraction_prompt(self, language: str) -> str:
        """Create extraction prompt based on language"""
        if language == 'nl':
            return """
            Analyseer de gegeven tekst en extracteer alle genoemde entiteiten.
            Identificeer personen, organisaties, locaties en gebeurtenissen.
            Geef voor elke entiteit de context waarin deze wordt genoemd.
            """
        else:  # Default to English
            return """
            Analyze the given text and extract all mentioned entities.
            Identify persons, organizations, locations, and events.
            For each entity, provide the context in which it is mentioned.
            """
    
    def _process_firecrawl_result(self, result: Dict, original_text: str) -> List[Dict[str, Any]]:
        """Convert Firecrawl extraction result to our entity format"""
        entities = []
        
        # Handle different result structures from Firecrawl
        data = result.get('data', [])
        if data and len(data) > 0:
            extracted = data[0].get('entities', {})
        else:
            extracted = result.get('entities', {})
        
        # Process each entity type
        entity_mappings = {
            'persons': EntityType.PERSON,
            'organizations': EntityType.ORGANIZATION,
            'locations': EntityType.LOCATION,
            'events': EntityType.EVENT
        }
        
        for entity_category, entity_type in entity_mappings.items():
            entity_list = extracted.get(entity_category, [])
            
            for entity_data in entity_list:
                if isinstance(entity_data, dict):
                    name = entity_data.get('name', '')
                    if name:
                        # Find position in original text (approximate)
                        start_pos = original_text.lower().find(name.lower())
                        end_pos = start_pos + len(name) if start_pos != -1 else -1
                        
                        entities.append({
                            'text': name,
                            'normalized_text': name.lower().strip(),
                            'entity_type': entity_type,
                            'start_position': start_pos if start_pos != -1 else 0,
                            'end_position': end_pos if end_pos != -1 else len(name),
                            'confidence': 0.85,  # High confidence for LLM extraction
                            'extraction_method': 'firecrawl_llm',
                            'context': entity_data.get('context', ''),
                            'attributes': {
                                'category': entity_category,
                                'additional_info': {k: v for k, v in entity_data.items() if k not in ['name', 'context']}
                            }
                        })
        
        return entities


# Backend registry for easy access
AVAILABLE_BACKENDS = {
    'enhanced_spacy': EnhancedSpacyBackend,
    'firecrawl_extraction': FirecrawlExtractionBackend,
}


async def get_backend(backend_name: str, config: Dict[str, Any] = None) -> EntityExtractionBackend:
    """Get and initialize an entity extraction backend"""
    if backend_name not in AVAILABLE_BACKENDS:
        raise ValueError(f"Unknown backend: {backend_name}. Available: {list(AVAILABLE_BACKENDS.keys())}")
    
    backend_class = AVAILABLE_BACKENDS[backend_name]
    backend = backend_class(config)
    await backend._initialize()
    
    return backend


async def list_available_backends() -> List[Dict[str, Any]]:
    """List all available backends with their status"""
    backends = []
    
    for name, backend_class in AVAILABLE_BACKENDS.items():
        try:
            backend = backend_class()
            await backend._initialize()
            health = await backend.health_check()
            backends.append(health)
        except Exception as e:
            backends.append({
                'backend': name,
                'available': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
    
    return backends