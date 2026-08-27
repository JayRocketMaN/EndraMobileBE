import cv2
from typing import Optional


def build_universal_rtsp_url(
    ip: str,
    port: int = 554,
    username: str = "",
    password: str = "",
    maker: Optional[str] = None,
    channel: int = 1,
    custom_path: Optional[str] = None
) -> str:
    """
    Constructs an RTSP URL based on camera brand or custom path overrides.
    """
    # 1. Custom path explicitly supplied by frontend/user
    if custom_path and custom_path.strip():
        path = custom_path.strip().lstrip("/")
        return f"rtsp://{username}:{password}@{ip}:{port}/{path}"

    # 2. Auto-resolve stream path based on brand (maker)
    maker_lower = (maker or "").lower()
    
    if "dahua" in maker_lower or "amcrest" in maker_lower:
        path = f"cam/realmonitor?channel={channel}&subtype=0"
    elif "reolink" in maker_lower:
        path = f"h264Preview_{channel:02d}_main"
    elif "axis" in maker_lower:
        path = "axis-media/media.amp"
    else:
        # Default Hikvision / Generic ONVIF path
        path = f"h264/ch{channel}/main"

    return f"rtsp://{username}:{password}@{ip}:{port}/{path}"


def verify_rtsp_credentials(rtsp_url: str, timeout_ms: int = 3000) -> bool:
    """
    Synchronous validation of camera stream credentials and frame acquisition.
    Intended to be executed off the main async event loop via `run_in_threadpool`.
    """
    try:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)

        if not cap.isOpened():
            return False

        ret, frame = cap.read()
        cap.release()

        # Check if frame exists and has valid matrix dimensions
        return bool(ret and frame is not None and frame.size > 0)
    except Exception:
        return False