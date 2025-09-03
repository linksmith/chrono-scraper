"""
User approval and evaluation API endpoints
"""
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.api.deps import get_db, get_current_superuser
from ....models.user import User
from ....models.user_approval import (
    UserEvaluation,
    UserEvaluationRead,
    ApprovalToken,
    ApprovalTokenAction,
    LLMEvaluationLog,
    ApprovalStatus
)
from ....services.user_evaluation_service import (
    evaluate_user_registration
)
from ....services.auth import get_user_by_id, send_user_approval_confirmation

router = APIRouter(prefix="/admin", tags=["admin", "user-approval"])
logger = logging.getLogger(__name__)


@router.post("/evaluate-user/{user_id}", response_model=UserEvaluationRead)
async def evaluate_user_registration_endpoint(
    user_id: int,
    model: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Evaluate a user registration using LLM analysis
    
    Requires superuser privileges.
    """
    # Get user to evaluate
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if evaluation already exists
    stmt = select(UserEvaluation).where(UserEvaluation.user_id == user_id)
    result = await db.execute(stmt)
    existing_evaluation = result.scalar_one_or_none()
    
    if existing_evaluation:
        return existing_evaluation
    
    # Perform evaluation
    start_time = datetime.utcnow()
    evaluation_result = await evaluate_user_registration(user, model)
    processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    # Create evaluation record
    evaluation = UserEvaluation(
        user_id=user_id,
        overall_score=evaluation_result.overall_score,
        legitimacy_score=evaluation_result.legitimacy_score,
        research_intent_score=evaluation_result.research_intent_score,
        risk_score=evaluation_result.risk_score,
        recommendation=evaluation_result.recommendation,
        reasoning=evaluation_result.reasoning,
        confidence=evaluation_result.confidence,
        red_flags=evaluation_result.red_flags,
        positive_indicators=evaluation_result.positive_indicators,
        additional_checks_needed=evaluation_result.additional_checks_needed,
        manual_review_required=evaluation_result.manual_review_required
    )
    
    db.add(evaluation)
    
    # Create evaluation log
    log_entry = LLMEvaluationLog(
        user_id=user_id,
        llm_configuration_id=1,  # Default config - should be properly referenced
        evaluation_input=f"User evaluation for {user.email}",
        evaluation_output=evaluation_result.reasoning,
        confidence_score=evaluation_result.confidence,
        recommended_action=evaluation_result.recommendation,
        processing_time_ms=int(processing_time),
        success=True
    )
    
    db.add(log_entry)
    await db.commit()
    await db.refresh(evaluation)
    
    logger.info(f"User {user_id} evaluated with score {evaluation_result.overall_score:.1f}/10")
    
    return evaluation


@router.get("/user-evaluations", response_model=List[UserEvaluationRead])
async def get_user_evaluations(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Get all user evaluations
    
    Requires superuser privileges.
    """
    stmt = (
        select(UserEvaluation)
        .offset(skip)
        .limit(limit)
        .order_by(UserEvaluation.created_at.desc())
    )
    result = await db.execute(stmt)
    evaluations = result.scalars().all()
    
    return evaluations


@router.get("/user-evaluations/{user_id}", response_model=UserEvaluationRead)
async def get_user_evaluation(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Get evaluation for a specific user
    
    Requires superuser privileges.
    """
    stmt = select(UserEvaluation).where(UserEvaluation.user_id == user_id)
    result = await db.execute(stmt)
    evaluation = result.scalar_one_or_none()
    
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User evaluation not found"
        )
    
    return evaluation


@router.post("/approve-user/{token}")
async def approve_user_with_token(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Approve a user using a secure token (for email action buttons)
    
    This endpoint can be called without authentication using the secure token.
    """
    # Find and validate token
    stmt = (
        select(ApprovalToken)
        .where(ApprovalToken.token == token)
        .where(ApprovalToken.action == ApprovalTokenAction.APPROVE)
        .where(ApprovalToken.is_used is False)
        .where(ApprovalToken.expires_at > datetime.utcnow())
    )
    result = await db.execute(stmt)
    approval_token = result.scalar_one_or_none()
    
    if not approval_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired approval token"
        )
    
    # Get user to approve
    user = await get_user_by_id(db, approval_token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update user status
    user.approval_status = ApprovalStatus.APPROVED
    user.approval_date = datetime.utcnow()
    
    # Mark token as used
    approval_token.is_used = True
    approval_token.used_at = datetime.utcnow()
    approval_token.admin_ip = request.client.host
    approval_token.admin_user_agent = request.headers.get("user-agent", "")
    
    await db.commit()
    
    # Send approval confirmation email to user
    try:
        await send_user_approval_confirmation(
            user=user,
            approved=True,
            admin_message="Your account has been approved and you can now access all platform features."
        )
    except Exception as e:
        logger.error(f"Failed to send approval confirmation email: {str(e)}")
    
    logger.info(f"User {user.email} approved via token {token[:8]}...")
    
    # Return HTML response for better UX
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Approved</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }}
            .success {{
                color: #16a34a;
                border: 2px solid #16a34a;
                padding: 20px;
                border-radius: 8px;
                background-color: #f0fdf4;
            }}
        </style>
    </head>
    <body>
        <div class="success">
            <h2>✅ User Approved Successfully</h2>
            <p><strong>Email:</strong> {user.email}</p>
            <p><strong>Name:</strong> {user.full_name or 'Not provided'}</p>
            <p><strong>Approved at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
            <p>The user has been notified of their approval and can now access the platform.</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.post("/deny-user/{token}")
