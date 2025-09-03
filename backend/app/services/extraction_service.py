"""
Content extraction service for advanced structured data extraction
"""
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, and_, func

# Optional dependency: spaCy. Avoid import-time failure in minimal test envs.
try:  # pragma: no cover - import guard
    import spacy as _spacy
except Exception:  # pragma: no cover
    _spacy = None
from concurrent.futures import ThreadPoolExecutor

from app.models.user import User
from app.models.shared_pages import PageV2 as Page
from app.models.extraction_schemas import (
    ContentExtractionSchema,
    ContentExtraction,
    ExtractionTemplate,
    SchemaType,
    ExtractionStatus,
    ExtractionMethod
)


class ExtractionService:
    """Service for managing content extraction schemas and extraction jobs"""
    
    def __init__(self):
        self.nlp = None
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def _load_nlp_model(self):
        """Load spaCy NLP model in thread pool"""
        if self.nlp is None and _spacy is not None:
            def load_model():
                try:
                    return _spacy.load("en_core_web_sm")
                except OSError:
                    # Fallback to blank model if language model not available
                    return _spacy.blank("en")
            
            loop = asyncio.get_event_loop()
            self.nlp = await loop.run_in_executor(self.executor, load_model)
    
    # Schema Management
    async def create_schema(
        self,
        db: AsyncSession,
        user: User,
        name: str,
        description: str,
        schema_type: SchemaType,
        field_definitions: Dict[str, Any],
        extraction_method: ExtractionMethod = ExtractionMethod.HYBRID,
        extraction_rules: Dict[str, Any] = None,
        css_selectors: Dict[str, str] = None,
        xpath_selectors: Dict[str, str] = None,
        llm_prompt_template: str = None,
        llm_model: str = None,
        validation_rules: Dict[str, Any] = None,
        confidence_threshold: float = 0.7
    ) -> ContentExtractionSchema:
        """Create a new content extraction schema"""
        
        schema = ContentExtractionSchema(
            user_id=user.id,
            name=name,
            description=description,
            schema_type=schema_type,
            field_definitions=field_definitions or {},
            extraction_method=extraction_method,
            extraction_rules=extraction_rules or {},
            css_selectors=css_selectors or {},
            xpath_selectors=xpath_selectors or {},
            llm_prompt_template=llm_prompt_template,
            llm_model=llm_model,
            validation_rules=validation_rules or {},
            confidence_threshold=confidence_threshold
        )
        
        db.add(schema)
        await db.commit()
        await db.refresh(schema)
        return schema
    
    async def update_schema(
        self,
        db: AsyncSession,
        user: User,
        schema_id: int,
        updates: Dict[str, Any]
    ) -> Optional[ContentExtractionSchema]:
        """Update an existing content extraction schema"""
        
        result = await db.execute(
            select(ContentExtractionSchema).where(
                and_(
                    ContentExtractionSchema.id == schema_id,
                    ContentExtractionSchema.user_id == user.id
                )
            )
        )
        schema = result.scalar_one_or_none()
        
        if not schema:
            return None
        
        # Create new version for significant changes
        if any(key in updates for key in ['field_definitions', 'extraction_rules', 'css_selectors', 'xpath_selectors']):
            new_schema = ContentExtractionSchema(
                user_id=user.id,
                name=updates.get('name', schema.name),
                description=updates.get('description', schema.description),
                schema_type=schema.schema_type,
                field_definitions=updates.get('field_definitions', schema.field_definitions),
                extraction_method=updates.get('extraction_method', schema.extraction_method),
                extraction_rules=updates.get('extraction_rules', schema.extraction_rules),
                css_selectors=updates.get('css_selectors', schema.css_selectors),
                xpath_selectors=updates.get('xpath_selectors', schema.xpath_selectors),
                llm_prompt_template=updates.get('llm_prompt_template', schema.llm_prompt_template),
                llm_model=updates.get('llm_model', schema.llm_model),
                validation_rules=updates.get('validation_rules', schema.validation_rules),
                confidence_threshold=updates.get('confidence_threshold', schema.confidence_threshold),
                version=schema.version + 1,
                parent_schema_id=schema.id,
                is_active=updates.get('is_active', schema.is_active),
                is_public=updates.get('is_public', schema.is_public)
            )
            
            db.add(new_schema)
            await db.commit()
            await db.refresh(new_schema)
            return new_schema
        else:
            # Minor updates to existing schema
            for key, value in updates.items():
                if hasattr(schema, key):
                    setattr(schema, key, value)
            
            schema.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(schema)
            return schema
    
    async def get_user_schemas(
        self,
        db: AsyncSession,
        user: User,
        schema_type: Optional[SchemaType] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> List[ContentExtractionSchema]:
        """Get user's content extraction schemas"""
        
        query = select(ContentExtractionSchema).where(
            ContentExtractionSchema.user_id == user.id
        )
        
        if schema_type:
            query = query.where(ContentExtractionSchema.schema_type == schema_type)
        
        if is_active:
            query = query.where(ContentExtractionSchema.is_active is True)
        
        query = query.order_by(ContentExtractionSchema.updated_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    async def get_public_schemas(
        self,
        db: AsyncSession,
        schema_type: Optional[SchemaType] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ContentExtractionSchema]:
        """Get public content extraction schemas"""
        
        query = select(ContentExtractionSchema).where(
            and_(
                ContentExtractionSchema.is_public is True,
                ContentExtractionSchema.is_active is True
            )
        )
        
        if schema_type:
            query = query.where(ContentExtractionSchema.schema_type == schema_type)
        
        query = query.order_by(ContentExtractionSchema.usage_count.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    # Content Extraction
    async def extract_content_with_schema(
        self,
        db: AsyncSession,
        user: User,
        page: Page,
        schema: ContentExtractionSchema,
        content: str = None
    ) -> ContentExtraction:
        """Extract structured content from a page using a schema"""
        
        # Use page content or provided content (after schema optimization)
        text_content = content or page.extracted_text or ""
        
        if not text_content:
            raise ValueError("No content available for extraction")
        
        # Create extraction record
        extraction = ContentExtraction(
            page_id=page.id,
            schema_id=schema.id,
            user_id=user.id,
            extraction_method=schema.extraction_method,
            status=ExtractionStatus.IN_PROGRESS
        )
        
        db.add(extraction)
        await db.commit()
        await db.refresh(extraction)
        
        try:
            start_time = datetime.utcnow()
            
            # Perform extraction based on method
            if schema.extraction_method == ExtractionMethod.RULE_BASED:
                extracted_data = await self._extract_with_rules(text_content, schema)
            elif schema.extraction_method == ExtractionMethod.ML_MODEL:
                extracted_data = await self._extract_with_ml(text_content, schema)
            elif schema.extraction_method == ExtractionMethod.LLM_EXTRACT:
                extracted_data = await self._extract_with_llm(text_content, schema)
            elif schema.extraction_method == ExtractionMethod.HYBRID:
                extracted_data = await self._extract_hybrid(text_content, schema)
            else:
                raise ValueError(f"Unknown extraction method: {schema.extraction_method}")
            
            end_time = datetime.utcnow()
            
            # Calculate quality metrics
            confidence_score = self._calculate_confidence(extracted_data, schema)
            completeness_score = self._calculate_completeness(extracted_data, schema)
            validation_score = self._validate_extraction(extracted_data, schema)
            
            # Update extraction record
            extraction.extracted_data = extracted_data
            extraction.extraction_metadata = {
                "extraction_time_ms": int((end_time - start_time).total_seconds() * 1000),
                "content_length": len(text_content),
                "schema_version": schema.version,
                "extraction_timestamp": end_time.isoformat()
            }
            extraction.confidence_score = confidence_score
            extraction.completeness_score = completeness_score
            extraction.validation_score = validation_score
            extraction.extraction_time_ms = int((end_time - start_time).total_seconds() * 1000)
            extraction.status = ExtractionStatus.COMPLETED
            extraction.requires_review = validation_score < schema.confidence_threshold
            
            # Update schema statistics
            schema.usage_count += 1
            schema.success_rate = await self._update_schema_success_rate(db, schema)
            schema.avg_confidence = await self._update_schema_avg_confidence(db, schema)
            
            await db.commit()
            await db.refresh(extraction)
            
            return extraction
            
        except Exception as e:
            extraction.status = ExtractionStatus.FAILED
            extraction.error_message = str(e)
            await db.commit()
            raise
    
    async def _extract_with_rules(self, content: str, schema: ContentExtractionSchema) -> Dict[str, Any]:
        """Extract content using rule-based approach with CSS/XPath selectors"""
        extracted_data = {}
        
        # For now, implement basic regex-based extraction
        # In production, you'd use BeautifulSoup or lxml for CSS/XPath
        for field_name, field_config in schema.field_definitions.items():
            extracted_value = None
            
            # Try CSS selector first
            if field_name in schema.css_selectors:
                # Placeholder for CSS selector extraction
                extracted_value = self._extract_with_regex(content, field_config.get('pattern', ''))
            
            # Try XPath selector
            elif field_name in schema.xpath_selectors:
                # Placeholder for XPath extraction
                extracted_value = self._extract_with_regex(content, field_config.get('pattern', ''))
            
            # Fallback to regex patterns from extraction rules
            elif field_name in schema.extraction_rules:
                pattern = schema.extraction_rules[field_name].get('pattern', '')
                extracted_value = self._extract_with_regex(content, pattern)
            
            extracted_data[field_name] = extracted_value
        
        return extracted_data
    
    async def _extract_with_ml(self, content: str, schema: ContentExtractionSchema) -> Dict[str, Any]:
        """Extract content using ML models (NLP)"""
        # If spaCy is unavailable in the environment, gracefully skip ML extraction
        if _spacy is None:
            return {}
        await self._load_nlp_model()
        
        def extract_with_nlp():
            doc = self.nlp(content)
            extracted_data = {}
            
            # Extract based on schema type
            if schema.schema_type == SchemaType.ARTICLE:
                extracted_data = {
                    "title": self._extract_title(content),
                    "author": self._extract_author(doc),
                    "publish_date": self._extract_date(content),
                    "content": content,
                    "summary": self._extract_summary(doc),
                    "keywords": [ent.text for ent in doc.ents if ent.label_ in ["PERSON", "ORG", "GPE"]],
                    "word_count": len(doc),
                    "reading_time": max(1, len(doc) // 200)  # Assuming 200 words per minute
                }
            elif schema.schema_type == SchemaType.PERSON:
                extracted_data = {
                    "name": self._extract_person_name(doc),
                    "title": self._extract_person_title(content),
                    "organization": self._extract_organization(doc),
                    "location": self._extract_location(doc),
                    "email": self._extract_email(content),
                    "phone": self._extract_phone(content)
                }
            elif schema.schema_type == SchemaType.ORGANIZATION:
                extracted_data = {
                    "name": self._extract_org_name(doc),
                    "industry": self._extract_industry(content),
                    "location": self._extract_location(doc),
                    "website": self._extract_website(content),
                    "description": self._extract_description(content)
                }
            else:
                # Generic extraction for custom schemas
                for field_name, field_config in schema.field_definitions.items():
                    extracted_data[field_name] = self._extract_generic_field(doc, field_config)
            
            return extracted_data
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, extract_with_nlp)
    
    async def _extract_with_llm(self, content: str, schema: ContentExtractionSchema) -> Dict[str, Any]:
        """Extract content using LLM (placeholder - would integrate with OpenAI/Anthropic)"""
        # This is a placeholder implementation
        # In production, you'd integrate with OpenAI, Anthropic, or other LLM providers
        
        if not schema.llm_prompt_template:
            raise ValueError("LLM prompt template not configured for schema")
        
        # Simulate LLM extraction with basic patterns
        extracted_data = {}
        
        for field_name, field_config in schema.field_definitions.items():
            # Basic extraction logic (in production, this would be LLM calls)
            if field_config.get('type') == 'string':
                extracted_data[field_name] = self._extract_with_regex(
                    content, 
                    field_config.get('pattern', f'{field_name}:?\s*([^\n]+)')
                )
            elif field_config.get('type') == 'number':
                pattern = r'\d+(?:\.\d+)?'
                matches = re.findall(pattern, content)
                extracted_data[field_name] = float(matches[0]) if matches else None
            elif field_config.get('type') == 'date':
                extracted_data[field_name] = self._extract_date(content)
            else:
                extracted_data[field_name] = None
        
        return extracted_data
    
    async def _extract_hybrid(self, content: str, schema: ContentExtractionSchema) -> Dict[str, Any]:
        """Extract content using hybrid approach (rules + ML + LLM)"""
        # Start with rule-based extraction
        rule_data = await self._extract_with_rules(content, schema)
        
        # Enhance with ML extraction
        ml_data = await self._extract_with_ml(content, schema)
        
        # Combine results with ML data taking precedence for missing fields
        extracted_data = rule_data.copy()
        for key, value in ml_data.items():
            if not extracted_data.get(key) and value:
                extracted_data[key] = value
        
        # For high-confidence fields, use LLM for validation/enhancement
        if schema.llm_prompt_template:
            try:
                llm_data = await self._extract_with_llm(content, schema)
                # Use LLM data for critical fields or when confidence is low
                for key, value in llm_data.items():
                    if value and (not extracted_data.get(key) or 
                                key in schema.validation_rules.get('critical_fields', [])):
                        extracted_data[key] = value
            except Exception:
                pass  # Fallback to rule + ML data if LLM fails
        
        return extracted_data
    
    # Helper methods for extraction
    def _extract_with_regex(self, content: str, pattern: str) -> Optional[str]:
        """Extract content using regex pattern"""
        if not pattern:
            return None
        
        try:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            return match.group(1).strip() if match and match.groups() else None
        except Exception:
            return None
    
    def _extract_title(self, content: str) -> Optional[str]:
        """Extract title from content"""
        patterns = [
            r'<title[^>]*>([^<]+)</title>',
            r'<h1[^>]*>([^<]+)</h1>',
            r'^([^\n]+)',  # First line
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                if len(title) > 10:  # Reasonable title length
                    return title
        
        return None
    
    def _extract_author(self, doc) -> Optional[str]:
        """Extract author using NLP"""
        # Look for person entities near "by", "author", etc.
        author_keywords = ["by", "author", "written by", "created by"]
        
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                # Check if person entity is near author keywords
                start_context = max(0, ent.start - 10)
                end_context = min(len(doc), ent.end + 10)
                context = doc[start_context:end_context].text.lower()
                
                if any(keyword in context for keyword in author_keywords):
                    return ent.text
        
        return None
    
    def _extract_date(self, content: str) -> Optional[str]:
        """Extract date from content"""
        date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',
            r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})\b',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_summary(self, doc) -> Optional[str]:
        """Extract summary from document"""
        sentences = list(doc.sents)
        if len(sentences) > 0:
            # Return first few sentences as summary
            summary_sentences = sentences[:3]
            return " ".join([sent.text.strip() for sent in summary_sentences])
        return None
    
    def _extract_person_name(self, doc) -> Optional[str]:
        """Extract person name from document"""
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                return ent.text
        return None
    
    def _extract_person_title(self, content: str) -> Optional[str]:
        """Extract person title/position"""
        title_patterns = [
            r'(?:title|position|role):\s*([^\n]+)',
            r'((?:CEO|CTO|CFO|Director|Manager|President|VP|Vice President)[^\n]*)',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_organization(self, doc) -> Optional[str]:
        """Extract organization from document"""
        for ent in doc.ents:
            if ent.label_ == "ORG":
                return ent.text
        return None
    
    def _extract_location(self, doc) -> Optional[str]:
        """Extract location from document"""
        for ent in doc.ents:
            if ent.label_ in ["GPE", "LOC"]:
                return ent.text
        return None
    
    def _extract_email(self, content: str) -> Optional[str]:
        """Extract email address"""
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, content)
        return match.group(0) if match else None
    
    def _extract_phone(self, content: str) -> Optional[str]:
        """Extract phone number"""
        patterns = [
            r'\b\d{3}-\d{3}-\d{4}\b',
            r'\(\d{3}\)\s*\d{3}-\d{4}',
            r'\b\d{10}\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(0)
        
        return None
    
    def _extract_org_name(self, doc) -> Optional[str]:
        """Extract organization name"""
        return self._extract_organization(doc)
    
    def _extract_industry(self, content: str) -> Optional[str]:
        """Extract industry information"""
        industry_keywords = [
            "technology", "healthcare", "finance", "education", "retail",
            "manufacturing", "consulting", "software", "biotechnology"
        ]
        
        content_lower = content.lower()
        for keyword in industry_keywords:
            if keyword in content_lower:
                return keyword.title()
        
        return None
    
    def _extract_website(self, content: str) -> Optional[str]:
        """Extract website URL"""
        pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*)?(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?'
        match = re.search(pattern, content)
        return match.group(0) if match else None
    
    def _extract_description(self, content: str) -> Optional[str]:
        """Extract description"""
        # Look for description patterns
        desc_patterns = [
            r'(?:description|about|overview):\s*([^\n]+)',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        ]
        
        for pattern in desc_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_generic_field(self, doc, field_config: Dict[str, Any]) -> Any:
        """Generic field extraction based on configuration"""
        field_type = field_config.get('type', 'string')
        pattern = field_config.get('pattern', '')
        
        if field_type == 'entity':
            entity_type = field_config.get('entity_type', 'PERSON')
            for ent in doc.ents:
                if ent.label_ == entity_type:
                    return ent.text
        elif field_type == 'regex' and pattern:
            return self._extract_with_regex(doc.text, pattern)
        
        return None
    
    # Quality calculation methods
    def _calculate_confidence(self, extracted_data: Dict[str, Any], schema: ContentExtractionSchema) -> float:
        """Calculate confidence score for extraction"""
        total_fields = len(schema.field_definitions)
        if total_fields == 0:
            return 0.0
        
        filled_fields = sum(1 for value in extracted_data.values() if value is not None)
        return filled_fields / total_fields
    
    def _calculate_completeness(self, extracted_data: Dict[str, Any], schema: ContentExtractionSchema) -> float:
        """Calculate completeness score for extraction"""
        required_fields = [
            field for field, config in schema.field_definitions.items()
            if config.get('required', False)
        ]
        
        if not required_fields:
            return 1.0
        
        filled_required = sum(
            1 for field in required_fields
            if extracted_data.get(field) is not None
        )
        return filled_required / len(required_fields)
    
    def _validate_extraction(self, extracted_data: Dict[str, Any], schema: ContentExtractionSchema) -> float:
        """Validate extraction against schema rules"""
        if not schema.validation_rules:
            return 1.0
        
        total_rules = 0
        passed_rules = 0
        
        for field, value in extracted_data.items():
            field_rules = schema.validation_rules.get(field, {})
            
            for rule_name, rule_config in field_rules.items():
                total_rules += 1
                
                if rule_name == 'min_length' and value:
                    if len(str(value)) >= rule_config:
                        passed_rules += 1
                elif rule_name == 'max_length' and value:
                    if len(str(value)) <= rule_config:
                        passed_rules += 1
                elif rule_name == 'pattern' and value:
                    if re.match(rule_config, str(value)):
                        passed_rules += 1
                elif rule_name == 'required':
                    if value is not None:
                        passed_rules += 1
        
        return passed_rules / total_rules if total_rules > 0 else 1.0
    
    async def _update_schema_success_rate(self, db: AsyncSession, schema: ContentExtractionSchema) -> float:
        """Update schema success rate based on completed extractions"""
        result = await db.execute(
            select(func.count(), func.sum(
                func.case((ContentExtraction.status == ExtractionStatus.COMPLETED, 1), else_=0)
            )).where(ContentExtraction.schema_id == schema.id)
        )
        
        total, successful = result.first()
        return (successful / total) if total > 0 else 0.0
    
    async def _update_schema_avg_confidence(self, db: AsyncSession, schema: ContentExtractionSchema) -> float:
        """Update schema average confidence score"""
        result = await db.execute(
            select(func.avg(ContentExtraction.confidence_score)).where(
                and_(
                    ContentExtraction.schema_id == schema.id,
                    ContentExtraction.status == ExtractionStatus.COMPLETED
                )
            )
        )
        
        avg_confidence = result.scalar()
        return float(avg_confidence) if avg_confidence is not None else 0.0
    
    # Template Management
    async def create_template_from_schema(
        self,
        db: AsyncSession,
        user: User,
        schema: ContentExtractionSchema,
        name: str,
        description: str,
        category: str,
        use_cases: List[str] = None,
        supported_domains: List[str] = None,
        tags: List[str] = None
    ) -> ExtractionTemplate:
        """Create a reusable template from an extraction schema"""
        
        template = ExtractionTemplate(
            created_by_user_id=user.id,
            schema_id=schema.id,
            name=name,
            description=description,
            category=category,
            template_config=schema.field_definitions,
            example_data={},  # Could be populated with sample extraction
            use_cases=use_cases or [],
            supported_domains=supported_domains or [],
            tags=tags or [],
            is_public=schema.is_public
        )
        
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template
    
    async def get_templates(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_featured: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[ExtractionTemplate]:
        """Get available extraction templates"""
        
        query = select(ExtractionTemplate).where(
            ExtractionTemplate.is_public is True
        )
        
        if category:
            query = query.where(ExtractionTemplate.category == category)
        
        if tags:
            # Check if any of the provided tags match template tags
            for tag in tags:
                query = query.where(ExtractionTemplate.tags.contains([tag]))
        
        if is_featured:
            query = query.where(ExtractionTemplate.is_featured is True)
        
        query = query.order_by(ExtractionTemplate.download_count.desc())
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()


# Create service instance
extraction_service = ExtractionService()