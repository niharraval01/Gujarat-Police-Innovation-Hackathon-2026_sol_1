"""
demo/run_live.py — connects the real edge pipeline (plate detector, tiered
OCR, face detector/recognizer, correlation engine) to the ACTUAL Sentinel
sandbox camera grid described in the Resources-tab integration reference,
instead of the synthetic frames used by demo/run_pipeline.py.

This cannot be exercised from this offline build environment (no internet
access here) — treat it as reviewed-and-ready, not run-and-verified. What
IS verified offline is the control flow it depends on: see
edge/test_live_ingest_offline.py, which drives edge/live_ingest.py against
a scripted mock capture (reconnect/backoff, warm-up tolerance,
discontinuity detection) and correlation/engine.py's own dedup/cooldown
tests. Run those first; run this once you actually have the sandbox host.

Usage:
    python3 demo/run_live.py --host <sandbox-host-from-resources-tab> \\
        [--max-cameras 8] [--camera-ids 1,2,3] [--seconds 120]

Pacing: per the integration guide's "DO pace your load", only the cameras
you explicitly select (or the first --max-cameras from the catalogue) are
opened. Raise --max-cameras deliberately while developing, not by default.

Before pointing this at real watchlist persons, call
face_recognizer.enroll(...) with real reference photos — an untrained
FaceRecognizer never raises a person alert (predict() returns None), by
design, so you don't get spurious matches against an empty gallery.
"""
import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import db
from bus import bus
from correlation.engine import CorrelationEngine
from edge.plate_detector import PlateDetector
from edge.plate_ocr import TieredPlateReader
from edge.face_pipeline import FaceDetector, FaceRecognizer, enroll_saved_watchlist_faces
from edge.live_ingest import fetch_catalogue, LiveRTSPSource


def sync_registry_from_catalogue(catalogue):
    """Populate the registry (Model 1 foundation) from the sandbox's own
    catalogue rather than our seeded Gujarat-district list — this is the
    real evaluation grid, so it's the source of truth for Step 4. Stream
    URLs are persisted too, so the dashboard can offer on-demand WebRTC
    (WHEP) live viewing per camera without hard-coding anything."""
    for entry in catalogue:
        db.upsert_camera({
            "camera_id": f"SANDBOX-{entry['camera_id']}",
            "name": entry["location_label"] or entry["camera_id"],
            "department": "Sandbox",
            "vendor": "unknown",
            "vms_platform": "sentinel-sandbox",
            "lat": entry["lat"] if entry["lat"] is not None else 0.0,
            "lon": entry["lon"] if entry["lon"] is not None else 0.0,
            "district": "Evaluation Grid",
            "camera_type": "fixed",
            "connectivity": "unknown",
            "rtsp_url": entry["rtsp_url"],
            "whep_url": entry["whep_url"],
            "hls_url": entry["hls_url"],
        })


def make_on_frame(engine, plate_detector, plate_reader, face_detector, face_recognizer, camera_id, lat, lon):
    def on_frame(rec):
        if rec.discontinuity:
            engine.reset_camera(camera_id)
            print(f"[{camera_id}] scene discontinuity (feed looped) — camera state reset")

        frame = rec.frame

        for p in plate_detector.detect(frame):
            text, conf, tier = plate_reader.read(p["crop"])
            if not text:
                continue
            _, alert = engine.process_plate_detection(camera_id, text, conf, tier, lat, lon)
            if alert and alert["is_new"]:
                print(f"[{camera_id}] ALERT vehicle={alert['match_key']} reason={alert['reason']} "
                      f"conf={conf:.2f} (read as {text})")

        for f in face_detector.detect(frame):
            label, sim = face_recognizer.predict(f["crop"])
            _, alert = engine.process_face_detection(camera_id, label, sim, lat, lon)
            if alert and alert["is_new"]:
                print(f"[{camera_id}] ALERT person={alert['match_key']} reason={alert['reason']} sim={sim:.2f}")

    return on_frame


