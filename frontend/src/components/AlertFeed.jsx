import { useState } from "react";
import { Check, LocateFixed, ShieldAlert, UserRound, Car, RotateCcw } from "lucide-react";
import { api, relativeTime } from "../lib/api";

const STATUS_TABS = [
  ["new", "New"],
  ["acknowledged", "Acknowledged"],
  ["all", "All"],
];

export default function AlertFeed({ alerts, status, unreadCount, onStatusChange, onUpdated, onLocate }) {
  const [notes, setNotes] = useState({});
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");

  async function toggle(alert) {
    setWorking(alert.alert_id);
    setError("");
    try {
      const updated = await api(`/alerts/${alert.alert_id}/acknowledge`, {
        method: "PATCH",
        body: JSON.stringify({
          acknowledged: !alert.acknowledged,
          note: notes[alert.alert_id] ?? alert.operator_notes ?? "",
        }),
      });
      setNotes((current) => ({ ...current, [alert.alert_id]: "" }));
      onUpdated(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setWorking("");
    }
  }

  return (
    <section className="panel alert-panel" id="alerts">
      <div className="panel-heading alert-heading">
        <div>
          <span className="eyebrow">Operator triage queue</span>
          <h2>Priority alerts {unreadCount > 0 && <b className="unread-badge" aria-label={`${unreadCount} unacknowledged alerts`}>{unreadCount > 99 ? "99+" : unreadCount}</b>}</h2>
        </div>
        <span className="live-pill"><i /> WebSocket live</span>
      </div>
      <div className="alert-tabs" role="tablist" aria-label="Alert status">
        {STATUS_TABS.map(([value, label]) => (
          <button key={value} role="tab" aria-selected={status === value} className={status === value ? "active" : ""} onClick={() => onStatusChange(value)}>
            {label}{value === "new" && unreadCount > 0 ? <b>{unreadCount}</b> : null}
          </button>
        ))}
      </div>
      {error && <div className="alert-error">Could not update alert: {error}</div>}
      <div className="alert-list">
        {alerts.length === 0 && <div className="empty-state"><ShieldAlert /> No {status === "all" ? "" : `${status} `}alerts</div>}
        {alerts.slice(0, 50).map((alert) => (
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
              {alert.operator_notes && <p className="saved-note"><b>Operator note:</b> {alert.operator_notes}</p>}
              <input
                className="operator-note"
                maxLength="2000"
                aria-label={`Operator note for ${alert.match_key}`}
                placeholder={alert.acknowledged ? "Update note (optional)" : "Add operator note (optional)"}
                value={notes[alert.alert_id] ?? ""}
                onChange={(event) => setNotes((current) => ({ ...current, [alert.alert_id]: event.target.value }))}
              />
            </div>
            <div className="alert-actions">
              <button className="icon-button" title="Locate camera" onClick={() => onLocate(alert.camera_id)}><LocateFixed size={15} /></button>
              <button disabled={working === alert.alert_id} className={`ack-button ${alert.acknowledged ? "done" : ""}`} onClick={() => toggle(alert)}>
                {alert.acknowledged ? <RotateCcw size={14} /> : <Check size={14} />} {alert.acknowledged ? "Reopen" : "Acknowledge"}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
