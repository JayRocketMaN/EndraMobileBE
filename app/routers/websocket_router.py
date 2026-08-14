import json
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

router = APIRouter(prefix="/ws", tags=["Batch 2: WebSockets & Live Streaming"])


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
            self.active_connections[camera_id].remove(websocket)
            if not self.active_connections[camera_id]:
                del self.active_connections[camera_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_text(json.dumps(message))

    async def broadcast_to_camera(self, camera_id: str, message: dict):
        """Broadcasts events (e.g. motion detected) to all viewers of a camera."""
        if camera_id in self.active_connections:
            for connection in self.active_connections[camera_id]:
                await connection.send_text(json.dumps(message))


manager = ConnectionManager()


# ==========================================
# WEBSOCKET STREAMING & SIGNALING ENDPOINT
# ==========================================

@router.websocket("/live-stream/{camera_id}")
async def camera_websocket_endpoint(websocket: WebSocket, camera_id: str):
    """
    WebSocket endpoint for WebRTC SDP signaling (Offer/Answer) 
    and receiving live AI threat/event feeds for a camera.
    """
    await manager.connect(camera_id, websocket)
    
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
            # Receive text frames (e.g. SDP offers/answers, ping/pong, ICE candidates)
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            
            event_type = data.get("type")

            # 1. Handle WebRTC SDP Offer
            if event_type == "sdp_offer":
                sdp_offer = data.get("sdp")
                
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
                # Echo / process candidate
                await manager.send_personal_message(
                    {
                        "type": "ice_candidate_ack",
                        "camera_id": camera_id,
                        "candidate": candidate
                    },
                    websocket
                )

            # 3. Heartbeat / Ping-Pong
            elif event_type == "ping":
                await manager.send_personal_message({"type": "pong"}, websocket)

            else:
                await manager.send_personal_message(
                    {"type": "error", "detail": f"Unknown event type: {event_type}"},
                    websocket
                )

    except WebSocketDisconnect:
        manager.disconnect(camera_id, websocket)
        print(f"Client disconnected from camera channel: {camera_id}")
    except Exception as e:
        manager.disconnect(camera_id, websocket)
        print(f"WebSocket error on camera {camera_id}: {str(e)}")