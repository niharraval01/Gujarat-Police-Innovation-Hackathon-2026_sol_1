"""
db.py — Registry, Watchlist, Detection & Alert store.

Uses SQLite for the hackathon demo (zero-config, offline, fully working).
The schema is deliberately vanilla SQL so migrating to PostgreSQL + PostGIS
for the statewide deployment (Model 1 foundation) is a connection-string
change, not a rewrite — see ARCHITECTURE.md "Path to Production".
"""

import sqlite3
import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "sentinel.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    camera_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    department      TEXT NOT NULL,
    vendor          TEXT,
    vms_platform    TEXT,
    lat             REAL,
    lon             REAL,
    district        TEXT,
    camera_type     TEXT,          -- fixed / PTZ / ANPR-dedicated
    connectivity    TEXT,          -- fiber / 4G / satellite
    storage_days    INTEGER DEFAULT 7,
    status          TEXT DEFAULT 'online',   -- online / offline / degraded
    last_heartbeat  REAL,
    rtsp_url        TEXT,          -- AI-inference source (edge nodes read this)
    whep_url        TEXT,          -- WebRTC low-latency browser preview (on-demand viewing)
    hls_url         TEXT           -- dashboard/mobile/restricted-network fallback preview
);

CREATE TABLE IF NOT EXISTS watchlist_vehicles (
    plate_number    TEXT PRIMARY KEY,
    reason          TEXT NOT NULL,     -- stolen / wanted / blacklisted / suspect
    source_system   TEXT,              -- VAHAN / eGujCop / manual
    added_at        REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS watchlist_persons (
    person_id       TEXT PRIMARY KEY,
    name            TEXT,
    reason          TEXT NOT NULL,     -- wanted / missing / suspect
    source_system   TEXT,              -- eGujCop / AFIS / NAFIS / manual
    face_label_id   INTEGER,           -- maps to LBPH trained label
    added_at        REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS detections (
    detection_id    TEXT PRIMARY KEY,
    camera_id       TEXT NOT NULL,
    ts              REAL NOT NULL,
    detection_type  TEXT NOT NULL,     -- plate / face
    raw_value       TEXT,              -- OCR'd plate text or face label
    confidence      REAL,
    inference_tier  TEXT,              -- edge / escalated
    lat             REAL,
    lon             REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id        TEXT PRIMARY KEY,
    detection_id    TEXT NOT NULL,
    camera_id       TEXT NOT NULL,
    ts              REAL NOT NULL,
    last_seen       REAL,
    match_type      TEXT NOT NULL,     -- vehicle / person
    match_key       TEXT NOT NULL,     -- plate_number or person_id
    reason          TEXT,
    confidence       REAL,
    lat             REAL,
    lon             REAL,
    acknowledged    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_detections_value ON detections(raw_value);
CREATE INDEX IF NOT EXISTS idx_detections_camera_ts ON detections(camera_id, ts);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(reset=False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------- Cameras ----------

def upsert_camera(cam: dict):
    defaults = {"storage_days": 7, "status": "online", "last_heartbeat": time.time(),
                "vendor": None, "vms_platform": None, "district": None, "camera_type": None,
                "connectivity": None, "rtsp_url": None, "whep_url": None, "hls_url": None}
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO cameras (camera_id, name, department, vendor, vms_platform,
                lat, lon, district, camera_type, connectivity, storage_days, status, last_heartbeat,
                rtsp_url, whep_url, hls_url)
               VALUES (:camera_id,:name,:department,:vendor,:vms_platform,:lat,:lon,
                :district,:camera_type,:connectivity,:storage_days,:status,:last_heartbeat,
                :rtsp_url,:whep_url,:hls_url)
               ON CONFLICT(camera_id) DO UPDATE SET
                 status=excluded.status, last_heartbeat=excluded.last_heartbeat,
                 rtsp_url=excluded.rtsp_url, whep_url=excluded.whep_url, hls_url=excluded.hls_url""",
            {**defaults, **cam},
        )


def list_cameras():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM cameras")]


def set_camera_heartbeat(camera_id, status="online"):
    with get_conn() as conn:
        conn.execute(
            "UPDATE cameras SET status=?, last_heartbeat=? WHERE camera_id=?",
            (status, time.time(), camera_id),
        )


# ---------- Watchlists ----------

def add_watchlist_vehicle(plate_number, reason, source_system="manual", notes=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO watchlist_vehicles (plate_number, reason, source_system, added_at, notes)
               VALUES (?,?,?,?,?)
               ON CONFLICT(plate_number) DO UPDATE SET reason=excluded.reason""",
            (plate_number.upper().replace(" ", ""), reason, source_system, time.time(), notes),
        )


def list_watchlist_vehicles():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM watchlist_vehicles")]


def add_watchlist_person(person_id, name, reason, face_label_id=None, source_system="manual", notes=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO watchlist_persons (person_id, name, reason, source_system, face_label_id, added_at, notes)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(person_id) DO UPDATE SET reason=excluded.reason""",
            (person_id, name, reason, source_system, face_label_id, time.time(), notes),
        )


def list_watchlist_persons():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM watchlist_persons")]


def find_person_by_label(face_label_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM watchlist_persons WHERE face_label_id=?", (face_label_id,)
        ).fetchone()
        return dict(row) if row else None


# ---------- Detections & Alerts ----------

def record_detection(camera_id, detection_type, raw_value, confidence, inference_tier, lat, lon, ts=None):
    det_id = str(uuid.uuid4())
    now = ts if ts is not None else time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO detections (detection_id, camera_id, ts, detection_type, raw_value,
                confidence, inference_tier, lat, lon) VALUES (?,?,?,?,?,?,?,?,?)""",
            (det_id, camera_id, now, detection_type, raw_value, confidence, inference_tier, lat, lon),
        )
    return det_id


def record_alert(detection_id, camera_id, match_type, match_key, reason, confidence, lat, lon, ts=None):
    alert_id = str(uuid.uuid4())
    now = ts if ts is not None else time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO alerts (alert_id, detection_id, camera_id, ts, last_seen, match_type, match_key,
                reason, confidence, lat, lon) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (alert_id, detection_id, camera_id, now, now, match_type, match_key, reason, confidence, lat, lon),
        )
    return alert_id


def touch_alert(alert_id, ts=None):
    """Update last_seen on an existing alert instead of creating a duplicate
    row — called when the same watchlist match is still in frame (cooldown
    window active). Keeps one alert card per real event instead of one per
    frame."""
    with get_conn() as conn:
        conn.execute("UPDATE alerts SET last_seen=? WHERE alert_id=?", (ts or time.time(), alert_id))


def list_alerts(limit=100):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
        )]


def vehicle_route(plate_number):
    """Reconstruct a vehicle's movement history from timestamped detections across cameras."""
    plate_number = plate_number.upper().replace(" ", "")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT d.ts, d.camera_id, d.confidence, d.lat, d.lon, c.name AS camera_name, c.district
               FROM detections d JOIN cameras c ON c.camera_id = d.camera_id
               WHERE d.detection_type='plate' AND d.raw_value=?
               ORDER BY d.ts ASC""",
            (plate_number,),
        ).fetchall()
        return [dict(r) for r in rows]
