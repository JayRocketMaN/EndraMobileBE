import os
import time
import threading
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from collections import deque
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

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

from app.core.database import SessionLocal
from app.models.surveillance_model import AIEvent, AIEventType

logging.basicConfig(
    level=os.getenv("ENDRA_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger("endra.videopipeline")


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


class TelemetryPublisher:
    """Async background worker for streaming pipeline inferences over WebSocket to Flutter UI."""

    def __init__(self, ingest_url: Optional[str] = None):
        self.ingest_url = ingest_url or os.getenv("ENDRA_WS_INGEST_URL", "ws://localhost:8000/api/v1/ws/ingest")
        self._queue = deque(maxlen=300)
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
        self._loop.run_until_complete(self._connect_and_stream())

    async def _connect_and_stream(self):
        while self._is_running:
            try:
                async with websockets.connect(self.ingest_url) as ws:
                    logger.info(f"[WS PUBLISHER] Stream connected: {self.ingest_url}")
                    while self._is_running:
                        if self._queue:
                            event_data = self._queue.popleft()
                            await ws.send(json.dumps(event_data))
                        else:
                            await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"[WS PUBLISHER] Connection dropped ({e}). Retry in 3s...")
                await asyncio.sleep(3)

    def publish(self, event_type: str, camera_id: int, payload_data: Dict[str, Any]):
        if not WEBSOCKETS_AVAILABLE or not self._is_running:
            return

        formatted_payload = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "camera_id": camera_id,
                **payload_data
            }
        }
        self._queue.append(formatted_payload)

    def stop(self):
        self._is_running = False
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


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

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="endra-vlm-loop"
        )
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
        except Exception:
            logger.exception("[LAYER 2] VLM event loop crashed.")
            self._ready.set()

    def submit(self, crop, event_context: str, meta: Optional[Dict[str, Any]] = None):
        if not OLLAMA_AVAILABLE or crop is None or getattr(crop, "size", 0) == 0:
            return

        now = time.time()
        with self._lock:
            if now - self._last_submit_time < self.global_cooldown_sec:
                return
            if self._pending >= self.max_pending:
                return
            self._pending += 1
            self._last_submit_time = now

        crop_copy = crop.copy() if hasattr(crop, "copy") else crop
        meta = meta or {}

        try:
            if self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._guarded_analyze(crop_copy, event_context, meta),
                    self._loop
                )
            else:
                with self._lock:
                    self._pending -= 1
        except Exception:
            with self._lock:
                self._pending -= 1

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

            except Exception as err:
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
Metadata: {json.dumps(safe_meta, default=str)}
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
        except Exception:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return {"category": "None", "confidence": 0, "security_relevance": False}

    def shutdown(self):
        try:
            if self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread.is_alive():
                self._thread.join(timeout=2)
        except Exception:
            pass


