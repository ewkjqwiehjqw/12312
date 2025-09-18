from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import calendar

from database import get_db
from models import User, Order, ReferralCode, ReferralUse
from auth import get_optional_current_user

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

# Security dependency - admin only
async def require_admin(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user)
) -> User:
    """Ensure user is authenticated and is an admin"""
    if not current_user:
        # Check if this is an API request
        if request.url.path.startswith("/admin/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        else:
            # For HTML pages, redirect to login
            from fastapi.responses import RedirectResponse
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="Redirecting to login",
                headers={"Location": "/auth/login"}
            )
    
    if not current_user.is_admin:
        # Access denied for non-admin users
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user

# Pydantic models for API responses
class AdminStats(BaseModel):
    total_users: int
    total_orders: int
    total_revenue: float
    pending_orders: int
    completed_orders: int
    shipped_orders: int
    failed_orders: int
    total_referrals: int
    active_referrals: int

class RevenueData(BaseModel):
    daily_revenue: List[dict]
    monthly_revenue: List[dict]
    top_materials: List[dict]

class OrderSummary(BaseModel):
    id: int
    uuid: str
    user_email: str
    product_type: str
    material: str
    teeth_selection: Optional[List[int]] = []
    product_details: Optional[dict] = {}
    total_price: float
    payment_status: str
    created_at: datetime
    updated_at: datetime

