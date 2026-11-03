"""
ENDRA video pipeline (single-file drop-in replacement)
=======================================================

One analytics core (YOLO seg + ByteTrack + baseline + Layer-2 VLM), two input
modes that are kept strictly apart:

  LIVE   rtsp:// | rtsps:// | rtmp:// | http(s):// | webcam index
         - background reader thread, always analyses the NEWEST frame (no lag build-up)
         - auto-reconnects when go2rtc / LetsView / the camera drops
         - writes events to the DB and evidence to ENDRA_EVIDENCE_DIR

  VIDEO  a file path (test footage)
         - deterministic: every frame is analysed, nothing is dropped
         - optional real-time pacing (for watching in Flutter) or max speed (for batch tests)
         - NEVER writes to the DB by default; everything lands in
           ENDRA_TEST_RUNS_DIR/<run_id>/ (events.jsonl, summary.json, VLM crops, evidence)
         - waits for the VLM to finish before closing the run, so summary.json is complete

The mode is auto-detected from the source string (override with mode="live"|"video").

Headless test run (no API server needed):
    python -m <your.module.path> path/to/clip.mp4 --all-tracks

Environment variables (all optional):
    ENDRA_YOLO_MODEL               yolo11n-seg.pt
    ENDRA_YOLO_IMGSZ               inference size, e.g. 640 (smaller = faster)
    ENDRA_EVIDENCE_DIR             ./media/evidence            (live evidence)
    ENDRA_TEST_VIDEO_DIR           ./media/test_videos         (video mode paths must live here)
    ENDRA_ALLOW_ANY_VIDEO_PATH     0                           (1 = allow paths outside that dir)
    ENDRA_TEST_RUNS_DIR            ./media/test_runs
    ENDRA_DATASET_DIR              ./media/dataset/hard_examples
    ENDRA_COLLECT_HARD_EXAMPLES    0                           (1 = save uncertain frames for labeling)
    ENDRA_VLM_MODEL                qwen2.5vl:3b
    ENDRA_VLM_COOLDOWN_SEC         20     per-track cooldown (video seconds in video mode)
    ENDRA_VLM_LOW_CONF             0.80   detections below this confidence go to the VLM
    ENDRA_VLM_ALL_TRACKS           0      1 = also send every target track once per cooldown
    ENDRA_VLM_GLOBAL_COOLDOWN_SEC  10     live only
    ENDRA_TEST_VLM_MAX_PENDING     16     video mode VLM queue size
    ENDRA_TEST_VLM_DRAIN_SEC       180    video mode: max wait for VLM at end of file
    ENDRA_MONITOR_PUBLISH_SEC      0.5    min seconds between MONITOR_DEVICE_UPDATE per track
    ENDRA_WS_INGEST_URL            ws://localhost:8000/api/v1/ws/ingest
    ENDRA_LOG_LEVEL                INFO
"""
from __future__ import annotations

import os

# Must be set before OpenCV opens its first stream: RTSP over TCP (UDP drops packets).
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import asyncio
import json
import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    from ultralytics import YOLO
    import supervision as sv
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

# The DB is optional so video tests can run headless without the app environment.
try:
    from app.core.database import SessionLocal
    from app.models.surveillance_model import AIEvent, AIEventType
    DB_AVAILABLE = True
except Exception as _db_exc:  # noqa: BLE001
    SessionLocal = AIEvent = AIEventType = None  # type: ignore[assignment]
    DB_AVAILABLE = False
    _DB_IMPORT_ERROR = _db_exc

