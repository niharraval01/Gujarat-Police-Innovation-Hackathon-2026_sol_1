# Sentinel Mesh — High-Level Design
### Gujarat CCTV Hackathon 2026 · Submission Model: **Hybrid** (Model 1 foundation + Model 2 viewing/analytics + Model 3 federation patterns)

## 1. Why hybrid, and why this specific hybrid

The brief itself says Model 1 (registry + GIS) is mandatory and must be
combined with at least one other model. Given the two hardest constraints
in the problem statement —

- **Geographical dispersion**: camera sites up to ~1,000km apart
- **Scale**: ~80,000 cameras statewide, heterogeneous vendors/VMS/formats

— the single biggest risk to any submission is an architecture that only
works at hackathon scale (50 demo cameras) and collapses at 80,000. A
fully centralised VMS (Model 4) ingesting raw video from 80,000 sites
needs backbone bandwidth and central GPU capacity that most state
networks cannot realistically fund or provision within a normal rollout
timeline.

**Our answer: don't centralise video — centralise *decisions*.**

Run AI inference (ANPR, face match, event detection) at or near the
camera, and ship only lightweight metadata to the centre. Pull raw video
centrally only when an operator needs to *see* something a metadata alert
already flagged. This is Model 2's "unified viewing without disturbing
existing infrastructure" combined with Model 1's registry, plus a
federation/event-bus layer (Model 3 pattern) so vendor heterogeneity is
absorbed by adapters instead of a rip-and-replace.

## 2. System architecture

```
 ┌────────────────────────────────────────────────────────────────────┐
 │                         DEPARTMENT CAMERA SITES                     │
 │  Home │ Food & Civil Supplies │ RTO │ Municipal │ (private, opt-in) │
 │  Hikvision / Dahua / CP Plus / Honeywell / Bosch — mixed VMS, IP+   │
 │  analog, 7–30 day local retention (unchanged)                       │
 └───────────────────────────────┬──────────────────────────────────┬─┘
                                  │ RTSP / ONVIF / vendor SDK          │
                                  ▼                                    │ on-demand pull
                    ┌─────────────────────────┐                       │ (live view only,
                    │   EDGE INFERENCE NODE     │                       │  see §5)
                    │  (per site / regional hub)│                       │
                    │  ── Plate detector        │                       │
                    │  ── Tiered OCR (edge→deep)│                       │
                    │  ── Face detect + match   │                       │
                    │  ── Health heartbeat       │                       │
                    └───────────┬───────────────┘                       │
                                 │ metadata only (plate text, confidence,│
                                 │ thumbnail, ts, gps) — few KB/event    │
                                 ▼                                       │
                    ┌─────────────────────────┐                       │
                    │   EVENT / METADATA BUS    │                       │
                    │   (Kafka / MQTT)           │                       │
                    └───────────┬───────────────┘                       │
                                 ▼                                       │
     ┌───────────────────────────────────────────────┐                 │
     │           CENTRAL CORRELATION & ALERT ENGINE    │                 │
     │  Fuzzy-matches every event against watchlists    │                 │
     │  (stolen vehicles, wanted/missing persons)        │                 │
     │  sourced from VAHAN / SARTHI / eGujCop / AFIS /    │                 │
     │  NAFIS. Raises alerts, geo-tags them.              │                 │
     └───────────────┬─────────────────────┬─────────────┘                 │
                      ▼                     ▼                              │
     ┌───────────────────────┐   ┌───────────────────────────┐            │
     │  REGISTRY + GIS STORE  │   │  UNIFIED COMMAND CONSOLE    │◄───────────┘
     │  (PostgreSQL+PostGIS)  │   │  Live map, alert feed,       │  Federation adapters
     │  Model 1 foundation    │   │  vehicle route reconstruction,│  (Model 3 pattern) proxy
     └───────────────────────┘   │  on-demand video pull        │  RTSP/ONVIF/SDK calls to
                                  └───────────────────────────┘  each vendor's native VMS
```

