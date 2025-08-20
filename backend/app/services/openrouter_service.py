"""
OpenRouter LLM service for generating project names and descriptions
"""
import logging
from typing import Dict, Any, Optional, List
import httpx
from dataclasses import dataclass
from urllib.parse import urlparse

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
        
        system_prompt = """You generate short, professional project names and concise descriptions for scraping projects.

Naming rules (critical):
- The title must be short (1-4 words), and MUST NOT include words like "Project", "Analysis", "Scraping", "Study", "Overview", or similar.
- Prefer recognizable organization names derived from the domains. One domain: just the organization/hostname. Two domains: "OrgA + OrgB". More than two: "OrgA + OrgB + N more".
- If clear organization names cannot be inferred, fall back to the domain name(s) (e.g., "example.com").
- If a domain includes a path, incorporate the key path term into the title (e.g., "Org Careers", "Org Research").
- Avoid punctuation-heavy titles; no colons or parentheses.

Description rules:
- 1-2 sentences max.
- Describe the type of web content likely to be captured and why it is useful. Avoid boilerplate like "This project will".

Respond ONLY in strict JSON with keys name, description, reasoning.
Format:
{
  "name": "Short Title",
  "description": "One or two sentences max.",
  "reasoning": "Brief rationale"
}
"""

        user_prompt = f"""Analyze these domains and create a SHORT title and a concise description following the rules.

Domains:
{domains_text}

Return strict JSON only."""

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
                    cleaned_name = self._clean_generated_name(result.get("name", ""), domains)
                    cleaned_description = self._clean_generated_description(result.get("description", ""))
                    return ProjectNameDescription(
                        name=cleaned_name or self._summarize_domains_for_title(domains),
                        description=cleaned_description or "Content from specified domains",
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
        """Generate fallback name and description when LLM fails (short, org-focused)."""
        title = self._summarize_domains_for_title(domains)
        # Description: short, neutral (include key path term when present)
        display_items = []
        for d in [v for v in domains if v]:
            host = self._normalize_hostname(d)
            seg = self._extract_primary_segment(d)
            if seg:
                display_items.append(f"{host}/{seg}")
            else:
                display_items.append(host)
        display = ", ".join(display_items[:3]) + (f" + {len(display_items) - 3} more" if len(display_items) > 3 else "")
        description = f"Content from {display}."

        return ProjectNameDescription(
            name=title,
            description=description,
            reasoning="Generated using fallback logic due to LLM service unavailability"
        )

    # -------- Helper methods for naming --------
    def _normalize_hostname(self, value: str) -> str:
        if not value:
            return ""
        text = value.strip()
        # Prepend scheme for robust parsing
        if "://" not in text:
            text_to_parse = f"http://{text}"
        else:
            text_to_parse = text
        try:
            parsed = urlparse(text_to_parse)
            host = parsed.netloc or parsed.path
        except Exception:
            host = text
        # Strip credentials and port
        host = host.split("@")[ -1 ].split(":")[0].lower()
        if host.startswith("www."):
            host = host[4:]
        # If someone passed a path-only string, fall back
        host = host.strip("/")
        return host

    # Removed TLD-specific fallback in favor of domain name fallback

    def _extract_primary_segment(self, value: str) -> Optional[str]:
        if not value:
            return None
        text = value.strip()
        text_to_parse = f"http://{text}" if "://" not in text else text
        try:
            parsed = urlparse(text_to_parse)
            path = parsed.path or ""
        except Exception:
            return None
        segments = [s for s in path.split('/') if s]
        if not segments:
            return None
        # Ignore locale-only segments
        locale_codes = {
            "en","nl","fr","de","es","it","pt","ru","zh","ja","ko","pl","cs","sv","no","da","fi","tr","ar","he","el","ro","hu","sk","sl","bg","uk","hi","bn","id","ms","th","vi"
        }
        for seg in segments:
            low = seg.lower()
            if low in locale_codes:
                continue
            cleaned = self._format_segment_to_title(seg)
            if cleaned:
                return cleaned
        return None

    def _format_segment_to_title(self, segment: str) -> str:
        slug = segment.replace('-', ' ').replace('_', ' ').strip()
        words = [w for w in slug.split() if w]
        if not words:
            return ""
        # Limit to first 3 words to keep it short
        words = words[:3]
        return " ".join(w.capitalize() for w in words)

    def _extract_org_name_from_domain(self, hostname: str) -> Optional[str]:
        if not hostname:
            return None
        parts = [p for p in hostname.split(".") if p]
        if not parts:
            return None
        # Handle some common 2nd-level TLD compounds
        second_level_suffixes = {
            "co.uk", "org.uk", "ac.uk", "gov.uk",
            "com.au", "net.au", "org.au",
            "co.nz", "org.nz",
            "com.br", "com.ar", "com.mx", "com.tr",
            "co.in", "co.jp", "com.cn"
        }
        sld_index = -2 if len(parts) >= 2 else -1
        if len(parts) >= 3:
            candidate = f"{parts[-2]}.{parts[-1]}"
            if candidate in second_level_suffixes:
                sld_index = -3
        label = parts[sld_index] if parts else hostname
        label = label.replace("-", " ").replace("_", " ").strip()
        if not label:
            return None
        # Title-case but keep short words reasonable
        return " ".join([w.capitalize() for w in label.split() if w])

    def _summarize_domains_for_title(self, domains: List[str]) -> str:
        # Build entries with host, org and optional primary segment
        raw_entries = [d for d in domains if d]
        entries = []
        for d in raw_entries:
            host = self._normalize_hostname(d)
            org = self._extract_org_name_from_domain(host) if host else None
            seg = self._extract_primary_segment(d)
            entries.append({"host": host, "org": org, "seg": seg})

        hostnames = [e["host"] for e in entries if e["host"]]
        org_names = [e["org"] for e in entries if e["org"]]
        # Deduplicate while preserving order
        seen = set()
        unique_orgs = []
        for o in org_names:
            if o.lower() not in seen:
                unique_orgs.append(o)
                seen.add(o.lower())
        if len(entries) == 1:
            e = entries[0]
            if e["org"] and e["seg"]:
                return f"{e['org']} {e['seg']}"
            if e["org"]:
                return e["org"]
            if e["host"] and e["seg"]:
                return f"{e['host']} {e['seg']}"
            return e["host"] or "Websites"
        if len(unique_orgs) == 1:
            # Multiple URLs but same org; if any segment present, include the first
            first_seg = next((e["seg"] for e in entries if e["seg"]), None)
            if first_seg:
                return f"{unique_orgs[0]} {first_seg} + {len(entries) - 1} more"
            return f"{unique_orgs[0]} + {len(entries) - 1} more"
        if len(unique_orgs) == 2:
            return f"{unique_orgs[0]} + {unique_orgs[1]}"
        if len(unique_orgs) >= 3:
            return f"{unique_orgs[0]} + {unique_orgs[1]} + {len(unique_orgs) - 2} more"
        # Fallback to normalized domain names
        if hostnames:
            if len(hostnames) == 1:
                # If we got here, no org; try include segment
                seg = entries[0]["seg"] if entries else None
                return f"{hostnames[0]} {seg}".strip() if seg else hostnames[0]
            if len(hostnames) == 2:
                return f"{hostnames[0]} + {hostnames[1]}"
            return f"{hostnames[0]} + {hostnames[1]} + {len(hostnames) - 2} more"
        return "Websites"

    def _clean_generated_name(self, name: str, domains: List[str]) -> str:
        if not isinstance(name, str):
            return self._summarize_domains_for_title(domains)
        raw = name.strip().strip('"\'')
        # Remove banned terms
        banned = [
            "project", "analysis", "scraping", "scraper", "study",
            "overview", "report", "dataset", "collection"
        ]
        words = [w for w in raw.replace(":", " ").replace("(", " ").replace(")", " ").replace("-", " ").split()]
        filtered = " ".join([w for w in words if w.lower() not in banned])
        filtered = filtered.strip()
        # Enforce brevity
        if len(filtered) > 60:
            filtered = filtered[:57].rstrip() + "..."
        # If empty or still contains banned tokens, summarize
        lower_filtered = filtered.lower()
        if not filtered or any(b in lower_filtered for b in banned):
            return self._summarize_domains_for_title(domains)
        return filtered

    def _clean_generated_description(self, description: str) -> str:
        if not isinstance(description, str):
            return ""
        desc = description.strip()
        # Keep it brief: 2 sentences max by naive split
        parts = [p.strip() for p in desc.split('.') if p.strip()]
        if not parts:
            return ""
        short = ". ".join(parts[:2])
        if not short.endswith('.'):
            short += '.'
        return short
    
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