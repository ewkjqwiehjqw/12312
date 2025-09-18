from fastapi import APIRouter, Request, Depends, HTTPException, status, Query, Path
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
import re
import html
import bleach
import secrets
import string
import logging

from models import User, Invoice, Order, ReferralCode, ReferralUse
from auth import get_optional_current_user, get_current_user
from database import get_db

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

def sanitize_string(value: str) -> str:
    """Sanitize string input to prevent XSS and injection attacks"""
    if not value:
        return ""
    # Remove HTML tags and strip whitespace
    sanitized = bleach.clean(value.strip(), tags=[], strip=True)
    # Escape HTML entities
    sanitized = html.escape(sanitized)
    return sanitized

def validate_referral_code(code: str) -> str:
    """Validate and sanitize referral code"""
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Referral code cannot be empty"
        )
    
    # Sanitize the code
    sanitized = sanitize_string(code)
    
    # Check length limits
    if len(sanitized) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Referral code too long"
        )
    
    # Only allow alphanumeric characters and hyphens
    if not re.match(r'^[a-zA-Z0-9\-]+$', sanitized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid referral code format"
        )
    
    return sanitized

def generate_secure_referral_code(length: int = 8) -> str:
    """Generate a cryptographically secure referral code"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    try:
        return templates.TemplateResponse(
            "landing.html",
            {"request": request, "user": current_user}
        )
    except Exception as e:
        logger.error(f"Error rendering home page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Page could not be loaded"
        )

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    try:
        # Redirect unauthenticated users to login page
        if current_user is None:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Check if user is active
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            logger.warning(f"Inactive user trying to access dashboard: {current_user.email[:5]}***")
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": current_user}
        )
    except Exception as e:
        logger.error(f"Error rendering dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard could not be loaded"
        )

@router.get("/studio", response_class=HTMLResponse)
async def studio_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    try:
        # Redirect unauthenticated users to login page
        if current_user is None:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Check if user is active
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        return templates.TemplateResponse(
            "order/create.html",
            {"request": request, "user": current_user}
        )
    except Exception as e:
        logger.error(f"Error rendering studio page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Studio page could not be loaded"
        )

@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    try:
        # Redirect unauthenticated users to login page
        if current_user is None:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Check if user is active
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        return templates.TemplateResponse(
            "checkout.html",
            {"request": request, "user": current_user}
        )
    except Exception as e:
        logger.error(f"Error rendering checkout page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Checkout page could not be loaded"
        )

@router.get("/invoice/success", response_class=HTMLResponse)
async def invoice_success_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    try:
        # Redirect unauthenticated users to login page
        if current_user is None:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Check if user is active
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
        return templates.TemplateResponse(
            "invoice/success.html",
            {"request": request, "user": current_user}
        )
    except Exception as e:
        logger.error(f"Error rendering invoice success page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Page could not be loaded"
        )

@router.get("/ref/{referral_code}")
async def referral_redirect(
    referral_code: str = Path(..., max_length=50, regex=r'^[a-zA-Z0-9\-]+$'),
    db: AsyncSession = Depends(get_db)
):
    """Redirect referral links to registration with pre-filled code"""
    try:
        # Additional validation and sanitization
        validated_code = validate_referral_code(referral_code)
        logger.info(f"Referral redirect attempt with code: {validated_code[:3]}***")
        
        # Validate that the referral code exists with proper error handling
        try:
            result = await db.execute(
                select(ReferralCode).where(ReferralCode.code == validated_code)
            )
            referral = result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Database error during referral code lookup: {str(e)}")
            # Redirect to regular register page on database error
            return RedirectResponse(url="/auth/register", status_code=status.HTTP_303_SEE_OTHER)
        
        if not referral:
            logger.warning(f"Invalid referral code accessed: {validated_code}")
            # Invalid referral code - redirect to regular register page
            return RedirectResponse(url="/auth/register", status_code=status.HTTP_303_SEE_OTHER)
        
        # Valid referral code - redirect to register with the code as a query parameter
        return RedirectResponse(
            url=f"/auth/register?ref={validated_code}", 
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in referral redirect: {str(e)}")
        return RedirectResponse(url="/auth/register", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    try:
        if current_user:
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "user": None}
        )
    except Exception as e:
        logger.error(f"Error rendering login page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login page could not be loaded"
        )

@router.get("/auth/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    ref: Optional[str] = Query(None, max_length=50)
):
    try:
        if current_user:
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        
        # Sanitize referral code if provided
        sanitized_ref = None
        if ref:
            try:
                sanitized_ref = validate_referral_code(ref)
            except HTTPException:
                # Invalid referral code - ignore it
                sanitized_ref = None
        
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "user": None, "referral_code": sanitized_ref}
        )
    except Exception as e:
        logger.error(f"Error rendering register page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration page could not be loaded"
        )

@router.get("/referrals", response_class=HTMLResponse)
async def referral_dashboard(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Redirect unauthenticated users to login page
        if current_user is None:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Check if user is active
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Get user's referral code with error handling
        try:
            referral_code_result = await db.execute(
                select(ReferralCode).where(ReferralCode.user_id == current_user.id)
            )
            user_referral_code = referral_code_result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching referral code: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error loading referral data"
            )
        
        # If user doesn't have a referral code, create one with secure generation
        if not user_referral_code:
            try:
                code = generate_secure_referral_code(8)
                user_referral_code = ReferralCode(user_id=current_user.id, code=code)
                db.add(user_referral_code)
                await db.commit()
                await db.refresh(user_referral_code)
            except SQLAlchemyError as e:
                logger.error(f"Database error creating referral code: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error creating referral code"
                )
        
        # Get referral stats with user details with error handling
        try:
            referral_uses_result = await db.execute(
                select(ReferralUse, User)
                .join(User, ReferralUse.referred_user_id == User.id)
                .where(ReferralUse.referral_code_id == user_referral_code.id)
                .order_by(ReferralUse.used_at.desc())
            )
            referral_data = referral_uses_result.all()
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching referral uses: {str(e)}")
            referral_data = []
        
        referral_uses = [ru for ru, user in referral_data]
        
        # Calculate stats with error handling
        total_referrals = len(referral_uses)
        active_referrals = len([r for r in referral_uses if r.is_active])
        pending_referrals = total_referrals - active_referrals
        
        # Calculate earnings and prepare detailed referral data
        total_earnings = 0.0
        detailed_referrals = []
        
        for referral_use, referred_user in referral_data:
            reward = 0.0
            if referral_use.is_active and referral_use.first_order_id:
                try:
                    # Get the order to calculate 20% of its value
                    order_result = await db.execute(
                        select(Order).where(Order.id == referral_use.first_order_id)
                    )
                    order = order_result.scalar_one_or_none()
                    if order and order.total_price:
                        reward = float(order.total_price) * 0.20  # 20% commission
                        total_earnings += reward
                except (SQLAlchemyError, ValueError, TypeError) as e:
                    logger.error(f"Error calculating referral reward: {str(e)}")
                    reward = 0.0
            
            detailed_referrals.append({
                'user': referred_user,
                'referral_use': referral_use,
                'reward': reward
            })
        
        return templates.TemplateResponse(
            "referrals.html",
            {
                "request": request, 
                "user": current_user,
                "referral_code": user_referral_code.code,
                "total_referrals": total_referrals,
                "active_referrals": active_referrals,
                "pending_referrals": pending_referrals,
                "total_earnings": round(total_earnings, 2),
                "detailed_referrals": detailed_referrals
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in referral dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Referral dashboard could not be loaded"
        )

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Redirect unauthenticated users to login page
        if current_user is None:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Check if user is active
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

        # Get all orders for the current user with error handling
        try:
            result = await db.execute(
                select(Order)
                .where(Order.user_id == current_user.id)
                .order_by(Order.created_at.desc())
            )
            orders = result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching orders: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error loading orders"
            )
        
        # Calculate stats with error handling
        try:
            total_orders = len(orders)
            pending_orders = len([o for o in orders if o.payment_status == 'pending'])
            completed_orders = len([o for o in orders if o.payment_status == 'paid'])
            shipped_orders = len([o for o in orders if o.payment_status == 'shipped'])
            
            # Calculate total spent with proper error handling
            total_spent = 0.0
            for order in orders:
                if order.payment_status in ['paid', 'shipped'] and order.total_price:
                    try:
                        total_spent += float(order.total_price)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid total_price for order {order.id}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error calculating order stats: {str(e)}")
            # Set default values on error
            total_orders = pending_orders = completed_orders = shipped_orders = 0
            total_spent = 0.0
        
        return templates.TemplateResponse(
            "orders.html",
            {
                "request": request, 
                "user": current_user,
                "orders": orders or [],
                "total_orders": total_orders,
                "pending_orders": pending_orders,
                "completed_orders": completed_orders,
                "shipped_orders": shipped_orders,
                "total_spent": round(total_spent, 2)
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in orders page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orders page could not be loaded"
        )