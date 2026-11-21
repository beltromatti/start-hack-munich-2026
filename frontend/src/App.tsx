import { useEffect, useMemo, useState } from "react";

type Event = {
  id: number; ts: number; run_id: string | null; agent: string; kind: string;
  summary: string; data: unknown; tokens_in: number; tokens_out: number;
};
type Usage = { tokens_in: number; tokens_out: number; llm_calls: number; cost_usd: number };
type Health = { ok: boolean; worker: boolean; llm: string; models: { parse: string; bid: string; write: string } };

const get = <T,>(path: string): Promise<T> => fetch(path).then((r) => r.json());
const time = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export default function App() {
  const [events, setEvents] = useState<Event[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [run, setRun] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let last = 0;
    const poll = async () => {
      try {
        const fresh = await get<Event[]>(`/api/events?since=${last}`);
        if (fresh.length) {
          last = fresh[fresh.length - 1].id;
          setEvents((old) => [...old, ...fresh].slice(-1000));
        }
        setUsage(await get<Usage>("/api/usage"));
        setOffline(false);
      } catch {
        setOffline(true);
      }
    };
    get<Health>("/api/health").then(setHealth).catch(() => setOffline(true));
    poll();
    const t = setInterval(poll, 2000);
    return () => clearInterval(t);
  }, []);

  const runs = useMemo(() => {
    const m = new Map<string, Event[]>();
    for (const e of events) if (e.run_id) m.set(e.run_id, [...(m.get(e.run_id) ?? []), e]);
    return [...m.entries()].reverse();
  }, [events]);
  const shown = run ? events.filter((e) => e.run_id === run) : events;

  return (
    <div className="page">
      <header>
        <h1>Agent Console</h1>
        <div className="meta">
          {offline ? <span className="bad">API offline</span> : health && <span>{health.models.parse} · forwarder {health.worker ? "live" : "off"}</span>}
          {usage && <span>{usage.llm_calls} calls · {usage.tokens_in + usage.tokens_out} tokens · ${usage.cost_usd.toFixed(4)}</span>}
        </div>
      </header>
      <main>
        <aside>
          <h2>Runs</h2>
          <button className={run === null ? "active" : ""} onClick={() => setRun(null)}>All activity</button>
          {runs.map(([id, ev]) => (
            <button key={id} className={run === id ? "active" : ""} onClick={() => setRun(id)}>
              <strong>{ev[0].agent}</strong>
              <span>{ev[0].summary}</span>
              <small>{time(ev[0].ts)} · {ev[ev.length - 1].kind}</small>
            </button>
          ))}
        </aside>
        <section>
          <h2>{run ? "Run timeline" : "Live timeline"}</h2>
          {shown.length === 0 && <p className="empty">No activity yet. Start the backend and drop a mail into backend/data/inbox.</p>}
          <ol>
            {[...shown].reverse().map((e) => (
              <li key={e.id} className={`k-${e.kind}`}>
                <time>{time(e.ts)}</time>
                <span className="agent">{e.agent}</span>
                <span className="kind">{e.kind}</span>
                <span className="text">{e.summary}</span>
                {e.tokens_in + e.tokens_out > 0 && <span className="tok">{e.tokens_in + e.tokens_out} tok</span>}
              </li>
            ))}
          </ol>
        </section>
      </main>
    </div>
  );
}
