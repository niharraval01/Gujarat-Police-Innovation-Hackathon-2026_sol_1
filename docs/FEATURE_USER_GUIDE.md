# Sentinel Mesh — feature-by-feature user guide

This guide explains what each visible feature does, why it exists, how to use
it, and what an operator should verify before acting.

## 1. Before operating

Choose the correct mode:

- **Public demo:** safe for presentation. All records are synthetic and edits
  stay in the current browser.
- **Local full stack:** required for persistent SQLite data, face-photo
  enrollment, RTSP inference, FastAPI endpoints, and live WebSocket alerts.

Use this operating sequence throughout the dashboard:

1. **Observe** the camera fleet and incoming events.
2. **Validate** confidence, source, timestamps, and available video.
3. **Correlate** against watchlist context, route history, and adjacent cameras.
4. **Respond** under the approved SOP, then record acknowledgement notes.

AI output is decision support. A plate/face match or risk score is not proof of
identity, guilt, or an event by itself.

## 2. State overview

### What it does

Shows camera count, online/degraded/offline health, active alerts, recent AI
detections, and the current explainable threat posture.

### Why use it

It gives a control-room operator a fast operational baseline and makes coverage
gaps visible before an alert is investigated.

### How to use it

1. Check **Camera fleet** against the expected onboarded count.
2. Check **Feeds online** and note degraded/offline totals.
3. Check **Active alerts** before lower-priority work.
4. Read the intelligence narrative and recommended actions.
5. Use **Refresh** if a manual refresh is needed; normal data also refreshes
   automatically.

Do not interpret the 0–99 posture as a probability. It is a priority score
constructed from reason severity, confidence, recency, repeated sightings,
anomalies, and camera gaps.

## 3. Statewide camera map

### What it does

Plots cameras on the free OpenStreetMap layer. Marker color indicates camera
health or a related alert.

### Why use it

Geography helps operators understand coverage, nearby cameras, district
hotspots, and where verification resources may be required.

### How to use it

1. Select a marker.
2. Review camera ID, name, district, VMS/vendor, connectivity, and state.
3. Select **Open live view** when WHEP or HLS is available.
4. If the button is disabled, live browser preview is unavailable for that
   camera; RTSP inference can still be running at the edge.

The map requires access to OpenStreetMap tiles but no map API key.

## 4. Vehicle route reconstruction

### What it does

Retrieves ordered plate detections from multiple cameras and draws the route on
the map.

### Why use it

It helps reconstruct movement without continuously transporting central raw
video. It can also expose impossible-travel patterns, duplicate/cloned plates,
or incorrect timestamps.

### How to use it

1. Enter a plate such as `GJ06AB1234` in **AI route reconstruction**.
2. Select **Trace**.
3. Review the ordered map points and timestamps.
4. Compare surprising jumps with camera clocks and source video.
5. Treat a route as metadata correlation until visually validated.

No route appears until that normalized plate has stored detection records.

## 5. Vehicle watchlist

### What it does

Stores normalized vehicle registration numbers with a reason, source system,
and case notes.

### Why use it

The correlation engine needs an authorized target registry to decide which OCR
detections deserve an alert.

### How to add a vehicle

1. Select **Watchlist** in the header.
2. Open **Vehicles**.
3. Enter the registration number.
4. Select `stolen`, `wanted`, `blacklisted`, or `suspect`.
5. Add a case/FIR/source reference in notes.
6. Select **Save vehicle**.

### How to remove a vehicle

1. Find the current entry.
2. Select **Remove**.
3. Confirm the prompt.

Removal stops future watchlist matches; it does not erase historical detection
or alert evidence.

## 6. Person watchlist and face enrollment

### What it does

Stores person metadata in SQLite and reference images on disk. At live-pipeline
startup, the images train the CPU-only LBPH recognizer under a stable numeric
label mapped to the Person ID.

### Why use it

Recognition requires authorized reference samples. Keeping images out of
SQLite simplifies image lifecycle and keeps the database focused on metadata.

### How to add a person

1. Select **Watchlist → Persons**.
2. Enter a stable Person ID and full name.
3. Select `wanted`, `missing`, or `suspect`.
4. Add case context and source details.
5. Select 1–8 clear JPEG/PNG face photos, at most 8 MB each.
6. Select **Save & stage enrollment**.
7. Restart `demo/run_live.py`.
8. Confirm its console reports the person/photo enrollment and no unexpected
   skipped items.

### How to remove a person

1. Select **Remove** on the person record.
2. Confirm deletion of its stored references.
3. Restart `demo/run_live.py` so its in-memory recognizer is rebuilt.

Use only authorized images. A match must be manually verified, especially
under poor lighting, pose changes, occlusion, or low-resolution CCTV.

## 7. Priority alert queue

### What it does

Receives watchlist alerts over `/ws/alerts` and groups them into **New**,
**Acknowledged**, and **All** views.

### Why use it

Triage prevents alerts from accumulating without ownership and creates a small
operator audit trail.

### How to use it

