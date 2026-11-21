// Synthetic 5U night: one RFQ every 6 minutes, carriers answering, quotes, bookings, disruptions.
// Pure functions of a simulated clock, so every view shows the same "live" world.
// Replace with real data from /api once the pipeline runs.
import { TARIFFS, type Tariff } from "./lanes";

export type Bucket = "green" | "yellow" | "red";
export type Stage = "received" | "pricing" | "waiting" | "quoted" | "accepted" | "booked" | "lost" | "missed";
export type MailKind = "rfq" | "bid" | "portal" | "tariff" | "tracking" | "booking" | "quote";

export interface Bid { carrier: string; source: "portal" | "email" | "sheet"; total: number; transitDays: number; at: number; rateId?: string }
export interface Step { t: number; agent: string; label: string; ms: number; costUsd: number; level: "ok" | "warn" | "error" }
export interface Mail { id: string; t: number; kind: MailKind; from: string; to: string; subject: string; body: string }
export interface Points { accuracy: number; cost: number; time: number; total: number; accepted: boolean }
export interface Case {
  id: string; round: number; start: number; customer: string; contact: string; origin: string; destination: string;
  weightKg: number; volumeCbm: number; chargeableKg: number; wants: "cheapest" | "fastest"; pickupZone: string;
  bucket: Bucket; reason: string | null; bids: Bid[]; chosen: Bid; bestPrice: number; quoteTotal: number;
  quoteAt: number; costUsd: number; outcome: "accepted" | "lost" | "missed"; steps: Step[]; mails: Mail[]; points: Points;
}
export interface View extends Case { stage: Stage; age: number; visibleSteps: Step[]; visibleMails: Mail[] }

export const ROUND_SEC = 360;
export const SPEED = 20; // 1 real second = 20 simulated seconds, so a 6-minute round takes 18 s
const DAY0 = Date.parse("2026-11-21T16:00:00+01:00") / 1000;

const CUSTOMERS = [
  ["Alpenwerk GmbH", "Lena Huber"], ["Isar Robotics", "Tobias Kern"], ["Hanse Pharma", "Mira Lindqvist"],
  ["Lindauer Präzision", "Jonas Baumann"], ["Mainfeld Textil", "Sara Okafor"], ["Rheinkraft Pumps", "Paul Weiss"],
  ["Nordlicht Optics", "Eva Schulz"], ["Bergmann Medtech", "Luca Rossi"],
];
const ZONES = ["60 Frankfurt am Main", "50 Köln", "20 Hamburg", "40 Düsseldorf", "80 München"];
const RED = ["Portal returned 503 for this lane, booking only by email", "Tariff changed since last hour, prices no longer match",
  "Origin airport closed for freighters tonight", "No carrier serves this destination on the portal"];
const YELLOW = ["Volume weight above gross weight, check dimensions", "Rate sheet and portal disagree by more than 3 %",
  "Pickup zone not in the zone list", "Two carriers tie on the 50/50 price and speed score"];

function rng(seed: number) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; };
}

export function tariffPrice(t: Tariff, chargeable: number): number {
  let i = 0;
  for (let k = 0; k < t.breaks.length; k++) if (chargeable >= t.breaks[k]) i = k;
  let freight = Math.max(t.min, chargeable * t.rates[i]);
  if (i + 1 < t.breaks.length) freight = Math.min(freight, Math.max(t.min, t.breaks[i + 1] * t.rates[i + 1])); // next break may be cheaper
  return Math.round((freight + chargeable * (t.fuel + t.sec)) * 100) / 100;
}

const lanes = [...new Set(TARIFFS.map((t) => `${t.origin}-${t.destination}`))];

