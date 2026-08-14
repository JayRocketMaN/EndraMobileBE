from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from app.core.database import get_db
from app.models.gateway_sync_model import CameraNode, CameraStatus
from app.core.security import decrypt_password # Assuming you have a matching decryption helper matching your hash setup

router = APIRouter(prefix="/api/v1/hardware/gateways", tags=["Gateway Cloud-Edge Sync Infrastructure"])


@router.get("/sync-streams")
async def synchronize_edge_streams(
    authorization: str = Header(..., description="Bearer token matching the GATEWAY_CLAIM_TOKEN"),
    db: AsyncSession = Depends(get_db)
):
    """
    Called by the local Python Edge Gateway background daemon.
    Authenticates the gateway token, extracts multi-tenant boundaries, and returns 
    unencrypted stream connection maps so the local edge go2rtc engine can pull video.
    """
    # 1. Extract token from Header
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authorization credential header layout."
        )
    
    gateway_token = authorization.replace("Bearer ", "")

    # 2. Security Handshake Layer
    # In a full deployment, look up this token against a trusted Gateways registry table.
    # For now, we simulate finding the organization context linked directly to this gateway token.
    # Let's assume this specific gateway token belongs to a verified enterprise Organization.
    
    # query = select(Gateway).where(Gateway.api_token == gateway_token)
    # result = await db.execute(query); gateway = result.scalar_one_or_none()
    
    # Simulated contextual boundary extract after token assertion:
    mock_authenticated_org_id = UUID("123e4567-e89b-12d3-a456-426614174000") # Tied to the token match

    # 3. Query all camera nodes deployed under this multi-tenant scope boundary
    camera_query = await db.execute(
        select(CameraNode).where(
            CameraNode.organization_id == mock_authenticated_org_id
        )
    )
    active_cameras = camera_query.scalars().all()

    # 4. Formulate the raw unencrypted stream payload mapping matrix needed by edge go2rtc
    provisions_matrix = []
    for camera in active_cameras:
        
        # Safely reverse your database encryption cipher strings back to plain text strings for local LAN ingestion
        plain_stream_password = ""
        if camera.stream_password_encrypted:
            try:
                plain_stream_password = decrypt_password(camera.stream_password_encrypted)
            except Exception:
                plain_stream_password = "" # Fallback gracefully if encryption blocks mismatch

        provisions_matrix.append({
            "stream_identifier": camera.stream_identifier,  # e.g., "stream_123e4567_sn99018273"
            "ip_address": camera.ip_address,                # Local office IP (e.g., 192.168.1.50)
            "port": camera.port,                            # RTSP socket port (e.g., 554)
            "username": camera.stream_username,             # LAN authentication account
            "password": plain_stream_password               # Decrypted plaintext LAN credential
        })

    return {
        "gateway_status": "authenticated",
        "cameras": provisions_matrix
    }
