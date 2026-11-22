import { useCallback, useEffect, useRef, useState } from "react";
import { Board, Deal, DealRow, Health, Me, get, post } from "./api";
import { BoardPane } from "./Side";
import { Desk } from "./desk/Desk";
import { Login } from "./desk/Login";
import { Voice } from "./voice/Voice";

const VOICE = new URLSearchParams(window.location.search).has("voice");
// The challenge's live leaderboard: for the team, at an address the product does not link to.
const CHALLENGE = window.location.pathname.replace(/\/+$/, "") === "/leaderboard/challenge";

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

function Challenge() {
  const [board] = usePoll<Board>("/api/board", 10000);
  return (
    <div className="challenge">
      <header><h1>Challenge leaderboard</h1><span className="muted">live from 5U, every 10 s</span><a href="/">Back to the desk</a></header>
      <BoardPane board={board} team="start-milan" />
    </div>
  );
}

// The desk (what the agent flagged, shipments, customers, network) with the sessions view as one of its pages.
function Signed({ me, signOut }: { me: Me; signOut: () => void }) {
  const [deals, online] = usePoll<DealRow[]>("/api/deals", 2000);
  const [health] = usePoll<Health>("/api/health", 10000);
  const [selected, setSelected] = useState<string | null>(null);
  const [deal, , reload] = usePoll<Deal>(selected ? `/api/deals/${selected}` : null, 1500);
  // /?voice: the voice desk, the app an operator adds to the phone's home screen (src/voice)
  if (VOICE) return <Voice deals={deals ?? []} />;
  return <Desk account={me.account} signOut={me.open ? null : signOut} deals={deals ?? []} online={online} worker={!!health?.worker} selected={selected} select={setSelected} deal={deal} reload={reload} />;
}

// Signed in, or the sign-in: /api/me says which (open while the server holds no account, as on a laptop).
export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [out, setOut] = useState(false);
  useEffect(() => { get<Me>("/api/me").then(setMe).catch(() => setOut(true)); }, []);
  useEffect(() => {
    const ended = () => { setMe(null); setOut(true); };
    window.addEventListener("desk:signed-out", ended);
    return () => window.removeEventListener("desk:signed-out", ended);
  }, []);
  if (out) return <Login done={(m) => { setMe(m); setOut(false); }} />;
  if (!me) return null;
  if (CHALLENGE) return <Challenge />;
  return <Signed me={me} signOut={() => { post("/api/logout", {}).finally(() => { setMe(null); setOut(true); }); }} />;
}
