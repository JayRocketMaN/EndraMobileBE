import numpy as np

try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False


class face_recognizer:
    def __init__(self, name: str = "buffalo_s", ctx_id: int = 0, det_size: tuple = (640, 640)):
        """
        Initializes RetinaFace (Detection) + ArcFace (Recognition).
        
        :param name: InsightFace model zoo name ('buffalo_s' is lightweight and fast).
        :param ctx_id: Device ID (0 for GPU execution, -1 for CPU execution).
        :param det_size: Input resolution tuple for face detection.
        """
        self.app = None
        if INSIGHTFACE_AVAILABLE:
            try:
                self.app = FaceAnalysis(name=name)
                self.app.prepare(ctx_id=ctx_id, det_size=det_size)
                print(f"[FaceRecognizer] Initialized '{name}' model suite on ctx_id={ctx_id}")
            except Exception as e:
                print(f"[FaceRecognizer] Failed to load InsightFace model: {e}")
        else:
            print("[FaceRecognizer] Warning: insightface library is not installed.")

    def verify_person(self, person_crop: np.ndarray):
        """
        Takes a cropped image region (BGR numpy array) of a person detected by YOLO.
        Returns the face embedding, detection confidence, and bounding box within the crop.
        """
        if not INSIGHTFACE_AVAILABLE or self.app is None:
            return None, "InsightFace Not Available"

        # Validate input crop image array
        if person_crop is None or person_crop.size == 0 or person_crop.shape[0] == 0 or person_crop.shape[1] == 0:
            return None, "Invalid Crop Input"

        try:
            # InsightFace expects standard OpenCV BGR images
            faces = self.app.get(person_crop)
            if not faces:
                return None, "No Face Detected"

            # Select the most prominent face found in the crop (highest detection score)
            primary_face = max(faces, key=lambda f: f.det_score)

            face_data = {
                "embedding": primary_face.embedding,  # 512-d feature vector
                "confidence": float(primary_face.det_score),
                "bbox": primary_face.bbox.astype(int).tolist(),  # [x1, y1, x2, y2] relative to crop
                "gender": getattr(primary_face, 'gender', None),
                "age": getattr(primary_face, 'age', None)
            }

            return face_data, "Face Captured"

        except Exception as e:
            print(f"[FaceRecognizer] Verification error: {e}")
            return None, f"Processing Error: {str(e)}"

    @staticmethod
    def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculates Cosine Similarity between two face embedding vectors.
        Returns a score between -1.0 and 1.0 (Higher means more similar).
        Typical ArcFace match threshold is >= 0.40 - 0.50.
        """
        if embedding1 is None or embedding2 is None:
            return 0.0

        dot_product = np.dot(embedding1, embedding2)
        norm_a = np.linalg.norm(embedding1)
        norm_b = np.linalg.norm(embedding2)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def match_against_db(self, target_embedding: np.ndarray, db_embeddings: dict, threshold: float = 0.45):
        """
        Compares a target embedding against a dictionary of stored user embeddings.
        
        :param target_embedding: 512-d numpy vector from verify_person()
        :param db_embeddings: Dict mapping user IDs to stored embeddings, e.g. {"user_1": np_array}
        :param threshold: Similarity cutoff threshold for positive identification
        :return: (best_match_id, match_score) or (None, highest_score)
        """
        best_match_id = None
        highest_score = 0.0

        for user_id, stored_embedding in db_embeddings.items():
            score = self.compute_similarity(target_embedding, stored_embedding)
            if score > highest_score:
                highest_score = score
                best_match_id = user_id

        if highest_score >= threshold:
            return best_match_id, highest_score
        
        return None, highest_score