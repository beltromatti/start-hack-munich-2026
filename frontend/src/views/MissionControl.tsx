// Option A: technical. Every request is a session; follow it step by step, see cost and latency, spot trouble.
import { useState } from "react";
import { fmtDur, fmtTime, type World } from "../sim/sim";
import { Dot, Kpi, StagePill } from "../ui";

export default function MissionControl({ w }: { w: World }) {
  const [sel, setSel] = useState<string | null>(null);
  const current = w.cases.find((c) => c.id === sel) ?? w.cases[0];
  const k = w.kpi;
  const attention = w.cases.filter((c) => c.bucket !== "green").slice(0, 6);
  const portalDown = w.cases.some((c) => c.age < 3600 && c.reason?.includes("503"));

  return (
    <div className="mc">
      <div className="kpis">
        <Kpi label="Points" value={String(k.points)} hint={`${k.rounds} rounds`} />
        <Kpi label="Accepted" value={`${Math.round(k.acceptedRate * 100)} %`} hint="within 5 % of best" tone={k.acceptedRate > 0.8 ? "good" : "warn"} />
        <Kpi label="Avg response" value={fmtDur(k.avgResponse)} hint="full points ≤ 2:00" tone={k.avgResponse <= 120 ? "good" : "warn"} />
        <Kpi label="LLM cost / quote" value={`$${k.costPerQuote.toFixed(4)}`} hint="zero points at $0.10" tone={k.costPerQuote < 0.01 ? "good" : "warn"} />
        <Kpi label="Next RFQ" value={fmtDur(w.nextRfqIn)} hint={`${k.open} open now`} />
      </div>

      <div className="mc-grid">
        <section className="panel">
          <h2>Sessions</h2>
          <ul className="list">
            {w.cases.slice(0, 40).map((c) => (
              <li key={c.id}>
                <button className={`session ${c.id === current.id ? "active" : ""}`} onClick={() => setSel(c.id)}>
                  <Dot bucket={c.bucket} />
                  <span className="mono">#{c.round}</span>
                  <span className="lane">{c.origin}→{c.destination}</span>
                  <StagePill stage={c.stage} />
                  <span className="muted mono">{fmtDur(Math.min(c.age, 5999))}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Session #{current.round} · {current.customer}</h2>
            <StagePill stage={current.stage} />
          </div>
          <p className="sub">{current.origin} → {current.destination} · {current.weightKg} kg · {current.volumeCbm} cbm · chargeable {current.chargeableKg} kg · wants <b>{current.wants}</b></p>
          <ol className="timeline">
            {current.visibleSteps.map((s, i) => (
              <li key={i} className={`lvl-${s.level}`}>
                <span className="mono muted">+{fmtDur(s.t)}</span>
                <span className={`agent a-${s.agent}`}>{s.agent}</span>
                <span className="text">{s.label}</span>
                <span className="mono muted">{s.ms} ms</span>
                <span className="mono muted">{s.costUsd ? `$${s.costUsd.toFixed(4)}` : "—"}</span>
              </li>
            ))}
            {current.stage === "waiting" && <li className="lvl-live"><span /><span className="agent">carrier</span><span className="text">Waiting for email bids…</span></li>}
          </ol>
          {["accepted", "booked", "lost", "missed"].includes(current.stage) && (
            <div className="score">
              <span>Score</span>
              <b>{current.points.total}</b>
              <span className="muted">accuracy {current.points.accuracy}/45 · cost {current.points.cost}/40 · time {current.points.time}/15</span>
            </div>
          )}
        </section>

        <aside className="stack">
          <section className="panel">
            <h2>Needs attention</h2>
            <ul className="list">
              {attention.map((c) => (
                <li key={c.id}>
                  <button className="attn" onClick={() => setSel(c.id)}>
                    <Dot bucket={c.bucket} />
                    <span><b>#{c.round}</b> {c.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section className="panel">
            <h2>Systems</h2>
            <ul className="health">
              <li><Dot bucket="green" /> Mailbox <span className="muted">polling every 2 s</span></li>
              <li><Dot bucket={portalDown ? "yellow" : "green"} /> Rate portal <span className="muted">{portalDown ? "503 on some lanes" : "ok · 41 reads left"}</span></li>
              <li><Dot bucket="green" /> LLM gateway <span className="muted">ok</span></li>
              <li><Dot bucket="green" /> Leaderboard <span className="muted">synced {fmtTime(w.now - 40)}</span></li>
            </ul>
          </section>
        </aside>
      </div>
    </div>
  );
}
