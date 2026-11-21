import { useEffect, useState } from "react";
import { fmtTime } from "./sim/sim";
import { useWorld } from "./sim/useWorld";
import Inbox from "./views/Inbox";
import MissionControl from "./views/MissionControl";
import Pipeline from "./views/Pipeline";

const OPTIONS = [
  { id: "a", label: "A · Mission Control", hint: "technical: sessions, steps, cost, health" },
  { id: "b", label: "B · Inbox", hint: "mail-first: thread + case facts" },
  { id: "c", label: "C · Pipeline", hint: "CRM: grouped by stage, won and lost" },
] as const;
type Opt = (typeof OPTIONS)[number]["id"];

export default function App() {
  const { w, paused, toggle } = useWorld();
  const [opt, setOpt] = useState<Opt>(() => (new URLSearchParams(location.search).get("v") as Opt) || "a");
  useEffect(() => { history.replaceState(null, "", `?v=${opt}`); }, [opt]);

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <h1>Forwarder Console</h1>
          <span className="badge">Synthetic data</span>
        </div>
        <nav className="seg" aria-label="Design option">
          {OPTIONS.map((o) => (
            <button key={o.id} title={o.hint} className={opt === o.id ? "active" : ""} onClick={() => setOpt(o.id)}>{o.label}</button>
          ))}
        </nav>
        <div className="clock">
          <span className="mono">{fmtTime(w.now)}</span>
          <button className="ghost" onClick={toggle}>{paused ? "Play" : "Pause"}</button>
        </div>
      </header>
      {opt === "a" && <MissionControl w={w} />}
      {opt === "b" && <Inbox w={w} />}
      {opt === "c" && <Pipeline w={w} />}
    </div>
  );
}
