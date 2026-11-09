import asyncio
import os
from app.services.video_pipeline import VideoPipeline

async def start_ai_pipeline():
    # Set the ingest telemetry WebSocket URL environment variable or pass it 
    # so the internal pipeline thread knows where to push real-time events.
    os.environ["TELEMETRY_WS_URL"] = "ws://localhost:8000/api/v1/ws/ingest"

    # Instantiate the pipeline object
    pipeline = VideoPipeline()
    
    print("Starting test video pipeline and connecting to backend telemetry...")
    
    # Start the pipeline using the correct UUID matching your WebSocket client viewer
    pipeline.start(
        stream_source="media/evidence/clips/livevid_crash0.mp4",
        camera_id="56b08f73-ebda-4b87-9822-3398c74da081",
        camera_name="Traffic Camera"
    )

if __name__ == "__main__":
    asyncio.run(start_ai_pipeline())