"""Explainable AI-assisted operational intelligence.

This module keeps working without cloud credentials. It combines transparent
threat scoring, spatio-temporal anomaly detection, and a small intent engine
over the live registry. Every result includes evidence or scoring factors so
an operator can audit it, and no police data leaves the deployment boundary.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict

import db


REASON_WEIGHTS = {
    "wanted": 36,
    "stolen": 31,
    "missing": 29,
    "suspect": 24,
    "blacklisted": 17,
}
PLATE_PATTERN = re.compile(r"\b[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{1,4}\b", re.I)


def _clamp(value, low=0, high=99):
    return max(low, min(high, value))


def severity_for(score):
    if score >= 82:
        return "critical"
    if score >= 68:
        return "high"
    if score >= 48:
        return "medium"
    return "low"


def score_alert(alert, repeat_count=1, now=None):
    """Score one alert with human-readable factors (0-99)."""
    now = now or time.time()
    reason = str(alert.get("reason") or "").lower()
    confidence = float(alert.get("confidence") or 0)
    if confidence > 1:
        confidence /= 100
    age_hours = max(0, (now - float(alert.get("ts") or now)) / 3600)
    recency = max(0, round(12 - min(age_hours, 24) * 0.5))
    reason_points = REASON_WEIGHTS.get(reason, 20)
    confidence_points = round(_clamp(confidence, 0, 1) * 24)
    repeat_points = min(max(repeat_count - 1, 0) * 4, 12)
    score = int(_clamp(15 + reason_points + confidence_points + recency + repeat_points))
    return {
        "score": score,
        "severity": severity_for(score),
        "factors": [
            {"label": f"{reason or 'unclassified'} watchlist", "points": reason_points},
            {"label": f"{confidence:.0%} model confidence", "points": confidence_points},
            {"label": "recent sighting", "points": recency},
            {"label": f"{repeat_count} correlated sighting(s)", "points": repeat_points},
        ],
    }


def _haversine_km(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _movement_anomalies(alerts):
    by_target = defaultdict(list)
    for alert in alerts:
        if alert.get("match_type") == "vehicle" and alert.get("lat") is not None and alert.get("lon") is not None:
            by_target[alert.get("match_key")].append(alert)

    anomalies = []
    for target, sightings in by_target.items():
        sightings.sort(key=lambda item: item.get("ts") or 0)
        peak_speed, pair = 0, None
        for first, second in zip(sightings, sightings[1:]):
            elapsed = float(second.get("ts") or 0) - float(first.get("ts") or 0)
            if elapsed <= 0:
                continue
            distance = _haversine_km((first["lat"], first["lon"]), (second["lat"], second["lon"]))
            speed = distance / (elapsed / 3600)
            if speed > peak_speed:
                peak_speed, pair = speed, (first, second, distance, elapsed)
        if pair and peak_speed > 180:
            first, second, distance, elapsed = pair
            anomalies.append({
                "type": "spatio_temporal",
                "severity": "critical" if peak_speed > 400 else "high",
                "title": f"Impossible travel pattern · {target}",
                "detail": (
                    f"Sightings moved {distance:.0f} km from {first.get('district') or first['camera_id']} "
                    f"to {second.get('district') or second['camera_id']} in {elapsed:.0f}s. "
                    "Validate clocks, plate identity, or cloned-plate activity."
                ),
                "confidence": 0.96,
                "target": target,
            })
    return anomalies


def _hotspots(alerts, scored_by_id):
    grouped = defaultdict(list)
    for alert in alerts:
        grouped[alert.get("district") or "Unknown"].append(alert)
    rows = []
    for district, items in grouped.items():
        scores = [scored_by_id[item["alert_id"]]["score"] for item in items]
        rows.append({
            "district": district,
            "alerts": len(items),
            "critical": sum(1 for score in scores if score >= 82),
            "risk_score": min(99, round(sum(scores) / len(scores) + min(len(items) - 1, 4) * 3)),
            "targets": len({item.get("match_key") for item in items}),
        })
    return sorted(rows, key=lambda row: (row["risk_score"], row["alerts"]), reverse=True)


def build_overview(now=None):
    now = now or time.time()
    cameras = db.list_cameras()
    alerts = db.list_alerts(limit=500)
    recent_detections = db.list_recent_detections(limit=500, since=now - 24 * 3600)
    target_counts = Counter(alert.get("match_key") for alert in alerts)

    scored_by_id, priority_alerts = {}, []
    for alert in alerts:
        assessment = score_alert(alert, target_counts[alert.get("match_key")], now)
        scored_by_id[alert["alert_id"]] = assessment
        priority_alerts.append({**alert, **assessment})
    priority_alerts.sort(key=lambda item: (item["score"], item.get("ts") or 0), reverse=True)

    anomalies = _movement_anomalies(alerts)
    for cam in cameras:
        if cam.get("status") in {"offline", "degraded"}:
            anomalies.append({
                "type": "camera_health",
                "severity": "high" if cam.get("status") == "offline" else "medium",
                "title": f"Camera {cam.get('status')} · {cam['camera_id']}",
                "detail": f"{cam['name']} in {cam.get('district') or 'unknown district'} needs operator review.",
                "confidence": 1.0,
                "camera_id": cam["camera_id"],
            })

    hotspots = _hotspots(alerts, scored_by_id)
    critical = sum(1 for item in priority_alerts if item["severity"] == "critical")
    unack = sum(1 for item in alerts if not item.get("acknowledged"))
    offline = sum(1 for cam in cameras if cam.get("status") == "offline")
    risk = min(99, 18 + critical * 14 + min(unack, 8) * 4 + min(len(anomalies), 4) * 6 + offline * 3)
    posture = severity_for(risk)

    lead = priority_alerts[0] if priority_alerts else None
    if lead:
        narrative = (
            f"{unack} unacknowledged alerts require review. Highest priority is {lead['match_key']} "
            f"at {lead.get('district') or lead['camera_id']} with risk {lead['score']}/99."
        )
    else:
        narrative = "No active watchlist alerts. Continue camera-health and ingestion monitoring."
    if anomalies:
        narrative += f" The local anomaly engine flagged {len(anomalies)} pattern(s) for validation."

    recommendations = []
    if lead:
        recommendations.append(f"Dispatch verification for {lead['match_key']} and preserve the related camera segment.")
    if anomalies:
        recommendations.append("Validate camera clocks and compare adjacent sightings before escalation.")
    if offline:
        recommendations.append(f"Restore {offline} offline camera(s) to close current coverage gaps.")
    if not recommendations:
        recommendations.append("Maintain monitoring; no immediate intervention is recommended.")

    return {
        "generated_at": now,
        "engine": "sentinel-local-intelligence-v1",
        "data_boundary": "on-premise · no external AI API",
        "risk_score": risk,
        "posture": posture,
        "narrative": narrative,
        "metrics": {
            "unacknowledged": unack,
            "critical": critical,
            "anomalies": len(anomalies),
            "detections_24h": len(recent_detections),
        },
        "priority_alerts": priority_alerts[:10],
        "hotspots": hotspots[:8],
        "anomalies": anomalies[:10],
        "recommendations": recommendations,
    }


def answer_query(question):
    """Answer common command-centre questions using deterministic local NLP."""
    question = (question or "").strip()
    lower = question.lower()
    overview = build_overview()
    alerts = db.list_alerts(limit=250)
    cameras = db.list_cameras()
    evidence = []

    plate_match = PLATE_PATTERN.search(question.upper())
    if plate_match:
        plate = re.sub(r"[^A-Z0-9]", "", plate_match.group(0).upper())
        route = db.vehicle_route(plate)
        intent = "vehicle_route"
        if route:
            districts = [hop.get("district") or hop["camera_id"] for hop in route]
            answer = f"{plate} has {len(route)} correlated sighting(s) across {' → '.join(districts)}."
            evidence = route[-8:]
        else:
            answer = f"No correlated route is currently stored for {plate}."
    elif any(word in lower for word in ("offline", "degraded", "camera health", "coverage")):
        intent = "camera_health"
        affected = [cam for cam in cameras if cam.get("status") != "online"]
        online = sum(1 for cam in cameras if cam.get("status") == "online")
        answer = f"{online} of {len(cameras)} cameras are online; {len(affected)} need attention."
        evidence = affected[:10]
    elif any(word in lower for word in ("hotspot", "district", "where", "risk area")):
        intent = "hotspots"
        top = overview["hotspots"][:3]
        if top:
            answer = "Highest current risk: " + ", ".join(
                f"{row['district']} ({row['risk_score']}/99, {row['alerts']} alerts)" for row in top
            ) + "."
            evidence = top
        else:
            answer = "No district hotspot is present in the current alert window."
    elif any(word in lower for word in ("alert", "wanted", "stolen", "suspect", "missing", "vehicle", "person")):
        intent = "alert_search"
        filters = [word for word in ("wanted", "stolen", "suspect", "missing", "blacklisted") if word in lower]
        match_type = "person" if "person" in lower else "vehicle" if "vehicle" in lower else None
        matches = [a for a in alerts if (not filters or str(a.get("reason")).lower() in filters)
                   and (not match_type or a.get("match_type") == match_type)]
        answer = f"I found {len(matches)} matching alert(s)."
        if matches:
            answer += " Latest: " + "; ".join(
                f"{a['match_key']} · {a.get('reason')} · {a.get('district') or a['camera_id']}" for a in matches[:3]
            ) + "."
        evidence = matches[:10]
    else:
        intent = "operational_summary"
        answer = overview["narrative"] + " " + overview["recommendations"][0]
        evidence = overview["priority_alerts"][:3]

    return {
        "question": question,
        "intent": intent,
        "answer": answer,
        "evidence": evidence,
        "generated_at": time.time(),
        "engine": "sentinel-local-nlp-v1",
        "suggestions": [
            "Which districts are highest risk?",
            "Show stolen vehicle alerts",
            "How is camera health?",
            "Trace GJ06AB1234",
        ],
    }
