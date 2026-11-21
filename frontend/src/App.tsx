import { useEffect, useState } from "react";
import { fmtTime } from "./sim/sim";
import { useWorld } from "./sim/useWorld";
import Inbox from "./views/Inbox";
import MissionControl from "./views/MissionControl";
import Pipeline from "./views/Pipeline";
import Standings from "./views/Standings";

const VIEWS = [
  { id: "a", label: "Sessions", hint: "technical: every request step by step, cost, health" },
  { id: "b", label: "Inbox", hint: "mail-first: thread + case facts" },
  { id: "c", label: "Pipeline", hint: "CRM: grouped by stage, won and lost" },
  { id: "d", label: "Standings", hint: "us against the other teams, live from the 5U board" },
] as const;
const THEMES = [
  { id: "ink", label: "Ink", hint: "Sam's brand: ink, one indigo accent, Helvetica, light numerals" },
  { id: "sempli", label: "Sempli", hint: "app look: system grey, white cards, sage, rounded numbers" },
  { id: "board", label: "Departures", hint: "airport board: black, amber, mono, all caps" },
] as const;
type V = (typeof VIEWS)[number]["id"];
type T = (typeof THEMES)[number]["id"];

export default function App() {
  const { w, paused, toggle } = useWorld();
  const q = new URLSearchParams(location.search);
  const [view, setView] = useState<V>((q.get("v") as V) || "a");
  const [theme, setTheme] = useState<T>((q.get("t") as T) || "ink");
  useEffect(() => {
    history.replaceState(null, "", `?v=${view}&t=${theme}`);
    document.documentElement.dataset.theme = theme;
  }, [view, theme]);

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <span className="kicker">START Milan · 5U AI</span>
          <h1>Forwarder Console</h1>
        </div>
        <nav className="seg" aria-label="View">
          {VIEWS.map((o) => (
            <button key={o.id} title={o.hint} className={view === o.id ? "active" : ""} onClick={() => setView(o.id)}>{o.label}</button>
          ))}
        </nav>
        <div className="clock">
          <nav className="seg small" aria-label="Design direction">
            {THEMES.map((o) => (
              <button key={o.id} title={o.hint} className={theme === o.id ? "active" : ""} onClick={() => setTheme(o.id)}>{o.label}</button>
            ))}
          </nav>
          {view !== "d" && <><span className="badge">Synthetic</span><span className="mono">{fmtTime(w.now)}</span>
            <button className="ghost" onClick={toggle}>{paused ? "Play" : "Pause"}</button></>}
        </div>
      </header>
      {view === "a" && <MissionControl w={w} />}
      {view === "b" && <Inbox w={w} />}
      {view === "c" && <Pipeline w={w} />}
      {view === "d" && <Standings />}
    </div>
  );
}
