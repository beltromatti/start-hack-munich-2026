// Structure 3: disruptions first (our angle). Green runs alone; show only what broke, why, and whether it repeats.
import type { BoardState } from "../sim/board";
import { fmtTime, type World } from "../sim/sim";

export default function Exceptions({ w, b }: { w: World; b: BoardState }) {
  const recent = w.cases.slice(0, 30);
  const count = (x: string) => recent.filter((c) => c.bucket === x).length;
  const reasons = new Map<string, { n: number; last: number; red: boolean }>();
  for (const c of recent) if (c.reason) {
    const r = reasons.get(c.reason) ?? { n: 0, last: 0, red: c.bucket === "red" };
    reasons.set(c.reason, { n: r.n + 1, last: Math.max(r.last, c.start), red: r.red || c.bucket === "red" });
  }
  const list = [...reasons.entries()].sort((a, x) => x[1].n - a[1].n);
  const hours = new Map<number, { n: number; ok: number }>();
  for (const c of w.cases) {
    if (!["accepted", "booked", "lost", "missed"].includes(c.stage)) continue;
    const h = Math.floor(c.start / 3600);
    const v = hours.get(h) ?? { n: 0, ok: 0 };
    hours.set(h, { n: v.n + 1, ok: v.ok + (c.points.accepted ? 1 : 0) });
  }
  const hourList = [...hours.entries()].sort((a, x) => a[0] - x[0]).slice(-8);

  return (
    <div className="ex">
      <section className="ex-buckets">
        <div className="card bucket green"><span className="huge">{count("green")}</span><span>Green · runs alone</span></div>
        <div className="card bucket yellow"><span className="huge">{count("yellow")}</span><span>Yellow · checked by the watcher</span></div>
        <div className="card bucket red"><span className="huge">{count("red")}</span><span>Red · reasoning model, human can step in</span></div>
        <div className="card bucket rank"><span className="huge">{b.us?.rank ?? "—"}<small>/{b.rows.length}</small></span><span>Rank {b.simulated ? "(sim)" : ""}</span></div>
      </section>

      <div className="ex-row">
        <section className="card grow">
          <h2>What broke, last 30 requests</h2>
          <ul className="reasons">
            {list.length === 0 && <li className="sub">Nothing. Everything ran green.</li>}
            {list.map(([reason, v]) => (
              <li key={reason}>
                <span className={`dot ${v.red ? "b-red" : "b-yellow"}`} />
                <span className="reason">{reason}</span>
                <span className="sub">last {fmtTime(v.last)}</span>
                <b>×{v.n}</b>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>Accepted per hour</h2>
          <p className="sub">A drop means the setup changed. 5U changes it about once an hour, unannounced.</p>
          <div className="hours">
            {hourList.map(([h, v]) => {
              const rate = v.n ? v.ok / v.n : 0;
              return (
                <div className="hour" key={h} title={`${Math.round(rate * 100)} % accepted`}>
                  <i className={rate < 0.8 ? "low" : ""} style={{ height: `${Math.max(6, rate * 100)}%` }} />
                  <span className="sub">{fmtTime(h * 3600).slice(0, 2)}h</span>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
