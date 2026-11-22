import { useEffect, useRef, useState } from "react";
import { get, post } from "./api";


function Answer({ dealId, note }: { dealId: string; note: string }) {
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);
  const send = () => { if (text.trim()) post(`/api/deals/${dealId}/person_answer`, { text }).then(() => setSent(true)); };
  return (
    <div className="card portal">
      <div className="card-head"><span className="tag">The agent asks you</span></div>
      <div className="portal-question">{note}</div>
      {sent ? <div className="muted">Sent: the agent goes on with your answer.</div> : (
        <div className="portal-keys">
          <input autoFocus placeholder="your answer" value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
          <button className="primary" onClick={send}>Answer</button>
        </div>
      )}
    </div>
  );
}

// What the agent asked a person for (ask_person): its page live, or a question to answer.
export function PersonCard({ dealId, need }: { dealId: string; need: { kind: "page" | "answer"; note: string; airline: string | null } }) {
  return need.kind === "answer" ? <Answer dealId={dealId} note={need.note} /> : <PortalView dealId={dealId} note={need.note} airline={need.airline} />;
}

type Needed = { deal: string; origin: string; destination: string; gross_kg: string; volume_cbm: string | null;
  chargeable_kg: string; airlines: { name: string; code: string | null }[] };
type Read = { total: string | null; days: string | null; rate_id: string | null; totals_seen: string[] };

const PORTAL = "https://start-hack.5u.ai/portal/ui";

function Copy({ label, value }: { label: string; value: string | null | undefined }) {
  const [done, setDone] = useState(false);
  if (!value) return null;
  const copy = () => { navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 900); }); };
  return <button className="chip" onClick={copy} title="copy">{label} <b className="mono">{value}</b>{done ? " ✓" : ""}</button>;
}

// A real desktop Chrome is shared into the conversation. The external-browser path stays available when
// Cloudflare or the desktop session refuses it; either path feeds the same rate reader and waiting agent.
function SharedBrowser({ dealId }: { dealId: string }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState("");
  const [restart, setRestart] = useState(0);
  const [text, setText] = useState("");
  const [key, setKey] = useState("");
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
        if (!r.ok) throw new Error(`Shared browser unavailable (${r.status}). Retry or use the link below.`);
        const blob = await r.blob();
        if (!active) return;
        const next = URL.createObjectURL(blob);
        if (url) URL.revokeObjectURL(url);
        url = next; setSrc(next);
      } catch (e) { if (active) setError(String(e)); }
      if (active) timer = window.setTimeout(poll, 700);
    };
    setSrc(""); setError("");
    post(`/api/portal/${dealId}/open`, {}).then(() => { if (active) void poll(); })
      .catch((e) => { if (active) setError(String(e)); });
    return () => { active = false; abort.abort(); window.clearTimeout(timer); if (url) URL.revokeObjectURL(url); };
  }, [dealId, restart]);
  const send = () => { if (text) { input("type", { text }); setText(""); } };
  return <div className="portal-live">
    <div className="portal-keys">
      <button onClick={() => setRestart((n) => n + 1)}>Reconnect view</button>
      <button onClick={() => input("focus", {})}>Show on desktop</button>
      <button onClick={() => input("open", { reload: true })}>Reload portal</button>
    </div>
    {error ? <div role="alert" className="portal-hint">{error}</div> : null}
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
    <div className="portal-keys">
      <input aria-label="Team key" type="password" autoComplete="off" placeholder="Your team key" value={key} onChange={(e) => setKey(e.target.value)} />
      <button disabled={!key} onClick={() => { input("type", { into: "key", text: key }); setKey(""); }}>Type my key</button>
    </div>
    <div className="muted portal-hint">Complete the check and submit the form. The agent reads the resulting rate automatically.</div>
  </div>;
}

export function PortalView({ dealId, note, airline }: { dealId: string; note: string; airline: string | null }) {
  const [need, setNeed] = useState<Needed | null>(null);
  const [pasted, setPasted] = useState("");
  const [read, setRead] = useState<Read | null>(null);
  const [msg, setMsg] = useState("");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    get<{ needed: Needed[] }>("/api/operator").then((o) => setNeed(o.needed.find((x) => x.deal === dealId) ?? null)).catch(() => undefined);
  }, [dealId]);
  const onPaste = (t: string) => {
    setPasted(t); setMsg("");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (!t.trim()) { setRead(null); return; }
      post<{ read: Read }>(`/api/deals/${dealId}/portal_rate`, { pasted: t, dry: true }).then((r) => setRead(r.read)).catch(() => setRead(null));
    }, 250);
  };
  const add = () => {
    post<{ ok?: boolean }>(`/api/deals/${dealId}/portal_rate`, { pasted, airline: airline ?? need?.airlines?.[0]?.name ?? "", who: "person" })
      .then(() => setMsg("Added: the agent quotes with it now."))
      .catch((e) => setMsg(`Not added: ${String(e)}`));
  };
  const ready = read && read.total && read.days && read.rate_id;
  const airlines = need?.airlines?.length ? need.airlines : (airline ? [{ name: airline, code: null }] : []);
  return (
    <div className="card portal">
      <div className="card-head">
        <span className="tag">Your turn on 5U's portal</span>
        {airline ? <span className="mono">{airline}</span> : null}
      </div>
      <div className="muted">{note}</div>
      <div className="portal-chips">
        <Copy label="from" value={need?.origin} /><Copy label="to" value={need?.destination} />
        <Copy label="kg" value={need?.gross_kg} /><Copy label="cbm" value={need?.volume_cbm} />
        {airlines.map((a) => <Copy key={a.name} label="airline" value={a.code ? `${a.name} (${a.code})` : a.name} />)}
      </div>
      <SharedBrowser key={dealId} dealId={dealId} />
      <details>
      <summary>Check still blocked? Use your own browser and paste the result</summary>
      <div className="portal-steps">
        <div className="portal-step"><b>1</b> In your Chrome: <a className="primary-link" href={PORTAL} target="_blank" rel="noopener noreferrer">open 5U's portal ↗</a> (pass the check, close any pop-up)</div>
        <div className="portal-step"><b>2</b> Type these (click to copy):
          <div className="portal-chips">
            <Copy label="from" value={need?.origin} />
            <Copy label="to" value={need?.destination} />
            <Copy label="kg" value={need?.gross_kg} />
            <Copy label="cbm" value={need?.volume_cbm} />
            {airlines.map((a) => <Copy key={a.name} label="airline" value={a.code ? `${a.name} (${a.code})` : a.name} />)}
          </div>
        </div>
        <div className="portal-step"><b>3</b> Copy the page's result (select all, copy) and paste it here:</div>
      </div>
      <textarea className="portal-paste" rows={4} placeholder="paste the rate the page shows: total EUR, transit days, R-… reference"
        value={pasted} onChange={(e) => onPaste(e.target.value)} />
      {read ? (
        <div className="portal-read">
          <span>total <b className="mono">{read.total ?? (read.totals_seen.length ? `one of ${read.totals_seen.join(", ")}` : "?")}</b></span>
          <span>days <b className="mono">{read.days ?? "?"}</b></span>
          <span>rate <b className="mono">{read.rate_id ?? "?"}</b></span>
          <button className="primary" disabled={!ready} onClick={add}>Add to the deal</button>
        </div>
      ) : null}
      {msg ? <div className="muted">{msg}</div> : null}
      </details>
    </div>
  );
}
