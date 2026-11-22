import { useEffect, useRef, useState } from "react";
import { get, post } from "./api";

// When 5U's rate API answers 503 for some airlines, their prices are still on 5U's portal page, which asks people
// to pass a check. A person on the team reads them there by hand and enters them here; the agent waits for them
// (up to 80 s after the customer's mail) only while operator mode is on.
const PORTAL = "https://start-hack.5u.ai/portal/ui";
const WAIT = 80;

type Missing = { name: string; code: string | null; break_above: string | null };
type Needed = { deal: string; subject: string; received_at: string; lane: string; weight_kg: string; volume_cbm: string | null; airlines: Missing[] };
type Op = { on: boolean; needed: Needed[] };

function beep() {
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    o.frequency.value = 880;
    o.connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.25);
  } catch { /* no audio */ }
}

function Row({ deal, a, weight }: { deal: string; a: Missing; weight: string }) {
  const [total, setTotal] = useState("");
  const [days, setDays] = useState("");
  const [rate, setRate] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  async function send() {
    setMsg(null);
    try {
      await post(`/api/deals/${deal}/portal_rate`, { airline: a.name, total, days, rate_id: rate, weight_kg: weight, who: "Mattia" });
      setMsg("added");
    } catch (e) { setMsg(String(e)); }
  }
  return (
    <div className="op-row">
      <span className="op-air"><strong>{a.name}</strong> {a.code ? <span className="mono">{a.code}</span> : null}</span>
      <input placeholder="total EUR" value={total} onChange={(e) => setTotal(e.target.value)} />
      <input placeholder="days" value={days} onChange={(e) => setDays(e.target.value)} />
      <input placeholder="rate_id" value={rate} onChange={(e) => setRate(e.target.value)} />
      <button className="primary" disabled={!total || !days} onClick={send}>Add</button>
      {msg ? <span className="muted">{msg}</span> : null}
    </div>
  );
}

export function OperatorStrip() {
  const [op, setOp] = useState<Op | null>(null);
  const [now, setNow] = useState(Date.now());
  const seen = useRef<Set<string>>(new Set());
  useEffect(() => {
    const load = () => get<Op>("/api/operator").then(setOp).catch(() => undefined);
    load();
    const t = setInterval(() => { load(); setNow(Date.now()); }, 1500);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    for (const n of op?.needed ?? []) {
      if (!seen.current.has(n.deal)) { seen.current.add(n.deal); if (op?.on) beep(); }
    }
  }, [op]);
  if (!op) return null;
  const toggle = () => post<Op>("/api/operator", { on: !op.on }).then(setOp);
  return (
    <section className={`operator${op.needed.length ? " needed" : ""}`}>
      <div className="op-head">
        <button className={op.on ? "primary" : ""} onClick={toggle}>{op.on ? "Operator mode on" : "Operator mode off"}</button>
        <span className="muted">
          {op.on ? "The agent waits up to 80 s after a request for prices you read on 5U's portal page." : "Turn on when you are at the desk: then missing portal prices wait for you."}
        </span>
        <a href={PORTAL} target="_blank" rel="noreferrer">Open 5U's portal page</a>
      </div>
      {op.needed.map((n) => {
        const left = Math.max(0, WAIT - Math.round((now - Date.parse(n.received_at)) / 1000));
        return (
          <div key={n.deal} className="op-deal">
            <div className="op-title">
              <strong>{n.lane}</strong> · {Number(n.weight_kg).toFixed(2)} kg{n.volume_cbm ? ` · ${n.volume_cbm} cbm` : ""} · {n.subject}
              <span className={`op-left${left < 20 ? " late" : ""}`}>{left} s left</span>
            </div>
            {n.airlines.map((a) => (
              <div key={a.name}>
                <Row deal={n.deal} a={a} weight={n.weight_kg} />
                {a.break_above ? <div className="muted op-break">also worth reading at {a.break_above} kg (the break above can be cheaper): enter it as its own line with that weight</div> : null}
              </div>
            ))}
          </div>
        );
      })}
    </section>
  );
}
