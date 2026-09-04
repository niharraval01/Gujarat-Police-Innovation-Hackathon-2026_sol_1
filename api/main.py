"""
api/main.py — REST + WebSocket API for the Sentinel Mesh dashboard.

Run (needs `pip install fastapi uvicorn[standard]` — internet required only
for this pip install step, not for anything the app does at runtime):

    cd sentinel-mesh
    pip install fastapi "uvicorn[standard]" --break-system-packages
    python3 -m uvicorn api.main:app --reload --port 8000

Then open frontend/index.html in a browser (it talks to http://localhost:8000).
"""

import re
import shutil
import sys
import time
from pathlib import Path
from typing import Literal
from urllib.parse import quote

sys.path.append(str(Path(__file__).parent.parent))

import cv2
import numpy as np
from fastapi import File, Form, FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from bus import bus
from intelligence.service import answer_query, build_overview

WATCHLIST_FACE_ROOT = (Path(__file__).parent.parent / "data" / "watchlist_faces").resolve()
PERSON_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
PHOTO_NAME_PATTERN = re.compile(r"^\d+\.jpg$")
MAX_REFERENCE_PHOTOS = 8
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTO_PIXELS = 25_000_000

app = FastAPI(
    title="Sentinel Mesh API",
    version="1.2.0",
    description="Edge-correlated CCTV intelligence for the Gujarat command centre.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the command-centre origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db(reset=False)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Registry (Model 1 foundation) ----------

@app.get("/cameras")
def get_cameras():
    return db.list_cameras()


class CameraIn(BaseModel):
    camera_id: str
    name: str
    department: str
    vendor: str = ""
    vms_platform: str = ""
    lat: float
    lon: float
    district: str = ""
    camera_type: str = "fixed"
    connectivity: str = "fiber"
    storage_days: int = 7
    rtsp_url: str | None = None
    whep_url: str | None = None
    hls_url: str | None = None


@app.post("/cameras")
def create_camera(cam: CameraIn):
    db.upsert_camera(cam.model_dump())
    return {"ok": True}


# ---------- Watchlists ----------

@app.get("/watchlist/vehicles")
def get_watchlist_vehicles():
    return db.list_watchlist_vehicles()


class VehicleWatchlistIn(BaseModel):
    plate_number: str
    reason: Literal["stolen", "wanted", "blacklisted", "suspect"]
    source_system: str = "manual"
    notes: str = ""


@app.post("/watchlist/vehicles")
def add_watchlist_vehicle(v: VehicleWatchlistIn):
    db.add_watchlist_vehicle(v.plate_number, v.reason, v.source_system, v.notes)
    return {"ok": True}


@app.delete("/watchlist/vehicles/{plate_number}")
def remove_watchlist_vehicle(plate_number: str):
    if not db.delete_watchlist_vehicle(plate_number):
        raise HTTPException(status_code=404, detail="Vehicle watchlist entry not found")
    return {"ok": True}


def _person_face_dir(person_id: str, create: bool = False):
    person_id = person_id.strip()
    if not PERSON_ID_PATTERN.fullmatch(person_id) or person_id in {".", ".."}:
        raise HTTPException(
            status_code=422,
            detail="person_id must use 1-64 letters, numbers, dots, dashes, or underscores",
        )
    target = (WATCHLIST_FACE_ROOT / person_id).resolve()
    if WATCHLIST_FACE_ROOT != target and WATCHLIST_FACE_ROOT not in target.parents:
        raise HTTPException(status_code=422, detail="Invalid person_id path")
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def _person_with_photos(person):
    folder = _person_face_dir(person["person_id"])
    photos = sorted(folder.glob("*.jpg")) if folder.exists() else []
    encoded_id = quote(person["person_id"], safe="")
    return {
        **person,
        "photo_count": len(photos),
        "photo_urls": [
            f"/watchlist/persons/{encoded_id}/photos/{quote(photo.name)}"
            for photo in photos
        ],
    }


@app.get("/watchlist/persons")
def get_watchlist_persons():
    return [_person_with_photos(person) for person in db.list_watchlist_persons()]


@app.post("/watchlist/persons")
async def add_watchlist_person(
    person_id: str = Form(...),
    name: str = Form(...),
    reason: Literal["wanted", "missing", "suspect"] = Form(...),
    source_system: str = Form("manual"),
    notes: str = Form(""),
    photos: list[UploadFile] = File(...),
):
    """Store reference photos and persist a stable LBPH label.

    Enrollment is intentionally picked up on the next live-pipeline start;
    hot-reloading a recognizer while camera threads are active is out of scope.
    """
    person_id = person_id.strip()
    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name cannot be empty")
    if not 1 <= len(photos) <= MAX_REFERENCE_PHOTOS:
        raise HTTPException(status_code=422, detail=f"Upload 1-{MAX_REFERENCE_PHOTOS} reference photos")

    folder = _person_face_dir(person_id)
    existing = sorted(folder.glob("*.jpg")) if folder.exists() else []
    if len(existing) + len(photos) > MAX_REFERENCE_PHOTOS:
        raise HTTPException(
            status_code=422,
            detail=f"A person can have at most {MAX_REFERENCE_PHOTOS} reference photos",
        )

    encoded_photos = []
    for photo in photos:
        raw = await photo.read(MAX_PHOTO_BYTES + 1)
        await photo.close()
        if not raw or len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail=f"{photo.filename or 'Photo'} is empty or larger than 8 MB")
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=422, detail=f"{photo.filename or 'Photo'} is not a readable image")
        if image.shape[0] * image.shape[1] > MAX_PHOTO_PIXELS:
            raise HTTPException(status_code=422, detail=f"{photo.filename or 'Photo'} dimensions are too large")
        ok, jpg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise HTTPException(status_code=422, detail=f"Could not normalize {photo.filename or 'photo'}")
        encoded_photos.append(jpg.tobytes())

    next_number = max([int(photo.stem) for photo in existing if photo.stem.isdigit()] or [0]) + 1
    created = []
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for offset, payload in enumerate(encoded_photos):
            destination = folder / f"{next_number + offset}.jpg"
            temporary = folder / f".{next_number + offset}.upload"
            temporary.write_bytes(payload)
            temporary.replace(destination)
            created.append(destination)
        db.add_watchlist_person(person_id, name, reason, None, source_system.strip() or "manual", notes)
        label_id = db.ensure_person_face_label(person_id)
    except Exception:
        for photo in created:
            photo.unlink(missing_ok=True)
        raise

    return {
        "ok": True,
        "person": _person_with_photos(db.get_watchlist_person(person_id)),
        "face_label_id": label_id,
        "restart_required": True,
        "message": "Reference photos saved. Restart the live pipeline to enroll them.",
    }


