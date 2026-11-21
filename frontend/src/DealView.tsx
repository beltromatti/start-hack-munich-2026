import { useMemo, useState } from "react";
import { Deal, Item, Option, post } from "./api";
import { STATUS, clock, parseJSON, usd, who } from "./format";

type Step =
  | { k: "mail"; from: string; at: string; subject: string; body: string }
  | { k: "said"; who: string; text: string; system: boolean }
  | { k: "nudge"; text: string }
  | { k: "tool"; name: string; args: Record<string, any>; out: Record<string, any> | null }
  | { k: "journal"; text: string };

const MAIL = /New mail in this thread: id (\d+), from (\S+), at (\S+)\nSubject: (.*)\n\n([\s\S]*)$/;

function steps(items: Item[]): Step[] {
  const outputs = new Map<string, Record<string, any> | null>();
  for (const it of items) if (it.type === "function_call_output" && it.call_id) outputs.set(it.call_id, parseJSON(it.output));
  const out: Step[] = [];
  for (const it of items) {
    if (it.role === "user" && typeof it.content === "string") {
      const c = it.content;
      if (c.startsWith("(system)")) { out.push({ k: "nudge", text: c.replace("(system) ", "") }); continue; }
      const m = c.match(MAIL);
      if (m) { out.push({ k: "mail", from: m[2], at: m[3], subject: m[4], body: m[5].trim() }); continue; }
      for (const part of c.split(/\n\n(?=Message from |Update from the system)/)) {
        const sys = part.match(/Update from the system \(([^)]*)\): ([\s\S]*)/);
        const op = part.match(/Message from (.+?) \(a person on our team, [^)]*\): ([\s\S]*)/);
        if (sys) out.push({ k: "said", who: "System", text: sys[2], system: true });
        else if (op) out.push({ k: "said", who: op[1], text: op[2], system: false });
      }
    } else if (it.type === "function_call" && it.name) {
      out.push({ k: "tool", name: it.name, args: parseJSON(it.arguments) ?? {}, out: outputs.get(it.call_id ?? "") ?? null });
    } else if (it.type === "message" && Array.isArray(it.content)) {
      const text = (it.content as { type: string; text?: string }[]).map((c) => c.text ?? "").join("").trim();
      if (text) out.push({ k: "journal", text });
    }
  }
  return out;
}

const KIND: Record<string, string> = {
  quote: "Quote", question: "Question", reply: "Reply", booking_confirmation: "Booking confirmation",
  tracking_answer: "Tracking answer", decline: "Decline", other: "Mail",
};

function Options({ out }: { out: Record<string, any> }) {
  const options: Option[] = out.options ?? [];
  if (out.missing) return <p className="muted">Missing to price it: {out.missing.join("; ")}</p>;
  if (!options.length) return <p className="muted">No options yet{out.still_waiting_for?.length ? `, waiting for ${out.still_waiting_for.length} carriers` : ""}.</p>;
  return (
    <table className="options">
      <thead><tr><th></th><th>Airline</th><th>Transit</th><th>Pickup</th><th>Source</th><th className="num">All-in</th></tr></thead>
      <tbody>
        {options.map((o) => (
          <tr key={o.option} className={o.option === out.recommended ? "rec" : ""}>
            <td className="mono">{o.option}</td>
            <td>{o.airline}{o.carrier_note ? <span className="hint" title={o.carrier_note}> ⓘ</span> : null}</td>
            <td>{o.transit_days} d</td>
            <td>{o.pickup ? `${o.pickup.trucker} · ${o.pickup.pickup_hours} h` : "–"}</td>
            <td className="muted">{o.source}</td>
            <td className="num mono">{o.total}</td>
          </tr>
        ))}
      </tbody>
      {out.still_waiting_for?.length ? <caption>Still waiting for {out.still_waiting_for.join(", ")}</caption> : null}
    </table>
  );
}

