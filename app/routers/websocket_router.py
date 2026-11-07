import json
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Adjust imports to match your project structure
from app.core.database import get_db

router = APIRouter(prefix="/ws", tags=["Batch 2: WebSockets & Live Streaming"])
logger = logging.getLogger("uvicorn.error")


class ConnectionManager:
    """Manages active WebSocket connections for cameras and clients."""
    def __init__(self):
        # Maps camera_id -> list of connected client WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, camera_id: str, websocket: WebSocket):
        await websocket.accept()
        if camera_id not in self.active_connections:
            self.active_connections[camera_id] = []
        self.active_connections[camera_id].append(websocket)

    def disconnect(self, camera_id: str, websocket: WebSocket):
        if camera_id in self.active_connections:
            if websocket in self.active_connections[camera_id]:
                self.active_connections[camera_id].remove(websocket)
            if not self.active_connections[camera_id]:
                del self.active_connections[camera_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_text(json.dumps(message))

    async def broadcast_to_camera(self, camera_id: str, message: dict):
        """Broadcasts events (e.g. motion detected) to all viewers of a camera."""
        if camera_id in self.active_connections:
            for connection in self.active_connections[camera_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error broadcasting to client on camera {camera_id}: {str(e)}")


manager = ConnectionManager()


# ==========================================
# WEBSOCKET STREAMING & SIGNALING ENDPOINT
# ==========================================

@router.websocket("/live-stream/{camera_id}")
async def camera_websocket_endpoint(
    websocket: WebSocket, 
    camera_id: str,
    user_id: int | None = Query(default=None, description="Optional user ID for session tracking")
):
    """
    WebSocket endpoint for WebRTC SDP signaling (Offer/Answer), 
    heartbeat pings, and receiving live AI threat/event feeds for a camera.
    """
    await manager.connect(camera_id, websocket)
    logger.info(f"Client connected to camera {camera_id} stream channel (User ID: {user_id})")
    
    # Notify client connection succeeded
    await manager.send_personal_message(
        {
            "event": "connected",
            "camera_id": camera_id,
            "message": f"Connected to real-time event & stream channel for camera {camera_id}"
        },
        websocket
    )

    try:
        while True:
            # Receive text frames with a timeout to prevent idle socket drops on Render proxy
            raw_data = await websocket.receive_text()
            
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": "error", "detail": "Invalid JSON payload received."},
                    websocket
                )
                continue
            
            event_type = data.get("type")

            # 1. Handle WebRTC SDP Offer
            if event_type == "sdp_offer":
                sdp_offer = data.get("sdp", "")
                
                # Mock WebRTC Answer response (Replace with real WebRTC pipeline / Layer 1 inference server)
                sdp_answer = f"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=ENDRA_WebRTC_Session\r\n{sdp_offer[:30]}..."
                
                await manager.send_personal_message(
                    {
                        "type": "sdp_answer",
                        "camera_id": camera_id,
                        "sdp": sdp_answer,
                        "status": "established"
                    },
                    websocket
                )

            # 2. Handle ICE Candidate exchange
            elif event_type == "ice_candidate":
                candidate = data.get("candidate")
                await manager.send_personal_message(
                    {
                        "type": "ice_candidate_ack",
                        "camera_id": camera_id,
                        "candidate": candidate
                    },
                    websocket
                )

            # 3. Heartbeat / Ping-Pong (Keeps Render proxy connection alive past 55s timeout)
            elif event_type == "ping":
                await manager.send_personal_message({"type": "pong"}, websocket)

            else:
                await manager.send_personal_message(
                    {"type": "error", "detail": f"Unknown event type: {event_type}"},
                    websocket
                )

    except WebSocketDisconnect:
        manager.disconnect(camera_id, websocket)
        logger.info(f"Client cleanly disconnected from camera channel: {camera_id}")
    except Exception as e:
        manager.disconnect(camera_id, websocket)
        logger.error(f"WebSocket error on camera {camera_id}: {str(e)}")


@router.websocket("/ingest")
async def pipeline_telemetry_ingest(websocket: WebSocket):
    """
    WebSocket endpoint for the active VideoPipeline background thread 
    to push analytics, bounding boxes, and security events.
    """
    await websocket.accept()
    logger.info("Pipeline telemetry publisher connected.")
    
    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                continue
            
            event_type = data.get("event_type")
            payload = data.get("payload", {})
            camera_id = str(payload.get("camera_id", "1"))
            
            # Broadcast the pipeline event to all Flutter / Next.js clients viewing this camera
            await manager.broadcast_to_camera(camera_id, {
                "event_type": event_type,
                "payload": payload
            })
            
    except WebSocketDisconnect:
        logger.warning("Pipeline telemetry publisher disconnected.")
    except Exception as e:
        logger.error(f"Telemetry ingestion error: {str(e)}")