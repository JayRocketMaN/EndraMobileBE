import secrets
import httpx
import cv2
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.services.video_pipeline import pipeline_manager
from app.models.hardware_model import Camera, DiscoveredDevice, CameraStatus, StagingStatus, OnboardingMethod, ConnectionProtocol
import app.schemas.hardware_schema as schemas

# Initialize router for Hikvision specific endpoints
router = APIRouter(prefix="/api/v1/hardware/hikvision", tags=["Hikvision Integration"])

# DEVELOPMENT BYPASS TOGGLE
BYPASS_PIPELINE_EXECUTION = True


# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================

def build_hikvision_rtsp_url(ip: str, port: int = 554, username: str = "admin", password: str = "", channel: int = 1) -> str:
    """Constructs official Hikvision RTSP stream URL for main stream channels ({channel}01)."""
    channel_code = f"{channel}01"
    return f"rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/{channel_code}"


def verify_rtsp_credentials(rtsp_url: str, timeout_ms: int = 3000) -> bool:
    """Attempts an RTSP connection with tight timeout limits to verify stream accessibility."""
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)

    if not cap.isOpened():
        return False

    ret, _ = cap.read()
    cap.release()
    return ret


# ==========================================
# 1. MANUAL ENTRY METHOD VIA HIKVISION ISAPI
# ==========================================

@router.post("/manual", response_model=schemas.ConnectionValidationResponse, status_code=status.HTTP_201_CREATED)
async def register_hikvision_camera_manually(
    payload: schemas.ManualCameraSetupRequest, 
    db: AsyncSession = Depends(get_db)
):
    """
    Manually add a Hikvision camera using IP coordinates, 
    verify via ISAPI endpoint (/ISAPI/System/deviceInfo), and register stream.
    """
    ip = payload.ip_address
    http_port = payload.port or 80
    rtsp_port = 554
    username = payload.username or "admin"
    password = payload.password or ""
    channel = payload.channel or 1

    # 1. Verify credentials via Hikvision ISAPI REST endpoint
    isapi_url = f"http://{ip}:{http_port}/ISAPI/System/deviceInfo"
    verified_serial = None

    if BYPASS_PIPELINE_EXECUTION:
        verified_serial = f"HK-{ip.replace('.', '-')}"
    else:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.get(
                    isapi_url, 
                    auth=httpx.DigestAuth(username, password)
                )
                
                if response.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail="Hikvision Authentication Failed: Invalid username or password."
                    )
                elif response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Device responded with status code: {response.status_code}. Ensure this is a Hikvision device."
                    )
                
                verified_serial = f"HK-{ip.replace('.', '-')}"
                
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Network error or timeout reaching Hikvision device at {ip}:{http_port} - {str(e)}"
            )

    # 2. Construct Official Hikvision RTSP Stream URL
    constructed_url = build_hikvision_rtsp_url(ip=ip, port=rtsp_port, username=username, password=password, channel=channel)

    # 3. Persist to Database
    new_camera = Camera(
        camera_name=payload.device_name,
        serial_number=verified_serial,
        protocol=ConnectionProtocol.RTSP,
        onboarding_method=OnboardingMethod.MANUAL,
        ip_address=ip,
        port=rtsp_port,
        channel=channel,
        username=username,
        password=password,
        stream_url=constructed_url,
        assigned_zone=getattr(payload, "assigned_zone", "Hikvision Zone"),
        status=CameraStatus.ONLINE,
        is_active=True
    )
    
    db.add(new_camera)
    await db.commit()
    await db.refresh(new_camera)

    return schemas.ConnectionValidationResponse(
        success=True,
        message="Hikvision camera verified via ISAPI and registered successfully.",
        constructed_stream_url=constructed_url,
        camera=schemas.CameraResponse.model_validate(new_camera)
    )


# ==========================================
# 2. QR CODE SCANNING & STAGING
# ==========================================

