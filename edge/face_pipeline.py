"""
face_pipeline.py — Face detection (Haar cascade) + face recognition
(LBPH — Local Binary Patterns Histograms) via opencv-contrib's cv2.face
module. Both ship inside OpenCV itself: no model download, no internet,
genuinely runs offline.

LBPH is a classical (pre-deep-learning) recognizer: robust enough to prove
the correlation pipeline end-to-end (detect face → recognize → match
against watchlist → alert), but noticeably weaker than deep embeddings
under pose/lighting variation.

PRODUCTION SWAP-IN: replace `FaceRecognizer` with ArcFace/InsightFace
embeddings + cosine-similarity search (a vector index such as FAISS scales
this to statewide AFIS/NAFIS-linked watchlists). The public interface
(`enroll(images, label)` / `predict(face_crop) -> (label, confidence)`)
is written so that swap requires no changes in correlation/engine.py.
"""

import cv2
import numpy as np


class FaceDetector:
    """
    scale_factor / min_neighbors / min_size default to production-sane
    values tuned for real photographs/video. This demo's synthetic
    cartoon-face stand-ins (see demo/synth_feed.py) are a weak visual proxy
    for a real face, so the demo runner passes a relaxed calibration
    explicitly — swap back to the defaults (or, better, real enrollment
    photos) for anything beyond the offline sandbox demo.
    """

    def __init__(self, scale_factor=1.1, min_neighbors=5, min_size=(40, 40)):
        self.cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self.min_size = min_size

    def detect(self, frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.cascade.detectMultiScale(
            gray, scaleFactor=self.scale_factor, minNeighbors=self.min_neighbors, minSize=self.min_size
        )
        return [{"box": (int(x), int(y), int(w), int(h)), "crop": gray[y:y + h, x:x + w]}
                for (x, y, w, h) in faces]


class FaceRecognizer:
    """Wraps cv2.face.LBPHFaceRecognizer for watchlist enrollment + lookup."""

    def __init__(self, confidence_threshold=75.0):
        # LBPH "confidence" is a DISTANCE (lower = better match) — we invert
        # it to a 0-1 similarity score downstream for a consistent API with
        # the OCR confidence convention used elsewhere in this codebase.
        self.model = cv2.face.LBPHFaceRecognizer_create()
        self.confidence_threshold = confidence_threshold
        self.trained = False

    def enroll(self, face_images_by_label: dict):
        """face_images_by_label: {label_id (int): [grayscale np.ndarray, ...]}"""
        images, labels = [], []
        for label, imgs in face_images_by_label.items():
            for img in imgs:
                images.append(cv2.resize(img, (150, 150)))
                labels.append(int(label))
        if not images:
            return
        self.model.train(images, np.array(labels))
        self.trained = True

    def predict(self, face_gray):
        if not self.trained:
            return None, 0.0
        face_gray = cv2.resize(face_gray, (150, 150))
        label, distance = self.model.predict(face_gray)
        similarity = max(0.0, 1.0 - (distance / 150.0))  # heuristic normalization to ~[0,1]
        if distance <= self.confidence_threshold:
            return label, similarity
        return None, similarity
