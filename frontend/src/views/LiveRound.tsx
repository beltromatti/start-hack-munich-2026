// Structure 2: the round that is running now. Clock first, one pipeline, the points still on the table.
import type { BoardState } from "../sim/board";
import { eur, fmtDur, type World } from "../sim/sim";

const STEPS = ["Read", "Price", "Quote", "Book"] as const;

export default function LiveRound({ w, b }: { w: World; b: BoardState }) {
  const c = w.cases[0];
  const left = Math.max(0, 360 - c.age);
  const step = c.stage === "booked" || c.stage === "accepted" ? 4 : c.age >= c.quoteAt ? 3 : c.stage === "waiting" ? 1 : c.age >= 3 ? 1 : 0;
  const timeLeftFull = Math.max(0, 120 - c.age);
  const quoted = c.age >= c.quoteAt;
  const prev = w.cases.slice(1, 9);
  const R = 88, C = 2 * Math.PI * R;

  return (
    <div className="lr">
      <section className="card lr-main">
        <div className="lr-clock">
          <svg viewBox="0 0 200 200" role="img" aria-label={`${fmtDur(left)} left`}>
            <circle cx="100" cy="100" r={R} className="ring-bg" />
            <circle cx="100" cy="100" r={R} className={`ring ${c.age > 120 ? "late" : ""}`} strokeDasharray={C} strokeDashoffset={C * (1 - left / 360)} />
          </svg>
          <div className="lr-clock-text"><span className="huge">{fmtDur(left)}</span><span className="sub">until it expires</span></div>
        </div>
        <div className="lr-info">
          <span className="label">Request #{c.round} · {c.customer}</span>
          <span className="lane-big">{c.origin} → {c.destination}</span>
          <span className="sub">{c.chargeableKg} kg chargeable · wants <b>{c.wants}</b>{c.reason ? ` · ${c.reason}` : ""}</span>
          <ol className="stepper">
            {STEPS.map((s, i) => <li key={s} className={i < step ? "done" : i === step ? "now" : ""}>{s}</li>)}
          </ol>
          <div className="on-table">
            <div><span className="label">Speed</span><b>{quoted ? `${c.points.accepted ? c.points.time : 0}/15` : timeLeftFull ? `${fmtDur(timeLeftFull)} for 15/15` : "below 15"}</b></div>
            <div><span className="label">Cost so far</span><b>${c.visibleSteps.reduce((a, s) => a + s.costUsd, 0).toFixed(4)}</b></div>
            <div><span className="label">Our quote</span><b>{quoted ? eur(c.quoteTotal) : "—"}</b></div>
          </div>
        </div>
      </section>

      <div className="lr-side">
        <section className="card">
          <span className="label">Rank {b.simulated && <em>sim</em>}</span>
          <span className="huge">{b.us?.rank ?? "—"}<small>/{b.rows.length}</small></span>
          <span className="sub">{b.leader && b.us && b.leader.team !== b.us.team ? `${Math.round(b.leader.total - b.us.total)} behind #1` : "leading"}</span>
        </section>
        <section className="card">
          <h2>Previous requests</h2>
          <ul className="prev">
            {prev.map((p) => (
              <li key={p.id}>
                <span className={`dot b-${p.points.accepted ? "green" : "red"}`} />
                <span>{p.origin}→{p.destination}</span>
                <b>{["accepted", "booked", "lost", "missed"].includes(p.stage) ? `${p.points.total}` : "…"}</b>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
