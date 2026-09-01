import { useState } from "react";
import { Bot, CornerDownLeft, Sparkles } from "lucide-react";
import { api } from "../lib/api";

const STARTERS = ["Which districts are highest risk?", "Show stolen vehicle alerts", "How is camera health?", "Trace GJ06AB1234"];

export default function AICopilot() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([{ role: "ai", text: "Ask me about routes, watchlist alerts, hotspots, or camera health. All analysis stays on this machine." }]);
  const [busy, setBusy] = useState(false);

  async function ask(value = question) {
    const clean = value.trim();
    if (!clean || busy) return;
    setQuestion("");
    setMessages((current) => [...current, { role: "user", text: clean }]);
    setBusy(true);
    try {
      const result = await api("/ai/copilot", { method: "POST", body: JSON.stringify({ question: clean }) });
      setMessages((current) => [...current, { role: "ai", text: result.answer, intent: result.intent }]);
    } catch (error) {
      setMessages((current) => [...current, { role: "ai", text: `I could not complete that analysis: ${error.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel copilot-panel" id="copilot">
      <div className="panel-heading">
        <div>
          <span className="eyebrow"><Sparkles size={12} /> Local intelligence</span>
          <h2>Sentinel Copilot</h2>
        </div>
        <span className="local-badge">ON-PREMISE</span>
      </div>
      <div className="chat-window">
        {messages.slice(-5).map((message, index) => (
          <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
            {message.role === "ai" && <Bot size={16} />}
            <div><p>{message.text}</p>{message.intent && <small>{message.intent.replaceAll("_", " ")}</small>}</div>
          </div>
        ))}
        {busy && <div className="message ai typing"><Bot size={16} /><span /><span /><span /></div>}
      </div>
      <div className="prompt-chips">
        {STARTERS.slice(0, 3).map((starter) => <button key={starter} onClick={() => ask(starter)}>{starter}</button>)}
      </div>
      <form className="copilot-input" onSubmit={(event) => { event.preventDefault(); ask(); }}>
        <input id="copilot-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask an operational question…" />
        <button type="submit" aria-label="Send question"><CornerDownLeft size={18} /></button>
      </form>
    </section>
  );
}