logging.basicConfig(
    level=os.getenv("ENDRA_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger("endra.videopipeline")


# ==========================================
# Config helpers
# ==========================================

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


EVIDENCE_DIR = os.getenv("ENDRA_EVIDENCE_DIR", "./media/evidence")
TEST_RUNS_DIR = os.getenv("ENDRA_TEST_RUNS_DIR", "./media/test_runs")
TEST_VIDEO_DIR = os.getenv("ENDRA_TEST_VIDEO_DIR", "./media/test_videos")
DATASET_DIR = os.getenv("ENDRA_DATASET_DIR", "./media/dataset/hard_examples")

LIVE_SCHEMES = ("rtsp://", "rtsps://", "rtmp://", "http://", "https://", "udp://", "tcp://")


def _json_default(obj: Any):
    """Make numpy scalars/arrays JSON-serialisable (track ids are numpy ints)."""
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except (ValueError, TypeError):
            pass
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return str(obj)


# UI Incident Mapping Enum matching Flutter frontend selections
class IncidentCategory(str, Enum):
    INTRUSION = "Intrusion"
    FIRE = "Fire"
    THEFT = "Theft"
    SUSPICIOUS = "Suspicious"
    VIOLENCE = "Violence"
    MEDICAL = "Medical"
    VANDALISM = "Vandalism"


class UrgencyLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SourceMode(str, Enum):
    LIVE = "live"
    VIDEO = "video"


def detect_source_mode(source: Any) -> SourceMode:
    if isinstance(source, int):
        return SourceMode.LIVE
    text = str(source).strip()
    if text.isdigit() or text.lower().startswith(LIVE_SCHEMES):
        return SourceMode.LIVE
    return SourceMode.VIDEO


def resolve_test_video(path: str) -> str:
    """Resolve a test video path; by default it must live inside ENDRA_TEST_VIDEO_DIR."""
    base = os.path.realpath(TEST_VIDEO_DIR)
    allow_any = _env_bool("ENDRA_ALLOW_ANY_VIDEO_PATH", False)

    if os.path.isabs(path):
        candidate = path
    else:
        candidate = os.path.join(base, path)
        if allow_any and not os.path.isfile(candidate) and os.path.isfile(path):
            candidate = path  # relative to the working directory (CLI use)
    candidate = os.path.realpath(candidate)

    if not allow_any:
        try:
            inside = os.path.commonpath([base, candidate]) == base
        except ValueError:  # different drives on Windows
            inside = False
        if not inside:
            raise ValueError(
                f"Video must be inside {base} (or set ENDRA_ALLOW_ANY_VIDEO_PATH=1)."
            )
    if not os.path.isfile(candidate):
        raise FileNotFoundError(f"Test video not found: {candidate}")
    return candidate


# ==========================================
# 1. FRAME SOURCES (the only thing that differs between live and test)
# ==========================================

class FrameSource(ABC):
    mode: SourceMode
    fps: float = 30.0
    finished: bool = False

    @abstractmethod
    def read(self) -> Optional[Tuple[Any, float]]:
        """Return (frame, timestamp_seconds) or None. None + finished=False means 'no new frame yet'."""

    @abstractmethod
    def stop(self) -> None:
        ...


class LiveSource(FrameSource):
    """Reads in its own thread, keeps only the newest frame, reconnects on failure."""

    mode = SourceMode.LIVE

    def __init__(self, url: Any):
        text = str(url).strip()
        self.url: Any = int(text) if text.isdigit() else text
        self.fps = 30.0
        self.finished = False
        self.connected = False
        self.last_frame_at = 0.0
        self._latest: Optional[Tuple[Any, float]] = None
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="endra-live-reader")
        self._thread.start()

    def _open(self):
        if isinstance(self.url, int):
            return cv2.VideoCapture(self.url)
        return cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

    def _loop(self):
        while self._running:
            cap = self._open()
            if not cap.isOpened():
                logger.warning(f"[LIVE] Could not open {self.url}; retrying in 3s")
                cap.release()
                self._sleep(3.0)
                continue

            logger.info(f"[LIVE] Connected: {self.url}")
            self.connected = True
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    logger.warning("[LIVE] Read failed; reconnecting")
                    break
                now = time.time()
                self.last_frame_at = now
                with self._lock:
                    self._latest = (frame, now)
            self.connected = False
            cap.release()
            self._sleep(1.0)

    def _sleep(self, seconds: float):
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(0.1)

    def read(self) -> Optional[Tuple[Any, float]]:
        with self._lock:
            packet, self._latest = self._latest, None  # each frame is handed out once
        return packet

    def stop(self) -> None:
        self._running = False


class VideoFileSource(FrameSource):
    """Deterministic file playback: every frame is returned, in order."""

    mode = SourceMode.VIDEO

    def __init__(self, path: str, loop: bool = False, realtime: bool = True,
                 frame_stride: int = 1, max_frames: Optional[int] = None):
        self.path = path
        self.loop = loop
        self.realtime = realtime
        self.frame_stride = max(1, int(frame_stride))
        self.max_frames = max_frames
        self.finished = False

        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            self._cap.release()
            raise RuntimeError(f"OpenCV could not open video: {path}")

        fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.fps = fps if fps > 1.0 else 30.0
        self.total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        self._index = 0           # frame index within the current pass
        self._ts_base = 0.0       # keeps timestamps increasing across loops
        self._returned = 0
        self._wall_start: Optional[float] = None

    def read(self) -> Optional[Tuple[Any, float]]:
        while not self.finished:
            ok, frame = self._cap.read()
            if not ok:
                if self.loop and self._index > 0:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self._ts_base += self._index / self.fps
                    self._index = 0
                    continue
                self.finished = True
                return None

            idx = self._index
            self._index += 1
            if self.frame_stride > 1 and idx % self.frame_stride:
                continue
            if self.max_frames and self._returned >= self.max_frames:
                self.finished = True
                return None

            ts = self._ts_base + idx / self.fps
            self._returned += 1

            if self.realtime:
                if self._wall_start is None:
                    self._wall_start = time.time()
                delay = self._wall_start + ts - time.time()
                if delay > 0:
                    time.sleep(delay)
            return frame, ts
        return None

    def stop(self) -> None:
        self.finished = True
        try:
            self._cap.release()
        except Exception:  # noqa: BLE001
            pass


# ==========================================
# 2. TELEMETRY (WebSocket to the backend ingest -> Flutter)
# ==========================================

class TelemetryPublisher:
    """Async background worker for streaming pipeline inferences over WebSocket to Flutter UI."""

    def __init__(self, ingest_url: Optional[str] = None):
        self.ingest_url = ingest_url or os.getenv("ENDRA_WS_INGEST_URL", "ws://localhost:8000/api/v1/ws/ingest")
        self._queue: deque = deque(maxlen=300)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="endra-ws-publisher")
        self._is_running = False

    def start(self):
        if not WEBSOCKETS_AVAILABLE:
            logger.warning("[WS PUBLISHER] 'websockets' missing. Telemetry streaming disabled.")
            return
        self._is_running = True
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_stream())
        finally:
            self._loop.close()

    async def _connect_and_stream(self):
        while self._is_running:
            try:
                async with websockets.connect(self.ingest_url) as ws:
                    logger.info(f"[WS PUBLISHER] Stream connected: {self.ingest_url}")
                    while self._is_running:
                        if self._queue:
                            event_data = self._queue.popleft()
                            await ws.send(json.dumps(event_data, default=_json_default))
                        else:
                            await asyncio.sleep(0.01)
            except Exception as e:  # noqa: BLE001
                if not self._is_running:
                    break
                logger.error(f"[WS PUBLISHER] Connection dropped ({e}). Retry in 3s...")
                await asyncio.sleep(3)

    def publish(self, event_type: str, camera_id: int, payload_data: Dict[str, Any]):
        if not WEBSOCKETS_AVAILABLE or not self._is_running:
            return

        self._queue.append({
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"camera_id": camera_id, **payload_data}
        })

    def stop(self):
        self._is_running = False  # the loop exits on its own and closes itself


# ==========================================
# 3. LAYER 2 VLM
# ==========================================

