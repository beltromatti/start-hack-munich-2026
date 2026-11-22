// Example data for looking at the desk without a backend (VITE_DEMO=1 at build time, or ?demo in the address).
// It answers the same paths as backend/app/main.py with the same shapes, from memory, and changes nothing anywhere.
// The agent in these examples works as the real one does: on its own, leaving a flagged note where a person may want to look.
import type { Board, Deal, DealRow, Health, Item, Mail, Usage } from "./api";

export const DEMO = import.meta.env.VITE_DEMO === "1" || new URLSearchParams(location.search).has("demo");

type Seed = {
  n: number; who: string; from: string; to: string; kg: number; pcs: number; goods: string; pref: "cheapest" | "fastest";
  status: string; quote?: string; secs?: number; airline?: string; days?: number; booking?: string; age: number;
  mail: string; subject: string; own?: string; after?: string; flag?: ["yellow" | "red", string]; memo?: string; changed?: [string, string]; history?: number;
};

const now = Math.floor(Date.now() / 1000);
const iso = (ago: number) => new Date((now - ago) * 1000).toISOString();
const hashOf = (t: string) => [...t].reduce((x, c) => (x * 31 + c.charCodeAt(0)) >>> 0, 7);
const CITIES: Record<string, string> = { FRA: "Frankfurt", MUC: "Munich", HAM: "Hamburg", DUS: "Düsseldorf", STR: "Stuttgart", ORD: "Chicago", DXB: "Dubai", JFK: "New York", SIN: "Singapore", NRT: "Tokyo", GRU: "São Paulo", LAX: "Los Angeles", SYD: "Sydney", PVG: "Shanghai", YYZ: "Toronto", MEX: "Mexico City", BOM: "Mumbai" };

