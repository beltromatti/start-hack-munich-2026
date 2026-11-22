import type { DealRow } from "../api";
import { Icon } from "./icons";
import type { Seen } from "./knowledge";
import { LANES } from "./network";
import { Cust, amount, city, ends, groupOf, median, money } from "./util";

// One customer at a glance: the customer in the middle, and around them what the record says. Where they ship,
// what they ship, what they ask for, how often they book, which airlines they end up on, and how long they have
// been with us. Every word on it is counted from their requests. Nothing is guessed, and a branch with nothing
// to say is left out.
type Hub = { id: string; icon: string; title: string; sub: string; leaves: string[] };
const tally = (xs: string[]) => [...new Set(xs)].map((x) => [x, xs.filter((y) => y === x).length] as [string, number]).sort((a, b) => b[1] - a[1]);
const ms = (t: number) => (t < 1e12 ? t * 1000 : t);
const dayOf = (t: number) => new Date(ms(t)).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const span = (s: number) => s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : Math.round(s / 3600) + " h";
const cut = (s: string, n = 30) => s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s;
const airlinesOn = (d: DealRow) => { const e = ends(d), l = e ? LANES.find((x) => x[0] === e[0] && x[1] === e[1]) : null; return l ? l[2].length : null; };

export function hubs(c: Cust, seen: Seen[]): Hub[] {
  const mine = seen.filter((s) => s.customer === c.email), n = c.deals.length, out: Hub[] = [];
  const from = tally(c.deals.map((d) => ends(d)?.[0]).filter((x): x is string => !!x)), to = tally(c.deals.map((d) => ends(d)?.[1]).filter((x): x is string => !!x));
  if (to.length) out.push({ id: "routes", icon: "mapPin", title: "Routes", sub: from.length ? "from " + city(from[0][0]) : to.length + " destinations", leaves: to.slice(0, 3).map(([code, k]) => "to " + city(code) + (k > 1 ? ", " + k + " times" : "")) });
  const kgs = c.deals.map((d) => Number(d.weight_kg)).filter((x) => x > 0), quotes = c.deals.map((d) => amount(d.quote)).filter((x): x is number => x != null);
  if (kgs.length) out.push({ id: "freight", icon: "package", title: "Freight", sub: Math.round(median(kgs)!).toLocaleString("en-US") + " kg typical", leaves: [quotes.length ? "around " + money(median(quotes)).replace(/\.\d\d$/, "") + " a shipment" : "", kgs.length > 1 ? "largest " + Math.round(Math.max(...kgs)).toLocaleString("en-US") + " kg" : "", c.value && quotes.length === c.quoted ? money(c.value).replace(/\.\d\d$/, "") + " quoted in all" : ""].filter(Boolean) });
  const prefs = tally(c.deals.map((d) => d.preference).filter((x): x is string => !!x));
  if (prefs.length) out.push({ id: "asks", icon: "tag", title: "Asks for", sub: "the " + prefs[0][0], leaves: prefs.slice(0, 2).map(([p, k]) => cap(p) + ", " + k + " of " + n) });
  const yes = median(mine.map((s) => s.yesAfter).filter((x): x is number => x != null)), t = median(c.deals.map((d) => d.response_seconds).filter((x): x is number => x != null && x >= 1));
  const lost = c.deals.filter((d) => d.status === "lost").length;
  if (c.quoted) out.push({ id: "books", icon: "plane", title: "Books", sub: c.booked + " of " + c.quoted + " quotes", leaves: [yes != null ? "says yes after " + span(yes) : "", t != null ? "we answer in " + span(t) : "", lost ? lost + " lost" : ""].filter(Boolean) });
  const flown = tally(mine.map((s) => s.chosen).filter((x): x is string => !!x));
  if (flown.length) out.push({ id: "air", icon: "network", title: "Flies with", sub: cut(flown[0][0], 18), leaves: flown.slice(0, 3).map(([a, k]) => cut(a, 22) + ", " + k + (k === 1 ? " time" : " times")) });
  const lang = mine.map((s) => s.lang).find(Boolean), first = Math.min(...c.deals.map((d) => ms(d.updated_at)));
  out.push({ id: "us", icon: "users", title: "With us", sub: n + (n === 1 ? " request" : " requests"), leaves: [n > 1 ? "since " + dayOf(first) : "", "last on " + dayOf(c.last), lang ? "writes in " + lang : ""].filter(Boolean) });
  return out.slice(0, 6);
}

