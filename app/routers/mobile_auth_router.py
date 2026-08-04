import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pwdlib import PasswordHash

from app.core.database import get_db
from app.models.mobile_user_model import MobileUser
from app.schemas.mobile_user_schema import (
    MobileUserRegisterSchema,
    MobileUserLoginSchema,
    MobileUserResponseSchema,
    SendPhoneOTPRequestSchema,
    VerifyPhoneOTPRequestSchema,
    SendEmailOTPRequestSchema,
    VerifyEmailOTPRequestSchema,
    OTPStatusResponseSchema,
    SetUserPinsRequestSchema,
    ValidateSOSPinRequestSchema,
    ValidateSOSPinResponseSchema,
    SelectUseCaseRequestSchema,
    CreateEmergencyContactSchema,
    EmergencyContactResponseSchema,
    UpdateAccountSetupStepSchema,
    UpdateAppPermissionsSchema,
    CompleteOnboardingSchema,
)

router = APIRouter(prefix="/api/v1/mobile/auth", tags=["Mobile Auth"])

# Initialize pwdlib with recommended password hashing settings
password_hash = PasswordHash.recommended()


# ==========================================
# Registration & Authentication
# ==========================================

@router.post("/register", response_model=MobileUserResponseSchema, status_code=status.HTTP_201_CREATED)
async def register_mobile_user(
    payload: MobileUserRegisterSchema,
    db: AsyncSession = Depends(get_db)
):
    # Check if phone number already registered
    query = select(MobileUser).where(MobileUser.phone_number == payload.phone_number)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mobile user with this phone number already exists."
        )

    # Check if email already registered (if email was provided)
    if payload.email:
        email_query = select(MobileUser).where(MobileUser.email == payload.email)
        email_result = await db.execute(email_query)
        if email_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mobile user with this email already exists."
            )

    # Hash password securely using pwdlib
    hashed_pwd = password_hash.hash(payload.password)

    new_user = MobileUser(
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        hashed_password=hashed_pwd,
        account_setup_step=1,  # Set next step after registration (PinSetupPage)
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=MobileUserResponseSchema)
async def login_mobile_user(
    payload: MobileUserLoginSchema,
    db: AsyncSession = Depends(get_db)
):
    if not payload.email and not payload.phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide either an email or phone number to log in."
        )

    # Allow login via either email or phone number
    if payload.email:
        query = select(MobileUser).where(MobileUser.email == payload.email)
    else:
        query = select(MobileUser).where(MobileUser.phone_number == payload.phone_number)

    result = await db.execute(query)
    user = result.scalar_one_or_none()

    # Verify password hash
    if not user or not password_hash.verify(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )

    return user


# ==========================================
# Phone OTP Endpoints
# ==========================================

@router.post("/send-phone-otp", response_model=OTPStatusResponseSchema)
async def send_phone_otp(
    payload: SendPhoneOTPRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    query = select(MobileUser).where(MobileUser.phone_number == payload.phone_number)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this phone number not found."
        )

    # Generate 6-digit OTP code
    otp = f"{random.randint(100000, 999999)}"
    
    user.phone_otp_code = otp
    user.phone_otp_expires_at = datetime.utcnow() + timedelta(minutes=5)
    await db.commit()

    # TODO: Trigger SMS Provider (e.g. Twilio, Termii, Africa's Talking)

    return OTPStatusResponseSchema(
        message="Phone OTP sent successfully.",
        success=True
    )


@router.post("/verify-phone-otp", response_model=OTPStatusResponseSchema)
async def verify_phone_otp(
    payload: VerifyPhoneOTPRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    query = select(MobileUser).where(MobileUser.phone_number == payload.phone_number)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    if not user.phone_otp_code or user.phone_otp_code != payload.otp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code."
        )

    if user.phone_otp_expires_at and datetime.utcnow() > user.phone_otp_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP code has expired. Please request a new one."
        )

    # Update verification status and clear token
    user.is_phone_verified = True
    user.phone_otp_code = None
    user.phone_otp_expires_at = None
    await db.commit()

    return OTPStatusResponseSchema(
        message="Phone number verified successfully.",
        success=True
    )


# ==========================================
# Email OTP Endpoints
# ==========================================

