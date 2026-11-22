import { useEffect, useRef, useState } from "react";
import { get, post } from "./api";

// When 5U's rate API answers 503 for some airlines, their prices are still on 5U's portal page, which asks people
// to pass a check. A person on the team reads them there by hand: this strip gives every field of that form ready
// to copy, reads the pasted result in code, and the agent quotes as soon as the prices are in (it waits for a
// person only while operator mode is on, up to wait_seconds after the customer's mail).
const PORTAL = "https://start-hack.5u.ai/portal/ui";

type Missing = { name: string; code: string | null; break_above: string | null };
type Needed = {
  deal: string; subject: string; customer: string; received_at: string; preference: string | null;
  origin: string; destination: string; gross_kg: string; volume_cbm: string | null; chargeable_kg: string;
  airlines: Missing[];
};
type Op = { on: boolean; wait_seconds: number; needed: Needed[] };
type Read = { total: string | null; days: string | null; rate_id: string | null; totals_seen: string[] };

function alarm(text: string) {
  try {
    const ctx = new AudioContext();
    [0, 0.3, 0.6].forEach((t) => {
      const o = ctx.createOscillator();
      o.frequency.value = 880;
      o.connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.18);
    });
  } catch { /* no audio */ }
  try {
    if ("Notification" in window && Notification.permission === "granted") new Notification("Portal price needed", { body: text });
  } catch { /* no notifications */ }
}

function Copy({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false);
  return (
    <button className="op-copy" title={`Copy ${label}`} onClick={() => {
      navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 1200); });
    }}>
      <span className="op-label">{label}</span><span className="mono">{value}</span><span className="op-ok">{done ? "copied" : "copy"}</span>
    </button>
  );
}

function Airline({ n, a, weight, note }: { n: Needed; a: Missing; weight: string; note?: string }) {
  const [pasted, setPasted] = useState("");
  const [read, setRead] = useState<Read | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  async function check(text: string) {
    setPasted(text);
    setMsg(null);
    if (!text.trim()) { setRead(null); return; }
    const r = await post<{ read: Read }>(`/api/deals/${n.deal}/portal_rate`, { airline: a.name, pasted: text, dry: true });
    setRead(r.read);
  }
  async function add() {
    try {
      await post(`/api/deals/${n.deal}/portal_rate`, { airline: a.name, pasted, weight_kg: weight, who: "Mattia" });
      setMsg("Added. The agent quotes as soon as the missing prices are in.");
    } catch (e) { setMsg(String(e)); }
  }
  return (
    <div className="op-air-box">
      <div className="op-step"><strong>{a.name}</strong>{note ? <span className="muted"> · {note}</span> : null}</div>
      <div className="op-fields">
        <Copy label="Origin" value={n.origin} />
        <Copy label="Destination" value={n.destination} />
        <Copy label="Weight kg" value={weight} />
        {n.volume_cbm ? <Copy label="Volume cbm" value={n.volume_cbm} /> : null}
        <Copy label="Airline" value={a.code ?? a.name} />
        <span className="muted op-key">Team key: your own (from .env or the browser's autofill)</span>
      </div>
      <textarea className="op-paste" rows={2} placeholder="Paste the page's result here (the 'Your rate' box): total, transit, rate_id are read for you"
        value={pasted} onChange={(e) => check(e.target.value)} />
      {read ? (
        <div className="op-read">
          <span>Total <strong className="mono">{read.total ?? "?"}{read.total ? " EUR" : ""}</strong></span>
          <span>Days <strong className="mono">{read.days ?? "?"}</strong></span>
          <span>Rate <strong className="mono">{read.rate_id ?? "?"}</strong></span>
          {read.totals_seen.length > 1 ? <span className="late">several amounts: {read.totals_seen.join(", ")}; paste only the result box</span> : null}
          <button className="primary" disabled={!read.total || !read.days} onClick={add}>Add price</button>
        </div>
      ) : null}
      {msg ? <div className="muted">{msg}</div> : null}
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
  useEffect(() => {
    for (const n of op?.needed ?? []) {
      if (!seen.current.has(n.deal)) {
        seen.current.add(n.deal);
        if (op?.on) alarm(`${n.origin}-${n.destination} ${n.gross_kg} kg: ${n.airlines.map((a) => a.code ?? a.name).join(", ")}`);
      }
    }
    document.title = op?.needed.length ? `(!) Portal price needed · ${title.current}` : title.current;
  }, [op]);
  if (!op) return null;
  const toggle = () => post<Op>("/api/operator", { on: !op.on }).then(setOp);
  const allow = () => { try { Notification.requestPermission(); } catch { /* none */ } };
  return (
    <section className={`operator${op.needed.length ? " needed" : ""}`}>
      <div className="op-head">
        <button className={op.on ? "primary" : ""} onClick={toggle}>{op.on ? "Operator mode on" : "Operator mode off"}</button>
        <span className="muted">
          {op.on ? `When 5U's rate API fails, the agent waits up to ${op.wait_seconds} s after the mail for the prices you read on 5U's portal page.`
            : "Turn on while you are at the desk: missing portal prices then wait for you (and an alarm rings)."}
        </span>
        <a className="op-link" href={PORTAL} target="_blank" rel="noreferrer">Open 5U's portal page</a>
        {"Notification" in window && Notification.permission !== "granted" ? <button onClick={allow}>Allow alerts</button> : null}
      </div>
      {op.needed.map((n) => {
        const left = Math.max(0, op.wait_seconds - Math.round((now - Date.parse(n.received_at)) / 1000));
        const w = Number(n.gross_kg).toFixed(2).replace(/\.00$/, "");
        return (
          <div key={n.deal} className="op-deal">
            <div className="op-title">
              <strong>{n.origin} → {n.destination}</strong>
              <span>{n.preference ?? "no preference"}</span>
              <span className="muted">{n.subject}</span>
              <span className={`op-left${left < 25 ? " late" : ""}`}>{left > 0 ? `${left} s left` : "time is up: the agent quotes without it"}</span>
            </div>
            <ol className="muted op-howto">
              <li>Open 5U's portal page, fill the form with the values below (click to copy), pass the check.</li>
              <li>Copy the result box and paste it under the airline: check total, days and rate, then Add price.</li>
            </ol>
            {n.airlines.map((a) => (
              <div key={a.name}>
                <Airline n={n} a={a} weight={w} />
                {a.break_above ? <Airline n={n} a={a} weight={a.break_above} note={`at the break above (${a.break_above} kg), often cheaper: only if there is time`} /> : null}
              </div>
            ))}
          </div>
        );
      })}
    </section>
  );
}
