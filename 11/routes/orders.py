from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import stripe
import os
import uuid
import logging
import hmac
import hashlib

from database import get_db
from models import Order, User, Invoice, ReferralCode, ReferralUse
from auth import get_current_user

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["orders"])

# ---------------------------------------------------------------------------
# Stripe Configuration
# ---------------------------------------------------------------------------
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# ---------------------------------------------------------------------------
# Pricing Configuration
# ---------------------------------------------------------------------------
GRILLZ_PRICES = {
    "gold": {
        "price": 299,
        "name": "18K Gold",
        "description": "Premium 18K gold finish"
    },
    "silver": {
        "price": 149,
        "name": "Silver",
        "description": "Sterling silver finish"
    },
    "diamond": {
        "price": 999,
        "name": "Iced",
        "description": "Premium diamond setting"
    }
}

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class MaterialPrice(BaseModel):
    price: float
    name: str
    description: str

class PricingResponse(BaseModel):
    materials: Dict[str, MaterialPrice]
    stripe_publishable_key: Optional[str] = None

class OrderCreate(BaseModel):
    product_type: str = Field(..., pattern="^(grillz|watch|bracelet)$")
    material: str = Field(..., min_length=1, max_length=50)
    teeth_selection: Optional[List[int]] = Field(default=[])
    product_details: Optional[dict] = Field(default_factory=dict)
    shipping_full_name: str = Field(..., min_length=1, max_length=255)
    shipping_address: str = Field(..., min_length=1, max_length=500)
    shipping_city: str = Field(..., min_length=1, max_length=100)
    shipping_zip_code: str = Field(..., min_length=1, max_length=20)
    use_referral_discount: Optional[bool] = False

class OrderResponse(BaseModel):
    id: int
    uuid: str
    product_type: str
    material: str
    teeth_selection: Optional[List[int]] = []
    product_details: Optional[dict] = {}
    total_price: float
    shipping_full_name: str
    shipping_address: str
    shipping_city: str
    shipping_zip_code: str
    payment_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateOrderResponse(BaseModel):
    success: bool
    order_uuid: str
    total_price: float
    currency: str
    client_secret: Optional[str] = None  # Stripe payment intent client secret
    payment_intent_id: Optional[str] = None  # Stripe payment intent ID
    message: str

class InvoiceResponse(BaseModel):
    success: bool
    invoice_uuid: str
    order_uuid: str
    amount: float
    currency: str
    status: str
    message: str

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.get("/prices", response_model=PricingResponse)
async def get_prices():
    """Get current pricing for all materials"""
    try:
        return PricingResponse(
            materials={
                material: MaterialPrice(**details)
                for material, details in GRILLZ_PRICES.items()
            },
            stripe_publishable_key=STRIPE_PUBLISHABLE_KEY
        )
    except Exception as e:
        logger.error(f"Error getting prices: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get pricing information"
        )

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    order_data: OrderCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new order"""
    logger.info(f"Creating order for user {current_user.id}: {order_data}")
    
    # Validate and calculate price
    total_price = 0
    
    if order_data.product_type == "grillz":
        material_config = GRILLZ_PRICES.get(order_data.material)
        if not material_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid material '{order_data.material}' for grillz"
            )
        
        if not order_data.teeth_selection or len(order_data.teeth_selection) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one tooth must be selected for grillz"
            )
        
        total_price = material_config["price"] * len(order_data.teeth_selection)
        
    elif order_data.product_type in ["watch", "bracelet"]:
        product_price = order_data.product_details.get("price", 0)
        if product_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product price"
            )
        total_price = product_price
    
    # Apply referral discount if requested
    discount_type = None
    if order_data.use_referral_discount:
        total_price, discount_type = await apply_referral_discount(
            db, current_user.id, total_price
        )

    # Generate unique UUID for order
    order_uuid = str(uuid.uuid4())
    
    # Create order
    order = Order(
        uuid=order_uuid,
        user_id=current_user.id,
        product_type=order_data.product_type,
        material=order_data.material,
        teeth_selection=order_data.teeth_selection,
        product_details={
            **order_data.product_details,
            "discount_applied": discount_type
        },
        total_price=total_price,
        shipping_full_name=order_data.shipping_full_name,
        shipping_address=order_data.shipping_address,
        shipping_city=order_data.shipping_city,
        shipping_zip_code=order_data.shipping_zip_code,
        payment_status="pending"
    )
    
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    # Create Stripe Checkout Session
    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': f'{order_data.product_type.title()} - {order_data.material.title()}',
                    'description': f'Custom {order_data.product_type} order',
                },
                'unit_amount': int(total_price * 100),  # Stripe expects cents
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f"{request.base_url}invoice/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{request.base_url}",
        metadata={
            'order_uuid': order.uuid,
            'product_type': order.product_type,
            'material': order.material,
            'user_id': str(current_user.id),
            'discount_type': discount_type or 'none'
        }
    )
    
    # Store checkout session ID
    order.stripe_payment_intent = checkout_session.id
    await db.commit()
    
    logger.info(f"Order and Stripe checkout session created: {order.uuid}")
    
    return CreateOrderResponse(
        success=True,
        order_uuid=order.uuid,
        total_price=order.total_price,
        currency="USD",
        client_secret=checkout_session.url,  # This is the Stripe checkout URL
        payment_intent_id=checkout_session.id,
        message="Order created successfully"
    )


@router.get("/orders", response_model=List[OrderResponse])
async def get_user_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all orders for the current user"""
    try:
        result = await db.execute(
            select(Order)
            .where(Order.user_id == current_user.id)
            .order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()
        return orders
        
    except Exception as e:
        logger.error(f"Error getting user orders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get orders"
        )

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

async def apply_referral_discount(db: AsyncSession, user_id: int, total_price: float):
    """Apply referral discount if available"""
    discount_type = None
    
    try:
        # Check for referee discount (10% off)
        result = await db.execute(
            select(ReferralUse)
            .where(ReferralUse.referred_user_id == user_id)
            .where(ReferralUse.referee_discount_used == False)
        )
        referee_discount = result.scalar_one_or_none()
        
        if referee_discount:
            total_price = total_price * 0.9  # 10% off
            referee_discount.referee_discount_used = True
            discount_type = "referee"
        else:
            # Check for referrer discount (20% off)
            result = await db.execute(
                select(ReferralCode).where(ReferralCode.user_id == user_id)
            )
            referral_code = result.scalar_one_or_none()
            
            if referral_code:
                result = await db.execute(
                    select(ReferralUse)
                    .where(ReferralUse.referral_code_id == referral_code.id)
                    .where(ReferralUse.referrer_discount_used == False)
                )
                referrer_discount = result.scalar_one_or_none()
                
                if referrer_discount:
                    total_price = total_price * 0.8  # 20% off
                    referrer_discount.referrer_discount_used = True
                    discount_type = "referrer"
        
        await db.commit()
        
    except Exception as e:
        logger.error(f"Error applying referral discount: {str(e)}")
        await db.rollback()
    
    return total_price, discount_type

# ---------------------------------------------------------------------------
# Stripe Webhook Handler
# ---------------------------------------------------------------------------

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Stripe webhook endpoint to handle payment events
    This endpoint is called by Stripe when payment events occur
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"Verified Stripe webhook event: {event['type']}")
        
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        logger.info(f"Processing checkout session completed: {session['id']}")
        
        try:
            await handle_successful_payment(db, session)
        except Exception as e:
            logger.error(f"Error processing successful payment: {str(e)}")
            # Don't raise here - we still want to return 200 to Stripe
            # to acknowledge we received the webhook
    
    # Handle payment failure events
    elif event['type'] == 'checkout.session.expired':
        session = event['data']['object']
        logger.info(f"Processing checkout session expired: {session['id']}")
        
        try:
            await handle_failed_payment(db, session)
        except Exception as e:
            logger.error(f"Error processing failed payment: {str(e)}")
    
    else:
        logger.info(f"Unhandled event type: {event['type']}")
    
    return JSONResponse(content={"status": "success"})

