import httpx
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.models.mobile_user_model import MobileUser, SubscriptionTier, Transaction
from app.schemas.mobile_user_schema import (
    InitiatePaymentRequestSchema,
    InitiatePaymentResponseSchema,
    PlanUpgradeResponseSchema,
    SelectPlanRequestSchema,
    UserSubscriptionStatusResponseSchema,
    VerifyPaymentResponseSchema
)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

# Pricing mapping in Kobo (₦1 = 100 kobo)
PLAN_PRICES = {
    SubscriptionTier.BASIC: 499900,   # ₦4,999.00
    SubscriptionTier.PREMIUM: 1299900 # ₦12,999.00
}




# ==========================================
# Endpoints
# ==========================================

@router.get("/status/{user_id}", response_model=UserSubscriptionStatusResponseSchema)
async def get_user_subscription_status(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    query = select(MobileUser).where(MobileUser.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    now = datetime.utcnow()
    is_trial_active = bool(user.trial_ends_at and user.trial_ends_at > now)

    return UserSubscriptionStatusResponseSchema(
    user_id=user.id,
    current_tier=user.current_plan,
    is_trial_active=is_trial_active,
    trial_ends_at=user.trial_ends_at,
    subscription_expires_at=user.subscription_expires_at
)

@router.post("/upgrade-plan", response_model=PlanUpgradeResponseSchema)
async def upgrade_user_plan(
    payload: SelectPlanRequestSchema,
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

    if user.current_plan == payload.target_tier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User is already on the {payload.target_tier.value.title()} plan."
        )

    now = datetime.utcnow()

    # 1. Immediate Downgrade to Free
    if payload.target_tier == SubscriptionTier.FREE:
        user.current_plan = SubscriptionTier.FREE
        user.trial_ends_at = None
        user.subscription_expires_at = None
        await db.commit()
        return PlanUpgradeResponseSchema(
            message="Account plan set to Free tier.",
            success=True,
            requires_payment=False
        )

    # 2. Start 14-Day Free Trial (No Payment Required)
    if payload.start_trial and not user.trial_ends_at:
        user.current_plan = payload.target_tier
        user.trial_ends_at = now + timedelta(days=14)
        user.subscription_expires_at = user.trial_ends_at
        await db.commit()
        return PlanUpgradeResponseSchema(
            message=f"14-day free trial activated for {payload.target_tier.value.title()} plan.",
            success=True,
            requires_payment=False
        )

    # 3. Paid Plan Upgrade via Squad Gateway
    amount_in_kobo = PLAN_PRICES.get(payload.target_tier)
    transaction_ref = f"endra_sub_{user.id}_{int(now.timestamp())}"

    squad_payload = {
        "email": user.email or f"user_{user.id}@endra.app",
        "amount": amount_in_kobo,
        "currency": "NGN",
        "initiate_type": "inline",
        "transaction_ref": transaction_ref,
        "callback_url": settings.SQUAD_CALLBACK_URL,
        "metadata": {
            "user_id": user.id,
            "target_tier": payload.target_tier.value
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.SQUAD_INITIATE_URL, 
            json=squad_payload, 
            headers=headers
        )
        res_data = response.json()

    if response.status_code == 200 and res_data.get("status") == 200:
        checkout_url = res_data["data"]["checkout_url"]
        return PlanUpgradeResponseSchema(
            message="Payment checkout initialized successfully.",
            success=True,
            requires_payment=True,
            checkout_url=checkout_url,
            transaction_ref=transaction_ref
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Failed to communicate with Squad payment gateway."
    )


@router.post("/squad-webhook")
async def squad_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    body = await request.json()
    event_data = body.get("data", {})

    if body.get("event") == "charge.successful" or event_data.get("transaction_status") == "success":
        metadata = event_data.get("metadata", {})
        user_id = metadata.get("user_id")
        target_tier_str = metadata.get("target_tier")

        if user_id and target_tier_str:
            query = select(MobileUser).where(MobileUser.id == int(user_id))
            result = await db.execute(query)
            user = result.scalar_one_or_none()

            if user:
                user.current_plan = SubscriptionTier(target_tier_str)
                user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
                await db.commit()

    return {"status": "success"}


# =====================================================================
# 1. INITIATE PAYMENT ENDPOINT
# =====================================================================
@router.post("/initiate-payment", response_model=InitiatePaymentResponseSchema)
async def initiate_payment(
    payload: InitiatePaymentRequestSchema,
    user_id: int,  # Replace with get_current_user dependency as needed
    db: AsyncSession = Depends(get_db)
):
    # Fetch User
    result = await db.execute(select(MobileUser).where(MobileUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate unique transaction reference
    transaction_ref = f"ENDR-{user.id}-{uuid.uuid4().hex[:8]}"
    amount_in_kobo = int(payload.amount * 100)

    squad_payload = {
        "email": user.email,
        "amount": amount_in_kobo,
        "currency": "NGN",
        "initiate_type": "inline",
        "transaction_ref": transaction_ref,
        "callback_url": settings.SQUAD_CALLBACK_URL,
        "metadata": {
            "user_id": user.id,
            "plan_name": payload.plan_name
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    # Call Squad GTCO API
    async with httpx.AsyncClient() as client:
        response = await client.post(settings.SQUAD_INITIATE_URL, json=squad_payload, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to initiate payment with Squad gateway"
        )

    response_data = response.json().get("data", {})
    checkout_url = response_data.get("checkout_url")

    # Store pending record in transactions table
    new_transaction = Transaction(
        user_id=user.id,
        transaction_ref=transaction_ref,
        plan_name=payload.plan_name,
        amount=payload.amount,
        status="pending",
        checkout_url=checkout_url
    )
    db.add(new_transaction)
    await db.commit()

    return InitiatePaymentResponseSchema(
        message="Payment initialized successfully.",
        success=True,
        checkout_url=checkout_url,
        transaction_ref=transaction_ref
    )


# =====================================================================
# 2. VERIFY PAYMENT ENDPOINT
# =====================================================================
@router.get("/verify-payment/{transaction_ref}", response_model=VerifyPaymentResponseSchema)
async def verify_payment(
    transaction_ref: str,
    db: AsyncSession = Depends(get_db)
):
    # Retrieve local transaction
    result = await db.execute(select(Transaction).where(Transaction.transaction_ref == transaction_ref))
    db_transaction = result.scalars().first()

    if not db_transaction:
        raise HTTPException(status_code=404, detail="Transaction reference not found")

    # Return quickly if already verified
    if db_transaction.status == "success":
        user_res = await db.execute(select(MobileUser).where(MobileUser.id == db_transaction.user_id))
        user = user_res.scalars().first()
        return VerifyPaymentResponseSchema(
            message="Payment already verified.",
            success=True,
            plan_name=db_transaction.plan_name,
            subscription_expires_at=user.subscription_expires_at
        )

    # Call Squad to verify status
    headers = {"Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}"}
    verify_endpoint = f"{settings.SQUAD_VERIFY_URL}/{transaction_ref}"

    async with httpx.AsyncClient() as client:
        response = await client.get(verify_endpoint, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid transaction reference or verification failed")

    res_body = response.json()
    transaction_status = res_body.get("data", {}).get("transaction_status")

    if transaction_status != "Success":
        db_transaction.status = "failed"
        await db.commit()
        raise HTTPException(status_code=400, detail="Payment was not successful")

    # Update payment status
    db_transaction.status = "success"

    # Upgrade User subscription (30 days from current date)
    user_res = await db.execute(select(MobileUser).where(MobileUser.id == db_transaction.user_id))
    user = user_res.scalars().first()

    user.current_plan = db_transaction.plan_name
    user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)

    await db.commit()

    return VerifyPaymentResponseSchema(
        message="Payment verified successfully. Subscription updated!",
        success=True,
        plan_name=user.current_plan,
        subscription_expires_at=user.subscription_expires_at
    )