const SEEDS: Seed[] = [
  { n: 2411, who: "hartmann.technik", from: "FRA", to: "ORD", kg: 480, pcs: 3, goods: "machine parts", pref: "cheapest", status: "booked", quote: "5655.55", secs: 44, airline: "Kestrel Airways", days: 4, booking: "KA-55018", age: 720, history: 5,
    subject: "Quote Frankfurt to Chicago", mail: "Hello,\nplease quote 3 crates of machine parts, 480 kg, Frankfurt to Chicago. Cheapest option, pickup on Tuesday.\n\nRegards\nClaudia Hartmann",
    changed: ["5655.55", "6221.11"], memo: "Wants pickup on Tuesdays.",
    after: "Hello Ms Hartmann,\nyour shipment is booked with Kestrel Airways and flies on Wednesday 25 November.\nOne thing changed: the airline raised its rate between our quote and the booking.\nTotal: 6221.11 EUR all-in\nIf that does not work for you, tell me today and I look for another flight.\n\nRegards\nGiulia",
    flag: ["yellow", "The airline booked 10 % above our quote: 6221.11 EUR instead of 5655.55. I told the customer the new total in the booking confirmation and offered to look for another flight."] },
  { n: 2414, who: "lumiere.cosmetics", from: "MUC", to: "DXB", kg: 212, pcs: 14, goods: "cosmetics", pref: "cheapest", status: "quoted", quote: "1186.20", secs: 47, airline: "Elbflug Air Freight", days: 4, age: 240, history: 3,
    subject: "Request: 14 cartons to Dubai", mail: "Hello,\nwe need to ship 14 cartons of cosmetics, 212 kg, about 2.78 cbm, from Munich to Dubai. Cheapest option please. Packing list attached.\n\nJulien Moreau",
    memo: "Sends a packing list with every request. Its figures count when the mail differs.",
    own: "Hello Mr Moreau,\ncheapest is Elbflug Air Freight, 4 days door to airport Dubai.\nTotal: 1186.20 EUR all-in\nI priced the 1.92 cbm from your packing list. Your mail says 2.78 cbm, and with that volume the total is 1717.90 EUR.\nA short yes and I book it.\n\nRegards\nGiulia",
    flag: ["yellow", "The packing list says 1.92 cbm and the mail says 2.78 cbm. I priced from the packing list and said so in the quote. With the mail's volume the total would be 1717.90 EUR."] },
  { n: 2416, who: "brandt.spielwaren", from: "HAM", to: "JFK", kg: 95, pcs: 2, goods: "toys", pref: "fastest", status: "waiting_customer", age: 60, history: 4,
    subject: "Change of delivery address", mail: "Hello,\nplease change the delivery address of our booked shipment to the one below and send all booking documents to this mail address.\n\nT. Brandt",
    memo: "Only Tobias Brandt changes a booking, and only from his known address.",
    own: "Hello,\nthe booking stays as it is for now. Which booking reference is it about? Then I can check it with the contact we have on file.\n\nRegards\nGiulia",
    flag: ["red", "The sender address is one character off the one we know (brandt.spie1waren) and asks to move a booked shipment. I changed nothing and asked for the booking reference."] },
  { n: 2417, who: "baltic.tools", from: "HAM", to: "SIN", kg: 1240, pcs: 6, goods: "hand tools", pref: "cheapest", status: "pricing", age: 180, history: 4, subject: "Rate request Hamburg to Singapore", mail: "Hi,\n6 pallets of hand tools, 1240 kg, Hamburg to Singapore. Cheapest please, ready on Wednesday.\n\nThanks\nMarta" },
  { n: 2418, who: "oberland.optik", from: "MUC", to: "NRT", kg: 64, pcs: 1, goods: "lenses", pref: "fastest", status: "waiting_customer", age: 360, history: 2, subject: "Urgent: lenses to Tokyo", mail: "Hello,\none box of lenses, 64 kg, to Tokyo as fast as possible. Please collect it from us.\n\nStefan Huber",
    own: "Hello Mr Huber,\nwhich postcode do we collect the box from? Then I can give you the fastest connection with pickup.\n\nRegards\nGiulia" },
  { n: 2409, who: "rheintal.pharma", from: "FRA", to: "GRU", kg: 320, pcs: 4, goods: "lab supplies", pref: "fastest", status: "quoted", quote: "3940.00", secs: 52, airline: "Riverbend Airlines Cargo", days: 2, age: 1080, history: 1, subject: "Lab supplies to São Paulo", mail: "Good morning,\n4 boxes of lab supplies, 320 kg, Frankfurt to São Paulo, fastest connection.\n\nDr. Anna Keller" },
  { n: 2405, who: "nordsee.audio", from: "HAM", to: "LAX", kg: 150, pcs: 2, goods: "loudspeakers", pref: "cheapest", status: "quoted", quote: "1422.80", secs: 41, airline: "Yellowtail Air Freight", days: 5, age: 1860, history: 1, subject: "Price HAM-LAX 150 kg", mail: "hey, need a price HAM to LAX, 150 kg, 2 boxes of speakers, cheapest pls.\n\nthx Jan" },
  { n: 2388, who: "sonnberg.keramik", from: "FRA", to: "SYD", kg: 275, pcs: 5, goods: "ceramics", pref: "cheapest", status: "quoted", quote: "2864.10", secs: 47, airline: "Helix Air Freight", days: 5, age: 3700, history: 1, subject: "Ceramics to Sydney", mail: "Hello,\n5 crates of ceramics, 275 kg, from Frankfurt to Sydney. The cheapest option is fine.\n\nLena Sonnberg" },
  { n: 2402, who: "kessler.maschinenbau", from: "STR", to: "PVG", kg: 2100, pcs: 8, goods: "gear units", pref: "cheapest", status: "booked", quote: "9318.40", secs: 39, airline: "Lumen Air Cargo", days: 4, booking: "LAC-48213", age: 3900, history: 6, memo: "Writes in German and formally. Asked to never fly with Zephyr Steppe Cargo again.", subject: "Gear units Stuttgart to Shanghai", mail: "Guten Tag,\nbitte um ein Angebot für 8 Kisten Getriebe, 2100 kg, Stuttgart nach Shanghai, günstigste Variante.\n\nMit freundlichen Grüßen\nUwe Kessler" },
  { n: 2398, who: "alpina.sport", from: "MUC", to: "YYZ", kg: 410, pcs: 7, goods: "ski boots", pref: "fastest", status: "booked", quote: "3077.25", secs: 43, airline: "Ibisair Cargo", days: 2, booking: "IBC-77120", age: 7300, history: 2, memo: "Needs every quote as a PDF as well.", subject: "Ski boots to Toronto", mail: "Hi,\n7 cartons of ski boots, 410 kg, Munich to Toronto, fastest please.\n\nMira" },
  { n: 2396, who: "vogel.sohn", from: "DUS", to: "MEX", kg: 88, pcs: 1, goods: "spare parts", pref: "fastest", status: "booked", quote: "986.50", secs: 45, airline: "Cobalt Skylift", days: 3, booking: "CSK-30955", age: 10900, history: 3, subject: "Spare part to Mexico City", mail: "Hello,\none box, 88 kg, spare parts, Düsseldorf to Mexico City. As fast as it goes.\n\nKarl Vogel" },
  { n: 2391, who: "elbe.chemie", from: "HAM", to: "BOM", kg: 600, pcs: 3, goods: "pigments", pref: "cheapest", status: "lost", quote: "3512.00", secs: 58, airline: "Fjordline Air Cargo", days: 4, age: 14500, history: 2, subject: "Pigments to Mumbai", mail: "Hello,\n3 drums of pigments, 600 kg, Hamburg to Mumbai, cheapest.\n\nInes Vogt" },
];

