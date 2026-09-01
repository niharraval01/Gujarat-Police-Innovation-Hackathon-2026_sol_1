import { useEffect, useRef, useState } from "react";
import { Radio, X } from "lucide-react";

export default function LiveViewModal({ camera, onClose }) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState("Connecting…");

  useEffect(() => {
    if (!camera) return undefined;
    const video = videoRef.current;
    let hls = null;
    let peer = null;
    let resourceUrl = null;
    let cancelled = false;

    async function connect() {
      try {
        if (camera.whep_url) {
          setStatus("Negotiating WebRTC/WHEP…");
          peer = new RTCPeerConnection();
          peer.addTransceiver("video", { direction: "recvonly" });
          peer.addTransceiver("audio", { direction: "recvonly" });
          peer.ontrack = (event) => { if (!cancelled) video.srcObject = event.streams[0]; };
          peer.onconnectionstatechange = () => {
            if (!cancelled) setStatus(peer.connectionState === "connected" ? "Live · WebRTC/WHEP" : `WebRTC · ${peer.connectionState}`);
          };
          const offer = await peer.createOffer();
          await peer.setLocalDescription(offer);
          const response = await fetch(camera.whep_url, { method: "POST", headers: { "Content-Type": "application/sdp" }, body: offer.sdp });
          if (!response.ok) throw new Error(`WHEP returned HTTP ${response.status}`);
          resourceUrl = response.headers.get("Location");
          await peer.setRemoteDescription({ type: "answer", sdp: await response.text() });
        } else if (camera.hls_url) {
          setStatus("Opening HLS fallback…");
          const { default: Hls } = await import("hls.js");
          if (Hls.isSupported()) {
            hls = new Hls({ maxBufferLength: 10, liveSyncDurationCount: 2 });
            hls.loadSource(camera.hls_url);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => { video.play().catch(() => {}); setStatus("Live · HLS"); });
            hls.on(Hls.Events.ERROR, (_, data) => { if (data.fatal) setStatus(`HLS error · ${data.details}`); });
          } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
            video.src = camera.hls_url;
            await video.play();
            setStatus("Live · native HLS");
          }
        } else {
          setStatus("No browser preview URL is available for this camera.");
        }
      } catch (error) {
        if (!cancelled) setStatus(`Connection failed · ${error.message}`);
      }
    }
    connect();

    return () => {
      cancelled = true;
      if (resourceUrl) fetch(resourceUrl, { method: "DELETE" }).catch(() => {});
      if (peer) peer.close();
      if (hls) hls.destroy();
      if (video) { video.srcObject = null; video.removeAttribute("src"); }
    };
  }, [camera]);

  if (!camera) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={`Live view ${camera.name}`}>
      <div className="live-modal">
        <div className="live-modal-head">
          <div><span className="eyebrow"><Radio size={12} /> On-demand stream</span><h2>{camera.name}</h2></div>
          <button onClick={onClose} aria-label="Close live view"><X /></button>
        </div>
        <div className="video-frame"><video ref={videoRef} autoPlay playsInline muted controls /></div>
        <div className="live-modal-foot"><span className="live-pill"><i /> {status}</span><small>{camera.camera_id} · Pull only while this window is open</small></div>
      </div>
    </div>
  );
}
