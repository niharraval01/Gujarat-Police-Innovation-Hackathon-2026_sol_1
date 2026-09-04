import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, BellRing, Bot, Camera, ChevronRight, CircleGauge, Database, Eye,
  BookOpenCheck, Info, LayoutDashboard, Menu, Network, RefreshCw, Search,
  ShieldCheck, Sparkles, TriangleAlert, Wifi, X, ListPlus, Volume2,
} from "lucide-react";
import MapPanel from "./components/MapPanel";
import AlertFeed from "./components/AlertFeed";
import AICopilot from "./components/AICopilot";
import LiveViewModal from "./components/LiveViewModal";
import WatchlistModal from "./components/WatchlistModal";
import { AboutProject, OperatorGuide } from "./components/InfoPages";
import { alertSocket, api, formatTime } from "./lib/api";

const EMPTY_STATS = { total_cameras: 0, online: 0, offline: 0, degraded: 0, districts: 0, total_alerts: 0 };
const EMPTY_AI = { risk_score: 0, posture: "low", narrative: "Analyzing operational data…", metrics: {}, priority_alerts: [], hotspots: [], anomalies: [], recommendations: [] };

function StatCard({ icon: Icon, label, value, meta, tone }) {
  return (
    <article className={`stat-card tone-${tone || "blue"}`}>
      <div className="stat-icon"><Icon size={19} /></div>
      <div><span>{label}</span><strong>{value}</strong><small>{meta}</small></div>
      <div className="stat-glow" />
    </article>
  );
}

function RiskRing({ score, posture }) {
  const degrees = Math.round((score / 99) * 360);
  return (
    <div className={`risk-ring ${posture}`} style={{ "--risk-angle": `${degrees}deg` }}>
      <div><strong>{score}</strong><span>/99</span></div>
    </div>
  );
}

