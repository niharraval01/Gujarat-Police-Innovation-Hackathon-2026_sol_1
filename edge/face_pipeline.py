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

from pathlib import Path

import cv2
import numpy as np

import db


WATCHLIST_FACE_ROOT = Path(__file__).parent.parent / "data" / "watchlist_faces"


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


def enroll_saved_watchlist_faces(face_recognizer, faces_root=None, detector=None):
    """Enroll persisted watchlist photos under stable database label IDs."""
    root = Path(faces_root or WATCHLIST_FACE_ROOT)
    if not root.exists():
        return {"people": 0, "photos": 0, "skipped": []}

    detector = detector or FaceDetector()
    enrollment = {}
    skipped = []
    photo_count = 0

    for person_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        person_id = person_dir.name
        person = db.get_watchlist_person(person_id)
        if person is None:
            skipped.append({"person_id": person_id, "reason": "not in watchlist database"})
            continue

        label_id = db.ensure_person_face_label(person_id)
        samples = []
        photo_paths = sorted(
            path for path in person_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        for photo_path in photo_paths:
            image = cv2.imread(str(photo_path), cv2.IMREAD_COLOR)
            if image is None:
                skipped.append({"person_id": person_id, "photo": photo_path.name, "reason": "unreadable image"})
                continue
            faces = detector.detect(image)
            if faces:
                # Use the largest detected face when a reference image contains
                # multiple people; it is normally the intended subject.
                crop = max(faces, key=lambda face: face["box"][2] * face["box"][3])["crop"]
            else:
                # Close-cropped faces do not always trigger Haar. Falling back
                # to the full image keeps enrollment offline and predictable.
                crop = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            samples.append(crop)
            photo_count += 1

        if samples:
            enrollment[int(label_id)] = samples
        else:
            skipped.append({"person_id": person_id, "reason": "no usable photos"})

    face_recognizer.enroll(enrollment)
    return {"people": len(enrollment), "photos": photo_count, "skipped": skipped}
