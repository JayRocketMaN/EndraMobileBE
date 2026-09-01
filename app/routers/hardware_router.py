import secrets
import cv2
import re
import json
import os
from typing import Any, List, Optional, Dict

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.services.video_pipeline import pipeline_manager
from app.models.hardware_model import Camera, DiscoveredDevice, CameraStatus, StagingStatus
import app.schemas.hardware_schema as schemas

# Initialize a SINGLE router instance for all hardware endpoints
router = APIRouter()


# ==========================================
# UTILITY HELPER FUNCTIONS
# ==========================================

def build_universal_rtsp_url(
    ip: str, 
    port: int, 
    username: str, 
    password: str, 
    channel: int = 1, 
    custom_path: Optional[str] = None
) -> str:
    """Formats RTSP URL depending on custom vendor path or generic fallback."""
    if custom_path and custom_path.strip():
        path = custom_path.strip().lstrip("/")
        return f"rtsp://{username}:{password}@{ip}:{port}/{path}"
    return f"rtsp://{username}:{password}@{ip}:{port}/h264/ch{channel}/main"


def verify_rtsp_credentials(rtsp_url: str, timeout_ms: int = 3000) -> bool:
    """Attempts an RTSP connection with tight timeout limits to prevent hanging."""
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


def generate_activation_token(prefix: str = "sec_tok") -> str:
    """Generate a unique token for activation and staged devices."""
    return f"{prefix}_{secrets.token_urlsafe(24)}"


async def verify_activation_token(db: AsyncSession, token: str):
    """Verifies that the provided activation token exists and is valid in the database."""
    query = await db.execute(
        select(DiscoveredDevice).where(
            DiscoveredDevice.activation_token == token
        )
    )
    return query.scalar_one_or_none()


def parse_third_party_qr(qr_payload: str) -> Dict[str, Any]:
    """Parses QR string formats: JSON objects, Key-Value pairs, or raw MAC/Serial strings."""
    cleaned = qr_payload.strip()
    result: Dict[str, Any] = {
        "identifier": None,
        "type": "unknown",
        "ip_address": None,
        "port": None,
        "username": None,
        "password": None,
        "channel": None,
        "custom_stream_path": None,
        "protocol": None,
    }

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            data = json.loads(cleaned)
            result["ip_address"] = data.get("ip_address") or data.get("ip")
            result["port"] = int(data["port"]) if data.get("port") else None
            result["username"] = data.get("username") or data.get("user")
            result["password"] = data.get("password") or data.get("pass")
            result["channel"] = int(data["channel"]) if data.get("channel") else None
            result["custom_stream_path"] = data.get("custom_stream_path") or data.get("path")
            result["protocol"] = data.get("protocol")

            identifier = data.get("mac_address") or data.get("mac") or data.get("serial_number") or data.get("sn")
            if identifier:
                result["identifier"] = str(identifier).upper()
                result["type"] = "mac" if ":" in str(identifier) or "-" in str(identifier) else "serial"
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    if "=" in cleaned:
        kv = dict(item.split("=", 1) for item in cleaned.split(";") if "=" in item)
        result["ip_address"] = kv.get("IP") or kv.get("ip")
        result["port"] = int(kv["PORT"]) if "PORT" in kv or "port" in kv else None
        result["username"] = kv.get("USER") or kv.get("username")
        result["password"] = kv.get("PASS") or kv.get("password")
        sn = kv.get("SN") or kv.get("SERIAL") or kv.get("s/n")
        mac = kv.get("MAC") or kv.get("mac")

        if mac:
            result["identifier"] = mac.upper()
            result["type"] = "mac"
            return result
        if sn:
            result["identifier"] = sn
            result["type"] = "serial"
            return result

    mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', cleaned)
    if mac_match:
        result["identifier"] = mac_match.group(0).upper()
        result["type"] = "mac"
        return result

    if len(cleaned) >= 4:
        result["identifier"] = cleaned
        result["type"] = "serial"

    return result


