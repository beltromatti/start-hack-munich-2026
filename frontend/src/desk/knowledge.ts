import { useEffect, useRef, useState } from "react";
import { Deal, DealRow, get } from "../api";
import { who } from "../format";
import { LANES } from "./network";
import { languageOf } from "./timeline";
import { Cust, LABEL, amount, city, customers, ends, flagNote, groupOf, kg, known, median, setFlagNote, since } from "./util";

// What the record teaches us, counted from the finished and running shipments: how each carrier answers and how
// each customer decides. Nothing is stored anywhere new: it is read from the same deals the desk shows.
export type Offer = { airline: string; total: number; days: number; source: string };
export type Seen = { id: string; customer: string; offers: Offer[]; chosen: string | null; lang: string | null; notes: string[];
  replies: { from: string; seconds: number | null; files: string[] }[]; yesAfter: number | null; flag: string | null };
export type CarrierFacts = { airline: string; offers: number; chosen: number; cheapest: number; above: number | null; via: string[]; reply: number | null; files: string[] };

const parse = (s: unknown): Record<string, any> | null => { if (typeof s !== "string" || !s) return null; try { return JSON.parse(s); } catch { return null; } };
const ms = (t: string | null | undefined) => t ? Date.parse(t) : NaN;
const VIA: Record<string, string> = { sheet: "rate sheet", "rate sheet": "rate sheet", portal: "rate portal", portal_memory: "rate portal", portal_page: "rate portal", ratedesk: "rate desk", mail: "mail", email: "mail", "carrier mail": "mail" };
const fileKind = (n: string) => /\.pdf$/i.test(n) ? "PDF" : /\.(xlsx?|csv)$/i.test(n) ? "spreadsheet" : /\.(docx?)$/i.test(n) ? "Word file" : /\.(mp3|wav|m4a|ogg)$/i.test(n) ? "voice message" : /\.(png|jpe?g)$/i.test(n) ? "picture" : "file";
const key = (s: string) => s.toLowerCase().replace(/[^a-z]/g, "");

export function read(deal: Deal): Seen {
  const items = deal.session?.items ?? [], outs = new Map<string, Record<string, any> | null>();
  for (const it of items) if (it.type === "function_call_output" && it.call_id) outs.set(it.call_id, parse(it.output));
  let offers: Offer[] = [], chosen: string | null = deal.data.booking?.airline || null, optionId: string | null = null, opts: any[] = [];
  for (const it of items) {
    if (it.type !== "function_call") continue;
    const a = parse(it.arguments) ?? {}, o = outs.get(it.call_id ?? "");
    if (it.name === "get_offers" && o?.options?.length) { opts = o.options; offers = opts.map((x) => ({ airline: String(x.airline), total: parseFloat(x.total), days: Number(x.transit_days), source: VIA[x.source] ?? String(x.source) })); }
    if (it.name === "send_mail" && a.kind === "quote" && !optionId) optionId = a.option_id ?? null;
  }
  if (!chosen && optionId) chosen = opts.find((x) => x.option === optionId)?.airline ?? null;
  const start = ms(deal.data.received_at);
  const replies = (deal.carrier_mails ?? []).map((m) => ({ from: who(m.sender), seconds: Number.isFinite(ms(m.received_at) - start) ? Math.max(0, Math.round((ms(m.received_at) - start) / 1000)) : null, files: (m.attachments ?? []).map((a) => fileKind(a.filename)) }));
  const out = deal.mails.find((m) => m.direction === "out"), yes = out ? deal.mails.find((m) => m.direction === "in" && m.id > out.id) : undefined;
  const gap = yes && out ? (ms(yes.received_at) - ms(out.received_at)) / 1000 : NaN;
  return { id: deal.id, customer: deal.data.customer, offers, chosen, lang: languageOf(deal), notes: (deal.data.notes ?? []).filter((n) => n.flag === "none" || !n.flag).map((n) => n.text), flag: (deal.data.notes ?? []).filter((n) => n.flag === "yellow" || n.flag === "red").map((n) => n.text).pop() ?? null, replies, yesAfter: deal.data.booking && Number.isFinite(gap) && gap > 0 ? Math.round(gap) : null };
}

/** Deal details, loaded once each and again when a deal changes. */
export function useKnowledge(deals: DealRow[]): { seen: Seen[]; ready: boolean } {
  const cache = useRef(new Map<string, { at: number; seen: Seen }>());
  const busy = useRef(false);
  const [tick, setTick] = useState(0);
  const want = deals.slice(0, 400);
  const stale = want.filter((d) => cache.current.get(d.id)?.at !== d.updated_at);
  useEffect(() => {
    if (busy.current || !stale.length) return;
    busy.current = true;
    const batch = stale.slice(0, 6);
    Promise.all(batch.map((d) => get<Deal>("/api/deals/" + d.id).then((x) => { const s = read(x); cache.current.set(d.id, { at: d.updated_at, seen: s }); setFlagNote(d.id, s.flag); }).catch(() => undefined)))
      .finally(() => { busy.current = false; setTick((t) => t + 1); });
  }, [stale.length, tick]);
  return { seen: want.map((d) => cache.current.get(d.id)?.seen).filter((x): x is Seen => !!x), ready: !stale.length };
}

