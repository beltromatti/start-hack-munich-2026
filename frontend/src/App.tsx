import { useCallback, useEffect, useRef, useState } from "react";
import { Board, Deal, DealRow, Health, get } from "./api";
import { Desk } from "./desk/Desk";
import { Voice } from "./voice/Voice";

const VOICE = new URLSearchParams(window.location.search).has("voice");

function usePoll<T>(path: string | null, ms: number): [T | null, boolean, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [ok, setOk] = useState(true);
  const request = useRef<AbortController | null>(null);
  const load = useCallback(() => {
    if (!path || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    get<T>(path, controller.signal).then((d) => {
      if (!controller.signal.aborted) { setData(d); setOk(true); }
    }).catch(() => { if (!controller.signal.aborted) setOk(false); })
      .finally(() => { if (request.current === controller) request.current = null; });
  }, [path]);
  useEffect(() => {
    setData(null);
    load();
    const t = setInterval(load, ms);
    return () => { clearInterval(t); request.current?.abort(); request.current = null; };
  }, [load, ms]);
  return [data, ok, load];
}

// The desk (what the agent flagged, shipments, customers, network) with the sessions view as one of its pages.
export default function App() {
  const [deals, online] = usePoll<DealRow[]>("/api/deals", 2000);
  const [health] = usePoll<Health>("/api/health", 10000);
  const [board] = usePoll<Board>("/api/board", 10000);
  const [selected, setSelected] = useState<string | null>(null);
  const [deal, , reload] = usePoll<Deal>(selected ? `/api/deals/${selected}` : null, 1500);
  // /?voice: the voice desk, the app an operator adds to the phone's home screen (src/voice)
  if (VOICE) return <Voice deals={deals ?? []} />;
  return <Desk deals={deals ?? []} online={online} worker={!!health?.worker} board={board} selected={selected} select={setSelected} deal={deal} reload={reload} />;
}
