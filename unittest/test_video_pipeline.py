import asyncio
from app.services.video_pipeline import VideoPipeline  # Or wherever your file is imported from
from app.core.database import AsyncSessionLocal
from sqlalchemy.future import select
# Import your camera model if needed

async def start_ai_pipeline():
    # Instantiate the pipeline object
    pipeline = VideoPipeline()
    
    # Start the pipeline using the correct .start(...) method signature
    pipeline.start(
        stream_source="media/evidence/clips/mov_bbb.mp4",
        camera_id=1,
        camera_name="Scanned Backyard Camera"
    )

if __name__ == "__main__":
    asyncio.run(start_ai_pipeline())