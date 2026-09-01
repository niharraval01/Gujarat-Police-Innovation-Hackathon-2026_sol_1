# Sentinel Mesh
### An edge-correlated CCTV intelligence platform — Gujarat CCTV Hackathon 2026

Sentinel Mesh is a working prototype of a **hybrid architecture** combining:

- **Model 1 (mandatory)** — centralised CCTV registry + GIS mapping
- **Model 2** — unified viewing & metadata analytics
- **Model 3 patterns** — a federation/event-bus layer so heterogeneous VMS
  vendors plug in through adapters, not replacement

...plus one deliberate architectural bet that is the actual pitch of this
submission:

> **Push AI inference to the edge; only send metadata — plate reads, face
> matches, confidence scores, timestamps, GPS — to the centre. Pull raw
> video only on demand.**

This is what makes "scale to ~80,000 cameras across 1,000km" tractable on
realistic government network budgets, instead of a central data-centre
trying to ingest 80,000 live video streams. See **ARCHITECTURE.md** for
the full rationale, diagrams, and how this maps to the evaluation
framework's bonus criteria (edge processing, bandwidth optimisation,
cross-camera correlation).

---

## What's actually running here (no mockups)

Everything below is real, tested, offline-runnable code — not a script
that prints fake output. It was built and verified in an environment with
**no internet access**, deliberately, to prove the edge tier survives
exactly the low-connectivity conditions it's designed for:

| Component | Technology | Status |
|---|---|---|
| Plate localisation | OpenCV Haar cascade (bundled, offline) | ✅ real, tested |
| Plate OCR | From-scratch template-matching engine (`edge/plate_ocr.py`) | ✅ real, tested — 100% char accuracy on clean plates, correctly degrades & escalates on noisy ones |
| Tiered inference | Confidence-based edge→cloud escalation | ✅ real, tested |
| Face detection | OpenCV Haar cascade (bundled, offline) | ✅ real, tested |
| Face recognition | `cv2.face` LBPH recognizer (bundled, offline) | ✅ real, tested |
| Fuzzy watchlist matching | Levenshtein-distance correlation engine | ✅ real, tested |
| Alert/detection dedup & cooldown | Per-camera debounce, discontinuity-aware reset | ✅ real, tested |
| Live RTSP ingestion (sandbox grid) | TCP transport, PTS timing, backoff, discontinuity detection | ✅ real, control-flow tested against a mock capture — not yet run against the actual sandbox (no internet in this build env) |
| Registry + GIS data model | SQLite (Postgres/PostGIS-ready schema) | ✅ real, tested — 50 cameras / 25 districts seeded, plus catalogue-sync path for the sandbox grid |
| Route reconstruction | Multi-camera timestamp stitching | ✅ real, tested |
| REST + WebSocket API | FastAPI | ✅ written, syntax-verified (needs `pip install` — see below) |
| Dashboard | React + Leaflet + OpenStreetMap, responsive AI command centre | ✅ production build, no map API key |
| Explainable intelligence | Local threat scoring, hotspot/anomaly analysis, operations copilot | ✅ on-premise, evidence-backed, no cloud AI key |

## Quick start

```bash
cd sentinel-mesh

# 1. Run the full offline pipeline demo (no extra installs needed —
#    opencv-contrib-python and numpy are the only dependencies and are
#    commonly already present):
python3 demo/run_pipeline.py

# 2. Install the API server dependencies and start the built React dashboard:
pip install -r requirements.txt
python3 -m uvicorn api.main:app --reload --port 8000
# then open http://localhost:8000 in a browser
```

### React command centre

The dashboard is now a production-built React application with a free
OpenStreetMap base layer (no CARTO account or map API key). To rebuild it
after changing `frontend/src`:

```bash
cd frontend
npm install
npm run build
cd ..
python -m uvicorn api.main:app --port 8000
```

FastAPI serves `frontend/dist` automatically when the build exists. During UI
development, run `npm run dev`; Vite proxies the API and WebSocket routes to
port 8000.

### Local AI capabilities

`intelligence/service.py` provides three explainable, on-premise features
without any external AI service or API key:

- threat-priority scoring with auditable scoring factors;
- district hotspot and spatio-temporal movement anomaly detection;
- a natural-language operations copilot for routes, alerts, hotspots, and
  camera health.

Use `GET /ai/overview` and `POST /ai/copilot`, or open the dashboard. These
features analyze metadata only and never transmit law-enforcement data outside
the deployment boundary.

Run verification with:

```bash
pip install -r requirements-dev.txt
pytest -q
```

`demo/run_pipeline.py` seeds 50 cameras across 25 Gujarat districts, a
sample watchlist, generates a synthetic multi-camera scenario (a
watchlisted vehicle passing 4 real cameras + 15 background vehicles + 1
watchlisted person), runs it through the full edge→correlation→alert
pipeline, and prints:
- per-frame plate reads with confidence + which inference tier handled it
- which detections triggered alerts and why
- the reconstructed timestamped route of the watchlisted vehicle across
  4 districts

## Project layout

