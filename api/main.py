"""
api/main.py — REST + WebSocket API for the Sentinel Mesh dashboard.

Run (needs `pip install fastapi uvicorn[standard]` — internet required only
for this pip install step, not for anything the app does at runtime):

    cd sentinel-mesh
    pip install fastapi "uvicorn[standard]" --break-system-packages
    python3 -m uvicorn api.main:app --reload --port 8000

Then open frontend/index.html in a browser (it talks to http://localhost:8000).
"""

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from bus import bus

app = FastAPI(title="Sentinel Mesh API", version="0.1.0")

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
    db.upsert_camera(cam.dict())
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
    return db.list_alerts(limit=limit)


# ---------- Vehicle movement / route reconstruction ----------

@app.get("/vehicles/{plate_number}/route")
def get_vehicle_route(plate_number: str):
    return db.vehicle_route(plate_number)


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
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
