"""
edge/live_ingest.py — connects to the real Sentinel sandbox camera grid
(the live evaluation feeds, per the Resources-tab integration reference),
instead of the synthetic frames used in demo/run_pipeline.py.

This module deliberately follows every DO/DON'T in that reference:

  DO  force RTSP over TCP                         -> _force_tcp_transport()
  DO  drive timing from PTS, never arrival time    -> LiveRTSPSource.read()
  DON'T trust reported frame rate                  -> we never read CAP_PROP_FPS
  DON'T assume constant frame rate                 -> caller uses PTS deltas, not a fixed tick
  DO  reconnect with exponential backoff           -> ExponentialBackoff
  DON'T treat join-time decoder warnings as fatal   -> WARMUP_GRACE_FAILURES
  DON'T assume a uniform grid                       -> catalogue drives per-camera config
  DO  expect a scene discontinuity at the loop point -> discontinuity flag on read()
  DON'T plan around downloading footage             -> this module only opens live RTSP,
                                                         never touches the /stream/<id> HTTP path
  DON'T publish to the gateway                       -> read-only client, no control calls
  DO  pace load                                      -> caller decides how many sources to open

NOTE ON CATALOGUE SCHEMA: the reference doc describes what /api/ingest
returns in prose ("id, location, codec, live status, stream properties,
and all three URLs") but not exact JSON key names. `_normalize_entry()`
below is deliberately defensive about key-name variants. The moment you
have real access, run `fetch_catalogue()` once, print the raw JSON, and
tighten `_normalize_entry()` to match exactly — don't trust this guess
under evaluation-day time pressure.
"""

import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2

WARMUP_GRACE_FAILURES = 60     # ~2-4s of decoder warm-up noise at typical fps, tolerated as non-fatal
STEADY_STATE_FAILURE_LIMIT = 30  # consecutive failures AFTER a good frame => treat as real disconnect
BACKOFF_START = 2.0
BACKOFF_CAP = 30.0


def _force_tcp_transport():
    # Must be set before cv2.VideoCapture(...) opens the stream — FFmpeg
    # reads this from the environment at open time. UDP is accepted by the
    # gateway but fails across NAT/most corporate firewalls and produces
    # corrupt frames that look like model bugs, per the integration guide.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


# ---------------------------------------------------------------------------
# Catalogue (/api/ingest) — always the source of truth for URLs and camera
# properties. Never hard-code stream URLs; ids and the camera set can change.
# ---------------------------------------------------------------------------

def fetch_catalogue(base_url, timeout=6):
    """GET {base_url}/api/ingest -> list[dict] of normalized camera entries.

    Uses stdlib urllib only (no extra dependency). Raises on network/parse
    failure — the caller decides whether to retry or abort.
    """
    url = base_url.rstrip("/") + "/api/ingest"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    entries = raw if isinstance(raw, list) else raw.get("cameras", raw.get("data", []))
    return [_normalize_entry(e) for e in entries]


def _normalize_entry(e):
    """Defensive key-name mapping — see module docstring note above."""
    cam_id = str(e.get("id") or e.get("camera_id") or e.get("stream_id"))
    rtsp = e.get("rtsp") or e.get("rtsp_url") or (e.get("urls") or {}).get("rtsp")
    whep = e.get("whep") or e.get("webrtc") or (e.get("urls") or {}).get("whep")
    hls = e.get("hls") or e.get("hls_url") or (e.get("urls") or {}).get("hls")
    location = e.get("location") or e.get("name") or e.get("site")
    lat = lon = None
    if isinstance(location, dict):
        lat, lon = location.get("lat"), location.get("lon") or location.get("lng")
        location_label = location.get("label") or location.get("name") or cam_id
    else:
        location_label = location or cam_id
    return {
        "camera_id": cam_id,
        "location_label": location_label,
        "lat": lat,
        "lon": lon,
        "codec": e.get("codec"),
        "live": e.get("live", e.get("status") == "live" if e.get("status") else True),
        "rtsp_url": rtsp,
        "whep_url": whep,
        "hls_url": hls,
        "raw": e,  # keep the original entry too, in case normalization missed a field you need
    }


