"""
api/main.py — REST + WebSocket API for the Sentinel Mesh dashboard.

Run (needs `pip install fastapi uvicorn[standard]` — internet required only
for this pip install step, not for anything the app does at runtime):

    cd sentinel-mesh
    pip install fastapi "uvicorn[standard]" --break-system-packages
    python3 -m uvicorn api.main:app --reload --port 8000

Then open frontend/index.html in a browser (it talks to http://localhost:8000).
"""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from bus import bus
from intelligence.service import answer_query, build_overview

app = FastAPI(
    title="Sentinel Mesh API",
    version="1.1.0",
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
    reason: str
    source_system: str = "manual"
    notes: str = ""


@app.post("/watchlist/vehicles")
def add_watchlist_vehicle(v: VehicleWatchlistIn):
    db.add_watchlist_vehicle(v.plate_number, v.reason, v.source_system, v.notes)
    return {"ok": True}


@app.get("/watchlist/persons")
def get_watchlist_persons():
    return db.list_watchlist_persons()


# ---------- Alerts ----------

@app.get("/alerts")
def get_alerts(limit: int = 100):
    return db.list_alerts(limit=max(1, min(limit, 500)))


class AlertAcknowledgement(BaseModel):
    acknowledged: bool = True


@app.patch("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, payload: AlertAcknowledgement):
    if not db.acknowledge_alert(alert_id, payload.acknowledged):
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
