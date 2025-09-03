"""
Invitation token endpoints
"""
from typing import Any, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.invitation import (
    InvitationToken,
    InvitationTokenCreate, 
    InvitationTokenRead,
    InvitationTokenValidation,
    generate_invitation_token
)
from app.services.admin_settings_service import can_create_invitation_tokens

router = APIRouter()


@router.post("/create", response_model=InvitationTokenRead)
async def create_invitation(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    invitation_in: InvitationTokenCreate
) -> Any:
    """
    Create a new invitation token.
    Only authenticated users can create invitations.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user cannot create invitations"
        )
    
    # Check if invitation token creation is allowed
    # Admins can always create invitation tokens regardless of the setting
    tokens_allowed = await can_create_invitation_tokens(db)
    if not tokens_allowed and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation token creation is currently disabled"
        )
    
    # Validate max_uses limit (1-10 as defined in model)
    if invitation_in.max_uses < 1 or invitation_in.max_uses > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_uses must be between 1 and 10"
        )
    
    # Set expiry to 7 days if not provided
    expires_at = invitation_in.expires_at
    if expires_at is None:
        expires_at = datetime.utcnow() + timedelta(days=7)
    elif expires_at <= datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expiration date must be in the future"
        )
    
    # Generate secure token
    token = generate_invitation_token()
    
    # Create invitation
    invitation = InvitationToken(
        token=token,
        creator_user_id=current_user.id,
        expires_at=expires_at,
        max_uses=invitation_in.max_uses
        # metadata field temporarily disabled due to SQLModel JSON issue
    )
    
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    
    return invitation


@router.get("/my-tokens", response_model=List[InvitationTokenRead])
async def list_my_invitations(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_used: bool = False
) -> Any:
    """
    List invitation tokens created by the current user.
    """
    query = select(InvitationToken).where(
        InvitationToken.creator_user_id == current_user.id
    )
    
    if not include_used:
        query = query.where(
            (InvitationToken.current_uses < InvitationToken.max_uses) &
            (InvitationToken.expires_at > datetime.utcnow())
        )
    
    result = await db.execute(query.order_by(InvitationToken.created_at.desc()))
    invitations = result.scalars().all()
    
    return list(invitations)


@router.post("/revoke/{token}")
async def revoke_invitation(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    token: str
) -> Any:
    """
    Revoke an invitation token.
    Only the creator can revoke their own tokens.
    """
    result = await db.execute(
        select(InvitationToken).where(
            (InvitationToken.token == token) &
            (InvitationToken.creator_user_id == current_user.id)
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation token not found or not owned by you"
        )
    
    # Mark as fully used to effectively revoke it
    invitation.current_uses = invitation.max_uses
    invitation.is_used = True
    
    await db.commit()
    
    return {"message": "Invitation token revoked successfully"}


@router.get("/validate/{token}", response_model=InvitationTokenValidation)
async def validate_invitation(
    *,
    db: AsyncSession = Depends(get_db),
    token: str
) -> Any:
    """
    Validate an invitation token.
    Returns validation status and metadata.
    """
    result = await db.execute(
        select(InvitationToken).where(InvitationToken.token == token)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        return InvitationTokenValidation(
            is_valid=False,
            message="Invalid invitation token"
        )
    
    # Check expiration
    if invitation.expires_at <= datetime.utcnow():
        return InvitationTokenValidation(
            is_valid=False,
            message="Invitation token has expired"
        )
    
    # Check usage limits
    if invitation.current_uses >= invitation.max_uses:
        return InvitationTokenValidation(
            is_valid=False,
            message="Invitation token has been fully used"
        )
    
    # Get creator name for display
    creator_result = await db.execute(
        select(User.full_name, User.email).where(User.id == invitation.creator_user_id)
    )
    creator_data = creator_result.first()
    creator_name = creator_data.full_name if creator_data and creator_data.full_name else creator_data.email if creator_data else "Unknown"
    
    uses_remaining = invitation.max_uses - invitation.current_uses
    
    return InvitationTokenValidation(
        is_valid=True,
        message="Valid invitation token",
        creator_name=creator_name,
        uses_remaining=uses_remaining,
        expires_at=invitation.expires_at
    )


async def consume_invitation_token(
    db: AsyncSession,
    token: str,
    used_by_email: str
) -> bool:
    """
    Internal function to consume an invitation token.
    Called during registration process.
    """
    result = await db.execute(
        select(InvitationToken).where(InvitationToken.token == token)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        return False
    
    # Validate token
    if (invitation.expires_at <= datetime.utcnow() or 
        invitation.current_uses >= invitation.max_uses):
        return False
    
    # Consume the token
    invitation.current_uses += 1
    invitation.used_by_email = used_by_email
    invitation.used_at = datetime.utcnow()
    
    # Mark as used if fully consumed
    if invitation.current_uses >= invitation.max_uses:
        invitation.is_used = True
    
    await db.commit()
    return True


@router.get("/stats")
async def get_invitation_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get invitation statistics for the current user.
    """
    # Count active tokens
    active_result = await db.execute(
        select(InvitationToken).where(
            (InvitationToken.creator_user_id == current_user.id) &
            (InvitationToken.current_uses < InvitationToken.max_uses) &
            (InvitationToken.expires_at > datetime.utcnow())
        )
    )
    active_tokens = len(active_result.scalars().all())
    
    # Count total tokens created
    total_result = await db.execute(
        select(InvitationToken).where(
            InvitationToken.creator_user_id == current_user.id
        )
    )
    total_tokens = len(total_result.scalars().all())
    
    # Count total uses
    uses_result = await db.execute(
        select(InvitationToken.current_uses).where(
            InvitationToken.creator_user_id == current_user.id
        )
    )
    total_uses = sum(row[0] for row in uses_result.fetchall())
    
    return {
        "active_tokens": active_tokens,
        "total_tokens_created": total_tokens, 
        "total_invitations_used": total_uses,
        "can_create_more": True  # Could add limits here later
    }