export default function App() {
  const [stats, setStats] = useState(EMPTY_STATS);
  const [cameras, setCameras] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [intelligence, setIntelligence] = useState(EMPTY_AI);
  const [detections, setDetections] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState(null);
  const [liveCamera, setLiveCamera] = useState(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(new Date());
  const [mobileNav, setMobileNav] = useState(false);
  const [view, setView] = useState("overview");
  const [watchlistOpen, setWatchlistOpen] = useState(false);
  const [alertStatus, setAlertStatus] = useState("new");
  const [alertSoundsEnabled, setAlertSoundsEnabled] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );
  const audioContextRef = useRef(null);
  const alertSoundsEnabledRef = useRef(false);

  const loadData = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [statsData, cameraData, alertData, aiData, detectionData] = await Promise.all([
        api("/stats"), api("/cameras"), api(`/alerts?limit=50&status=${alertStatus}`), api("/ai/overview"), api("/detections/recent?limit=20"),
      ]);
      setStats(statsData);
      setCameras(cameraData);
      setAlerts(alertData);
      setIntelligence(aiData);
      setDetections(detectionData);
      setConnected(true);
      setError("");
    } catch (err) {
      setConnected(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [alertStatus]);

  const signalNewAlert = useCallback((incoming) => {
    if (!alertSoundsEnabledRef.current) return;
    const context = audioContextRef.current;
    if (context) {
      if (context.state === "suspended") context.resume().catch(() => {});
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(740, context.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(980, context.currentTime + 0.12);
      gain.gain.setValueAtTime(0.0001, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.18);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start();
      oscillator.stop(context.currentTime + 0.2);
    }
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      const notification = new Notification(`Sentinel alert · ${incoming.match_key}`, {
        body: `${incoming.reason || "Watchlist match"} at ${incoming.camera_id}`,
        icon: "/brand/gujarat-police.png",
        tag: incoming.alert_id,
      });
      notification.onclick = () => {
        window.focus();
        document.getElementById("alerts")?.scrollIntoView({ behavior: "smooth" });
        notification.close();
      };
    }
  }, []);

  async function enableOperatorAlerts() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext && !audioContextRef.current) audioContextRef.current = new AudioContext();
    if (audioContextRef.current?.state === "suspended") await audioContextRef.current.resume();
    alertSoundsEnabledRef.current = true;
    setAlertSoundsEnabled(true);
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      setNotificationPermission(await Notification.requestPermission());
    } else if (typeof Notification !== "undefined") {
      setNotificationPermission(Notification.permission);
    }
  }

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000);
    const refresh = setInterval(() => loadData(true), 20000);
    return () => { clearInterval(timer); clearInterval(refresh); };
  }, [loadData]);
  useEffect(() => {
    let socket;
    let retry;
    let disposed = false;
    function connect() {
      if (disposed) return;
      socket = alertSocket();
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        const incoming = JSON.parse(event.data);
        signalNewAlert(incoming);
        loadData(true);
      };
      socket.onerror = () => setConnected(false);
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) retry = setTimeout(connect, 3000);
      };
    }
    connect();
    return () => { disposed = true; clearTimeout(retry); if (socket) socket.close(); };
  }, [loadData, signalNewAlert]);

  const cameraById = useMemo(() => Object.fromEntries(cameras.map((camera) => [camera.camera_id, camera])), [cameras]);
  const locateCamera = (id) => { const camera = cameraById[id]; if (camera) { setSelectedCamera(camera); document.getElementById("map")?.scrollIntoView({ behavior: "smooth" }); } };
  const updateAlert = () => { loadData(true); };
  const navigate = (nextView, anchor) => {
    setView(nextView);
    setMobileNav(false);
    if (anchor) setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" }), 40);
    else window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openCopilot = () => {
    navigate("overview", "copilot");
    setTimeout(() => document.getElementById("copilot-question")?.focus(), 350);
  };
  useEffect(() => {
    const shortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openCopilot();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });
  const navItems = [
    { icon: LayoutDashboard, label: "Overview", view: "overview" },
    { icon: Network, label: "Live mesh", view: "overview", anchor: "map" },
    { icon: BellRing, label: "Alerts", view: "overview", anchor: "alerts", badge: intelligence.metrics?.unacknowledged },
    { icon: Bot, label: "AI copilot", view: "overview", anchor: "copilot" },
  ];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "open" : ""}`}>
        <div className="brand-block">
          <a className="government-brand" href="https://sentinel.gujarat.gov.in/" target="_blank" rel="noreferrer">
            <img src="/brand/gujarat-police.png" alt="Gujarat Police crest" />
            <span><strong>Government of Gujarat</strong><b>Home Department</b><small>Sentinel Mesh</small></span>
          </a>
          <button className="mobile-close" onClick={() => setMobileNav(false)}><X size={19} /></button>
        </div>
        <nav>
          <span className="nav-label">Command centre</span>
          {navItems.map(({ icon: Icon, label, view: targetView, anchor, badge }) => (
            <a key={`${targetView}-${anchor || label}`} className={view === targetView && (!anchor || window.location.hash === `#${anchor}`) ? "active" : ""} href={anchor ? `#${anchor}` : "#overview"} onClick={(event) => { event.preventDefault(); navigate(targetView, anchor); }}>
              <Icon size={18} /><span>{label}</span>{badge > 0 && <b>{badge}</b>}
            </a>
          ))}
          <span className="nav-label second">System</span>
          <a href="/docs" target="_blank" rel="noreferrer"><Database size={18} /><span>API console</span></a>
          <a href="#fleet" onClick={(event) => { event.preventDefault(); navigate("overview", "fleet"); }}><Camera size={18} /><span>Camera fleet</span></a>
          <span className="nav-label second">Help & project</span>
          <a href="#guide" className={view === "guide" ? "active" : ""} onClick={(event) => { event.preventDefault(); navigate("guide"); }}><BookOpenCheck size={18} /><span>How to operate</span></a>
          <a href="#about" className={view === "about" ? "active" : ""} onClick={(event) => { event.preventDefault(); navigate("about"); }}><Info size={18} /><span>About project</span></a>
        </nav>
        <div className="edge-status">
          <div className="edge-icon"><Sparkles size={17} /></div>
          <div><strong>Edge AI active</strong><span>Local inference · secured</span></div>
          <i />
        </div>
        <div className="sidebar-foot"><span>SM-KRNR-2026</span><strong>v1.2.0</strong></div>
      </aside>

      <main>
        <header className="topbar">
          <button className="menu-button" onClick={() => setMobileNav(true)}><Menu /></button>
          <div className="page-title"><span>{view === "overview" ? "Operations" : "Sentinel Mesh"} /</span><strong>{view === "overview" ? "State overview" : view === "guide" ? "Operator guide" : "About"}</strong></div>
          <button className="header-search" onClick={openCopilot}><Search size={16} /><span>Search via Sentinel Copilot</span><kbd>Ctrl K</kbd></button>
          <div className="header-actions">
            <div className="time-block"><strong>{clock.toLocaleTimeString("en-IN", { hour12: false })}</strong><small>IST · {clock.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</small></div>
            <button className="topbar-action" onClick={() => setWatchlistOpen(true)} title="Manage vehicle and person watchlists"><ListPlus size={16} /> <span>Watchlist</span></button>
            <button className={`topbar-action ${alertSoundsEnabled ? "enabled" : ""}`} onClick={enableOperatorAlerts} title={notificationPermission === "denied" ? "Sound enabled; browser notifications are blocked" : "Enable alert sound and request desktop notifications"}><Volume2 size={16} /> <span>{alertSoundsEnabled ? "Alerts on" : "Enable alerts"}</span></button>
            <button className={`connection ${connected ? "online" : "offline"}`}><i /> {connected ? "Mesh online" : "Disconnected"}</button>
            <button className="refresh-button" onClick={() => loadData()} title="Refresh"><RefreshCw size={17} className={loading ? "spinning" : ""} /></button>
          </div>
        </header>

        <div className="content" id="overview">
          {error && <div className="error-banner"><TriangleAlert size={17} /> API unavailable: {error}</div>}
          <div className={view === "overview" ? "dashboard-view" : "dashboard-view view-hidden"}>
          <section className="hero-strip">
            <div className="hero-copy">
              <span className="eyebrow"><Activity size={12} /> Government of Gujarat · Home Department</span>
              <h1>Good {clock.getHours() < 12 ? "morning" : clock.getHours() < 17 ? "afternoon" : "evening"}, Control Room.</h1>
              <p>{intelligence.narrative}</p>
              <div className="hero-actions"><a href="#alerts">Review priority alerts <ChevronRight size={15} /></a><span><ShieldCheck size={15} /> Analysis stays on-premise</span></div>
            </div>
            <div className="posture-card">
              <RiskRing score={intelligence.risk_score} posture={intelligence.posture} />
              <div><span>AI threat posture</span><strong>{intelligence.posture}</strong><small>{intelligence.engine || "local engine"}</small></div>
            </div>
          </section>

          <section className="stats-grid">
            <StatCard icon={Camera} label="Camera fleet" value={stats.total_cameras} meta={`${stats.districts} districts onboarded`} tone="blue" />
            <StatCard icon={Wifi} label="Feeds online" value={`${stats.online}/${stats.total_cameras}`} meta={`${stats.degraded} degraded · ${stats.offline} offline`} tone="green" />
            <StatCard icon={BellRing} label="Active alerts" value={intelligence.metrics?.unacknowledged ?? stats.total_alerts} meta={`${intelligence.metrics?.critical || 0} critical priority`} tone="red" />
            <StatCard icon={Eye} label="AI detections · 24h" value={intelligence.metrics?.detections_24h || detections.length} meta="Plate + face metadata" tone="amber" />
          </section>

          <section className="main-grid">
            <MapPanel cameras={cameras} alerts={alerts} selectedCamera={selectedCamera} onSelectCamera={setSelectedCamera} onLiveView={setLiveCamera} />
            <section className="panel intelligence-card">
              <div className="panel-heading"><div><span className="eyebrow"><Sparkles size={12} /> Explainable AI</span><h2>Intelligence brief</h2></div><CircleGauge size={20} /></div>
              <div className="brief-lead"><span className={`severity-beacon ${intelligence.posture}`} /><div><strong>Operational posture · {intelligence.posture}</strong><p>{intelligence.narrative}</p></div></div>
              <div className="brief-section"><span className="mini-label">Recommended actions</span>{intelligence.recommendations.map((item, index) => <div className="recommendation" key={item}><b>0{index + 1}</b><p>{item}</p></div>)}</div>
              <div className="brief-section"><span className="mini-label">Anomaly engine</span>{intelligence.anomalies.length ? intelligence.anomalies.slice(0, 2).map((item) => <article className="anomaly" key={item.title}><TriangleAlert size={16} /><div><strong>{item.title}</strong><p>{item.detail}</p><small>{Math.round((item.confidence || 0) * 100)}% pattern confidence</small></div></article>) : <p className="quiet-text">No anomalous patterns detected.</p>}</div>
              <div className="data-boundary"><ShieldCheck size={16} /><span>{intelligence.data_boundary || "On-premise · no external AI API"}</span></div>
            </section>
          </section>

          <section className="hotspot-panel panel">
            <div className="panel-heading"><div><span className="eyebrow">AI-ranked geography</span><h2>District risk hotspots</h2></div><small>Based on watchlist severity, confidence & repeat movement</small></div>
            <div className="hotspot-grid">{intelligence.hotspots.length ? intelligence.hotspots.slice(0, 5).map((item, index) => <article key={item.district}><span className="rank">0{index + 1}</span><div className="hotspot-copy"><strong>{item.district}</strong><small>{item.alerts} alerts · {item.targets} target{item.targets === 1 ? "" : "s"}</small></div><div className="risk-bar"><i style={{ width: `${item.risk_score}%` }} /></div><b>{item.risk_score}</b></article>) : <p className="quiet-text">No alert hotspots yet.</p>}</div>
          </section>

          <section className="lower-grid">
            <AlertFeed alerts={alerts} status={alertStatus} unreadCount={intelligence.metrics?.unacknowledged || 0} onStatusChange={setAlertStatus} onUpdated={updateAlert} onLocate={locateCamera} />
            <AICopilot />
          </section>

          <section className="panel fleet-panel" id="fleet">
            <div className="panel-heading"><div><span className="eyebrow">Vendor-neutral registry</span><h2>Camera fleet health</h2></div><span className="provider-pill">Catalogue-driven · /api/ingest</span></div>
            <div className="fleet-table"><div className="fleet-head"><span>Camera</span><span>District</span><span>VMS / Vendor</span><span>Transport</span><span>Status</span></div>{cameras.slice(0, 8).map((camera) => <button className="fleet-row" key={camera.camera_id} onClick={() => { setSelectedCamera(camera); document.getElementById("map")?.scrollIntoView({ behavior: "smooth" }); }}><span><i className={`camera-state ${camera.status}`} /><div><strong>{camera.camera_id}</strong><small>{camera.name}</small></div></span><span>{camera.district}</span><span>{camera.vms_platform || camera.vendor}</span><span>{camera.connectivity}</span><span className={`status-tag ${camera.status}`}>{camera.status}</span></button>)}</div>
          </section>

          <footer><span>Government of Gujarat · Home Department · Sentinel Mesh</span><span>OpenStreetMap · FastAPI · React · OpenCV · <b>SM-KRNR-2026</b></span></footer>
          </div>
          {view === "guide" && <OperatorGuide onOpenDashboard={() => navigate("overview")} />}
          {view === "about" && <AboutProject />}
        </div>
      </main>
      {mobileNav && <button className="nav-backdrop" onClick={() => setMobileNav(false)} aria-label="Close menu" />}
      <LiveViewModal camera={liveCamera} onClose={() => setLiveCamera(null)} />
      <WatchlistModal open={watchlistOpen} onClose={() => setWatchlistOpen(false)} onChanged={() => loadData(true)} />
      <div className="ownership-watermark" aria-hidden="true">SM · KRNR · 2026</div>
    </div>
  );
}