async def handle_successful_payment(db: AsyncSession, session):
    """Handle successful payment completion"""
    checkout_session_id = session['id']
    
    # Find the order by checkout session ID
    result = await db.execute(
        select(Order).where(Order.stripe_payment_intent == checkout_session_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        logger.error(f"Order not found for checkout session: {checkout_session_id}")
        return
    
    if order.payment_status == 'paid':
        logger.info(f"Order {order.uuid} already marked as paid")
        return
    
    # Update order status to paid
    order.payment_status = 'paid'
    order.updated_at = datetime.utcnow()
    
    logger.info(f"Order {order.uuid} marked as paid")
    
    # Activate referral bonuses if this is the user's first paid order
    await activate_referral_bonus(db, order.user_id, order.id)
    
    await db.commit()
    logger.info(f"Successfully processed payment for order {order.uuid}")

async def handle_failed_payment(db: AsyncSession, session):
    """Handle failed/expired payment"""
    checkout_session_id = session['id']
    
    # Find the order by checkout session ID
    result = await db.execute(
        select(Order).where(Order.stripe_payment_intent == checkout_session_id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        logger.error(f"Order not found for checkout session: {checkout_session_id}")
        return
    
    # Update order status to failed
    order.payment_status = 'failed'
    order.updated_at = datetime.utcnow()
    
    await db.commit()
    logger.info(f"Order {order.uuid} marked as failed")

async def activate_referral_bonus(db: AsyncSession, user_id: int, order_id: int):
    """Activate referral bonuses when user completes their first order"""
    try:
        # Check if this user was referred by someone
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user or not user.referred_by:
            return  # User wasn't referred
        
        # Find the referral use record
        referral_code_result = await db.execute(
            select(ReferralCode).where(ReferralCode.code == user.referred_by)
        )
        referral_code = referral_code_result.scalar_one_or_none()
        
        if not referral_code:
            logger.warning(f"Referral code {user.referred_by} not found")
            return
        
        referral_use_result = await db.execute(
            select(ReferralUse).where(
                ReferralUse.referral_code_id == referral_code.id,
                ReferralUse.referred_user_id == user_id
            )
        )
        referral_use = referral_use_result.scalar_one_or_none()
        
        if not referral_use:
            logger.warning(f"Referral use record not found for user {user_id}")
            return
        
        if referral_use.is_active:
            logger.info(f"Referral bonus already activated for user {user_id}")
            return
        
        # Activate the referral bonus
        referral_use.is_active = True
        referral_use.first_order_id = order_id
        
        await db.commit()
        logger.info(f"Activated referral bonus for user {user_id}, referrer gets commission")
        
    except Exception as e:
        logger.error(f"Error activating referral bonus: {str(e)}")
        await db.rollback()