/** What stands out about this customer, each sentence counted from their requests. */
export function insights(c: Cust, seen: Seen[]): string[] {
  const mine = seen.filter((s) => s.customer === c.email), out: string[] = [], n = c.deals.length;
  if (c.quoted >= 3) {
    if (c.booked / c.quoted >= 0.7) out.push(c.name + " books most of what we quote: " + c.booked + " of " + c.quoted + ".");
    else if (c.booked / c.quoted <= 0.4) out.push(c.name + " books " + c.booked + " of " + c.quoted + " quotes. A call before the next one may do more than a faster answer.");
  }
  const routes = tally(c.deals.map((d) => { const e = ends(d); return e ? e[0] + "-" + e[1] : ""; }).filter(Boolean));
  const main = routes[0] ? c.deals.find((d) => { const e = ends(d); return e && e[0] + "-" + e[1] === routes[0][0]; }) : null;
  const prefs = tally(c.deals.map((d) => d.preference).filter((x): x is string => !!x));
  if (main && airlinesOn(main) === 1) { const e = ends(main)!; out.push("Their main route, " + city(e[0]) + " to " + city(e[1]) + ", has only one airline on our rate sheets, so there is no second price to offer them."); }
  else if (prefs.length === 1 && prefs[0][1] >= 3) out.push(prefs[0][0] === "fastest" ? "They ask for the fastest option every time. Transit days matter more to them than the last euro." : "They ask for the cheapest option every time, so a second airline on their routes is worth more than speed.");
  const to = tally(c.deals.map((d) => ends(d)?.[1]).filter((x): x is string => !!x));
  if (to[0] && n >= 4 && to[0][1] * 2 >= n) out.push(to[0][1] + " of their " + n + " requests go to " + city(to[0][0]) + ".");
  const yes = median(mine.map((s) => s.yesAfter).filter((x): x is number => x != null));
  if (yes != null && yes <= 900 && out.length < 3) out.push("When they book, the yes comes within " + span(yes) + ".");
  if (c.needs && out.length < 3) out.push("One of their shipments carries a note from Giulia.");
  return out.slice(0, 3);
}

const W = 1000, H = 560, CX = 500, CY = 280;
export function CustomerMap({ c, seen }: { c: Cust; seen: Seen[] }) { return <NodeMap name={c.name} hs={hubs(c, seen)} />; }

/** The same picture for anything with a name and branches: a customer, an airline. */
export function NodeMap({ name, hs }: { name: string; hs: Hub[] }) {
  const left = hs.filter((_, i) => i % 2 === 0), right = hs.filter((_, i) => i % 2 === 1);
  const place = (side: Hub[], dir: 1 | -1) => side.map((h, i) => { const a = (i - (side.length - 1) / 2) * 0.74, x = CX + dir * 262 * Math.cos(a), y = CY + 205 * Math.sin(a); return { h, x, y, dir }; });
  const nodes = [...place(left, -1), ...place(right, 1)];
  return (
    <svg className="dk-cmap" viewBox={"0 0 " + W + " " + H} role="img" aria-label={"What the record says about " + name + ". " + hs.map((h) => h.title + ": " + h.sub + (h.leaves.length ? ", " + h.leaves.join(", ") : "")).join(". ")}>
      <defs><filter id="cm-soft" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="6" stdDeviation="9" floodColor="#1e281e" floodOpacity="0.1" /></filter></defs>
      <ellipse cx={CX} cy={CY} rx="262" ry="205" className="orbit" />
      {nodes.map(({ h, x, y, dir }, i) => (
        <g key={h.id} className="h" style={{ animationDelay: 120 + i * 70 + "ms" }}>
          <path className="l" pathLength={1} d={"M" + (CX + dir * 60) + " " + CY + "C" + (CX + dir * 150) + " " + CY + " " + (x - dir * 120) + " " + y + " " + (x - dir * 50) + " " + y} />
          {h.leaves.map((leaf, k) => { const ly = y + (k - (h.leaves.length - 1) / 2) * 40, lx = x + dir * 74, text = cut(leaf, 32), w = Math.min(232, text.length * 6.5 + 26); return (
            <g key={leaf}>
              <path className="l thin" pathLength={1} d={"M" + (x + dir * 50) + " " + y + "C" + (x + dir * 66) + " " + y + " " + (lx - dir * 14) + " " + ly + " " + lx + " " + ly} />
              <rect className="leaf" x={dir === 1 ? lx : lx - w} y={ly - 15} width={w} height={30} rx={15} />
              <text className="lt" x={dir === 1 ? lx + 13 : lx - 13} y={ly + 4.5} textAnchor={dir === 1 ? "start" : "end"}>{text}</text>
            </g>
          ); })}
          <circle cx={x} cy={y} r="50" className="hub" filter="url(#cm-soft)" />
          <g transform={"translate(" + (x - 10) + " " + (y - 31) + ")"}><Icon n={h.icon} size={20} /></g>
          <text className="ht" x={x} y={y + 9} textAnchor="middle">{h.title}</text>
          <text className="hs" x={x} y={y + 25} textAnchor="middle">{cut(h.sub, 17)}</text>
        </g>
      ))}
      <g className="me">
        <circle cx={CX} cy={CY} r="62" className="hub" filter="url(#cm-soft)" />
        <circle cx={CX} cy={CY} r="50" className="face" />
        <text x={CX} y={CY + 13} textAnchor="middle" className="ini">{name[0]}</text>
      </g>
    </svg>
  );
}

