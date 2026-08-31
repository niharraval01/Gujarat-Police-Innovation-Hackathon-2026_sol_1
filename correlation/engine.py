"""
correlation/engine.py — the piece that turns "a metadata event arrived"
into "an alert was raised". This is the heart of the AI + watchlist
correlation requirement in the problem statement.

Design notes:
- Plate OCR is never perfect, so exact-string matching against the
  watchlist would silently miss real hits. We use a small edit-distance
  (Levenshtein) fuzzy matcher and accept 1-character drift for plates of
  length >= 8 — tunable via MAX_EDIT_DISTANCE.
- Matching is done in-process against SQLite for the demo. At statewide
  scale this becomes a stream processor (Kafka Streams / Flink) doing the
  same fuzzy-join against a watchlist table replicated from VAHAN/eGujCop —
  see ARCHITECTURE.md.
- Against a LIVE feed (see edge/live_ingest.py) the same plate is seen on
  every frame for as long as the vehicle is in view — often for seconds,
  at whatever frame rate the camera happens to deliver. Without dedup this
  turns one real event into dozens of duplicate detection rows and alert
  cards. Two independent debounce windows handle this:
    * MIN_DETECTION_INTERVAL_SECONDS — collapse repeated raw sightings of
      the same value at the same camera into one detection row, touching
      its timestamp rather than inserting a new one.
    * ALERT_COOLDOWN_SECONDS — collapse repeated watchlist hits into one
      alert card, updating `last_seen` instead of re-alerting and re-
      pushing to the dashboard on every frame.
  Both caches are per-camera and are cleared by reset_camera(), which the
  live ingestion loop calls whenever it detects a scene discontinuity
  (the sandbox feed looping back to its start) — old dwell-time context
  is no longer valid once the scene has hard-cut.
"""

import time

import db

MAX_EDIT_DISTANCE = 1
MIN_PLATE_LEN_FOR_FUZZY = 8
MIN_DETECTION_INTERVAL_SECONDS = 4
ALERT_COOLDOWN_SECONDS = 45


