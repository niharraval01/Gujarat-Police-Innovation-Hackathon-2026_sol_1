import {
  BellRing, BookOpenCheck, Bot, Camera, Car, CheckCircle2, Database, ExternalLink,
  Eye, Fingerprint, ImagePlus, Map, Network, Play, Route, Satellite, ShieldCheck, Users,
} from "lucide-react";
import { assetUrl, isDemoMode } from "../lib/api";

const OFFICIAL_SITE = "https://sentinel.gujarat.gov.in/";

function PageIntro({ eyebrow, title, children }) {
  return (
    <div className="info-intro">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      <img src={assetUrl("brand/gujarat-police.png")} alt="Gujarat Police crest" />
    </div>
  );
}

export function OperatorGuide({ onOpenDashboard }) {
  const tasks = [
    {
      icon: Map,
      title: "Monitor the camera mesh",
      why: "Confirm coverage and camera health before relying on alert evidence.",
      steps: ["Review online, degraded, and offline totals.", "Select a map marker for camera details.", "Check the fleet row for vendor and transport.", "Escalate unexplained coverage gaps."],
    },
    {
      icon: Car,
      title: "Add a vehicle watchlist target",
      why: "Plate detections alert only when they correlate with an authorized target.",
      steps: ["Open Watchlist, then Vehicles.", "Enter the registration number and reason.", "Add a case/source note.", "Save, then remove the entry when authorization ends."],
    },
    {
      icon: ImagePlus,
      title: "Enroll a person safely",
      why: "The local recognizer needs authorized reference samples mapped to a stable Person ID.",
      steps: ["Open Watchlist, then Persons.", "Add identity, reason, notes, and 1–8 clear photos.", "Save the staged enrollment.", "Restart demo/run_live.py and check enrollment output."],
    },
    {
      icon: BellRing,
      title: "Review and acknowledge an alert",
      why: "Triage assigns a reviewed state without deleting the evidence.",
      steps: ["Open Priority alerts.", "Validate the plate/person and confidence.", "Locate the camera on the map.", "Acknowledge only after operator review."],
    },
    {
      icon: Route,
      title: "Reconstruct a vehicle route",
      why: "Ordered metadata can reveal movement while avoiding continuous central video transfer.",
      steps: ["Enter a registration number in AI route reconstruction.", "Select Trace.", "Review ordered map hops and timestamps.", "Validate impossible-travel anomalies before escalation."],
    },
    {
      icon: Play,
      title: "Open live video on demand",
      why: "Pull raw video only when human verification is required.",
      steps: ["Select a camera marker.", "Choose Open live view when WHEP/HLS is available.", "Use video only for verification.", "Close the viewer to release the stream immediately."],
    },
    {
      icon: Bot,
      title: "Use Sentinel Copilot",
      why: "Evidence-backed intent search reduces navigation time without outsourcing data.",
      steps: ["Ask about hotspots, stolen vehicles, routes, or camera health.", "Review the returned evidence.", "Treat the answer as decision support, not an enforcement decision."],
    },
  ];

  return (
    <div className="info-view operator-guide">
      <PageIntro eyebrow="Operator handbook · v1.2" title="How to operate Sentinel Mesh">
        A concise field guide for command-centre operators, technical evaluators, and camera administrators.
      </PageIntro>

      <section className="guide-mode-callout info-panel">
        <ShieldCheck size={19} />
        <div><strong>{isDemoMode ? "Public demonstration mode" : "Local full-stack mode"}</strong><p>{isDemoMode ? "All visible records are synthetic; changes remain in this browser and no photos are uploaded." : "FastAPI, SQLite, saved face references, and the live alert channel are available on this machine."}</p></div>
      </section>

      <section className="info-panel quick-start-panel">
        <div className="info-heading"><div><BookOpenCheck size={19} /><span>Start here</span></div><button onClick={onOpenDashboard}>Open dashboard</button></div>
        <div className="workflow-row">
          {["Observe", "Validate", "Correlate", "Respond"].map((label, index) => (
            <div className="workflow-step" key={label}><b>{index + 1}</b><div><strong>{label}</strong><small>{["Monitor fleet and alerts", "Check confidence and video", "Review routes and context", "Acknowledge and dispatch"][index]}</small></div></div>
          ))}
        </div>
      </section>

      <section className="guide-grid">
        {tasks.map(({ icon: Icon, title, why, steps }) => (
          <article className="info-panel task-card" key={title}>
            <div className="task-title"><span><Icon size={19} /></span><h2>{title}</h2></div>
            <p className="task-why"><b>Why:</b> {why}</p>
            <ol>{steps.map((step) => <li key={step}>{step}</li>)}</ol>
          </article>
        ))}
      </section>

      <section className="info-panel system-flow">
        <div className="info-heading"><div><Network size={19} /><span>How the system works</span></div><small>Metadata-first, video on demand</small></div>
        <div className="architecture-flow">
          <div><Camera /><strong>Camera grid</strong><small>RTSP over TCP</small></div><i>→</i>
          <div><Fingerprint /><strong>Edge AI</strong><small>Plate + face inference</small></div><i>→</i>
          <div><Database /><strong>Metadata bus</strong><small>PTS-stamped events</small></div><i>→</i>
          <div><ShieldCheck /><strong>Correlation</strong><small>Watchlist + anomaly</small></div><i>→</i>
          <div><Eye /><strong>Command centre</strong><small>Evidence-led response</small></div>
        </div>
      </section>

      <section className="guide-notes">
        <article className="info-panel"><h3>Evaluation-day camera connection</h3><p>Always load camera IDs and RTSP/WHEP/HLS URLs from <code>/api/ingest</code>. Force RTSP over TCP, use presentation timestamps rather than arrival time, and reconnect with exponential backoff.</p></article>
        <article className="info-panel"><h3>Operator responsibility</h3><p>AI scores prioritize review; they do not establish identity or guilt. Confirm high-impact events against live video, source systems, and standard operating procedures.</p></article>
      </section>

      <section className="guide-docs info-panel">
        <div><BookOpenCheck size={18} /><div><strong>Detailed project guides</strong><p>Installation, optional free local LLM preparation, image requirements, troubleshooting, and full feature procedures.</p></div></div>
        <a href="https://github.com/niharraval01/Gujarat-Police-Innovation-Hackathon-2026_sol_1/blob/main/docs/LLM_AND_RUNTIME_SETUP.md" target="_blank" rel="noreferrer">Setup guide <ExternalLink size={13} /></a>
        <a href="https://github.com/niharraval01/Gujarat-Police-Innovation-Hackathon-2026_sol_1/blob/main/docs/FEATURE_USER_GUIDE.md" target="_blank" rel="noreferrer">Feature guide <ExternalLink size={13} /></a>
      </section>
    </div>
  );
}

