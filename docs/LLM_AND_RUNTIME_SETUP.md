# Sentinel Mesh — AI, images, and runtime setup

This guide takes a new machine from a clean clone to a working Sentinel Mesh
prototype. It also explains which AI components are already included, what
vehicle/face data they accept, and how to prepare an optional free local LLM.

> **Important:** no LLM, CARTO account, paid API, cloud AI key, or GPU is
> required for the working prototype. OpenStreetMap is the only map layer.

## 1. Understand the two running modes

| Mode | Use it for | Data and backend |
|---|---|---|
| GitHub Pages public demo | Presentation, UI review, and safe feature exploration | Synthetic data stored in the visitor's browser; no Python backend, uploads, RTSP, or real WebSocket |
| Local full-stack mode | API, SQLite, face-photo enrollment, live alerts, and camera integration | FastAPI + SQLite + OpenCV + in-process event bus |

Public demo:
<https://niharraval01.github.io/Gujarat-Police-Innovation-Hackathon-2026_sol_1/>

## 2. Prerequisites

Install the following on the machine:

- Git.
- Python 3.10–3.12. Python 3.11 is the safest default for the current OpenCV
  dependency set.
- Node.js 22 if you intend to rebuild the React frontend. Node is not required
  merely to run the already-built `frontend/dist` through FastAPI.
- A modern browser. Chrome, Edge, or Firefox are suitable.
- For real camera mode: network access to the sandbox `/api/ingest` catalogue
  and its RTSP/WHEP/HLS endpoints.

Confirm the tools:

```powershell
git --version
python --version
node --version
npm --version
```

On Linux/macOS, use `python3` where `python` is not available.

## 3. Clone and create an isolated Python environment

```powershell
git clone https://github.com/niharraval01/Gujarat-Police-Innovation-Hackathon-2026_sol_1.git
cd Gujarat-Police-Innovation-Hackathon-2026_sol_1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS activation:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`opencv-contrib-python` is required rather than base `opencv-python` because
the face recognizer uses `cv2.face.LBPHFaceRecognizer_create()`.

Verify the important imports:

```powershell
python -c "import cv2, fastapi, numpy; print('OpenCV', cv2.__version__, 'LBPH', hasattr(cv2, 'face'))"
```

The final value must be `LBPH True`.

## 4. Build the React dashboard

The repository already contains a production build. Rebuild it after changing
anything under `frontend/src`:

```powershell
cd frontend
npm ci
npm run build
cd ..
```

`npm ci` uses the committed lockfile and is preferred on a fresh machine.

## 5. Start the full local application

From the repository root with the virtual environment active:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open:

- Dashboard: <http://127.0.0.1:8000/>
- Health check: <http://127.0.0.1:8000/health>
- Interactive API documentation: <http://127.0.0.1:8000/docs>

Expected health response:

```json
{"status":"ok"}
```

Keep the terminal open while using the dashboard. Stop the server with
`Ctrl+C`.

## 6. Representative database and safe backups

The SQLite database is `sentinel.db`. Uploaded face references are separate
files under `data/watchlist_faces/<person_id>/`.

Before running a reset or synthetic demonstration, create a local backup:

```powershell
New-Item -ItemType Directory -Force .local-backups | Out-Null
Copy-Item sentinel.db .local-backups\sentinel-manual-backup.db
```

Linux/macOS:

```bash
mkdir -p .local-backups
cp sentinel.db .local-backups/sentinel-manual-backup.db
```

> `python seed_data.py` and `python demo/run_pipeline.py` reset `sentinel.db`.
> Use them only for representative demo data, never against an operational
> database without a backup.

Run the offline synthetic pipeline:

```powershell
python demo/run_pipeline.py
```

The expected scenario contains 50 cameras, 20 events, and 5 watchlist alerts.

## 7. What “AI” means in the current project

| Capability | Current implementation | External key/model download |
|---|---|---|
| Plate localization | OpenCV Haar cascade | None |
| Plate OCR | CPU template matching with confidence-based escalation interface | None for the working edge tier |
| Face detection | OpenCV frontal-face Haar cascade | None |
| Face recognition | OpenCV LBPH | None |
| Watchlist correlation | Fuzzy plate matching and label mapping | None |
| Threat score/hotspots/anomalies | Explainable deterministic scoring over stored metadata | None |
| Sentinel Copilot | Deterministic intent detection and evidence retrieval in `intelligence/service.py` | None |

Sentinel Copilot is deliberately **not a generative LLM today**. It recognizes
route, alert, hotspot, and camera-health questions and constructs answers from
current database evidence. This makes the prototype offline, auditable, and
predictable.

## 8. Optional free local LLM preparation with Ollama

This section is optional. It prepares a local model for a future Copilot
adapter; it does not automatically replace the current deterministic engine.

Why Ollama:

- it runs locally and can use CPU or a supported GPU;
- its local API is available at `http://localhost:11434/api`;
- local API access does not require an API key;
- the model and prompts can remain on the workstation.

