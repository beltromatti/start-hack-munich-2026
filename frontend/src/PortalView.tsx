import { ReactNode, useEffect, useRef, useState } from "react";
import { BrowserActivity, post } from "./api";

const ACTION: Record<string, string> = {
  open: "Opening the page", read: "Reading the page", look: "Looking at the page",
  act: "Interacting with the page", save_rate: "Saving the rate", close: "Page closed",
};
function pageLabel(url?: string) {
  try { const u = new URL(url ?? "https://start-hack.5u.ai/portal/ui"); return u.hostname + (u.pathname === "/" ? "" : u.pathname); }
  catch { return "5U portal"; }
}

// Observing or reconnecting never navigates the agent's page. Only explicit input changes it.
export function PortalView({ dealId, activity, url, children }: {
  dealId: string; activity: BrowserActivity; url?: string; children?: ReactNode;
}) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [restart, setRestart] = useState(0);
  const [text, setText] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const mounted = useRef(false);
  const closed = activity.action === "close";

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const input = (action: string, payload: Record<string, unknown>) => {
    queue.current = queue.current.then(async () => {
      if (!mounted.current) return;
      const result = await post<{ error?: string }>(`/api/portal/${dealId}/${action}`, payload);
      if (result.error) throw new Error(result.error);
      if (mounted.current) setError("");
    }).catch((e) => { if (mounted.current) setError(String(e)); });
  };
  useEffect(() => {
    if (closed) { setSrc(""); setConnectionError(""); return; }
    let active = true, current = "", pending = "", timer: number | undefined;
    const abort = new AbortController();
    const poll = async () => {
      try {
        const r = await fetch(`/api/portal/${dealId}/shot`, { signal: abort.signal, cache: "no-store" });
        if (!r.ok) throw new Error("Waiting for the browser. Reconnecting automatically…");
        const blob = await r.blob();
        if (!active) return;
        pending = URL.createObjectURL(blob);
        const frame = new Image(); frame.src = pending;
        await frame.decode();
        if (!active) return;
        const previous = current;
        current = pending; pending = "";
        setSrc(current); setConnectionError("");
        if (previous) URL.revokeObjectURL(previous);
      } catch (e) {
        if (pending) { URL.revokeObjectURL(pending); pending = ""; }
        if (active) setConnectionError(String(e).replace(/^Error: /, ""));
      }
      if (active) timer = window.setTimeout(poll, 700);
    };
    setSrc(""); setError(""); setConnectionError("");
    void poll();
    return () => {
      active = false; abort.abort(); window.clearTimeout(timer);
      if (current) URL.revokeObjectURL(current);
      if (pending) URL.revokeObjectURL(pending);
    };
  }, [dealId, restart, closed]);
  useEffect(() => {
    if (!menuOpen) return;
    const dismiss = (e: PointerEvent) => { if (!menu.current?.contains(e.target as Node)) setMenuOpen(false); };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); setMenuOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", dismiss); document.removeEventListener("keydown", escape); };
  }, [menuOpen]);
  const command = (fn: () => void) => { fn(); setMenuOpen(false); };
  const send = () => { if (text) { input("type", { text }); setText(""); setMenuOpen(false); } };

  return <section className="portal" aria-label="Agent browser">
    <header className="portal-bar">
      <svg className="portal-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
        <rect x="2" y="3" width="16" height="14" rx="3" /><path d="M2 7h16M5 5h.1M8 5h.1" />
      </svg>
      <div className="portal-address" title={pageLabel(url)}>{pageLabel(url)}</div>
      <span className={`portal-state${activity.active ? " is-live" : ""}`}><span className="pulse" />{activity.active ? "Live" : closed ? "Closed" : "Ready"}</span>
      <div className="portal-menu" ref={menu}>
        <button className="portal-more" ref={trigger} aria-label="Browser options" aria-expanded={menuOpen}
          aria-controls={`browser-options-${dealId}`} onClick={() => setMenuOpen((open) => !open)}>⋯</button>
        {menuOpen ? <div className="portal-menu-panel" id={`browser-options-${dealId}`}>
          <span className="portal-menu-label">Browser controls</span>
          <button disabled={closed} onClick={() => command(() => setRestart((n) => n + 1))}>Reconnect view</button>
          <button disabled={closed} onClick={() => command(() => input("focus", {}))}>Show on desktop</button>
          <button disabled={closed} onClick={() => command(() => input("open", { reload: true }))}>Reload portal</button>
          {children ? <button onClick={() => command(() => setShowSteps((shown) => !shown))}>{showSteps ? "Hide" : "Show"} tool activity</button> : null}
          <div className="portal-menu-input">
            <label htmlFor={`browser-text-${dealId}`}>Type into the selected field</label>
            <input id={`browser-text-${dealId}`} disabled={closed} placeholder="Text or paste…" value={text}
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
            <div className="portal-shortcuts">
              <button disabled={closed || !text} onClick={send}>Type</button>
              <button disabled={closed} onClick={() => command(() => input("type", { key: "Tab" }))}>Tab</button>
              <button disabled={closed} onClick={() => command(() => input("type", { key: "Enter" }))}>Enter</button>
            </div>
            <div className="portal-shortcuts">
              <button disabled={closed} onClick={() => command(() => input("scroll", { y: -500 }))}>Scroll up</button>
              <button disabled={closed} onClick={() => command(() => input("scroll", { y: 500 }))}>Scroll down</button>
            </div>
          </div>
        </div> : null}
      </div>
    </header>
    {error || connectionError ? <div role="status" className="portal-error">{error || connectionError}</div> : null}
    <div className="portal-viewport">
      {closed ? <div className="portal-placeholder">Page closed by the agent.</div>
        : !src ? <div className="portal-placeholder"><span className="pulse" /> Connecting to the browser…</div>
        : <img className="portal-shot" src={src} alt="Live browser page. Click, type or paste to interact."
          tabIndex={0} draggable={false}
          onClick={(e) => {
            e.currentTarget.focus({ preventScroll: true });
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
          }} />}
    </div>
    <footer className="portal-foot"><span>{activity.active ? ACTION[activity.action] ?? "Working in the browser" : closed ? "Session finished" : "Agent's browser session"}</span><span>Click to interact</span></footer>
    {showSteps ? <div className="portal-activity">{children}</div> : null}
  </section>;
}
