import { Check, LocateFixed, ShieldAlert, UserRound, Car } from "lucide-react";
import { api, relativeTime } from "../lib/api";

export default function AlertFeed({ alerts, onUpdated, onLocate }) {
  async function toggle(alert) {
    const updated = await api(`/alerts/${alert.alert_id}/acknowledge`, {
      method: "PATCH",
      body: JSON.stringify({ acknowledged: !alert.acknowledged }),
    });
    onUpdated(updated);
  }

  return (
    <section className="panel alert-panel" id="alerts">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Live correlation stream</span>
          <h2>Priority alerts</h2>
        </div>
        <span className="live-pill"><i /> WebSocket live</span>
      </div>
      <div className="alert-list">
        {alerts.length === 0 && <div className="empty-state"><ShieldAlert /> No active alerts</div>}
        {alerts.slice(0, 8).map((alert) => (
          <article className={`alert-row ${alert.acknowledged ? "acknowledged" : ""}`} key={alert.alert_id}>
            <div className={`alert-icon ${alert.match_type}`}>
              {alert.match_type === "person" ? <UserRound size={18} /> : <Car size={18} />}
            </div>
            <div className="alert-copy">
              <div className="alert-title-line">
                <strong>{alert.match_key}</strong>
                <span className={`reason-badge ${String(alert.reason).toLowerCase()}`}>{alert.reason}</span>
              </div>
              <p>{alert.camera_name || alert.camera_id}</p>
              <small>{alert.district || "Unknown district"} · {relativeTime(alert.ts)} · {Math.round((alert.confidence || 0) * 100)}% confidence</small>
            </div>
            <div className="alert-actions">
              <button className="icon-button" title="Locate camera" onClick={() => onLocate(alert.camera_id)}><LocateFixed size={15} /></button>
              <button className={`ack-button ${alert.acknowledged ? "done" : ""}`} onClick={() => toggle(alert)}>
                <Check size={14} /> {alert.acknowledged ? "Acknowledged" : "Acknowledge"}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
