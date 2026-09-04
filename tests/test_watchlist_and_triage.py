import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import cv2
import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

import db
from edge.face_pipeline import enroll_saved_watchlist_faces


@contextmanager
def _temporary_database():
    original = db.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        db.DB_PATH = Path(directory) / "sentinel-test.db"
        try:
            yield Path(directory)
        finally:
            db.DB_PATH = original


def _camera_and_alert():
    db.upsert_camera({
        "camera_id": "TEST-CAM-1",
        "name": "Test camera",
        "department": "Home",
        "lat": 23.0,
        "lon": 72.0,
        "district": "Test district",
    })
    detection_id = db.record_detection(
        "TEST-CAM-1", "plate", "GJ01AA0001", 0.95, "edge", 23.0, 72.0
    )
    return db.record_alert(
        detection_id, "TEST-CAM-1", "vehicle", "GJ01AA0001", "wanted", 0.95, 23.0, 72.0
    )


def test_existing_database_gets_operator_notes_migration():
    with _temporary_database():
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            conn.execute(
                """CREATE TABLE alerts (
                    alert_id TEXT PRIMARY KEY, detection_id TEXT, camera_id TEXT,
                    ts REAL, last_seen REAL, match_type TEXT, match_key TEXT,
                    reason TEXT, confidence REAL, lat REAL, lon REAL,
                    acknowledged INTEGER DEFAULT 0
                )"""
            )
            conn.commit()
        db.init_db(reset=False)
        with db.get_conn() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(alerts)")}
        assert "operator_notes" in columns


def test_alert_status_filters_and_operator_notes():
    with _temporary_database():
        db.init_db(reset=True)
        alert_id = _camera_and_alert()
        assert [row["alert_id"] for row in db.list_alerts(status="new")] == [alert_id]
        assert db.list_alerts(status="acknowledged") == []

        assert db.acknowledge_alert(alert_id, True, "Dispatch unit 12 notified")
        assert db.list_alerts(status="new") == []
        acknowledged = db.list_alerts(status="acknowledged")
        assert acknowledged[0]["operator_notes"] == "Dispatch unit 12 notified"
        assert len(db.list_alerts(status="all")) == 1

        assert db.acknowledge_alert(alert_id, False)
        reopened = db.get_alert(alert_id)
        assert reopened["acknowledged"] == 0
        assert reopened["operator_notes"] == "Dispatch unit 12 notified"


def test_watchlist_delete_and_stable_person_labels():
    with _temporary_database():
        db.init_db(reset=True)
        db.add_watchlist_vehicle("gj 01 aa 0001", "stolen", notes="case-1")
        assert db.list_watchlist_vehicles()[0]["plate_number"] == "GJ01AA0001"
        assert db.delete_watchlist_vehicle("GJ 01 AA 0001")

        db.add_watchlist_person("PERSON-1", "Test Person", "wanted", notes="case-2")
        first_label = db.ensure_person_face_label("PERSON-1")
        assert first_label == db.ensure_person_face_label("PERSON-1")
        db.add_watchlist_person("PERSON-1", "Updated Name", "suspect")
        assert db.get_watchlist_person("PERSON-1")["face_label_id"] == first_label
        assert db.delete_watchlist_person("PERSON-1")


def test_saved_photos_are_enrolled_under_database_label():
    class FakeDetector:
        def detect(self, image):
            return []

    class FakeRecognizer:
        def __init__(self):
            self.enrollment = None

        def enroll(self, enrollment):
            self.enrollment = enrollment

    with _temporary_database() as directory:
        db.init_db(reset=True)
        db.add_watchlist_person("PERSON-2", "Reference Person", "missing")
        expected_label = db.ensure_person_face_label("PERSON-2")
        faces_root = directory / "watchlist_faces"
        person_dir = faces_root / "PERSON-2"
        person_dir.mkdir(parents=True)
        assert cv2.imwrite(str(person_dir / "1.jpg"), np.full((80, 60, 3), 128, dtype=np.uint8))

        recognizer = FakeRecognizer()
        report = enroll_saved_watchlist_faces(recognizer, faces_root, detector=FakeDetector())
        assert report["people"] == 1
        assert report["photos"] == 1
        assert list(recognizer.enrollment) == [expected_label]
        assert recognizer.enrollment[expected_label][0].ndim == 2


if __name__ == "__main__":
    tests = [
        test_existing_database_gets_operator_notes_migration,
        test_alert_status_filters_and_operator_notes,
        test_watchlist_delete_and_stable_person_labels,
        test_saved_photos_are_enrolled_under_database_label,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print("All watchlist and triage tests passed.")
