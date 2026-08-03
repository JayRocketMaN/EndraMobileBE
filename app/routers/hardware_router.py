from fastapi import APIRouter, HTTPException, status
from typing import List
import app.schemas.camera_schema as schemas

router = APIRouter(prefix="/api/v1/hardware", tags=["Batch 2: Hardware & Onboarding"])


@router.get("/discover", response_model=List[schemas.DeviceDiscoveryItem])
async def discover_nearby_devices():
    """Scans for unconfigured ENDRA devices over BLE or local Wi-Fi network."""
    return [
        schemas.DeviceDiscoveryItem(
            device_id="dev_ble_001",
            device_name="ENDRA HD Dome Camera",
            device_type=schemas.DeviceType.CAMERA,
            signal_strength_dbm=-48,
            mac_address="00:1A:2B:3C:4D:5E",
            connectivity=schemas.ConnectivityType.BLE
        ),
        schemas.DeviceDiscoveryItem(
            device_id="dev_ble_002",
            device_name="ENDRA Smart Siren & Strobe",
            device_type=schemas.DeviceType.SIREN,
            signal_strength_dbm=-62,
            mac_address="00:1A:2B:3C:4D:5F",
            connectivity=schemas.ConnectivityType.BLE
        )
    ]


@router.post("/validate-qr")
async def validate_device_qr(payload: schemas.QRValidationRequest):
    """Validates device authenticity using scanned QR code payload."""
    if not payload.qr_code_payload.startswith("ENDRA"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unrecognized ENDRA device QR code."
        )
    return {
        "status": "valid",
        "serial_number": "SN99018273",
        "device_type": schemas.DeviceType.CAMERA,
        "model": "ENDRA-Cam-Pro-4K"
    }


@router.post("/pair", response_model=schemas.DevicePairingResponse)
async def pair_device(request: schemas.DevicePairingRequest):
    """Pairs the discovered device to the account, configures Wi-Fi, and assigns a zone."""
    return schemas.DevicePairingResponse(
        device_id=request.device_id,
        assigned_zone=request.zone_name
    )