def _levenshtein(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > MAX_EDIT_DISTANCE + 1:
        return MAX_EDIT_DISTANCE + 1  # short-circuit, too far apart to matter
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def _best_fuzzy_match(plate_text, watchlist_plates):
    plate_text = plate_text.upper().replace(" ", "")
    if not plate_text:
        return None
    best, best_dist = None, MAX_EDIT_DISTANCE + 1
    for wl_plate in watchlist_plates:
        if abs(len(wl_plate) - len(plate_text)) > MAX_EDIT_DISTANCE:
            continue
        dist = _levenshtein(plate_text, wl_plate)
        allowed = MAX_EDIT_DISTANCE if len(plate_text) >= MIN_PLATE_LEN_FOR_FUZZY else 0
        if dist <= allowed and dist < best_dist:
            best, best_dist = wl_plate, dist
    return best


class CorrelationEngine:
    def __init__(self, event_bus=None, clock=time.time):
        """
        Args:
            event_bus: optional pub/sub for live push to the dashboard WebSocket.
            clock: callable returning current time as a float (seconds). Defaults
                   to ``time.time`` (wall-clock).

        NOTE — deliberate design choice: the dedup and cooldown windows
        (MIN_DETECTION_INTERVAL_SECONDS, ALERT_COOLDOWN_SECONDS) use
        wall-clock time, not the PTS from the video frame. This is intentional:
          * PTS is the right source of truth for frame-ordering and timing
            inside the ingestion pipeline (see edge/live_ingest.py), where we
            want to correctly detect scene discontinuities and avoid frame-rate
            assumptions.
          * The dedup/cooldown windows are operator-facing: "don't raise a
            second alert for the same plate within 45 real seconds" is a
            meaningful statement about calendar time for a human dispatcher,
            not about video PTS. Using PTS here would make the window
            video-speed-dependent and break for looped or accelerated feeds.
          * ``clock`` is injectable so unit tests can control time without
            touching real system time. See correlation/test_engine.py.
        """
        self.bus = event_bus
        self._clock = clock
        self._last_detection = {}   # (camera_id, dtype, value) -> {"id": detection_id, "ts": float}
        self._last_alert = {}       # (camera_id, match_type, match_key) -> {"alert_id": ..., "ts": float}

    def reset_camera(self, camera_id):
        """Drop this camera's dedup/cooldown state — call on a detected
        scene discontinuity (feed loop restart) so stale dwell-time context
        doesn't suppress a genuinely new sighting after the hard cut."""
        for cache in (self._last_detection, self._last_alert):
            for key in [k for k in cache if k[0] == camera_id]:
                del cache[key]

    def _get_or_record_detection(self, camera_id, dtype, value, confidence, tier, lat, lon):
        now = self._clock()
        key = (camera_id, dtype, value)
        prior = self._last_detection.get(key)
        if prior and now - prior["ts"] < MIN_DETECTION_INTERVAL_SECONDS:
            prior["ts"] = now
            return prior["id"], False
        detection_id = db.record_detection(camera_id, dtype, value, confidence, tier, lat, lon, ts=now)
        self._last_detection[key] = {"id": detection_id, "ts": now}
        return detection_id, True

    def _raise_or_touch_alert(self, camera_id, detection_id, match_type, match_key, reason, confidence, lat, lon,
                               extra=None):
        now = self._clock()
        key = (camera_id, match_type, match_key)
        prior = self._last_alert.get(key)
        if prior and now - prior["ts"] < ALERT_COOLDOWN_SECONDS:
            prior["ts"] = now
            db.touch_alert(prior["alert_id"], now)
            return prior["alert_id"], False
        alert_id = db.record_alert(detection_id, camera_id, match_type, match_key, reason, confidence, lat, lon, ts=now)
        self._last_alert[key] = {"alert_id": alert_id, "ts": now}
        return alert_id, True

    def process_plate_detection(self, camera_id, plate_text, confidence, inference_tier, lat, lon):
        norm_plate = plate_text.upper().replace(" ", "")
        detection_id, _ = self._get_or_record_detection(camera_id, "plate", norm_plate, confidence,
                                                          inference_tier, lat, lon)
        watchlist = {v["plate_number"]: v for v in db.list_watchlist_vehicles()}
        match = _best_fuzzy_match(plate_text, list(watchlist.keys()))
        alert = None
        if match:
            entry = watchlist[match]
            alert_id, is_new = self._raise_or_touch_alert(camera_id, detection_id, "vehicle", match,
                                                            entry["reason"], confidence, lat, lon)
            alert = {
                "alert_id": alert_id, "camera_id": camera_id, "match_type": "vehicle",
                "match_key": match, "reason": entry["reason"], "confidence": confidence,
                "lat": lat, "lon": lon, "detected_as": plate_text, "is_new": is_new,
            }
            if self.bus and is_new:
                self.bus.publish("alert", alert)
        return detection_id, alert

    def process_face_detection(self, camera_id, face_label, similarity, lat, lon):
        detection_id, _ = self._get_or_record_detection(camera_id, "face", str(face_label), similarity,
                                                          "edge", lat, lon)
        alert = None
        if face_label is not None:
            person = db.find_person_by_label(face_label)
            if person:
                alert_id, is_new = self._raise_or_touch_alert(camera_id, detection_id, "person", person["person_id"],
                                                                person["reason"], similarity, lat, lon)
                alert = {
                    "alert_id": alert_id, "camera_id": camera_id, "match_type": "person",
                    "match_key": person["person_id"], "name": person.get("name"),
                    "reason": person["reason"], "confidence": similarity, "lat": lat, "lon": lon,
                    "is_new": is_new,
                }
                if self.bus and is_new:
                    self.bus.publish("alert", alert)
        return detection_id, alert
