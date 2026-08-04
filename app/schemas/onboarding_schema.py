"""from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ProtectionUseCase(str, Enum):
    MYSELF = "Myself"
    FAMILY = "Family"
    HOME = "Home"
    BUSINESS = "Business"
    VEHICLE = "Vehicle"
    COMMUNITY = "Community"


class ContactRelationship(str, Enum):
    MOTHER = "Mother"
    FATHER = "Father"
    SIBLING = "Sibling"
    SPOUSE = "Spouse"
    FRIEND = "Friend"
    COLLEAGUE = "Colleague"


class PropertyType(str, Enum):
    RESIDENTIAL = "Residential"
    COMMERCIAL = "Commercial"
    RETAIL = "Retail"
    INDUSTRIAL = "Industrial"


class CreateAccountRequest(BaseModel):
    full_name: str = Field(..., example="Adaeze Okonkwo")
    phone_number: str = Field(..., example="+2348000000000")
    password: str = Field(..., min_length=8)


class OTPVerificationRequest(BaseModel):
    phone_number: str
    otp_code: str = Field(..., min_length=6, max_length=6, example="111111")


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class SetSecurityPINRequest(BaseModel):
    normal_pin: str = Field(..., min_length=6, max_length=6, example="111111")
    duress_pin: Optional[str] = Field(None, min_length=6, max_length=6, example="222222")


class ProtectionSelectionRequest(BaseModel):
    primary_use_case: ProtectionUseCase


class EmergencyContact(BaseModel):
    id: Optional[str] = None
    full_name: str = Field(..., example="Ade Obi")
    relationship: ContactRelationship
    phone_number: str = Field(..., example="+2340920123456")
    is_verified: bool = True


class AppPermissionsState(BaseModel):
    location_access: bool = True
    push_notifications: bool = True
    background_activity: bool = True


class AddPropertyRequest(BaseModel):
    property_name: str = Field(..., example="My Home")
    full_address: str = Field(..., example="12 Adeola Way, Lekki Phase 1")
    property_type: PropertyType = PropertyType.RESIDENTIAL
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PropertyResponse(AddPropertyRequest):
    property_id: str"""