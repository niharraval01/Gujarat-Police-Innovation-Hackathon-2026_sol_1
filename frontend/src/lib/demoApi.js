const STORAGE_KEY = "sentinel-mesh-pages-demo-v1";

const SITES = [
  ["Valsad", "Valsad", 20.5992, 72.9342],
  ["Dahod", "Dahod", 22.8331, 74.2593],
  ["Gir Somnath", "Veraval", 20.9077, 70.3661],
  ["Jamnagar", "Jamnagar", 22.4707, 70.0577],
  ["Devbhoomi Dwarka", "Dwarka", 22.2394, 68.9678],
  ["Ahmedabad", "Ahmedabad", 23.0225, 72.5714],
  ["Surat", "Surat", 21.1702, 72.8311],
  ["Vadodara", "Vadodara", 22.3072, 73.1812],
  ["Rajkot", "Rajkot", 22.3039, 70.8022],
  ["Bhavnagar", "Bhavnagar", 21.7645, 72.1519],
  ["Junagadh", "Junagadh", 21.5222, 70.4579],
  ["Gandhinagar", "Gandhinagar", 23.2156, 72.6369],
  ["Anand", "Anand", 22.5645, 72.9289],
  ["Bharuch", "Bharuch", 21.7051, 73.0],
  ["Navsari", "Navsari", 20.9467, 72.952],
  ["Mehsana", "Mehsana", 23.588, 72.3693],
  ["Patan", "Patan", 23.8493, 72.1266],
  ["Morbi", "Morbi", 22.8173, 70.8378],
  ["Porbandar", "Porbandar", 21.6417, 69.6293],
  ["Kutch", "Bhuj", 23.2419, 69.6669],
  ["Surendranagar", "Surendranagar", 22.728, 71.6379],
  ["Panchmahal", "Godhra", 22.7772, 73.6151],
  ["Ankleshwar", "Ankleshwar", 21.6266, 73.0104],
  ["Amreli", "Amreli", 21.6032, 71.2213],
  ["Botad", "Botad", 22.1704, 71.666],
];

const VEHICLES = [
  ["GJ06AB1234", "stolen", "VAHAN", "Reported stolen — Ahmedabad, 12 Aug 2026"],
  ["GJ18CD5678", "wanted", "eGujCop", "Vehicle linked to open FIR #2026/4471"],
  ["GJ01XY9999", "blacklisted", "manual", "Repeated overloading violations"],
  ["GJ27PQ0001", "suspect", "eGujCop", "Flagged in ongoing surveillance case"],
  ["GJ05LM4321", "stolen", "VAHAN", "Reported stolen — Surat, 03 Aug 2026"],
];

const clone = (value) => JSON.parse(JSON.stringify(value));
const normalizePlate = (value) => String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

function generateCameras() {
  const vendors = ["Hikvision", "Dahua", "CP Plus", "Honeywell", "Bosch"];
  const platforms = ["HikCentral", "DSS Pro", "Milestone XProtect", "Genetec Security Center"];
  return Array.from({ length: 50 }, (_, index) => {
    const [district, city, lat, lon] = SITES[index % SITES.length];
    const number = index + 1;
    const offset = (((number * 17) % 11) - 5) / 125;
    const status = number % 23 === 0 ? "offline" : number % 11 === 0 ? "degraded" : "online";
    return {
      camera_id: `GJ-${district.replace(/\s/g, "").slice(0, 3).toUpperCase()}-${String(number).padStart(3, "0")}`,
      name: `${city} ${number % 3 === 0 ? "Traffic Junction" : "Police Checkpoint"} Cam-${number}`,
      department: "Home",
      vendor: vendors[index % vendors.length],
      vms_platform: platforms[index % platforms.length],
      lat: Number((lat + offset).toFixed(5)),
      lon: Number((lon - offset / 2).toFixed(5)),
      district,
      camera_type: number % 4 === 0 ? "ANPR-dedicated" : "fixed",
      connectivity: number % 7 === 0 ? "4G" : "fiber",
      storage_days: number % 3 === 0 ? 30 : 15,
      status,
      rtsp_url: null,
      whep_url: null,
      hls_url: null,
    };
  });
}

