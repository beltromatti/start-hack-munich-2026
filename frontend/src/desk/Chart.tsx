import { useState } from "react";
import { Chart, post } from "../api";
import { Matrix } from "./analysis";
import { Icon } from "./icons";
import { MatrixChart } from "./Matrix";
import { Bars } from "./Numbers";

// A chart the backend computed from the register (charts.py). The assistant chooses what to look at; every number
// here comes from code. Categories as a ranked list of bars, time as columns, figures that move together as a matrix.
const NAMES: Record<string, string> = { price_per_kg_eur: "Price per kg", weight_kg: "Weight", answer_seconds: "Answer time", wants_fastest: "Wants fastest", booked: "Booked", room_eur: "Room to next option", ai_cost_usd: "AI cost" };
const num = (v: number, unit?: string) => unit === "EUR" ? "€" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  : unit === "USD" ? "$" + v.toFixed(4) : v.toLocaleString("en-US", { maximumFractionDigits: 1 }) + (unit && !["shipments", "bookings"].includes(unit) ? " " + unit : "");

export function ChartView({ c, keep, drop }: { c: Chart; keep?: boolean; drop?: () => void }) {
  const [kept, setKept] = useState("");
  const pin = () => post("/api/pins", { spec: c.spec }).then(() => setKept("On your Efficiency page.")).catch(() => setKept("That did not go through."));
  const tools = (
    <span className="dk-ch-tools">
      {keep && !kept ? <button className="dk-btn sm" onClick={pin}><Icon n="layoutDashboard" size={14} />Keep on Efficiency</button> : null}
      {kept ? <small>{kept}</small> : null}
      {drop ? <button className="dk-btn sm" onClick={drop} aria-label={"Remove " + c.title}><Icon n="x" size={14} />Remove</button> : null}
    </span>
  );
  if (c.kind === "matrix" && c.vars && c.r) {
    const m: Matrix = { vars: c.vars.map((v) => NAMES[v] ?? v), r: c.r, n: c.n, target: "", text: "", insights: [], example: false };
    return <div className="dk-ch"><div className="dk-ch-h"><b>{c.title}</b>{tools}</div><MatrixChart m={m} /><small className="dk-ch-n">Across {c.n} shipments. Pearson r, computed from the register.</small></div>;
  }
  const pts = c.points ?? [];
  const time = c.kind === "line" || c.spec.group_by === "day" || c.spec.group_by === "hour";
  const max = Math.max(1e-9, ...pts.map((p) => Math.abs(p.value)));
  return (
    <div className="dk-ch">
      <div className="dk-ch-h"><b>{c.title}</b>{tools}</div>
      {!pts.length ? <p className="dk-bs">Nothing on the record matches yet.</p> : time
        ? <Bars data={pts.map((p) => ({ label: p.label, value: p.value, tip: p.label + ": " + num(p.value, c.unit) + " (" + p.n + (p.n === 1 ? " shipment)" : " shipments)") }))} name={c.title} />
        : <ol className="dk-hb">{pts.map((p) => <li key={p.label}><span>{p.label}</span><i style={{ width: Math.max(2, (Math.abs(p.value) / max) * 100) + "%" }} /><b className="dk-num">{num(p.value, c.unit)}</b></li>)}</ol>}
      <small className="dk-ch-n">{c.total != null && pts.length > 1 ? "Total " + num(c.total, c.unit) + ". " : ""}From {c.n} shipments in the register.</small>
    </div>
  );
}
