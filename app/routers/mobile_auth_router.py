import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pwdlib import PasswordHash

from app.core.database import get_db
from app.models.mobile_user_model import MobileUser, EmergencyContact
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

# Development Toggle for OTP Verification
USE_HARDCODED_OTP = True
STATIC_TEST_OTP = "123456"


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

    # FIX: Offload CPU-heavy hashing to threadpool to avoid event loop stalls
    hashed_pwd = await run_in_threadpool(password_hash.hash, payload.password)

    new_user = MobileUser(
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        hashed_password=hashed_pwd,
        account_setup_step=1,  # Set next step after registration
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
    # Normalize empty strings to None
    email = payload.email.strip() if payload.email and payload.email.strip() else None
    phone_number = payload.phone_number.strip() if payload.phone_number and payload.phone_number.strip() else None

    if not email and not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide either an email or phone number to log in."
        )

    # Allow login via either email or phone number
    if email:
        query = select(MobileUser).where(MobileUser.email == email)
    else:
        query = select(MobileUser).where(MobileUser.phone_number == phone_number)

    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )

    # Offload CPU-heavy hash verification to threadpool
    is_valid_password = await run_in_threadpool(password_hash.verify, payload.password, user.hashed_password)
    if not is_valid_password:
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

    otp = STATIC_TEST_OTP if USE_HARDCODED_OTP else f"{random.randint(100000, 999999)}"
    
    user.phone_otp_code = otp
    user.phone_otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
    await db.commit()

    print(f"\n[PHONE OTP] Active Code for {payload.phone_number}: {otp}\n")

    return OTPStatusResponseSchema(
        message=f"Phone OTP sent successfully. (Dev OTP: {otp})",
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

    is_dev_otp = USE_HARDCODED_OTP and payload.otp_code == STATIC_TEST_OTP
    is_db_otp = user.phone_otp_code and user.phone_otp_code == payload.otp_code

    if not (is_dev_otp or is_db_otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code."
        )

    if not is_dev_otp:
        if user.phone_otp_expires_at and datetime.utcnow() > user.phone_otp_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP code has expired. Please request a new one."
            )

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

    otp = STATIC_TEST_OTP if USE_HARDCODED_OTP else f"{random.randint(100000, 999999)}"
    
    user.email_otp_code = otp
    user.email_otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
    await db.commit()

    print(f"\n[EMAIL OTP] Active Code for {payload.email}: {otp}\n")

    return OTPStatusResponseSchema(
        message=f"Email verification token sent successfully. (Dev OTP: {otp})",
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

    is_dev_otp = USE_HARDCODED_OTP and payload.otp_code == STATIC_TEST_OTP
    is_db_otp = user.email_otp_code and user.email_otp_code == payload.otp_code

    if not (is_dev_otp or is_db_otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code."
        )

    if not is_dev_otp:
        if user.email_otp_expires_at and datetime.utcnow() > user.email_otp_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired. Please request a new one."
            )

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

    # FIX: Offload PIN hashing to threadpool
    user.hashed_normal_pin = await run_in_threadpool(password_hash.hash, payload.normal_pin)
    user.hashed_duress_pin = await run_in_threadpool(password_hash.hash, payload.duress_pin)
    user.has_setup_pins = True

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
    query = select(MobileUser).where(MobileUser.id == payload.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not user.hashed_normal_pin or not user.hashed_duress_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User PINs are not configured."
        )

    # FIX: Offload PIN verification to threadpool
    is_normal = await run_in_threadpool(password_hash.verify, payload.pin_entered, user.hashed_normal_pin)
    if is_normal:
        return ValidateSOSPinResponseSchema(
            status="verified_normal_pin",
            is_duress=False
        )

    is_duress = await run_in_threadpool(password_hash.verify, payload.pin_entered, user.hashed_duress_pin)
    if is_duress:
        return ValidateSOSPinResponseSchema(
            status="verified_duress_pin",
            is_duress=True
        )

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
async def add_emergency_contact(
    contact: CreateEmergencyContactSchema,
    db: AsyncSession = Depends(get_db)
):
    new_contact = EmergencyContact(
        user_id=contact.user_id,
        full_name=contact.full_name,
        relationship=contact.relationship,
        phone_number=contact.phone_number,
    )

    db.add(new_contact)
    await db.commit()
    await db.refresh(new_contact)

    return new_contact


@router.post("/update-setup-step", response_model=MobileUserResponseSchema)
async def update_account_setup_step(
    payload: UpdateAccountSetupStepSchema,
    db: AsyncSession = Depends(get_db)
):
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