function initialState() {
  const cameras = generateCameras();
  const now = Date.now() / 1000;
  const sightings = [5, 7, 8, 17].map((siteIndex, index) => {
    const camera = cameras[siteIndex];
    return {
      detection_id: `DEMO-ROUTE-${index + 1}`,
      camera_id: camera.camera_id,
      camera_name: camera.name,
      district: camera.district,
      lat: camera.lat,
      lon: camera.lon,
      detection_type: "plate",
      value: "GJ06AB1234",
      confidence: 0.91 + index * 0.01,
      ts: now - (48 - index * 11) * 60,
    };
  });
  const alertSpecs = [
    ["ALERT-DEMO-001", 17, "vehicle", "GJ06AB1234", "stolen", 0.96, 8],
    ["ALERT-DEMO-002", 12, "vehicle", "GJ18CD5678", "wanted", 0.93, 19],
    ["ALERT-DEMO-003", 5, "person", "P-1001", "wanted", 0.89, 31],
    ["ALERT-DEMO-004", 31, "vehicle", "GJ05LM4321", "stolen", 0.91, 46],
    ["ALERT-DEMO-005", 7, "person", "P-1002", "missing", 0.87, 63],
  ];
  const alerts = alertSpecs.map(([alertId, cameraIndex, matchType, matchKey, reason, confidence, minutes]) => {
    const camera = cameras[cameraIndex];
    return {
      alert_id: alertId,
      camera_id: camera.camera_id,
      camera_name: camera.name,
      district: camera.district,
      lat: camera.lat,
      lon: camera.lon,
      match_type: matchType,
      match_key: matchKey,
      reason,
      confidence,
      ts: now - minutes * 60,
      acknowledged: 0,
      operator_notes: "",
    };
  });
  const detections = [
    ...sightings,
    ...alerts.map((alert, index) => ({
      detection_id: `DEMO-DETECTION-${index + 1}`,
      camera_id: alert.camera_id,
      camera_name: alert.camera_name,
      district: alert.district,
      lat: alert.lat,
      lon: alert.lon,
      detection_type: alert.match_type === "person" ? "face" : "plate",
      value: alert.match_key,
      confidence: alert.confidence,
      ts: alert.ts,
    })),
  ];
  return {
    cameras,
    vehicles: VEHICLES.map(([plate_number, reason, source_system, notes]) => ({ plate_number, reason, source_system, notes })),
    persons: [
      { person_id: "P-1001", name: "Unidentified Suspect A", reason: "wanted", face_label_id: 1, source_system: "eGujCop", notes: "Wanted in theft case #2026/1187", photo_count: 1, photo_urls: [] },
      { person_id: "P-1002", name: "Missing Person B", reason: "missing", face_label_id: 2, source_system: "manual", notes: "Reported missing — family contacted via helpline", photo_count: 1, photo_urls: [] },
    ],
    alerts,
    detections,
  };
}

function readState() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : initialState();
  } catch {
    return initialState();
  }
}

function writeState(state) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // The demo remains usable in privacy modes that disable browser storage.
  }
}

function overview(state) {
  const unacknowledged = state.alerts.filter((alert) => !alert.acknowledged).length;
  const grouped = new Map();
  state.alerts.forEach((alert) => {
    const row = grouped.get(alert.district) || { district: alert.district, alerts: 0, targets: new Set(), risk: 48 };
    row.alerts += 1;
    row.targets.add(alert.match_key);
    row.risk = Math.max(row.risk, Math.round(alert.confidence * 62 + (alert.reason === "wanted" ? 31 : 24)));
    grouped.set(alert.district, row);
  });
  const hotspots = [...grouped.values()]
    .map((row) => ({ district: row.district, alerts: row.alerts, targets: row.targets.size, critical: row.risk >= 82 ? 1 : 0, risk_score: Math.min(99, row.risk) }))
    .sort((first, second) => second.risk_score - first.risk_score);
  const anomalies = state.cameras
    .filter((camera) => camera.status !== "online")
    .slice(0, 4)
    .map((camera) => ({
      type: "camera_health",
      severity: camera.status === "offline" ? "high" : "medium",
      title: `Camera ${camera.status} · ${camera.camera_id}`,
      detail: `${camera.name} in ${camera.district} needs operator review.`,
      confidence: 1,
      camera_id: camera.camera_id,
    }));
  const critical = state.alerts.filter((alert) => alert.reason === "wanted" && alert.confidence >= 0.9).length;
  const riskScore = Math.min(99, 28 + critical * 12 + unacknowledged * 5 + anomalies.length * 3);
  const posture = riskScore >= 82 ? "critical" : riskScore >= 68 ? "high" : riskScore >= 48 ? "medium" : "low";
  const lead = state.alerts.find((alert) => !alert.acknowledged) || state.alerts[0];
  return {
    generated_at: Date.now() / 1000,
    engine: "sentinel-public-demo-v1",
    data_boundary: "Public demonstration · synthetic browser-local data",
    risk_score: riskScore,
    posture,
    narrative: lead
      ? `${unacknowledged} demonstration alerts await review. Highest visible priority is ${lead.match_key} at ${lead.district}.`
      : "No demonstration alerts are currently active.",
    metrics: { unacknowledged, critical, anomalies: anomalies.length, detections_24h: state.detections.length },
    priority_alerts: clone(state.alerts),
    hotspots,
    anomalies,
    recommendations: [
      lead ? `Validate ${lead.match_key} against the related camera evidence before escalation.` : "Maintain camera-health monitoring.",
      "Use the local FastAPI deployment for real camera feeds, persistent enrollment, and live alert delivery.",
    ],
  };
}