const mailOf = (who: string) => who + "@hackloop.mail";
const dealId = (n: number) => "deal-" + n;
const DESK = "desk@milan-forwarding.example";

function build(s: Seed): Deal {
  const id = dealId(s.n), cust = mailOf(s.who), root = s.n, items: Item[] = [], mails: Mail[] = [];
  const call = (name: string, args: unknown, out: unknown) => { const c = "c" + items.length; items.push({ type: "function_call", name, call_id: c, arguments: JSON.stringify(args) }); items.push({ type: "function_call_output", call_id: c, output: JSON.stringify(out) }); };
  const mailIn = (mid: number, ago: number, subject: string, body: string) => { mails.push({ id: mid, direction: "in", sender: cust, recipient: DESK, subject, body, received_at: iso(ago), kind: "request", attachments: mid === root && s.n === 2414 ? [{ id: 1, filename: "packing-list.pdf", content_type: "application/pdf", size: 48213 }] : null });
    items.push({ role: "user", content: "New mail in this thread: id " + mid + ", from " + cust + ", at " + iso(ago) + "\nTheir own words are in " + (s.who.startsWith("kessler") ? "German" : "English") + ".\nSubject: " + subject + "\n\n" + body }); };
  const mailOut = (mid: number, ago: number, kind: string, body: string, quote?: string) => { mails.push({ id: mid, direction: "out", sender: DESK, recipient: cust, subject: "Re: " + s.subject, body, received_at: iso(ago), kind });
    call("send_mail", { kind, option_id: kind === "quote" ? "A" : null, body }, { to: cust, sent: mid, recorded_quote: quote }); };
  mailIn(root, s.age, s.subject, s.n === 2414 ? s.mail + "\n\n[attachment packing-list.pdf]\n14 cartons, gross 212 kg, 1.92 cbm, cosmetics, non-hazardous" : s.mail);
  const OTHER = ["Wayzata Air Cargo", "Polaris Air Logistics", "Helix Air Freight", "Elbflug Air Freight", "Kestrel Airways", "Cobalt Skylift", "Orion Cargo Air"].filter((a) => a !== s.airline);
  const SRC = ["rate sheet", "portal", "carrier mail"], base = Number(s.quote ?? "0");
  const opts = s.airline && s.quote ? [
    { option: "A", airline: s.airline, transit_days: s.days ?? 4, total: s.quote, source: SRC[s.n % 3], pickup: { trucker: "Main Spedition", pickup_hours: 6 }, bookable_reference: null, carrier_note: null },
    { option: "B", airline: OTHER[s.n % OTHER.length], transit_days: 3, total: (base * (1.03 + (s.n % 7) / 100)).toFixed(2), source: SRC[(s.n + 1) % 3], pickup: { trucker: "Main Spedition", pickup_hours: 6 }, bookable_reference: "R-" + s.n, carrier_note: null },
    { option: "C", airline: OTHER[(s.n + 3) % OTHER.length], transit_days: 2, total: (base * (1.11 + (s.n % 9) / 100)).toFixed(2), source: "carrier mail", pickup: { trucker: "Nordtrans", pickup_hours: 4 }, bookable_reference: null, carrier_note: null },
  ] : [];
  if (s.status === "pricing") call("get_offers", { shipment: { origin_airport: s.from, destination_airport: s.to, weight: { value: s.kg, unit: "kg" } }, preference: s.pref }, { options: [], still_waiting_for: ["Polaris Air Logistics", "Meridian Freightways"] });
  if (opts.length) call("get_offers", { shipment: { origin_airport: s.from, destination_airport: s.to, weight: { value: s.kg, unit: "kg" } }, preference: s.pref }, { shipment: { chargeable_kg: s.n === 2414 ? 320 : s.kg }, options: opts, recommended: "A" });
  if (s.status === "waiting_customer" && s.own) mailOut(root + 1, s.age - 20, "question", s.own);
  if (s.quote && s.secs) mailOut(root + 1, s.age - s.secs, "quote", s.own ?? "Hello,\n" + s.pref + " is " + s.airline + ", " + s.days + " days airport to airport, pickup included.\nTotal: " + s.quote + " EUR all-in\nA short yes and I book it.\n\nRegards\nGiulia", s.quote + " EUR");
  if (s.booking && s.secs) {
    const wait = Math.min(Math.max(60, s.age - s.secs - 120), 240 + (hashOf(s.who) % 9) * 310);
    mailIn(root + 2, s.age - s.secs - wait, "Re: " + s.subject, "Yes, please book it.");
    call("book", { option_id: "A" }, { status: "confirmed", booking_reference: s.booking, team_reference: "MF-" + s.n, via: "portal" });
    mailOut(root + 3, s.age - s.secs - wait - 25, "booking_confirmation", s.after ?? "Hello,\nyour shipment is booked with " + s.airline + ", reference " + s.booking + ".\n\nRegards\nGiulia");
  }
  if (s.memo) call("note", { text: s.memo, flag: "none" }, { ok: true });
  if (s.flag) call("note", { text: s.flag[1], flag: s.flag[0] }, { ok: true });
  const d: Deal["data"] = { root, customer: cust, subject: s.subject, received_at: iso(s.age), preference: s.pref,
    request: { origin: s.from, destination: s.to, weight_kg: s.kg, chargeable_kg: s.n === 2414 ? 320 : s.kg, pieces: s.pcs, goods: s.goods },
    notes: [...(s.memo ? [{ at: now - s.age + 30, text: s.memo, flag: "none" }] : []), ...(s.flag ? [{ at: now - Math.max(20, s.age - 110), text: s.flag[1], flag: s.flag[0] }] : [])] };
  if (s.flag) d.flag = s.flag[0];
  if (s.quote && s.secs) d.quote = { amount: s.quote + " EUR", option: "A", response_seconds: s.secs };
  if (s.booking) d.booking = { booking_reference: s.booking, team_reference: "MF-" + s.n, status: "confirmed", airline: s.airline ?? "", route: s.from + "-" + s.to, via: "portal", amount: s.changed ? s.changed[1] : s.quote,
    ...(s.changed ? { price_changed: { quoted: s.changed[0] + " EUR", booked: s.changed[1] + " EUR" } } : {}) };
  const carrierMails: Mail[] = opts.filter((o) => o.source === "carrier mail").map((o, i) => ({ id: root + 20 + i, direction: "in" as const, sender: o.airline.toLowerCase().replace(/[^a-z]+/g, "-") + "@hackloop.mail", recipient: DESK,
    subject: "Re: Rate request " + s.from + "-" + s.to, body: "Our offer: " + o.total + " EUR, " + o.transit_days + " days.", received_at: iso(s.age - 18 - (hashOf(o.airline) % 6) * 9), kind: "bid",
    attachments: hashOf(o.airline) % 3 === 0 ? [{ id: 1, filename: "offer.pdf", content_type: "application/pdf", size: 31200 }] : hashOf(o.airline) % 3 === 1 ? [{ id: 1, filename: "rates.xlsx", size: 18400 }] : null }));
  return { id, status: s.status, updated_at: now - (s.flag ? Math.max(20, s.age - 110) : s.age), data: d, mails, carrier_mails: carrierMails, events: [], usage: { tokens_in: 5200, tokens_out: 410, llm_calls: 3, cost_usd: 0.0004 + (s.n % 7) / 20000 }, session: { status: "idle", items } };
}

