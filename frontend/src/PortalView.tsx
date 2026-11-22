import { useEffect, useRef, useState } from "react";
import { post } from "./api";

// The shared browser's page (5U's portal page) live inside the deal's conversation: the agent opened and filled it,
// the person does only what a person must (the check, the team key, a banner) and sends; the agent reads the result.
const PAGE = { width: 720, height: 860 };

export function PortalView({ dealId, note, airline }: { dealId: string; note: string; airline: string | null }) {
  const [tick, setTick] = useState(0);
  const [text, setText] = useState("");
  const img = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 600);
    return () => clearInterval(t);
  }, []);
  const click = (e: React.MouseEvent<HTMLImageElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    post(`/api/portal/${dealId}/click`, { x: ((e.clientX - r.left) / r.width) * PAGE.width, y: ((e.clientY - r.top) / r.height) * PAGE.height });
    setTimeout(() => setTick((x) => x + 1), 200);
  };
  const send = (key?: string) => {
    post(`/api/portal/${dealId}/type`, { text: key ? "" : text, key });
    if (!key) setText("");
    setTimeout(() => setTick((x) => x + 1), 200);
  };
  return (
    <div className="card portal">
      <div className="card-head">
        <span className="tag">Your turn on 5U's portal</span>
        {airline ? <span className="mono">{airline}</span> : null}
        <span className="muted">{note}</span>
      </div>
      <img ref={img} className="portal-shot" src={`/api/portal/${dealId}/shot?t=${tick}`} onClick={click} alt="5U portal page" />
      <div className="portal-keys">
        <input autoFocus placeholder="click a field above, then type here (the check, the team key)" value={text}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { send(); } }} />
        <button onClick={() => send()}>Type</button>
        <button onClick={() => send("Tab")}>Tab</button>
        <button className="primary" onClick={() => send("Enter")}>Enter</button>
      </div>
      <div className="muted portal-hint">Click a field in the page, type here, press Type; then click the page's send button. The agent reads the result and goes on.</div>
    </div>
  );
}