@app.get("/watchlist/persons/{person_id}/photos/{photo_name}")
def get_watchlist_photo(person_id: str, photo_name: str):
    if not PHOTO_NAME_PATTERN.fullmatch(photo_name):
        raise HTTPException(status_code=404, detail="Photo not found")
    photo = _person_face_dir(person_id) / photo_name
    if not photo.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(photo, media_type="image/jpeg")


@app.delete("/watchlist/persons/{person_id}")
def remove_watchlist_person(person_id: str):
    folder = _person_face_dir(person_id)
    if not db.delete_watchlist_person(person_id):
        raise HTTPException(status_code=404, detail="Person watchlist entry not found")
    if folder.exists():
        shutil.rmtree(folder)
    return {"ok": True}


# ---------- Alerts ----------

@app.get("/alerts")
def get_alerts(
    limit: int = 100,
    status: Literal["new", "acknowledged", "all"] = "new",
):
    return db.list_alerts(limit=max(1, min(limit, 500)), status=status)


class AlertAcknowledgement(BaseModel):
    acknowledged: bool = True
    note: str | None = None


@app.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, payload: AlertAcknowledgement):
    if payload.note is not None and len(payload.note) > 2000:
        raise HTTPException(status_code=422, detail="Operator note must be 2000 characters or fewer")
    if not db.acknowledge_alert(alert_id, payload.acknowledged, payload.note):
        raise HTTPException(status_code=404, detail="Alert not found")
    return db.get_alert(alert_id)


