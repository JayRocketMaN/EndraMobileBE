import time
import numpy as np
import cv2

class SecurityRulesEngine:
    """
    Layer 1 Custom Perimeter Security Rules Engine.
    Evaluates tracking metrics, spatial geometry, and velocity to trigger 
    Layer 2 (Qwen2.5-VL) ONLY when genuine anomalies occur.
    """
    def __init__(self, loiter_limit_sec: float = 10.0, stationary_speed_px: float = 3.0, confidence_threshold: float = 0.85):
        self.loiter_limit_sec = loiter_limit_sec      # Trigger if stopped/loitering > 10 seconds
        self.stationary_speed_px = stationary_speed_px  # Movement under 3px/frame is considered stationary
        self.confidence_threshold = confidence_threshold
        # Track persistent object history: {track_id: {"first_seen": timestamp, "positions": [(x, y), ...]}}
        self.track_history = {}

    def is_inside_polygon(self, point: tuple, polygon: list) -> bool:
        """
        Uses OpenCV PointPolygonTest to check if a bounding box center is inside a defined zone.
        """
        if not polygon or len(polygon) < 3:
            return False
        pts = np.array(polygon, dtype=np.int32)
        # Returns +1 (inside), 0 (on edge), -1 (outside)
        result = cv2.pointPolygonTest(pts, point, False)
        return result >= 0

    def calculate_velocity(self, positions: list) -> float:
        """
        Calculates average pixel displacement per frame over recent position history.
        """
        if len(positions) < 2:
            return 0.0
        # Calculate Euclidean distance between the most recent positions
        p1 = np.array(positions[-1])
        p2 = np.array(positions[-2])
        return float(np.linalg.norm(p1 - p2))

    def evaluate_pose_risk(self, keypoints) -> str:
        """
        Analyzes 2D pose keypoint landmarks for crouching, prone, or suspicious postures.
        """
        if keypoints is None or len(keypoints) == 0:
            return "NORMAL"

        try:
            shoulders_y = (keypoints[5][1] + keypoints[6][1]) / 2.0
            hips_y = (keypoints[11][1] + keypoints[12][1]) / 2.0
            ankles_y = (keypoints[15][1] + keypoints[16][1]) / 2.0

            torso_height = abs(hips_y - shoulders_y)
            leg_height = abs(ankles_y - hips_y)

            if leg_height > 0 and (torso_height / leg_height) > 1.8:
                return "CROUCHING_OR_SUSPICIOUS"
        except Exception:
            pass

        return "NORMAL"

    def evaluate_detection(self, track_id: int, label: str, bbox: list, confidence: float, keypoints=None, restricted_zone_poly: list = None) -> tuple[bool, str, dict]:
        """
        Evaluates dynamic tracking data against security rules.
        Returns: (should_trigger_vlm: bool, trigger_reason: str, metadata: dict)
        """
        current_time = time.time()
        x1, y1, x2, y2 = bbox
        center_pt = (int((x1 + x2) / 2), int((y1 + y2) / 2))

        # 1. Update Track History
        if track_id not in self.track_history:
            self.track_history[track_id] = {
                "first_seen": current_time,
                "positions": [center_pt]
            }
        else:
            self.track_history[track_id]["positions"].append(center_pt)
            # Keep only last 30 frame positions for velocity checks
            if len(self.track_history[track_id]["positions"]) > 30:
                self.track_history[track_id]["positions"].pop(0)

        track_data = self.track_history[track_id]
        loiter_duration = current_time - track_data["first_seen"]
        velocity = self.calculate_velocity(track_data["positions"])
        is_stationary = velocity < self.stationary_speed_px

        # 2. Check Restricted Zone (Spatial Polygon Intersection)
        in_restricted_zone = False
        if restricted_zone_poly:
            in_restricted_zone = self.is_inside_polygon(center_pt, restricted_zone_poly)

        # 3. Compile Metadata
        meta = {
            "track_id": track_id,
            "label": label,
            "confidence": int(confidence * 100),
            "loiter_seconds": round(loiter_duration, 1),
            "velocity": round(velocity, 2),
            "in_restricted_zone": in_restricted_zone,
            "is_stationary": is_stationary
        }

        # -------------------- RULE EVALUATION ENGINE -------------------- #

        # RULE A: VEHICLES (Cars, Trucks, Motorcycles)
        if label in ["car", "truck", "bus", "motorcycle"]:
            # Ignore routine traffic driving past on roads!
            if not in_restricted_zone:
                return False, "ROUTINE_TRAFFIC_PASSTHROUGH", meta
            
            # Car in restricted zone but moving smoothly -> Monitor silently
            if in_restricted_zone and not is_stationary:
                return False, "VEHICLE_TRANSITING_RESTRICTED_ZONE", meta

            # Threat Condition: Vehicle stopped/parked in a restricted zone longer than threshold
            if in_restricted_zone and is_stationary and loiter_duration >= self.loiter_limit_sec:
                return True, f"VEHICLE_LOITERING_RESTRICTED_ZONE ({int(loiter_duration)}s)", meta

        # RULE B: PERSONS
        elif label == "person":
            pose_flag = self.evaluate_pose_risk(keypoints)

            # Threat Condition B1: Person crouching or suspicious stance near perimeter
            if in_restricted_zone and pose_flag != "NORMAL":
                return True, f"SUSPICIOUS_POSTURE ({pose_flag})", meta

            # Threat Condition B2: Person loitering inside restricted zone
            if in_restricted_zone and loiter_duration >= self.loiter_limit_sec:
                return True, f"PERSON_LOITERING_RESTRICTED_ZONE ({int(loiter_duration)}s)", meta

        # RULE C: UNATTENDED ITEMS / BAGS
        elif label in ["backpack", "suitcase", "handbag"]:
            if in_restricted_zone and is_stationary and loiter_duration >= 5.0:
                return True, "POSSIBLE_UNATTENDED_BAGGAGE", meta

        # No triggers matched -> Normal flow, skip VLM inference
        return False, "NO_RULE_VIOLATION", meta