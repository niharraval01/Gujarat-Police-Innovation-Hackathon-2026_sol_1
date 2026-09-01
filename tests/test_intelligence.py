import tempfile
import time
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import db
from intelligence.service import answer_query, build_overview, score_alert


@contextmanager
def _temporary_database():
    original = db.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        db.DB_PATH = Path(directory) / "sentinel-test.db"
        try:
            yield
        finally:
            db.DB_PATH = original


def _seed_minimal_database():
    db.init_db(reset=True)
    db.upsert_camera({
        "camera_id": "GJ-AHM-001",
        "name": "Ahmedabad Checkpoint",
        "department": "Home",
        "lat": 23.02,
        "lon": 72.57,
        "district": "Ahmedabad",
        "status": "online",
    })
    db.add_watchlist_vehicle("GJ01AA0001", "wanted", "eGujCop")
    detection_id = db.record_detection(
        "GJ-AHM-001", "plate", "GJ01AA0001", 0.94, "edge", 23.02, 72.57
    )
    db.record_alert(
        detection_id, "GJ-AHM-001", "vehicle", "GJ01AA0001", "wanted", 0.94, 23.02, 72.57
    )


def test_score_alert_is_explainable():
    result = score_alert({"reason": "wanted", "confidence": 0.95, "ts": time.time()}, repeat_count=2)
    assert result["score"] >= 80
    assert result["severity"] == "critical"
    assert len(result["factors"]) == 4


def test_overview_prioritizes_current_alert():
    with _temporary_database():
        _seed_minimal_database()
        result = build_overview()
        assert result["data_boundary"].startswith("on-premise")
        assert result["metrics"]["unacknowledged"] == 1
        assert result["priority_alerts"][0]["match_key"] == "GJ01AA0001"
        assert result["hotspots"][0]["district"] == "Ahmedabad"


def test_copilot_traces_plate():
    with _temporary_database():
        _seed_minimal_database()
        result = answer_query("Trace GJ01AA0001")
        assert result["intent"] == "vehicle_route"
        assert "1 correlated sighting" in result["answer"]
        assert result["evidence"][0]["district"] == "Ahmedabad"


if __name__ == "__main__":
    tests = [
        test_score_alert_is_explainable,
        test_overview_prioritizes_current_alert,
        test_copilot_traces_plate,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print("All intelligence tests passed.")