### Windows

1. Install Ollama using the official Windows installer:
   <https://docs.ollama.com/windows>
2. Open a new PowerShell window.
3. Confirm it is available:

   ```powershell
   ollama --version
   ```

4. Download the small text model recommended for this metadata-only Copilot:

   ```powershell
   ollama pull gemma3:1b
   ```

   The official model page lists this model at about 815 MB:
   <https://ollama.com/library/gemma3>

5. Test it interactively:

   ```powershell
   ollama run gemma3:1b
   ```

6. Exit the chat with `/bye`, then test the local API:

   ```powershell
   $body = @{
     model = "gemma3:1b"
     messages = @(@{ role = "user"; content = "Summarize three camera alerts." })
     stream = $false
   } | ConvertTo-Json -Depth 5

   Invoke-RestMethod -Method Post `
     -Uri http://127.0.0.1:11434/api/chat `
     -ContentType "application/json" `
     -Body $body
   ```

The official chat API specification is at
<https://docs.ollama.com/api/chat>.

### Linux/macOS

Install Ollama using the appropriate official installer, then use the same
model commands:

```bash
ollama pull gemma3:1b
ollama run gemma3:1b
curl http://127.0.0.1:11434/api/chat -d '{
  "model": "gemma3:1b",
  "messages": [{"role": "user", "content": "Summarize three camera alerts."}],
  "stream": false
}'
```

### Integration status and safe design

Ollama is **prepared but not wired into Sentinel Mesh** by these steps. The UI
continues to call `POST /ai/copilot`, which currently uses
`intelligence.service.answer_query()`.

A future LLM adapter should:

1. Keep the current deterministic engine as the evidence source and fallback.
2. Send only a small structured metadata summary—not face photos, raw video,
   secrets, or an unrestricted database dump—to the local model.
3. Call `POST http://127.0.0.1:11434/api/chat` with `stream: false` and a short
   timeout.
4. Require the response to cite alert IDs/camera IDs supplied in the prompt.
5. Label generated prose as decision support and preserve human review.
6. Keep Ollama bound to localhost. Its local API has no authentication, so do
   not expose port `11434` to a public or untrusted network.

For a stronger workstation, `gemma3:4b` is a larger option. The 1B text model
is the practical default because Sentinel Copilot works over text metadata and
does not need a vision-language model.

## 9. Vehicle/watchlist input setup

The vehicle watchlist accepts **plate text**, not a car photograph.

1. Start the local application.
2. Select **Watchlist** in the header.
3. Open **Vehicles**.
4. Enter a registration number, for example `GJ06AB1234`.
5. Select `stolen`, `wanted`, `blacklisted`, or `suspect`.
6. Add a case reference or operational note.
7. Save the vehicle.

Spaces and punctuation are normalized before matching. During real operation,
plate images come from RTSP camera frames. The edge detector extracts the plate
crop and OCR converts it to text; the correlation engine then fuzzy-matches
that text against the watchlist.

There is currently no still-car-image upload feature. Use
`demo/run_pipeline.py` for a synthetic plate demonstration or `demo/run_live.py`
for live RTSP frames.

## 10. Face-photo enrollment setup

Reference-photo limits enforced by the API:

- 1–8 images per submission;
- JPEG or PNG input;
- maximum 8 MB per file;
- maximum 25 megapixels per image;
- person ID: 1–64 letters, numbers, dots, dashes, or underscores.

Recommended references:

- one consenting/authorized subject per image;
- clear, front-facing face with both eyes visible;
- even lighting and minimal motion blur;
- no beauty filters, masks, sunglasses, or heavy occlusion;
- include a few modest lighting/expression variations;
- crop near the head and shoulders, while retaining the full face.

Enrollment steps:

1. Start FastAPI and open the local dashboard.
2. Select **Watchlist → Persons**.
3. Enter a stable Person ID, name, reason, and case notes.
4. Select 1–8 reference images.
5. Select **Save & stage enrollment**.
6. Stop `demo/run_live.py` if it is already running.
7. Restart the live pipeline. It scans `data/watchlist_faces/*/`, assigns or
   reuses `face_label_id`, and trains LBPH at startup.

There is no recognizer hot reload in this prototype. Adding a database record
does not make live face matching active until the pipeline restarts.

LBPH is appropriate for a CPU-only prototype but is sensitive to pose,
lighting, aging, and camera quality. A possible match must always be verified by
an operator; it must not be treated as proof of identity.

## 11. Connect real sandbox cameras

Obtain the sandbox hostname from the authorized integration reference. First
test a small number of cameras:

```powershell
python demo/run_live.py --host YOUR_SANDBOX_HOST --scheme https --max-cameras 2 --seconds 60
```

Or select specific catalogue IDs:

```powershell
python demo/run_live.py --host YOUR_SANDBOX_HOST --scheme https --max-cameras 2 --camera-ids 1,2 --seconds 120
```

Requirements:

- the machine can reach `https://HOST/api/ingest` (or HTTP when specified);
- firewall/VPN rules allow the supplied RTSP endpoints;
- camera URLs come from the catalogue and are not hard-coded;
- load begins with 1–2 cameras and is raised deliberately;
- face references are uploaded before the pipeline starts;
- the FastAPI dashboard runs in a separate terminal.

The live reader forces RTSP over TCP, uses presentation timestamps, tolerates
decoder warm-up, reconnects with backoff, and resets per-camera correlation
state on stream discontinuities.

## 12. Browser notifications

1. Use the dashboard on `localhost` or HTTPS.
2. Select **Enable alerts** in the header.
3. Allow browser notifications when the browser asks.
4. Keep the tab open for WebSocket alerts and the short Web Audio beep.

The application never requests permission automatically. If permission was
previously denied, reset it from the browser's site settings.

## 13. Verification checklist

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Then verify:

- `/health` returns `ok`;
- the dashboard shows cameras and map markers;
- a vehicle can be added and removed;
- a person can be saved with photos;
- `demo/run_live.py` reports the number of enrolled people after restart;
- alerts can be acknowledged, noted, reopened, and filtered;
- route tracing returns ordered sightings for a detected plate;
- Sentinel Copilot answers using current stored evidence.

## 14. Common setup failures

| Symptom | Resolution |
|---|---|
| `No module named cv2` | Activate `.venv`, then reinstall `requirements.txt`. |
| `module 'cv2' has no attribute 'face'` | Remove base `opencv-python` and install `opencv-contrib-python`. |
| Dashboard is blank after source edits | Run `npm ci` and `npm run build` under `frontend`. |
| Map panel has no tiles | Allow access to the OpenStreetMap tile CDN; the rest of the local app can still operate. |
| Person saved but never matched | Restart `demo/run_live.py` and check its enrollment/skipped-photo output. |
| No live preview button | The camera catalogue did not provide WHEP/HLS, although RTSP inference may still work. |
| RTSP continually reconnects | Check VPN/firewall, catalogue URL, codec support, and start with one camera. |
| Copilot works without Ollama | Expected—the current Copilot is deterministic local NLP. |
| Ollama works but Copilot output is unchanged | Expected until an explicit backend LLM adapter is implemented. |
| GitHub Pages changes disappear on refresh/device change | Expected—public-demo mutations use browser-local storage. |
