import { useEffect, useState } from "react";
import { useBoard } from "./sim/board";
import { fmtTime } from "./sim/sim";
import { useWorld } from "./sim/useWorld";
import Exceptions from "./views/Exceptions";
import Inbox from "./views/Inbox";
import LiveRound from "./views/LiveRound";
import MissionControl from "./views/MissionControl";
import Pipeline from "./views/Pipeline";
import Score from "./views/Score";
import Standings from "./views/Standings";

const MAIN = [
  { id: "1", label: "1 · Score", hint: "the score equation: total, three levers, biggest leak, round by round" },
  { id: "2", label: "2 · Live round", hint: "the request running now: clock, pipeline, points still on the table" },
  { id: "3", label: "3 · Exceptions", hint: "disruptions first: green runs alone, what broke and whether it repeats" },
] as const;
const DETAIL = [
  { id: "a", label: "Sessions" }, { id: "b", label: "Inbox" }, { id: "c", label: "Pipeline" }, { id: "d", label: "Standings" },
] as const;
type V = (typeof MAIN)[number]["id"] | (typeof DETAIL)[number]["id"];

export default function App() {
  const { w, paused, toggle } = useWorld();
  const b = useBoard();
  const [view, setView] = useState<V>((new URLSearchParams(location.search).get("v") as V) || "1");
  useEffect(() => {
    history.replaceState(null, "", `?v=${view}`);
    document.documentElement.dataset.theme = "night";
  }, [view]);

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <span className="kicker">START Milan · 5U AI</span>
          <h1>Forwarder</h1>
        </div>
        <nav className="seg" aria-label="Structure">
          {MAIN.map((o) => (
            <button key={o.id} title={o.hint} className={view === o.id ? "active" : ""} onClick={() => setView(o.id)}>{o.label}</button>
          ))}
        </nav>
        <div className="clock">
          <select className="details" value={DETAIL.some((d) => d.id === view) ? view : ""} onChange={(e) => e.target.value && setView(e.target.value as V)} aria-label="Detail views">
            <option value="">Details…</option>
            {DETAIL.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
          </select>
          <span className="badge">Synthetic</span>
          <span className="mono">{fmtTime(w.now)}</span>
          <button className="ghost" onClick={toggle}>{paused ? "Play" : "Pause"}</button>
        </div>
      </header>
      {view === "1" && <Score w={w} b={b} />}
      {view === "2" && <LiveRound w={w} b={b} />}
      {view === "3" && <Exceptions w={w} b={b} />}
      {view === "a" && <MissionControl w={w} />}
      {view === "b" && <Inbox w={w} />}
      {view === "c" && <Pipeline w={w} />}
      {view === "d" && <Standings />}
    </div>
  );
}
