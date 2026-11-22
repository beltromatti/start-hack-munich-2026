import { useState } from "react";
import type { DealRow } from "../api";
import { amount, lane, median, money } from "./util";

// How the desk is doing, counted from the same deals the other pages read: how much it answered on its own,
// how fast, and how much was booked. Nothing here is stored or estimated. A number that the data cannot give
// (the model cost when it is zero) is left out.
const ms = (t: number) => (t < 1e12 ? t * 1000 : t);
const day = (t: number) => { const d = new Date(ms(t)); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
const short = (key: string) => new Date(key + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const secs = (s: number | null) => s == null ? "–" : s < 100 ? Math.round(s) + " s" : (s / 60).toFixed(1) + " min";
const isBooked = (d: DealRow) => !!d.booking || d.status === "booked";

type Bar = { label: string; value: number; tip: string };

// One series, so no legend: the title names it. Thin bars from the baseline with rounded tops, a quiet axis,
// the highest bar labelled, and the exact value of any bar on hover or focus.
function Bars({ data, name }: { data: Bar[]; name: string }) {
  const [on, setOn] = useState(-1);
  const W = 560, H = 190, top = 22, base = H - 26, max = Math.max(1, ...data.map((d) => d.value));
  const slot = W / data.length, w = Math.min(26, slot - 4), peak = data.findIndex((d) => d.value === max);
  const every = Math.max(1, Math.ceil(data.length / 7));
  return (
    <div className="dk-chart">
      <svg viewBox={"0 0 " + W + " " + H} role="img" aria-label={name + ". " + data.map((d) => d.tip).join(". ")}>
        <line x1="0" x2={W} y1={base + 0.5} y2={base + 0.5} className="ax" />
        {data.map((d, i) => {
          const h = d.value ? Math.max(3, (d.value / max) * (base - top)) : 0, x = i * slot + (slot - w) / 2, r = Math.min(4, h);
          return (
            <g key={i} className={on >= 0 && on !== i ? "dim" : ""} tabIndex={0} onMouseEnter={() => setOn(i)} onMouseLeave={() => setOn(-1)} onFocus={() => setOn(i)} onBlur={() => setOn(-1)}>
              <rect x={i * slot} y={0} width={slot} height={H} fill="transparent" />
              {h ? <path className="bar" d={"M" + x + " " + base + "V" + (base - h + r) + "a" + r + " " + r + " 0 0 1 " + r + " -" + r + "h" + (w - 2 * r) + "a" + r + " " + r + " 0 0 1 " + r + " " + r + "V" + base + "Z"} /> : null}
              {i === peak && on < 0 ? <text x={x + w / 2} y={base - h - 6} textAnchor="middle" className="val">{d.value}</text> : null}
              {(data.length - 1 - i) % every === 0 ? <text x={i * slot + slot / 2} y={H - 8} textAnchor="middle" className="lab">{d.label}</text> : null}
            </g>
          );
        })}
      </svg>
      <p className="dk-tip" aria-hidden="true">{on >= 0 ? data[on].tip : "Point at a bar for its exact number."}</p>
    </div>
  );
}

export function Numbers({ deals }: { deals: DealRow[] }) {
  const total = deals.length, quoted = deals.filter((d) => d.quote), booked = deals.filter(isBooked);
  const times = quoted.map((d) => d.response_seconds).filter((x): x is number => x != null && x >= 1);
  const med = median(times), fast = times.filter((x) => x <= 120).length;
  const weight = booked.reduce((s, d) => s + (Number(d.weight_kg) || 0), 0);
  const value = booked.reduce((s, d) => s + (amount(d.quote) ?? 0), 0), priced = booked.filter((d) => amount(d.quote) != null).length;
  const cost = deals.reduce((s, d) => s + (d.cost_usd || 0), 0);
  const flaggedN = deals.filter((d) => d.flag === "red" || d.flag === "yellow").length;
  const pct = (a: number, b: number) => b ? Math.round((a / b) * 100) + " %" : "–";
  // the last 14 days, by the day of a shipment's last step (the list carries no arrival time)
  const days: Bar[] = [];
  for (let i = 13; i >= 0; i--) {
    const key = day(Date.now() - i * 86400000), on = deals.filter((d) => day(d.updated_at) === key), b = on.filter(isBooked).length;
    days.push({ label: short(key), value: on.length, tip: short(key) + ": " + on.length + (on.length === 1 ? " shipment" : " shipments") + ", " + b + " booked" });
  }
  const BUCKETS: [string, number, number][] = [["under 30 s", 0, 30], ["30 to 45 s", 30, 45], ["45 to 60 s", 45, 60], ["1 to 1.5 min", 60, 90], ["1.5 to 2 min", 90, 120], ["over 2 min", 120, Infinity]];
  const speed: Bar[] = BUCKETS.map(([label, a, b]) => { const n = times.filter((x) => x >= a && x < b).length; return { label, value: n, tip: label + ": " + n + " of " + times.length + " quotes" }; });
  const routes = [...deals.reduce((m, d) => { const k = lane(d); if (k) m.set(k, [...(m.get(k) ?? []), d]); return m; }, new Map<string, DealRow[]>())]
    .map(([k, ds]) => ({ k, n: ds.length, booked: ds.filter(isBooked).length, med: median(ds.map((d) => d.response_seconds).filter((x): x is number => x != null && x >= 1)), value: ds.reduce((s, d) => s + (amount(d.quote) ?? 0), 0) }))
    .sort((a, b) => b.n - a.n || b.value - a.value).slice(0, 8);
  const tiles: [string, string, string][] = [
    ["Answered", pct(quoted.length, total), quoted.length + " of " + total + " requests got a quote"],
    ["Typical answer", secs(med), times.length ? fast + " of " + times.length + " quotes left within 2 minutes" : "No quote has a time yet"],
    ["Booked", String(booked.length), pct(booked.length, quoted.length) + " of the quotes became a booking"],
    ["Freight booked", weight ? Math.round(weight).toLocaleString("en-US") + " kg" : "–", !booked.length ? "No booking yet" : priced === booked.length ? money(value) + " in booked quotes" : priced ? money(value) + " in the " + priced + " bookings with a recorded price" : booked.length + " bookings"],
  ];
  if (cost > 0 && quoted.length) tiles.push(["Model cost per quote", "$" + (cost / quoted.length).toFixed(4), "$" + cost.toFixed(2) + " for all " + total + " requests"]);
  return (
    <>
      <section className="dk-lead">
        <h2>{total ? pct(quoted.length, total) + " of requests got a quote" + (med != null ? ", typically in " + secs(med) + "." : ".") : "No requests yet."}</h2>
        <p>Counted from the shipments on this desk. {flaggedN ? flaggedN + (flaggedN === 1 ? " of them carries" : " of them carry") + " a note from Giulia." : "None of them carries a note from Giulia."}</p>
      </section>
      <div className="dk-kpis">{tiles.map(([label, big, sub]) => <section key={label} className="dk-box dk-kpi"><small>{label}</small><b>{big}</b><span>{sub}</span></section>)}</div>
      <div className="dk-two even">
        <section className="dk-box"><div className="dk-bh"><h2>Shipments per day</h2></div><p className="dk-bs">The last 14 days, by the day of a shipment's last step.</p><Bars data={days} name="Shipments per day" /></section>
        <section className="dk-box"><div className="dk-bh"><h2>Time from request to quote</h2></div><p className="dk-bs">How many quotes left in each span of time.</p><Bars data={speed} name="Time from request to quote" /></section>
      </div>
      <section className="dk-box">
        <div className="dk-bh"><h2>Busiest routes</h2></div>
        <table className="dk-nt"><thead><tr><th>Route</th><th>Requests</th><th>Booked</th><th>Typical answer</th><th>Quoted</th></tr></thead>
          <tbody>{routes.map((r) => <tr key={r.k}><td>{r.k}</td><td>{r.n}</td><td>{r.booked}</td><td>{secs(r.med)}</td><td>{r.value ? money(r.value) : "–"}</td></tr>)}</tbody></table>
        {!routes.length ? <div className="dk-empty"><b>No routes yet</b>They appear with the first request that names an origin and a destination.</div> : null}
      </section>
    </>
  );
}
