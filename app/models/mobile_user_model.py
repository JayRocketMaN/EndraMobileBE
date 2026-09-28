import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, Numeric, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship as sqlalchemy_relationship  # <-- Alias to prevent shadowing
from app.core.database import Base


class UseCaseEnum(str, enum.Enum):
    PERSONAL = "Myself"
    FAMILY = "Family"
    BUSINESS = "Business"
    PROPERTY = "Property"
    HOME = "Home"
    VEHICLE = "Vehicle"
    COMMUNITY = "Community"


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class MobileUser(Base):
    __tablename__ = "mobile_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Verification Fields
    phone_otp_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    phone_otp_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    email_otp_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    email_otp_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Security PIN Fields
    hashed_normal_pin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_duress_pin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    has_setup_pins: Mapped[bool] = mapped_column(Boolean, default=False)

    # Onboarding & Profile Setup
    primary_use_case: Mapped[Optional[UseCaseEnum]] = mapped_column(
        SQLEnum(
            UseCaseEnum, 
            native_enum=False, 
            values_callable=lambda x: [e.value for e in x]
        ), 
        nullable=True
    )
    account_setup_step: Mapped[int] = mapped_column(Integer, default=0)
    is_onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Subscription Management
    current_plan: Mapped[SubscriptionTier] = mapped_column(
        SQLEnum(
            SubscriptionTier,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=SubscriptionTier.FREE,
        nullable=False
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Permissions & Push Notifications
    location_permission_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    push_notifications_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    background_activity_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    fcm_device_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ORM Relationships
    emergency_contacts: Mapped[List["EmergencyContact"]] = sqlalchemy_relationship(
        "EmergencyContact", back_populates="user", cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = sqlalchemy_relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
    )


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mobile_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    relationship_type: Mapped[str] = mapped_column("relationship", String(50), nullable=False)  # Map database column 'relationship' to attribute 'relationship_type' to prevent variable shadowing
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship back to MobileUser
    user: Mapped["MobileUser"] = sqlalchemy_relationship("MobileUser", back_populates="emergency_contacts")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mobile_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    transaction_ref: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    plan_name: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(
            TransactionStatus,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=TransactionStatus.PENDING,
        nullable=False
    )
    checkout_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship back to MobileUser
    user: Mapped["MobileUser"] = sqlalchemy_relationship("MobileUser", back_populates="transactions")