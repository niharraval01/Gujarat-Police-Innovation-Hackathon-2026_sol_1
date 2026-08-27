"""
plate_detector.py — Edge-tier plate LOCALIZATION.

Uses OpenCV's bundled Haar cascade (haarcascade_russian_plate_number.xml),
which ships inside opencv-contrib and needs no internet/model download —
this is exactly the property that makes it viable to run on low-power edge
boxes at ~80,000 camera sites instead of shipping raw video to the cloud.

PRODUCTION SWAP-IN: replace `PlateDetector.detect()` internals with a
YOLOv8n-ANPR model (ultralytics) for robust detection under night/rain/angle
conditions. Interface (list of (x,y,w,h) boxes) stays identical, so nothing
downstream (OCR, correlation engine) needs to change.
"""

import cv2
import numpy as np


class PlateDetector:
    def __init__(self):
        self.cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
        )

    def detect(self, frame_bgr):
        """Returns list of dicts: {box: (x,y,w,h), crop: np.ndarray}"""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        boxes = self.cascade.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=4, minSize=(60, 20)
        )
        results = []
        for (x, y, w, h) in boxes:
            crop = frame_bgr[y:y + h, x:x + w]
            results.append({"box": (int(x), int(y), int(w), int(h)), "crop": crop})
        return results
