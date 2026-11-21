import { useMemo, useState } from "react";
import { Board, DealRow, Incident, post } from "./api";
import { STATUS, ago, who } from "./format";

const FILTERS: [string, (d: DealRow) => boolean][] = [
  ["All", () => true],
  ["Active", (d) => ["new", "pricing", "waiting_customer"].includes(d.status)],
  ["Quoted", (d) => d.status === "quoted"],
  ["Booked", (d) => d.status === "booked"],
  ["Flagged", (d) => !!d.flag],
];

export function DealList({ deals, selected, onSelect }: { deals: DealRow[]; selected: string | null; onSelect: (id: string) => void }) {
  const [filter, setFilter] = useState(0);
  const [q, setQ] = useState("");
  const shown = useMemo(() => deals.filter(FILTERS[filter][1]).filter((d) =>
    !q || `${d.customer} ${d.subject} ${d.route} ${d.booking}`.toLowerCase().includes(q.toLowerCase())), [deals, filter, q]);
  return (
    <aside className="deals">
      <div className="pane-head">
        <h3>Deals <span className="count">{deals.length}</span></h3>
        <input className="search" placeholder="Search customer, route, booking" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="chips">
          {FILTERS.map(([name, fn], i) => (
            <button key={name} className={i === filter ? "chip on" : "chip"} onClick={() => setFilter(i)}>
              {name} <span>{deals.filter(fn).length}</span>
            </button>
          ))}
        </div>
      </div>
      <ul className="deal-list">
        {shown.map((d) => {
          const st = STATUS[d.status] ?? { label: d.status, tone: "neutral" };
          return (
            <li key={d.id}>
              <button className={d.id === selected ? "row on" : "row"} onClick={() => onSelect(d.id)}>
                <div className="row-top">
                  <span className={`pill ${st.tone}`}>{st.label}</span>
                  {d.flag ? <span className={`flag ${d.flag}`} title={`flag ${d.flag}`} /> : null}
                  <span className="when">{ago(d.updated_at)}</span>
                </div>
                <div className="row-main">
                  <span className="name">{who(d.customer)}</span>
                  <span className="amount mono">{d.quote ?? ""}</span>
                </div>
                <div className="row-sub">
                  <span className="mono">{d.route && d.route !== "undefined-undefined" ? d.route.replace("-", " → ") : "–"}</span>
                  {d.weight_kg ? <span>{Number(d.weight_kg).toFixed(0)} kg</span> : null}
                  {d.response_seconds != null ? <span>{Math.round(d.response_seconds)} s</span> : null}
                  {d.booking ? <span className="mono">{d.booking}</span> : null}
                </div>
              </button>
            </li>
          );
        })}
        {!shown.length && <li className="empty">No deals yet. The first request arrives at 16:00, then one every 6 minutes.</li>}
      </ul>
    </aside>
  );
}

export function Incidents({ items, onChange }: { items: Incident[]; onChange: () => void }) {
  return (
    <>
      <div className="pane-head"><h3>Watcher <span className="count">{items.length} open</span></h3></div>
      <ul className="incidents">
        {items.map((i) => {
          const g = i.data.diagnosis ?? {};
          return (
            <li key={i.id} className={g.urgent ? "urgent" : ""}>
              <div className="inc-top">
                <span className={`pill ${g.urgent ? "bad" : "warn"}`}>{g.urgent ? "urgent" : "check"}</span>
                <span className="muted small">{ago(i.data.at)}{g.confidence ? ` · ${g.confidence}` : ""}</span>
                <button className="link" onClick={() => post(`/api/incidents/${i.id}/close`, {}).then(onChange)}>Close</button>
              </div>
              <div className="inc-what">{i.data.what}</div>
              {g.fix ? <div className="inc-fix"><span className="muted">Fix</span> {g.fix}{g.where ? <span className="muted"> · {g.where}</span> : null}</div> : null}
            </li>
          );
        })}
        {!items.length && <li className="empty">Nothing unusual: the market looks like the baseline.</li>}
      </ul>
    </>
  );
}

export function BoardPane({ board, team, children }: { board: Board | null; team: string; children?: React.ReactNode }) {
  const ranking = board?.public.ranking ?? [];
  const mine = board?.me.requests ?? [];
  return (
    <aside className="board">
      <div className="pane-head"><h3>Leaderboard <span className="count">{board?.public.overview?.rounds_sent ?? 0} rounds</span></h3></div>
      <table className="ranking">
        <thead><tr><th>#</th><th>Team</th><th className="num">Points</th><th className="num">Acc.</th><th className="num">Bk.</th></tr></thead>
        <tbody>
          {ranking.map((r) => (
            <tr key={r.team} className={r.name === team ? "us" : r.reference_team ? "ref" : ""}>
              <td>{r.rank}</td>
              <td>{r.team}{r.reference_team ? <span className="muted"> · ref</span> : null}</td>
              <td className="num mono">{r.total.toFixed(1)}</td>
              <td className="num">{r.accepted}/{r.answered}</td>
              <td className="num">{r.bookings}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pane-head"><h3>Our verdicts</h3></div>
      <ul className="verdicts">
        {mine.map((r, i) => (
          <li key={i}>
            <span className="mono">R{String(r.round_no ?? r.round ?? "?")}</span>
            <span className={`pill ${r.verdict === "accepted" ? "ok" : r.verdict === "rejected" || r.verdict === "no answer" ? "bad" : "neutral"}`}>{String(r.verdict ?? "")}</span>
            <span className="muted small">{typeof r.reason === "string" ? r.reason : ""}</span>
            <span className="num mono">{typeof r.points === "object" && r.points ? Object.values(r.points as Record<string, number>).reduce((a, b) => a + (Number(b) || 0), 0).toFixed(1) : ""}</span>
          </li>
        ))}
        {!mine.length && <li className="empty">Verdicts appear after the first rounds.</li>}
      </ul>
      {children}
    </aside>
  );
}
