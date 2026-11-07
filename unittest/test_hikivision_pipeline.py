import os
import cv2
import time

class HikvisionTestPipeline:
    def __init__(self, camera_id: str, stream_url: str):
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.is_running = False
        self.cap = None

    def start(self):
        print(f"Starting test pipeline for camera {self.camera_id} using source: {self.stream_url}")
        self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_ANY)
        self.is_running = True

        while self.is_running:
            # Check if capture is valid/open, if not, attempt to reopen
            if not self.cap or not self.cap.isOpened():
                print("Stream capture lost. Reconnecting...")
                time.sleep(0.5)
                self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_ANY)
                continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                # Re-initialize the capture object to cleanly loop the local clip from the beginning
                if self.cap:
                    self.cap.release()
                self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_ANY)
                time.sleep(0.03)
                continue

            # Simulate frame processing / AI threat detection overlay
            cv2.putText(
                frame, 
                f"TEST PIPELINE: {self.camera_id}", 
                (30, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (0, 255, 0), 
                2
            )

            # Optional: Display the frame locally for visual confirmation during testing
            # cv2.imshow(f"Camera Sandbox - {self.camera_id}", frame)
            
            # Control frame rate playback speed (~30 fps)
            if cv2.waitKey(30) & 0xFF == ord('q'):
                break

    def stop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        print(f"Test pipeline stopped for camera {self.camera_id}.")

if __name__ == "__main__":
    # Dynamically resolve absolute path to the local video file in the project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEST_STREAM_URL = os.path.join(base_dir, "media", "evidence", "clips", "mov_bbb.mp4")
    
    pipeline = HikvisionTestPipeline(camera_id="test-hik-01", stream_url=TEST_STREAM_URL)
    
    try:
        pipeline.start()
    except KeyboardInterrupt:
        pipeline.stop()