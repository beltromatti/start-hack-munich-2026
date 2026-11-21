import { useCallback, useEffect, useState } from "react";
import { Board, Deal, DealRow, Health, Incident, Usage, get } from "./api";
import { DealView } from "./DealView";
import { BoardPane, DealList, Incidents } from "./Side";
import { usd } from "./format";

const TEAM = "start-milan";

function usePoll<T>(path: string | null, ms: number): [T | null, boolean, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [ok, setOk] = useState(true);
  const load = useCallback(() => {
    if (!path) return;
    get<T>(path).then((d) => { setData(d); setOk(true); }).catch(() => setOk(false));
  }, [path]);
  useEffect(() => {
    setData(null);
    load();
    const t = setInterval(load, ms);
    return () => clearInterval(t);
  }, [load, ms]);
  return [data, ok, load];
}

export default function App() {
  const [deals, online] = usePoll<DealRow[]>("/api/deals", 2000);
  const [health] = usePoll<Health>("/api/health", 10000);
  const [usage] = usePoll<Usage>("/api/usage", 5000);
  const [board] = usePoll<Board>("/api/board", 10000);
  const [incidents, , reloadIncidents] = usePoll<Incident[]>("/api/incidents", 15000);
  const [selected, setSelected] = useState<string | null>(null);
  const [deal, , reload] = usePoll<Deal>(selected ? `/api/deals/${selected}` : null, 1500);

  useEffect(() => {
    if (!selected && deals?.length) setSelected(deals[0].id);
  }, [deals, selected]);

  const quoted = deals?.filter((d) => d.quote).length ?? 0;
  const times = (deals ?? []).map((d) => d.response_seconds).filter((x): x is number => x != null);
  const avg = times.length ? Math.round(times.reduce((a, b) => a + b, 0) / times.length) : null;
  const me = board?.me;
  const accepted = board?.public.ranking?.find((r) => r.name === TEAM);

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 18.5 29 7l-7.5 19-5-7.2L9 23l1.4-6.9z" /></svg>
          <div>
            <h1>START Milan Forwarding</h1>
            <p>Autonomous air export desk · one agent per deal</p>
          </div>
        </div>
        <dl className="kpis">
          <div><dt>Requests</dt><dd>{deals?.length ?? "–"}</dd></div>
          <div><dt>Quoted</dt><dd>{quoted}</dd></div>
          <div><dt>Accepted</dt><dd>{accepted ? `${accepted.accepted}/${accepted.answered}` : "–"}</dd></div>
          <div><dt>Booked</dt><dd>{deals?.filter((d) => d.booking).length ?? "–"}</dd></div>
          <div><dt>Avg reply</dt><dd>{avg != null ? `${avg} s` : "–"}</dd></div>
          <div><dt>Cost / quote</dt><dd>{usage && quoted ? usd(usage.cost_usd / quoted) : "–"}</dd></div>
          <div><dt>Points</dt><dd>{me?.total != null ? me.total.toFixed(1) : "–"}{me?.rank ? <small> · #{me.rank}</small> : null}</dd></div>
        </dl>
        <div className={`live ${online && health?.worker ? "on" : "off"}`}>
          <span className="pulse" />
          {online ? (health?.worker ? "Live" : "API only") : "Offline"}
          <small>{health ? `${health.models.agent} · ${health.models.effort}` : ""}</small>
        </div>
      </header>
      <main className="grid">
        <DealList deals={deals ?? []} selected={selected} onSelect={setSelected} />
        {deal ? <DealView deal={deal} onSent={reload} /> : (
          <section className="deal placeholder">
            <p>Every request becomes a deal with its own agent session: the mails, what the agent did and why, the priced options, the booking. Select one on the left.</p>
          </section>
        )}
        <BoardPane board={board} team={TEAM}>
          <Incidents items={incidents ?? []} onChange={reloadIncidents} />
        </BoardPane>
      </main>
    </div>
  );
}