// earlier requests of the same customers, so the customer base has a history
function past(s: Seed, k: number): Deal {
  const dests = ["ORD", "DXB", "JFK", "SIN", "NRT", "LAX", "SYD", "PVG", "YYZ", "MEX", "BOM"], to = dests[(s.n + k * 3) % dests.length];
  const kg = 80 + ((s.n * (k + 3)) % 17) * 60, won = (s.n + k) % 3 !== 0, q = (kg * (2.6 + ((s.n + k) % 9) / 5)).toFixed(2);
  return build({ ...s, n: s.n - 40 - k * 23, to, kg, pcs: 1 + (k % 5), status: won ? "booked" : k === 0 ? "quoted" : "lost", quote: q, secs: 38 + ((s.n + k) % 20), airline: ["Kestrel Airways", "Elbflug Air Freight", "Helix Air Freight", "Cobalt Skylift"][(s.n + k) % 4], days: 3 + (k % 3),
    booking: won ? "BK-" + (s.n * 7 + k) : undefined, age: 86400 * (2 + k * 4) + (s.n % 5000), subject: "Request " + CITIES[s.from] + " to " + (CITIES[to] ?? to), mail: "Hello,\n" + kg + " kg from " + CITIES[s.from] + " to " + (CITIES[to] ?? to) + ", " + s.pref + " please.\n\nRegards",
    own: undefined, after: undefined, flag: undefined, memo: undefined, changed: undefined });
}

