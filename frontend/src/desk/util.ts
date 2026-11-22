import type { DealRow } from "../api";
import { who } from "../format";
import { CITY } from "./network";

export type Group = "needs" | "working" | "quoted" | "booked" | "lost";
export const LABEL: Record<Group, string> = { needs: "Flagged", working: "In progress", quoted: "Quote sent", booked: "Booked", lost: "Lost" };

// The agent works on its own (no person in the loop). What it wants a person to see, it flags with a note:
// "needs" is that flag. Nothing waits for an answer.
const NOTES = new Map<string, string>();
/** The flagged notes by deal, kept current by the knowledge hook, so every list can say why a shipment is flagged. */
export const setFlagNote = (id: string, text: string | null) => { if (text) NOTES.set(id, text); else NOTES.delete(id); };
export const flagNote = (d: DealRow) => NOTES.get(d.id) ?? null;
export const flagged = (d: DealRow) => d.flag === "red" || d.flag === "yellow";
export const groupOf = (d: DealRow): Group => flagged(d) ? "needs" : d.status === "booked" ? "booked" : d.status === "lost" ? "lost" : d.status === "quoted" ? "quoted" : "working";
export const amount = (q: string | number | null | undefined) => { const n = typeof q === "number" ? q : parseFloat(String(q ?? "")); return Number.isFinite(n) ? n : null; };
export const money = (q: string | number | null | undefined) => { const n = amount(q); return n == null ? "–" : "€" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
export const ends = (d: DealRow): [string, string] | null => { const [o, t] = (d.route ?? "").split("-"); return o && t && o !== "undefined" && o !== "None" && t !== "None" ? [o, t] : null; };
export const city = (c: string) => CITY[c] ?? c;
export const kg = (d: DealRow) => d.weight_kg ? Number(d.weight_kg).toLocaleString("en-US", { maximumFractionDigits: 0 }) + " kg" : "";
export const name = (d: DealRow) => who(d.customer);
export const lane = (d: DealRow) => { const e = ends(d); return e ? city(e[0]) + " to " + city(e[1]) : ""; };
export const firstSentence = (t: string) => { const m = t.match(/^.*?[.?!](\s|$)/); return (m ? m[0] : t).trim().replace(/\.$/, ""); };
export const why = (d: DealRow) => flagNote(d) ? firstSentence(flagNote(d)!) : "Flagged by the AI Worker";
export const median = (xs: number[]) => { const a = xs.slice().sort((x, y) => x - y); return a.length ? a[Math.floor(a.length / 2)] : null; };
const ms = (ts: number | string) => typeof ts === "number" ? ts * 1000 : Date.parse(ts);
/** How long ago, in the words a person says: 40 s, 12 min, 3 h, 4 days. */
export function since(ts: number | string | null | undefined): string {
  if (ts == null) return "";
  const s = Math.max(0, Math.round((Date.now() - ms(ts)) / 1000));
  return s < 90 ? s + " s" : s < 5400 ? Math.round(s / 60) + " min" : s < 172800 ? Math.round(s / 3600) + " h" : Math.round(s / 86400) + " days";
}
/** A clock time today, a date before that. */
export function when(ts: number | string | null | undefined): string {
  if (ts == null) return "";
  const d = new Date(ms(ts));
  return Date.now() - d.getTime() < 20 * 3600 * 1000 ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export type Cust = { email: string; name: string; deals: DealRow[]; value: number; booked: number; quoted: number; last: number; needs: boolean };
export function customers(deals: DealRow[]): Cust[] {
  const m = new Map<string, Cust>();
  for (const d of deals) {
    const email = d.customer ?? "unknown";
    const c = m.get(email) ?? { email, name: who(d.customer), deals: [], value: 0, booked: 0, quoted: 0, last: 0, needs: false };
    c.deals.push(d); c.value += amount(d.quote) ?? 0; c.booked += d.booking || d.status === "booked" ? 1 : 0; c.quoted += d.quote ? 1 : 0;
    c.last = Math.max(c.last, d.updated_at); c.needs = c.needs || groupOf(d) === "needs"; m.set(email, c);
  }
  return [...m.values()].sort((a, b) => b.last - a.last);
}
const top = (xs: string[]) => { const m = new Map<string, number>(); xs.forEach((x) => m.set(x, (m.get(x) ?? 0) + 1)); return [...m.entries()].sort((a, b) => b[1] - a[1]); };
/** What the record says about a customer, as short facts. Nothing here is guessed: each line is counted from their shipments. */
export function known(c: Cust): [string, string][] {
  const out: [string, string][] = [], n = c.deals.length;
  const from = top(c.deals.map((d) => ends(d)?.[0]).filter((x): x is string => !!x));
  const to = top(c.deals.map((d) => ends(d)?.[1]).filter((x): x is string => !!x));
  const pref = top(c.deals.map((d) => d.preference).filter((x): x is string => !!x));
  const w = median(c.deals.map((d) => Number(d.weight_kg)).filter((x) => x > 0));
  const q = median(c.deals.map((d) => amount(d.quote)).filter((x): x is number => x != null));
  const t = median(c.deals.map((d) => d.response_seconds).filter((x): x is number => x != null));
  if (from.length) out.push(["Ships from", city(from[0][0]) + (n > 1 ? ", " + from[0][1] + " of " + n + " requests" : "")]);
  if (to.length) out.push(["Sends to", to.slice(0, 3).map((x) => city(x[0])).join(", ")]);
  if (pref.length) out.push(["Asks for", pref[1] && pref[0][1] === pref[1][1] ? pref[0][0] + " and " + pref[1][0] + ", about as often" : "the " + pref[0][0] + " option" + (n > 1 ? ", " + pref[0][1] + " of " + n + " times" : "")]);
  if (w != null) out.push(["Typical shipment", Math.round(w).toLocaleString("en-US") + " kg" + (q != null ? ", around " + money(q).replace(/\.\d\d$/, "") : "")]);
  if (c.quoted) out.push(["Books", c.booked + " of " + c.quoted + " quotes"]);
  if (t != null && t >= 1) out.push(["We answer in", Math.round(t) + " s"]);
  return out;
}
