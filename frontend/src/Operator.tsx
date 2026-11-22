import { useEffect, useMemo, useRef, useState } from "react";
import { DealRow, get, post } from "./api";

// Notifications observe autonomous browser work; switching alerts off never stops the agent.
type Op = { on: boolean };

function alarm() {
  try {
    const ctx = new AudioContext();
    [0, 0.25, 0.5].forEach((t) => {
      const o = ctx.createOscillator();
      o.frequency.value = 880;
      o.connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.15);
      if (t === 0.5) o.onended = () => { void ctx.close(); };
    });
  } catch { /* no audio */ }
}

export function OperatorStrip({ deals, onOpen }: { deals: DealRow[]; onOpen: (id: string) => void }) {
  const [op, setOp] = useState<Op | null>(null);
  const seen = useRef<Set<string>>(new Set());
  const title = useRef(document.title);
  useEffect(() => {
    const load = () => get<Op>("/api/operator").then(setOp).catch(() => undefined);
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);
  const waiting = useMemo(() => deals.filter((d) => d.browser_activity?.active), [deals]);
  useEffect(() => {
    for (const d of op?.on ? waiting : []) {
      const key = `${d.id}:${d.browser_activity?.since}`;
      if (seen.current.has(key)) continue;
      seen.current.add(key);
      alarm();
      onOpen(d.id);
      try {
        if ("Notification" in window && Notification.permission === "granted") {
          const n = new Notification("Agent working on 5U's portal", { body: `${d.route ?? ""}: ${d.browser_activity?.note ?? ""}`, requireInteraction: true });
          n.onclick = () => { window.focus(); onOpen(d.id); n.close(); };
        }
      } catch { /* none */ }
    }
    document.title = waiting.length ? `Agent on portal · ${title.current}` : title.current;
  }, [waiting, op?.on, onOpen]);
  if (!op) return null;
  const toggle = () => post<Op>("/api/operator", { on: !op.on }).then((x) => setOp({ on: x.on }));
  return (
    <section className={`operator${waiting.length ? " needed" : ""}`}>
      <div className="op-line">
        <button className={`op-toggle${op.on ? " on" : ""}`} onClick={toggle}>{op.on ? "Alerts ON" : "Alerts OFF"}</button>
        {"Notification" in window && Notification.permission !== "granted"
          ? <button className="chip" onClick={() => Notification.requestPermission()}>Allow alerts</button> : null}
        <span className="muted op-hint">
          {waiting.length ? waiting.map((d) => <a key={d.id} href="#" onClick={(e) => { e.preventDefault(); onOpen(d.id); }}>{d.route}: {"watch the agent on the portal"} </a>)
            : op.on ? "the agent works autonomously; its browser opens here when needed" : "alerts muted; the agent continues autonomously"}
        </span>
      </div>
    </section>
  );
}
