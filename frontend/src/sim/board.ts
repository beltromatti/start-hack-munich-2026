// 5U public leaderboard (CORS open). Live from the first round; a labelled simulation before that.
import { useEffect, useState } from "react";

export const BOARD_URL = "https://api.start-hack.5u.ai/v1/board";
export const US = "START Milan";
const END = Date.parse("2026-11-22T12:45:00+01:00") / 1000;

export interface Row { rank: number; team: string; total: number; accepted: number; answered: number; accept_rate: number | null; human: number; bookings: number }
export interface Board { frozen_at: string | null; overview: { rounds_sent: number; teams: number }; ranking: Row[] }

function simulate(teams: string[], seed: number): Board {
  const rounds = 40 + Math.floor(seed % 200);
  const ranking = teams.map((team, i) => {
    const skill = 0.45 + ((i * 37) % 50) / 100 + (team === US ? 0.3 : 0);
    const answered = Math.min(rounds, Math.round(rounds * (0.8 + ((i * 13) % 20) / 100)));
    const accepted = Math.round(answered * Math.min(0.97, skill));
    return { rank: 0, team, total: Math.round(accepted * (70 + Math.min(1, skill) * 22)), accepted, answered,
      accept_rate: answered ? accepted / answered : null, human: team === US ? 10 : 0, bookings: Math.round(accepted * 0.4) };
  }).sort((a, b) => b.total - a.total).map((r, i) => ({ ...r, rank: i + 1 }));
  return { frozen_at: null, overview: { rounds_sent: rounds, teams: teams.length }, ranking };
}

export function useBoard() {
  const [live, setLive] = useState<Board | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let stop = false;
    const load = () => fetch(BOARD_URL).then((r) => r.json()).then((b: Board) => !stop && setLive(b)).catch(() => {});
    load();
    const t = setInterval(() => { load(); setTick((x) => x + 1); }, 15000);
    return () => { stop = true; clearInterval(t); };
  }, []);
  const simulated = !live || live.overview.rounds_sent === 0;
  const teams = live?.ranking.map((r) => r.team) ?? [US, "Team B", "Team C", "Team D", "Team E"];
  const board = simulated ? simulate(teams, Date.now() / 18000 + tick) : live!;
  const rows = board.ranking;
  const us = rows.find((r) => r.team === US);
  const leader = rows[0];
  const above = us ? rows.filter((r) => r.total > us.total).at(-1) : undefined;
  const below = us ? rows.find((r) => r.total < us.total) : undefined;
  const perRequest = us && us.answered ? us.total / us.answered : 0;
  const roundsLeft = Math.max(0, Math.floor((END - Date.now() / 1000) / 360));
  return { board, rows, simulated, us, leader, above, below, perRequest, roundsLeft,
    projected: us ? Math.round(us.total + perRequest * roundsLeft) : 0 };
}
export type BoardState = ReturnType<typeof useBoard>;
