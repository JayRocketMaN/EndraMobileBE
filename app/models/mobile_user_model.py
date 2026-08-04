import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class UseCaseEnum(str, enum.Enum):
    PERSONAL = "Myself"
    FAMILY = "Family"
    BUSINESS = "Business"
    PROPERTY = "Property"
    HOME = "Home"
    VEHICLE = "Vehicle"
    COMMUNITY = "Community"


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

    # Security PIN Fields (Stored as secure hashes)
    hashed_normal_pin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_duress_pin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    has_setup_pins: Mapped[bool] = mapped_column(Boolean, default=False)

    # Onboarding & Profile Setup Fields
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

    # App Permissions & Device Notification Fields
    location_permission_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    push_notifications_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    background_activity_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    fcm_device_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mobile_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    relationship: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., Mother, Father, Spouse, Friend
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)