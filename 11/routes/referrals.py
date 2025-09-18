from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import User, ReferralCode, ReferralUse
from auth import get_current_user

router = APIRouter(prefix="/referrals", tags=["referrals"])

class ReferralStats(BaseModel):
    code: str
    total_referrals: int
    successful_referrals: int
    available_discounts: int
    referral_url: str

class ReferralHistory(BaseModel):
    referred_user_email: str
    used_at: datetime
    discount_used: bool

@router.get("/stats", response_model=ReferralStats)
async def get_referral_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get user's referral code
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.user_id == current_user.id)
    )
    referral_code = result.scalar_one_or_none()
    if not referral_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No referral code found"
        )

    # Get referral statistics
    result = await db.execute(
        select(
            func.count(ReferralUse.id).label("total"),
            func.count(ReferralUse.id).filter(ReferralUse.is_active == True).label("active"),
            func.count(ReferralUse.id).filter(
                ReferralUse.is_active == True,
                ReferralUse.referrer_discount_used == False
            ).label("available")
        ).where(ReferralUse.referral_code_id == referral_code.id)
    )
    stats = result.first()
    
    return ReferralStats(
        code=referral_code.code,
        total_referrals=stats[0] or 0,
        successful_referrals=stats[1] or 0,
        available_discounts=stats[2] or 0,
        referral_url=f"/register?ref={referral_code.code}"
    )

@router.get("/history", response_model=List[ReferralHistory])
async def get_referral_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get user's referral code
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.user_id == current_user.id)
    )
    referral_code = result.scalar_one_or_none()
    if not referral_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No referral code found"
        )

    # Get referral history with referred user details
    result = await db.execute(
        select(ReferralUse, User)
        .join(User, ReferralUse.referred_user_id == User.id)
        .where(ReferralUse.referral_code_id == referral_code.id)
        .order_by(ReferralUse.used_at.desc())
    )
    history = result.all()

    return [
        ReferralHistory(
            referred_user_email=user.email,
            used_at=use.used_at,
            discount_used=use.referrer_discount_used
        )
        for use, user in history
    ]

@router.get("/check-discount")
async def check_available_discount(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check if user has an unused referee discount
    result = await db.execute(
        select(ReferralUse)
        .where(ReferralUse.referred_user_id == current_user.id)
        .where(ReferralUse.referee_discount_used == False)
    )
    referee_discount = result.scalar_one_or_none()
    if referee_discount:
        return {"discount": 0.10, "type": "referee"}  # 10% discount

    # Check if user has unused referrer discounts from successful referrals
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.user_id == current_user.id)
    )
    referral_code = result.scalar_one_or_none()
    if referral_code:
        result = await db.execute(
            select(ReferralUse)
            .where(ReferralUse.referral_code_id == referral_code.id)
            .where(ReferralUse.referrer_discount_used == False)
            .where(ReferralUse.is_active == True)  # Only count active referrals
        )
        referrer_discount = result.scalar_one_or_none()
        if referrer_discount:
            return {"discount": 0.20, "type": "referrer"}  # 20% discount

    return {"discount": 0, "type": None} 