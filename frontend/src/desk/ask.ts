import type { DealRow } from "../api";
import type { Matrix } from "./analysis";
import { CITY, LANES, ORIGINS } from "./network";
import { Cust, amount, city, customers, ends, groupOf, kg, lane, median, money, name, since, why } from "./util";

// The ask bar. It answers from the desk's own record, in code: no model call, no cost, the same answer every time.
// Three things it can do for you go through the API the desk already has, each after one click on the button.
export type Act = { label: string; kind: "tell"; deal: string; text: string };
export type Answer = { via?: "assistant" | "record"; text: string; rows?: DealRow[]; facts?: [string, string][]; customer?: string; act?: Act; page?: "ship" | "cust" | "net"; matrix?: Matrix };
export const TRY = ["What should I look at?", "Give me the overview", "Which airline do we book most?", "Which quotes are still open?", "Cheapest way to Hong Kong"];

const plural = (n: number, one: string, many: string) => n + " " + (n === 1 ? one : many);
const CODES = Object.keys(CITY);

function places(q: string): string[] {
  const up = q.toUpperCase().match(/\b[A-Z]{3}\b/g) ?? [], low = q.toLowerCase();
  const byCode = up.filter((c) => CODES.includes(c));
  const byCity = CODES.filter((c) => low.includes(CITY[c].toLowerCase()) || low.includes(CITY[c].toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")));
  return [...new Set([...byCode, ...byCity])];
}
function customerIn(q: string, list: Cust[]): Cust | null {
  const low = q.toLowerCase();
  return list.find((c) => low.includes(c.name.toLowerCase())) ?? list.find((c) => c.name.toLowerCase().split(/\s+/).some((w) => w.length > 3 && low.includes(w))) ?? null;
}
function overview(deals: DealRow[]): Answer {
  const g = (x: string) => deals.filter((d) => groupOf(d) === x), needs = g("needs"), open = g("quoted");
  const quoted = deals.filter((d) => d.quote), t = median(quoted.map((d) => d.response_seconds).filter((x): x is number => x != null));
  const sum = quoted.reduce((s, d) => s + (amount(d.quote) ?? 0), 0);
  return { text: needs.length ? plural(needs.length, "shipment is", "shipments are") + " flagged for a look. Everything else ran without a note." : "Nothing is flagged. Everything ran without a note.",
    facts: [["Requests", String(deals.length)], ["Quoted", quoted.length + (t != null && t >= 1 ? ", typically after " + Math.round(t) + " s" : "")], ["Booked", String(g("booked").length)],
      ["Quotes without a yes", String(open.length)], ["In progress", String(g("working").length)], ["Lost", String(g("lost").length)], ["Quoted in total", money(sum)]], rows: needs };
}

export function answer(question: string, deals: DealRow[]): Answer {
  const q = question.trim(), low = q.toLowerCase(), list = customers(deals), who = customerIn(q, list), at = places(q);
  const g = (x: string) => deals.filter((d) => groupOf(d) === x);
  if (!q) return { text: "Ask about a customer, a city or a price. Or say what should happen." };

  // things it does for you
  const tell = q.match(/^(?:tell|ask|remind)\s+(?:the ai worker\s+)?(?:about\s+|for\s+|on\s+)?(.+?)\s*[:,]\s*(.+)$/i);
  if (tell && who) return { text: "This goes to Giulia for " + who.name + "'s latest shipment: “" + tell[2] + "”", act: { label: "Send it", kind: "tell", deal: who.deals[0].id, text: tell[2] }, rows: [who.deals[0]] };

  // prices and the network
  const dest = at.find((c) => !ORIGINS.includes(c)), org = at.find((c) => ORIGINS.includes(c));
  if (org && /clos|shut|strike|down|outage|if\b/.test(low)) {
    const ls = LANES.filter((l) => l[0] === org), lost = [...new Set(ls.map((l) => l[1]))].filter((d) => !LANES.some((l) => l[1] === d && l[0] !== org));
    const hit = deals.filter((d) => ends(d)?.[0] === org && ["needs", "working", "quoted"].includes(groupOf(d)));
    return { text: "If " + city(org) + " closes, " + (ls.length - lost.length) + " of " + ls.length + " destinations still fly from another German airport.", page: "net", rows: hit, facts: [["Lose their only route", lost.length ? lost.map(city).join(", ") : "none"], ["Open shipments from " + city(org), String(hit.length)]] };
  }
  if (dest && /price|cost|cheap|rate|how much|quote for|fastest/.test(low)) {
    const ls = LANES.filter((l) => l[1] === dest && (!org || l[0] === org)).sort((a, b) => a[2][0][1] - b[2][0][1]);
    if (!ls.length) return { text: "No rate sheet covers " + city(dest) + (org ? " from " + city(org) : "") + ". Giulia asks the rate portal for that." };
    return { text: city(dest) + " is cheapest from " + city(ls[0][0]) + " with " + ls[0][2][0][0] + ": " + ls[0][2][0][1].toFixed(2) + " EUR per kg, " + ls[0][2][0][2] + " days.", page: "net",
      facts: ls.map((l) => ["From " + city(l[0]), l[2].map((a) => a[0] + " " + a[1].toFixed(2)).join(" · ") + " EUR/kg"] as [string, string]).concat([["Priced for", "100 kg, fuel and security included"]]) };
  }
  const airline = [...new Set(LANES.flatMap((l) => l[2].map((a) => a[0])))].find((a) => low.includes(a.toLowerCase()));
  if (airline) {
    const mine = LANES.filter((l) => l[2].some((a) => a[0] === airline));
    return { text: airline + " flies " + plural(mine.length, "route", "routes") + " for us and is the cheapest on " + LANES.filter((l) => l[2][0][0] === airline).length + ".", page: "net",
      facts: [["From", [...new Set(mine.map((l) => l[0]))].map(city).join(", ")], ["To", [...new Set(mine.map((l) => l[1]))].slice(0, 8).map(city).join(", ") + (mine.length > 8 ? " and more" : "")]] };
  }

  // one customer
  if (who) {
    const open = who.deals.filter((d) => groupOf(d) === "needs");
    return { text: who.name + ": " + plural(who.deals.length, "shipment", "shipments") + ", " + who.booked + " booked, " + money(who.value) + " quoted." + (open.length ? " " + plural(open.length, "one is", "are") + " flagged." : ""), rows: who.deals.slice(0, 5), customer: who.email };
  }

  // lists
  if (/overview|summary|how (are|is|did)|status|last night|overnight|today|report|recap|berblick|bersicht/.test(low)) return overview(deals);
  if (/need|flag|look at|attention|for me|to do|todo|unusual|odd|check/.test(low)) { const n = g("needs"); return n.length ? { text: plural(n.length, "shipment is", "shipments are") + " flagged. Giulia already handled each and left a note.", rows: n } : { text: "Nothing is flagged." }; }
  if (/open quote|still open|no answer|no yes|follow.?up|chase|waiting for (the )?customer|pending|not booked/.test(low)) { const o = g("quoted").sort((a, b) => a.updated_at - b.updated_at); return o.length ? { text: plural(o.length, "quote is", "quotes are") + " out without a yes. The oldest went out " + since(o[0].updated_at) + " ago.", rows: o.slice(0, 8), page: "ship" } : { text: "Every quote has an answer." }; }
  if (/lost|lose|declin|reject/.test(low)) { const l = g("lost"); return l.length ? { text: plural(l.length, "request was", "requests were") + " lost. Open one to read why.", rows: l.slice(0, 8), page: "ship" } : { text: "Nothing was lost." }; }
  if (/book|confirmed|flying/.test(low)) { const b = g("booked"); return { text: plural(b.length, "shipment is", "shipments are") + " booked.", rows: b.slice(0, 8), page: "ship" }; }
  if (/progress|working|right now|pricing|busy/.test(low)) { const w = g("working"); return w.length ? { text: "Giulia is on " + plural(w.length, "shipment", "shipments") + " right now.", rows: w } : { text: "Nothing is in progress." }; }
  if (/slow|longest|took/.test(low)) { const s = deals.filter((d) => d.response_seconds != null).sort((a, b) => b.response_seconds! - a.response_seconds!).slice(0, 5); return { text: "These quotes took the longest.", rows: s, facts: s.map((d) => [name(d), Math.round(d.response_seconds!) + " s"] as [string, string]) }; }
  if (/biggest|largest|highest|top|most valuable/.test(low)) { const s = deals.filter((d) => amount(d.quote) != null).sort((a, b) => amount(b.quote)! - amount(a.quote)!).slice(0, 5); return { text: "The biggest quotes on the desk.", rows: s }; }
  if (/customer/.test(low)) return { text: plural(list.length, "customer", "customers") + " on record. The latest request came from " + (list[0]?.name ?? "nobody") + ".", page: "cust" };

  // a place, or plain words
  if (at.length) { const r = deals.filter((d) => { const e = ends(d); return e && at.every((c) => e.includes(c)); }); return r.length ? { text: plural(r.length, "shipment", "shipments") + (at.length === 2 ? " between " + city(at[0]) + " and " + city(at[1]) : " through " + city(at[0])) + ".", rows: r.slice(0, 8), page: "ship" } : { text: "No shipment through " + at.map(city).join(" and ") + " on the desk." }; }
  const words = low.split(/\s+/).filter((w) => w.length > 2);
  const r = deals.filter((d) => words.every((w) => (name(d) + " " + (d.subject ?? "") + " " + (d.booking ?? "") + " " + lane(d) + " " + kg(d) + " " + why(d)).toLowerCase().includes(w)));
  return r.length ? { text: plural(r.length, "shipment matches", "shipments match") + ".", rows: r.slice(0, 8) } : { text: "Nothing on the desk matches that. Try a customer, a city, or ask what is flagged." };
}

/** The same question to the assistant behind /api/ask: it reads the register with its own tools (our own model key,
 * answers checked against the register). The page sends what it computed, which the assistant may read too. Throws when there is none. */
export async function askModel(question: string, deals: DealRow[], desk: unknown, earlier: { q: string; a: string }[] = []): Promise<Answer> {
  const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, desk, earlier }) });
  if (r.status === 429) return { via: "assistant", text: "Too many questions for a minute. Try again shortly." };
  if (!r.ok) throw new Error(String(r.status));
  const j = await r.json() as { text: string; facts: [string, string][]; rows: string[]; customer: string | null; page: Answer["page"] | null; act: { kind: "tell"; deal: string; text: string } | null };
  const list = customers(deals), c = j.customer ? list.find((x) => x.email === j.customer || x.name === j.customer) : undefined;
  const label = j.act ? "Tell Giulia: " + j.act.text : "";
  return { via: "assistant", text: j.text, facts: j.facts?.length ? j.facts : undefined, rows: j.rows.map((id) => deals.find((d) => d.id === id)).filter((d): d is DealRow => !!d),
    customer: c?.email, page: j.page ?? undefined, act: j.act ? { label, ...j.act } : undefined };
}
