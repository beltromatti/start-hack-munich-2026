import { useState } from "react";
import { post } from "./api";

// The agent's own browser page (5U's portal page) live inside the deal's conversation, to watch only: 5U, Sun 04:06,
// "If the harness asks a person to solve anything, that's a human". A person answers the agent's questions in words.

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

// What the agent asked a person for (ask_person): a question in words.
export function PersonCard({ dealId, need }: { dealId: string; need: { kind: string; note: string; airline: string | null } }) {
  return <Answer dealId={dealId} note={need.note} />;
}