```
sentinel-mesh/
├── db.py                    # registry / watchlist / detections / alerts (SQLite)
├── bus.py                   # in-process pub/sub (Kafka/MQTT swap-in point)
├── seed_data.py              # 50-camera registry + sample watchlist
├── edge/
│   ├── plate_detector.py     # Haar cascade plate localisation
│   ├── plate_ocr.py          # from-scratch OCR + tiered escalation
│   ├── face_pipeline.py      # Haar face detection + LBPH recognition
│   ├── live_ingest.py        # real RTSP client for the sandbox grid (TCP, PTS, backoff)
│   └── test_live_ingest_offline.py  # control-flow tests against a mock capture
├── correlation/
│   └── engine.py             # fuzzy watchlist matching + dedup/cooldown + alert generation
├── demo/
│   ├── synth_feed.py         # synthetic multi-camera scenario generator
│   ├── run_pipeline.py       # end-to-end offline demo runner (synthetic frames)
│   └── run_live.py            # real orchestrator against the sandbox camera grid
├── api/
│   └── main.py                # FastAPI REST + WebSocket backend
├── frontend/
│   ├── src/                   # React command centre source
│   └── dist/                  # production build served by FastAPI
├── intelligence/
│   └── service.py             # local risk scoring, anomalies, hotspots, copilot
├── ARCHITECTURE.md            # HLD content — architecture, diagrams, scaling
└── requirements.txt
```

## Path to production (what to swap in once you have internet / real feeds)

Every module below was written with a narrow, documented interface so the
swap is additive, not a rewrite:

1. **Plate OCR** — implement `DeepANPRAdapter.read()` in `edge/plate_ocr.py`
   with EasyOCR / PaddleOCR / a YOLOv8-ANPR+CRNN model. The tiered reader
   already calls it automatically when edge confidence is low.
2. **Face recognition** — swap `FaceRecognizer` (LBPH) for ArcFace/
   InsightFace embeddings + a vector index (FAISS) once you're matching
   against AFIS/NAFIS at scale. Same `enroll()` / `predict()` interface.
3. **Event bus** — swap `bus.py`'s in-process queue for Kafka or MQTT.
   `correlation/engine.py` only calls `.publish(topic, payload)`.
4. **Database** — swap SQLite for PostgreSQL + PostGIS (schema in `db.py`
   is vanilla SQL; add lat/lon geometry columns for real spatial queries).
5. **Video ingestion** — today the edge modules take a numpy frame from a
   synthetic generator. Point them at real frames via OpenCV's
   `cv2.VideoCapture(rtsp_url)` or an ONVIF client — the detector/OCR/face
   calls downstream don't change.
6. **Camera onboarding at real sites** — `db.upsert_camera()` /
   `POST /cameras` already accept vendor, VMS platform, connectivity type;
   wire this to whatever bulk-import or Model 3 adapter you build for each
   vendor's SDK.

## Connecting to the real evaluation grid (Resources tab sandbox)

The hackathon's Resources tab publishes a separate integration reference
for the actual live camera grid used in the Step 4 technical evaluation
(RTSP/WebRTC/HLS, a `/api/ingest` catalogue, no file download). That guide
imposes real constraints a synthetic demo never exercises — continuous
live video means the same plate is seen on every frame for as long as a
vehicle is in view, feeds reconnect and loop, and frame rate is not
constant. This build now has a dedicated layer for that:

- **`edge/live_ingest.py`** — `LiveRTSPSource` forces RTSP-over-TCP,
  drives all timing from PTS (never wall-clock arrival time — the gateway
  replays a buffered GOP on connect, so the first second or two arrives
  faster than real time), reconnects with exponential backoff (2s → 30s
  cap), tolerates join-time decoder warnings without treating them as
  fatal, and flags scene discontinuities (the feed looping back to its
  start). `fetch_catalogue()` reads `/api/ingest` so camera ids and URLs
  are never hard-coded.
- **`correlation/engine.py`** now debounces: a plate sitting in frame for
  several seconds of continuous video produces one detection row and one
  alert (with `last_seen` advancing), not one of each per frame. A scene
  discontinuity calls `engine.reset_camera(camera_id)`, clearing that
  camera's dedup state so a genuinely new sighting right after a hard cut
  isn't suppressed by stale context.
- **`demo/run_live.py`** — the real orchestrator: fetches the catalogue,
  syncs it into the registry, opens up to `--max-cameras` live sources on
  their own threads (pacing, per the guide), and runs the same
  detector → OCR → face-rec → correlation pipeline used in the synthetic
  demo.
- **`edge/test_live_ingest_offline.py`** — since this build environment
  has no internet, the ingestion control flow (reconnect/backoff, warm-up
  tolerance, discontinuity detection) is verified against a scripted mock
  capture instead of a real RTSP server. Run this, and
  `python3 -c "..."`-style checks in this README's history, before trusting
  `run_live.py` against the real grid.

**Before the live evaluation:** the catalogue's exact JSON key names
aren't given in the reference doc, only described in prose. The moment you
have real access, run `fetch_catalogue()` once, print an entry's `raw`
field, and tighten `_normalize_entry()` in `edge/live_ingest.py` to match
exactly — don't trust the defensive guess under time pressure. Also call
`face_recognizer.enroll(...)` with real watchlist photos before relying on
person alerts; an untrained recognizer never matches, by design.

## Honesty notes (what's simulated vs. what's real)

Per the hackathon brief's explicit allowance to "create and use
representative datasets," the **video source** in this offline demo is
synthetic (drawn with OpenCV, not downloaded stock footage). Everything
downstream of the pixels — detection, OCR, face recognition, fuzzy
matching, alerting, GIS route reconstruction, the API, the dashboard — is
real, operational code, not a scripted mock. For your actual submission,
re-run `demo/run_pipeline.py`-style logic against your own phone footage
or webcam capture (explicitly permitted as "Demonstration on Participant's
Own Feed") — the pipeline code does not change, only the frame source does.