const first = (s: string) => s.toLowerCase().split(" ")[0];
const flownWith = (airline: string, deals: DealRow[], seen: Seen[]) => { const ids = new Set(seen.filter((s) => s.chosen && first(s.chosen) === first(airline)).map((s) => s.id)); return deals.filter((d) => ids.has(d.id)); };
const sheetOf = (airline: string) => LANES.filter((l) => l[2].some((a) => first(a[0]) === first(airline)));

/** An airline at a glance: what we booked with them, and what this month's rate sheets say about them. */
export function airlineHubs(airline: string, deals: DealRow[], seen: Seen[]): Hub[] {
  const mine = flownWith(airline, deals, seen), all = seen.filter((s) => s.chosen).length, out: Hub[] = [];
  if (mine.length) {
    const kgs = mine.reduce((s, d) => s + (Number(d.weight_kg) || 0), 0), last = Math.max(...mine.map((d) => ms(d.updated_at)));
    out.push({ id: "booked", icon: "plane", title: "Booked", sub: mine.length + (mine.length === 1 ? " time" : " times"), leaves: [kgs ? Math.round(kgs).toLocaleString("en-US") + " kg in all" : "", all ? Math.round(mine.length / all * 100) + " % of our bookings" : "", "last on " + dayOf(last)].filter(Boolean) });
    const to = tally(mine.map((d) => ends(d)?.[1]).filter((x): x is string => !!x)), from = tally(mine.map((d) => ends(d)?.[0]).filter((x): x is string => !!x));
    if (to.length) out.push({ id: "to", icon: "mapPin", title: "Flies to", sub: to.length + (to.length === 1 ? " city" : " cities"), leaves: to.slice(0, 3).map(([c, k]) => city(c) + (k > 1 ? ", " + k + " times" : "")) });
    if (from.length) out.push({ id: "from", icon: "package", title: "From", sub: city(from[0][0]), leaves: from.slice(0, 3).map(([c, k]) => city(c) + ", " + k + (k === 1 ? " time" : " times")) });
    const who = tally(mine.map((d) => d.customer).filter((x): x is string => !!x));
    if (who.length) out.push({ id: "who", icon: "users", title: "Customers", sub: who.length + " we know", leaves: who.slice(0, 3).map(([e, k]) => cut(e.split("@")[0].split(/[-._]+/).map(cap).join(" "), 19) + ", " + k + (k === 1 ? " time" : " times")) });
  }
  const sheet = sheetOf(airline);
  if (sheet.length) {
    const prices = sheet.map((l) => l[2].find((a) => first(a[0]) === first(airline))![1]), cheapest = sheet.filter((l) => first(l[2][0][0]) === first(airline)).length, alone = sheet.filter((l) => l[2].length === 1).length;
    out.push({ id: "sheet", icon: "tag", title: "Rate sheet", sub: sheet.length + " routes", leaves: ["cheapest on " + cheapest + " of them", alone ? "only airline on " + alone : "", "from " + Math.min(...prices).toFixed(2) + " EUR/kg"].filter(Boolean) });
  }
  return out;
}

export function airlineInsights(airline: string, deals: DealRow[], seen: Seen[]): string[] {
  const mine = flownWith(airline, deals, seen), counts = tally(seen.map((s) => s.chosen).filter((x): x is string => !!x).map(first)), all = counts.reduce((s, x) => s + x[1], 0), out: string[] = [];
  if (!mine.length) out.push("We have not booked with " + airline + " yet.");
  else if (counts[0] && counts[0][0] === first(airline) && counts.length > 1) out.push(airline + " carried more of our bookings than any other airline: " + mine.length + " of " + all + ".");
  else out.push(airline + " carried " + mine.length + " of our " + all + " bookings.");
  const from = tally(mine.map((d) => ends(d)?.[0]).filter((x): x is string => !!x));
  if (mine.length >= 3 && from.length === 1) out.push("Every booking with them left from " + city(from[0][0]) + ".");
  const alone = sheetOf(airline).filter((l) => l[2].length === 1).length;
  if (alone) out.push("They are the only airline on " + alone + " routes of our rate sheets. A price rise there has no second offer behind it.");
  return out.slice(0, 3);
}

export function open(c: Cust): DealRow[] { return c.deals.filter((d) => ["needs", "working", "quoted"].includes(groupOf(d))).slice(0, 3); }