# ---------- Vehicle movement / route reconstruction ----------

@app.get("/vehicles/{plate_number}/route")
def get_vehicle_route(plate_number: str):
    return db.vehicle_route(plate_number)


# ---------- Camera detail ----------

@app.get("/cameras/{camera_id}")
def get_camera(camera_id: str):
    cams = db.list_cameras()
    cam = next((c for c in cams if c["camera_id"] == camera_id), None)
    if cam is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam


# ---------- Catalogue debug (operator tool) ----------

@app.get("/api/ingest/debug")
def debug_ingest_catalogue(host: str, scheme: str = "http"):
    """Operator debug tool: fetch and compare the raw vs. normalised /api/ingest
    catalogue from the given sandbox host.

    Use this on evaluation day to verify that edge/live_ingest.py's
    _normalize_entry() maps the actual JSON keys correctly before starting
    the live pipeline. If the normalized fields show None where you expect
    a URL, look at the 'raw' field and fix _normalize_entry().

    Example:
        GET /api/ingest/debug?host=sandbox.example.org
        GET /api/ingest/debug?host=sandbox.example.org&scheme=https
    """
    from edge.live_ingest import fetch_catalogue
    base_url = f"{scheme}://{host}"
    try:
        catalogue = fetch_catalogue(base_url, timeout=10)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach {base_url}/api/ingest: {exc}"
        )
    return {
        "source": f"{base_url}/api/ingest",
        "count": len(catalogue),
        "cameras": [
            {
                "normalized": {
                    k: v for k, v in entry.items() if k != "raw"
                },
                "raw": entry["raw"],
            }
            for entry in catalogue
        ],
    }


# ---------- Dashboard stats ----------

@app.get("/stats")
def get_stats():
    cams = db.list_cameras()
    alerts = db.list_alerts(limit=9999)
    return {
        "total_cameras": len(cams),
        "online": sum(1 for c in cams if c.get("status") == "online"),
        "offline": sum(1 for c in cams if c.get("status") == "offline"),
        "degraded": sum(1 for c in cams if c.get("status") == "degraded"),
        "districts": len(set(c.get("district", "") for c in cams)),
        "total_alerts": len(alerts),
        "watchlist_vehicles": len(db.list_watchlist_vehicles()),
        "watchlist_persons": len(db.list_watchlist_persons()),
    }


# ---------- Local explainable intelligence ----------

@app.get("/ai/overview")
def ai_overview():
    """Threat posture, prioritized alerts, hotspots, and anomaly evidence.

    Runs entirely inside the deployment boundary; no cloud AI key is used.
    """
    return build_overview()


class CopilotQuery(BaseModel):
    question: str


@app.post("/ai/copilot")
def ai_copilot(query: CopilotQuery):
    if not query.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")
    return answer_query(query.question)


@app.get("/detections/recent")
def recent_detections(limit: int = 50):
    return db.list_recent_detections(limit=max(1, min(limit, 500)))


@app.get("/analytics/timeline")
def activity_timeline(hours: int = 24):
    hours = max(1, min(hours, 168))
    bucket_seconds = 3600 if hours > 12 else 900
    since = time.time() - hours * 3600
    rows = db.detection_timeline(since, bucket_seconds)
    buckets = {}
    for row in rows:
        index = int(row["bucket"])
        bucket = buckets.setdefault(index, {
            "ts": since + index * bucket_seconds,
            "plate": 0,
            "face": 0,
            "total": 0,
        })
        count = int(row["count"])
        bucket[row["detection_type"]] = count
        bucket["total"] += count
    return {
        "hours": hours,
        "bucket_seconds": bucket_seconds,
        "series": [buckets[key] for key in sorted(buckets)],
    }


# ---------- Live alert feed over WebSocket ----------

@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    queue = bus.subscribe("alert")
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        bus.unsubscribe("alert", queue)


# ---------- Serve the dashboard itself ----------
frontend_root = Path(__file__).parent.parent / "frontend"
frontend_dir = frontend_root / "dist" if (frontend_root / "dist").exists() else frontend_root
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