async def _persist_paired_device(
    db: AsyncSession, 
    request: Any,
    rtsp_url: str
) -> Camera:
    # 1. Update or create the Staged DiscoveredDevice record
    query = await db.execute(
        select(DiscoveredDevice).where(DiscoveredDevice.last_known_ip == request.ip_address)
    )
    staged = query.scalar_one_or_none()
    if staged:
        staged.staging_status = StagingStatus.PAIRED
    
    # 2. Check if the camera already exists in the Camera table
    cam_query = await db.execute(
        select(Camera).where(Camera.ip_address == request.ip_address)
    )
    camera = cam_query.scalar_one_or_none()
    
    if camera:
        camera.device_name = request.device_name
        camera.port = request.port
        camera.username = request.username
        camera.password = request.password
        camera.stream_url = rtsp_url
        camera.status = CameraStatus.CONNECTED
        camera.assigned_zone = request.zone_name or camera.assigned_zone
    else:
        camera = Camera(
            device_name=request.device_name,
            ip_address=request.ip_address,
            port=request.port or 554,
            channel=getattr(request, "channel", 1) or 1,
            username=request.username,
            password=request.password,
            custom_stream_path=getattr(request, "custom_stream_path", None),
            assigned_zone=getattr(request, "zone_name", "Default Zone"),
            stream_url=rtsp_url,
            status=CameraStatus.CONNECTED
        )
        db.add(camera)

    await db.commit()
    await db.refresh(camera)
    return camera
# ==========================================
# 3. DEVELOPMENT BYPASS UTILITIES
# ==========================================

@router.post("/test-utility/generate-mock-qr")
async def generate_mock_qr_string(
    mac_address: str = "AA:BB:CC:11:22:33",
    ip_address: str = "192.168.1.200"
):
    """
    Development bypass tool. Returns a structured JSON string payload 
    simulating a camera vendor's raw scanned QR code.
    
    TIP: If you are deploying or testing this on cloud services like Render, 
    change the 'ip_address' field parameter to 'rtsp.stream', username to 'demo', 
    and password to 'demo' to pass live stream handshakes successfully.
    """
    # Dynamic parameter mappings based on input string context
    is_public_test = ip_address.strip().lower() == "rtsp.stream"
    
    mock_payload = {
        "ip_address": ip_address.strip(),
        "port": 554,
        "username": "demo" if is_public_test else "admin",
        "password": "demo" if is_public_test else "Password123",
        "channel": 1,
        "custom_stream_path": "/pattern" if is_public_test else "/live/ch0_main",
        "mac_address": mac_address.strip().upper(),
        "protocol": "RTSP"
    }
    
    # Converts the Python dictionary into a tight JSON string payload 
    # that your parse_third_party_qr function expects
    qr_string_format = json.dumps(mock_payload)
    
    return {
        "message": "Copy the text inside 'raw_qr_payload' and send it to your /validate-qr endpoint.",
        "raw_qr_payload": qr_string_format
    }


# ==========================================
# 1. QR CODE VALIDATION & STAGING
# ==========================================

@router.post("/validate-qr", response_model=schemas.QRValidationResponse)
async def validate_third_party_qr(
    payload: schemas.QRValidationRequest,
    db: AsyncSession = Depends(get_db)
):
    parsed = parse_third_party_qr(payload.qr_code_payload)
    identifier = parsed["identifier"]

    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract a valid MAC address, Serial Number, or JSON payload from the scanned QR code."
        )

    can_auto_pair = bool(
        parsed["ip_address"] and 
        parsed["username"] and 
        parsed["password"]
    )

    activation_token = generate_activation_token(prefix="sec_tok")

    query = await db.execute(
        select(DiscoveredDevice).where(
            (DiscoveredDevice.mac_address == identifier) | 
            (DiscoveredDevice.serial_number == identifier)
        )
    )
    staged_device = query.scalar_one_or_none()

    if staged_device:
        staged_device.activation_token = activation_token
        staged_device.staging_status = StagingStatus.VALIDATED
        if parsed["ip_address"]:
            staged_device.last_known_ip = parsed["ip_address"]
    else:
        staged_device = DiscoveredDevice(
            device_id=generate_activation_token(prefix="dev_qr"),
            serial_number=identifier if parsed["type"] == "serial" else None,
            mac_address=identifier if parsed["type"] == "mac" else None,
            activation_token=activation_token,
            last_known_ip=parsed["ip_address"],
            staging_status=StagingStatus.VALIDATED
        )
        db.add(staged_device)

    await db.commit()

    return schemas.QRValidationResponse(
        status="validated",
        activation_token=activation_token,
        identifier=identifier,
        device_type=schemas.DeviceType.CAMERA,
        can_auto_pair=can_auto_pair,
        ip_address=parsed["ip_address"],
        port=parsed["port"] or 554,
        username=parsed["username"],
        password=parsed["password"],
        channel=parsed["channel"] or 1,
        custom_stream_path=parsed["custom_stream_path"],
        protocol=schemas.ConnectionProtocol.RTSP if parsed["protocol"] is None else parsed["protocol"]
 )