export function makeCase(round: number): Case {
  const r = rng(round * 7919 + 17);
  const lane = lanes[Math.floor(r() * lanes.length)];
  const [origin, destination] = lane.split("-");
  const carriers = TARIFFS.filter((t) => t.origin === origin && t.destination === destination);
  const [customer, contact] = CUSTOMERS[Math.floor(r() * CUSTOMERS.length)];
  const weightKg = Math.round(40 + r() * 1400);
  const volumeCbm = Math.round((weightKg / 167) * (0.6 + r() * 0.9) * 10) / 10;
  const chargeableKg = Math.max(weightKg, Math.round(volumeCbm * 167));
  const wants = r() < 0.65 ? "cheapest" : "fastest";
  const start = DAY0 + (round - 1) * ROUND_SEC;
  const roll = r();
  const bucket: Bucket = roll < 0.12 ? "red" : roll < 0.32 ? "yellow" : "green";
  const reason = bucket === "red" ? RED[Math.floor(r() * RED.length)] : bucket === "yellow" ? YELLOW[Math.floor(r() * YELLOW.length)] : null;

  const bids: Bid[] = carriers.map((t, i) => {
    const source: Bid["source"] = i === 0 ? "portal" : r() < 0.5 ? "email" : "sheet";
    const at = source === "portal" ? 6 : source === "sheet" ? 2 : 40 + Math.round(r() * 110);
    return { carrier: t.airline, source, total: tariffPrice(t, chargeableKg) * (source === "email" ? 0.97 + r() * 0.08 : 1),
      transitDays: t.transit + (source === "email" && r() < 0.3 ? 1 : 0), at, rateId: source === "portal" ? `R-${round}x${i}k7` : undefined };
  }).map((b) => ({ ...b, total: Math.round(b.total * 100) / 100 }));
  const best = wants === "cheapest"
    ? bids.reduce((a, b) => (b.total < a.total ? b : a))
    : bids.reduce((a, b) => (b.transitDays < a.transitDays || (b.transitDays === a.transitDays && b.total < a.total) ? b : a));
  const miss = (bucket === "red" && r() < 0.7) || (bucket === "yellow" && r() < 0.2);
  const chosen = miss ? bids.reduce((a, b) => (b.total > a.total ? b : a)) : best;
  const quoteTotal = Math.round(chosen.total * (miss ? 1.06 : 1 + r() * 0.012) * 100) / 100;
  const lastBid = Math.max(...bids.map((b) => b.at));
  const quoteAt = Math.min(330, (bucket === "green" ? Math.min(lastBid, 75) : lastBid) + 12 + Math.round(r() * 20));
  const costUsd = bucket === "red" ? 0.018 + r() * 0.02 : bucket === "yellow" ? 0.004 + r() * 0.004 : 0.0009 + r() * 0.0012;
  const accepted = quoteTotal <= best.total * 1.05;
  const outcome: Case["outcome"] = quoteAt > 330 ? "missed" : accepted ? "accepted" : "lost";

  const acc = accepted ? Math.round(45 * Math.max(0, 1 - (quoteTotal / best.total - 1) / 0.05)) : 0;
  const cost = accepted ? Math.round(40 * Math.max(0, 1 - costUsd / 0.1)) : 0;
  const time = accepted ? Math.round(15 * (quoteAt <= 120 ? 1 : Math.max(0, (360 - quoteAt) / 240))) : 0;
  const points = { accuracy: acc, cost, time, total: acc + cost + time, accepted };

  const steps = ([
    { t: 1, agent: "router", label: "Mail sorted: customer RFQ", ms: 180, costUsd: 0.0002, level: "ok" },
    { t: 3, agent: "rfq", label: `Parsed: ${origin}→${destination}, ${weightKg} kg, ${volumeCbm} cbm, ${wants}`, ms: 1400, costUsd: costUsd * 0.4, level: "ok" },
    { t: 4, agent: "pricing", label: `Chargeable weight ${chargeableKg} kg (max of gross and cbm × 167)`, ms: 3, costUsd: 0, level: "ok" },
    ...bids.map((b) => ({ t: b.at, agent: b.source === "email" ? "carrier" : "pricing",
      label: `${b.carrier}: ${b.total.toFixed(2)} EUR, ${b.transitDays} d (${b.source})`, ms: b.source === "email" ? 900 : 120, costUsd: b.source === "email" ? costUsd * 0.15 : 0, level: "ok" as const })),
    ...(reason ? [{ t: 9, agent: "watcher", label: `${bucket.toUpperCase()}: ${reason}`, ms: 2200, costUsd: bucket === "red" ? costUsd * 0.4 : 0, level: bucket === "red" ? "error" as const : "warn" as const }] : []),
    { t: quoteAt - 6, agent: "pricing", label: `Best for "${wants}": ${chosen.carrier} ${chosen.total.toFixed(2)} EUR`, ms: 4, costUsd: 0, level: miss ? "warn" : "ok" },
    { t: quoteAt, agent: "writer", label: `Quote sent: ${quoteTotal.toFixed(2)} EUR all-in`, ms: 1100, costUsd: costUsd * 0.2, level: "ok" },
    ...(outcome === "accepted" ? [
      { t: quoteAt + 70, agent: "rfq", label: "Customer accepted", ms: 160, costUsd: 0, level: "ok" as const },
      { t: quoteAt + 80, agent: "booking", label: chosen.rateId ? `Booked by rate ID ${chosen.rateId}` : `Booking requested by email at ${chosen.carrier}`, ms: 400, costUsd: 0, level: "ok" as const },
    ] : outcome === "lost" ? [{ t: quoteAt + 60, agent: "rfq", label: "Rejected: more than 5 % above the best price", ms: 0, costUsd: 0, level: "error" as const }] : []),
  ] as Step[]).sort((a, b) => a.t - b.t);

  const ref = `Q-${String(round).padStart(4, "0")}`;
  const mails = ([
    { id: `${ref}-in`, t: 0, kind: "rfq", from: `${contact} <${contact.split(" ")[0].toLowerCase()}@${customer.split(" ")[0].toLowerCase()}.example>`, to: "us",
      subject: `Air freight ${origin} – ${destination}, ${weightKg} kg`,
      body: `Hello,\n\ncould you quote air freight from zone ${ZONES[round % ZONES.length].split(" ")[0]} (pickup) via ${origin} to ${destination}?\n${weightKg} kg, ${volumeCbm} cbm, ready tomorrow. We need the ${wants} option.\n\nThanks,\n${contact}\n${customer}` },
    ...bids.filter((b) => b.source === "email").map((b, i) => ({ id: `${ref}-bid${i}`, t: b.at, kind: "bid" as const, from: b.carrier, to: "us",
      subject: `Re: Bid request ${origin}-${destination}`, body: `We can offer ${b.total.toFixed(2)} EUR all-in, ${b.transitDays} days airport to airport.` })),
    { id: `${ref}-out`, t: quoteAt, kind: "quote", from: "us", to: contact, subject: `Re: Air freight ${origin} – ${destination}`,
      body: `Hi ${contact.split(" ")[0]},\n\nthanks for the request. For ${weightKg} kg from ${origin} to ${destination} the ${wants} option is ${chosen.carrier}: ${quoteTotal.toFixed(2)} EUR all-in, ${chosen.transitDays} days airport to airport, pickup included.\n\nShall I book it?\n\nBest,\nNight Desk` },
    ...(outcome === "accepted" ? [{ id: `${ref}-ok`, t: quoteAt + 70, kind: "rfq" as const, from: contact, to: "us", subject: "Re: Air freight", body: "Great, please book." }] : []),
  ] as Mail[]).sort((a, b) => a.t - b.t);

  return { id: ref, round, start, customer, contact, origin, destination, weightKg, volumeCbm, chargeableKg, wants,
    pickupZone: ZONES[round % ZONES.length], bucket, reason, bids, chosen, bestPrice: best.total, quoteTotal, quoteAt,
    costUsd, outcome, steps, mails, points };
}