class VideoPipeline:
    def __init__(
        self,
        seg_model_path: str = "yolo11n-seg.pt",
        confidence_threshold: float = 0.4,
        min_motion_area: int = 500,
        buffer_seconds: int = 5,
        target_fps: int = 30,
        storage_dir: str = "./media/evidence"
    ):
        self.seg_model_path = seg_model_path
        self.confidence_threshold = confidence_threshold
        self.min_motion_area = min_motion_area
        self.target_fps = target_fps
        self.buffer_seconds = buffer_seconds

        self.frame_buffer = deque(maxlen=self.target_fps * self.buffer_seconds)
        self.storage_dir = storage_dir
        os.makedirs(os.path.join(self.storage_dir, "snapshots"), exist_ok=True)
        os.makedirs(os.path.join(self.storage_dir, "clips"), exist_ok=True)

        self.baseline_stats = {"people": 0.0, "vehicles": 0.0, "sample_count": 0}
        self.system_health_score = 82  # Matches UI 82% system health gauge

        self.vlm_cooldown_sec = float(os.getenv("ENDRA_VLM_COOLDOWN_SEC", "20"))
        self.vlm_low_conf_threshold = float(os.getenv("ENDRA_VLM_LOW_CONF", "0.80"))
        self.last_vlm_at = {}

        self.vlm_client = CloudVLMService(global_cooldown_sec=10.0, on_result=self._handle_vlm_result)
        self.vlm_target_classes = {"person", "backpack", "handbag", "suitcase", "bicycle", "car", "motorcycle"}

        self.publisher = TelemetryPublisher()
        self._is_running = False
        self._thread = None
        self.active_camera_id = None
        self.camera_name = "Gate Cam — Front Entrance"

        self.lock = threading.Lock()
        self.latest_frame = None
        self.on_alert_callback = None

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

    def _save_snapshot(self, frame, event_id: str) -> Optional[str]:
        if frame is None or not CV_AVAILABLE:
            return None
        try:
            filename = f"snapshot_{event_id}_{int(time.time())}.jpg"
            filepath = os.path.join(self.storage_dir, "snapshots", filename)
            cv2.imwrite(filepath, frame)
            return filepath
        except Exception as e:
            logger.error(f"Snapshot capture error: {e}")
            return None

    def _record_video_clip(self, buffered_frames: List[np.ndarray], event_id: str, frame_shape: tuple) -> Optional[str]:
        if not buffered_frames or not CV_AVAILABLE:
            return None
        try:
            filename = f"clip_{event_id}_{int(time.time())}.mp4"
            filepath = os.path.join(self.storage_dir, "clips", filename)
            h, w = frame_shape[:2]
            out = cv2.VideoWriter(filepath, cv2.VideoWriter_fourcc(*'mp4v'), self.target_fps, (w, h))
            for frame in buffered_frames:
                out.write(frame)
            out.release()
            return filepath
        except Exception as e:
            logger.error(f"Video clip record error: {e}")
            return None

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

        # Dispatch WebSocket notice to Command Center dashboard
        self.publisher.publish(
            event_type="USER_SUBMITTED_REPORT",
            camera_id=self.active_camera_id or 1,
            payload_data=payload
        )

        return payload

    def _log_event_to_db(self, camera_id: int, event_type: AIEventType, confidence: float, details: str = "", frame: Optional[np.ndarray] = None):
        with SessionLocal() as db:
            try:
                event_key = f"{camera_id}_{event_type.value}_{int(time.time())}"
                snapshot_path = self._save_snapshot(frame, event_key) if frame is not None else None

                if frame is not None:
                    buffer_copy = list(self.frame_buffer)
                    threading.Thread(
                        target=self._record_video_clip,
                        args=(buffer_copy, event_key, frame.shape),
                        daemon=True
                    ).start()

                db_event = AIEvent(
                    camera_id=camera_id,
                    event_type=event_type,
                    confidence_score=float(confidence),
                    snapshot_url=snapshot_path,
                    video_clip_url=None
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
            except Exception as e:
                logger.error(f"Database write error: {e}")
                db.rollback()

    def _make_context_crop(self, frame, xyxy, frame_width: int, frame_height: int, pad_ratio: float = 0.35):
        if frame is None or not CV_AVAILABLE:
            return None
        x1, y1, x2, y2 = map(int, xyxy)
        w, h = max(1, x2 - x1), max(1, y2 - y1)
        pad = int(max(w, h) * pad_ratio)

        cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
        cx2, cy2 = min(frame_width, x2 + pad), min(frame_height, y2 + pad)
        return frame[cy1:cy2, cx1:cx2]

    def _maybe_trigger_vlm(self, camera_id: int, track_id, crop, context_msg: str, meta: Dict[str, Any]):
        if crop is None or getattr(crop, "size", 0) == 0:
            return

        key = f"{camera_id}:{track_id if track_id is not None else 'no_track'}"
        now = time.time()

        if now - self.last_vlm_at.get(key, 0.0) < self.vlm_cooldown_sec:
            return

        self.last_vlm_at[key] = now

        self.publisher.publish(
            event_type="LAYER2_VLM_TRIGGER",
            camera_id=camera_id,
            payload_data={
                "trigger_reason": context_msg,
                "confidence": float(meta.get("confidence", 0.0)),
                "label": meta.get("label"),
                "track_id": track_id
            }
        )

        self.vlm_client.submit(crop, context_msg, meta)

    def _handle_vlm_result(self, parsed: Dict[str, Any], meta: Dict[str, Any]):
        try:
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
            self.publisher.publish(
                event_type="RECENT_ACTIVITY_UPDATE",
                camera_id=camera_id,
                payload_data=payload
            )

            # 2. Trigger Auto Responder Dispatch Message (/login/messages)
            if parsed.get("dispatch_recommended", False):
                self.publisher.publish(
                    event_type="RESPONDER_DISPATCH_TRIGGER",
                    camera_id=camera_id,
                    payload_data={
                        "channel": "ENDRA Command Center",
                        "status_message": "Responder dispatched to your location.",
                        "eta_minutes": 8
                    }
                )

            self._log_event_to_db(
                camera_id=camera_id,
                event_type=getattr(AIEventType, "VLM_ALERT", AIEventType.ANOMALOUS_BEHAVIOR),
                confidence=confidence / 100.0,
                details=json.dumps(payload),
                frame=self.latest_frame
            )
        except Exception:
            logger.exception("[LAYER 2] Failed handling VLM result.")

    def start(self, stream_source, camera_id: int, camera_name: str = "Gate Cam — Front Entrance"):
        if not CV_AVAILABLE:
            raise RuntimeError("OpenCV / YOLO dependencies missing.")

        if self._is_running:
            return False

        self._is_running = True
        self.active_camera_id = camera_id
        self.camera_name = camera_name

        self.publisher.start()

        self._thread = threading.Thread(
            target=self._run_pipeline,
            args=(stream_source, camera_id),
            daemon=True
        )
        self._thread.start()
        return True

    def stop(self):
        if not self._is_running:
            return False

        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        self.publisher.stop()
        self.vlm_client.shutdown()
        return True

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

    def _run_pipeline(self, stream_source, camera_id: int):
        seg_model = YOLO(self.seg_model_path)
        mask_annotator = sv.MaskAnnotator(color_lookup=sv.ColorLookup.INDEX)
        box_annotator = sv.BoxAnnotator(thickness=2)
        label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
        bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)

        cap = cv2.VideoCapture(stream_source)
        if not cap.isOpened():
            self._is_running = False
            return

        try:
            while self._is_running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame_h, frame_w = frame.shape[:2]
                self.frame_buffer.append(frame.copy())

                fg_mask = bg_subtractor.apply(frame)
                _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

                if cv2.countNonZero(thresh) < self.min_motion_area:
                    with self.lock:
                        self.latest_frame = frame
                    continue

                seg_results = seg_model.track(
                    frame, persist=True, tracker="bytetrack.yaml",
                    conf=self.confidence_threshold, verbose=False
                )

                people_count, vehicle_count = 0, 0

                if seg_results and len(seg_results) > 0:
                    result = seg_results[0]
                    detections = sv.Detections.from_ultralytics(result)

                    if detections.tracker_id is not None:
                        for idx, track_id in enumerate(detections.tracker_id):
                            xyxy = detections.xyxy[idx].tolist()
                            class_id = detections.class_id[idx]
                            confidence = float(detections.confidence[idx])
                            class_name = seg_model.names.get(class_id, "object")

                            if class_name == "person":
                                people_count += 1
                            elif class_name in ("car", "motorcycle", "bus", "truck"):
                                vehicle_count += 1

                            # Update Monitor Grid telemetry (/monitor)
                            self.publisher.publish(
                                event_type="MONITOR_DEVICE_UPDATE",
                                camera_id=camera_id,
                                payload_data={
                                    "device_count": 1,
                                    "online_count": 1,
                                    "alert_count": 1 if confidence < self.vlm_low_conf_threshold else 0,
                                    "track_id": int(track_id),
                                    "label": class_name,
                                    "confidence": round(confidence, 2),
                                    "bounding_box": [round(c, 1) for c in xyxy]
                                }
                            )

                            if confidence < self.vlm_low_conf_threshold and class_name in self.vlm_target_classes:
                                crop = self._make_context_crop(frame, xyxy, frame_w, frame_h)
                                meta = {
                                    "camera_id": camera_id,
                                    "camera_name": self.camera_name,
                                    "track_id": track_id,
                                    "label": class_name,
                                    "confidence": confidence,
                                    "trigger": "low_confidence_detection"
                                }
                                self._maybe_trigger_vlm(
                                    camera_id, track_id, crop,
                                    f"Low confidence ({confidence:.2f}) detection for '{class_name}' at {self.camera_name}.",
                                    meta
                                )

                    is_anomaly, anomaly_reason = self._update_and_check_baseline(people_count, vehicle_count)
                    if is_anomaly:
                        self.publisher.publish(
                            event_type="BASELINE_ANOMALY",
                            camera_id=camera_id,
                            payload_data={
                                "details": anomaly_reason,
                                "people_count": people_count,
                                "vehicle_count": vehicle_count
                            }
                        )

                    annotated = mask_annotator.annotate(scene=frame.copy(), detections=detections)
                    annotated = box_annotator.annotate(scene=annotated, detections=detections)
                    annotated = label_annotator.annotate(scene=annotated, detections=detections)

                    with self.lock:
                        self.latest_frame = annotated
                else:
                    with self.lock:
                        self.latest_frame = frame
        finally:
            cap.release()
            self._is_running = False


pipeline_manager: Dict[int, VideoPipeline] = {}