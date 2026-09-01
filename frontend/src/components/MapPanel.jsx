import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Crosshair, Play, Route, Search } from "lucide-react";
import { api, formatTime } from "../lib/api";

const STATUS_COLORS = { online: "#35d49a", degraded: "#f4b942", offline: "#ff5b68" };

function MapFocus({ camera, route }) {
  const map = useMap();
  useEffect(() => {
    if (route.length > 1) map.fitBounds(route.map((hop) => [hop.lat, hop.lon]), { padding: [42, 42] });
    else if (camera?.lat != null) map.flyTo([camera.lat, camera.lon], 10, { duration: 0.8 });
  }, [camera, route, map]);
  return null;
}

export default function MapPanel({ cameras, alerts, selectedCamera, onSelectCamera, onLiveView }) {
  const [plate, setPlate] = useState("GJ06AB1234");
  const [route, setRoute] = useState([]);
  const [routeState, setRouteState] = useState("");
  const alertCameras = useMemo(() => new Set(alerts.map((alert) => alert.camera_id)), [alerts]);

  async function traceVehicle(event) {
    event?.preventDefault();
    const normalized = plate.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!normalized) return;
    setRouteState("Tracing correlated metadata…");
    try {
      const result = await api(`/vehicles/${normalized}/route`);
      setRoute(result);
      setRouteState(result.length ? `${result.length} sightings reconstructed` : "No sightings found");
    } catch (error) {
      setRouteState(error.message);
    }
  }

  return (
    <section className="panel map-card" id="map">
      <div className="panel-heading map-heading">
        <div>
          <span className="eyebrow">Geospatial command layer</span>
          <h2>Statewide camera mesh</h2>
        </div>
        <div className="map-legend">
          <span><i className="legend-dot online" /> Online</span>
          <span><i className="legend-dot alert" /> Alert</span>
        </div>
      </div>
      <div className="map-stage">
        <MapContainer center={[22.4, 71.5]} zoom={7} minZoom={5} maxZoom={18} zoomControl={false}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          {cameras.filter((camera) => camera.lat != null && camera.lon != null).map((camera) => {
            const hasAlert = alertCameras.has(camera.camera_id);
            const selected = selectedCamera?.camera_id === camera.camera_id;
            const color = hasAlert ? "#ff5b68" : STATUS_COLORS[camera.status] || "#8191a7";
            return (
              <CircleMarker
                key={camera.camera_id}
                center={[camera.lat, camera.lon]}
                radius={selected ? 10 : hasAlert ? 7 : 5}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.88, weight: selected ? 3 : 1.5 }}
                eventHandlers={{ click: () => onSelectCamera(camera) }}
              >
                <Tooltip direction="top" offset={[0, -5]} opacity={1}>{camera.camera_id} · {camera.district}</Tooltip>
                <Popup>
                  <div className="map-popup">
                    <span className={`status-tag ${camera.status}`}>{camera.status}</span>
                    <strong>{camera.name}</strong>
                    <small>{camera.camera_id} · {camera.district}</small>
                    <div className="popup-grid"><span>{camera.vendor || "Unknown vendor"}</span><span>{camera.connectivity}</span></div>
                    <button disabled={!camera.whep_url && !camera.hls_url} onClick={() => onLiveView(camera)}>
                      <Play size={13} /> {camera.whep_url || camera.hls_url ? "Open live view" : "Preview unavailable"}
                    </button>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
          {route.length > 1 && <Polyline positions={route.map((hop) => [hop.lat, hop.lon])} pathOptions={{ color: "#6de1ff", weight: 3, dashArray: "8 8" }} />}
          {route.map((hop, index) => (
            <CircleMarker key={`${hop.camera_id}-${hop.ts}`} center={[hop.lat, hop.lon]} radius={6} pathOptions={{ color: "#06111f", fillColor: "#6de1ff", fillOpacity: 1, weight: 2 }}>
              <Tooltip>{index + 1}. {hop.district} · {formatTime(hop.ts)}</Tooltip>
            </CircleMarker>
          ))}
          <MapFocus camera={selectedCamera} route={route} />
        </MapContainer>

        <form className="route-control glass" onSubmit={traceVehicle}>
          <div className="route-title"><Route size={15} /><span>AI route reconstruction</span></div>
          <div className="route-input">
            <Search size={15} />
            <input value={plate} onChange={(event) => setPlate(event.target.value)} placeholder="Enter vehicle plate" aria-label="Vehicle plate" />
            <button type="submit">Trace</button>
          </div>
          {routeState && <small>{routeState}</small>}
        </form>

        <div className="map-provider glass"><Crosshair size={13} /> Free OpenStreetMap · no API key</div>
      </div>
    </section>
  );
}
