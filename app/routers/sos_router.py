from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.core.security import get_current_user, verify_password
from app.models.mobile_user_model import (
    EmergencyContact,
    EmergencyDirectory,
    MobileUser,
    SOSEvent,
)
from app.schemas.mobile_user_schema import (
    EmergencyContactItem,
    LocationUpdateSchema,
    SOSContactsResponseSchema,
    SOSTriggerRequest,
    SOSTriggerResponseSchema,
    SOSCancelRequestSchema,
    SOSCancelResponseSchema,
    SOSEventResponseSchema,
    SOSWebSocketBroadcastSchema,
    ValidateSOSPinResponseSchema,
)
from app.services.google_map_service import GoogleMapsService
from app.services.sms_service import SMSService
from fastapi.concurrency import run_in_threadpool
from app.core.security import get_current_user, password_hash

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sos", tags=["SOS Emergency"])


# ==========================================
# WebSocket Connection Manager for SOS Tracking
# ==========================================
class SOSConnectionManager:
    """Manages active WebSocket tracking sessions keyed by event_id."""
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, event_id: int, websocket: WebSocket):
        await websocket.accept()
        if event_id not in self.active_connections:
            self.active_connections[event_id] = []
        self.active_connections[event_id].append(websocket)

    def disconnect(self, event_id: int, websocket: WebSocket):
        if event_id in self.active_connections:
            if websocket in self.active_connections[event_id]:
                self.active_connections[event_id].remove(websocket)
            if not self.active_connections[event_id]:
                del self.active_connections[event_id]

    async def broadcast_to_event(self, event_id: int, message: dict):
        if event_id in self.active_connections:
            for connection in self.active_connections[event_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


sos_ws_manager = SOSConnectionManager()


# ==========================================
# 1. Get Regional & Personal SOS Contacts
# ==========================================
@router.get("/contacts", response_model=SOSContactsResponseSchema)
async def get_sos_contacts(
    state: str = Query(
        "Lagos State",
        description="State name for regional emergency directory lookups",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user),
):
    dir_result = await db.execute(
        select(EmergencyDirectory).where(
            (EmergencyDirectory.state_name == state)
            | (EmergencyDirectory.scope.in_(["federal", "national"]))
        )
    )
    directory_items = dir_result.scalars().all()

    national_contacts = []
    state_contacts = []

    for item in directory_items:
        contact_item = EmergencyContactItem(
            name=item.title,
            phone_number=item.primary_number,
            relation=getattr(item, "category", "Emergency Agency"),
            source=item.scope,
        )
        if item.scope in ["federal", "national"]:
            national_contacts.append(contact_item)
        else:
            state_contacts.append(contact_item)

    if not national_contacts:
        national_contacts.append(
            EmergencyContactItem(
                name="National Emergency Helpline",
                phone_number="112",
                relation="Emergency",
                source="default",
            )
        )

    user_contacts_result = await db.execute(
        select(EmergencyContact).where(
            EmergencyContact.user_id == current_user.id
        )
    )
    db_contacts = user_contacts_result.scalars().all()

    personal_contacts = [
        EmergencyContactItem(
            name=c.full_name,
            phone_number=c.phone_number,
            relation=c.relation,
            source="personal",
        )
        for c in db_contacts
    ]

    return SOSContactsResponseSchema(
        national_emergency=national_contacts,
        state_emergency=state_contacts,
        personal_emergency_contacts=personal_contacts,
    )


# ==========================================
# 2. Trigger Active SOS Emergency Alert
# ==========================================
@router.post("/trigger", response_model=SOSTriggerResponseSchema)
async def trigger_sos_alert(
    payload: SOSTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user),
):
    sos_event = SOSEvent(
        user_id=current_user.id,
        alert_type=payload.alert_type,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_active=True,
    )
    db.add(sos_event)
    await db.commit()
    await db.refresh(sos_event)

    street_address = await GoogleMapsService.reverse_geocode(
        payload.latitude, payload.longitude
    )
    
    if not street_address or street_address.strip() == "":
        street_address = f"Latitude: {payload.latitude}, Longitude: {payload.longitude}"

    tracking_link = f"https://app.endra.security/track/live?event_id={sos_event.id}&user={current_user.id}"

    user_name = current_user.full_name or "A user"

    contacts_result = await db.execute(
        select(EmergencyContact).where(
            EmergencyContact.user_id == current_user.id
        )
    )
    personal_contacts = contacts_result.scalars().all()

    sms_dispatch_count = 0
    for contact in personal_contacts:
        if contact.phone_number:
            await SMSService.send_sos_alert_sms(
                to_phone_number=contact.phone_number,
                user_name=user_name,
                location=street_address,
                tracking_link=tracking_link
            )
            sms_dispatch_count += 1

    return {
        "status": "success",
        "message": "SOS alert triggered successfully.",
        "event_id": sos_event.id,
        "resolved_address": street_address,
        "notified_contacts_count": sms_dispatch_count,
        "tracking_link": tracking_link,
    }