export function AboutProject() {
  const capabilities = [
    [Camera, "Vendor-neutral registry", "50-camera prototype across 25 Gujarat districts"],
    [Satellite, "Resilient live ingestion", "RTSP/TCP, PTS timing, mixed codecs and reconnect backoff"],
    [Fingerprint, "Edge inference", "Local plate OCR, face recognition and tiered escalation"],
    [Map, "Cross-camera intelligence", "Routes, hotspots, watchlist correlation and anomaly evidence"],
  ];

  return (
    <div className="info-view about-view">
      <PageIntro eyebrow="Government of Gujarat · Home Department" title="About Sentinel Mesh">
        An edge-correlated CCTV intelligence prototype built for the Gujarat Police Innovation Challenge 2026.
      </PageIntro>

      <section className="about-purpose info-panel">
        <div><span className="section-index">01</span><h2>Purpose</h2></div>
        <p>Sentinel Mesh unifies heterogeneous camera estates without replacing existing VMS platforms. AI inference runs close to the camera; only high-value metadata moves to the command centre, while raw video is pulled when an operator requests verification.</p>
      </section>

      <section className="capability-grid">
        {capabilities.map(([Icon, title, detail]) => <article className="info-panel" key={title}><Icon size={21} /><strong>{title}</strong><p>{detail}</p></article>)}
      </section>

      <section className="about-split">
        <article className="info-panel governance-card">
          <span className="section-index">02</span><h2>Responsible intelligence</h2>
          <ul>
            <li><CheckCircle2 /> Explainable priority factors and evidence</li>
            <li><CheckCircle2 /> No external AI API or map API key</li>
            <li><CheckCircle2 /> On-premise metadata processing</li>
            <li><CheckCircle2 /> Human acknowledgement before action</li>
          </ul>
        </article>
        <article className="info-panel stewardship-card">
          <span className="section-index">03</span><h2>Project stewardship</h2>
          <p>Prototype architecture, implementation, and experience design by</p>
          <div className="creator-names"><strong>Krishna Raval</strong><span>&</span><strong>Nihar Raval</strong></div>
          <small>Authorship reference · SM-KRNR-2026</small>
        </article>
      </section>

      <section className="official-reference info-panel">
        <img src={assetUrl("brand/gujarat-police.png")} alt="Gujarat Police crest" />
        <div><strong>Government of Gujarat</strong><span>Home Department</span><p>Built as an independent hackathon prototype in support of unified, secure, and intelligent CCTV operations.</p></div>
        <a href={OFFICIAL_SITE} target="_blank" rel="noreferrer">Official challenge portal <ExternalLink size={14} /></a>
      </section>
    </div>
  );
}
