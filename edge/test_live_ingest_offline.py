"""
edge/test_live_ingest_offline.py — exercises LiveRTSPSource's control flow
(reconnect/backoff, discontinuity detection, warm-up tolerance) against a
mock capture object, since there is no live RTSP server reachable from this
build environment. Run: python3 edge/test_live_ingest_offline.py
"""
import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from edge.live_ingest import LiveRTSPSource, FrameRecord


class MockCapture:
    """
    Scripted fake of cv2.VideoCapture. `script` is a list of steps, each
    either ("fail",) for a bad read() or ("ok", pts_ms) for a good one.
    """
    def __init__(self, script, opens_ok=True):
        self.script = list(script)
        self._opens_ok = opens_ok
        self._i = 0

    def isOpened(self):
        return self._opens_ok

    def read(self):
        if self._i >= len(self.script):
            return False, None
        step = self.script[self._i]
        self._i += 1
        if step[0] == "fail":
            return False, None
        return True, f"frame@{step[1]}"

    def get(self, prop):
        # returns the pts of the *last* successful read
        for step in reversed(self.script[:self._i]):
            if step[0] == "ok":
                return step[1]
        return 0.0

    def release(self):
        pass


def test_warmup_noise_is_not_fatal():
    """A few decode failures right after connecting (join-time decoder
    warnings) must NOT trigger a reconnect — only steady-state failures
    past the limit should."""
    script = [("fail",)] * 5 + [("ok", 100.0), ("ok", 133.0), ("ok", 166.0)]
    factory_calls = []

    def factory(url):
        factory_calls.append(url)
        return MockCapture(script)

    src = LiveRTSPSource("cam-1", "rtsp://fake/1", capture_factory=factory)
    frames = []
    stop_after = {"n": 0}

    def on_frame(rec):
        frames.append(rec)
        stop_after["n"] += 1

    src.run(on_frame, should_stop=lambda: stop_after["n"] >= 3, sleep_fn=lambda s: None)
    assert len(factory_calls) == 1, f"should not have reconnected during warm-up noise, got {len(factory_calls)} opens"
    assert [f.pts_ms for f in frames] == [100.0, 133.0, 166.0]
    print("PASS: warm-up decode noise tolerated without reconnect")


def test_steady_state_disconnect_triggers_reconnect_with_backoff():
    """After a good frame, a long run of failures should be treated as a
    real disconnect, and the source should reconnect with backoff."""
    script_1 = [("ok", 0.0), ("ok", 33.0)] + [("fail",)] * 40  # disconnect after 2 good frames
    script_2 = [("ok", 0.0), ("ok", 33.0), ("ok", 66.0)]
    captures = [MockCapture(script_1), MockCapture(script_2)]
    opens = {"n": 0}

    def factory(url):
        cap = captures[min(opens["n"], len(captures) - 1)]
        opens["n"] += 1
        return cap

    sleeps = []
    src = LiveRTSPSource("cam-2", "rtsp://fake/2", capture_factory=factory)
    frames = []

    def on_frame(rec):
        frames.append(rec)

    src.run(on_frame, should_stop=lambda: len(frames) >= 5, sleep_fn=lambda s: sleeps.append(s))
    assert opens["n"] == 2, f"expected exactly one reconnect (2 opens total), got {opens['n']}"
    assert len(sleeps) == 1 and sleeps[0] == 2.0, f"expected a single base-delay backoff sleep, got {sleeps}"
    assert [f.pts_ms for f in frames] == [0.0, 33.0, 0.0, 33.0, 66.0]
    print("PASS: steady-state disconnect triggers exactly one reconnect with correct backoff")


def test_discontinuity_detected_on_loop_restart():
    """When PTS jumps backward (the feed looped), discontinuity must be
    flagged so the caller can reset long-lived per-camera state."""
    script = [("ok", 9000.0), ("ok", 9033.0), ("ok", 40.0), ("ok", 73.0)]
    src = LiveRTSPSource("cam-3", "rtsp://fake/3", capture_factory=lambda url: MockCapture(script))
    src.open()
    recs = [src.read() for _ in range(4)]
    flags = [r.discontinuity for r in recs]
    assert flags == [False, False, True, False], flags
    print("PASS: loop-point discontinuity correctly flagged exactly once")


def test_large_forward_gap_flagged_but_normal_jitter_is_not():
    script = [("ok", 0.0), ("ok", 200.0), ("ok", 20200.0)]  # 200ms normal-ish gap, then a 20s stall
    src = LiveRTSPSource("cam-4", "rtsp://fake/4", capture_factory=lambda url: MockCapture(script))
    src.open()
    recs = [src.read() for _ in range(3)]
    assert recs[1].discontinuity is False, "a 200ms gap is ordinary jitter, not a discontinuity"
    assert recs[2].discontinuity is True, "a 20s forward gap should be flagged"
    print("PASS: forward-gap threshold distinguishes jitter from a real discontinuity")


if __name__ == "__main__":
    test_warmup_noise_is_not_fatal()
    test_steady_state_disconnect_triggers_reconnect_with_backoff()
    test_discontinuity_detected_on_loop_restart()
    test_large_forward_gap_flagged_but_normal_jitter_is_not()
    print("\nAll live_ingest offline tests passed.")
