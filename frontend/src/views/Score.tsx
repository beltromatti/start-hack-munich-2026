// Structure 1: the score equation. One number, the three levers, where we leak points, round by round.
import type { BoardState } from "../sim/board";
import type { World } from "../sim/sim";

const LEVERS = [
  { key: "accuracy", label: "Price accuracy", max: 45, how: "full at the best price, 0 beyond +5 %" },
  { key: "cost", label: "LLM cost", max: 40, how: "full at $0, zero at $0.10 per quote" },
  { key: "time", label: "Speed", max: 15, how: "full within 2:00, zero at 6:00" },
] as const;

export default function Score({ w, b }: { w: World; b: BoardState }) {
  const done = w.cases.filter((c) => ["accepted", "booked", "lost", "missed"].includes(c.stage));
  const n = Math.max(1, done.length);
  const got = (k: "accuracy" | "cost" | "time") => done.reduce((a, c) => a + c.points[k], 0);
  const rejected = done.filter((c) => !c.points.accepted).length;
  const leaks = [
    ...LEVERS.map((l) => ({ label: l.label, lost: done.filter((c) => c.points.accepted).length * l.max - got(l.key) })),
    { label: "Rejected (> 5 % above best)", lost: rejected * 100 },
  ].sort((a, x) => x.lost - a.lost);
  const total = done.reduce((a, c) => a + c.points.total, 0);
  const last = done.slice(0, 24).reverse();

  return (
    <div className="sc">
      <section className="card hero">
        <div>
          <span className="label">Our points</span>
          <span className="huge">{total.toLocaleString("de-DE")}</span>
          <span className="sub">{Math.round(total / n)} of 100 per request · {done.length} requests scored</span>
        </div>
        <div className="hero-rank">
          <span className="label">Rank {b.simulated && <em>sim</em>}</span>
          <span className="huge">{b.us ? b.us.rank : "—"}<small>/{b.rows.length}</small></span>
          <span className="sub">{b.above ? `${Math.round(b.above.total - (b.us?.total ?? 0))} behind ${b.above.team}` : "leading"}</span>
        </div>
      </section>

      <section className="card">
        <h2>Where the points come from</h2>
        <div className="levers">
          {LEVERS.map((l) => {
            const avg = got(l.key) / Math.max(1, done.length - rejected);
            return (
              <div className="lever" key={l.key}>
                <div className="lever-top"><span>{l.label}</span><b>{avg.toFixed(1)}<small> / {l.max}</small></b></div>
                <div className="meter"><i style={{ width: `${(avg / l.max) * 100}%` }} /></div>
                <span className="sub">{l.how}</span>
              </div>
            );
          })}
        </div>
        <p className="gate"><span className={`dot ${rejected ? "b-red" : "b-green"}`} /> Gate: only quotes within 5 % of the best price score. {rejected} of {done.length} rejected.</p>
      </section>

      <div className="sc-row">
        <section className="card">
          <h2>Biggest leak</h2>
          <ol className="leaks">
            {leaks.map((l, i) => (
              <li key={l.label} className={i === 0 ? "top" : ""}><span>{l.label}</span><b>−{Math.round(l.lost)}</b></li>
            ))}
          </ol>
        </section>
        <section className="card grow">
          <h2>Last {last.length} requests</h2>
          <div className="rounds">
            {last.map((c) => (
              <div className="round" key={c.id} title={`#${c.round} ${c.origin}→${c.destination}: ${c.points.total} pt`}>
                {c.points.accepted ? <>
                  <i className="seg-time" style={{ height: `${c.points.time}%` }} />
                  <i className="seg-cost" style={{ height: `${c.points.cost}%` }} />
                  <i className="seg-acc" style={{ height: `${c.points.accuracy}%` }} />
                </> : <i className="seg-miss" style={{ height: "100%" }} />}
              </div>
            ))}
          </div>
          <div className="legend"><span><i className="seg-acc" />accuracy</span><span><i className="seg-cost" />cost</span><span><i className="seg-time" />speed</span><span><i className="seg-miss" />rejected / missed</span></div>
        </section>
      </div>
    </div>
  );
}
