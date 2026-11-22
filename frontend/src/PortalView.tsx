import { useEffect, useRef, useState } from "react";
import { BrowserActivity, post } from "./api";

// The UI observes the agent's existing page. Mounting or reconnecting never navigates or resets its work.
function SharedBrowser({ dealId }: { dealId: string }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [restart, setRestart] = useState(0);
  const [text, setText] = useState("");
  const img = useRef<HTMLImageElement>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const input = (action: string, payload: Record<string, unknown>) => {
    queue.current = queue.current.then(() => post<{ error?: string }>(`/api/portal/${dealId}/${action}`, payload))
      .then((r) => { if (r.error) throw new Error(r.error); setError(""); })
      .catch((e) => setError(String(e)));
  };
  useEffect(() => {
    let active = true, url = "", timer: number | undefined;
    const abort = new AbortController();
    const poll = async () => {
      try {
        const r = await fetch(`/api/portal/${dealId}/shot`, { signal: abort.signal, cache: "no-store" });
        if (!r.ok) throw new Error(`Waiting for the agent's browser (${r.status}). The view reconnects automatically.`);
        const blob = await r.blob();
        if (!active) return;
        const next = URL.createObjectURL(blob);
        if (url) URL.revokeObjectURL(url);
        url = next; setSrc(next); setConnectionError("");
      } catch (e) { if (active) setConnectionError(String(e)); }
      if (active) timer = window.setTimeout(poll, 700);
    };
    setSrc(""); setError(""); setConnectionError("");
    void poll();
    return () => { active = false; abort.abort(); window.clearTimeout(timer); if (url) URL.revokeObjectURL(url); };
  }, [dealId, restart]);
  const send = () => { if (text) { input("type", { text }); setText(""); } };
  return <div className="portal-live">
    <div className="portal-keys">
      <button onClick={() => setRestart((n) => n + 1)}>Reconnect view</button>
      <button onClick={() => input("focus", {})}>Show on desktop</button>
      <button onClick={() => input("open", { reload: true })}>Reload portal</button>
    </div>
    {error || connectionError ? <div role="alert" className="portal-hint">{error || connectionError}</div> : null}
    {!src && !error ? <div className="muted">Opening shared Chrome…</div> : null}
    {src ? <img ref={img} className="portal-shot" src={src} alt="Live 5U portal. Click to focus, then type or paste."
      tabIndex={0} draggable={false}
      onClick={(e) => {
        e.currentTarget.focus();
        const r = e.currentTarget.getBoundingClientRect();
        input("click", { x: (e.clientX - r.left) * e.currentTarget.naturalWidth / r.width,
          y: (e.clientY - r.top) * e.currentTarget.naturalHeight / r.height });
      }}
      onPaste={(e) => { e.preventDefault(); input("type", { text: e.clipboardData.getData("text") }); }}
      onKeyDown={(e) => {
        if ((e.metaKey || e.ctrlKey) && ["v", "c", "x"].includes(e.key.toLowerCase())) return;
        if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
          e.preventDefault(); input("type", { text: e.key });
        } else if (["Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"].includes(e.key)
          || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a")) {
          e.preventDefault(); input("type", { key: `${e.metaKey || e.ctrlKey ? "ControlOrMeta+" : ""}${e.shiftKey ? "Shift+" : ""}${e.key}` });
        }
      }} /> : null}
    <div className="portal-keys">
      <input aria-label="Text for the selected portal field" placeholder="Click a field above, then type or paste here" value={text}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
      <button onClick={send}>Type</button>
      <button onClick={() => input("type", { key: "Tab" })}>Tab</button>
      <button onClick={() => input("type", { key: "Enter" })}>Enter</button>
      <button onClick={() => input("scroll", { y: -500 })}>Scroll up</button>
      <button onClick={() => input("scroll", { y: 500 })}>Scroll down</button>
    </div>
    <div className="muted portal-hint">The agent operates this page, including the team key and checks. Click the view to interact.</div>
  </div>;
}


export function PortalView({ dealId, activity }: { dealId: string; activity: BrowserActivity }) {
  return <div className="card portal">
    <div className="card-head">
      <span className="tag">{activity.active ? "Agent on 5U's portal" : "Agent's portal session"}</span>
      {activity.airline ? <span className="mono">{activity.airline}</span> : null}
      <span className="muted">{activity.note} · {activity.action}</span>
    </div>
    {activity.action !== "close" ? <SharedBrowser key={dealId} dealId={dealId} /> : <p className="muted">Page closed by the agent.</p>}
  </div>;
}