@router.post("/send-email-otp", response_model=OTPStatusResponseSchema)
async def send_email_otp(
    payload: SendEmailOTPRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    query = select(MobileUser).where(MobileUser.email == payload.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this email not found."
        )

    # Generate 6-digit OTP code
    otp = f"{random.randint(100000, 999999)}"
    
    user.email_otp_code = otp
    user.email_otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
    await db.commit()

    # TODO: Trigger Email Provider (e.g. FastMail, SendGrid, Amazon SES)

    return OTPStatusResponseSchema(
        message="Email verification token sent successfully.",
        success=True
    )


@router.post("/verify-email-otp", response_model=OTPStatusResponseSchema)
async def verify_email_otp(
    payload: VerifyEmailOTPRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    query = select(MobileUser).where(MobileUser.email == payload.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    if not user.email_otp_code or user.email_otp_code != payload.otp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code."
        )

    if user.email_otp_expires_at and datetime.utcnow() > user.email_otp_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new one."
        )

    # Update verification status and clear token
    user.is_email_verified = True
    user.email_otp_code = None
    user.email_otp_expires_at = None
    await db.commit()

    return OTPStatusResponseSchema(
        message="Email verified successfully.",
        success=True
    )


# ==========================================
# PIN Setup & SOS Verification Endpoints
# ==========================================

@router.post("/setup-pins", response_model=OTPStatusResponseSchema)
async def setup_user_pins(
    payload: SetUserPinsRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Saves and hashes both Normal and Duress security PINs for a user,
    and updates the onboarding setup step.
    """
    if payload.normal_pin == payload.duress_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Normal PIN and Duress PIN cannot be the same."
        )

    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Hash both PINs securely
    user.hashed_normal_pin = password_hash.hash(payload.normal_pin)
    user.hashed_duress_pin = password_hash.hash(payload.duress_pin)
    user.has_setup_pins = True

    # Advance setup step to Step 2 (UseCaseSelectionPage)
    if user.account_setup_step < 2:
        user.account_setup_step = 2

    await db.commit()

    return OTPStatusResponseSchema(
        message="Security PINs configured successfully.",
        success=True
    )


@router.post("/verify-sos-pin", response_model=ValidateSOSPinResponseSchema)
async def verify_sos_cancellation_pin(
    payload: ValidateSOSPinRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Validates an entered PIN during SOS alert cancellation.
    Returns whether the cancellation is normal or triggered under duress.
    """
    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not user.hashed_normal_pin or not user.hashed_duress_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User PINs are not configured."
        )

    # 1. Check Normal PIN
    if password_hash.verify(payload.pin_entered, user.hashed_normal_pin):
        return ValidateSOSPinResponseSchema(
            status="normal_cancellation",
            is_duress=False
        )

    # 2. Check Duress PIN
    if password_hash.verify(payload.pin_entered, user.hashed_duress_pin):
        return ValidateSOSPinResponseSchema(
            status="duress_cancellation",
            is_duress=True
        )

    # 3. Invalid PIN
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid PIN code."
    )


# ==========================================
# Account Setup & Onboarding Endpoints
# ==========================================

@router.post("/select-use-case", response_model=MobileUserResponseSchema)
async def select_primary_use_case(
    payload: SelectUseCaseRequestSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Saves user's selected primary protection use case (Step Index 2)
    and advances setup progress to Step Index 3 (EmergencyContactPage).
    """
    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    user.primary_use_case = payload.primary_use_case
    if user.account_setup_step < 3:
        user.account_setup_step = 3

    await db.commit()
    await db.refresh(user)

    return user


@router.post("/emergency-contacts", response_model=EmergencyContactResponseSchema)
async def add_emergency_contact(contact: CreateEmergencyContactSchema):
    return EmergencyContactResponseSchema(
        id="cnt_001",
        full_name=contact.full_name,
        relationship=contact.relationship,
        phone_number=contact.phone_number,
        is_verified=True
    )



@router.post("/update-setup-step", response_model=MobileUserResponseSchema)
async def update_account_setup_step(
    payload: UpdateAccountSetupStepSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Directly updates the current page index for the wizard flow.
    If set to step 4 or beyond, marks onboarding as completed.
    """
    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    user.account_setup_step = payload.step
    if payload.step >= 4:
        user.is_onboarding_completed = True

    await db.commit()
    await db.refresh(user)

    return user


@router.post("/update-permissions", response_model=MobileUserResponseSchema)
async def update_app_permissions(
    payload: UpdateAppPermissionsSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Updates granted app permission flags and FCM device token for push notifications.
    """
    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    user.location_permission_granted = payload.location_permission_granted
    user.push_notifications_granted = payload.push_notifications_granted
    user.background_activity_granted = payload.background_activity_granted

    if payload.fcm_device_token:
        user.fcm_device_token = payload.fcm_device_token

    await db.commit()
    await db.refresh(user)

    return user


@router.post("/complete-onboarding", response_model=MobileUserResponseSchema)
async def complete_onboarding(
    payload: CompleteOnboardingSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Marks the onboarding process as fully completed (step 4), routing the
    mobile application directly to the main dashboard.
    """
    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    user.is_onboarding_completed = True
    user.account_setup_step = 4

    await db.commit()
    await db.refresh(user)

    return user