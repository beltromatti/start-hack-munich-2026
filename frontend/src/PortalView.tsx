import { useEffect, useRef, useState } from "react";
import { post } from "./api";

// The shared browser's page (5U's portal page) live inside the deal's conversation: the agent opened and filled it,
// the person does only what a person must (the check, the team key, a banner) and sends; the agent reads the result.
const PAGE = { width: 720, height: 860 };

function Answer({ dealId, note }: { dealId: string; note: string }) {
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);
  const send = () => { if (text.trim()) post(`/api/deals/${dealId}/person_answer`, { text }).then(() => setSent(true)); };
  return (
    <div className="card portal">
      <div className="card-head"><span className="tag">The agent asks you</span></div>
      <div className="portal-question">{note}</div>
      {sent ? <div className="muted">Sent: the agent goes on with your answer.</div> : (
        <div className="portal-keys">
          <input autoFocus placeholder="your answer" value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
          <button className="primary" onClick={send}>Answer</button>
        </div>
      )}
    </div>
  );
}

// What the agent asked a person for (ask_person): its page live, or a question to answer.
export function PersonCard({ dealId, need }: { dealId: string; need: { kind: "page" | "answer"; note: string; airline: string | null } }) {
  return need.kind === "answer" ? <Answer dealId={dealId} note={need.note} /> : <PortalView dealId={dealId} note={need.note} airline={need.airline} />;
}

export function PortalView({ dealId, note, airline }: { dealId: string; note: string; airline: string | null }) {
  const [tick, setTick] = useState(0);
  const [text, setText] = useState("");
  // the person's team key stays in their own browser and is typed only when they click (like a password manager)
  const [saved, setSaved] = useState<string | null>(() => { try { return localStorage.getItem("fiveu_team_key"); } catch { return null; } });
  const [draft, setDraft] = useState("");
  const [keyMsg, setKeyMsg] = useState("");
  const typeKey = () => {
    if (!saved) return;
    post<{ ok?: boolean; error?: string }>(`/api/portal/${dealId}/type`, { into: "key", text: saved })
      .then((r) => setKeyMsg(r.error ?? "key typed"));
    setTimeout(() => setTick((x) => x + 1), 200);
  };
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
        {saved ? <>
          <button className="primary" onClick={typeKey}>Type my key</button>
          <button onClick={() => { try { localStorage.removeItem("fiveu_team_key"); } catch { /* none */ } setSaved(null); }}>forget key</button>
          {keyMsg ? <span className="muted">{keyMsg}</span> : null}
        </> : <>
          <input type="password" placeholder="team key: saved in this browser only" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button onClick={() => { try { localStorage.setItem("fiveu_team_key", draft); } catch { /* none */ } setSaved(draft); setDraft(""); }}>Save key</button>
        </>}
      </div>
      <div className="portal-keys">
        <input autoFocus placeholder="click the check's field above, type the answer here, press Type" value={text}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { send(); } }} />
        <button onClick={() => send()}>Type</button>
        <button onClick={() => send("Tab")}>Tab</button>
        <button className="primary" onClick={() => send("Enter")}>Enter</button>
      </div>
      <div className="muted portal-hint">Type my key fills the key field; click the check's field, type the answer, press Type; then press the page's send button. The agent reads the result and goes on.</div>
    </div>
  );
}
