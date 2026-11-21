// Option D: how we stand against the other teams. Reads 5U's public leaderboard live (CORS is open),
// and computes gaps, pace and a projection. Before the first round it shows a clearly marked simulation.
import { useEffect, useState } from "react";
import { Kpi } from "../ui";

const BOARD = "https://api.start-hack.5u.ai/v1/board";
const US = "START Milan";
const END = Date.parse("2026-11-22T12:45:00+01:00") / 1000;
const ROUND = 360;

interface Row { rank: number; team: string; total: number; accepted: number; answered: number; accept_rate: number | null; human: number; bookings: number; reference_team?: boolean }
interface Board { frozen_at: string | null; overview: { rounds_sent: number; teams: number; accepted: number; bookings: number }; ranking: Row[]; rounds: unknown[]; bookings: unknown[] }

function simulate(teams: string[], now: number): Board {
  const rounds = 40 + Math.floor((now / 18) % 200);
  const ranking = teams.map((team, i) => {
    const skill = 0.45 + ((i * 37) % 50) / 100 + (team === US ? 0.08 : 0);
    const answered = Math.min(rounds, Math.round(rounds * (0.8 + ((i * 13) % 20) / 100)));
    const accepted = Math.round(answered * Math.min(0.97, skill));
    return { rank: 0, team, total: Math.round(accepted * (70 + skill * 22)), accepted, answered, accept_rate: answered ? accepted / answered : null,
      human: team === US ? 10 : 0, bookings: Math.round(accepted * 0.4) };
  }).sort((a, b) => b.total - a.total).map((r, i) => ({ ...r, rank: i + 1 }));
  return { frozen_at: null, overview: { rounds_sent: rounds, teams: teams.length, accepted: 0, bookings: 0 }, ranking, rounds: [], bookings: [] };
}

export default function Standings() {
  const [live, setLive] = useState<Board | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let stop = false;
    const load = () => fetch(BOARD).then((r) => r.json()).then((b: Board) => { if (!stop) { setLive(b); setErr(null); } })
      .catch((e) => !stop && setErr(String(e)));
    load();
    const t = setInterval(() => { load(); setTick((x) => x + 1); }, 15000);
    return () => { stop = true; clearInterval(t); };
  }, []);

  const simulated = !live || live.overview.rounds_sent === 0;
  const teams = live?.ranking.map((r) => r.team) ?? [US, "Team B", "Team C", "Team D"];
  const b = simulated ? simulate(teams, Date.now() / 1000 + tick * 15) : live!;
  const rows = b.ranking;
  const us = rows.find((r) => r.team === US);
  const leader = rows[0];
  const above = us ? rows.filter((r) => r.total > us.total).at(-1) : undefined;
  const perRound = us && us.answered ? us.total / us.answered : 0;
  const leftRounds = Math.max(0, Math.floor((END - Date.now() / 1000) / ROUND));
  const projected = us ? Math.round(us.total + perRound * leftRounds) : 0;
  const gapLeader = us && leader ? leader.total - us.total : 0;
  const max = Math.max(1, ...rows.map((r) => r.total));

  return (
    <div className="st">
      <div className="st-head">
        <span className={`badge ${simulated ? "" : "live"}`}>{simulated ? "Simulation until the first round · live board from 16:00" : "Live · 5U leaderboard"}</span>
        <span className="muted">{b.overview.teams} teams · {b.overview.rounds_sent} rounds sent{err ? ` · board offline: ${err}` : ""}</span>
      </div>
      <div className="kpis">
        <Kpi label="Our rank" value={us ? `${us.rank} / ${rows.length}` : "—"} hint={US} tone={us && us.rank <= 3 ? "good" : undefined} />
        <Kpi label="Gap to #1" value={gapLeader ? `−${Math.round(gapLeader)}` : "leading"} hint={gapLeader ? `≈ ${(gapLeader / 100).toFixed(1)} perfect rounds` : leader?.team} tone={gapLeader ? "warn" : "good"} />
        <Kpi label="Gap to next" value={above && us ? `−${Math.round(above.total - us.total)}` : "—"} hint={above ? above.team : "nobody above"} />
        <Kpi label="Points / request" value={perRound.toFixed(1)} hint="max 100" />
        <Kpi label="Projected final" value={String(projected)} hint={`${leftRounds} rounds left at this pace`} />
      </div>
      <section className="panel">
        <h2>Standings</h2>
        <div className="table st-table" role="table">
          <div className="tr th" role="row"><span>#</span><span>Team</span><span /><span className="num">Points</span><span className="num">Accepted</span><span className="num">Rate</span><span className="num">Booked</span><span className="num">Human</span></div>
          {rows.map((r) => (
            <div className={`tr ${r.team === US ? "us" : ""}`} role="row" key={r.team}>
              <span className="mono">{r.rank}</span>
              <span className="cust">{r.team}{r.team === US ? " (us)" : ""}</span>
              <span className="bar"><i style={{ width: `${(r.total / max) * 100}%` }} /></span>
              <span className="num">{Math.round(r.total)}</span>
              <span className="num">{r.accepted}/{r.answered}</span>
              <span className="num">{r.accept_rate == null ? "—" : `${Math.round(r.accept_rate * 100)} %`}</span>
              <span className="num">{r.bookings}</span>
              <span className="num">{r.human}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