"""# ==========================================
# 2. DEVICE PAIRING
# ==========================================

@router.post("/pair-qr", response_model=schemas.DevicePairingResponse)
async def pair_camera_via_qr(
    request: schemas.QrDevicePairingRequest,  # <-- Strictly enforces token requirement
    db: AsyncSession = Depends(get_db)
):
    #Pairs a camera utilizing a secure, pre-validated QR activation token.
    staged_device = await verify_activation_token(db, request.activation_token)
    if not staged_device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired QR activation token. Please scan the QR code again."
        )

    # Corrected Pydantic lookup: request.ip -> request.ip_address
    rtsp_url = build_universal_rtsp_url(
        ip=request.ip_address,
        port=request.port,
        username=request.username,
        password=request.password,
        channel=request.channel or 1,
        custom_path=request.custom_stream_path
    )

    is_valid = await run_in_threadpool(verify_rtsp_credentials, rtsp_url, 3000)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verified, but failed to connect to RTSP stream. Check IP, port, or credentials."
        )

    device = await _persist_paired_device(db, request)
    pipeline_manager.start(stream_source=rtsp_url, camera_id=device.id)

    # Corrected to perfectly match DevicePairingResponse schema properties
    return schemas.DevicePairingResponse(
        status="paired",
        camera_id=device.device_id,
        device_name=device.device_name,
        assigned_zone=device.assigned_zone or "Default Zone",
        constructed_stream_url=rtsp_url,
        is_online=True
    )"""

# ==========================================
# INTERNAL UTILITY PERSISTENCE HELPER
# ==========================================

async def _persist_paired_device(
    db: AsyncSession, 
    request: Any  # Polymorphic helper supporting all pairing variants cleanly
) -> DiscoveredDevice:
    """Helper function to create or update functional DiscoveredDevice entity objects."""
    # FIXED: Changed request.ip to request.ip_address to match schema contracts perfectly
    query = await db.execute(
        select(DiscoveredDevice).where(DiscoveredDevice.last_known_ip == request.ip_address)
    )
    device = query.scalar_one_or_none()

    if device:
        # FIX: Removed 'protocol' assignment because the column doesn't exist on DiscoveredDevice
        device.last_known_port = request.port
        device.cached_username = request.username
        device.cached_password = request.password
        device.device_name = request.device_name
        device.assigned_zone = request.zone_name
        device.staging_status = StagingStatus.PAIRED
        device.mac_address = request.mac_address or device.mac_address
        device.serial_number = request.serial_number or device.serial_number
        
        # Safely bind UI brand parameters if provided
        if hasattr(request, "maker") and request.maker:
            device.maker = request.maker
        if hasattr(request, "model") and request.model:
            device.model = request.model
    else:
        # FIX: Adjusted dictionary keys to align explicitly with DiscoveredDevice model columns
        device = DiscoveredDevice(
            device_id=f"cam_{secrets.token_hex(4)}",
            last_known_ip=request.ip_address,
            last_known_port=request.port,
            cached_username=request.username,
            cached_password=request.password,
            device_name=request.device_name,
            staging_status=StagingStatus.PAIRED,
            mac_address=request.mac_address,
            serial_number=request.serial_number,
            maker=getattr(request, "maker", None),
            model=getattr(request, "model", None)
        )
        db.add(device)

    await db.commit()
    await db.refresh(device)
    return device



# ==========================================
# 2. DEVICE PAIRING ENDPOINTS
# ==========================================

# 🧪 TOGGLE FLAG: Set to True for testing/frontend development. 
# Set to False when you want the real YOLO/VLM pipeline to engage.
BYPASS_PIPELINE_EXECUTION = True


