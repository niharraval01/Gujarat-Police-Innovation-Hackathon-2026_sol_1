import { useEffect, useState } from "react";
import { Car, ImagePlus, LoaderCircle, RotateCw, Trash2, UserRound, X } from "lucide-react";
import { api, isDemoMode } from "../lib/api";

const EMPTY_VEHICLE = { plate_number: "", reason: "stolen", notes: "" };
const EMPTY_PERSON = { person_id: "", name: "", reason: "wanted", notes: "" };

export default function WatchlistModal({ open, onClose, onChanged }) {
  const [section, setSection] = useState("vehicles");
  const [vehicles, setVehicles] = useState([]);
  const [persons, setPersons] = useState([]);
  const [vehicle, setVehicle] = useState(EMPTY_VEHICLE);
  const [person, setPerson] = useState(EMPTY_PERSON);
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setBusy(true);
    try {
      const [vehicleData, personData] = await Promise.all([
        api("/watchlist/vehicles"),
        api("/watchlist/persons"),
      ]);
      setVehicles(vehicleData);
      setPersons(personData);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!open) return undefined;
    load();
    const closeOnEscape = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  if (!open) return null;

  async function addVehicle(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/watchlist/vehicles", {
        method: "POST",
        body: JSON.stringify({ ...vehicle, source_system: "manual" }),
      });
      setVehicle(EMPTY_VEHICLE);
      setNotice("Vehicle watchlist entry saved.");
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function addPerson(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!photos.length) {
      setError("Select at least one reference face photo.");
      return;
    }
    const form = new FormData();
    Object.entries({ ...person, source_system: "manual" }).forEach(([key, value]) => form.append(key, value));
    photos.forEach((photo) => form.append("photos", photo));
    setBusy(true);
    try {
      const result = await api("/watchlist/persons", { method: "POST", body: form });
      setPerson(EMPTY_PERSON);
      setPhotos([]);
      formElement.reset();
      setNotice(result.message);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeVehicle(plateNumber) {
    if (!window.confirm(`Remove ${plateNumber} from the vehicle watchlist?`)) return;
    setBusy(true);
    try {
      await api(`/watchlist/vehicles/${encodeURIComponent(plateNumber)}`, { method: "DELETE" });
      setNotice(`${plateNumber} removed.`);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function removePerson(entry) {
    if (!window.confirm(`Remove ${entry.name || entry.person_id} and all saved reference photos?`)) return;
    setBusy(true);
    try {
      await api(`/watchlist/persons/${encodeURIComponent(entry.person_id)}`, { method: "DELETE" });
      setNotice(isDemoMode ? `${entry.name || entry.person_id} removed from this browser's demo data.` : `${entry.name || entry.person_id} removed. Restart the live pipeline to refresh enrollment.`);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="live-modal watchlist-modal" role="dialog" aria-modal="true" aria-labelledby="watchlist-title">
        <header className="live-modal-head">
          <div><span className="eyebrow">Authorized target management</span><h2 id="watchlist-title">Watchlist registry</h2></div>
          <div className="modal-head-actions">
            <button onClick={load} title="Refresh watchlist" aria-label="Refresh watchlist"><RotateCw size={16} className={busy ? "spinning" : ""} /></button>
            <button onClick={onClose} title="Close" aria-label="Close watchlist"><X size={18} /></button>
          </div>
        </header>

        <div className="watchlist-tabs" role="tablist" aria-label="Watchlist type">
          <button className={section === "vehicles" ? "active" : ""} onClick={() => setSection("vehicles")}><Car size={15} /> Vehicles <b>{vehicles.length}</b></button>
          <button className={section === "persons" ? "active" : ""} onClick={() => setSection("persons")}><UserRound size={15} /> Persons <b>{persons.length}</b></button>
        </div>

        {(error || notice) && <div className={`watchlist-message ${error ? "error" : "success"}`}>{error || notice}<button onClick={() => { setError(""); setNotice(""); }}><X size={13} /></button></div>}

        <div className="watchlist-body">
          {section === "vehicles" ? (
            <>
              <form className="watchlist-form" onSubmit={addVehicle}>
                <div className="form-heading"><Car size={17} /><div><strong>Add vehicle</strong><small>Plate matching is normalized automatically</small></div></div>
                <label>Plate number<input required maxLength="20" placeholder="GJ01AB1234" value={vehicle.plate_number} onChange={(event) => setVehicle({ ...vehicle, plate_number: event.target.value.toUpperCase() })} /></label>
                <label>Reason<select value={vehicle.reason} onChange={(event) => setVehicle({ ...vehicle, reason: event.target.value })}><option value="stolen">Stolen</option><option value="wanted">Wanted</option><option value="blacklisted">Blacklisted</option><option value="suspect">Suspect</option></select></label>
                <label className="wide">Operator notes<textarea maxLength="1000" placeholder="Case reference or operational context" value={vehicle.notes} onChange={(event) => setVehicle({ ...vehicle, notes: event.target.value })} /></label>
                <button className="primary-action" disabled={busy}>{busy ? <LoaderCircle size={15} className="spinning" /> : <Car size={15} />} Save vehicle</button>
              </form>
              <WatchlistEntries entries={vehicles} type="vehicle" onRemove={removeVehicle} />
            </>
          ) : (
            <>
              <form className="watchlist-form person-form" onSubmit={addPerson}>
                <div className="form-heading"><ImagePlus size={17} /><div><strong>Add person + reference photos</strong><small>1–8 clear front-facing images, 8 MB each</small></div></div>
                <label>Person ID<input required maxLength="64" pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,63}" placeholder="PERSON-1042" value={person.person_id} onChange={(event) => setPerson({ ...person, person_id: event.target.value })} /></label>
                <label>Name<input required maxLength="120" placeholder="Full name" value={person.name} onChange={(event) => setPerson({ ...person, name: event.target.value })} /></label>
                <label>Reason<select value={person.reason} onChange={(event) => setPerson({ ...person, reason: event.target.value })}><option value="wanted">Wanted</option><option value="missing">Missing</option><option value="suspect">Suspect</option></select></label>
                <label>Face photos<input required type="file" accept="image/jpeg,image/png" multiple onChange={(event) => setPhotos(Array.from(event.target.files || []))} /><small>{photos.length ? `${photos.length} selected` : "JPEG or PNG"}</small></label>
                <label className="wide">Operator notes<textarea maxLength="1000" placeholder="Case reference or identifying context" value={person.notes} onChange={(event) => setPerson({ ...person, notes: event.target.value })} /></label>
                <button className="primary-action" disabled={busy}>{busy ? <LoaderCircle size={15} className="spinning" /> : <UserRound size={15} />} Save & stage enrollment</button>
              </form>
              <div className="restart-advisory"><RotateCw size={15} /><span>{isDemoMode ? <>Public-demo photo selections are represented as browser-local records; images are not uploaded. Use the FastAPI deployment for actual LBPH enrollment.</> : <>Face enrollment updates when <b>demo/run_live.py</b> next starts. Hot reload is not enabled in this prototype.</>}</span></div>
              <WatchlistEntries entries={persons} type="person" onRemove={removePerson} />
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function WatchlistEntries({ entries, type, onRemove }) {
  return (
    <div className="watchlist-entries">
      <div className="list-caption"><span>Current entries</span><small>{entries.length} record{entries.length === 1 ? "" : "s"}</small></div>
      {!entries.length && <div className="watchlist-empty">No {type === "vehicle" ? "vehicles" : "persons"} enrolled.</div>}
      {entries.map((entry) => {
        const key = type === "vehicle" ? entry.plate_number : entry.person_id;
        return (
          <article className="watchlist-entry" key={key}>
            <div className="watchlist-avatar">
              {type === "person" && entry.photo_urls?.[0] ? <img src={entry.photo_urls[0]} alt="" /> : type === "person" ? <UserRound size={17} /> : <Car size={17} />}
            </div>
            <div><strong>{type === "vehicle" ? entry.plate_number : entry.name}</strong><span>{type === "person" ? `${entry.person_id} · ${entry.photo_count || 0} photo(s) · label ${entry.face_label_id ?? "pending"}` : entry.source_system || "manual"}</span>{entry.notes && <small>{entry.notes}</small>}</div>
            <span className={`reason-badge ${String(entry.reason).toLowerCase()}`}>{entry.reason}</span>
            <button className="delete-action" onClick={() => onRemove(type === "vehicle" ? entry.plate_number : entry)} title={`Remove ${key}`}><Trash2 size={15} /><span>Remove</span></button>
          </article>
        );
      })}
    </div>
  );
}
