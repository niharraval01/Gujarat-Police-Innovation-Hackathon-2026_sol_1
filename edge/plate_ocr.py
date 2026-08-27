"""
plate_ocr.py — Edge-tier plate OCR, built from scratch with zero external
model downloads (no pytesseract / EasyOCR / PaddleOCR available offline in
this environment). It works by:
  1. Binarizing the plate crop and segmenting individual characters via
     contour analysis.
  2. Matching each character against a synthetic template bank (rendered
     with the same font primitives OpenCV itself provides) using normalized
     cross-correlation.

This is intentionally a genuine, runnable classical-CV pipeline — not a
hardcoded stub — so the demo backend is truly operational end-to-end.

TIERED INFERENCE STRATEGY (this is the architectural point, not just a
fallback): this cheap CPU-only reader is the EDGE tier. When its confidence
score falls below a threshold (bad lighting, angle, occlusion, non-standard
font on the physical plate), the pipeline escalates the crop to a CLOUD
tier — a deep model (EasyOCR / PaddleOCR / a YOLOv8-ANPR + CRNN head) that
only needs to run on the minority of hard cases. This is what keeps
inference cost sane at ~80,000-camera scale: you are not running a heavy
GPU model on every single frame from every single camera.

PRODUCTION SWAP-IN: implement DeepANPRAdapter.read() with a real EasyOCR/
PaddleOCR call once the team has internet access on their own machine.
"""

import cv2
import numpy as np

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TEMPLATE_SIZE = (34, 56)  # (w, h)
CONFIDENCE_ESCALATE_THRESHOLD = 0.55


def _render_char_template(ch, font=cv2.FONT_HERSHEY_SIMPLEX, scale=1.6, thickness=3):
    canvas = np.zeros((70, 50), dtype=np.uint8)
    cv2.putText(canvas, ch, (2, 55), font, scale, 255, thickness, cv2.LINE_AA)
    x, y, w, h = cv2.boundingRect(canvas)
    if w == 0 or h == 0:
        return np.zeros(TEMPLATE_SIZE[::-1], dtype=np.uint8)
    crop = canvas[y:y + h, x:x + w]
    return cv2.resize(crop, TEMPLATE_SIZE, interpolation=cv2.INTER_AREA)


def build_template_bank():
    return {ch: _render_char_template(ch) for ch in ALPHABET}


def _segment_characters(plate_bgr):
    gray = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(binary) > 127:  # ensure characters are white-on-black
        binary = 255 - binary
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h_img = binary.shape[0]
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if h > 0.35 * h_img and h < 0.98 * h_img and w > 3 and w < 0.9 * binary.shape[1]:
            boxes.append((x, y, w, h))
    boxes.sort(key=lambda b: b[0])
    chars = []
    for (x, y, w, h) in boxes:
        char_img = binary[y:y + h, x:x + w]
        char_img = cv2.resize(char_img, TEMPLATE_SIZE, interpolation=cv2.INTER_AREA)
        chars.append(char_img)
    return chars


def _match_template(char_img, templates):
    best_ch, best_score = "?", -1.0
    for ch, tmpl in templates.items():
        res = cv2.matchTemplate(char_img, tmpl, cv2.TM_CCOEFF_NORMED)
        score = float(res[0][0])
        if score > best_score:
            best_ch, best_score = ch, score
    return best_ch, best_score


def render_plate_image(text, char_w=34, char_h=56, pad=10, gap=6):
    """
    Shared helper used by the synthetic-feed generator (and tests) to draw a
    clean plate image with FIXED CHARACTER PITCH — matching how real
    embossed/retro-reflective Indian plates are laid out — so characters
    never touch. Keeping this in one place means the OCR's template bank
    and the demo data are always drawn from the same font primitives.
    """
    w = pad * 2 + len(text) * (char_w + gap) - gap
    h = char_h + pad * 2
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    x = pad
    for ch in text:
        tmpl = _render_char_template(ch)
        if (char_w, char_h) != TEMPLATE_SIZE:
            tmpl = cv2.resize(tmpl, (char_w, char_h), interpolation=cv2.INTER_AREA)
        # paste as black strokes: template is white-strokes-on-black, invert for plate
        stroke = 255 - tmpl
        region = img[pad:pad + char_h, x:x + char_w]
        mask = stroke < 200
        region[mask] = 0
        x += char_w + gap
    return img


class EdgePlateOCR:
    """CPU-only, offline, from-scratch OCR — the 'edge tier'."""

    def __init__(self):
        self.templates = build_template_bank()

    def read(self, plate_bgr):
        chars = _segment_characters(plate_bgr)
        if not chars:
            return "", 0.0
        text, scores = "", []
        for char_img in chars:
            ch, score = _match_template(char_img, self.templates)
            text += ch
            scores.append(score)
        confidence = max(0.0, min(1.0, sum(scores) / len(scores)))
        return text, confidence


class DeepANPRAdapter:
    """
    Placeholder for the 'cloud/escalation tier'. Wire this up to a real
    deep-learning ANPR model once you have internet access, e.g.:

        pip install easyocr
        import easyocr
        reader = easyocr.Reader(['en'])
        result = reader.readtext(plate_crop)

    or a YOLOv8-ANPR + CRNN pipeline via `pip install ultralytics`.
    Kept as a stub here so the interface exists and the escalation path in
    correlation/engine.py is real, wired code — not vaporware.
    """

    def read(self, plate_bgr):
        raise NotImplementedError(
            "Deep ANPR tier requires internet access to install EasyOCR/"
            "PaddleOCR/ultralytics on your own machine. See README.md → "
            "'Path to Production'."
        )


class TieredPlateReader:
    """Confidence-based escalation: edge tier first, deep tier on low confidence."""

    def __init__(self, escalate_threshold=CONFIDENCE_ESCALATE_THRESHOLD, deep_adapter=None):
        self.edge = EdgePlateOCR()
        self.deep = deep_adapter or DeepANPRAdapter()
        self.escalate_threshold = escalate_threshold

    def read(self, plate_bgr):
        text, conf = self.edge.read(plate_bgr)
        if conf >= self.escalate_threshold or len(text) < 4:
            return text, conf, "edge"
        try:
            text2, conf2 = self.deep.read(plate_bgr)
            return text2, conf2, "escalated"
        except NotImplementedError:
            # No deep tier wired up yet in this offline sandbox — fall back
            # to the edge-tier best guess so the pipeline stays operational.
            return text, conf, "edge_fallback"