## 3. Component detail

### 3.1 Registry & GIS (Model 1 — mandatory foundation)
Every camera onboarded — department, vendor, VMS, connectivity type,
retention policy, lat/lon, health status — lives in one table, regardless
of who owns the physical hardware. This is what makes gap analysis
("which junctions in Dahod have no coverage?") and future onboarding
possible without a redesign. **Prototype**: `db.py` + `seed_data.py`,
50 cameras across 25 districts, GIS rendering in the React application under
`frontend/src`.

### 3.2 Edge inference tier
Runs at the camera/NVR/regional-hub level. Two responsibilities only:
detect + read/recognize, emit metadata. Deliberately kept cheap enough to
run on commodity hardware (a Raspberry Pi 5 / Jetson Nano class device
handles this workload) so it scales linearly with camera count without
requiring central GPU capacity per camera.

**Tiered inference** (the specific technical bet of this design):
a cheap CPU-only model runs on every frame. Only when its confidence is
low (bad light, odd angle, occlusion) does the frame escalate to a
heavier deep model. In the offline prototype this is: a from-scratch
template-matching OCR (edge tier) escalating to a documented EasyOCR/
PaddleOCR/YOLOv8-ANPR adapter (deep tier) — see `edge/plate_ocr.py`. In
production the ratio of edge-only vs escalated frames is what determines
your actual GPU sizing at the centre (see §6).

### 3.3 Event / metadata bus (Model 3 pattern)
Edge nodes publish detection events to a topic; the correlation engine
subscribes. This is also the seam where a Model-3-style federation
adapter sits: instead of every department's VMS talking a different
protocol to a central viewer, each department's edge node publishes to
the same bus in the same event schema. Prototype uses an in-process
pub/sub (`bus.py`) with a documented Kafka/MQTT swap for production.

### 3.4 Correlation & alerting engine
Subscribes to the metadata stream, fuzzy-matches plate reads against the
vehicle watchlist (Levenshtein distance, tolerant of 1-character OCR
drift) and face labels against the person watchlist, geo-tags the result,
writes an alert. Prototype: `correlation/engine.py`, verified against
exact-match, OCR-noise fuzzy-match, and true-negative cases.

### 3.5 Unified command console (Model 2 pattern)
The operator-facing layer: live GIS map of all onboarded cameras
color-coded by health, a real-time alert feed (WebSocket-pushed), and
vehicle movement reconstruction (stitches a plate's detections across
cameras into a timestamped route). Raw video is pulled on demand via
RTSP/ONVIF proxy only when an operator opens a specific camera or
responds to an alert — not streamed centrally at all times. Prototype:
`frontend/src` + `api/main.py`.

## 4. AI / video analytics approach

| Capability | Edge tier (always-on, cheap) | Deep tier (escalated only) |
|---|---|---|
| Plate detection | Haar-cascade localisation | YOLOv8n-ANPR |
| Plate OCR | Template-matching (this repo) | EasyOCR / PaddleOCR |
| Face detection | Haar-cascade | Same (detection is cheap either way) |
| Face recognition | LBPH (this repo) | ArcFace / InsightFace embeddings + FAISS |
| Escalation trigger | Confidence < threshold | — |

This tiering is the direct answer to "AI processing capacity" in the
scalability requirement: you are not provisioning GPU inference for
80,000 concurrent streams, only for the (typically small) fraction of
frames edge models flag as low-confidence.

## 5. Bandwidth: why metadata-first changes the economics

Illustrative order-of-magnitude comparison (assumptions stated — get real
figures from a network audit before committing to a BoQ):

- **Centralised raw video** @ ~80,000 cameras × ~2 Mbps (H.264, modest
  resolution) sustained ≈ **160 Gbps** of backbone capacity, continuously,
  statewide.
- **Metadata-first**: assume ~50 vehicle-detection events/camera/hour
  (busy junction estimate) × 80,000 cameras × ~20KB per event (plate
  text + confidence + a small JPEG thumbnail) ≈ **~178 Mbps** sustained.

