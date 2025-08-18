"""
API endpoints for user entity extraction configuration
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.models.user_config import UserEntityConfig, get_backend_options, get_entity_extraction_recommendations
from app.services.entity_extraction import EntityExtractionService

router = APIRouter()


@router.get("/entity-config")
async def get_user_entity_config(
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserEntityConfig:
    """Get current user's entity extraction configuration"""
    
    # Try to get existing config
    result = await session.execute(
        select(UserEntityConfig).where(UserEntityConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        # Create default configuration
        config = UserEntityConfig(
            user_id=current_user.id,
            enabled=False,
            backend="enhanced_spacy",
            language="en",
            enable_wikidata=True,
            confidence_threshold=0.7,
            enable_entity_types=["person", "organization", "location", "event"],
            max_entities_per_page=100,
            enable_context_extraction=True
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)
    
    return config


@router.put("/entity-config")
async def update_user_entity_config(
    config_data: Dict[str, Any],
    current_user: User = Depends(deps.get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserEntityConfig:
    """Update user's entity extraction configuration"""
    
    # Get existing config or create new one
    result = await session.execute(
        select(UserEntityConfig).where(UserEntityConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    if not config:
        config = UserEntityConfig(user_id=current_user.id)
        session.add(config)
    
    # Update configuration fields
    for field, value in config_data.items():
        if hasattr(config, field):
            setattr(config, field, value)
    
    # Validate backend exists
    if config.backend not in ['enhanced_spacy', 'firecrawl_extraction']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid backend: {config.backend}"
        )
    
    # Validate language
    if config.language not in ['en', 'nl', 'de', 'fr', 'es', 'it', 'pt', 'pl', 'ru', 'zh', 'ja']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language: {config.language}"
        )
    
    # Validate confidence threshold
    if not 0.1 <= config.confidence_threshold <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confidence threshold must be between 0.1 and 1.0"
        )
    
    await session.commit()
    await session.refresh(config)
    
    return config


@router.get("/entity-backends")
async def get_available_entity_backends(
    current_user: User = Depends(deps.get_current_user),
) -> List[Dict[str, Any]]:
    """Get list of available entity extraction backends with their capabilities"""
    
    # Get backend options with pros/cons
    backend_options = get_backend_options()
    
    # Check actual availability of backends
    extraction_service = EntityExtractionService()
    available_backends = await extraction_service.get_available_backends()
    
    # Merge backend information
    result = []
    for option in backend_options:
        backend_info = next(
            (b for b in available_backends if b['backend'] == option.backend),
            {'available': False}
        )
        
        result.append({
            **option.dict(),
            'available': backend_info.get('available', False),
            'status': backend_info
        })
    
    return result


@router.get("/entity-backends/{backend_name}")
async def get_entity_backend_info(
    backend_name: str,
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, Any]:
    """Get detailed information about a specific entity backend"""
    
    extraction_service = EntityExtractionService()
    backend_info = await extraction_service.get_backend_info(backend_name)
    
    return backend_info


@router.post("/entity-backends/{backend_name}/test")
async def test_entity_backend(
    backend_name: str,
    test_data: Dict[str, Any],
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, Any]:
    """Test entity extraction with a specific backend"""
    
    test_text = test_data.get('text', '')
    language = test_data.get('language', 'en')
    backend_config = test_data.get('config', {})
    
    if not test_text or len(test_text.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test text is required"
        )
    
    if len(test_text) > 10000:  # Limit test text size
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test text too long (max 10,000 characters)"
        )
    
    try:
        extraction_service = EntityExtractionService()
        
        # Extract entities using specified backend
        entities = await extraction_service.extract_entities_from_text(
            text=test_text,
            extraction_method="backend",
            backend=backend_name,
            backend_config=backend_config,
            language=language
        )
        
        # Optionally enrich with Wikidata if requested
        if test_data.get('enable_wikidata', False):
            entities = await extraction_service.enrich_entities_with_wikidata(entities, language)
        
        return {
            'backend': backend_name,
            'language': language,
            'entities': entities,
            'entity_count': len(entities),
            'extraction_time': test_data.get('extraction_time', 0),
            'test_successful': True
        }
        
    except Exception as e:
        return {
            'backend': backend_name,
            'language': language,
            'entities': [],
            'entity_count': 0,
            'error': str(e),
            'test_successful': False
        }


@router.post("/entity-recommendations")
async def get_entity_extraction_recommendations_endpoint(
    requirements: Dict[str, Any],
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, Any]:
    """Get personalized entity extraction backend recommendations"""
    
    use_case = requirements.get('use_case', 'general')
    languages = requirements.get('languages', ['en'])
    accuracy_priority = requirements.get('accuracy_priority', 'balanced')
    cost_concern = requirements.get('cost_concern', 'medium')
    
    recommendations = get_entity_extraction_recommendations(
        use_case=use_case,
        languages=languages,
        accuracy_priority=accuracy_priority,
        cost_concern=cost_concern
    )
    
    # Get detailed info for each recommended backend
    extraction_service = EntityExtractionService()
    backend_details = []
    
    for backend_name in recommendations:
        backend_info = await extraction_service.get_backend_info(backend_name)
        backend_details.append(backend_info)
    
    return {
        'recommendations': recommendations,
        'reasoning': {
            'use_case': use_case,
            'languages': languages,
            'accuracy_priority': accuracy_priority,
            'cost_concern': cost_concern
        },
        'backend_details': backend_details
    }