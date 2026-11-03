from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.mobile_user_model import EmergencyDirectory, EmergencyContact, MobileUser
from app.schemas.mobile_user_schema import SOSContactsResponseSchema, EmergencyContactItem
from app.core.security import get_current_user

router = APIRouter(prefix="/api/v1/sos", tags=["SOS Emergency"])

@router.get("/contacts", response_model=SOSContactsResponseSchema)
async def get_sos_contacts(
    state: str = Query("Lagos State", description="State name for regional emergency directory lookups"),
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user)
):
    # 1. Fetch Federal/National and State Directory items from the database
    dir_result = await db.execute(
        select(EmergencyDirectory).where(
            (EmergencyDirectory.state_name == state) | (EmergencyDirectory.scope.in_(["federal", "national"]))
        )
    )
    directory_items = dir_result.scalars().all()

    national_contacts = []
    state_contacts = []

    # Categorize directory rows into National/Federal and State lists for frontend tabs
    for item in directory_items:
        contact_item = EmergencyContactItem(
            name=item.title,             # Mapped to model's 'title' field
            phone_number=item.primary_number,  # Mapped to model's 'primary_number' field
            relation=getattr(item, "category", "Emergency Agency"),
            source=item.scope
        )
        if item.scope in ["federal", "national"]:
            national_contacts.append(contact_item)
        else:
            state_contacts.append(contact_item)

    # Fallback default national emergency (e.g., 112) if none exist in DB yet
    if not national_contacts:
        national_contacts.append(
            EmergencyContactItem(
                name="National Emergency Helpline",
                phone_number="112",
                relation="Emergency",
                source="default"
            )
        )

    # 2. Fetch User's Self-Added Personal Emergency Contacts from Database
    user_contacts_result = await db.execute(
        select(EmergencyContact).where(EmergencyContact.user_id == current_user.id)
    )
    db_contacts = user_contacts_result.scalars().all()
    
    personal_contacts = [
        EmergencyContactItem(
            name=c.full_name,
            phone_number=c.phone_number,
            relation=c.relation,
            source="personal"
        ) for c in db_contacts
    ]
    
    # 3. Return structured response for all frontend tabs
    return SOSContactsResponseSchema(
        national_emergency=national_contacts,
        state_emergency=state_contacts,
        personal_emergency_contacts=personal_contacts
    )








from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.mobile_user_model import MobileUser, EmergencyContact
from app.models.mobile_user_model import SOSEvent  # Ensure this is imported from your models
from app.schemas.mobile_user_schema import SOSTriggerRequest, LocationUpdateSchema
from app.core.security import get_current_user
from app.services.sms_service import send_sos_sms

router = APIRouter(prefix="/api/v1/sos", tags=["SOS Emergency"])

@router.post("/trigger")
async def trigger_sos_alert(
    payload: SOSTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user)
):
    # 1. Log the active SOS Event in the database with current coordinates
    sos_event = SOSEvent(
        user_id=current_user.id,
        alert_type=payload.alert_type,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_active=True
    )
    db.add(sos_event)
    await db.commit()
    await db.refresh(sos_event)

    # 2. Generate Live Location Tracking Link
    # (Points to your frontend live tracker view or a dedicated tracking map page)
    tracking_link = f"https://app.endra.security/track/live?event_id={sos_event.id}&user={current_user.id}"

    # 3. Fetch user's saved personal emergency contacts
    contacts_result = await db.execute(
        select(EmergencyContact).where(EmergencyContact.user_id == current_user.id)
    )
    personal_contacts = contacts_result.scalars().all()

    # 4. Construct emergency alert text message
    user_name = current_user.full_name or "A user"
    alert_message = (
        f"EMERGENCY ALERT: {user_name} has triggered an {payload.alert_type.upper()} alert! "
        f"They need immediate assistance. Track their live location here: {tracking_link}"
    )

    # 5. Loop through personal emergency contacts and dispatch SMS
    sms_dispatch_count = 0
    for contact in personal_contacts:
        if contact.phone_number:
            await send_sos_sms(contact.phone_number, alert_message)
            sms_dispatch_count += 1

    # 6. Notify ENDRA Operators Dashboard (via WebSockets or event logs)
    # TODO: Broadcast event_id to connected operator websocket channels

    return {
        "status": "success",
        "message": "SOS alert triggered successfully. Personal contacts notified.",
        "event_id": sos_event.id,
        "notified_contacts_count": sms_dispatch_count,
        "tracking_link": tracking_link
    }

@router.patch("/location/{event_id}")
async def update_live_location(
    event_id: int,
    payload: LocationUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user)
):
    """Continuously updates the live GPS coordinates of an active emergency event for real-time tracking."""
    result = await db.execute(
        select(SOSEvent).where(SOSEvent.id == event_id, SOSEvent.user_id == current_user.id)
    )
    sos_event = result.scalars().first()

    if not sos_event or not sos_event.is_active:
        raise HTTPException(status_code=404, detail="Active SOS event not found.")

    sos_event.latitude = payload.latitude
    sos_event.longitude = payload.longitude
    await db.commit()

    return {"status": "success", "message": "Live location updated successfully."}