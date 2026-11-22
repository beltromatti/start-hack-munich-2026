import { useEffect, useRef, useState } from "react";
import { DealRow, get, post } from "./api";

// Operator mode: a person is at the desk. When the agent asks for one on 5U's portal page (portal_page ask_person),
// an alarm rings, a notification comes, and the deal opens with the page live in its conversation.
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
  const waiting = deals.filter((d) => d.needs_person);
  useEffect(() => {
    for (const d of waiting) {
      const key = `${d.id}:${d.needs_person?.since}`;
      if (seen.current.has(key)) continue;
      seen.current.add(key);
      alarm();
      onOpen(d.id);
      try {
        if ("Notification" in window && Notification.permission === "granted") {
          const n = new Notification(d.needs_person?.kind === "answer" ? "The agent asks you" : "Your turn on 5U's portal", { body: `${d.route ?? ""}: ${d.needs_person?.note ?? ""}`, requireInteraction: true });
          n.onclick = () => { window.focus(); onOpen(d.id); n.close(); };
        }
      } catch { /* none */ }
    }
    document.title = waiting.length ? `(!) Your turn · ${title.current}` : title.current;
  });
  if (!op) return null;
  const toggle = () => post<Op>("/api/operator", { on: !op.on }).then((x) => setOp({ on: x.on }));
  return (
    <section className={`operator${waiting.length ? " needed" : ""}`}>
      <div className="op-line">
        <button className={`op-toggle${op.on ? " on" : ""}`} onClick={toggle}>{op.on ? "Operator ON" : "Operator OFF"}</button>
        {"Notification" in window && Notification.permission !== "granted"
          ? <button className="chip" onClick={() => Notification.requestPermission()}>Allow alerts</button> : null}
        <span className="muted op-hint">
          {waiting.length ? waiting.map((d) => <a key={d.id} href="#" onClick={(e) => { e.preventDefault(); onOpen(d.id); }}>{d.route}: {d.needs_person?.kind === "answer" ? "a question for you" : "your turn on the portal"} </a>)
            : op.on ? "at the desk: when the agent needs a person, its deal opens in front of you" : "off: the agent quotes without asking anyone"}
        </span>
      </div>
    </section>
  );
}
