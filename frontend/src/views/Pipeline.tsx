// Option C: CRM. Every request as a row, grouped by where it stands; won, lost, points and margin at a glance.
import { eur, fmtDur, type View, type World } from "../sim/sim";
import { Dot, Kpi, StagePill } from "../ui";

const GROUPS: { title: string; test: (c: View) => boolean }[] = [
  { title: "Needs attention", test: (c) => c.bucket === "red" && !["booked", "accepted", "lost", "missed"].includes(c.stage) },
  { title: "In progress", test: (c) => ["received", "pricing", "waiting"].includes(c.stage) && c.bucket !== "red" },
  { title: "Quoted, waiting for customer", test: (c) => c.stage === "quoted" },
  { title: "Won", test: (c) => c.stage === "accepted" || c.stage === "booked" },
  { title: "Lost or missed", test: (c) => c.stage === "lost" || c.stage === "missed" },
];

export default function Pipeline({ w }: { w: World }) {
  const won = w.cases.filter((c) => c.stage === "accepted" || c.stage === "booked");
  const lost = w.cases.filter((c) => c.stage === "lost" || c.stage === "missed");
  return (
    <div className="pl">
      <div className="kpis">
        <Kpi label="Won" value={String(won.length)} hint={`${lost.length} lost or missed`} tone="good" />
        <Kpi label="Points" value={String(w.kpi.points)} />
        <Kpi label="Booked value" value={eur(won.reduce((a, c) => a + c.quoteTotal, 0))} />
        <Kpi label="Avg gap to best" value={`${(won.reduce((a, c) => a + (c.quoteTotal / c.bestPrice - 1), 0) / Math.max(1, won.length) * 100).toFixed(1)} %`} hint="must stay under 5 %" />
      </div>
      {GROUPS.map((g) => {
        const rows = w.cases.filter(g.test);
        if (!rows.length) return null;
        return (
          <section key={g.title} className="group">
            <h2>{g.title} <span className="muted">{rows.length}</span></h2>
            <div className="table" role="table">
              {rows.slice(0, 30).map((c) => {
                const done = ["accepted", "booked", "lost", "missed"].includes(c.stage);
                return (
                  <div className="tr" role="row" key={c.id}>
                    <Dot bucket={c.bucket} title={c.reason ?? "green"} />
                    <span className="mono muted">{c.id}</span>
                    <span className="cust">{c.customer}</span>
                    <span className="lane">{c.origin}→{c.destination}</span>
                    <span className="num">{c.chargeableKg} kg</span>
                    <span className="muted">{c.wants}</span>
                    <span className="num">{c.age >= c.quoteAt ? eur(c.quoteTotal) : "—"}</span>
                    <span className="num muted">{c.age >= c.quoteAt ? `+${((c.quoteTotal / c.bestPrice - 1) * 100).toFixed(1)} %` : ""}</span>
                    <span className="num">{done ? `${c.points.total} pt` : fmtDur(Math.min(c.age, 359))}</span>
                    <StagePill stage={c.stage} />
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