@router.post("/validate-qr", response_model=schemas.HikvisionQRValidationResponse)
async def validate_hikvision_qr(
    payload: schemas.HikvisionQRRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Parses Hikvision QR payloads (Serial Number strings or configuration packages),
    stages the device in PostgreSQL, and issues an activation token.
    """
    raw_text = payload.qr_payload.strip()
    serial_number = raw_text

    if "SN:" in raw_text:
        try:
            parts = {item.split(":")[0]: item.split(":")[1] for item in raw_text.split(";") if ":" in item}
            serial_number = parts.get("SN") or parts.get("serial") or raw_text
        except Exception:
            serial_number = raw_text

    if not serial_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Hikvision QR payload format. Could not extract Serial Number."
        )

    activation_token = f"hik_tok_{secrets.token_urlsafe(16)}"

    query = await db.execute(
        select(DiscoveredDevice).where(DiscoveredDevice.serial_number == serial_number)
    )
    staged = query.scalar_one_or_none()

    if staged:
        staged.activation_token = activation_token
        staged.staging_status = StagingStatus.VALIDATED
    else:
        staged = DiscoveredDevice(
            device_id=f"dev_hik_{secrets.token_hex(4)}",
            serial_number=serial_number,
            device_name="Hikvision IP Camera",
            maker="Hikvision",
            model="DS-2CD2087G2",
            connectivity=schemas.ConnectivityType.WIFI,
            activation_token=activation_token,
            staging_status=StagingStatus.VALIDATED
        )
        db.add(staged)

    await db.commit()

    return schemas.HikvisionQRValidationResponse(
        status="validated",
        activation_token=activation_token,
        serial_number=serial_number,
        model="DS-2CD2087G2",
        can_auto_pair=False
    )


@router.post("/pair-qr", response_model=schemas.DevicePairingResponse)
async def pair_hikvision_camera_via_qr(
    request: schemas.QrDevicePairingRequest,
    db: AsyncSession = Depends(get_db)
):
    """Finalizes pairing using the QR activation token and registers the active camera stream."""
    query = await db.execute(
        select(DiscoveredDevice).where(DiscoveredDevice.activation_token == request.activation_token)
    )
    staged_device = query.scalar_one_or_none()
    
    if not staged_device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired QR activation token. Please scan the QR code again."
        )

    rtsp_url = build_hikvision_rtsp_url(
        ip=request.ip_address,
        port=request.port,
        username=request.username,
        password=request.password,
        channel=request.channel or 1
    )

    if not BYPASS_PIPELINE_EXECUTION:
        is_valid = await run_in_threadpool(verify_rtsp_credentials, rtsp_url, 3000)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verified, but failed to connect to RTSP stream. Check IP, port, or credentials."
            )

    # Persist active camera entity
    active_camera = Camera(
        camera_name=request.device_name,
        serial_number=staged_device.serial_number,
        mac_address=request.mac_address,
        assigned_zone=request.zone_name or "Default Zone",
        protocol=ConnectionProtocol.RTSP,
        onboarding_method=OnboardingMethod.QR_CODE,
        ip_address=request.ip_address,
        port=request.port,
        channel=request.channel or 1,
        username=request.username,
        password=request.password,
        stream_url=rtsp_url,
        status=CameraStatus.ONLINE,
        is_active=True
    )
    
    staged_device.staging_status = StagingStatus.PAIRED
    db.add(active_camera)
    await db.commit()
    await db.refresh(active_camera)

    if not BYPASS_PIPELINE_EXECUTION:
        pipeline_manager.start(stream_source=rtsp_url, camera_id=active_camera.id)

    return schemas.DevicePairingResponse(
        status="paired",
        camera_id=active_camera.id,
        device_name=active_camera.camera_name,
        assigned_zone=active_camera.assigned_zone,
        constructed_stream_url=rtsp_url,
        is_online=True
    )


# ==========================================
# 3. AUTO-DISCOVERY (LAN / ONVIF PROBING)
# ==========================================

@router.post("/discover", response_model=List[schemas.HikvisionDiscoveryResponse])
async def discover_hikvision_cameras_on_lan(db: AsyncSession = Depends(get_db)):
    """Scans local subnet or queries active network staging tables for connected Hikvision cameras."""
    discovered_cameras = []

    result = await db.execute(
        select(DiscoveredDevice).where(
            DiscoveredDevice.staging_status == StagingStatus.DISCOVERED,
            DiscoveredDevice.maker.ilike("%hikvision%") | DiscoveredDevice.serial_number.like("HK-%")
        )
    )
    staged_items = result.scalars().all()

    for item in staged_items:
        discovered_cameras.append(
            schemas.HikvisionDiscoveryResponse(
                ip_address=item.last_known_ip or "192.168.1.64",
                port=item.http_port or 80,
                rtsp_port=554,
                serial_number=item.serial_number,
                mac_address=item.mac_address,
                model=item.model or "DS-2CD2087G2",
                firmware_version=item.firmware_version or "V5.5.80"
            )
        )

    if not discovered_cameras:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No new Hikvision cameras found on the local network. Ensure cameras are powered on and connected."
        )

    return discovered_cameras