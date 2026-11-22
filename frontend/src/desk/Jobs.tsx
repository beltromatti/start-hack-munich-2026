import { useState } from "react";
import type { DealRow } from "../api";
import { MatrixChart } from "./Matrix";
import { matrix } from "./analysis";
import { Icon } from "./icons";

// Analyses the desk assistant repeats on its own. A job is made in the chat ("make this a job"). A draft of the
// idea: jobs are kept in this browser and run while the desk is open, nothing runs on the server yet.
export type Job = { id: string; title: string; q: string; every: "day" | "week"; label: string; created: number; last: number; result: string };
const at = (t: number) => new Date(t).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function Jobs({ jobs, deals, run, remove, ask }: { jobs: Job[]; deals: DealRow[]; run: (id: string) => void; remove: (id: string) => void; ask: () => void }) {
  const [open, setOpen] = useState<string | null>(jobs[0]?.id ?? null);
  return (
    <>
      <section className="dk-lead">
        <h2>{jobs.length ? jobs.length + (jobs.length === 1 ? " analysis repeats" : " analyses repeat") + " on " + (jobs.length === 1 ? "its" : "their") + " own." : "No jobs yet."}</h2>
        <p>You make a job in the chat: ask for an analysis, then say "make this a job". <b>A draft:</b> jobs are kept in this browser and run while the desk is open.</p>
      </section>
      {jobs.map((j) => (
        <section key={j.id} className="dk-box">
          <div className="dk-set">
            <span className="dk-sq q"><Icon n="repeat" size={15} /></span>
            <span style={{ minWidth: 0 }}><b>{j.title}</b><small>{j.label} · last run {at(j.last)}</small><small className="dk-fence">{j.result}</small></span>
            <span className="dk-ctl"><button className="dk-btn" onClick={() => setOpen(open === j.id ? null : j.id)}>{open === j.id ? "Hide result" : "Show result"}</button><button className="dk-btn" onClick={() => run(j.id)}>Run now</button><button className="dk-btn" onClick={() => remove(j.id)}>Remove</button></span>
          </div>
          {open === j.id ? <div style={{ padding: "0 18px 16px" }}><MatrixChart m={matrix(deals)} /></div> : null}
        </section>
      ))}
      {!jobs.length ? <section className="dk-box"><div className="dk-empty"><b>Nothing repeats yet</b>Ask the desk for an analysis and tell it to make that a job.<br /><button className="dk-btn k" style={{ marginTop: 12 }} onClick={ask}>Open the chat</button></div></section> : null}
    </>
  );
}
