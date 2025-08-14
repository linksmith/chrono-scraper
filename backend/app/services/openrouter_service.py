"""
OpenRouter LLM service for generating project names and descriptions
"""
import logging
from typing import Dict, Any, Optional, List
import httpx
from dataclasses import dataclass

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProjectNameDescription:
    """Container for generated project name and description"""
    name: str
    description: str
    reasoning: Optional[str] = None


class OpenRouterService:
    """Service for generating project names and descriptions using OpenRouter"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
        self.base_url = getattr(settings, 'OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
        self.default_model = getattr(settings, 'OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
        
        if not self.api_key:
            logger.warning("OpenRouter API key not found in settings")
    
    async def generate_project_name_description(
        self,
        domains: List[str],
        model: Optional[str] = None
    ) -> ProjectNameDescription:
        """
        Generate project name and description based on domain list
        
        Args:
            domains: List of domain names
            model: OpenRouter model to use (defaults to claude-3.5-sonnet)
            
        Returns:
            ProjectNameDescription with generated name and description
        """
        if not domains:
            raise ValueError("At least one domain is required")
        
        # If no API key is configured, use fallback immediately
        if not self.api_key:
            logger.info("OpenRouter API key not configured, using fallback name generation")
            return self._generate_fallback_name_description(domains)
        
        model_to_use = model or self.default_model
        
        # Create prompt for project generation
        domains_text = "\n".join([f"- {domain}" for domain in domains])
        
        system_prompt = """You are an expert at analyzing websites and creating descriptive project names and descriptions for web scraping projects. 

Your task is to analyze the provided domain names and generate:
1. A concise, descriptive project name (3-8 words)
2. A detailed description explaining what this project will analyze

Focus on:
- The industry/sector of the domains
- The type of content likely to be found
- The research purpose or value
- Use professional, research-oriented language

Respond in JSON format:
{
    "name": "Project Name Here",
    "description": "Detailed description here",
    "reasoning": "Brief explanation of your choices"
}"""

        user_prompt = f"""Analyze these domains and create a project name and description:

{domains_text}

Generate a professional project name and description that captures what kind of research or analysis this scraping project would be used for."""

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model_to_use,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.7
                    }
                )
                
                if response.status_code != 200:
                    error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Try to parse JSON response
                try:
                    import json
                    result = json.loads(content)
                    
                    return ProjectNameDescription(
                        name=result.get("name", "Web Scraping Project"),
                        description=result.get("description", "Analysis of web content from specified domains"),
                        reasoning=result.get("reasoning")
                    )
                except json.JSONDecodeError:
                    # Fallback if JSON parsing fails
                    logger.warning("Could not parse JSON response from OpenRouter, using fallback")
                    return self._generate_fallback_name_description(domains)
                
        except httpx.TimeoutException:
            logger.error("OpenRouter API timeout")
            return self._generate_fallback_name_description(domains)
        except Exception as e:
            logger.error(f"Error generating project name/description: {str(e)}")
            return self._generate_fallback_name_description(domains)
    
    def _generate_fallback_name_description(self, domains: List[str]) -> ProjectNameDescription:
        """Generate fallback name and description when LLM fails"""
        if len(domains) == 1:
            domain = domains[0]
            # Extract main domain without subdomains
            main_domain = domain.split('.')[-2] if '.' in domain else domain
            name = f"{main_domain.title()} Analysis Project"
            description = f"Web scraping and analysis project for {domain} content"
        else:
            name = f"Multi-Domain Analysis Project ({len(domains)} sites)"
            domain_list = ", ".join(domains[:3])
            if len(domains) > 3:
                domain_list += f" and {len(domains) - 3} others"
            description = f"Comprehensive web scraping project analyzing content from {domain_list}"
        
        return ProjectNameDescription(
            name=name,
            description=description,
            reasoning="Generated using fallback logic due to LLM service unavailability"
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if OpenRouter service is accessible"""
        if not self.api_key:
            return {
                "status": "error",
                "message": "API key not configured"
            }
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "api_key_configured": True
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"API returned {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }


# Global instance
openrouter_service = OpenRouterService()


async def generate_project_name_description(
    domains: List[str],
    model: Optional[str] = None
) -> ProjectNameDescription:
    """
    Convenience function for generating project name and description
    
    Args:
        domains: List of domain names
        model: OpenRouter model to use
        
    Returns:
        ProjectNameDescription with generated content
    """
    return await openrouter_service.generate_project_name_description(domains, model)