function copilotAnswer(question, state) {
  const clean = String(question || "").trim();
  const lower = clean.toLowerCase();
  const summary = overview(state);
  const plate = normalizePlate(clean.match(/[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{1,4}/i)?.[0]);
  let intent = "operational_summary";
  let answer = `${summary.narrative} This answer uses synthetic GitHub Pages demonstration data.`;
  let evidence = summary.priority_alerts.slice(0, 3);
  if (plate) {
    intent = "vehicle_route";
    evidence = state.detections.filter((item) => normalizePlate(item.value) === plate);
    answer = evidence.length
      ? `${plate} has ${evidence.length} synthetic correlated sighting(s) across ${evidence.map((item) => item.district).join(" → ")}.`
      : `No demonstration route is stored for ${plate}.`;
  } else if (/offline|degraded|camera health|coverage/.test(lower)) {
    intent = "camera_health";
    evidence = state.cameras.filter((camera) => camera.status !== "online");
    answer = `${state.cameras.length - evidence.length} of ${state.cameras.length} demonstration cameras are online; ${evidence.length} need attention.`;
  } else if (/hotspot|district|where|risk area/.test(lower)) {
    intent = "hotspots";
    evidence = summary.hotspots.slice(0, 3);
    answer = `Highest synthetic risk: ${evidence.map((item) => `${item.district} (${item.risk_score}/99)`).join(", ")}.`;
  } else if (/alert|wanted|stolen|suspect|missing|vehicle|person/.test(lower)) {
    intent = "alert_search";
    const reasons = ["wanted", "stolen", "suspect", "missing", "blacklisted"].filter((reason) => lower.includes(reason));
    evidence = state.alerts.filter((alert) => !reasons.length || reasons.includes(alert.reason));
    answer = `I found ${evidence.length} matching synthetic alert(s).${evidence.length ? ` Latest: ${evidence.slice(0, 3).map((item) => `${item.match_key} · ${item.district}`).join("; ")}.` : ""}`;
  }
  return { question: clean, intent, answer, evidence: clone(evidence), generated_at: Date.now() / 1000, engine: "sentinel-public-demo-nlp-v1" };
}

function parseJsonBody(options) {
  if (!options.body) return {};
  if (typeof options.body === "string") return JSON.parse(options.body);
  return options.body;
}

export async function demoApi(path, options = {}) {
  const state = readState();
  const url = new URL(path, window.location.origin);
  const method = String(options.method || "GET").toUpperCase();
  const pathname = url.pathname;

  if (method === "GET" && pathname === "/stats") {
    return {
      total_cameras: state.cameras.length,
      online: state.cameras.filter((camera) => camera.status === "online").length,
      offline: state.cameras.filter((camera) => camera.status === "offline").length,
      degraded: state.cameras.filter((camera) => camera.status === "degraded").length,
      districts: new Set(state.cameras.map((camera) => camera.district)).size,
      total_alerts: state.alerts.length,
      watchlist_vehicles: state.vehicles.length,
      watchlist_persons: state.persons.length,
    };
  }
  if (method === "GET" && pathname === "/cameras") return clone(state.cameras);
  if (method === "GET" && pathname === "/detections/recent") return clone(state.detections.slice(0, Number(url.searchParams.get("limit")) || 50));
  if (method === "GET" && pathname === "/ai/overview") return overview(state);
  if (method === "POST" && pathname === "/ai/copilot") return copilotAnswer(parseJsonBody(options).question, state);
  if (method === "GET" && pathname === "/alerts") {
    const status = url.searchParams.get("status") || "new";
    const limit = Number(url.searchParams.get("limit")) || 100;
    const alerts = state.alerts.filter((alert) => status === "all" || (status === "acknowledged" ? alert.acknowledged : !alert.acknowledged));
    return clone(alerts.slice(0, limit));
  }
  if (method === "GET" && pathname === "/watchlist/vehicles") return clone(state.vehicles);
  if (method === "GET" && pathname === "/watchlist/persons") return clone(state.persons);

  const routeMatch = pathname.match(/^\/vehicles\/([^/]+)\/route$/);
  if (method === "GET" && routeMatch) {
    const plate = normalizePlate(decodeURIComponent(routeMatch[1]));
    return clone(state.detections.filter((item) => item.detection_type === "plate" && normalizePlate(item.value) === plate).sort((first, second) => first.ts - second.ts));
  }
  const alertMatch = pathname.match(/^\/alerts\/([^/]+)\/acknowledge$/);
  if (method === "PATCH" && alertMatch) {
    const alert = state.alerts.find((item) => item.alert_id === decodeURIComponent(alertMatch[1]));
    if (!alert) throw new Error("Alert not found");
    const payload = parseJsonBody(options);
    alert.acknowledged = payload.acknowledged === false ? 0 : 1;
    if (payload.note !== undefined) alert.operator_notes = String(payload.note || "");
    writeState(state);
    return clone(alert);
  }
  if (method === "POST" && pathname === "/watchlist/vehicles") {
    const payload = parseJsonBody(options);
    const plate = normalizePlate(payload.plate_number);
    if (!plate) throw new Error("Plate number is required");
    if (state.vehicles.some((item) => item.plate_number === plate)) throw new Error("Vehicle is already on the watchlist");
    state.vehicles.unshift({ ...payload, plate_number: plate, source_system: payload.source_system || "manual" });
    writeState(state);
    return { ok: true };
  }
  if (method === "POST" && pathname === "/watchlist/persons") {
    const form = options.body;
    const personId = String(form.get("person_id") || "").trim();
    const photos = form.getAll("photos");
    if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(personId)) throw new Error("Enter a valid person ID");
    if (!photos.length || photos.length > 8) throw new Error("Select 1–8 reference photos");
    if (state.persons.some((item) => item.person_id === personId)) throw new Error("Person ID is already on the watchlist");
    const nextLabel = Math.max(0, ...state.persons.map((item) => Number(item.face_label_id) || 0)) + 1;
    const person = {
      person_id: personId,
      name: String(form.get("name") || "").trim(),
      reason: String(form.get("reason") || "wanted"),
      source_system: String(form.get("source_system") || "manual"),
      notes: String(form.get("notes") || ""),
      face_label_id: nextLabel,
      photo_count: photos.length,
      photo_urls: [],
    };
    state.persons.unshift(person);
    writeState(state);
    return { ok: true, person: clone(person), face_label_id: nextLabel, restart_required: false, message: "Person saved in this browser's demonstration watchlist." };
  }
  const vehicleDelete = pathname.match(/^\/watchlist\/vehicles\/([^/]+)$/);
  if (method === "DELETE" && vehicleDelete) {
    const plate = normalizePlate(decodeURIComponent(vehicleDelete[1]));
    const next = state.vehicles.filter((item) => item.plate_number !== plate);
    if (next.length === state.vehicles.length) throw new Error("Vehicle watchlist entry not found");
    state.vehicles = next;
    writeState(state);
    return { ok: true };
  }
  const personDelete = pathname.match(/^\/watchlist\/persons\/([^/]+)$/);
  if (method === "DELETE" && personDelete) {
    const personId = decodeURIComponent(personDelete[1]);
    const next = state.persons.filter((item) => item.person_id !== personId);
    if (next.length === state.persons.length) throw new Error("Person watchlist entry not found");
    state.persons = next;
    writeState(state);
    return { ok: true };
  }
  throw new Error(`This operation is unavailable in the public demo (${method} ${pathname})`);
}

export function demoAlertSocket() {
  const socket = { onopen: null, onmessage: null, onerror: null, onclose: null };
  const openTimer = window.setTimeout(() => socket.onopen?.({ type: "open" }), 40);
  socket.close = () => {
    window.clearTimeout(openTimer);
    window.setTimeout(() => socket.onclose?.({ type: "close" }), 0);
  };
  return socket;
}