That's roughly a 3-order-of-magnitude reduction — it's what turns "needs a
dedicated telecom-grade backbone" into "runs over the connectivity many
sites already have," including 4G/satellite links in border and rural
districts. On-demand video pull (only when an operator opens a feed)
still requires provisioning for concurrent viewer sessions, but that
number is bounded by command-centre seats, not camera count.

## 6. Scalability strategy toward ~80,000 cameras

- **Compute**: edge nodes at camera/NVR level or regional aggregation
  hubs (one hub per ~50–200 cameras in a taluka/district, matching this
  prototype's 50-camera test scale) running the tiered inference stack.
  Central tier sized for correlation + the escalated-frame fraction only.
- **Network**: fiber where available; documented 4G/satellite fallback
  with store-and-forward buffering at the edge node during outages (queue
  locally, flush metadata when connectivity resumes — video itself never
  needs to leave the site except on-demand).
- **Storage tiering**: hot (7 days, NVMe, fast retrieval for active
  investigations) → warm (15–30 days, object storage) → cold (90+ days,
  low-cost archive) for *metadata + thumbnails*. Raw video retention stays
  governed by each department's existing policy (7/15/30 days as-is);
  Sentinel Mesh does not mandate centralising the video itself.
  PostgreSQL + PostGIS for the registry/metadata; object storage
  (S3-compatible / Ceph) for thumbnails and any escalated video clips.
- **Onboarding without redesign**: new camera = one registry row +
  pointing an edge node at its RTSP/ONVIF endpoint. No schema or
  pipeline change. New department = same event schema on the bus.
- **Disaster recovery**: regional hubs replicate metadata to a DR site
  asynchronously; registry/GIS database has standard hot-standby
  replication; edge nodes are stateless enough to be redeployed without
  data loss (their only local state is a short store-and-forward buffer).
- **Monitoring**: camera heartbeat already modeled in `db.py`
  (`last_heartbeat`, `status`) — extend with Prometheus/Grafana for
  hub-level health, queue depth, and escalation-rate dashboards.

## 7. Cybersecurity architecture

- **Transport**: TLS for all edge→bus and bus→centre traffic; VPN/MPLS
  overlay for inter-department links where available.
- **AuthN/AuthZ**: role-based access control at the console (department-
  scoped views — an RTO operator shouldn't see Home Department alerts by
  default); service-to-service auth (mTLS or signed tokens) between edge
  nodes and the bus.
- **Data minimisation**: centralising metadata rather than raw video is
  itself a privacy control — it reduces the volume of sensitive video
  data that has to be secured, transmitted, and retained centrally, and
  keeps footage of uninvolved bystanders on department-controlled storage
  under existing retention policy rather than duplicating it centrally.
- **Audit trail**: every watchlist addition, alert acknowledgment, and
  camera-registry change is logged with actor + timestamp (extend `db.py`
  tables with an `audit_log` table before production).
- **Network segmentation**: edge nodes on an isolated VLAN per site;
  central correlation engine has no direct inbound path to camera
  networks, only the outbound RTSP/ONVIF pull path for on-demand viewing.

## 8. Department-wise information required (to move past the prototype)

To onboard real feeds, each department needs to confirm: camera
count/locations (lat-lon or address), vendor + VMS platform + SDK/API
availability, current retention policy, existing network connectivity
per site, and any legal/procedural constraints on cross-department data
sharing (especially for private/commercial camera integration, which the
brief flags as "wherever feasible and permitted").

## 9. Mapping to the evaluation framework

| Evaluation area | How this design addresses it |
|---|---|
| Successful test case | Registry seeded with 50 cameras; ANPR + watchlist correlation + alerting demonstrated end-to-end offline |
| Solution architecture | Hybrid model with explicit interoperability seam (event bus) and no vendor lock-in |
| Video analytics output | Tiered ANPR + face recognition with confidence scores and timestamps |
| Scalability & PoC readiness | Bandwidth/compute argument scoped to 80,000 cameras, not just the 50-camera demo |
| Bonus: edge processing / bandwidth optimisation | Core architectural thesis, not an add-on |
| Bonus: cross-camera correlation | Vehicle route reconstruction across districts implemented and demoed |
| Bonus: integration-ready APIs | REST + WebSocket API, adapter-pattern registry inserts |

## 10. Open-source stack alignment

The hackathon's organizer materials list a recommended open-source stack:
React, Python, Node.js, PostgreSQL, PostGIS, WebRTC, RTSP, Kafka,
RabbitMQ, TensorFlow, PyTorch, FFmpeg, GStreamer, Leaflet, OpenLayers.
Where this build matches, diverges, or defers, and why:

| Recommended | This build | Note |
|---|---|---|
| Python | ✅ used throughout (edge pipeline, correlation engine, FastAPI) | |
| RTSP | ✅ `edge/live_ingest.py` | TCP transport, PTS-driven timing |
| WebRTC | ✅ WHEP client in the React dashboard | on-demand live preview — see below |
| FFmpeg | ✅ OpenCV's bundled FFMPEG backend | confirmed compiled in; no GStreamer install needed for this build |
| Leaflet | ✅ dashboard map | |
| PostgreSQL / PostGIS | 📋 documented swap-in, not yet executed | `db.py`'s schema is vanilla SQL specifically so this is a connection-string change |
| Kafka / RabbitMQ | 📋 documented swap-in, not yet executed | `bus.py`'s interface (`publish`/`subscribe`) is already shaped to match |
| TensorFlow / PyTorch | 📋 deep-tier swap-in point exists, not yet wired | EasyOCR/PaddleOCR/YOLOv8/InsightFace — the concrete options named throughout this doc — are themselves built on these frameworks |
| GStreamer | 📋 alternative to the FFmpeg backend already in use | both are open-source and interchangeable at the ingestion layer; not needed twice |
| React | ✅ production-built command-centre UI | compiled assets are served locally by FastAPI; no runtime React CDN dependency |
| Node.js | ❌ Python used server-side instead | Python is *also* on the recommended list; FastAPI (Python) was chosen for one consistent language across the edge pipeline and the API rather than splitting the stack |
| OpenLayers | ❌ Leaflet used instead | both are open-source; Leaflet was simply lighter for this scope |

Every technology actually used is open-source with no proprietary
dependency, satisfying the requirement regardless of which specific
option from each category was picked.

### Live view over WebRTC (WHEP) — closing the loop on "pull video on demand"

Section 1's architectural thesis — *pull raw video centrally only on
demand* — was, until this revision, a claim the dashboard didn't actually
implement; it showed alerts and a map, never live video. The sandbox
grid's `/stream/<id>/whep` endpoint is exactly the mechanism this design
already called for, so the dashboard now includes a real WHEP client:
clicking a camera whose registry entry has a `whep_url` opens an
`RTCPeerConnection`, negotiates over WHEP (POST the SDP offer, apply the
SDP answer), and renders the live feed in a modal. Closing it sends the
WHEP session's `DELETE` (via the `Location` header returned at
negotiation) so the server frees the session — the same "don't leave
connections open" pacing discipline the RTSP ingestion side already
follows, applied to the browser too.

## 11. Future roadmap

1. Swap edge-tier OCR/face-rec for deep models once connectivity allows
   (interfaces already support this without touching correlation logic).
2. Real VAHAN/eGujCop/AFIS/NAFIS integration (currently mocked as local
   watchlist tables with the same shape as those systems' key fields).
3. Multi-camera visual re-identification (appearance-based, not just
   plate-based) for vehicles whose plates are obscured or misread.
4. Private/commercial camera opt-in flow (society/mall CCTV) with consent
   and scoped access, per the brief's "wherever feasible and permitted."