@router.post("/pair-qr", response_model=schemas.DevicePairingResponse)
async def pair_camera_via_qr(
    request: schemas.QrDevicePairingRequest,
    db: AsyncSession = Depends(get_db)
):
    """Finalizes pairing by verifying an active token context session."""
    staged_device = await verify_activation_token(db, request.activation_token)
    if not staged_device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired QR activation token. Please scan the QR code again."
        )

    rtsp_url = build_universal_rtsp_url(
        ip=request.ip_address,
        port=request.port,
        username=request.username,
        password=request.password,
        channel=request.channel or 1,
        custom_path=request.custom_stream_path
    )

    # 1. Persist directly to your PostgreSQL database safely
    device = await _persist_paired_device(db, request)

    # 2. PIPELINE INTERCEPTION CHECK
    if BYPASS_PIPELINE_EXECUTION:
        # Log the bypass and return a fake active state to satisfy the mobile client
        print(f"🧪 [BYPASS MODE] Saved QR camera '{device.device_name}' to DB. Skipping live pipeline start.")
        is_stream_online = True
    else:
        # Production: Verify credentials via OpenCV and engage multi-threaded frame capture
        is_valid = await run_in_threadpool(verify_rtsp_credentials, rtsp_url, 3000)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verified, but failed to connect to RTSP stream. Check IP, port, or credentials."
            )
        pipeline_manager.start(stream_source=rtsp_url, camera_id=device.device_id)
        is_stream_online = True

    return schemas.DevicePairingResponse(
        status="paired",
        camera_id=device.device_id,
        device_name=device.device_name,
        assigned_zone=device.assigned_zone or "Default Zone",
        constructed_stream_url=rtsp_url,
        is_online=is_stream_online
    )


@router.post("/pair-discovered", response_model=schemas.DevicePairingResponse)
async def pair_auto_discovered_camera(
    request: schemas.DiscoveredDevicePairingRequest,
    db: AsyncSession = Depends(get_db)
):
    """Natively locks and pairs auto-discovered local area network endpoints."""
    rtsp_url = build_universal_rtsp_url(
        ip=request.ip_address,
        port=request.port,
        username=request.username,
        password=request.password,
        channel=request.channel or 1,
        custom_path=request.custom_stream_path
    )

    # 1. Persist directly to your PostgreSQL database safely
    device = await _persist_paired_device(db, request)

    # 2. PIPELINE INTERCEPTION CHECK
    if BYPASS_PIPELINE_EXECUTION:
        # Log the bypass and return a fake active state to satisfy the mobile client
        print(f"🧪 [BYPASS MODE] Saved Discovered camera '{device.device_name}' to DB. Skipping live pipeline start.")
        is_stream_online = True
    else:
        # Production: Verify credentials via OpenCV and engage multi-threaded frame capture
        is_valid = await run_in_threadpool(verify_rtsp_credentials, rtsp_url, 3000)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate RTSP stream. Verify IP address, port, username, or password."
            )
        pipeline_manager.start(stream_source=rtsp_url, camera_id=device.device_id)
        is_stream_online = True

    return schemas.DevicePairingResponse(
        status="paired",
        camera_id=device.device_id,
        device_name=device.device_name,
        assigned_zone=device.assigned_zone or "Default Zone",
        constructed_stream_url=rtsp_url,
        is_online=is_stream_online
    )
