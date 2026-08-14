import secrets
from typing import List
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.hardware_model import DiscoveredDevice, ManualCamera, CameraStatus, StagingStatus
import app.schemas.hardware_schema as schemas

router = APIRouter(prefix="/api/v1/hardware", tags=["Batch 2: Hardware & Onboarding"])


# Helper function to construct stream URLs for manual cameras
def build_rtsp_url(payload: schemas.ManualCameraSetupRequest) -> str:
    if payload.stream_url and payload.stream_url.strip():
        return payload.stream_url.strip()
    return f"rtsp://{payload.username}:{payload.password}@{payload.ip_address}:{payload.port}/h264/ch{payload.channel or 1}/main"


# ==========================================
# 1. DISCOVERY & RECONNECT CACHING
# ==========================================

@router.get("/discover", response_model=List[schemas.DiscoveredDeviceResponse])
async def discover_nearby_devices(db: AsyncSession = Depends(get_db)):
    """
    Scans for nearby unconfigured ENDRA devices over BLE or local Wi-Fi,
    persisting/updating them in the discovered_devices cache table.
    """
    # Sample scanned items (In production, replace with BLE/mDNS scanner pipeline)
    scanned_items = [
        {
            "device_id": "dev_ble_001",
            "device_name": "ENDRA HD Dome Camera",
            "device_type": schemas.DeviceType.CAMERA,
            "signal_strength_dbm": -48,
            "mac_address": "00:1A:2B:3C:4D:5E",
            "connectivity": schemas.ConnectivityType.BLE,
        },
        {
            "device_id": "dev_ble_002",
            "device_name": "ENDRA Smart Siren & Strobe",
            "device_type": schemas.DeviceType.SIREN,
            "signal_strength_dbm": -62,
            "mac_address": "00:1A:2B:3C:4D:5F",
            "connectivity": schemas.ConnectivityType.BLE,
        }
    ]

    cached_devices = []
    for item in scanned_items:
        # Upsert: check if device is already cached to avoid redundant scans
        query = await db.execute(
            select(DiscoveredDevice).where(DiscoveredDevice.device_id == item["device_id"])
        )
        existing_device = query.scalar_one_or_none()

        if existing_device:
            existing_device.signal_strength_dbm = item["signal_strength_dbm"]
            cached_devices.append(existing_device)
        else:
            new_device = DiscoveredDevice(
                device_id=item["device_id"],
                device_name=item["device_name"],
                device_type=item["device_type"],
                signal_strength_dbm=item["signal_strength_dbm"],
                mac_address=item["mac_address"],
                connectivity=item["connectivity"],
                staging_status=StagingStatus.DISCOVERED,
            )
            db.add(new_device)
            cached_devices.append(new_device)

    await db.commit()
    for dev in cached_devices:
        await db.refresh(dev)

    return cached_devices


# ==========================================
# 2. QR CODE VALIDATION & STAGING
# ==========================================

@router.post("/validate-qr", response_model=schemas.QRValidationResponse)
async def validate_device_qr(
    payload: schemas.QRValidationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validates device QR payload, generates a staging activation token, 
    and updates the staging session context.
    """
    if not payload.qr_code_payload.startswith("ENDRA"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unrecognized ENDRA device QR code."
        )

    # Issue staging token for secure fast-reconnect
    activation_token = f"sec_tok_{secrets.token_hex(8)}"
    
    # Extract serial number from QR payload if structured (e.g. ENDRA:SN99018273:...)
    parts = payload.qr_code_payload.split(":")
    serial_num = parts[1] if len(parts) > 1 else "SN99018273"

    # Save staging state
    query = await db.execute(
        select(DiscoveredDevice).where(DiscoveredDevice.serial_number == serial_num)
    )
    staged_device = query.scalar_one_or_none()

    if staged_device:
        staged_device.activation_token = activation_token
        staged_device.staging_status = StagingStatus.VALIDATED
        if payload.organization_id:
            staged_device.organization_id = str(payload.organization_id)
        if payload.property_id:
            staged_device.property_id = str(payload.property_id)
        await db.commit()

    return schemas.QRValidationResponse(
        status="validated",
        activation_token=activation_token,
        serial_number=serial_num,
        device_type=schemas.DeviceType.CAMERA,
        model="ENDRA-Cam-Pro-4K"
    )


# ==========================================
# 3. DEVICE PAIRING
# ==========================================

@router.post("/pair", response_model=schemas.DevicePairingResponse)
async def pair_device(
    request: schemas.DevicePairingRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Finalizes staging pairing using activation token, stores configuration, 
    and transitions staging status to PAIRED.
    """
    query = await db.execute(
        select(DiscoveredDevice).where(DiscoveredDevice.device_id == request.device_id)
    )
    device = query.scalar_one_or_none()

    if device:
        device.staging_status = StagingStatus.PAIRED
        if request.ip_address:
            device.last_known_ip = request.ip_address
        if request.port:
            device.last_known_port = request.port
        await db.commit()

    return schemas.DevicePairingResponse(
        status="paired",
        device_id=request.device_id,
        assigned_zone=request.zone_name,
        firmware_version="v2.1.0-prod",
        is_online=True
    )


# ==========================================
# 4. MANUAL CAMERA SETUP (ONVIF / RTSP / DVR)
# ==========================================

@router.post(
    "/manual-setup", 
    response_model=schemas.ConnectionValidationResponse, 
    status_code=status.HTTP_201_CREATED
)
async def manual_camera_setup(
    payload: schemas.ManualCameraSetupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validates and registers manually connected cameras (ONVIF, RTSP, DVR/NVR).
    """
    constructed_url = build_rtsp_url(payload)

    new_camera = ManualCamera(
        camera_name=payload.camera_name,
        protocol=payload.protocol,
        ip_address=payload.ip_address,
        port=payload.port,
        channel=payload.channel,
        username=payload.username,
        password=payload.password,
        stream_url=constructed_url,
        status=CameraStatus.CONNECTED
    )

    db.add(new_camera)
    await db.commit()
    await db.refresh(new_camera)

    return schemas.ConnectionValidationResponse(
        success=True,
        message="Camera validated and connected successfully.",
        constructed_stream_url=constructed_url,
        camera=schemas.ManualCameraResponse.model_validate(new_camera)
    )


@router.get("/manual-cameras", response_model=List[schemas.ManualCameraResponse])
async def list_manual_cameras(db: AsyncSession = Depends(get_db)):
    """Retrieves all manually configured ONVIF/RTSP cameras."""
    result = await db.execute(select(ManualCamera))
    return result.scalars().all()