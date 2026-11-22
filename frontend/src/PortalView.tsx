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

// 5U's portal page sits behind Cloudflare's check for people, which a browser driven by a program never passes
// (round 120). So the person uses their own Chrome: the data to type, ready to copy; the page in a new tab of their
// browser; and the result pasted back here, read by code (total, days, R-...) and added to the deal. The agent,
// waiting in ask_person, goes on the moment the price is in.
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
      <textarea className="portal-paste" autoFocus rows={4} placeholder="paste the rate the page shows: total EUR, transit days, R-… reference"
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
    </div>
  );
}