def main():
    ap = argparse.ArgumentParser(description="Connect Sentinel Mesh to the live sandbox camera grid.")
    ap.add_argument("--host", required=True, help="Sandbox host from the Resources tab, e.g. sandbox.example.org")
    ap.add_argument("--scheme", default="http", choices=["http", "https"])
    ap.add_argument("--max-cameras", type=int, default=8, help="Pace load: only open this many cameras at once")
    ap.add_argument("--camera-ids", default=None, help="Comma-separated camera ids to open (default: first N)")
    ap.add_argument("--seconds", type=int, default=60, help="Run duration before stopping and closing all sources")
    args = ap.parse_args()

    base_url = f"{args.scheme}://{args.host}"
    print(f"Fetching camera catalogue from {base_url}/api/ingest ...")
    catalogue = fetch_catalogue(base_url)
    print(f"Catalogue has {len(catalogue)} cameras. "
          f"If this looks wrong, print(catalogue[0]['raw']) and check edge/live_ingest.py's _normalize_entry().")

    db.init_db(reset=False)
    sync_registry_from_catalogue(catalogue)

    if args.camera_ids:
        wanted = set(args.camera_ids.split(","))
        selected = [c for c in catalogue if c["camera_id"] in wanted]
    else:
        selected = catalogue[:args.max_cameras]
    if len(selected) > args.max_cameras:
        print(f"Trimming selection to --max-cameras={args.max_cameras} (pace your load).")
        selected = selected[:args.max_cameras]

    plate_detector = PlateDetector()
    plate_reader = TieredPlateReader()
    face_detector = FaceDetector()
    face_recognizer = FaceRecognizer()
    # Enrollment is startup-only in this pass. Restart this live pipeline after
    # adding or removing person photos; there is no recognizer hot-reload while
    # camera worker threads may be calling predict().
    enrollment = enroll_saved_watchlist_faces(face_recognizer, detector=face_detector)
    print(
        f"Enrolled {enrollment['people']} watchlist person(s) from "
        f"{enrollment['photos']} reference photo(s)."
    )
    if enrollment["skipped"]:
        print(f"Skipped {len(enrollment['skipped'])} enrollment item(s): {enrollment['skipped']}")
    engine = CorrelationEngine(event_bus=bus)

    deadline = time.time() + args.seconds
    sources, threads = [], []
    for entry in selected:
        if not entry["rtsp_url"]:
            print(f"Skipping {entry['camera_id']}: no rtsp_url found — check _normalize_entry() against the "
                  f"real catalogue schema.")
            continue
        camera_id = f"SANDBOX-{entry['camera_id']}"
        lat, lon = entry["lat"] or 0.0, entry["lon"] or 0.0
        # Gap 3 fix: log the codec field so mixed H.264/H.265 grids are visible
        # in the operator console. OpenCV+FFmpeg handles both transparently, but
        # logging makes silent codec-mismatch failures easier to diagnose.
        codec = entry.get("codec") or "unknown"
        print(f"[{camera_id}] codec={codec}  rtsp={entry['rtsp_url']}"
              + (f"  whep={entry['whep_url']}" if entry.get("whep_url") else "")
              + (f"  hls={entry['hls_url']}" if entry.get("hls_url") else ""))
        src = LiveRTSPSource(camera_id, entry["rtsp_url"])
        on_frame = make_on_frame(engine, plate_detector, plate_reader, face_detector, face_recognizer,
                                  camera_id, lat, lon)
        th = threading.Thread(
            target=src.run,
            kwargs={"on_frame": on_frame, "should_stop": lambda: time.time() > deadline},
            daemon=True,
        )
        sources.append(src)
        threads.append(th)

    print(f"Opening {len(threads)} live camera(s) for {args.seconds}s (RTSP over TCP, PTS-driven timing) ...")
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    print("Run window elapsed. Closing all sources — don't leave connections open past what you're using.")
    for src in sources:
        src.close()


if __name__ == "__main__":
    main()