export function carrierFacts(seen: Seen[]): CarrierFacts[] {
  const m = new Map<string, { offers: number; chosen: number; cheapest: number; above: number[]; via: Map<string, number>; reply: number[]; files: Set<string> }>();
  const at = (a: string) => { if (!m.has(a)) m.set(a, { offers: 0, chosen: 0, cheapest: 0, above: [], via: new Map(), reply: [], files: new Set() }); return m.get(a)!; };
  for (const s of seen) {
    const best = Math.min(...s.offers.map((o) => o.total));
    for (const o of s.offers) { const c = at(o.airline); c.offers++; if (o.total === best) c.cheapest++; else c.above.push(o.total / best - 1); c.via.set(o.source, (c.via.get(o.source) ?? 0) + 1); }
    if (s.chosen) at(s.chosen).chosen++;
    for (const r of s.replies) { const a = [...m.keys()].find((k) => key(k).startsWith(key(r.from).slice(0, 6)) || key(r.from).startsWith(key(k).slice(0, 6))); if (!a) continue; if (r.seconds != null) at(a).reply.push(r.seconds); r.files.forEach((f) => at(a).files.add(f)); }
  }
  return [...m.entries()].map(([airline, c]) => ({ airline, offers: c.offers, chosen: c.chosen, cheapest: c.cheapest, above: c.above.length ? c.above.reduce((x, y) => x + y, 0) / c.above.length : null,
    via: [...c.via.entries()].sort((x, y) => y[1] - x[1]).map((x) => x[0]), reply: median(c.reply), files: [...c.files] })).sort((a, b) => b.chosen - a.chosen || b.offers - a.offers);
}

export function customerExtra(c: Cust, seen: Seen[]): [string, string][] {
  const mine = seen.filter((s) => s.customer === c.email), out: [string, string][] = [];
  const yes = median(mine.map((s) => s.yesAfter).filter((x): x is number => x != null));
  const lang = mine.map((s) => s.lang).find(Boolean);
  const flown = mine.map((s) => s.chosen).filter((x): x is string => !!x), fav = flown.length ? [...new Set(flown)].map((a) => [a, flown.filter((x) => x === a).length] as [string, number]).sort((a, b) => b[1] - a[1])[0] : null;
  if (yes != null) out.push(["Says yes after", yes < 90 ? yes + " s" : yes < 5400 ? Math.round(yes / 60) + " min" : Math.round(yes / 3600) + " h"]);
  if (fav && flown.length > 1 && fav[1] * 2 >= flown.length) out.push(["Mostly flies with", fav[0] + ", " + fav[1] + " of " + flown.length]);
  if (lang) out.push(["Writes in", lang]);
  return out;
}

/** One line of what to expect on a shipment, from the customer's history. Empty when there is too little to say. */
export function expect(d: DealRow, list: Cust[], seen: Seen[]): string {
  const c = list.find((x) => x.email === d.customer);
  if (!c || c.quoted < 2) return "";
  const yes = customerExtra(c, seen).find((x) => x[0] === "Says yes after");
  return c.name + " booked " + c.booked + " of " + c.quoted + " quotes so far" + (yes ? " and usually says yes after " + yes[1] : "") + ".";
}

/** The desk as compact data for the ask field: only what a question can be about, nothing private beyond the record. */
export function context(deals: DealRow[], seen: Seen[]) {
  const by = new Map(seen.map((s) => [s.id, s])), list = customers(deals);
  return {
    asked_at: new Date().toISOString().slice(0, 16),
    shipments: deals.slice(0, 70).map((d) => { const e = ends(d), s = by.get(d.id), t = s?.offers.map((o) => o.total) ?? [];
      return { id: d.id, customer: who(d.customer), from: e ? city(e[0]) : null, to: e ? city(e[1]) : null, route: e ? e[0] + "-" + e[1] : null, weight: kg(d) || null, wants: d.preference, status: LABEL[groupOf(d)].toLowerCase(),
        quote_eur: amount(d.quote), answered_in_s: d.response_seconds != null ? Math.round(d.response_seconds) : null, last_change: since(d.updated_at) + " ago", airline: s?.chosen ?? null,
        cheapest_offer_eur: t.length ? Math.min(...t) : null, dearest_offer_eur: t.length ? Math.max(...t) : null, flagged_note: flagNote(d) }; }),
    customers: list.map((c) => ({ name: c.name, shipments: c.deals.length, booked: c.booked, quotes: c.quoted, quoted_eur: Math.round(c.value), facts: Object.fromEntries([...known(c), ...customerExtra(c, seen)]), remembered: [...new Set(seen.filter((s) => s.customer === c.email).flatMap((s) => s.notes))] })),
    carriers: carrierFacts(seen).map((c) => ({ airline: c.airline, offers_to_us: c.offers, times_chosen: c.chosen, times_cheapest: c.cheapest, typically_above_best_pct: c.above != null ? Math.round(c.above * 100) : null, answers_by: c.via, typical_reply_s: c.reply, sends: c.files })),
    rate_sheets: { note: "EUR per kg at 100 kg, fuel and security included, cheapest airline first", routes: LANES.map((l) => l[0] + "-" + l[1] + ": " + l[2].map((a) => a[0] + " " + a[1].toFixed(2) + " (" + a[2] + "d)").join(", ")) },
    not_recorded: ["our margin or buying price", "customer phone numbers", "anything outside this desk"],
  };
}
