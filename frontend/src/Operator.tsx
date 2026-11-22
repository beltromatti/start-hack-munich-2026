import { useEffect, useRef, useState } from "react";
import { get, post } from "./api";

// When 5U's rate API answers 503 for some airlines, their prices are still on 5U's portal page, which asks people
// to pass a check. A person reads them there by hand: one compact card per request, the form's values to copy, and
// one paste box that reads airline, total, days and rate_id in code and adds the price at once.
const PORTAL = "https://start-hack.5u.ai/portal/ui";

type Missing = { name: string; code: string | null; break_above: string | null };
type Needed = {
  deal: string; subject: string; received_at: string; preference: string | null;
  origin: string; destination: string; gross_kg: string; volume_cbm: string | null; chargeable_kg: string;
  airlines: Missing[];
};
type Op = { on: boolean; wait_seconds: number; needed: Needed[] };
type Read = { total: string | null; days: string | null; rate_id: string | null; totals_seen: string[] };

function alarm(text: string) {
  try {
    const ctx = new AudioContext();
    [0, 0.25, 0.5].forEach((t) => {
      const o = ctx.createOscillator();
      o.frequency.value = 880;
      o.connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.15);
    });
  } catch { /* no audio */ }
  try {
    if ("Notification" in window && Notification.permission === "granted") new Notification("Portal price needed", { body: text });
  } catch { /* none */ }
}

function Chip({ label, value, big, active, onPick }: { label?: string; value: string; big?: boolean; active?: boolean; onPick?: () => void }) {
  const [done, setDone] = useState(false);
  return (
    <button className={`chip${big ? " big" : ""}${done ? " done" : ""}${active ? " active" : ""}`} title="Click to copy"
      onClick={() => { onPick?.(); navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 900); }); }}>
      {label ? <small>{label}</small> : null}<b>{value}</b>
    </button>
  );
}

function Card({ n, left }: { n: Needed; left: number }) {
  const [log, setLog] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [current, setCurrent] = useState<string | null>(n.airlines.length === 1 ? n.airlines[0].name : null);
  const kg = String(Number(n.gross_kg)).replace(/\.0+$/, "");
  async function paste(t: string) {
    setText(t);
    if (!t.trim()) return;
    const low = t.toLowerCase();
    const a = n.airlines.find((x) => (x.code && new RegExp(`\\b${x.code}\\b`).test(t)) || low.includes(x.name.toLowerCase()))
      ?? n.airlines.find((x) => x.name === current);
    const r = (await post<{ read: Read }>(`/api/deals/${n.deal}/portal_rate`, { airline: a?.name ?? "", pasted: t, dry: true })).read;
    if (!a || !r.total || !r.days || r.totals_seen.length > 1) {
      setLog((l) => [`✗ not added: ${!a ? "which airline? click its code first, then paste" : !r.total ? "no total in EUR" : !r.days ? "no transit days" : "several amounts, paste only the result box"}`, ...l]);
      return;
    }
    try {
      await post(`/api/deals/${n.deal}/portal_rate`, { airline: a.name, pasted: t, weight_kg: kg, who: "Mattia" });
      setLog((l) => [`✓ ${a.code ?? a.name} ${r.total} EUR · ${r.days} d · ${r.rate_id ?? "no rate_id"}`, ...l]);
      setText("");
    } catch (e) { setLog((l) => [`✗ ${String(e)}`, ...l]); }
  }
  return (
    <div className="op-card">
      <div className="op-line">
        <b className="op-lane">{n.origin} → {n.destination}</b>
        <span className="op-pref">{n.preference ?? "any"}</span>
        <span className={`op-left${left < 25 ? " late" : ""}`}>{left}s</span>
      </div>
      <div className="op-line">
        <Chip big label="Origin" value={n.origin} />
        <Chip big label="Destination" value={n.destination} />
        <Chip big label="Weight kg" value={kg} />
        {n.volume_cbm ? <Chip big label="Volume cbm" value={String(Number(n.volume_cbm))} /> : null}
        <span className="op-sep">Airline:</span>
        {n.airlines.map((a) => <Chip key={a.name} value={a.code ?? a.name} active={current === a.name} onPick={() => setCurrent(a.name)} />)}
      </div>
      <textarea className="op-paste" rows={2} value={text} placeholder="Paste the portal's result here: it is added at once"
        onChange={(e) => paste(e.target.value)} />
      {log.length ? <div className="op-log">{log.slice(0, 4).map((x, i) => <div key={i} className={x.startsWith("✓") ? "ok" : "late"}>{x}</div>)}</div> : null}
    </div>
  );
}

export function OperatorStrip() {
  const [op, setOp] = useState<Op | null>(null);
  const [now, setNow] = useState(Date.now());
  const seen = useRef<Set<string>>(new Set());
  const title = useRef(document.title);
  useEffect(() => {
    const load = () => get<Op>("/api/operator").then(setOp).catch(() => undefined);
    load();
    const t = setInterval(() => { load(); setNow(Date.now()); }, 1000);
    return () => clearInterval(t);
  }, []);
  const live = (op?.needed ?? [])
    .map((n) => ({ n, left: (op?.wait_seconds ?? 95) - Math.round((now - Date.parse(n.received_at)) / 1000) }))
    .filter((x) => x.left > 0);
  useEffect(() => {
    for (const { n } of live) {
      if (!seen.current.has(n.deal)) {
        seen.current.add(n.deal);
        if (op?.on) alarm(`${n.origin}-${n.destination} ${n.gross_kg} kg: ${n.airlines.map((a) => a.code ?? a.name).join(", ")}`);
      }
    }
    document.title = live.length ? `(!) Portal price · ${title.current}` : title.current;
  });
  if (!op) return null;
  const toggle = () => post<Op>("/api/operator", { on: !op.on }).then(setOp);
  return (
    <section className={`operator${live.length ? " needed" : ""}`}>
      <div className="op-line">
        <button className={`op-toggle${op.on ? " on" : ""}`} onClick={toggle}>{op.on ? "Operator ON" : "Operator OFF"}</button>
        <a className="op-link" href={PORTAL} target="_blank" rel="noreferrer">5U portal ↗</a>
        {"Notification" in window && Notification.permission !== "granted"
          ? <button className="chip" onClick={() => Notification.requestPermission()}>Allow alerts</button> : null}
        <span className="muted op-hint">{op.on ? (live.length ? "copy → portal → pass the check → paste the result below" : "waiting: an alarm rings when a price is needed")
          : "turn on when you are at the desk"}</span>
      </div>
      {live.map(({ n, left }) => <Card key={n.deal} n={n} left={left} />)}
    </section>
  );
}
