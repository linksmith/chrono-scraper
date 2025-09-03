"""
Wikidata integration service for entity disambiguation and enrichment
"""
import logging
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..models.entities import CanonicalEntity, EntityType

logger = logging.getLogger(__name__)


class WikidataService:
    """Service for Wikidata entity resolution and disambiguation"""
    
    def __init__(self):
        self.base_url = "https://www.wikidata.org"
        self.sparql_endpoint = "https://query.wikidata.org/sparql"
        self.entity_search_url = "https://www.wikidata.org/w/api.php"
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 3600  # 1 hour
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Chrono-Scraper/1.0 (https://github.com/your-repo) Research Tool'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def search_entities(self, query: str, entity_type: str = None, language: str = 'en', limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for entities in Wikidata
        
        Args:
            query: Search query (entity name)
            entity_type: Filter by entity type (person, organization, location, etc.)
            language: Language code for results
            limit: Maximum number of results
            
        Returns:
            List of entity candidates with Wikidata IDs and metadata
        """
        if not self.session:
            logger.error("WikidataService session not initialized. Use async context manager.")
            return []
        
        cache_key = f"search:{query}:{entity_type}:{language}:{limit}"
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if datetime.utcnow().timestamp() - timestamp < self.cache_ttl:
                logger.debug(f"Cache hit for Wikidata search: {query}")
                return cached_result
        
        try:
            # Use Wikidata search API
            params = {
                'action': 'wbsearchentities',
                'format': 'json',
                'language': language,
                'type': 'item',
                'search': query,
                'limit': limit
            }
            
            async with self.session.get(self.entity_search_url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Wikidata search failed: {response.status}")
                    return []
                
                data = await response.json()
                search_results = data.get('search', [])
                
                # Enrich results with additional metadata
                enriched_results = []
                for result in search_results:
                    entity_id = result.get('id')
                    if entity_id:
                        # Get additional details for each entity
                        details = await self._get_entity_details(entity_id, language)
                        
                        enriched_result = {
                            'wikidata_id': entity_id,
                            'label': result.get('label', ''),
                            'description': result.get('description', ''),
                            'url': result.get('concepturi', ''),
                            'match_score': self._calculate_match_score(query, result),
                            'details': details
                        }
                        
                        # Filter by entity type if specified
                        if entity_type:
                            if self._matches_entity_type(details, entity_type):
                                enriched_results.append(enriched_result)
                        else:
                            enriched_results.append(enriched_result)
                
                # Cache results
                self.cache[cache_key] = (enriched_results, datetime.utcnow().timestamp())
                
                logger.debug(f"Found {len(enriched_results)} Wikidata entities for '{query}'")
                return enriched_results
                
        except Exception as e:
            logger.error(f"Wikidata search failed for '{query}': {e}")
            return []
    
    async def _get_entity_details(self, entity_id: str, language: str = 'en') -> Dict[str, Any]:
        """Get detailed information about a Wikidata entity"""
        cache_key = f"details:{entity_id}:{language}"
        if cache_key in self.cache:
            cached_result, timestamp = self.cache[cache_key]
            if datetime.utcnow().timestamp() - timestamp < self.cache_ttl:
                return cached_result
        
        try:
            # SPARQL query to get entity details
            sparql_query = f"""
            SELECT ?item ?itemLabel ?itemDescription ?instanceOf ?instanceOfLabel 
                   ?birthDate ?deathDate ?inception ?dissolved ?country ?countryLabel
                   ?coordinates ?website ?image
            WHERE {{
                BIND(wd:{entity_id} AS ?item)
                OPTIONAL {{ ?item wdt:P31 ?instanceOf . }}
                OPTIONAL {{ ?item wdt:P569 ?birthDate . }}
                OPTIONAL {{ ?item wdt:P570 ?deathDate . }}
                OPTIONAL {{ ?item wdt:P571 ?inception . }}
                OPTIONAL {{ ?item wdt:P576 ?dissolved . }}
                OPTIONAL {{ ?item wdt:P17 ?country . }}
                OPTIONAL {{ ?item wdt:P625 ?coordinates . }}
                OPTIONAL {{ ?item wdt:P856 ?website . }}
                OPTIONAL {{ ?item wdt:P18 ?image . }}
                
                SERVICE wikibase:label {{ 
                    bd:serviceParam wikibase:language "{language},en" . 
                }}
            }}
            """
            
            params = {
                'query': sparql_query,
                'format': 'json'
            }
            
            async with self.session.get(self.sparql_endpoint, params=params) as response:
                if response.status != 200:
                    logger.warning(f"SPARQL query failed for {entity_id}: {response.status}")
                    return {}
                
                data = await response.json()
                bindings = data.get('results', {}).get('bindings', [])
                
                if not bindings:
                    return {}
                
                # Process SPARQL results
                binding = bindings[0]  # Take first result
                details = {
                    'types': [],
                    'birth_date': binding.get('birthDate', {}).get('value'),
                    'death_date': binding.get('deathDate', {}).get('value'),
                    'inception_date': binding.get('inception', {}).get('value'),
                    'dissolved_date': binding.get('dissolved', {}).get('value'),
                    'country': binding.get('countryLabel', {}).get('value'),
                    'coordinates': binding.get('coordinates', {}).get('value'),
                    'website': binding.get('website', {}).get('value'),
                    'image': binding.get('image', {}).get('value')
                }
                
                # Collect all instance types
                for binding in bindings:
                    instance_of = binding.get('instanceOfLabel', {}).get('value')
                    if instance_of and instance_of not in details['types']:
                        details['types'].append(instance_of)
                
                # Cache results
                self.cache[cache_key] = (details, datetime.utcnow().timestamp())
                
                return details
                
        except Exception as e:
            logger.error(f"Failed to get details for entity {entity_id}: {e}")
            return {}
    
    def _calculate_match_score(self, query: str, result: Dict[str, Any]) -> float:
        """Calculate match score between query and search result"""
        label = result.get('label', '').lower()
        description = result.get('description', '').lower()
        query_lower = query.lower()
        
        score = 0.0
        
        # Exact label match gets highest score
        if label == query_lower:
            score = 1.0
        elif query_lower in label:
            score = 0.8
        elif label in query_lower:
            score = 0.7
        else:
            # Calculate string similarity
            score = self._string_similarity(query_lower, label)
        
        # Boost score if query appears in description
        if query_lower in description:
            score = min(1.0, score + 0.1)
        
        # Penalize very short labels that might be ambiguous
        if len(label) < 3:
            score *= 0.8
        
        return score
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity using Jaccard coefficient"""
        if not s1 or not s2:
            return 0.0
        
        # Convert to word sets
        words1 = set(s1.split())
        words2 = set(s2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _matches_entity_type(self, details: Dict[str, Any], entity_type: str) -> bool:
        """Check if entity details match the requested entity type"""
        entity_types = [t.lower() for t in details.get('types', [])]
        
        type_mappings = {
            'person': ['human', 'person', 'individual'],
            'organization': ['organization', 'company', 'corporation', 'business', 'institution', 
                           'government organization', 'non-profit organization', 'political party'],
            'location': ['geographic location', 'city', 'country', 'region', 'place', 'administrative territorial entity',
                        'municipality', 'settlement', 'geographic region'],
            'event': ['event', 'occurrence', 'historical event', 'conference', 'meeting', 'competition']
        }
        
        target_types = type_mappings.get(entity_type.lower(), [entity_type.lower()])
        
        return any(target_type in entity_types for target_type in target_types)
    
    async def disambiguate_entity(self, entity_text: str, entity_type: EntityType, 
                                context: str = "", language: str = 'en') -> Optional[Dict[str, Any]]:
        """
        Disambiguate an entity using context and return best Wikidata match
        
        Args:
            entity_text: The entity text to disambiguate
            entity_type: Type of entity (person, organization, etc.)
            context: Context text to help disambiguation
            language: Language code
            
        Returns:
            Best matching Wikidata entity or None
        """
        type_mapping = {
            EntityType.PERSON: 'person',
            EntityType.ORGANIZATION: 'organization',
            EntityType.LOCATION: 'location',
            EntityType.EVENT: 'event'
        }
        
        search_type = type_mapping.get(entity_type)
        candidates = await self.search_entities(entity_text, search_type, language, limit=5)
        
        if not candidates:
            logger.debug(f"No Wikidata candidates found for '{entity_text}'")
            return None
        
        # If only one candidate with high confidence, return it
        if len(candidates) == 1 and candidates[0]['match_score'] > 0.8:
            return candidates[0]
        
        # Use context to improve disambiguation
        if context:
            best_candidate = self._select_best_with_context(candidates, context)
            if best_candidate:
                return best_candidate
        
        # Return highest scoring candidate
        best_candidate = max(candidates, key=lambda x: x['match_score'])
        if best_candidate['match_score'] > 0.6:  # Minimum confidence threshold
            return best_candidate
        
        logger.debug(f"No high-confidence Wikidata match for '{entity_text}' (best score: {best_candidate['match_score']})")
        return None
    
    def _select_best_with_context(self, candidates: List[Dict[str, Any]], context: str) -> Optional[Dict[str, Any]]:
        """Select best candidate using context information"""
        context_lower = context.lower()
        
        # Look for context clues in descriptions
        best_candidate = None
        best_score = 0.0
        
        for candidate in candidates:
            context_score = 0.0
            description = candidate.get('description', '').lower()
            details = candidate.get('details', {})
            
            # Check if description keywords appear in context
            if description:
                desc_words = set(description.split())
                context_words = set(context_lower.split())
                common_words = desc_words.intersection(context_words)
                context_score = len(common_words) / len(desc_words) if desc_words else 0
            
            # Boost score for additional context matches
            if details.get('country') and details['country'].lower() in context_lower:
                context_score += 0.2
            
            # Combine original match score with context score
            total_score = candidate['match_score'] * 0.7 + context_score * 0.3
            
            if total_score > best_score:
                best_score = total_score
                best_candidate = candidate
        
        return best_candidate if best_score > 0.5 else None
    
    async def enrich_canonical_entity(self, canonical_entity: CanonicalEntity, 
                                    language: str = 'en') -> Dict[str, Any]:
        """
        Enrich a canonical entity with Wikidata information
        
        Args:
            canonical_entity: The entity to enrich
            language: Language for Wikidata content
            
        Returns:
            Enrichment data to merge with entity
        """
        wikidata_match = await self.disambiguate_entity(
            canonical_entity.primary_name,
            canonical_entity.entity_type,
            canonical_entity.description or "",
            language
        )
        
        if not wikidata_match:
            return {}
        
        # Prepare enrichment data
        enrichment = {
            'wikidata_id': wikidata_match['wikidata_id'],
            'wikidata_url': wikidata_match['url'],
            'wikidata_description': wikidata_match['description'],
            'confidence_score': max(canonical_entity.confidence_score, wikidata_match['match_score']),
        }
        
        # Add structured details
        details = wikidata_match.get('details', {})
        if details:
            # Update external IDs
            new_external_ids = canonical_entity.external_ids.copy()
            new_external_ids['wikidata'] = wikidata_match['wikidata_id']
            enrichment['external_ids'] = new_external_ids
            
            # Update attributes with Wikidata info
            new_attributes = canonical_entity.attributes.copy()
            
            if canonical_entity.entity_type == EntityType.PERSON:
                if details.get('birth_date'):
                    new_attributes['birth_date'] = details['birth_date']
                if details.get('death_date'):
                    new_attributes['death_date'] = details['death_date']
                if details.get('country'):
                    new_attributes['nationality'] = details['country']
                    
            elif canonical_entity.entity_type == EntityType.ORGANIZATION:
                if details.get('inception_date'):
                    new_attributes['founded'] = details['inception_date']
                if details.get('dissolved_date'):
                    new_attributes['dissolved'] = details['dissolved_date']
                if details.get('country'):
                    new_attributes['headquarters'] = details['country']
                    
            elif canonical_entity.entity_type == EntityType.LOCATION:
                if details.get('country'):
                    new_attributes['country'] = details['country']
                if details.get('coordinates'):
                    new_attributes['coordinates'] = details['coordinates']
            
            # Add entity types and website
            if details.get('types'):
                new_attributes['wikidata_types'] = details['types']
            if details.get('website'):
                new_attributes['website'] = details['website']
            
            enrichment['attributes'] = new_attributes
            
            # Improve description if current one is empty or generic
            if not canonical_entity.description or len(canonical_entity.description) < 20:
                if wikidata_match['description']:
                    enrichment['description'] = wikidata_match['description']
        
        logger.info(f"Enriched entity '{canonical_entity.primary_name}' with Wikidata ID: {wikidata_match['wikidata_id']}")
        return enrichment


# Global service instance
wikidata_service = WikidataService()