# ---------------------------------------------------------------------------
# Reconnection policy
# ---------------------------------------------------------------------------

@dataclass
class ExponentialBackoff:
    start: float = BACKOFF_START
    cap: float = BACKOFF_CAP
    _delay: float = field(default=None, repr=False)

    def __post_init__(self):
        self._delay = self.start

    def next(self):
        d = self._delay
        self._delay = min(self._delay * 2, self.cap)
        return d

    def reset(self):
        self._delay = self.start


# ---------------------------------------------------------------------------
# Live source
# ---------------------------------------------------------------------------

@dataclass
class FrameRecord:
    ok: bool
    frame: object = None
    pts_ms: float = None
    discontinuity: bool = False
    reason: str = ""


class LiveRTSPSource:
    """
    One camera's live connection. Call open()/read()/close() directly for
    unit testing (inject `capture_factory` to avoid touching real network),
    or use run() for the batteries-included reconnect loop.
    """

    def __init__(self, camera_id, rtsp_url, capture_factory=None):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self._capture_factory = capture_factory or (lambda url: cv2.VideoCapture(url, cv2.CAP_FFMPEG))
        self._cap = None
        self._last_pts = None
        self._got_first_good_frame = False

    def open(self):
        _force_tcp_transport()
        self._cap = self._capture_factory(self.rtsp_url)
        self._last_pts = None
        self._got_first_good_frame = False
        return bool(self._cap and self._cap.isOpened())

    def read(self):
        """One frame. Never treats a single failed read as fatal — the
        caller (run()) applies the warm-up-vs-steady-state failure policy."""
        if self._cap is None:
            return FrameRecord(ok=False, reason="not_opened")
        ok, frame = self._cap.read()
        if not ok:
            return FrameRecord(ok=False, reason="decode_or_join_warning")

        # DO drive timing from PTS, never wall-clock arrival time.
        pts_ms = self._cap.get(cv2.CAP_PROP_POS_MSEC)
        discontinuity = False
        if self._last_pts is not None:
            delta = pts_ms - self._last_pts
            # Loop point (scene cut back to the start) or any large backward
            # jump. A generous forward-gap allowance covers real variable
            # frame intervals (DON'T assume constant frame rate) without
            # miscalling ordinary jitter a discontinuity.
            if delta < -50 or delta > 15000:
                discontinuity = True
        self._last_pts = pts_ms
        self._got_first_good_frame = True
        return FrameRecord(ok=True, frame=frame, pts_ms=pts_ms, discontinuity=discontinuity)

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def run(self, on_frame: Callable[[FrameRecord], None], should_stop: Optional[Callable[[], bool]] = None,
             sleep_fn=time.sleep, max_reconnects: Optional[int] = None):
        """
        Batteries-included loop: open, read until real disconnect, reconnect
        with exponential backoff, repeat. `should_stop()` lets the caller
        end the loop cleanly (pacing — close cameras you're done with) —
        that is a deliberate stop, not a disconnect, so it must never incur
        a backoff sleep.
        """
        backoff = ExponentialBackoff()
        reconnects = 0

        def stopped():
            return should_stop is not None and should_stop()

        while True:
            if stopped():
                return
            if not self.open():
                reconnects += 1
                if max_reconnects and reconnects > max_reconnects:
                    return
                sleep_fn(backoff.next())
                continue
            backoff.reset()  # successful open resets the policy

            consecutive_failures = 0
            disconnected = False
            while True:
                if stopped():
                    self.close()
                    return
                rec = self.read()
                if rec.ok:
                    consecutive_failures = 0
                    on_frame(rec)
                    continue

                consecutive_failures += 1
                limit = STEADY_STATE_FAILURE_LIMIT if self._got_first_good_frame else WARMUP_GRACE_FAILURES
                if consecutive_failures > limit:
                    disconnected = True
                    break
                # else: normal join-time decoder noise (e.g. "Error
                # constructing the frame RPS" until the first IDR frame) —
                # not fatal, keep reading.

            self.close()
            if not disconnected:
                return
            reconnects += 1
            if max_reconnects and reconnects > max_reconnects:
                return
            sleep_fn(backoff.next())
