from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    orders = relationship("Order", back_populates="user")
    referral_code = relationship("ReferralCode", back_populates="user", uselist=False)
    referred_by = Column(String, nullable=True)  # Stores the referral code used during registration

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_type = Column(String(50), nullable=False, default="grillz")  # grillz, watch, bracelet
    material = Column(String(50), nullable=False)
    teeth_selection = Column(JSON, default=list)  # Store as JSON array (for grillz)
    product_details = Column(JSON, default=dict)  # Store product-specific details
    total_price = Column(Float, nullable=False)
    shipping_full_name = Column(String(255), nullable=False)
    shipping_address = Column(Text, nullable=False)
    shipping_city = Column(String(100), nullable=False)
    shipping_zip_code = Column(String(20), nullable=False)
    stripe_payment_intent = Column(String(255), unique=True, nullable=True)  # Stripe payment intent ID
    payment_status = Column(String(20), nullable=False, default="pending")  # pending, paid, failed
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="orders")
    invoice = relationship("Invoice", back_populates="order", uselist=False)

class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    order_uuid = Column(String(36), ForeignKey("orders.uuid"), unique=True, nullable=False)
    amount = Column(Float, nullable=False)  # USD amount
    currency = Column(String(10), nullable=False, default="USD")
    crypto_amount = Column(String(50), nullable=True)  # Amount in crypto
    crypto_currency = Column(String(20), nullable=True)  # Crypto currency code
    crypto_network = Column(String(50), nullable=True)  # Blockchain network
    payment_address = Column(String(255), nullable=True)  # Crypto wallet address
    payment_url = Column(Text, nullable=True)  # Cryptomus payment page URL
    status = Column(String(20), nullable=False, default="pending")  # pending, paid, expired, etc.
    expires_at = Column(DateTime, nullable=True)  # Invoice expiration time
    is_final = Column(Boolean, nullable=False, default=False)  # Whether invoice is finalized
    payment_transaction = Column(String(255), nullable=True)  # Transaction hash
    confirmed_at = Column(DateTime, nullable=True)  # When payment was confirmed
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    order = relationship("Order", back_populates="invoice") 

class ReferralCode(Base):
    __tablename__ = "referral_codes"
    
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="referral_code")
    uses = relationship("ReferralUse", back_populates="referral_code")

class ReferralUse(Base):
    __tablename__ = "referral_uses"
    
    id = Column(Integer, primary_key=True)
    referral_code_id = Column(Integer, ForeignKey("referral_codes.id"))
    referred_user_id = Column(Integer, ForeignKey("users.id"))
    first_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)  # Track first completed order
    used_at = Column(DateTime, default=datetime.utcnow)
    referrer_discount_used = Column(Boolean, default=False)  # 20% discount for referrer
    referee_discount_used = Column(Boolean, default=False)   # 10% discount for referee
    is_active = Column(Boolean, default=False)  # Only becomes true after first order is paid
    
    referral_code = relationship("ReferralCode", back_populates="uses")
    referred_user = relationship("User", foreign_keys=[referred_user_id])
    first_order = relationship("Order", foreign_keys=[first_order_id]) 