function ToolStep({ s }: { s: Extract<Step, { k: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const { name, args, out } = s;
  const err = out && "error" in out ? String(out.error) : null;
  if (name === "send_mail") {
    return (
      <div className="card out">
        <div className="card-head">
          <span className="tag">{KIND[args.kind] ?? args.kind}</span>
          <span>to {out?.to ?? "customer"}</span>
          {out?.recorded_quote ? <span className="amount mono">{out.recorded_quote}</span> : null}
        </div>
        {err ? <p className="error">{err}</p> : <pre className="body">{args.body}</pre>}
      </div>
    );
  }
  let title = name, detail: JSX.Element | null = null;
  if (name === "get_offers") {
    const sh = args.shipment;
    title = sh ? `Priced ${sh.origin_airport ?? (sh.pickup?.postcode ? `pickup ${sh.pickup.postcode}` : "?")} → ${sh.destination_airport ?? "?"}, ${sh.weight?.value ?? "?"} ${sh.weight?.unit ?? ""} · ${args.preference}`
      : "Waited for the remaining carriers";
    if (out) {
      const n = (out.options ?? []).length;
      title += n ? ` · ${n} options, recommended ${out.recommended}` : "";
      detail = <Options out={out} />;
    }
  } else if (name === "book") {
    title = out?.status ? `Booked ${args.option_id}: ${out.booking_reference ?? out.team_reference} (${out.status}, via ${out.via})` : `Booking ${args.option_id}`;
  } else if (name === "crm") {
    title = `Searched the CRM for “${args.query}” · ${out?.total_matches ?? 0} found`;
  } else if (name === "deal") {
    title = "Read the deal";
  } else if (name === "carrier_status") {
    title = out?.carrier_reply ? "Airline status" : "Asked the airline for the status";
    detail = out?.carrier_reply ? <pre className="body quote">{out.carrier_reply}</pre> : null;
  } else if (name === "mail_carrier") {
    title = `Wrote to ${args.to}: ${args.subject}`;
    detail = <pre className="body">{args.body}</pre>;
  } else if (name === "note") {
    return <div className={`note flag-${args.flag}`}><span className="dot" />{args.text}</div>;
  } else if (name === "no_reply") {
    title = `No reply needed: ${args.reason}`;
  }
  return (
    <div className={`step${err ? " failed" : ""}`}>
      <button className="step-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="tool">{name}</span><span className="title">{title}</span>
        {detail || err ? <span className="chev">{open ? "▾" : "▸"}</span> : null}
      </button>
      {open && (err ? <p className="error">{err}</p> : detail)}
    </div>
  );
}

export function DealView({ deal, onSent }: { deal: Deal; onSent: () => void }) {
  const items = deal.session?.items ?? [];
  const list = useMemo(() => steps(items), [items]);
  const d = deal.data;
  const req = d.request ?? {};
  const st = STATUS[deal.status] ?? { label: deal.status, tone: "neutral" };
  const [mode, setMode] = useState<"agent" | "customer">("agent");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send() {
    if (!text.trim()) return;
    setBusy(true); setErr(null);
    try {
      if (mode === "agent") await post(`/api/sessions/session-${d.root}/message`, { text, who: "Mattia" });
      else await post(`/api/deals/${deal.id}/reply`, { body: text, kind: "reply" });
      setText(""); onSent();
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  return (
    <section className="deal">
      <header className="deal-head">
        <div>
          <div className="eyebrow">{who(d.customer)} · <span className="mono">{d.customer}</span></div>
          <h2>{d.subject || "(no subject)"}</h2>
          <div className="facts">
            <span className={`pill ${st.tone}`}>{st.label}</span>
            {req.origin ? <span className="mono">{String(req.origin)} → {String(req.destination)}</span> : null}
            {req.chargeable_kg ? <span>{Number(req.chargeable_kg).toFixed(0)} kg chargeable</span> : null}
            {req.pickup_zone ? <span>pickup zone {String(req.pickup_zone)}</span> : null}
            {d.preference ? <span>{d.preference}</span> : null}
            {d.flag ? <span className={`pill ${d.flag === "red" ? "bad" : "warn"}`}>flag {d.flag}</span> : null}
          </div>
        </div>
        <dl className="deal-kpis">
          <div><dt>Quote</dt><dd className="mono">{d.quote?.amount ?? "–"}</dd></div>
          <div><dt>Reply in</dt><dd>{d.quote ? `${Math.round(d.quote.response_seconds)} s` : "–"}</dd></div>
          <div><dt>Booking</dt><dd className="mono">{d.booking?.booking_reference ?? (d.booking ? d.booking.status : "–")}</dd></div>
          <div><dt>Model cost</dt><dd>{usd(deal.usage.cost_usd)}</dd></div>
        </dl>
      </header>

      {d.booking?.carrier_status ? (
        <div className="banner"><strong>Latest airline status</strong> · {d.booking.carrier_status.at}<pre className="body">{d.booking.carrier_status.text}</pre></div>
      ) : null}

      <ol className="timeline">
        {list.map((s, i) => (
          <li key={i} className={`t-${s.k}`}>
            {s.k === "mail" && (
              <div className="card in">
                <div className="card-head"><span className="tag">Mail in</span><span className="mono">{s.from}</span><span className="muted">{clock(s.at)}</span></div>
                <div className="subject">{s.subject}</div>
                <pre className="body">{s.body}</pre>
              </div>
            )}
            {s.k === "said" && <div className={`said${s.system ? " system" : ""}`}><strong>{s.who}</strong> {s.text}</div>}
            {s.k === "nudge" && <div className="said system"><strong>System</strong> {s.text}</div>}
            {s.k === "tool" && <ToolStep s={s} />}
            {s.k === "journal" && <div className="journal">{s.text}</div>}
          </li>
        ))}
        {deal.session?.status === "running" && <li className="t-live"><span className="pulse" /> working…</li>}
        {!list.length && <li className="muted">No session yet.</li>}
      </ol>

      <div className="composer">
        <div className="seg" role="tablist">
          <button role="tab" aria-selected={mode === "agent"} onClick={() => setMode("agent")}>Tell the agent</button>
          <button role="tab" aria-selected={mode === "customer"} onClick={() => setMode("customer")}>Reply to the customer</button>
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          placeholder={mode === "agent" ? "An instruction for this deal: it is followed, and wins over earlier decisions." : "Your own mail to the customer, sent in this thread."}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }} />
        <div className="composer-foot">
          {err ? <span className="error">{err}</span> : <span className="muted">⌘↵ to send</span>}
          <button className="primary" disabled={busy || !text.trim()} onClick={send}>{mode === "agent" ? "Send to agent" : "Send mail"}</button>
        </div>
      </div>
    </section>
  );
}