let DEALS: Deal[] = SEEDS.flatMap((s) => [build(s), ...Array.from({ length: s.history ?? 0 }, (_, k) => past(s, k))]).sort((a, b) => b.updated_at - a.updated_at);

function row(d: Deal): DealRow {
  const r = d.data.request ?? {};
  return { id: d.id, status: d.status, updated_at: d.updated_at, customer: d.data.customer, subject: d.data.subject, route: r.origin + "-" + r.destination,
    weight_kg: r.weight_kg != null ? String(r.weight_kg) : null, preference: d.data.preference ?? null, quote: d.data.quote?.amount ?? null,
    response_seconds: d.data.quote?.response_seconds ?? null, booking: d.data.booking?.booking_reference ?? null, flag: d.data.flag ?? null, needs_person: null, cost_usd: d.usage.cost_usd };
}

const BOARD: Board = { me: { team: "start-milan", rank: 1, total: 10969.4, scores_revealed: true, requests: [] },
  public: { overview: { rounds_sent: 117, teams: 4, accepted: 101, bookings: 38 }, rounds: [],
    ranking: [["start-milan", 10969.4, 101, 117, 38], ["example-team-b", 10419.1, 96, 117, 35], ["example-team-c", 10399.8, 97, 117, 33], ["example-team-d", 10126.0, 93, 117, 31]].map((r, i) => ({ rank: i + 1, team: String(r[0]), name: String(r[0]), total: Number(r[1]), accepted: Number(r[2]), answered: Number(r[3]), accept_rate: Number(r[2]) / Number(r[3]), bookings: Number(r[4]), reference_team: false, human: 0 })) } };
