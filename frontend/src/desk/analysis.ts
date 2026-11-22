import type { DealRow } from "../api";
import { DEMO } from "../demo";
import { LANES } from "./network";
import { amount, ends } from "./util";

// The deep-dive the desk assistant can do on the record: how the things we know about a shipment move together.
// Every number is a Pearson correlation computed here from the quoted shipments, never written by a model.
// Margin is not on the record (the register keeps what we quoted, not what we paid), so with real data the matrix
// leaves it out and says so. With the example data a made-up margin stands in, and the answer says that too.
export type Matrix = { vars: string[]; r: (number | null)[][]; n: number; target: string; text: string; insights: string[]; example: boolean };

const unit = (s: string) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 1000) / 1000; };
const airlines = (d: DealRow) => { const e = ends(d), l = e ? LANES.find((x) => x[0] === e[0] && x[1] === e[1]) : null; return l ? l[2].length : 0; };
/** Example data only: a margin in percent of the quote, so the demo has something to analyse. It is built to
 *  be higher where more airlines compete and where the customer wants speed, lower on heavy shipments, plus noise. */
const exampleMargin = (d: DealRow) => Math.max(3, Math.min(24, 8 + 2.4 * airlines(d) + (d.preference === "fastest" ? 3.5 : 0) - 0.0022 * (Number(d.weight_kg) || 0) + (unit(d.id) - 0.5) * 5));

function pearson(a: (number | null)[], b: (number | null)[]): number | null {
  const xs: number[] = [], ys: number[] = [];
  a.forEach((x, i) => { const y = b[i]; if (x != null && y != null) { xs.push(x); ys.push(y); } });
  if (xs.length < 5) return null;
  const mx = xs.reduce((s, v) => s + v, 0) / xs.length, my = ys.reduce((s, v) => s + v, 0) / ys.length;
  let sxy = 0, sxx = 0, syy = 0;
  xs.forEach((x, i) => { sxy += (x - mx) * (ys[i] - my); sxx += (x - mx) ** 2; syy += (ys[i] - my) ** 2; });
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}

const SAYS: Record<string, [string, string]> = {
  "Airlines on the route": ["is higher on routes where more airlines compete", "is lower on routes where more airlines compete"],
  "Weight": ["is higher on heavier shipments", "is lower on heavier shipments"],
  "Wants fastest": ["is higher when the customer asks for the fastest option", "is lower when the customer asks for the fastest option"],
  "Answer time": ["is higher where we answered more slowly", "is higher where we answered faster"],
  "Price per kg": ["rises with the price per kg", "falls as the price per kg rises"],
  "Booked": ["is higher on shipments that were booked", "is lower on shipments that were booked"],
  "Margin": ["rises with the margin", "falls as the margin rises"],
};
const strength = (r: number) => Math.abs(r) >= 0.5 ? "strong" : Math.abs(r) >= 0.3 ? "clear" : "weak";
export const fmt = (r: number | null) => r == null ? "n/a" : (r >= 0 ? "+" : "") + r.toFixed(2);

export function matrix(deals: DealRow[]): Matrix {
  const rows = deals.filter((d) => amount(d.quote) != null && Number(d.weight_kg) > 0);
  const col = (f: (d: DealRow) => number | null) => rows.map(f);
  const perKg = (d: DealRow) => amount(d.quote)! / Number(d.weight_kg);
  const cols: [string, (number | null)[]][] = [
    ["Price per kg", col(perKg)],
    ["Weight", col((d) => Number(d.weight_kg))],
    ["Answer time", col((d) => d.response_seconds != null && d.response_seconds >= 1 ? d.response_seconds : null)],
    ["Airlines on the route", col((d) => airlines(d) || null)],
    ["Wants fastest", col((d) => d.preference ? (d.preference === "fastest" ? 1 : 0) : null)],
    ["Booked", col((d) => d.booking || d.status === "booked" ? 1 : 0)],
  ];
  if (DEMO) cols.unshift(["Margin", col((d) => exampleMargin(d))]);
  const vars = cols.map((c) => c[0]), r = cols.map((a, i) => cols.map((b, j) => i === j ? 1 : pearson(a[1], b[1])));
  const target = vars[0] === "Margin" ? "Margin" : "Booked", ti = vars.indexOf(target);
  const ranked = vars.map((v, i) => ({ v, r: r[ti][i] })).filter((x) => x.v !== target && x.r != null && Math.abs(x.r) >= 0.15).sort((a, b) => Math.abs(b.r!) - Math.abs(a.r!));
  const subject = target === "Booked" ? "The share of quotes that get booked" : "Our margin";
  const insights = ranked.slice(0, 3).map((x) => subject + " " + (SAYS[x.v] ?? ["rises with " + x.v.toLowerCase(), "falls as " + x.v.toLowerCase() + " rises"])[x.r! > 0 ? 0 : 1] + ": a " + strength(x.r!) + " link, r = " + fmt(x.r) + ".");
  const lead = rows.length < 5 ? "There are only " + rows.length + " quoted shipments so far, too few to compare." : "I compared " + vars.length + " things we know about each of the " + rows.length + " quoted shipments. " + (insights[0] ?? "None of them moves clearly with " + (target === "Margin" ? "our margin" : "what gets booked") + ".");
  const text = lead + (target === "Booked" && rows.length >= 5 ? " Margin is not on the record yet, because the register keeps what we quoted and not what we paid, so this looks at what gets booked instead." : "");
  return { vars, r, n: rows.length, target, text, insights: insights.slice(1), example: DEMO };
}

export const wantsMatrix = (low: string) => /correlat|matrix|what (drives|affects|influences|moves)|effect of|impact of|how do .* relate/.test(low) || (/margin/.test(low) && /graph|chart|why|depend|variable|driv|affect/.test(low));
