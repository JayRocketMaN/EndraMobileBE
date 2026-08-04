from datetime import datetime
from enum import Enum
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
import re

# ==========================================
# Enums
# ==========================================

class UseCaseEnum(str, Enum):
    PERSONAL = "personal"
    FAMILY = "family"
    BUSINESS = "business"
    PROPERTY = "property"


# ==========================================
# Authentication Schemas
# ==========================================

# Schema matching user_model.dart JSON output with dual identifier field validation
class MobileUserLoginSchema(BaseModel):
    identifier: Optional[str] = Field(None, json_schema_extra={"example": "user@example.com or +2348000000000"})
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "user@example.com"})
    phone_number: Optional[str] = Field(None, json_schema_extra={"example": "+2348000000000"})
    password: str = Field(..., json_schema_extra={"example": "yourpassword"})

    @field_validator("identifier")
    @classmethod
    def validate_login_identifier(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        clean_value = value.strip()
        is_email = re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", clean_value)
        is_phone = re.match(r"^\+?[1-9]\d{1,14}$", clean_value)
        if not is_email and not is_phone:
            raise ValueError("Identifier must be a valid email address or international format phone number.")
        return clean_value


# Schema matching the Create Account screen form inputs
class MobileUserRegisterSchema(BaseModel):
    full_name: Optional[str] = Field(None, json_schema_extra={"example": "Adaeze Okonkwo"})
    phone_number: str = Field(..., json_schema_extra={"example": "+2348000000000"})
    password: str = Field(..., json_schema_extra={"example": "yourpassword"})
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "user@example.com"})


# ==========================================
# Universal / Split OTP Verification Schemas
# ==========================================

# Unified payload for single input dispatch components
class SendUniversalOTPRequestSchema(BaseModel):
    identifier: str = Field(..., json_schema_extra={"example": "user@example.com or +2348000000000"})

    @field_validator("identifier")
    @classmethod
    def validate_universal_identifier(cls, value: str) -> str:
        clean_value = value.strip()
        is_email = re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", clean_value)
        is_phone = re.match(r"^\+?[1-9]\d{1,14}$", clean_value)
        if not is_email and not is_phone:
            raise ValueError("Universal destination target must be a valid email address or phone number string.")
        return clean_value


# Universal submission validator matching unified form layouts
class VerifyUniversalOTPRequestSchema(BaseModel):
    identifier: str = Field(..., json_schema_extra={"example": "user@example.com or +2348000000000"})
    otp_code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})


# ==========================================
# Legacy Phone OTP Schemas (Kept for Flutter Layout Safety)
# ==========================================

class SendPhoneOTPRequestSchema(BaseModel):
    phone_number: str = Field(..., json_schema_extra={"example": "+2348000000000"})


class VerifyPhoneOTPRequestSchema(BaseModel):
    phone_number: str = Field(..., json_schema_extra={"example": "+2348000000000"})
    otp_code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})


# ==========================================
# Legacy Email OTP Schemas (Kept for Flutter Layout Safety)
# ==========================================

class SendEmailOTPRequestSchema(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@example.com"})


class VerifyEmailOTPRequestSchema(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@example.com"})
    otp_code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})


# ==========================================
# PIN Setup & Verification Schemas
# ==========================================

class SetUserPinsRequestSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    normal_pin: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})
    duress_pin: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "654321"})


class ValidateSOSPinRequestSchema(BaseModel):
    user_id: int
    pin_entered: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})


class ValidateSOSPinResponseSchema(BaseModel):
    status: str  # "normal_cancellation" | "duress_cancellation" | "invalid"
    is_duress: bool


# ==========================================
# Account Setup & Onboarding Schemas
# ==========================================

class SelectUseCaseRequestSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    primary_use_case: UseCaseEnum = Field(..., description="Selected protection use case")


class CreateEmergencyContactSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    full_name: str = Field(..., json_schema_extra={"example": "Adaeze Obi"})
    relationship: str = Field(..., json_schema_extra={"example": "Mother"})
    phone_number: str = Field(..., json_schema_extra={"example": "+2348012345678"})


class EmergencyContactResponseSchema(BaseModel):
    id: int
    user_id: int
    full_name: str
    relationship: str
    phone_number: str
    created_at: datetime

    class Config:
        from_attributes = True


class EmergencyContactListResponseSchema(BaseModel):
    contacts: List[EmergencyContactResponseSchema]
    total: int


class UpdateAppPermissionsSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    location_permission_granted: bool = Field(False, json_schema_extra={"example": True})
    push_notifications_granted: bool = Field(False, json_schema_extra={"example": True})
    background_activity_granted: bool = Field(False, json_schema_extra={"example": True})
    fcm_device_token: Optional[str] = Field(None, json_schema_extra={"example": "fcm_token_xyz_123"})


class CompleteOnboardingSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})


class UpdateAccountSetupStepSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    step: int = Field(..., ge=0, le=4, json_schema_extra={"example": 4})


# ==========================================
# Response Schemas
# ==========================================

class OTPStatusResponseSchema(BaseModel):
    message: str
    success: bool


class MobileUserResponseSchema(BaseModel):
    id: int
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    is_phone_verified: bool = False
    is_email_verified: bool = False
    has_setup_pins: bool = False
    
    # Onboarding & Setup Fields
    primary_use_case: Optional[UseCaseEnum] = None
    account_setup_step: int = 0
    is_onboarding_completed: bool = False

    # App Permissions & Device Fields
    location_permission_granted: bool = False
    push_notifications_granted: bool = False
    background_activity_granted: bool = False
    fcm_device_token: Optional[str] = None

    is_active: bool = True

    class Config:
        from_attributes = True