let alerts = true;
// One request arrives half a minute after the page opens (the lookalike sender), so the desk visibly reacts.
const opened = Date.now(), LATE = "deal-2416";
function arrived(): Deal[] {
  if (real) return DEALS;
  if (Date.now() - opened < 30000) return DEALS.filter((d) => d.id !== LATE);
  const d = DEALS.find((x) => x.id === LATE);
  if (d && !(d as { shown?: boolean }).shown) { (d as { shown?: boolean }).shown = true; const t = Math.floor(Date.now() / 1000); d.updated_at = t - 4; d.data.received_at = new Date((t - 40) * 1000).toISOString(); d.mails.forEach((m, i) => { m.received_at = new Date((t - 40 + i * 22) * 1000).toISOString(); }); DEALS.sort((a, b) => b.updated_at - a.updated_at); }
  return DEALS;
}

// A recorded night instead of the examples, when the host serves one at /data/real.json (the repo ships none).
// Add ?example to the address to see the examples anyway.
let real: { label: string; deals: Deal[]; board: Board } | null = null;
const ready: Promise<void> = DEMO && !new URLSearchParams(location.search).has("example")
  ? fetch("/data/real.json").then((r) => (r.ok ? r.json() : null)).then((j) => { if (j && Array.isArray(j.deals) && j.deals.length) { real = j; DEALS = j.deals; } }).catch(() => undefined)
  : Promise.resolve();
/** What the data is, for the badge in the header: the label of a recorded night, or null for the examples. */
export const recorded = (): string | null => real?.label ?? null;

export async function demo<T>(path: string, body?: unknown): Promise<T> {
  await ready;
  const p = path.split("?")[0], b = (body ?? {}) as Record<string, unknown>;
  const out = (x: unknown) => Promise.resolve(JSON.parse(JSON.stringify(x)) as T);
  const one = p.match(/^\/api\/deals\/([^/]+)(?:\/(\w+))?$/);
  if (p === "/api/deals" || p === "/api/rfqs") return out(arrived().map(row));
  if (p === "/api/health") return out({ ok: true, worker: true, llm: "example data", models: { agent: "example", effort: "low" } } satisfies Health);
  if (p === "/api/usage") return out({ tokens_in: 612000, tokens_out: 48000, llm_calls: 351, cost_usd: 0.0447 } satisfies Usage);
  if (p === "/api/board") return out(real ? real.board : BOARD);
  if (p === "/api/operator") { if (body) alerts = !!b.on; return out({ on: alerts, autonomous: true, needed: [] }); }
  if (one) {
    const d = DEALS.find((x) => x.id === one[1]);
    if (!d) return Promise.reject(new Error("404 " + path));
    if (!one[2]) return out(d);
    if (one[2] === "reply") {
      const c = "c" + d.session!.items.length, id = d.data.root + 40 + d.session!.items.length;
      d.session!.items.push({ type: "function_call", name: "send_mail", call_id: c, arguments: JSON.stringify({ kind: "reply", body: String(b.body ?? "") }) });
      d.session!.items.push({ type: "function_call_output", call_id: c, output: JSON.stringify({ to: d.data.customer, sent: id }) });
      return out({ sent: id });
    }
    return out({ ok: true });
  }
  const sess = p.match(/^\/api\/sessions\/session-(\d+)\/message$/);
  if (sess) {
    const d = DEALS.find((x) => String(x.data.root) === sess[1]);
    if (d) { d.session!.items.push({ role: "user", content: "Message from " + String(b.who ?? "Sam") + " (a person on our team, at the desk): " + String(b.text ?? "") });
      d.session!.items.push({ type: "message", content: [{ type: "output_text", text: "Noted for this shipment. I follow it from here on." }] }); }
    return out({ ok: true });
  }
  return out([]);
}
