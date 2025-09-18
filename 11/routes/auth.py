from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr

from database import get_db
from models import User, ReferralCode, ReferralUse
from auth import (
    verify_password,
    create_access_token,
    get_password_hash,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter(prefix="/auth", tags=["auth"])

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    referral_code: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    email: str
    full_name: str
    is_admin: bool

@router.post("/login")
async def login(
    user_data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == user_data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    response.set_cookie(
        key="auth_token",
        value=access_token,
        httponly=True,
        max_age=60*60*24,
        samesite="lax"
    )
    return {"message": "Login successful"}

@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Handle referral code if provided
    referral_code = None
    if user_data.referral_code:
        result = await db.execute(
            select(ReferralCode).where(ReferralCode.code == user_data.referral_code)
        )
        referral_code = result.scalar_one_or_none()
        if not referral_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid referral code"
            )

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        referred_by=user_data.referral_code
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create referral code for new user
    import uuid
    new_referral = ReferralCode(
        code=str(uuid.uuid4())[:8],
        user_id=user.id
    )
    db.add(new_referral)

    # Record referral use if code was provided
    if referral_code:
        referral_use = ReferralUse(
            referral_code_id=referral_code.id,
            referred_user_id=user.id
        )
        db.add(referral_use)

    await db.commit()
    return UserResponse(
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin
    )

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        email=current_user.email,
        full_name=current_user.full_name,
        is_admin=current_user.is_admin
    )

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("auth_token")
    return {"message": "Successfully logged out"} 