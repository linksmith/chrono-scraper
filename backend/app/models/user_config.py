"""
User configuration models for entity extraction and other preferences
"""
from typing import Dict, Any, Optional, List
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime


class UserEntityConfig(SQLModel, table=True):
    """User configuration for entity extraction preferences"""
    __tablename__ = "user_entity_config"
    
    # Primary key
    user_id: int = Field(foreign_key="users.id", primary_key=True)
    
    # Entity extraction preferences
    enabled: bool = Field(default=False, description="Enable entity extraction for this user")
    backend: str = Field(default="enhanced_spacy", description="Preferred extraction backend")
    language: str = Field(default="en", description="Primary language for extraction")
    
    # Backend-specific configuration
    backend_config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    # Wikidata enrichment
    enable_wikidata: bool = Field(default=True, description="Enable Wikidata enrichment")
    wikidata_language: str = Field(default="en", description="Language for Wikidata content")
    
    # Quality and filtering
    confidence_threshold: float = Field(default=0.7, description="Minimum confidence for entities")
    enable_entity_types: List[str] = Field(default_factory=lambda: ["person", "organization", "location", "event"], sa_column=Column(JSON))
    
    # Performance settings
    max_entities_per_page: int = Field(default=100, description="Maximum entities to extract per page")
    enable_context_extraction: bool = Field(default=True, description="Extract context around entities")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserEntityBackendOption(SQLModel):
    """Pydantic model for entity backend options shown to user"""
    
    # Backend identification
    backend: str = Field(description="Backend identifier")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="Backend description")
    
    # Capabilities
    supported_languages: List[str] = Field(description="Supported language codes")
    entity_types: List[str] = Field(description="Supported entity types")
    
    # Performance characteristics
    speed: str = Field(description="Speed rating: fast, medium, slow")
    accuracy: str = Field(description="Accuracy rating: standard, high, research")
    cost: str = Field(description="Cost: free, low, medium, high")
    
    # Requirements and limitations
    requires_api_key: bool = Field(default=False, description="Requires API key")
    requires_internet: bool = Field(default=False, description="Requires internet connection")
    max_text_length: Optional[int] = Field(default=None, description="Maximum text length per request")
    
    # Pros and cons for UI display
    pros: List[str] = Field(description="Advantages of this backend")
    cons: List[str] = Field(description="Limitations of this backend")
    
    # Configuration
    config_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON schema for configuration")
    available: bool = Field(description="Whether backend is currently available")


def get_backend_options() -> List[UserEntityBackendOption]:
    """Get all available backend options with pros/cons for UI display"""
    
    return [
        UserEntityBackendOption(
            backend="enhanced_spacy",
            name="Enhanced spaCy (Recommended)",
            description="Advanced multilingual entity recognition with Dutch and English support",
            supported_languages=["en", "nl", "xx"],
            entity_types=["person", "organization", "location", "event", "product", "date", "money", "email", "url"],
            speed="fast",
            accuracy="high",
            cost="free",
            requires_api_key=False,
            requires_internet=False,
            max_text_length=1000000,  # 1MB text
            pros=[
                "✅ Free to use - no API costs",
                "✅ Excellent Dutch and English support",
                "✅ Fast processing speed (~120ms per page)",
                "✅ Works offline - no internet required",
                "✅ High accuracy for standard entities",
                "✅ Built-in context extraction",
                "✅ Privacy-friendly - all processing local"
            ],
            cons=[
                "❌ Limited to Dutch and English languages",
                "❌ Requires spaCy model downloads (~500MB)",
                "❌ Weaker on very specialized entity types",
                "❌ No built-in entity linking to knowledge bases"
            ],
            available=True
        ),
        
        UserEntityBackendOption(
            backend="firecrawl_extraction",
            name="Firecrawl AI Extraction",
            description="LLM-powered structured entity extraction with rich context understanding",
            supported_languages=["en", "nl", "de", "fr", "es", "it", "pt", "pl", "ru", "zh", "ja"],
            entity_types=["person", "organization", "location", "event", "product", "concept"],
            speed="medium",
            accuracy="research",
            cost="low",
            requires_api_key=False,  # Uses local Firecrawl instance
            requires_internet=True,   # Needs connection to local Firecrawl
            max_text_length=100000,   # 100KB per request
            pros=[
                "✅ Highest accuracy entity extraction",
                "✅ Excellent multilingual support (11+ languages)",
                "✅ Rich context understanding and relationships",
                "✅ Handles complex entity types and nested structures",
                "✅ Uses local Firecrawl instance - no external API costs",
                "✅ Custom schema support for domain-specific entities",
                "✅ Built-in entity relationship detection"
            ],
            cons=[
                "❌ Slower processing (~500ms per page)",
                "❌ Requires Firecrawl service to be running",
                "❌ Higher memory usage for complex extractions",
                "❌ May over-extract in some cases",
                "❌ Dependent on Firecrawl service availability"
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "firecrawl_url": {
                        "type": "string",
                        "default": "http://localhost:3002",
                        "description": "Firecrawl service URL"
                    },
                    "extraction_timeout": {
                        "type": "integer",
                        "default": 30,
                        "description": "Timeout in seconds for extraction"
                    }
                }
            },
            available=True
        )
    ]


def get_entity_extraction_recommendations(
    use_case: str = "general",
    languages: List[str] = ["en"],
    accuracy_priority: str = "balanced",
    cost_concern: str = "medium"
) -> List[str]:
    """
    Get backend recommendations based on user requirements
    
    Args:
        use_case: "research", "production", "general", "osint"
        languages: List of required language codes
        accuracy_priority: "speed", "balanced", "accuracy"
        cost_concern: "low", "medium", "high"
        
    Returns:
        List of recommended backend names in order of preference
    """
    
    # Research and OSINT investigations - prioritize accuracy
    if use_case in ["research", "osint"]:
        if "nl" in languages:
            return ["enhanced_spacy", "firecrawl_extraction"]
        else:
            return ["firecrawl_extraction", "enhanced_spacy"]
    
    # Production usage - prioritize speed and reliability
    elif use_case == "production":
        if accuracy_priority == "speed":
            return ["enhanced_spacy", "firecrawl_extraction"]
        else:
            return ["enhanced_spacy", "firecrawl_extraction"]
    
    # General usage - balanced approach
    else:
        # If user needs Dutch support, spaCy is excellent
        if "nl" in languages:
            return ["enhanced_spacy", "firecrawl_extraction"]
        
        # For other languages or high accuracy needs
        if accuracy_priority == "accuracy":
            return ["firecrawl_extraction", "enhanced_spacy"]
        else:
            return ["enhanced_spacy", "firecrawl_extraction"]