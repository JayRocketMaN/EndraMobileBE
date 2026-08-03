from datetime import datetime
from enum import Enum
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


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

# Schema matching user_model.dart JSON output
class MobileUserLoginSchema(BaseModel):
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "user@example.com"})
    phone_number: Optional[str] = Field(None, json_schema_extra={"example": "+2348000000000"})
    password: str = Field(..., json_schema_extra={"example": "yourpassword"})


# Schema matching the Create Account screen form inputs
class MobileUserRegisterSchema(BaseModel):
    full_name: Optional[str] = Field(None, json_schema_extra={"example": "Adaeze Okonkwo"})
    phone_number: str = Field(..., json_schema_extra={"example": "+2348000000000"})
    password: str = Field(..., json_schema_extra={"example": "yourpassword"})
    email: Optional[EmailStr] = Field(None, json_schema_extra={"example": "user@example.com"})


# ==========================================
# Phone OTP Schemas
# ==========================================

# Request payload to send Phone OTP
class SendPhoneOTPRequestSchema(BaseModel):
    phone_number: str = Field(..., json_schema_extra={"example": "+2348000000000"})


# Request payload when submitting 6-digit code for Phone Verification
class VerifyPhoneOTPRequestSchema(BaseModel):
    phone_number: str = Field(..., json_schema_extra={"example": "+2348000000000"})
    otp_code: str = Field(..., min_length=6, max_length=6, json_schema_extra={"example": "123456"})


# ==========================================
# Email OTP Schemas
# ==========================================

# Request payload to send Email OTP
class SendEmailOTPRequestSchema(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "user@example.com"})


# Request payload when submitting 6-digit code for Email Verification
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

# Payload for UseCaseSelectionPage step (Step Index 2)
class SelectUseCaseRequestSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    primary_use_case: UseCaseEnum = Field(..., description="Selected protection use case")


# Payload for EmergencyContactPage step (Step Index 3)
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


# Payload for App Permissions Page (Step Index 4)
class UpdateAppPermissionsSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    location_permission_granted: bool = Field(False, json_schema_extra={"example": True})
    push_notifications_granted: bool = Field(False, json_schema_extra={"example": True})
    background_activity_granted: bool = Field(False, json_schema_extra={"example": True})
    fcm_device_token: Optional[str] = Field(None, json_schema_extra={"example": "fcm_token_xyz_123"})


# Payload to complete onboarding entirely
class CompleteOnboardingSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})


# Generic step update schema for AccountSetupScreen wizard
class UpdateAccountSetupStepSchema(BaseModel):
    user_id: int = Field(..., json_schema_extra={"example": 1})
    step: int = Field(..., ge=0, le=4, json_schema_extra={"example": 4})


# ==========================================
# Response Schemas
# ==========================================

# Generic Status Response for OTP operations
class OTPStatusResponseSchema(BaseModel):
    message: str
    success: bool


# Main Response schema sent back to Flutter
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