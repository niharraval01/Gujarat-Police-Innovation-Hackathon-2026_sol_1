"""
demo/synth_feed.py — generates a representative synthetic dataset (as
explicitly permitted by the hackathon brief) simulating:

  1. A watchlisted vehicle passing several real cameras from the registry,
     at increasing timestamps — this is what proves out cross-camera
     vehicle re-identification + route reconstruction on the GIS map.
  2. Background "noise" traffic (non-watchlisted plates) at other cameras,
     so the correlation engine has to actually discriminate, not just
     alert on everything it sees.
  3. A watchlisted "person of interest" face appearing at one camera.

Each synthetic frame is a real image (numpy/OpenCV), run through the exact
same edge_pipeline used for live camera frames — nothing here is faked at
the pipeline level, only the *source video* is synthetic.
"""

import random
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import cv2
import numpy as np

from edge.plate_ocr import render_plate_image


def make_traffic_frame(plate_text, w=640, h=360, jitter_seed=0):
    """A simple synthetic 'road camera frame': grey road, a car-shaped
    rectangle, plate mounted on it. Real enough for the plate detector's
    Haar cascade + our from-scratch OCR to actually process."""
    rng = np.random.RandomState(jitter_seed)
    frame = np.full((h, w, 3), (110, 110, 110), dtype=np.uint8)  # road
    cv2.rectangle(frame, (0, h - 40), (w, h), (70, 70, 70), -1)  # road edge

    car_x, car_y = w // 2 - 110, h // 2 - 40
    cv2.rectangle(frame, (car_x, car_y), (car_x + 220, car_y + 90), (40, 40, 180), -1)  # car body
    cv2.rectangle(frame, (car_x + 20, car_y - 25), (car_x + 200, car_y), (200, 200, 200), -1)  # windshield

    plate_img = render_plate_image(plate_text, char_w=18, char_h=28, pad=4, gap=3)
    ph, pw = plate_img.shape[:2]
    px, py = car_x + 60, car_y + 55
    frame[py:py + ph, px:px + pw] = plate_img

    noise = rng.normal(0, 6, frame.shape).astype(np.int16)
    frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return frame, (px, py, pw, ph)


def make_face_frame(w=480, h=480, eye_offset=20, skin=(180, 150, 130), seed=0):
    rng = np.random.RandomState(seed)
    img = np.full((h, w, 3), 220, dtype=np.uint8)
    cx, cy, r = w // 2, h // 2, 90
    cv2.circle(img, (cx, cy), r, skin, -1)
    cv2.circle(img, (cx - eye_offset - 10, cy - 20), 12, (30, 30, 30), -1)
    cv2.circle(img, (cx + eye_offset + 10, cy - 20), 12, (30, 30, 30), -1)
    cv2.ellipse(img, (cx, cy + 35), (26, 12), 0, 0, 180, (60, 40, 40), 3)
    noise = rng.normal(0, 4, img.shape).astype(np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def build_scenario(cameras, watchlisted_plate="GJ06AB1234", watched_face_label=1, n_background=15, seed=7):
    """
    Returns an ordered list of synthetic 'events':
        {camera_id, lat, lon, ts_offset, kind: 'plate'|'face', frame}

    The watchlisted vehicle is routed through 4 real cameras (from the
    registry, across different districts) with increasing timestamps —
    this is the storyline the GIS route-reconstruction demo replays.
    """
    rng = random.Random(seed)
    events = []

    route_cams = rng.sample(cameras, k=min(4, len(cameras)))
    for i, cam in enumerate(route_cams):
        frame, plate_box = make_traffic_frame(watchlisted_plate, jitter_seed=i)
        events.append({
            "camera_id": cam["camera_id"], "lat": cam["lat"], "lon": cam["lon"],
            "ts_offset": i * 45.0,  # seconds apart as the vehicle travels
            "kind": "plate",
            "frame": frame, "plate_box": plate_box,
        })

    other_plates = [f"GJ{rng.randint(1,30):02d}{chr(65+rng.randint(0,25))}{chr(65+rng.randint(0,25))}"
                     f"{rng.randint(1000,9999)}" for _ in range(n_background)]
    for i, plate in enumerate(other_plates):
        cam = rng.choice(cameras)
        frame, plate_box = make_traffic_frame(plate, jitter_seed=100 + i)
        events.append({
            "camera_id": cam["camera_id"], "lat": cam["lat"], "lon": cam["lon"],
            "ts_offset": rng.uniform(0, 180),
            "kind": "plate",
            "frame": frame, "plate_box": plate_box,
        })

    face_cam = rng.choice(cameras)
    events.append({
        "camera_id": face_cam["camera_id"], "lat": face_cam["lat"], "lon": face_cam["lon"],
        "ts_offset": 60.0, "kind": "face",
        "frame": make_face_frame(seed=99),
    })

    events.sort(key=lambda e: e["ts_offset"])
    return events