class CloudVLMService:
    """Async Layer 2 VLM scene understanding service tailored for ENDRA Security Center."""

    def __init__(
        self,
        model: Optional[str] = None,
        max_concurrency: int = 1,
        max_pending: int = 2,
        global_cooldown_sec: float = 10.0,
        on_result=None,
    ):
        self.model = model or os.getenv("ENDRA_VLM_MODEL", "qwen2.5vl:3b")
        self.max_concurrency = max_concurrency
        self.max_pending = max_pending
        self.global_cooldown_sec = global_cooldown_sec
        self.on_result = on_result

        self._pending = 0
        self._last_submit_time = 0.0
        self._lock = threading.Lock()

        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._sem = None

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="endra-vlm-loop")
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)

        async def _setup():
            self._sem = asyncio.Semaphore(self.max_concurrency)
            self._ready.set()

        try:
            self._loop.run_until_complete(_setup())
            self._loop.run_forever()
        except Exception:  # noqa: BLE001
            logger.exception("[LAYER 2] VLM event loop crashed.")
            self._ready.set()

    def submit(self, crop, event_context: str, meta: Optional[Dict[str, Any]] = None) -> bool:
        """Returns True if the crop was queued, False if it was dropped (cooldown / queue full)."""
        if not OLLAMA_AVAILABLE or crop is None or getattr(crop, "size", 0) == 0:
            return False

        now = time.time()
        with self._lock:
            if self.global_cooldown_sec > 0 and now - self._last_submit_time < self.global_cooldown_sec:
                return False
            if self._pending >= self.max_pending:
                return False
            self._pending += 1
            self._last_submit_time = now

        crop_copy = crop.copy() if hasattr(crop, "copy") else crop
        meta = meta or {}

        try:
            if self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._guarded_analyze(crop_copy, event_context, meta), self._loop
                )
                return True
        except Exception:  # noqa: BLE001
            pass

        with self._lock:
            self._pending = max(0, self._pending - 1)
        return False

    def wait_idle(self, timeout: float = 120.0, should_abort: Optional[Callable[[], bool]] = None) -> bool:
        """Block until every queued crop has been analysed (used at the end of a test video)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._pending == 0:
                    return True
            if should_abort and should_abort():
                return False
            time.sleep(0.25)
        return False

    async def _guarded_analyze(self, crop, event_context: str, meta: Dict[str, Any]):
        try:
            await self._analyze(crop, event_context, meta)
        finally:
            with self._lock:
                self._pending = max(0, self._pending - 1)

    async def _analyze(self, crop, event_context: str, meta: Dict[str, Any]):
        if self._sem is None:
            return

        async with self._sem:
            image_bytes = await asyncio.to_thread(self._encode_jpeg_bytes, crop)
            if not image_bytes:
                return

            prompt = self._build_prompt(event_context, meta)
            loop = asyncio.get_running_loop()
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: ollama.chat(
                        model=self.model,
                        messages=[{
                            'role': 'system',
                            'content': "You are ENDRA Layer 2, a security threat detection VLM. Output ONLY strict JSON."
                        }, {
                            'role': 'user',
                            'content': prompt,
                            'images': [image_bytes]
                        }],
                        format="json"
                    )
                )

                content = response.get('message', {}).get('content', '')
                parsed = self._extract_json(content)

                if self.on_result:
                    await asyncio.to_thread(self.on_result, parsed, meta)

            except Exception as err:  # noqa: BLE001
                logger.error(f"[LAYER 2] VLM execution failed: {err}")

    @staticmethod
    def _encode_jpeg_bytes(crop, max_side: int = 768, quality: int = 82) -> bytes:
        if crop is None or getattr(crop, "size", 0) == 0 or not CV_AVAILABLE:
            return b""
        h, w = crop.shape[:2]
        scale = min(1.0, max_side / float(max(h, w)))
        if scale < 1.0:
            crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return buf.tobytes() if ok else b""

    def _build_prompt(self, event_context: str, meta: Dict[str, Any]) -> str:
        safe_meta = {
            "label": meta.get("label"),
            "confidence": meta.get("confidence"),
            "camera_name": meta.get("camera_name", "Gate Cam — Front Entrance"),
            "trigger": meta.get("trigger"),
        }
        return f"""Analyze this cropped security clip.
