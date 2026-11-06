import cv2
import os

# Enforce TCP transport for RTSP streams to avoid packet drops / timeouts
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Official Wowza public RTSP test endpoint
RTSP_URL = "rtsp://9627b0bf2a7b.entrypoint.cloud.wowza.com:1935/app-p5260J38/66abe4b9_stream1"

print(f"Connecting to RTSP Stream: {RTSP_URL}...")
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)

# Optional timeout settings for OpenCV
cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)

if not cap.isOpened():
    print("Error: Could not open RTSP stream. Check internet connection or stream URL.")
    exit()

print("RTSP Stream connected successfully! Press 'q' inside the video window to exit.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Frame drop or stream disconnected.")
        break

    cv2.imshow("ENDRA Backend - RTSP Stream Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()