class UserSummary(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    created_at: datetime
    total_orders: int
    total_spent: float

class OrderStatusUpdate(BaseModel):
    status: str

# ---------------------------------------------------------------------------
# Admin Dashboard Routes
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Admin dashboard homepage"""
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "user": current_user}
    )

@router.get("/orders", response_class=HTMLResponse)
async def admin_orders(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Admin orders management page"""
    return templates.TemplateResponse(
        "admin/orders.html",
        {"request": request, "user": current_user}
    )

@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Admin users management page"""
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "user": current_user}
    )



# ---------------------------------------------------------------------------
# Admin API Routes
# ---------------------------------------------------------------------------

@router.get("/api/stats", response_model=AdminStats)
async def get_admin_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get overall admin statistics"""
    
    try:
        # Get user stats
        users_result = await db.execute(select(func.count(User.id)))
        total_users = users_result.scalar() or 0
        
        # Get order stats
        orders_result = await db.execute(select(func.count(Order.id)))
        total_orders = orders_result.scalar() or 0
        
        pending_result = await db.execute(
            select(func.count(Order.id)).where(Order.payment_status == 'pending')
        )
        pending_orders = pending_result.scalar() or 0
        
        completed_result = await db.execute(
            select(func.count(Order.id)).where(Order.payment_status == 'paid')
        )
        completed_orders = completed_result.scalar() or 0
        
        shipped_result = await db.execute(
            select(func.count(Order.id)).where(Order.payment_status == 'shipped')
        )
        shipped_orders = shipped_result.scalar() or 0
        
        failed_result = await db.execute(
            select(func.count(Order.id)).where(Order.payment_status == 'failed')
        )
        failed_orders = failed_result.scalar() or 0
        
        # Get revenue (from paid and shipped orders)
        revenue_result = await db.execute(
            select(func.sum(Order.total_price)).where(
                Order.payment_status.in_(['paid', 'shipped'])
            )
        )
        total_revenue = revenue_result.scalar() or 0.0
        
        # Get referral stats - handle case where ReferralUse table might not exist or be empty
        try:
            referrals_result = await db.execute(select(func.count(ReferralUse.id)))
            total_referrals = referrals_result.scalar() or 0
            
            active_referrals_result = await db.execute(
                select(func.count(ReferralUse.id)).where(ReferralUse.is_active == True)
            )
            active_referrals = active_referrals_result.scalar() or 0
        except Exception:
            # If referral tables don't exist or have issues, default to 0
            total_referrals = 0
            active_referrals = 0
        
        return AdminStats(
            total_users=total_users,
            total_orders=total_orders,
            total_revenue=total_revenue,
            pending_orders=pending_orders,
            completed_orders=completed_orders,
            shipped_orders=shipped_orders,
            failed_orders=failed_orders,
            total_referrals=total_referrals,
            active_referrals=active_referrals
        )
    except Exception as e:
        print(f"Error in get_admin_stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stats error: {str(e)}"
        )

@router.get("/api/orders", response_model=List[OrderSummary])
async def get_all_orders(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
):
    """Get all orders with optional filtering"""
    
    query = select(Order, User.email).join(User, Order.user_id == User.id)
    
    if status:
        query = query.where(Order.payment_status == status)
    
    query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    order_data = result.all()
    
    return [
        OrderSummary(
            id=order.id,
            uuid=order.uuid,
            user_email=email,
            product_type=order.product_type,
            material=order.material,
            teeth_selection=order.teeth_selection if order.teeth_selection else [],
            product_details=order.product_details if order.product_details else {},
            total_price=order.total_price,
            payment_status=order.payment_status,
            created_at=order.created_at,
            updated_at=order.updated_at
        )
        for order, email in order_data
    ]

@router.get("/api/users", response_model=List[UserSummary])
async def get_all_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """Get all users with their order statistics"""
    
    try:
        # Get all users first
        users_query = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        users_result = await db.execute(users_query)
        users = users_result.scalars().all()
        
        # Build response with basic user data and simple stats
        user_summaries = []
        for user in users:
            # Get order count for this user
            orders_count_query = select(func.count(Order.id)).where(Order.user_id == user.id)
            orders_count_result = await db.execute(orders_count_query)
            total_orders = orders_count_result.scalar() or 0
            
            # Get total spent for this user (paid and shipped orders)
            total_spent_query = select(func.sum(Order.total_price)).where(
                and_(Order.user_id == user.id, Order.payment_status.in_(['paid', 'shipped']))
            )
            total_spent_result = await db.execute(total_spent_query)
            total_spent = total_spent_result.scalar() or 0.0
            
            user_summaries.append(UserSummary(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_admin=user.is_admin,
                created_at=user.created_at,
                total_orders=total_orders,
                total_spent=float(total_spent)
            ))
        
        return user_summaries
    except Exception as e:
        print(f"Error in get_all_users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

@router.post("/api/users/{user_id}/toggle-admin")
async def toggle_user_admin(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Toggle admin status for a user - admin only"""
    
    try:
        # Get the target user
        result = await db.execute(select(User).where(User.id == user_id))
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent users from removing their own admin status (to avoid lockout)
        if target_user.id == current_user.id and target_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own admin status"
            )
        
        # Toggle admin status
        target_user.is_admin = not target_user.is_admin
        await db.commit()
        
        return {
            "success": True,
            "message": f"User {'granted' if target_user.is_admin else 'removed'} admin access",
            "user_id": user_id,
            "is_admin": target_user.is_admin
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        print(f"Error toggling admin status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user admin status"
        )

@router.get("/api/revenue", response_model=RevenueData)
async def get_revenue_analytics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get revenue analytics data"""
    
    # Get daily revenue for last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_result = await db.execute(
        select(
            func.date(Order.created_at).label('date'),
            func.sum(Order.total_price).label('revenue')
        )
        .where(
            and_(
                Order.payment_status == 'paid',
                Order.created_at >= thirty_days_ago
            )
        )
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    )
    daily_revenue = [
        {"date": str(date), "revenue": float(revenue)}
        for date, revenue in daily_result.all()
    ]
    
    # Get monthly revenue for last 12 months
    twelve_months_ago = datetime.utcnow() - timedelta(days=365)
    monthly_result = await db.execute(
        select(
            func.extract('year', Order.created_at).label('year'),
            func.extract('month', Order.created_at).label('month'),
            func.sum(Order.total_price).label('revenue')
        )
        .where(
            and_(
                Order.payment_status == 'paid',
                Order.created_at >= twelve_months_ago
            )
        )
        .group_by(
            func.extract('year', Order.created_at),
            func.extract('month', Order.created_at)
        )
        .order_by(
            func.extract('year', Order.created_at),
            func.extract('month', Order.created_at)
        )
    )
    monthly_revenue = [
        {
            "month": f"{calendar.month_abbr[int(month)]} {int(year)}",
            "revenue": float(revenue)
        }
        for year, month, revenue in monthly_result.all()
    ]
    
    # Get top materials by revenue
    materials_result = await db.execute(
        select(
            Order.material,
            func.sum(Order.total_price).label('revenue'),
            func.count(Order.id).label('count')
        )
        .where(Order.payment_status == 'paid')
        .group_by(Order.material)
        .order_by(func.sum(Order.total_price).desc())
    )
    top_materials = [
        {
            "material": material,
            "revenue": float(revenue),
            "count": count
        }
        for material, revenue, count in materials_result.all()
    ]
    
    return RevenueData(
        daily_revenue=daily_revenue,
        monthly_revenue=monthly_revenue,
        top_materials=top_materials
    )


@router.put("/api/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update order status manually"""
    
    try:
        if status_update.status not in ['pending', 'paid', 'shipped', 'failed', 'cancelled']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid status. Must be one of: pending, paid, shipped, failed, cancelled"
            )
        
        # Get the order
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Order not found"
            )
        
        old_status = order.payment_status
        order.payment_status = status_update.status
        order.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "order_id": order_id,
            "old_status": old_status,
            "new_status": status_update.status,
            "message": f"Order status updated from {old_status} to {status_update.status}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        print(f"Error updating order status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order status"
        )
