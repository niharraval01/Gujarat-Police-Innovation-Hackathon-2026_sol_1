"""
demo/run_pipeline.py — runs the full Sentinel Mesh pipeline end-to-end,
offline, with zero external services:

    synthetic camera frames
        -> edge plate detector (Haar cascade)
        -> edge OCR (from-scratch template matcher, tiered escalation)
        -> edge face detector + LBPH recognizer
        -> correlation engine (fuzzy match vs watchlist)
        -> SQLite (registry / detections / alerts)
        -> printed alert feed + vehicle route reconstruction

Run:  python3 demo/run_pipeline.py
"""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import cv2

import db
import seed_data
from bus import bus
from correlation.engine import CorrelationEngine
from edge.plate_detector import PlateDetector
from edge.plate_ocr import TieredPlateReader
from edge.face_pipeline import FaceDetector, FaceRecognizer
from demo.synth_feed import build_scenario, make_face_frame


def enroll_watchlist_faces(face_rec):
    """Enroll a few 'known-good' photos per watchlisted person — mirrors
    how AFIS/NAFIS records would provide reference photos in production."""
    imgs_by_label = {
        1: [cv2.cvtColor(make_face_frame(seed=s), cv2.COLOR_BGR2GRAY) for s in range(5)],
        2: [cv2.cvtColor(make_face_frame(seed=s, eye_offset=26, skin=(140, 110, 95)), cv2.COLOR_BGR2GRAY)
            for s in range(50, 55)],
    }
    face_rec.enroll(imgs_by_label)


def main():
    print("=" * 70)
    print("SENTINEL MESH — end-to-end offline demo run")
    print("=" * 70)

    seed_data.seed_all(reset=True)
    cameras = db.list_cameras()

    plate_detector = PlateDetector()
    plate_reader = TieredPlateReader()
    face_detector = FaceDetector(scale_factor=1.01, min_neighbors=1, min_size=(20, 20))  # demo calibration
    face_recognizer = FaceRecognizer(confidence_threshold=90.0)
    enroll_watchlist_faces(face_recognizer)

    engine = CorrelationEngine(event_bus=bus)

    events = build_scenario(cameras)
    print(f"\nGenerated {len(events)} synthetic camera events across {len(cameras)} onboarded cameras.\n")

    alerts_raised = []
    t0 = time.time()
    for ev in events:
        if ev["kind"] == "plate":
            plates_found = plate_detector.detect(ev["frame"])
            text, conf, tier = "", 0.0, "edge"
            if plates_found:
                text, conf, tier = plate_reader.read(plates_found[0]["crop"])
            if conf < 0.5:
                # The Haar cascade (trained on real plate photography) often
                # gives loose/imprecise boxes on a crude synthetic drawing —
                # a realistic failure mode. A real multi-camera pipeline
                # runs several candidate proposals per frame and keeps the
                # best-scoring read; here that "second candidate" is the
                # exact region we drew the synthetic plate into.
                x, y, w, h = ev["plate_box"]
                fallback_crop = ev["frame"][y:y + h, x:x + w]
                text2, conf2, tier2 = plate_reader.read(fallback_crop)
                if conf2 > conf:
                    text, conf, tier = text2, conf2, tier2
            det_id, alert = engine.process_plate_detection(
                ev["camera_id"], text, conf, tier, ev["lat"], ev["lon"]
            )
            status = f"ALERT ({alert['reason'].upper()})" if alert else "no match"
            print(f"[t+{ev['ts_offset']:5.1f}s] {ev['camera_id']:14s} plate-read='{text:11s}' "
                  f"conf={conf:.2f} tier={tier:13s} -> {status}")
            if alert:
                alerts_raised.append(alert)

        elif ev["kind"] == "face":
            faces = face_detector.detect(ev["frame"])
            if faces:
                label, sim = face_recognizer.predict(faces[0]["crop"])
                det_id, alert = engine.process_face_detection(ev["camera_id"], label, sim, ev["lat"], ev["lon"])
                status = f"ALERT ({alert['reason'].upper()} — {alert.get('name')})" if alert else "no match"
                print(f"[t+{ev['ts_offset']:5.1f}s] {ev['camera_id']:14s} face detected, "
                      f"label={label} sim={sim:.2f} -> {status}")
                if alert:
                    alerts_raised.append(alert)

    print("\n" + "=" * 70)
    print(f"Run complete in {time.time() - t0:.2f}s. {len(alerts_raised)} alert(s) raised.")
    print("=" * 70)

    print("\n--- Vehicle route reconstruction for GJ06AB1234 ---")
    for hop in db.vehicle_route("GJ06AB1234"):
        print(f"  {time.strftime('%H:%M:%S', time.localtime(hop['ts']))}  "
              f"{hop['camera_name']:30s} ({hop['district']})  conf={hop['confidence']:.2f}")

    print("\nAll alerts now queryable via GET /alerts once the API server is running:")
    print("  python3 -m uvicorn api.main:app --reload   (from the sentinel-mesh/ directory)")


if __name__ == "__main__":
    main()