Context: {event_context}
Metadata: {json.dumps(safe_meta, default=_json_default)}
Output JSON shape:
{{
  "category": "Intrusion" | "Suspicious" | "Theft" | "Violence" | "Vandalism" | "None",
  "urgency": "High" | "Medium" | "Low",
  "confidence": 0-100,
  "description": "Short incident summary",
  "security_relevance": true/false,
  "dispatch_recommended": true/false
}}"""

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        if not text:
            return {"category": "None", "confidence": 0, "security_relevance": False}
        text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:  # noqa: BLE001
                    pass
        return {"category": "None", "confidence": 0, "security_relevance": False}

    def shutdown(self):
        try:
            if self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread.is_alive():
                self._thread.join(timeout=2)
        except Exception:  # noqa: BLE001
            pass


# ==========================================
# 4. TEST-RUN RECORDER + TRAINING-DATA COLLECTOR
# ==========================================

class RunRecorder:
    """Video-mode only: writes events.jsonl while running and summary.json at the end."""

    def __init__(self, run_dir: str, meta: Dict[str, Any]):
        self.dir = run_dir
        self.meta = meta
        os.makedirs(self.dir, exist_ok=True)
        self._events = open(os.path.join(self.dir, "events.jsonl"), "a", encoding="utf-8")
        self._tracks: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._baseline_anomalies = 0
        self._vlm_results = 0

    def log_event(self, event_type: str, camera_id: int, video_ts: float, payload: Dict[str, Any]):
        if event_type == "BASELINE_ANOMALY":
            self._baseline_anomalies += 1
        line = {"video_ts": round(video_ts, 3), "event_type": event_type,
                "camera_id": camera_id, "payload": payload}
        with self._lock:
            self._events.write(json.dumps(line, default=_json_default) + "\n")
            self._events.flush()

    def update_track(self, track_id: int, label: str, confidence: float, ts: float):
        with self._lock:
            t = self._tracks.get(track_id)
            if t is None:
                t = self._tracks[track_id] = {
                    "track_id": track_id, "label": label, "first_ts": round(ts, 3),
                    "last_ts": round(ts, 3), "frames": 0, "conf_min": confidence,
                    "conf_max": confidence, "_conf_sum": 0.0, "vlm": []
                }
            t["label"] = label
            t["last_ts"] = round(ts, 3)
            t["frames"] += 1
            t["_conf_sum"] += confidence
            t["conf_min"] = min(t["conf_min"], confidence)
            t["conf_max"] = max(t["conf_max"], confidence)

    def add_vlm_result(self, track_id: Optional[int], video_ts: Optional[float],
                       parsed: Dict[str, Any], crop_path: Optional[str]):
        entry = {"video_ts": video_ts, "crop": crop_path, "result": parsed}
        with self._lock:
            self._vlm_results += 1
            if track_id is not None and int(track_id) in self._tracks:
                self._tracks[int(track_id)]["vlm"].append(entry)
            self._events.write(json.dumps(
                {"video_ts": video_ts, "event_type": "VLM_RESULT",
                 "track_id": track_id, "payload": entry}, default=_json_default) + "\n")
            self._events.flush()

    def close(self, extra: Dict[str, Any]):
        with self._lock:
            tracks = []
            for t in self._tracks.values():
                item = {k: v for k, v in t.items() if not k.startswith("_")}
                item["conf_avg"] = round(t["_conf_sum"] / max(1, t["frames"]), 3)
                item["conf_min"] = round(item["conf_min"], 3)
                item["conf_max"] = round(item["conf_max"], 3)
                tracks.append(item)
            tracks.sort(key=lambda x: x["first_ts"])
            summary = {**self.meta, **extra, "baseline_anomalies": self._baseline_anomalies,
                       "vlm_results": self._vlm_results, "tracks": tracks}
            with open(os.path.join(self.dir, "summary.json"), "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2, default=_json_default)
            try:
                self._events.close()
            except Exception:  # noqa: BLE001
                pass


class HardExampleCollector:
    """Saves uncertain frames + model pre-annotations (YOLO txt) for labeling and fine-tuning.

    The .txt files are model PREDICTIONS (boxes only), not ground truth: review them in a
    labeling tool (CVAT / Label Studio / Roboflow) before training.
    """

    def __init__(self, root: str, tag: str, min_interval_sec: float = 2.0, max_images: int = 500):
        self.img_dir = os.path.join(root, "images")
        self.lbl_dir = os.path.join(root, "labels")
        os.makedirs(self.img_dir, exist_ok=True)
        os.makedirs(self.lbl_dir, exist_ok=True)
        self.root = root
        self.tag = tag
        self.min_interval_sec = min_interval_sec
        self.max_images = max_images
        self._last_ts = -1e12
        self._count = 0
        self._classes_written = False

    def maybe_save(self, frame, boxes_xyxy, class_ids, names: Dict[int, str], ts: float) -> Optional[str]:
        if self._count >= self.max_images or ts - self._last_ts < self.min_interval_sec:
            return None
        self._last_ts = ts
        h, w = frame.shape[:2]
        stem = f"{self.tag}_{self._count:05d}"
        img_path = os.path.join(self.img_dir, stem + ".jpg")
        if not cv2.imwrite(img_path, frame):
            return None

        lines = []
        for (x1, y1, x2, y2), cid in zip(boxes_xyxy, class_ids):
            cx = min(max(((x1 + x2) / 2.0) / w, 0.0), 1.0)
            cy = min(max(((y1 + y2) / 2.0) / h, 0.0), 1.0)
            bw = min(max((x2 - x1) / w, 0.0), 1.0)
            bh = min(max((y2 - y1) / h, 0.0), 1.0)
            lines.append(f"{int(cid)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        with open(os.path.join(self.lbl_dir, stem + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        if not self._classes_written:
            with open(os.path.join(self.root, "classes.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(f"{i}: {n}" for i, n in sorted(names.items())))
            self._classes_written = True

        self._count += 1
        return img_path


# ==========================================
# 5. THE PIPELINE
# ==========================================

class VideoPipeline:
    def __init__(
        self,
        seg_model_path: Optional[str] = None,
        confidence_threshold: float = 0.4,
        min_motion_area: int = 500,
        buffer_seconds: int = 5,
        target_fps: int = 30,
        storage_dir: Optional[str] = None,
        log_to_db: Optional[bool] = None,
        publish_telemetry: bool = True,
        collect_hard_examples: Optional[bool] = None,
        vlm_all_tracks: Optional[bool] = None,
    ):
        self.seg_model_path = seg_model_path or os.getenv("ENDRA_YOLO_MODEL", "yolo11n-seg.pt")
        self.confidence_threshold = confidence_threshold
        self.min_motion_area = min_motion_area
        self.buffer_seconds = buffer_seconds
        self.target_fps = target_fps
        self.storage_dir = storage_dir or EVIDENCE_DIR

        # None = decide per mode at start(): live -> DB on, video -> DB off
        self._log_to_db_opt = log_to_db
        self.publish_telemetry = publish_telemetry
        self._collect_opt = collect_hard_examples
        self._vlm_all_opt = vlm_all_tracks

        self.baseline_stats = {"people": 0.0, "vehicles": 0.0, "sample_count": 0}
        self.system_health_score = 82  # Matches UI 82% system health gauge

        self.vlm_cooldown_sec = _env_float("ENDRA_VLM_COOLDOWN_SEC", 20.0)
        self.vlm_low_conf_threshold = _env_float("ENDRA_VLM_LOW_CONF", 0.80)
        self.vlm_drain_timeout = _env_float("ENDRA_TEST_VLM_DRAIN_SEC", 180.0)
        self.monitor_publish_sec = _env_float("ENDRA_MONITOR_PUBLISH_SEC", 0.5)
        self.vlm_target_classes = {"person", "backpack", "handbag", "suitcase", "bicycle", "car", "motorcycle"}
        self.last_vlm_at: Dict[str, float] = {}
        self._last_monitor_pub: Dict[int, float] = {}

        # runtime state (filled in start())
        self.mode: Optional[SourceMode] = None
        self.source: Optional[FrameSource] = None
        self.source_label = ""
        self.run_id: Optional[str] = None
        self.run_dir: Optional[str] = None
        self.evidence_dir = self.storage_dir
        self.log_to_db = False
        self.vlm_all_tracks = False
        self.publisher: Optional[TelemetryPublisher] = None
        self.vlm_client: Optional[CloudVLMService] = None
        self.recorder: Optional[RunRecorder] = None
        self.collector: Optional[HardExampleCollector] = None
        self.status = "idle"   # idle | starting | running | finishing | finished | stopped | error
        self.error: Optional[str] = None

        self._is_running = False
        self._finalized = True
        self._final_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.active_camera_id: Optional[int] = None
        self.camera_name = "Gate Cam — Front Entrance"

        self.lock = threading.Lock()
        self.latest_frame = None
        self.on_alert_callback = None

        self._buffer: deque = deque(maxlen=max(1, target_fps * buffer_seconds))
        self._buffer_lock = threading.Lock()
        self._track_kwargs: Dict[str, Any] = {}
        self._last_ts = 0.0
        self._counters = {"frames_total": 0, "frames_motion": 0, "frames_analyzed": 0,
                          "vlm_submitted": 0, "vlm_dropped": 0}

    # ---------- lifecycle ----------

    def start(
        self,
        stream_source,
        camera_id: int,
        camera_name: str = "Gate Cam — Front Entrance",
        *,
        mode: Optional[str] = None,
        loop: bool = False,
        realtime: bool = True,
        frame_stride: int = 1,
        max_frames: Optional[int] = None,
        run_label: Optional[str] = None,
    ):
        if not CV_AVAILABLE:
            raise RuntimeError("OpenCV / YOLO dependencies missing.")
        if self._is_running:
            return False

        resolved = SourceMode(mode.lower()) if mode else detect_source_mode(stream_source)

        # Build the source first so a bad path fails fast, before any threads exist.
        video_path = None
        if resolved is SourceMode.VIDEO:
            video_path = resolve_test_video(str(stream_source))
            source: FrameSource = VideoFileSource(
                video_path, loop=loop, realtime=realtime,
                frame_stride=frame_stride, max_frames=max_frames)
            self.source_label = video_path
        else:
            source = LiveSource(stream_source)
            self.source_label = str(stream_source)

        self.mode = resolved
        self.source = source
        self.active_camera_id = camera_id
        self.camera_name = camera_name
        self.error = None
        self.status = "starting"
        self.latest_frame = None
        self.last_vlm_at = {}
        self._last_monitor_pub = {}
        self._last_ts = 0.0
        self._counters = {k: 0 for k in self._counters}
        self.baseline_stats = {"people": 0.0, "vehicles": 0.0, "sample_count": 0}
        self.target_fps = max(1, int(round(source.fps)))
        with self._buffer_lock:
            self._buffer = deque(maxlen=max(1, int(self.target_fps * self.buffer_seconds)))

        # Per-mode output locations
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if resolved is SourceMode.VIDEO:
            stem = run_label or os.path.splitext(os.path.basename(video_path))[0]
            stem = re.sub(r"[^A-Za-z0-9_.-]", "_", stem)
            self.run_id = f"{stamp}_{stem}"
            self.run_dir = os.path.join(TEST_RUNS_DIR, self.run_id)
            self.evidence_dir = os.path.join(self.run_dir, "evidence")
        else:
            self.run_id = f"live_{stamp}"
            self.run_dir = None
            self.evidence_dir = self.storage_dir
        for sub in ("snapshots", "clips"):
            os.makedirs(os.path.join(self.evidence_dir, sub), exist_ok=True)

        # Per-mode policies
        self.log_to_db = self._log_to_db_opt if self._log_to_db_opt is not None else (resolved is SourceMode.LIVE)
        if self.log_to_db and not DB_AVAILABLE:
            logger.warning(f"[PIPELINE] DB unavailable ({_DB_IMPORT_ERROR}); events will not be stored.")
        self.vlm_all_tracks = (self._vlm_all_opt if self._vlm_all_opt is not None
                               else _env_bool("ENDRA_VLM_ALL_TRACKS", False))
        collect = (self._collect_opt if self._collect_opt is not None
                   else _env_bool("ENDRA_COLLECT_HARD_EXAMPLES", False))

        self._track_kwargs = dict(persist=True, tracker="bytetrack.yaml",
                                  conf=self.confidence_threshold, verbose=False)
        imgsz = _env_int("ENDRA_YOLO_IMGSZ", 0)
        if imgsz:
            self._track_kwargs["imgsz"] = imgsz

        if not OLLAMA_AVAILABLE:
            logger.warning("[LAYER 2] 'ollama' package missing: VLM analysis is disabled.")

        try:
            self.collector = (HardExampleCollector(os.path.join(DATASET_DIR, resolved.value), self.run_id)
                              if collect else None)
            self.recorder = None
            if resolved is SourceMode.VIDEO:
                self.recorder = RunRecorder(self.run_dir, {
                    "run_id": self.run_id, "mode": "video", "camera_id": camera_id,
                    "source": video_path, "source_fps": source.fps,
                    "total_frames_in_file": getattr(source, "total_frames", None),
                    "realtime": realtime, "loop": loop, "frame_stride": frame_stride,
                    "yolo_model": self.seg_model_path, "vlm_model": os.getenv("ENDRA_VLM_MODEL", "qwen2.5vl:3b"),
                    "vlm_all_tracks": self.vlm_all_tracks,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                })

            self.publisher = None
            if self.publish_telemetry:
                self.publisher = TelemetryPublisher()
                self.publisher.start()

            if resolved is SourceMode.VIDEO:
                self.vlm_client = CloudVLMService(
                    max_pending=_env_int("ENDRA_TEST_VLM_MAX_PENDING", 16),
                    global_cooldown_sec=0.0,
                    on_result=self._handle_vlm_result)
            else:
                self.vlm_client = CloudVLMService(
                    global_cooldown_sec=_env_float("ENDRA_VLM_GLOBAL_COOLDOWN_SEC", 10.0),
                    on_result=self._handle_vlm_result)

            self._finalized = False
            self._is_running = True
            self._thread = threading.Thread(
                target=self._run_pipeline, args=(source, camera_id), daemon=True, name="endra-pipeline")
            self._thread.start()
        except Exception:
            self._is_running = False
            self._finalize("error")
            raise

        logger.info(f"[PIPELINE] Started camera={camera_id} mode={resolved.value} source={self.source_label}")
        return True

    def stop(self):
        was_running = self._is_running
        self._is_running = False
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        self._finalize("stopped")
        return was_running

    def _finalize(self, final_status: str):
        """Idempotent teardown; safe to call from the pipeline thread and from stop()."""
        with self._final_lock:
            if self._finalized:
                return
            self._finalized = True

        if self.source:
            self.source.stop()
        if self.recorder:
            try:
                self.recorder.close({
                    "status": final_status,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "video_seconds_processed": round(self._last_ts, 3),
                    **{f"count_{k}": v for k, v in self._counters.items()},
                    "error": self.error,
                })
            except Exception:  # noqa: BLE001
                logger.exception("[PIPELINE] Could not write summary.json")
        if self.publisher:
            self.publisher.stop()
        if self.vlm_client:
            self.vlm_client.shutdown()
        self.status = final_status
        logger.info(f"[PIPELINE] Camera {self.active_camera_id} {final_status}"
                    + (f" (run dir: {self.run_dir})" if self.run_dir else ""))

    def get_status(self) -> Dict[str, Any]:
        return {
            "camera_id": self.active_camera_id,
            "status": self.status,
            "running": self._is_running,
            "mode": self.mode.value if self.mode else None,
            "source": self.source_label,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "log_to_db": self.log_to_db,
            "live_connected": getattr(self.source, "connected", None),
            "error": self.error,
            **self._counters,
        }

    # ---------- MJPEG feed ----------

    def generate_frames(self):
        while self._is_running:
            frame_to_process = None
            with self.lock:
                if self.latest_frame is not None:
                    frame_to_process = self.latest_frame.copy()

            if frame_to_process is None:
                time.sleep(0.03)
                continue

            success, buffer = cv2.imencode('.jpg', frame_to_process, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if not success:
                continue

            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.033)

    def _set_latest(self, frame):
        with self.lock:
            self.latest_frame = frame

    # ---------- event plumbing ----------

    def _emit(self, event_type: str, camera_id: int, payload: Dict[str, Any]):
        if self.publisher:
            self.publisher.publish(event_type=event_type, camera_id=camera_id, payload_data=payload)
        if self.recorder and event_type != "MONITOR_DEVICE_UPDATE":
            self.recorder.log_event(event_type, camera_id, self._last_ts, payload)

    def submit_user_report(
        self,
        camera_name: str,
        incident_type: IncidentCategory,
        urgency: UrgencyLevel,
        description: str,
        evidence_photo_path: Optional[str] = None,
        notify_monitoring_center: bool = True
    ) -> Dict[str, Any]:
        """Direct API hook for user-submitted reports from `/activity`."""
        report_id = f"RPT-{int(time.time())}"

        payload = {
            "report_id": report_id,
            "camera_name": camera_name,
            "incident_type": incident_type.value,
            "urgency_level": urgency.value,
            "description": description,
            "notify_monitoring_center": notify_monitoring_center,
            "evidence_attached": evidence_photo_path is not None,
            "timestamp": time.time()
        }

        self._emit("USER_SUBMITTED_REPORT", self.active_camera_id or 1, payload)
        return payload

    # ---------- evidence ----------

    def _buffer_frame(self, frame, ts: float):
        """Ring buffer of JPEG bytes (~100x smaller than raw frames)."""
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok:
            with self._buffer_lock:
                self._buffer.append((ts, buf.tobytes()))

    def _save_snapshot(self, frame, event_id: str) -> Optional[str]:
        if frame is None or not CV_AVAILABLE:
            return None
        try:
            filename = f"snapshot_{event_id}_{int(time.time())}.jpg"
            filepath = os.path.join(self.evidence_dir, "snapshots", filename)
            cv2.imwrite(filepath, frame)
            return filepath
        except Exception as e:  # noqa: BLE001
            logger.error(f"Snapshot capture error: {e}")
            return None

    def _record_video_clip(self, packets: List[Tuple[float, bytes]], filepath: str, frame_shape: tuple):
        if len(packets) < 2 or not CV_AVAILABLE:
            return
        out = None
        try:
            span = packets[-1][0] - packets[0][0]
            fps = (len(packets) - 1) / span if span > 0 else float(self.target_fps)
            fps = max(1.0, min(60.0, fps))
            h, w = frame_shape[:2]
            out = cv2.VideoWriter(filepath, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
            for _ts, jpg in packets:
                img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                if img.shape[:2] != (h, w):
                    img = cv2.resize(img, (w, h))
                out.write(img)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Video clip record error: {e}")
        finally:
            if out is not None:
                out.release()

    def _log_event_to_db(self, camera_id: int, event_type, confidence: float,
                         details: str = "", frame=None):
        if not (self.log_to_db and DB_AVAILABLE):
            return
        with SessionLocal() as db:
            try:
                event_key = f"{camera_id}_{event_type.value}_{int(time.time())}"
                snapshot_path = self._save_snapshot(frame, event_key) if frame is not None else None

                clip_path = None
                if frame is not None:
                    with self._buffer_lock:
                        packets = list(self._buffer)
                    if packets:
                        clip_path = os.path.join(self.evidence_dir, "clips", f"clip_{event_key}.mp4")
                        threading.Thread(
                            target=self._record_video_clip,
                            args=(packets, clip_path, frame.shape),
                            daemon=True
                        ).start()

                db_event = AIEvent(
                    camera_id=camera_id,
                    event_type=event_type,
                    confidence_score=float(confidence),
                    snapshot_url=snapshot_path,
                    video_clip_url=clip_path
                )
                if hasattr(db_event, "details"):
                    db_event.details = details

                db.add(db_event)
                db.commit()

                if self.on_alert_callback:
                    self.on_alert_callback({
                        "camera_id": camera_id,
                        "event_type": event_type.value,
                        "confidence_score": round(float(confidence), 2),
                        "details": details,
                        "snapshot_url": snapshot_path,
                        "timestamp": time.time()
                    })
            except Exception as e:  # noqa: BLE001
                logger.error(f"Database write error: {e}")
                db.rollback()

    # ---------- analytics ----------

    def _update_and_check_baseline(self, people_count: int, vehicle_count: int) -> Tuple[bool, str]:
        alpha = 0.05
        if self.baseline_stats["sample_count"] == 0:
            self.baseline_stats["people"] = float(people_count)
            self.baseline_stats["vehicles"] = float(vehicle_count)
        else:
            self.baseline_stats["people"] = (1 - alpha) * self.baseline_stats["people"] + alpha * people_count
            self.baseline_stats["vehicles"] = (1 - alpha) * self.baseline_stats["vehicles"] + alpha * vehicle_count

        self.baseline_stats["sample_count"] += 1
        expected = self.baseline_stats["people"]

        if self.baseline_stats["sample_count"] > 30 and people_count > (expected * 2.5) and people_count >= 3:
            return True, f"Environmental Surge: {people_count} individuals detected at {self.camera_name}."

        return False, "Normal"

    def _make_context_crop(self, frame, xyxy, frame_width: int, frame_height: int, pad_ratio: float = 0.35):
        if frame is None or not CV_AVAILABLE:
            return None
        x1, y1, x2, y2 = map(int, xyxy)
        w, h = max(1, x2 - x1), max(1, y2 - y1)
        pad = int(max(w, h) * pad_ratio)

        cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
        cx2, cy2 = min(frame_width, x2 + pad), min(frame_height, y2 + pad)
        return frame[cy1:cy2, cx1:cx2]

    def _maybe_trigger_vlm(self, camera_id: int, track_id: int, crop, context_msg: str,
                           meta: Dict[str, Any], ts: float):
        if crop is None or getattr(crop, "size", 0) == 0 or self.vlm_client is None:
            return

        key = f"{camera_id}:{track_id}"
        # Cooldown runs on SOURCE time, so a fast offline test behaves like real time.
        if ts - self.last_vlm_at.get(key, -1e12) < self.vlm_cooldown_sec:
            return

        meta["video_ts"] = round(ts, 3)
        if self.recorder:
            crop_path = os.path.join(self.run_dir, "vlm_crops", f"track{track_id}_{ts:010.2f}.jpg")
            os.makedirs(os.path.dirname(crop_path), exist_ok=True)
            if cv2.imwrite(crop_path, crop):
                meta["crop_path"] = crop_path

        if self.vlm_client.submit(crop, context_msg, meta):
            self.last_vlm_at[key] = ts
            self._counters["vlm_submitted"] += 1
            self._emit("LAYER2_VLM_TRIGGER", camera_id, {
                "trigger_reason": context_msg,
                "confidence": float(meta.get("confidence", 0.0)),
                "label": meta.get("label"),
                "track_id": track_id
            })
        else:
            self._counters["vlm_dropped"] += 1

    def _handle_vlm_result(self, parsed: Dict[str, Any], meta: Dict[str, Any]):
        try:
            if self.recorder:
                self.recorder.add_vlm_result(meta.get("track_id"), meta.get("video_ts"),
                                             parsed, meta.get("crop_path"))

            if not isinstance(parsed, dict) or not parsed.get("security_relevance", False):
                return

            confidence = float(parsed.get("confidence", 80))
            if confidence < 60:
                return

            camera_id = meta.get("camera_id")
            category = parsed.get("category", IncidentCategory.SUSPICIOUS.value)
            urgency = parsed.get("urgency", UrgencyLevel.HIGH.value)

            payload = {
                "title": f"Unknown {category}",
                "location": self.camera_name,
                "urgency": urgency,
                "description": parsed.get("description", "Potential security anomaly detected."),
                "dispatch_recommended": parsed.get("dispatch_recommended", True),
                "timestamp_str": "Just now"
            }

            # 1. Update Recent Activity Feed (/login dashboard)
            self._emit("RECENT_ACTIVITY_UPDATE", camera_id, payload)

            # 2. Trigger Auto Responder Dispatch Message (/login/messages)
            if parsed.get("dispatch_recommended", False):
                self._emit("RESPONDER_DISPATCH_TRIGGER", camera_id, {
                    "channel": "ENDRA Command Center",
                    "status_message": "Responder dispatched to your location.",
                    "eta_minutes": 8
                })

            if self.log_to_db and DB_AVAILABLE:
                self._log_event_to_db(
                    camera_id=camera_id,
                    event_type=getattr(AIEventType, "VLM_ALERT", AIEventType.ANOMALOUS_BEHAVIOR),
                    confidence=confidence / 100.0,
                    details=json.dumps(payload),
                    frame=self.latest_frame
                )
        except Exception:  # noqa: BLE001
            logger.exception("[LAYER 2] Failed handling VLM result.")

    # ---------- main loop ----------

    def _run_pipeline(self, source: FrameSource, camera_id: int):
        final_status = "stopped"
        natural_end = False
        try:
            seg_model = YOLO(self.seg_model_path)
            annotators = (
                sv.MaskAnnotator(color_lookup=sv.ColorLookup.INDEX),
                sv.BoxAnnotator(thickness=2),
                sv.LabelAnnotator(text_scale=0.5, text_thickness=1),
            )
            bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)
            self.status = "running"

            while self._is_running:
                packet = source.read()
                if packet is None:
                    if source.finished:
                        natural_end = True
                        break
                    time.sleep(0.005)  # live: no new frame yet
                    continue
                frame, ts = packet
                self._process_frame(frame, ts, camera_id, seg_model, annotators, bg_subtractor)

            final_status = "finished" if natural_end else "stopped"
        except Exception as exc:  # noqa: BLE001
            logger.exception("[PIPELINE] Crashed")
            self.error = str(exc)
            final_status = "error"
        finally:
            try:
                # Test videos: let the VLM finish so summary.json contains every result.
                if natural_end and self.vlm_client is not None:
                    self.status = "finishing"
                    self.vlm_client.wait_idle(self.vlm_drain_timeout,
                                              should_abort=lambda: not self._is_running)
            except Exception:  # noqa: BLE001
                logger.exception("[PIPELINE] VLM drain failed")
            self._is_running = False
            self._finalize(final_status)

    def _process_frame(self, frame, ts: float, camera_id: int, seg_model, annotators, bg_subtractor):
        mask_annotator, box_annotator, label_annotator = annotators
        self._counters["frames_total"] += 1
        self._last_ts = ts
        frame_h, frame_w = frame.shape[:2]
        self._buffer_frame(frame, ts)

        fg_mask = bg_subtractor.apply(frame)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        if cv2.countNonZero(thresh) < self.min_motion_area:
            self._set_latest(frame)
            return
        self._counters["frames_motion"] += 1

        seg_results = seg_model.track(frame, **self._track_kwargs)
        if not seg_results:
            self._set_latest(frame)
            return

        result = seg_results[0]
        detections = sv.Detections.from_ultralytics(result)
        names = seg_model.names
        self._counters["frames_analyzed"] += 1

        people_count, vehicle_count = 0, 0
        has_uncertain = False

        if detections.tracker_id is not None:
            for idx, raw_track_id in enumerate(detections.tracker_id):
                track_id = int(raw_track_id)
                xyxy = detections.xyxy[idx].tolist()
                class_id = int(detections.class_id[idx])
                confidence = float(detections.confidence[idx])
                class_name = names.get(class_id, "object")

                if class_name == "person":
                    people_count += 1
                elif class_name in ("car", "motorcycle", "bus", "truck"):
                    vehicle_count += 1

                if self.recorder:
                    self.recorder.update_track(track_id, class_name, confidence, ts)

                low_conf = confidence < self.vlm_low_conf_threshold
                if low_conf:
                    has_uncertain = True

                # Update Monitor Grid telemetry (/monitor), throttled per track
                if ts - self._last_monitor_pub.get(track_id, -1e12) >= self.monitor_publish_sec:
                    self._last_monitor_pub[track_id] = ts
                    self._emit("MONITOR_DEVICE_UPDATE", camera_id, {
                        "device_count": 1,
                        "online_count": 1,
                        "alert_count": 1 if low_conf else 0,
                        "track_id": track_id,
                        "label": class_name,
                        "confidence": round(confidence, 2),
                        "bounding_box": [round(c, 1) for c in xyxy]
                    })

                if class_name in self.vlm_target_classes and (low_conf or self.vlm_all_tracks):
                    crop = self._make_context_crop(frame, xyxy, frame_w, frame_h)
                    trigger = "low_confidence_detection" if low_conf else "track_review"
                    meta = {
                        "camera_id": camera_id,
                        "camera_name": self.camera_name,
                        "track_id": track_id,
                        "label": class_name,
                        "confidence": confidence,
                        "trigger": trigger
                    }
                    context = (f"Low confidence ({confidence:.2f}) detection for '{class_name}' at {self.camera_name}."
                               if low_conf else
                               f"Routine review of tracked '{class_name}' (conf {confidence:.2f}) at {self.camera_name}.")
                    self._maybe_trigger_vlm(camera_id, track_id, crop, context, meta, ts)

        if len(self._last_monitor_pub) > 2000:
            self._last_monitor_pub = {k: v for k, v in self._last_monitor_pub.items() if ts - v < 60}

        if self.collector and has_uncertain and len(detections) > 0:
            self.collector.maybe_save(frame, detections.xyxy, detections.class_id, names, ts)

        is_anomaly, anomaly_reason = self._update_and_check_baseline(people_count, vehicle_count)
        if is_anomaly:
            self._emit("BASELINE_ANOMALY", camera_id, {
                "details": anomaly_reason,
                "people_count": people_count,
                "vehicle_count": vehicle_count
            })

        annotated = mask_annotator.annotate(scene=frame.copy(), detections=detections)
        annotated = box_annotator.annotate(scene=annotated, detections=detections)
        annotated = label_annotator.annotate(scene=annotated, detections=detections)
        self._set_latest(annotated)


# ==========================================
# 6. PIPELINE MANAGER (what the router calls)
# ==========================================

class PipelineManager:
    """One pipeline per camera id. A fresh VideoPipeline is created on every start,
    because stop() permanently tears down that instance's worker threads."""

    def __init__(self):
        self._pipelines: Dict[int, VideoPipeline] = {}
        self._lock = threading.Lock()

    def start_camera(
        self,
        camera_id: int,
        source: str,
        camera_name: str = "Gate Cam — Front Entrance",
        *,
        replace: bool = False,
        pipeline_options: Optional[Dict[str, Any]] = None,
        **start_options: Any,
    ) -> VideoPipeline:
        """start_options: mode, loop, realtime, frame_stride, max_frames, run_label.
        pipeline_options: constructor overrides (log_to_db, publish_telemetry, ...)."""
        with self._lock:
            existing = self._pipelines.get(camera_id)
            if existing and existing._is_running:
                if not replace:
                    return existing
                existing.stop()

            pipeline = VideoPipeline(**(pipeline_options or {}))
            pipeline.start(source, camera_id, camera_name, **start_options)
            self._pipelines[camera_id] = pipeline
            return pipeline

    def get_pipeline(self, camera_id: int) -> Optional[VideoPipeline]:
        return self._pipelines.get(camera_id)

    def stop_camera(self, camera_id: int) -> bool:
        with self._lock:
            pipeline = self._pipelines.pop(camera_id, None)
        if pipeline is None:
            return False
        pipeline.stop()
        return True

    def stop_all(self):
        for camera_id in list(self._pipelines):
            self.stop_camera(camera_id)

    def status(self) -> Dict[int, Dict[str, Any]]:
        return {cid: p.get_status() for cid, p in self._pipelines.items()}


