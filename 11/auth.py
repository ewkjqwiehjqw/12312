from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status, Depends, Request, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import User
from database import get_db

# Security configuration
SECRET_KEY = "your-secret-key-keep-it-secret"  # Change this in production!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    auth_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )
    if not auth_token:
        raise credentials_exception
    try:
        payload = jwt.decode(auth_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    async with db as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

# Optional dependency for routes that can be accessed by both authenticated and anonymous users
async def get_optional_current_user(
    auth_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not auth_token:
        return None
    try:
        return await get_current_user(auth_token, db)
    except HTTPException:
        return None

# Dependency that redirects to login for API routes instead of returning JSON error
async def get_current_user_or_redirect(
    request: Request,
    auth_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    try:
        return await get_current_user(auth_token, db)
    except HTTPException:
        # Check if this is an API request or HTML request
        accept_header = request.headers.get("accept", "")
        if "application/json" in accept_header or request.url.path.startswith("/api/"):
            # For API requests, return 401 with redirect info
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please redirect to /auth/login"
            )
        else:
            # For HTML requests, redirect directly
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="Redirecting to login",
                headers={"Location": "/auth/login"}
            ) 