// Option B: mail-first. Read every mail like the forwarder would, with the case facts beside the thread.
import { useState } from "react";
import { eur, fmtTime, type MailKind, type World } from "../sim/sim";
import { Dot, StagePill } from "../ui";

const KINDS: { id: MailKind | "all"; label: string }[] = [
  { id: "all", label: "All" }, { id: "rfq", label: "Customers" }, { id: "bid", label: "Carrier bids" }, { id: "quote", label: "Our quotes" },
];

export default function Inbox({ w }: { w: World }) {
  const [kind, setKind] = useState<MailKind | "all">("all");
  const [sel, setSel] = useState<string | null>(null);
  const mails = w.cases.slice(0, 25).flatMap((c) => c.visibleMails.map((m) => ({ ...m, c })))
    .filter((m) => kind === "all" || m.kind === kind)
    .sort((a, b) => b.c.start + b.t - (a.c.start + a.t));
  const current = w.cases.find((c) => c.id === sel) ?? w.cases[0];

  return (
    <div className="ib">
      <section className="panel ib-list">
        <div className="chips">
          {KINDS.map((k) => (
            <button key={k.id} className={`chip ${kind === k.id ? "active" : ""}`} onClick={() => setKind(k.id)}>{k.label}</button>
          ))}
        </div>
        <ul className="list">
          {mails.slice(0, 60).map((m) => (
            <li key={m.id}>
              <button className={`mail ${m.c.id === current.id ? "active" : ""}`} onClick={() => setSel(m.c.id)}>
                <span className="mail-top">
                  <span className={`kind k-${m.kind}`}>{m.kind === "rfq" ? "customer" : m.kind}</span>
                  <span className="from">{m.from === "us" ? "You" : m.from.split(" <")[0]}</span>
                  <span className="muted mono">{fmtTime(m.c.start + m.t)}</span>
                </span>
                <span className="subject">{m.subject}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel ib-thread">
        <div className="panel-head">
          <h2>{current.customer}</h2>
          <StagePill stage={current.stage} />
        </div>
        <div className="thread">
          {current.visibleMails.map((m) => (
            <article key={m.id} className={`msg ${m.from === "us" ? "out" : m.kind === "bid" ? "carrier" : "in"}`}>
              <header><b>{m.from === "us" ? "You (agent)" : m.from.split(" <")[0]}</b><span className="muted mono">{fmtTime(current.start + m.t)}</span></header>
              <p>{m.body}</p>
            </article>
          ))}
          {current.stage === "waiting" && <p className="muted typing">Collecting carrier bids…</p>}
        </div>
      </section>

      <aside className="panel ib-facts">
        <h2>Case {current.id}</h2>
        <dl className="facts">
          <dt>Lane</dt><dd>{current.origin} → {current.destination}</dd>
          <dt>Weight</dt><dd>{current.weightKg} kg · {current.volumeCbm} cbm</dd>
          <dt>Chargeable</dt><dd>{current.chargeableKg} kg</dd>
          <dt>Wants</dt><dd>{current.wants}</dd>
          <dt>Pickup</dt><dd>{current.pickupZone}</dd>
          <dt>Triage</dt><dd><Dot bucket={current.bucket} /> {current.reason ?? "green, no issues"}</dd>
        </dl>
        <h3>Offers</h3>
        <table className="bids">
          <tbody>
            {current.bids.map((b) => (
              <tr key={b.carrier} className={b.carrier === current.chosen.carrier ? "chosen" : ""}>
                <td>{b.carrier}<span className="muted"> · {b.source}</span></td>
                <td className="num">{current.age >= b.at ? eur(b.total) : "…"}</td>
                <td className="num muted">{b.transitDays} d</td>
              </tr>
            ))}
          </tbody>
        </table>
        {current.age >= current.quoteAt && (
          <div className="quote">
            <span>Quoted</span><b>{eur(current.quoteTotal)}</b>
            <span className="muted">best {eur(current.bestPrice)} · {((current.quoteTotal / current.bestPrice - 1) * 100).toFixed(1)} % above</span>
          </div>
        )}
      </aside>
    </div>
  );
}