1. Open **New** and start with the highest operational priority.
2. Review target, reason, location, age, and confidence.
3. Select the locate button to focus the source camera.
4. Validate against available video and source-system context.
5. Enter a concise operator note—what was checked and the outcome.
6. Select **Acknowledge** only after review.
7. Use **Acknowledged** to review completed items.
8. Select **Reopen** when new evidence requires renewed attention.

Acknowledgement changes workflow state; it does not delete the alert.

## 8. Sound and desktop notifications

### What it does

Plays a short Web Audio beep and displays a native notification for a new
WebSocket alert when browser permission is granted.

### Why use it

It helps an operator notice urgent events while working elsewhere in the
command-centre interface.

### How to use it

1. Select **Enable alerts** in the header.
2. Allow notifications when prompted.
3. Keep the browser open.
4. Use the notification to return to the alert queue.

Permission is requested only after the button is selected. Browsers generally
require `localhost` or HTTPS for notification features.

## 9. Intelligence brief and district hotspots

### What it does

Ranks alert priority, aggregates district risk, and exposes movement/camera
health anomalies with supporting detail.

### Why use it

It compresses a larger event list into a review order while keeping the reason
for each recommendation visible.

### How to use it

1. Read the operational narrative.
2. Review each recommended action.
3. Inspect anomaly title, detail, and confidence.
4. Compare the top hotspot districts with raw alerts.
5. Validate anomalies before escalation; clock error or OCR confusion can look
   like impossible travel.

The engine is deterministic and local. It does not call a cloud LLM.

## 10. Sentinel Copilot

### What it does

Recognizes common operational intents and answers from current camera,
detection, alert, and route metadata.

### Why use it

It reduces navigation time while retaining an evidence-backed, predictable
answer path suitable for an offline prototype.

### How to use it

Select a prompt chip or ask questions such as:

- `Which districts are highest risk?`
- `Show stolen vehicle alerts`
- `How is camera health?`
- `Trace GJ06AB1234`

Use `Ctrl+K`/`Cmd+K` to focus the Copilot quickly. Verify the returned result
against the map and alert queue before taking action.

Current Copilot is deterministic local NLP, not a generative LLM. See
`docs/LLM_AND_RUNTIME_SETUP.md` for the optional free local LLM preparation and
the safe integration boundary.

## 11. Camera fleet health

### What it does

Lists camera ID/name, district, VMS/vendor, transport, and online state.

### Why use it

An offline camera is an evidence gap. Vendor/transport details help direct an
issue to the correct support path.

### How to use it

1. Open **Camera fleet** from the sidebar.
2. Select a row to focus that camera on the map.
3. Investigate degraded/offline states.
4. Confirm the camera catalogue and stream URL before blaming AI inference.

## 12. Live view

### What it does

Opens an on-demand browser stream using WHEP/WebRTC when available, with HLS as
the compatible fallback.

### Why use it

Raw video is pulled only for human verification, reducing continuous central
bandwidth use.

### How to use it

1. Select a map marker with preview support.
2. Select **Open live view**.
3. Wait for WHEP or HLS connection status.
4. Verify the event.
5. Close the modal promptly to release the stream.

The public GitHub Pages demo intentionally provides no real camera URLs.

## 13. API console

### What it does

The local sidebar opens FastAPI's generated API documentation at `/docs`.

### Why use it

It allows developers/evaluators to inspect schemas and exercise endpoints
without a separate API client.

### How to use it

1. Start FastAPI locally.
2. Open **API console**.
3. Expand an endpoint and select **Try it out**.
4. Supply representative, non-sensitive input.
5. Review status and response body.

On GitHub Pages the same link opens the API source because no Python server can
run on static hosting.

## 14. Real-time end-to-end flow

1. `demo/run_live.py` reads authorized camera definitions from `/api/ingest`.
2. `LiveRTSPSource` opens paced RTSP/TCP feeds and yields PTS-timed frames.
3. OpenCV detects plates and faces; OCR/LBPH produce labels and confidence.
4. `correlation/engine.py` matches watchlists and applies per-camera
   deduplication/cooldown.
5. Detections and alerts are stored in SQLite.
6. `bus.py` publishes a new alert to FastAPI's WebSocket subscribers.
7. The React dashboard refreshes counts, map state, intelligence, and triage.
8. The operator validates evidence, records a note, and acknowledges the alert.

## 15. Public-demo behavior

The GitHub Pages site supports safe demonstrations of:

- dashboard navigation and map presentation;
- representative camera/alert data;
- vehicle and person watchlist UI;
- alert acknowledge/reopen workflow;
- route reconstruction;
- deterministic Copilot queries.

Changes use browser local storage and are not shared with other users. Photo
selections are represented only as demo records and are never uploaded. Use the
local full stack for actual persistence and inference.

## 16. Operator close-out checklist

- No high-priority New alerts were left unreviewed.
- Acknowledgement notes contain a clear validation outcome.
- Reopened alerts have an owner/follow-up.
- Offline/degraded camera gaps were reported.
- On-demand streams were closed after verification.
- Uploaded references remain authorized and current.
- No AI result was treated as an enforcement decision without human review.