const cache = new Map<number, Case>();
const get = (round: number) => { if (!cache.has(round)) cache.set(round, makeCase(round)); return cache.get(round)!; };

export function viewAt(c: Case, now: number): View {
  const age = now - c.start;
  const visibleSteps = c.steps.filter((s) => s.t <= age);
  const visibleMails = c.mails.filter((m) => m.t <= age);
  let stage: Stage = "received";
  if (age >= 4) stage = "pricing";
  if (age >= 7) stage = "waiting";
  if (age >= c.quoteAt) stage = "quoted";
  if (c.outcome === "missed" && age >= 360) stage = "missed";
  if (c.outcome === "lost" && age >= c.quoteAt + 60) stage = "lost";
  if (c.outcome === "accepted" && age >= c.quoteAt + 70) stage = "accepted";
  if (c.outcome === "accepted" && age >= c.quoteAt + 80) stage = "booked";
  return { ...c, stage, age, visibleSteps, visibleMails };
}

export function world(now: number) {
  const rounds = Math.max(1, Math.floor((now - DAY0) / ROUND_SEC) + 1);
  const cases = Array.from({ length: rounds }, (_, i) => viewAt(get(i + 1), now)).reverse();
  const done = cases.filter((c) => ["accepted", "booked", "lost", "missed"].includes(c.stage) || c.age > c.quoteAt + 90);
  const scored = done.filter((c) => c.points.accepted);
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
  return {
    now, cases, nextRfqIn: ROUND_SEC - ((now - DAY0) % ROUND_SEC),
    kpi: {
      rounds, points: sum(scored.map((c) => c.points.total)),
      acceptedRate: done.length ? scored.length / done.length : 0,
      avgResponse: done.length ? sum(done.map((c) => c.quoteAt)) / done.length : 0,
      costPerQuote: done.length ? sum(done.map((c) => c.costUsd)) / done.length : 0,
      open: cases.filter((c) => ["received", "pricing", "waiting"].includes(c.stage)).length,
      attention: cases.filter((c) => c.bucket !== "green" && c.age < 3600).length,
    },
  };
}
export type World = ReturnType<typeof world>;

export const START_AT = DAY0 + ROUND_SEC * 14 + 40; // open the demo ~1.5 h into the night
export const fmtTime = (s: number) => new Date(s * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin" });
export const fmtDur = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
export const eur = (n: number) => n.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