pipeline_manager = PipelineManager()


# ==========================================
# 7. HEADLESS TEST RUNNER
# ==========================================

def _cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the ENDRA pipeline on a test video (no API server needed).")
    parser.add_argument("video", help="Path to a video file")
    parser.add_argument("--realtime", action="store_true", help="Pace playback at the video's fps (default: max speed)")
    parser.add_argument("--loop", action="store_true", help="Loop the video until Ctrl+C")
    parser.add_argument("--stride", type=int, default=1, help="Analyse every Nth frame")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--all-tracks", action="store_true", help="Send every target track to the VLM, not just low-confidence ones")
    parser.add_argument("--collect", action="store_true", help="Save uncertain frames for labeling")
    parser.add_argument("--telemetry", action="store_true", help="Publish WebSocket events to the backend")
    args = parser.parse_args()

    os.environ["ENDRA_ALLOW_ANY_VIDEO_PATH"] = "1"
    pipe = VideoPipeline(
        log_to_db=False,
        publish_telemetry=args.telemetry,
        collect_hard_examples=True if args.collect else None,
        vlm_all_tracks=True if args.all_tracks else None,
    )
    pipe.start(args.video, camera_id=1, mode="video", loop=args.loop, realtime=args.realtime,
               frame_stride=args.stride, max_frames=args.max_frames)
    try:
        while pipe._is_running:
            time.sleep(0.5)
        if pipe._thread:
            pipe._thread.join(timeout=30)
    except KeyboardInterrupt:
        pipe.stop()
    print(json.dumps(pipe.get_status(), indent=2, default=_json_default))
    if pipe.run_dir:
        print(f"\nResults: {os.path.abspath(pipe.run_dir)}  (summary.json, events.jsonl, vlm_crops/)")


if __name__ == "__main__":
    _cli()