async def deny_user_with_token(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Deny a user using a secure token (for email action buttons)
    
    This endpoint can be called without authentication using the secure token.
    """
    # Find and validate token
    stmt = (
        select(ApprovalToken)
        .where(ApprovalToken.token == token)
        .where(ApprovalToken.action == ApprovalTokenAction.DENY)
        .where(ApprovalToken.is_used is False)
        .where(ApprovalToken.expires_at > datetime.utcnow())
    )
    result = await db.execute(stmt)
    denial_token = result.scalar_one_or_none()
    
    if not denial_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired denial token"
        )
    
    # Get user to deny
    user = await get_user_by_id(db, denial_token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update user status
    user.approval_status = ApprovalStatus.DENIED
    user.approval_date = datetime.utcnow()
    
    # Mark token as used
    denial_token.is_used = True
    denial_token.used_at = datetime.utcnow()
    denial_token.admin_ip = request.client.host
    denial_token.admin_user_agent = request.headers.get("user-agent", "")
    
    await db.commit()
    
    # Send denial confirmation email to user
    try:
        await send_user_approval_confirmation(
            user=user,
            approved=False,
            admin_message="Unfortunately, we are unable to approve your account at this time. If you believe this is an error, please contact our support team."
        )
    except Exception as e:
        logger.error(f"Failed to send denial confirmation email: {str(e)}")
    
    logger.info(f"User {user.email} denied via token {token[:8]}...")
    
    # Return HTML response for better UX
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Denied</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }}
            .denied {{
                color: #dc2626;
                border: 2px solid #dc2626;
                padding: 20px;
                border-radius: 8px;
                background-color: #fef2f2;
            }}
        </style>
    </head>
    <body>
        <div class="denied">
            <h2>❌ User Registration Denied</h2>
            <p><strong>Email:</strong> {user.email}</p>
            <p><strong>Name:</strong> {user.full_name or 'Not provided'}</p>
            <p><strong>Denied at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
            <p>The user registration has been denied. The user has been notified.</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.post("/manual-approve-user/{user_id}")
async def manual_approve_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Manually approve a user (for admin panel use)
    
    Requires superuser privileges.
    """
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.approval_status = ApprovalStatus.APPROVED
    user.approval_date = datetime.utcnow()
    
    await db.commit()
    
    # Send approval confirmation email to user
    try:
        await send_user_approval_confirmation(
            user=user,
            approved=True,
            admin_message="Your account has been manually approved by our admin team."
        )
    except Exception as e:
        logger.error(f"Failed to send approval confirmation email: {str(e)}")
    
    logger.info(f"User {user.email} manually approved by {current_user.email}")
    
    return {"message": "User approved successfully", "user_id": user_id}


@router.post("/manual-deny-user/{user_id}")
async def manual_deny_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Manually deny a user (for admin panel use)
    
    Requires superuser privileges.
    """
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.approval_status = ApprovalStatus.DENIED
    user.approval_date = datetime.utcnow()
    
    await db.commit()
    
    # Send denial confirmation email to user
    try:
        await send_user_approval_confirmation(
            user=user,
            approved=False,
            admin_message="Your account application has been reviewed by our admin team. Unfortunately, we are unable to approve your account at this time."
        )
    except Exception as e:
        logger.error(f"Failed to send denial confirmation email: {str(e)}")
    
    logger.info(f"User {user.email} manually denied by {current_user.email}")
    
    return {"message": "User denied successfully", "user_id": user_id}


@router.get("/pending-approvals", response_model=List[dict])
async def get_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Get all users pending approval with their evaluations
    
    Requires superuser privileges.
    """
    stmt = (
        select(User)
        .where(User.approval_status == ApprovalStatus.PENDING)
        .where(User.is_verified is True)
        .order_by(User.created_at.desc())
    )
    result = await db.execute(stmt)
    pending_users = result.scalars().all()
    
    # Get evaluations for these users
    user_ids = [user.id for user in pending_users]
    eval_stmt = select(UserEvaluation).where(UserEvaluation.user_id.in_(user_ids))
    eval_result = await db.execute(eval_stmt)
    evaluations = {eval.user_id: eval for eval in eval_result.scalars().all()}
    
    # Combine user and evaluation data
    pending_data = []
    for user in pending_users:
        evaluation = evaluations.get(user.id)
        pending_data.append({
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at,
                "research_interests": user.research_interests,
                "academic_affiliation": user.academic_affiliation,
                "research_purpose": user.research_purpose,
            },
            "evaluation": {
                "overall_score": evaluation.overall_score if evaluation else None,
                "recommendation": evaluation.recommendation if evaluation else None,
                "reasoning": evaluation.reasoning if evaluation else None,
                "confidence": evaluation.confidence if evaluation else None,
            } if evaluation else None
        })
    
    return pending_data