# ==========================================
# 3. MANUAL CAMERA SETUP
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
    constructed_url = build_universal_rtsp_url(
        ip=payload.ip_address,
        port=payload.port or 554,
        username=payload.username,
        password=payload.password,
        channel=payload.channel or 1,
        custom_path=getattr(payload, "custom_stream_path", None)
    )

    # PIPELINE INTERCEPTION CHECK
    if BYPASS_PIPELINE_EXECUTION:
        print(f"🧪 [BYPASS MODE] Skipping RTSP connection test for manual camera '{payload.device_name}'.")
    else:
        is_valid = await run_in_threadpool(verify_rtsp_credentials, constructed_url, 3000)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to connect to camera. Please verify the IP address, port, username, password, or custom stream path."
            )

    query = await db.execute(
        select(Camera).where(Camera.ip_address == payload.ip_address)
    )
    existing_camera = query.scalar_one_or_none()

    if existing_camera:
        existing_camera.camera_name = payload.device_name  # Corrected field mapping
        existing_camera.port = payload.port or 554
        existing_camera.channel = payload.channel or 1
        existing_camera.username = payload.username
        existing_camera.password = payload.password
        existing_camera.custom_stream_path = getattr(payload, "custom_stream_path", None)
        existing_camera.assigned_zone = getattr(payload, "assigned_zone", "Default Zone")
        existing_camera.stream_url = constructed_url
        existing_camera.status = CameraStatus.CONNECTED
        camera = existing_camera
    else:
        camera = Camera(
            camera_name=payload.device_name,  # Corrected field mapping
            ip_address=payload.ip_address,
            port=payload.port or 554,
            channel=payload.channel or 1,
            username=payload.username,
            password=payload.password,
            custom_stream_path=getattr(payload, "custom_stream_path", None),
            assigned_zone=getattr(payload, "assigned_zone", "Default Zone"),
            stream_url=constructed_url,
            status=CameraStatus.CONNECTED
        )
        db.add(camera)

    await db.commit()
    await db.refresh(camera)

    # START PIPELINE OR BYPASS
    if BYPASS_PIPELINE_EXECUTION:
        print(f"🧪 [BYPASS MODE] Saved manual camera '{camera.camera_name}' to DB. Skipping live pipeline start.")
    else:
        pipeline_manager.start(stream_source=camera.stream_url, camera_id=camera.id)

    return schemas.ConnectionValidationResponse(
        success=True,
        message="Camera validated and connected successfully.",
        constructed_stream_url=constructed_url,
        camera=schemas.CameraResponse.model_validate(camera)
    )
# ==========================================
# 4. UNIFIED CAMERA CRUD & AGGREGATION
# ==========================================

@router.get("/cameras", response_model=List[schemas.CameraResponse])
async def list_all_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera))
    return result.scalars().all()


@router.get("/cameras/{camera_id}", response_model=schemas.CameraResponse)
async def get_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Camera with ID '{camera_id}' not found."
        )
    return camera

@router.put("/cameras/{camera_id}", response_model=schemas.CameraResponse)
async def update_camera(
    camera_id: str, 
    payload: schemas.CameraUpdateRequest, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Camera with ID '{camera_id}' not found."
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(camera, key, value)

    camera.stream_url = build_universal_rtsp_url(
        ip=camera.ip_address,
        port=camera.port,
        username=camera.username,
        password=camera.password,
        channel=camera.channel or 1,
        custom_path=camera.custom_stream_path
    )

    await db.commit()
    await db.refresh(camera)

    # If pipeline_manager is a dict, manage active pipeline entries directly
    if isinstance(pipeline_manager, dict):
        # Stop existing pipeline process if present in dictionary
        existing_pipeline = pipeline_manager.pop(camera.id, None)
        if existing_pipeline and hasattr(existing_pipeline, "stop"):
            existing_pipeline.stop()

    return camera


@router.delete("/cameras/{camera_id}", status_code=status.HTTP_200_OK)
async def delete_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Camera with ID '{camera_id}' not found."
        )

    # If pipeline_manager is a dict, manage active pipeline entries directly
    if isinstance(pipeline_manager, dict):
        existing_pipeline = pipeline_manager.pop(camera.id, None)
        if existing_pipeline and hasattr(existing_pipeline, "stop"):
            existing_pipeline.stop()

    await db.delete(camera)
    await db.commit()

    return {"status": "success", "message": f"Camera '{camera_id}' deleted successfully."}


# ==========================================
# 5. STREAM CONTROL ENDPOINTS
# ==========================================

@router.post("/cameras/{camera_id}/start")
async def start_camera_stream(camera_id: int, rtsp_url: str):
    pipeline = pipeline_manager.start_camera(camera_id, rtsp_url)
    return {"status": "started", "camera_id": camera_id}


@router.get("/cameras/{camera_id}/feed")
async def stream_camera_feed(camera_id: int):
    pipeline = pipeline_manager.get_pipeline(camera_id)
    if not pipeline or not pipeline._is_running:
        raise HTTPException(status_code=404, detail="Camera pipeline not active")
    
    return StreamingResponse(
        pipeline.generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.post("/cameras/{camera_id}/stop")
async def stop_camera_stream(camera_id: int):
    success = pipeline_manager.stop_camera(camera_id)
    return {"status": "stopped" if success else "not_found", "camera_id": camera_id}