# ==========================================
# 3. Update Live GPS Coordinates & WS Broadcast
# ==========================================
@router.patch("/location/{event_id}")
async def update_live_location(
    event_id: int,
    payload: LocationUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user),
):
    result = await db.execute(
        select(SOSEvent).where(
            SOSEvent.id == event_id, SOSEvent.user_id == current_user.id
        )
    )
    sos_event = result.scalars().first()

    if not sos_event or not sos_event.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active SOS event not found.",
        )

    sos_event.latitude = payload.latitude
    sos_event.longitude = payload.longitude
    await db.commit()

    await sos_ws_manager.broadcast_to_event(
        event_id,
        {
            "event_type": "location_update",
            "event_id": event_id,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "status": "active",
        },
    )

    return {
        "status": "success",
        "message": "Live location updated and broadcasted.",
    }


# ==========================================
# 4. WebSocket Endpoint for Tracking Maps
# ==========================================
@router.websocket("/ws/{event_id}")
async def sos_tracker_websocket(websocket: WebSocket, event_id: int):
    await sos_ws_manager.connect(event_id, websocket)
    
    await websocket.send_json({
        "event_type": "connected",
        "event_id": event_id,
        "message": f"Connected to live emergency tracking channel for event {event_id}"
    })

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        sos_ws_manager.disconnect(event_id, websocket)
    except Exception:
        sos_ws_manager.disconnect(event_id, websocket)


# ==========================================
# 5. Cancel SOS Trigger via Security PIN
# ==========================================
@router.post("/cancel/{event_id}", response_model=SOSCancelResponseSchema)
async def cancel_sos_alert(
    event_id: int,
    payload: SOSCancelRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_current_user),
):
    if not current_user.hashed_normal_pin or not current_user.hashed_duress_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User security PINs are not configured.",
        )

    # Verify normal PIN first
    is_normal = await run_in_threadpool(
        password_hash.verify, payload.pin, current_user.hashed_normal_pin
    )
    
    is_duress = False
    if not is_normal:
        is_duress = await run_in_threadpool(
            password_hash.verify, payload.pin, current_user.hashed_duress_pin
        )

    if not is_normal and not is_duress:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN code.",
        )

    result = await db.execute(
        select(SOSEvent).where(
            SOSEvent.id == event_id,
            SOSEvent.user_id == current_user.id,
            SOSEvent.is_active == True,
        )
    )
    sos_event = result.scalars().first()

    if not sos_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active SOS event not found or already closed.",
        )

    tracking_link = f"https://app.endra.security/track/live?event_id={sos_event.id}&user={current_user.id}"

    if is_normal:
        # Standard cancellation flow
        sos_event.is_active = False
        await db.commit()

        await sos_ws_manager.broadcast_to_event(
            event_id,
            {
                "event_type": "sos_cancelled",
                "event_id": event_id,
                "status": "cancelled",
                "message": "Emergency event has been safely cancelled by the user.",
            },
        )
        return SOSCancelResponseSchema(
            status="success",
            message="SOS alert cancelled successfully.",
            is_duress=False,
        )

    else:
        # Covert duress flow
        sos_event.is_under_duress = True 
        await db.commit()

        # Reverse geocode physical location coordinates
        readable_address = await GoogleMapsService.reverse_geocode(
            sos_event.latitude, sos_event.longitude
        )
        if not readable_address or readable_address.strip() == "":
            readable_address = f"Latitude: {sos_event.latitude}, Longitude: {sos_event.longitude}"

        # Combine Duress Warning Header with the Human-Readable Address
        duress_location = f"Covert Duress Location ({readable_address})"

        contacts_result = await db.execute(
            select(EmergencyContact).where(EmergencyContact.user_id == current_user.id)
        )
        for contact in contacts_result.scalars().all():
            if contact.phone_number:
                await SMSService.send_sos_alert_sms(
                    to_phone_number=contact.phone_number,
                    user_name=current_user.full_name or "A user",
                    location=duress_location,  # ✅ Emphasizes duress AND shows street address
                    tracking_link=tracking_link,
                )

        await sos_ws_manager.broadcast_to_event(
            event_id,
            {
                "event_type": "duress_cancellation_intercepted",
                "event_id": event_id,
                "status": "covert_tracking_active",
                "message": "WARNING: User entered duress PIN. Cancellation is a facade.",
                "is_under_duress": True,
            },
        )

        return SOSCancelResponseSchema(
            status="success",
            message="SOS alert cancelled successfully.",
            is_duress=True,
        )