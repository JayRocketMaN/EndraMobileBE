import os
import time

# --- Settings (set BEFORE the pipeline starts) -------------------------------
CAMERA_ID = "56b08f73-ebda-4b87-9822-3398c74da081"   # must match the id your viewer subscribes to
INGEST_URL = "ws://localhost:8000/ws/ingest"
INGEST_HEADERS = "X-User-ID=5"                       # remove if the ingest route needs no header

os.environ["ENDRA_ALLOW_ANY_VIDEO_PATH"] = "1"       # video lives outside media/test_videos
os.environ["ENDRA_WS_INGEST_URL"] = INGEST_URL       # (the old name TELEMETRY_WS_URL also works now)
os.environ["ENDRA_WS_INGEST_HEADERS"] = INGEST_HEADERS

from app.services.v_pipeline_2 import VideoPipeline # noqa: E402


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    video_path = os.path.join(base_dir, "media", "evidence", "clips", "livevid_crash0.mp4")

    pipeline = VideoPipeline(
        log_to_db=False,           # tests never write to the database
        # vlm_all_tracks=True,     # uncomment to send every vehicle to the VLM (slow on busy roads)
    )

    print("Starting test video pipeline and connecting to backend telemetry...")
    pipeline.start(
        video_path,
        camera_id=CAMERA_ID,
        camera_name="Traffic Camera",
        mode="video",
        loop=True,                 # keep replaying so telemetry keeps flowing; False = stop at end of file
        realtime=True,             # play at the video's own speed
    )
    print("Pipeline running. Press Ctrl+C to stop.")

    try:
        while pipeline.get_status()["running"]:
            time.sleep(1)
    except KeyboardInterrupt:
        pipeline.stop()
        print("Pipeline stopped by user.")

    status = pipeline.get_status()
    print(f"Final status: {status['status']}  frames analysed: {status['frames_analyzed']}")
    if pipeline.run_dir:
        print(f"Results: {os.path.abspath(pipeline.run_dir)}")


if __name__ == "__main__":
    main()