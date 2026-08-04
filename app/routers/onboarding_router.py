"""from fastapi import APIRouter, HTTPException, status
import app.schemas.onboarding_schema as schemas

router = APIRouter(prefix="/api/v1/onboarding", tags=["User Onboarding & Setup"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def create_account(request: schemas.CreateAccountRequest):
    return {
        "status": "otp_sent",
        "message": f"6-digit code sent to {request.phone_number}",
        "resend_in_seconds": 45
    }


@router.post("/verify-otp", response_model=schemas.AuthTokenResponse)
async def verify_otp(request: schemas.OTPVerificationRequest):
    if request.otp_code != "111111":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code."
        )
    return schemas.AuthTokenResponse(
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        user_id="user_usr_9021"
    )


@router.post("/set-pins")
async def set_security_pins(request: schemas.SetSecurityPINRequest):
    return {
        "status": "success",
        "normal_pin_set": True,
        "duress_pin_set": request.duress_pin is not None
    }


@router.post("/select-protection")
async def select_protection_use_case(request: schemas.ProtectionSelectionRequest):
    return {
        "status": "saved",
        "selected_use_case": request.primary_use_case
    }


@router.post("/emergency-contacts", response_model=schemas.EmergencyContactResponse)
async def add_emergency_contact(contact: schemas.CreateEmergencyContactRequest):
    return schemas.EmergencyContactResponse(
        id="cnt_001",
        full_name=contact.full_name,
        relationship=contact.relationship,
        phone_number=contact.phone_number,
        is_verified=True
    )


@router.post("/permissions")
async def sync_app_permissions(permissions: schemas.AppPermissionsState):
    return {
        "status": "synced",
        "all_granted": permissions.location_access and permissions.push_notifications and permissions.background_activity
    }


@router.post("/properties", response_model=schemas.PropertyResponse)
async def register_property(payload: schemas.AddPropertyRequest):
    return schemas.PropertyResponse(
        property_id="prop_lk_01",
        property_name=payload.property_name,
        full_address=payload.full_address,
        property_type=payload.property_type,
        latitude=6.4474,
        longitude=3.4723
    )"""