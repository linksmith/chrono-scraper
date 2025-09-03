"""
Enhanced LLM-based user evaluation service for signup approval
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import httpx
from dataclasses import dataclass

from ..core.config import settings
from ..models.user import User
from ..models.user_approval import (
    ApprovalToken, 
    ApprovalTokenAction
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Container for user evaluation results"""
    overall_score: float  # 0.0 to 10.0
    legitimacy_score: float  # 0.0 to 10.0
    research_intent_score: float  # 0.0 to 10.0
    risk_score: float  # 0.0 to 10.0 (higher = more risk)
    recommendation: str  # "approve", "deny", "manual_review"
    reasoning: str
    confidence: float  # 0.0 to 1.0
    red_flags: Optional[str] = None
    positive_indicators: Optional[str] = None
    additional_checks_needed: bool = False
    manual_review_required: bool = False


class UserEvaluationService:
    """Service for evaluating user registrations using OpenRouter LLM"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
        self.base_url = getattr(settings, 'OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
        self.default_model = getattr(settings, 'OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')
        
        if not self.api_key:
            logger.warning("OpenRouter API key not configured for user evaluation")
    
    async def evaluate_user(
        self,
        user: User,
        model: Optional[str] = None
    ) -> EvaluationResult:
        """
        Evaluate a user registration using LLM analysis
        
        Args:
            user: User object to evaluate
            model: OpenRouter model to use (defaults to Claude 3.5 Sonnet)
            
        Returns:
            EvaluationResult with detailed analysis
        """
        if not self.api_key:
            logger.warning("OpenRouter API key not configured, using fallback evaluation")
            return self._generate_fallback_evaluation(user)
        
        model_to_use = model or self.default_model
        
        # Create evaluation prompt
        system_prompt = self._get_evaluation_system_prompt()
        user_prompt = self._format_user_data_for_evaluation(user)
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
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
                        "max_tokens": 1500,
                        "temperature": 0.1
                    }
                )
                
                if response.status_code != 200:
                    error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return self._generate_fallback_evaluation(user)
                
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Parse JSON response
                try:
                    result_data = json.loads(content)
                    return self._parse_evaluation_response(result_data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse JSON response from LLM: {e}")
                    return self._generate_fallback_evaluation(user)
                    
        except httpx.TimeoutException:
            logger.error("OpenRouter API timeout during user evaluation")
            return self._generate_fallback_evaluation(user)
        except Exception as e:
            logger.error(f"Error during user evaluation: {str(e)}")
            return self._generate_fallback_evaluation(user)
    
    def _get_evaluation_system_prompt(self) -> str:
        """Generate system prompt for user evaluation"""
        return """You are an expert security analyst evaluating user registrations for a professional web scraping research platform called Chrono Scraper. This platform is used for OSINT investigations, academic research, and historical web content analysis.

EVALUATION CRITERIA:

1. LEGITIMACY SCORE (0-10):
   - Professional email domains (.edu, .org, .gov) = higher scores
   - Personal emails (gmail, yahoo) = moderate scores
   - Generic/suspicious domains = lower scores
   - Consistency between name, affiliation, and research purpose

2. RESEARCH INTENT SCORE (0-10):
   - Clear, specific research objectives
   - Academic, journalistic, or professional use cases
   - Historical analysis, OSINT, content preservation goals
   - Well-articulated research methodology

3. RISK SCORE (0-10, higher = more concerning):
   - Vague or suspicious research purposes
   - Commercial scraping intent
   - Potential policy violations
   - Lack of specific research goals

4. OVERALL SCORE (0-10):
   - Composite assessment of all factors
   - Account for user's professional background
   - Consider research ethics and platform fit

RECOMMENDATIONS:
- "approve": Scores 7+ overall, low risk, clear research intent
- "deny": Scores 4- overall, high risk, suspicious intent  
- "manual_review": Scores 5-6 overall or any red flags present

RED FLAGS:
- Extremely vague research descriptions
- Commercial scraping indicators
- Suspicious email patterns
- Inconsistent information
- Potential terms of service violations

POSITIVE INDICATORS:
- Academic/institutional affiliations
- Specific research questions
- Historical/archival research goals
- OSINT/journalism backgrounds
- Clear ethical research framework

Respond ONLY in strict JSON format:
{
  "overall_score": 8.5,
  "legitimacy_score": 9.0,
  "research_intent_score": 8.0,
  "risk_score": 2.0,
  "recommendation": "approve",
  "reasoning": "Detailed explanation of your assessment",
  "confidence": 0.85,
  "red_flags": null,
  "positive_indicators": "Academic affiliation, specific research goals",
  "additional_checks_needed": false,
  "manual_review_required": false
}"""
    
    def _format_user_data_for_evaluation(self, user: User) -> str:
        """Format user data for LLM evaluation"""
        # Extract domain from email
        email_domain = user.email.split('@')[1] if '@' in user.email else 'unknown'
        
        return f"""Evaluate this user registration for approval:

EMAIL: {user.email}
EMAIL DOMAIN: {email_domain}
FULL NAME: {user.full_name or 'Not provided'}
RESEARCH INTERESTS: {user.research_interests or 'Not provided'}
ACADEMIC AFFILIATION: {user.academic_affiliation or 'Not provided'}
PROFESSIONAL TITLE: {user.professional_title or 'Not provided'}
ORGANIZATION WEBSITE: {user.organization_website or 'Not provided'}
RESEARCH PURPOSE: {user.research_purpose or 'Not provided'}
EXPECTED USAGE: {user.expected_usage or 'Not provided'}

REGISTRATION DATE: {user.created_at.strftime('%Y-%m-%d')}
AGREEMENTS ACCEPTED: Data Handling: {user.data_handling_agreement}, Ethics: {user.ethics_agreement}

Please provide a comprehensive evaluation based on the criteria outlined in your instructions."""
    
    def _parse_evaluation_response(self, data: Dict[str, Any]) -> EvaluationResult:
        """Parse LLM response into EvaluationResult"""
        try:
            return EvaluationResult(
                overall_score=float(data.get("overall_score", 5.0)),
                legitimacy_score=float(data.get("legitimacy_score", 5.0)),
                research_intent_score=float(data.get("research_intent_score", 5.0)),
                risk_score=float(data.get("risk_score", 5.0)),
                recommendation=data.get("recommendation", "manual_review"),
                reasoning=data.get("reasoning", "No reasoning provided"),
                confidence=float(data.get("confidence", 0.5)),
                red_flags=data.get("red_flags"),
                positive_indicators=data.get("positive_indicators"),
                additional_checks_needed=data.get("additional_checks_needed", False),
                manual_review_required=data.get("manual_review_required", False)
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing evaluation response: {e}")
            return self._generate_default_evaluation()
    
    def _generate_fallback_evaluation(self, user: User) -> EvaluationResult:
        """Generate fallback evaluation when LLM is unavailable"""
        # Simple heuristic-based evaluation
        legitimacy_score = 5.0
        research_intent_score = 5.0
        risk_score = 5.0
        
        # Check email domain
        email_domain = user.email.split('@')[1].lower() if '@' in user.email else ''
        academic_domains = ['.edu', '.ac.', '.gov', '.org']
        
        if any(domain in email_domain for domain in academic_domains):
            legitimacy_score += 2.0
            risk_score -= 1.0
        
        # Check for research-related content
        research_text = f"{user.research_interests or ''} {user.research_purpose or ''}"
        research_keywords = ['research', 'academic', 'study', 'analysis', 'investigation', 'journalism', 'osint']
        
        if any(keyword in research_text.lower() for keyword in research_keywords):
            research_intent_score += 1.5
            risk_score -= 0.5
        
        # Check for required information
        if user.research_purpose and user.research_interests:
            research_intent_score += 1.0
        
        if user.academic_affiliation or user.professional_title:
            legitimacy_score += 1.0
        
        # Calculate overall score
        overall_score = (legitimacy_score + research_intent_score + (10 - risk_score)) / 3
        
        # Determine recommendation
        if overall_score >= 7.0 and risk_score <= 4.0:
            recommendation = "approve"
        elif overall_score <= 4.0 or risk_score >= 7.0:
            recommendation = "deny"
        else:
            recommendation = "manual_review"
        
        return EvaluationResult(
            overall_score=min(10.0, max(0.0, overall_score)),
            legitimacy_score=min(10.0, max(0.0, legitimacy_score)),
            research_intent_score=min(10.0, max(0.0, research_intent_score)),
            risk_score=min(10.0, max(0.0, risk_score)),
            recommendation=recommendation,
            reasoning="Fallback evaluation used due to LLM service unavailability. Basic heuristics applied.",
            confidence=0.6,
            red_flags=None,
            positive_indicators="Academic domain detected" if any(domain in email_domain for domain in academic_domains) else None,
            additional_checks_needed=True,
            manual_review_required=True
        )
    
    def _generate_default_evaluation(self) -> EvaluationResult:
        """Generate default conservative evaluation"""
        return EvaluationResult(
            overall_score=5.0,
            legitimacy_score=5.0,
            research_intent_score=5.0,
            risk_score=5.0,
            recommendation="manual_review",
            reasoning="Default evaluation due to parsing error",
            confidence=0.3,
            additional_checks_needed=True,
            manual_review_required=True
        )
    
    async def generate_approval_tokens(
        self,
        user: User,
        evaluation: EvaluationResult,
        hours_valid: int = 72
    ) -> Tuple[ApprovalToken, ApprovalToken]:
        """
        Generate secure approval and denial tokens for email actions
        
        Args:
            user: User object
            evaluation: Evaluation result
            hours_valid: Token validity period in hours
            
        Returns:
            Tuple of (approval_token, denial_token)
        """
        import secrets
        
        expires_at = datetime.utcnow() + timedelta(hours=hours_valid)
        
        # Create approval token
        approval_token = ApprovalToken(
            user_id=user.id,
            token=f"approve_{secrets.token_urlsafe(32)}",
            action=ApprovalTokenAction.APPROVE,
            expires_at=expires_at,
            admin_message=f"LLM Evaluation Score: {evaluation.overall_score:.1f}/10 - {evaluation.recommendation.upper()}"
        )
        
        # Create denial token
        denial_token = ApprovalToken(
            user_id=user.id,
            token=f"deny_{secrets.token_urlsafe(32)}",
            action=ApprovalTokenAction.DENY,
            expires_at=expires_at,
            admin_message=f"User registration denied. Score: {evaluation.overall_score:.1f}/10"
        )
        
        return approval_token, denial_token
    
    async def generate_admin_notification_data(
        self,
        user: User,
        evaluation: EvaluationResult,
        approval_token: ApprovalToken,
        denial_token: ApprovalToken
    ) -> Dict[str, Any]:
        """
        Generate data for admin notification email
        
        Args:
            user: User object
            evaluation: Evaluation result
            approval_token: Token for approval action
            denial_token: Token for denial action
            
        Returns:
            Dictionary with email template data
        """
        # Determine urgency and styling based on evaluation
        if evaluation.recommendation == "approve":
            urgency = "low"
            recommendation_color = "#16a34a"  # green
            recommendation_text = "✅ RECOMMENDED FOR APPROVAL"
        elif evaluation.recommendation == "deny":
            urgency = "high"
            recommendation_color = "#dc2626"  # red
            recommendation_text = "❌ RECOMMENDED FOR DENIAL"
        else:
            urgency = "medium"
            recommendation_color = "#f59e0b"  # yellow
            recommendation_text = "⚠️ MANUAL REVIEW REQUIRED"
        
        # Extract email domain for context
        email_domain = user.email.split('@')[1] if '@' in user.email else 'unknown'
        
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "email_domain": email_domain,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M UTC"),
            },
            "evaluation": {
                "overall_score": evaluation.overall_score,
                "legitimacy_score": evaluation.legitimacy_score,
                "research_intent_score": evaluation.research_intent_score,
                "risk_score": evaluation.risk_score,
                "recommendation": evaluation.recommendation,
                "recommendation_text": recommendation_text,
                "recommendation_color": recommendation_color,
                "reasoning": evaluation.reasoning,
                "confidence": evaluation.confidence,
                "red_flags": evaluation.red_flags,
                "positive_indicators": evaluation.positive_indicators,
            },
            "user_details": {
                "research_interests": user.research_interests,
                "academic_affiliation": user.academic_affiliation,
                "professional_title": user.professional_title,
                "organization_website": user.organization_website,
                "research_purpose": user.research_purpose,
                "expected_usage": user.expected_usage,
            },
            "actions": {
                "approval_url": f"{settings.BACKEND_URL}/api/v1/admin/approve-user/{approval_token.token}",
                "denial_url": f"{settings.BACKEND_URL}/api/v1/admin/deny-user/{denial_token.token}",
                "admin_panel_url": f"{settings.BACKEND_URL}/admin/users/{user.id}",
            },
            "urgency": urgency,
            "notification_id": f"user_signup_{user.id}_{int(datetime.utcnow().timestamp())}"
        }


# Global instance
user_evaluation_service = UserEvaluationService()


async def evaluate_user_registration(
    user: User,
    model: Optional[str] = None
) -> EvaluationResult:
    """
    Convenience function for evaluating user registrations
    
    Args:
        user: User object to evaluate
        model: OpenRouter model to use
        
    Returns:
        EvaluationResult with detailed analysis
    """
    return await user_evaluation_service.evaluate_user(user, model)


async def generate_admin_notification(
    user: User,
    evaluation: EvaluationResult
) -> Dict[str, Any]:
    """
    Convenience function for generating admin notification data
    
    Args:
        user: User object
        evaluation: Evaluation result
        
    Returns:
        Dictionary with notification data
    """
    approval_token, denial_token = await user_evaluation_service.generate_approval_tokens(
        user, evaluation
    )
    
    return await user_evaluation_service.generate_admin_notification_data(
        user, evaluation, approval_token, denial_token
    )