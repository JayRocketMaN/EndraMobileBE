import secrets
import httpx
import cv2
import json
import os
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db 
from app.core.security import get_current_user
# Updated to use v_pipeline_2 manager or adapter
from app.services.v_pipeline_2 import VideoPipeline
from app.models.hardware_model import Camera, DiscoveredDevice, CameraStatus, StagingStatus, OnboardingMethod, ConnectionProtocol
from app.models.mobile_user_model import MobileUser
from app.models.hardware_model import ConnectivityType as DBConnectivityType
import app.schemas.hardware_schema as schemas

# Initialize router for Hikvision specific endpoints
router = APIRouter(prefix="/api/v1/hardware/hikvision", tags=["Hikvision Integration"])

logger = logging.getLogger(__name__)

# DEVELOPMENT BYPASS TOGGLE (Set to False when connecting real hardware)
BYPASS_PIPELINE_EXECUTION = True

# Global dictionary or manager for active pipeline instances if needed per camera
active_pipelines = {}


# ==========================================
# AUTH DEPENDENCY HELPER (X-User-ID)
# ==========================================
async def get_user_by_header(
    x_user_id: Optional[int] = Header(None, description="Pass the user ID directly for identification"),
    db: AsyncSession = Depends(get_db)
) -> MobileUser:
    """Identifies the user via the X-User-ID header consistently across routes."""
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header missing from request context."
        )

    result = await db.execute(
        select(MobileUser).where(MobileUser.id == x_user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User profile corresponding to ID {x_user_id} does not exist."
        )
        
    return user


# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================

def get_test_clip_path() -> str:
    """Dynamically resolves the absolute path to the local test video file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "media", "evidence", "clips", "livevid_crash0.mp4")


def build_hikvision_rtsp_url(ip: str, port: int = 554, username: str = "admin", password: str = "", channel: int = 1) -> str:
    """
    Constructs official Hikvision RTSP stream URL, or falls back to the local test clip path 
    if testing locally with sandbox IP addresses.
    """
    if ip in ["127.0.0.1", "localhost", "test"]:
        test_clip_path = get_test_clip_path()
        if os.path.exists(test_clip_path):
            return test_clip_path
            
    channel_code = f"{channel}01"
    return f"rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/{channel_code}"


def verify_rtsp_credentials(rtsp_url: str, timeout_ms: int = 3000) -> bool:
    """Attempts an RTSP or local file connection to verify stream accessibility."""
    if os.path.exists(rtsp_url):
        cap = cv2.VideoCapture(rtsp_url)
    else:
        options = f"rtsp_transport;tcp|timeout;{timeout_ms * 1000}|stimeout;{timeout_ms * 1000}"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = options
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)

    if not cap.isOpened():
        return False

    ret, _ = cap.read()
    cap.release()
    return ret


def to_db_connectivity(value) -> DBConnectivityType:
    raw = str(getattr(value, "value", value)).strip().lower().replace("-", "").replace("_", "")
    mapping = {
        "ble": DBConnectivityType.BLE,
        "wifi": DBConnectivityType.WIFI,
        "cellular": DBConnectivityType.CELLULAR,
    }
    try:
        return mapping[raw]
    except KeyError:
        raise ValueError(f"Unsupported connectivity value: {value!r}")


def start_pipeline_for_camera(camera_id: str, stream_source: str, camera_name: str):
    """Initializes and starts a VideoPipeline instance for the given camera."""
    try:
        # Ensure ingestion environment variables are configured for backend web socket sync
        os.environ["ENDRA_WS_INGEST_URL"] = os.environ.get("ENDRA_WS_INGEST_URL", "ws://localhost:8000/ws/ingest")
        os.environ["ENDRA_WS_INGEST_HEADERS"] = os.environ.get("ENDRA_WS_INGEST_HEADERS", "X-User-ID=5")
        os.environ["ENDRA_ALLOW_ANY_VIDEO_PATH"] = "1"

        pipeline = VideoPipeline(log_to_db=False)
        pipeline.start(
            stream_source,
            camera_id=camera_id,
            camera_name=camera_name,
            mode="video",
            loop=True,
            realtime=True
        )
        active_pipelines[camera_id] = pipeline
        logger.info(f"Successfully started v_pipeline_2 for camera {camera_id}")
    except Exception:
        logger.exception("Failed to start v_pipeline_2 for camera %s", camera_id)


# ==========================================
# 1. MANUAL ENTRY METHOD VIA HIKVISION ISAPI
# ==========================================
@router.post("/manual", response_model=schemas.ConnectionValidationResponse, status_code=status.HTTP_201_CREATED)
async def register_hikvision_camera_manually(
    payload: schemas.ManualCameraSetupRequest, 
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_user_by_header)
):
    ip = payload.ip_address
    http_port = payload.port or 80
    rtsp_port = 554
    username = payload.username or "admin"
    password = payload.password or ""
    channel = payload.channel or 1

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
                        detail=f"Device responded with status code: {response.status_code}."
                    )
                verified_serial = f"HK-{ip.replace('.', '-')}"
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Network error reaching Hikvision device at {ip}:{http_port}: {str(e)}"
            )

    constructed_url = build_hikvision_rtsp_url(ip=ip, port=rtsp_port, username=username, password=password, channel=channel)

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
        is_active=True,
        owner_id=current_user.id,
        property_id=getattr(payload, "property_id", None)
    )
    
    db.add(new_camera)
    await db.commit()
    await db.refresh(new_camera)

    # Start the video pipeline automatically using the database-generated UUID
    test_video_path = get_test_clip_path()
    start_pipeline_for_camera(str(new_camera.id), test_video_path, new_camera.camera_name)

    return schemas.ConnectionValidationResponse(
        success=True,
        message="Hikvision camera verified and registered successfully with dynamic UUID and active v_pipeline_2 test pipeline.",
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
    raw_text = payload.qr_payload.strip()
    serial_number = raw_text

    if "SN:" in raw_text:
        try:
            parts = {}
            for item in raw_text.split(";"):
                key, sep, value = item.partition(":")
                if sep:
                    parts[key.strip()] = value.strip()
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
            connectivity=to_db_connectivity(schemas.ConnectivityType.WIFI),
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
    db: AsyncSession = Depends(get_db),
    current_user: MobileUser = Depends(get_user_by_header)
):
    query = await db.execute(
        select(DiscoveredDevice).where(
            DiscoveredDevice.activation_token == request.activation_token,
            DiscoveredDevice.staging_status == StagingStatus.VALIDATED,
        )
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
                detail="Token verified, but failed to connect to stream source. Check IP or credentials."
            )

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
        is_active=True,
        owner_id=current_user.id,
        property_id=getattr(request, "property_id", None)
    )

    staged_device.staging_status = StagingStatus.PAIRED
    db.add(active_camera)
    await db.commit()
    await db.refresh(active_camera)

    # Start analytics pipeline using v_pipeline_2 and generated active_camera.id
    test_video_path = get_test_clip_path()
    start_pipeline_for_camera(str(active_camera.id), test_video_path, active_camera.camera_name)

    return schemas.DevicePairingResponse(
        status="paired",
        camera_id=active_camera.id,
        device_name=active_camera.camera_name,
        assigned_zone=active_camera.assigned_zone,
        constructed_stream_url=rtsp_url,
        is_online=True
    )


# ==========================================
# 3. STREAM CONTROL & FEED ENDPOINTS
# ==========================================

@router.post("/cameras/{camera_id}/start")
async def start_camera_stream(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Manually trigger or restart the video pipeline for a specific database-generated camera ID."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera with ID '{camera_id}' not found in database.")

    test_video_path = get_test_clip_path()
    start_pipeline_for_camera(str(camera.id), test_video_path, camera.camera_name)
    
    return {
        "status": "started", 
        "camera_id": str(camera.id), 
        "camera_name": camera.camera_name,
        "stream_source": test_video_path
    }


@router.get("/cameras/{camera_id}/feed")
async def stream_camera_feed(camera_id: str):
    """Streams MJPEG frames from the active pipeline for frontend playback."""
    pipeline = active_pipelines.get(camera_id)
    if not pipeline or not pipeline.get_status().get("running"):
        raise HTTPException(status_code=404, detail="Camera pipeline not active")
    
    # Assuming the v_pipeline_2 class has a frame generator method, or fall back to standard generation
    return StreamingResponse(
        pipeline.generate_frames() if hasattr(pipeline, "generate_frames") else iter([]),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.post("/cameras/{camera_id}/stop")
async def stop_camera_stream(camera_id: str):
    pipeline = active_pipelines.get(camera_id)
    if pipeline and hasattr(pipeline, "stop"):
        pipeline.stop()
        del active_pipelines[camera_id]
        return {"status": "stopped", "camera_id": camera_id}
    return {"status": "not_found", "camera_id": camera_id}


# ==========================================
# 4. AUTO-DISCOVERY (LAN / ONVIF PROBING)
# ==========================================

@router.post("/discover", response_model=List[schemas.HikvisionDiscoveryResponse])
async def discover_hikvision_cameras_on_lan(db: AsyncSession = Depends(get_db)):
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
                ip_address=item.last_known_ip or "127.0.0.1",
                port=item.http_port or 80,
                rtsp_port=554,
                serial_number=item.serial_number,
                mac_address=item.mac_address,
                model=item.model or "DS-2CD2087G2",
                firmware_version=item.firmware_version or "V5.5.80"
            )
        )

    if not discovered_cameras:
        discovered_cameras.append(
            schemas.HikvisionDiscoveryResponse(
                ip_address="127.0.0.1",
                port=80,
                rtsp_port=554,
                serial_number="HK-127-0-0-1",
                mac_address="AA:BB:CC:DD:EE:FF",
                model="DS-2CD2087G2",
                firmware_version="V5.5.80"
            )
        )

    return discovered_cameras