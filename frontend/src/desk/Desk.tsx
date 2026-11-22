import { useEffect, useMemo, useRef, useState } from "react";
import { Board, Deal, DealRow, get, post } from "../api";
import { DEMO } from "../demo";
import { DealView } from "../DealView";
import { OperatorStrip } from "../Operator";
import { BoardPane, DealList } from "../Side";
import { who } from "../format";
import { Act, Answer, TRY, answer, askModel } from "./ask";
import { CarrierFacts, Seen, carrierFacts, context, customerExtra, expect, useKnowledge } from "./knowledge";
import { Ground, Mark, Mood } from "./Ground";
import { Icon } from "./icons";
import { CITY, LANES, ORIGINS, REGION } from "./network";
import { Numbers } from "./Numbers";
import { Rights, ROLE_NAME, ROLE_SEES, Setup } from "./Setup";
import { Step, languageOf, timeline } from "./timeline";
import { Cust, Group, LABEL, amount, city, flagNote, customers, ends, groupOf, kg, known, lane, median, money, name, since, when, why } from "./util";
import "./desk.css";

// The desk around the sessions UI. The agent runs on its own; this shows a person what it did, what it flagged and why,
// and lets them say something to it. Nothing here makes the agent wait.
// It reads the API the sessions view reads and keeps nothing of its own on the server.

type Page = "home" | "ship" | "cust" | "net" | "sess" | "help" | "ask" | "setup" | "eff";
// Three people run this company, and each opens the desk on what they care about.
type Role = "ops" | "sales" | "carriers";
type Person = { id: string; name: string; role: Role; title: string; cares: string; photo?: boolean; added?: boolean };
const PEOPLE: Person[] = [
  { id: "sam", name: "Sam", role: "ops", title: "Operations", cares: "What the AI Worker flagged", photo: true },
  { id: "jan", name: "Jan", role: "sales", title: "Sales", cares: "Customers and open quotes", photo: true },
  { id: "mattia", name: "Mattia", role: "carriers", title: "Carriers and rates", cares: "Airlines, routes and prices", photo: true },
];
let ME = "Sam";
// what the person signed in may do in this desk (set in Desk, read where something is written)
let CAN: Rights = { tell: true, sessions: true, setup: true };

function Face({ p, size = 36 }: { p: Person; size?: number }) {
  const [missing, setMissing] = useState("");
  return <span className="dk-face" style={{ width: size, height: size }}>{p.name[0]}{p.photo && missing !== p.id ? <img key={p.id} src={"/people/" + p.id + ".png"} alt="" onError={() => setMissing(p.id)} /> : null}</span>;
}

// A wheel that eases in and out: the page follows the hand a moment later, never abruptly.
function useSoftScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const goal = new WeakMap<HTMLElement, number>(), live = new Set<HTMLElement>();
    let raf = 0;
    const step = () => {
      for (const el of [...live]) { const d = (goal.get(el) ?? 0) - el.scrollTop; if (Math.abs(d) < 1) { el.scrollTop = goal.get(el) ?? 0; live.delete(el); } else el.scrollTop += Math.abs(d * 0.2) < 1 ? Math.sign(d) : d * 0.2; }
      raf = live.size ? requestAnimationFrame(step) : 0;
    };
    const wheel = (e: WheelEvent) => {
      if (e.ctrlKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      const el = (e.target as HTMLElement).closest<HTMLElement>("[data-soft]"), max = el ? el.scrollHeight - el.clientHeight : 0;
      if (!el || max <= 0) return;
      e.preventDefault();
      const from = live.has(el) ? goal.get(el) ?? el.scrollTop : el.scrollTop;
      goal.set(el, Math.max(0, Math.min(max, from + e.deltaY * (e.deltaMode === 1 ? 32 : 1))));
      live.add(el); if (!raf) raf = requestAnimationFrame(step);
    };
    window.addEventListener("wheel", wheel, { passive: false });
    return () => { window.removeEventListener("wheel", wheel); cancelAnimationFrame(raf); };
  }, []);
}
const thinOnes = (deals: DealRow[]) => deals.filter((d) => ["needs", "working", "quoted"].includes(groupOf(d)) && ends(d)).map((d) => { const e = ends(d)!, l = LANES.find((x) => x[0] === e[0] && x[1] === e[1]); return { d, n: l ? l[2].length : 0, only: l && l[2].length === 1 ? l[2][0][0] : null }; }).filter((x) => x.n < 2);
const TEAM = "start-milan";
const AVC: [string, string][] = [["#e8eefc", "#2b4a9b"], ["#fde9e0", "#b4441c"], ["#e6f4ec", "#1b6b43"], ["#f3eafc", "#6a3aa8"], ["#fdf2d8", "#8a5a07"], ["#e3f3f6", "#1c6470"]];
const hash = (s: string) => [...s].reduce((t, c) => (t * 31 + c.charCodeAt(0)) >>> 0, 7);
const ago = (ts: number | string | null | undefined) => { const s = since(ts); return s ? s + " ago" : ""; };

function Avatar({ name }: { name: string }) {
  const c = AVC[hash(name) % AVC.length];
  return <span className="dk-av" style={{ background: c[0], color: c[1] }}>{name[0] ?? "?"}</span>;
}
function Pill({ g }: { g: Group }) { return <span className={"dk-pill " + g}><i />{LABEL[g]}</span>; }
function RouteLine({ d }: { d: DealRow }) {
  const e = ends(d);
  if (!e) return <span style={{ color: "var(--d-faint)" }}>not read yet</span>;
  return <span className={"dk-route" + (groupOf(d) === "needs" ? " hot" : "")}><b>{e[0]}</b><u /><span>{city(e[1])}</span><u className="e" />{e[1]}</span>;
}
function Row({ d, open }: { d: DealRow; open: (id: string) => void }) {
  const g = groupOf(d);
  return (
    <button className="dk-it" onClick={() => open(d.id)}>
      <span className={"dk-sq " + (g === "needs" ? "r" : g === "booked" ? "g" : g === "working" ? "a" : g === "lost" ? "q" : "b")}><Icon n={g === "needs" ? "triangleAlert" : g === "booked" ? "plane" : g === "working" ? "loader" : g === "lost" ? "x" : "send"} size={15} /></span>
      <span style={{ minWidth: 0 }}><b>{g === "needs" ? why(d) : name(d) + (lane(d) ? " · " + lane(d) : "")}</b><small>{g === "needs" ? name(d) + (lane(d) ? " · " + lane(d) : "") + " · " : ""}{[kg(d), d.quote ? money(d.quote) : "", LABEL[g].toLowerCase()].filter(Boolean).join(" · ")}</small></span>
      <time>{ago(d.updated_at)}</time>
    </button>
  );
}

// One field to ask in. It looks and behaves like the chat people already know: a question, a plain answer.
type Turn = { q: string; a: Answer | null; done?: string };

// Example questions written out letter by letter, at an uneven human pace, then wiped and replaced by the next.
function useTyped(lines: string[] | undefined, on: boolean): string {
  const [text, setText] = useState("");
  useEffect(() => {
    if (!lines?.length || !on) { setText(""); return; }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setText(lines[0]); return; }
    let i = 0, n = 0, back = false, t = 0;
    const tick = () => {
      const line = lines[i % lines.length];
      if (!back && n < line.length) { n++; setText(line.slice(0, n)); t = window.setTimeout(tick, 38 + Math.random() * 70 + (line[n - 1] === " " ? 40 : 0)); }
      else if (!back) { back = true; t = window.setTimeout(tick, 2100); }
      else if (n > 0) { n = Math.max(0, n - 2); setText(line.slice(0, n)); t = window.setTimeout(tick, 16); }
      else { back = false; i++; t = window.setTimeout(tick, 420); }
    };
    t = window.setTimeout(tick, 700);
    return () => clearTimeout(t);
  }, [lines, on]);
  return text;
}
const EXAMPLES: Record<Role, string[]> = {
  ops: ["What should I look at first?", "Which quotes took the longest today?", "What happened with Hartmann's booking?", "Tell the AI Worker for Lumiere that the packing list always counts"],
  sales: ["Who has not answered our quote yet?", "What do we know about Kessler?", "Which customer books least of what we quote?", "Where did comparing save a customer the most?"],
  carriers: ["Which airline do we book most?", "What is the cheapest way to Hong Kong?", "What if Frankfurt closes?", "Which airline answers us fastest?"],
};

function Composer({ send, big, line, focus, hint = "Ask anything", examples }: { send: (q: string) => void; big?: boolean; line?: boolean; focus?: boolean; hint?: string; examples?: string[] }) {
  const [q, setQ] = useState("");
  const typed = useTyped(examples, !q);
  const go = () => { if (q.trim()) { send(q.trim()); setQ(""); } };
  return (
    <div className={"dk-cmp" + (big ? " big" : "") + (line ? " line" : "")}>
      {examples && !q ? <span className="dk-typed" aria-hidden="true">{typed}<i /></span> : null}
      <input value={q} autoFocus={focus} placeholder={examples ? "" : hint} aria-label={hint} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
      <button onClick={go} disabled={!q.trim()} aria-label="Send"><Icon n="arrowUp" size={17} /></button>
    </div>
  );
}

function AskPage({ role, turns, send, open, go, pickCustomer, run }: { role: Role; turns: Turn[]; send: (q: string) => void; open: (id: string) => void; go: (p: Page) => void; pickCustomer: (email: string) => void; run: (i: number) => void }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [turns.length, turns[turns.length - 1]?.a]);
  if (!turns.length) return <div className="dk-askp empty"><span className="dk-orb" /><h2>What do you want to know?</h2><Composer send={send} big focus examples={EXAMPLES[role]} /><p className="dk-fine">Answers come from this desk's own record.</p></div>;
  return (
    <div className="dk-askp">
      <div className="dk-thread" data-soft>
        {turns.map((t, i) => (
          <div key={i} className="dk-turn">
            <p className="dk-q">{t.q}</p>
            {!t.a ? <p className="dk-think"><i /><i /><i /></p> : (
              <div className="dk-a">
                <p>{t.a.text}</p>
                {t.a.facts ? <dl className="dk-kv">{t.a.facts.map((f) => <div key={f[0]}><dt>{f[0]}</dt><dd>{f[1]}</dd></div>)}</dl> : null}
                {t.a.rows?.length ? <div className="dk-rows">{t.a.rows.map((d) => <Row key={d.id} d={d} open={open} />)}</div> : null}
                {t.a.act || t.a.customer || t.a.page || t.done ? (
                  <div className="dk-acts">
                    {t.a.act && !t.done ? <button className="dk-btn k" onClick={() => run(i)}><Icon n="check" />{t.a.act.label}</button> : null}
                    {t.done ? <span className="dk-done"><Icon n="circleCheck" />{t.done}</span> : null}
                    {t.a.customer ? <button className="dk-btn" onClick={() => pickCustomer(t.a!.customer!)}>Open the customer</button> : null}
                    {t.a.page ? <button className="dk-btn" onClick={() => go(t.a!.page!)}>{t.a.page === "net" ? "Open the network" : t.a.page === "cust" ? "Open customers" : "Open shipments"}</button> : null}
                  </div>
                ) : null}
                {t.a.via === "record" ? <p className="dk-fine">The assistant is not reachable. This is the plain lookup.</p> : null}
              </div>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="dk-dock"><Composer send={send} focus /><p className="dk-fine">Answers come from this desk's own record.</p></div>
    </div>
  );
}

function Lead({ title, sub, send, role }: { title: string; sub: string; send: (q: string) => void; role: Role }) {
  return <section className="dk-lead mid"><span className="dk-orb" /><h2>{title}</h2><p>{sub}</p><Composer send={send} big examples={EXAMPLES[role]} /></section>;
}

function Home({ role, deals, list, seen, open, pick, seenIds, send }: { role: Role; deals: DealRow[]; list: Cust[]; seen: Seen[]; open: (id: string) => void; pick: (email: string) => void; seenIds: Set<string>; send: (q: string) => void }) {
  const all = deals.filter((d) => groupOf(d) === "needs"), needs = all.filter((d) => !seenIds.has(d.id));
  const work = deals.filter((d) => groupOf(d) === "working");
  const openQuotes = deals.filter((d) => groupOf(d) === "quoted").sort((a, b) => a.updated_at - b.updated_at);
  const quoted = deals.filter((d) => d.quote), booked = deals.filter((d) => d.booking || d.status === "booked").length;
  const t = median(quoted.map((d) => d.response_seconds).filter((x): x is number => x != null));
  const quoteRow = (d: DealRow) => (
    <button key={d.id} className="dk-it" onClick={() => open(d.id)}>
      <span className="dk-sq b"><Icon n="send" size={15} /></span>
      <span style={{ minWidth: 0 }}><b>{name(d)}{lane(d) ? " · " + lane(d) : ""}</b><small>{money(d.quote)} · out for {since(d.updated_at)}</small></span>
      <Icon n="chevronRight" size={15} />
    </button>
  );
  const custRow = (c: Cust, sub: string) => (
    <button key={c.email} className="dk-it" onClick={() => pick(c.email)}>
      <Avatar name={c.name} />
      <span style={{ minWidth: 0 }}><b>{c.name}</b><small>{sub}</small></span>
      <Icon n="chevronRight" size={15} />
    </button>
  );
  if (role === "sales") {
    const watch = list.filter((c) => c.needs || (c.quoted >= 2 && c.booked * 2 < c.quoted)).slice(0, 5), top = list.slice().sort((a, b) => b.value - a.value).slice(0, 5);
    return (
      <>
        <Lead role={role} title={openQuotes.length ? openQuotes.length + (openQuotes.length === 1 ? " quote is" : " quotes are") + " waiting for a yes." : "Every quote has an answer."} sub={list.length + " customers. " + booked + " of " + quoted.length + " quotes became bookings."} send={send} />
        <section className="dk-box"><div className="dk-bh"><h2>Follow up</h2></div>{openQuotes.slice(0, 5).map(quoteRow)}{!openQuotes.length ? <div className="dk-empty"><b>Nothing to chase</b>A quote shows up here until the customer answers.</div> : null}</section>
        <div className="dk-two even">
          <section className="dk-box"><div className="dk-bh"><h2>Customers to watch</h2></div>{watch.map((c) => custRow(c, c.needs ? "Has a flagged shipment" : "Booked " + c.booked + " of " + c.quoted + " quotes"))}{!watch.length ? <div className="dk-empty"><b>None right now</b>A customer shows up here when they book less than half of our quotes.</div> : null}</section>
          <section className="dk-box"><div className="dk-bh"><h2>Biggest customers</h2></div>{top.map((c) => custRow(c, money(c.value) + " quoted · " + c.deals.length + " shipments"))}</section>
        </div>
      </>
    );
  }
  if (role === "carriers") {
    const thin = thinOnes(deals), best = carrierFacts(seen).slice(0, 5);
    return (
      <>
        <Lead role={role} title={thin.length ? thin.length + (thin.length === 1 ? " open shipment depends" : " open shipments depend") + " on one airline." : "Every open shipment has a second offer."} sub={LANES.length + " routes on this month's rate sheets. " + LANES.filter((l) => l[2].length === 1).length + " of them have only one airline."} send={send} />
        <Watch deals={deals} open={open} />
        <section className="dk-box"><div className="dk-bh"><h2>Airlines we book most</h2></div>
          {best.map((c) => <div key={c.airline} className="dk-it"><span className="dk-sq q"><Icon n="plane" size={15} /></span><span style={{ minWidth: 0 }}><b>{c.airline}</b><small>{c.offers} offers to us{c.via.length ? " · answers by " + c.via.slice(0, 2).join(" and ") : ""}{c.reply != null ? " · typically in " + c.reply + " s" : ""}</small></span><time>chosen {c.chosen} times</time></div>)}
          {!best.length ? <div className="dk-empty"><b>Reading the record</b>The airlines appear once the first offers are in.</div> : null}
        </section>
      </>
    );
  }
  return (
    <>
      <Lead role={role} title={needs.length ? needs.length + (needs.length === 1 ? " shipment is" : " shipments are") + " flagged for a look." : "Nothing is flagged."} sub={deals.length + " requests on the desk, " + quoted.length + " quoted" + (t != null && t >= 1 ? " after " + Math.round(t) + " s on a typical one" : "") + ", " + booked + " booked. The AI Worker handled all of them on its own."} send={send} />
      <section className="dk-box">
        <div className="dk-bh"><h2>Flagged by the AI Worker</h2></div>
        <p className="dk-bs">It decided these itself and left a note. Read it, and say so if you see it differently.</p>
        {needs.slice(0, 6).map((d) => (
          <button key={d.id} className="dk-it big" onClick={() => open(d.id)}>
            <span className={"dk-sq " + (d.flag === "red" ? "r" : "a")}><Icon n="flag" size={15} /></span>
            <span style={{ minWidth: 0 }}><b>{why(d)}</b><small>{name(d)}{lane(d) ? " · " + lane(d) : ""}{kg(d) ? " · " + kg(d) : ""} · {ago(d.updated_at)}</small></span>
            <Icon n="chevronRight" size={16} />
          </button>
        ))}
        {needs.length > 6 ? <p className="dk-bs">And {needs.length - 6} more under Shipments, Flagged.</p> : null}
        {!needs.length ? <div className="dk-empty"><b>All clear</b>{all.length ? "You have seen all " + all.length + " flagged shipments." : "A shipment shows up here when the AI Worker meets something unusual."}</div> : null}
      </section>
      <div className="dk-two even">
        <section className="dk-box"><div className="dk-bh"><h2>Waiting for the customer</h2></div>{openQuotes.slice(0, 5).map(quoteRow)}{!openQuotes.length ? <div className="dk-empty"><b>No open quotes</b>Every quote has an answer.</div> : null}</section>
        <section className="dk-box">
          <div className="dk-bh"><h2>In progress</h2></div>
          {work.map((d) => (
            <button key={d.id} className="dk-it" onClick={() => open(d.id)}>
              <span className="dk-sq a"><Icon n="loader" size={15} /></span>
              <span style={{ minWidth: 0 }}><b>{name(d)}{lane(d) ? " · " + lane(d) : ""}</b><small>{d.browser_activity?.active ? "Reading a price on the rate portal" : d.status === "waiting_customer" ? "Asked the customer a question" : d.status === "pricing" ? "Collecting prices from the airlines" : d.status === "quoted" ? "Booking the flight" : "Reading the request"} · {since(d.updated_at)}</small></span>
              <Icon n="chevronRight" size={15} />
            </button>
          ))}
          {!work.length ? <div className="dk-empty"><b>Nothing in progress</b>A new request appears here within seconds.</div> : null}
        </section>
      </div>
    </>
  );
}

function Shipments({ deals, open }: { deals: DealRow[]; open: (id: string) => void }) {
  const [f, setF] = useState<Group | "all">("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const per = 10;
  const shown = useMemo(() => deals.filter((d) => f === "all" || groupOf(d) === f)
    .filter((d) => !q || (who(d.customer) + " " + (d.route ?? "") + " " + (d.subject ?? "") + " " + (d.booking ?? "")).toLowerCase().includes(q.toLowerCase())), [deals, f, q]);
  const pages = Math.max(1, Math.ceil(shown.length / per)), p = Math.min(page, pages - 1);
  const needs = deals.filter((d) => groupOf(d) === "needs");
  const F: (Group | "all")[] = ["all", "needs", "working", "quoted", "booked", "lost"];
  return (
    <section style={{ display: "grid", gap: 14 }}>
      <div className="dk-th">
        <div className="dk-chips">
          {F.map((x) => <button key={x} aria-pressed={f === x} onClick={() => { setF(x); setPage(0); }}>{x === "all" ? "All" : LABEL[x]}<span>{x === "all" ? deals.length : deals.filter((d) => groupOf(d) === x).length}</span></button>)}
        </div>
        <div className="dk-rt">
          <label className="dk-sr"><Icon n="search" /><input placeholder="Customer, route, booking" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} aria-label="Search shipments" /></label>
          
        </div>
      </div>
      <div className="dk-tw">
        <table>
          <thead><tr><th>Customer</th><th>Route</th><th>Freight</th><th className="r">Quote</th><th>Status</th><th className="r">Answered in</th><th /></tr></thead>
          <tbody>
            {shown.slice(p * per, p * per + per).map((d) => {
              const g = groupOf(d), nm = name(d);
              return (
                <tr key={d.id} onClick={() => open(d.id)}>
                  <td><span className="dk-who"><Avatar name={nm} /><span><b>{nm}</b><small>{d.subject || "no subject"} · {ago(d.updated_at)}</small></span></span></td>
                  <td><RouteLine d={d} /></td>
                  <td>{kg(d) || "–"} {d.preference ? <span style={{ color: "var(--d-muted)" }}>{d.preference}</span> : null}</td>
                  <td className="r dk-num">{money(d.quote)}</td>
                  <td><Pill g={g} /></td>
                  <td className="r dk-num">{d.response_seconds != null ? Math.round(d.response_seconds) + " s" : "–"}</td>
                  <td className="go"><Icon n="chevronRight" size={16} /></td>
                </tr>
              );
            })}
            {!shown.length ? <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--d-muted)", padding: 26 }}>No shipment fits. Clear the search or pick another filter.</td></tr> : null}
          </tbody>
        </table>
      </div>
      <div className="dk-pg">
        <span>{shown.length} {shown.length === 1 ? "shipment" : "shipments"}</span>
        <ol>
          <li><button disabled={p === 0} onClick={() => setPage(p - 1)} aria-label="Previous page"><Icon n="chevronLeft" size={14} /></button></li>
          {Array.from({ length: pages }, (_, i) => <li key={i}><button aria-current={i === p ? "page" : undefined} onClick={() => setPage(i)}>{i + 1}</button></li>)}
          <li><button disabled={p >= pages - 1} onClick={() => setPage(p + 1)} aria-label="Next page"><Icon n="chevronRight" size={14} /></button></li>
        </ol>
      </div>
    </section>
  );
}


function Customers({ deals, pick }: { deals: DealRow[]; pick: (email: string) => void }) {
  const list = customers(deals);
  return (
    <section style={{ display: "grid", gap: 14 }}>
      <div className="dk-th"><span style={{ color: "var(--d-muted)" }}>{list.length} on record, latest request first</span></div>
      <div className="dk-tw">
        <table>
          <thead><tr><th>Customer</th><th>Usually</th><th className="r">Shipments</th><th className="r">Booked</th><th className="r">Quoted</th><th>Last request</th><th /></tr></thead>
          <tbody>
            {list.map((c) => {
              const k = known(c), from = k.find((x) => x[0] === "Ships from"), pref = k.find((x) => x[0] === "Asks for");
              return (
                <tr key={c.email} onClick={() => pick(c.email)}>
                  <td><span className="dk-who"><Avatar name={c.name} /><span><b>{c.name}</b><small>{c.email}</small></span></span></td>
                  <td>{[from ? from[1].split(",")[0] : "", pref ? pref[1].split(",")[0].replace("the ", "").replace(" option", "") : ""].filter(Boolean).join(" · ")}</td>
                  <td className="r dk-num">{c.deals.length}</td><td className="r dk-num">{c.booked} of {c.quoted}</td><td className="r dk-num">{money(c.value)}</td><td>{ago(c.last)}</td>
                  <td className="r">{c.needs ? <Pill g="needs" /> : null}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CustomerPage({ c, seen, open, back, teach }: { c: Cust; seen: Seen[]; open: (id: string) => void; back: () => void; teach: (deal: string, text: string) => Promise<string> }) {
  const [told, setTold] = useState("");
  const add = (text: string) => { if (c.deals[0]) teach(c.deals[0].id, "About this customer, to remember: " + text).then(setTold); };
  const latest = c.deals[0], facts = [...known(c), ...customerExtra(c, seen)];
  const notes = [...new Set(seen.filter((x) => x.customer === c.email).flatMap((x) => x.notes))];
  return (
    <>
      <div className="dk-prof">
        <Avatar name={c.name} />
        <div><h2>{c.name}</h2><small>{c.email} · {c.deals.length} {c.deals.length === 1 ? "request" : "requests"}, the last one {ago(c.last)}</small></div>
        <div className="dk-rt"><button className="dk-btn" onClick={back}>All customers</button>{latest ? <button className="dk-btn k" onClick={() => open(latest.id)}>{c.needs ? "Read the flagged shipment" : "Open latest shipment"}</button> : null}</div>
      </div>
      <div className="dk-three">
        <section className="dk-box"><div className="dk-bh"><h2>History</h2></div>
          <ol className="dk-tl pad">
            {c.deals.slice(0, 6).map((d) => {
              const g = groupOf(d);
              return (
                <li key={d.id} className={g === "needs" ? "hot" : g === "booked" ? "ok" : g === "working" ? "work" : g === "lost" ? "off" : "out"}>
                  <span className="dk-dot"><Icon n={g === "needs" ? "triangleAlert" : g === "booked" ? "plane" : g === "working" ? "loader" : g === "lost" ? "x" : "send"} size={12} /></span>
                  <button className="dk-step" onClick={() => open(d.id)}>
                    <b>{g === "needs" ? why(d) : LABEL[g]}{lane(d) ? " · " + lane(d) : ""}</b>
                    <small>{[kg(d), d.preference, d.quote ? money(d.quote) : "", d.response_seconds != null ? "answered in " + Math.round(d.response_seconds) + " s" : ""].filter(Boolean).join(" · ")}</small>
                  </button>
                  <time>{when(d.updated_at)}</time>
                </li>
              );
            })}
          </ol>
        </section>
        <section className="dk-box"><div className="dk-bh"><h2>What we know</h2></div><dl className="dk-kv pad">{facts.map((f) => <div key={f[0]}><dt>{f[0]}</dt><dd>{f[1]}</dd></div>)}</dl></section>
        <section className="dk-box"><div className="dk-bh"><h2>Remembered</h2></div>
          {notes.length ? <ul className="dk-notes">{notes.map((n) => <li key={n}><Icon n="brain" size={14} />{n}</li>)}</ul> : <p className="dk-bs">Nothing yet. Tell it what to keep in mind for this customer.</p>}
          {CAN.tell ? <div className="dk-tell in"><Composer line hint="Teach it something" send={add} /></div> : null}
          {told ? <p className="dk-bs"><span className="dk-done"><Icon n="circleCheck" />Passed on. It keeps it for their next request.</span></p> : null}
        </section>
      </div>
    </>
  );
}

function Watch({ deals, open }: { deals: DealRow[]; open: (id: string) => void }) {
  const thin = thinOnes(deals);
  const gaps = LANES.filter((l) => l[2].length > 1).map((l) => ({ l, x: l[2][l[2].length - 1][1] / l[2][0][1] })).sort((a, b) => b.x - a.x).slice(0, 4);
  return (
    <div className="dk-two even">
      <section className="dk-box">
        <div className="dk-bh"><h2>Open shipments with one option</h2></div>
        <p className="dk-bs">If that airline says no or raises its price, there is no second offer on our sheets.</p>
        {thin.slice(0, 5).map(({ d, only }) => (
          <button key={d.id} className="dk-it" onClick={() => open(d.id)}>
            <span className="dk-sq a"><Icon n="triangleAlert" size={15} /></span>
            <span style={{ minWidth: 0 }}><b>{name(d)} · {lane(d)}</b><small>{only ? "Only " + only + " flies this on our rate sheets" : "Not on our rate sheets, priced through the rate portal"}</small></span>
            <Icon n="chevronRight" size={15} />
          </button>
        ))}
        {!thin.length ? <div className="dk-empty"><b>None right now</b>Every open shipment has at least two airlines to compare.</div> : null}
      </section>
      <section className="dk-box">
        <div className="dk-bh"><h2>Where comparing pays most</h2></div>
        <p className="dk-bs">Routes where the dearest airline costs far more than the cheapest, for 100 kg.</p>
        {gaps.map(({ l, x }) => (
          <div key={l[0] + l[1]} className="dk-it">
            <span className="dk-sq q"><Icon n="tag" size={15} /></span>
            <span style={{ minWidth: 0 }}><b>{city(l[0])} to {city(l[1])}</b><small>{l[2][0][0]} {l[2][0][1].toFixed(2)} EUR/kg, {l[2][l[2].length - 1][0]} {l[2][l[2].length - 1][1].toFixed(2)}</small></span>
            <time>{x.toFixed(1)} times</time>
          </div>
        ))}
      </section>
    </div>
  );
}

function Carriers({ learned }: { learned: CarrierFacts[] }) {
  const names = [...new Set(LANES.flatMap((l) => l[2].map((a) => a[0])))].sort();
  const single = LANES.filter((l) => l[2].length === 1).length;
  return (
    <>
      <section style={{ display: "grid", gap: 14 }}>
        <div className="dk-th"><h2>Airlines</h2><span style={{ color: "var(--d-muted)" }}>{names.length} with a rate sheet this month, {single} routes have only one of them</span></div>
        <div className="dk-tw">
          <table>
            <thead><tr><th>Airline</th><th className="r">Routes</th><th className="r">Lowest price</th><th className="r">Offers to us</th><th className="r">Chosen</th><th>Answers by</th><th className="r">Typical reply</th></tr></thead>
            <tbody>
              {names.map((n) => {
                const mine = LANES.filter((l) => l[2].some((a) => a[0] === n)), prices = mine.map((l) => l[2].find((a) => a[0] === n)![1]);
                const k = learned.find((c) => c.airline.toLowerCase().startsWith(n.toLowerCase()));
                return (
                  <tr key={n} style={{ cursor: "default" }}>
                    <td><span className="dk-who"><span className="dk-av" style={{ background: "#f0f0f0" }}>{n[0]}</span><span><b>{n}</b><small>Airline</small></span></span></td>
                    <td className="r dk-num">{mine.length}</td><td className="r dk-num">{Math.min(...prices).toFixed(2)} EUR/kg</td>
                    <td className="r dk-num">{k ? k.offers : "–"}</td><td className="r dk-num">{k ? k.chosen : "–"}</td>
                    <td>{k ? [...k.via, ...k.files].slice(0, 3).join(", ") : <span style={{ color: "var(--d-faint)" }}>no offer yet</span>}</td><td className="r dk-num">{k?.reply != null ? k.reply + " s" : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p style={{ color: "var(--d-muted)", fontSize: 13 }}>Routes and prices are from this month's rate sheets, for 100 kg all in. The other columns are counted from the offers these airlines made on our shipments.</p>
      </section>
    </>
  );
}

function Network({ deals }: { deals: DealRow[] }) {
  const [pin, setPin] = useState("");
  const [hov, setHov] = useState("");
  const sel = hov || pin;
  const [closed, setClosed] = useState("");
  const regOf = (d: string) => Object.keys(REGION).find((r) => REGION[r].includes(d)) ?? "Other";
  const tri = useMemo(() => LANES.flatMap((l) => l[2].map((a) => ({ o: l[0], d: l[1], al: a[0], p: a[1], r: regOf(l[1]) }))), []);
  const als = useMemo(() => [...new Set(tri.map((t) => t.al))].sort(), [tri]);
  const regs = Object.keys(REGION), H = 600, cw = 214, X = [8, 343, 678];
  const hit = sel ? tri.filter((t) => sel === "a:" + t.o || sel === "l:" + t.al || sel === "r:" + t.r) : tri;
  const ys = (n: number, h: number) => (i: number) => Math.round(i * (H / n) + (H / n - h) / 2);
  const ya = ys(6, 58), yl = ys(als.length, 40), yr = ys(regs.length, 58);
  const curve = (x1: number, y1: number, x2: number, y2: number) => "M" + x1 + " " + y1 + "C" + (x1 + 60) + " " + y1 + " " + (x2 - 60) + " " + y2 + " " + x2 + " " + y2;
  const live = (o: string) => deals.filter((d) => ends(d)?.[0] === o && ["needs", "working", "quoted"].includes(groupOf(d)));
  const lostIf = (o: string) => [...new Set(LANES.filter((l) => l[0] === o).map((l) => l[1]))].filter((d) => !LANES.some((l) => l[1] === d && l[0] !== o));
  const node = (id: string, x: number, y: number, h: number, a: string, b: string, right: string, dot?: "h" | "d") => {
    const on = sel === id, dim = !!sel && !on && !hit.some((t) => id === "a:" + t.o || id === "l:" + t.al || id === "r:" + t.r);
    return (
      <g key={id} className={"dk-nc" + (on ? " on" : dim ? " dim" : "") + (pin === id ? " pin" : "")} onClick={() => { setPin(pin === id ? "" : id); setClosed(""); }} onMouseEnter={() => setHov(id)} onMouseLeave={() => setHov("")}>
        <rect x={x} y={y} width={cw} height={h} rx={11} />
        <text x={x + 14} y={y + (b ? h / 2 - 3 : h / 2 + 4.5)}>{a}</text>
        {b ? <text className="s" x={x + 14} y={y + h / 2 + 14}>{b}</text> : null}
        <text className="s e" x={x + cw - 14} y={y + h / 2 + 4}>{right}</text>
        {dot ? <circle cx={x + cw - 14} cy={y + 14} r={4} fill={dot === "h" ? "#d92d20" : "#141414"} /> : null}
      </g>
    );
  };
  let panel: JSX.Element;
  if (!sel) panel = (<><h3>How your freight moves</h3><p>Six German airports, ten airlines, six regions. A thicker line means more routes. Point at a box to follow it.</p>
    <div className="dk-f3"><div><b>{LANES.length}</b><span>routes</span></div><div><b>{LANES.filter((l) => l[2].length === 1).length}</b><span>with one airline</span></div><div><b>1.8x</b><span>widest price gap</span></div></div></>);
  else if (sel[0] === "a") {
    const o = sel.slice(2), ls = LANES.filter((l) => l[0] === o), lost = lostIf(o), mine = live(o);
    panel = (<><h3>{city(o)} ({o})</h3><p><b>{ls.length} routes</b> with {new Set(ls.flatMap((l) => l[2].map((a) => a[0]))).size} airlines. <b>{ls.filter((l) => l[2].length === 1).length}</b> have only one airline.</p>
      <div className="dk-rw">{mine.map((d) => <div key={d.id}><span>{who(d.customer)}</span><b>to {city(ends(d)![1])}</b></div>)}</div>
      {closed === o ? <p className="dk-hot">If {city(o)} closes, {ls.length - lost.length} of {ls.length} destinations still fly from another airport.{lost.length ? " " + lost.map(city).join(", ") + " lose their only route." : ""}</p>
        : <button className="dk-link" onClick={() => setClosed(o)}>What if {city(o)} closes?</button>}</>);
  } else if (sel[0] === "l") {
    const al = sel.slice(2), ts = tri.filter((t) => t.al === al).sort((a, b) => a.p - b.p);
    panel = (<><h3>{al}</h3><p><b>{ts.length} routes</b> from {new Set(ts.map((t) => t.o)).size} German airports. Its lowest prices for 100 kg, all in:</p>
      <div className="dk-rw">{ts.slice(0, 6).map((t) => <div key={t.o + t.d}><span>{t.o} to {city(t.d)}</span><b>{t.p.toFixed(2)} EUR/kg</b></div>)}</div></>);
  } else {
    const r = sel.slice(2), ds = REGION[r].map((d) => tri.filter((t) => t.d === d).sort((a, b) => a.p - b.p)[0]).filter(Boolean);
    panel = (<><h3>{r}</h3><p><b>{ds.length} destinations</b>. Lowest price for 100 kg, all in:</p>
      <div className="dk-rw">{ds.map((t) => <div key={t.d}><span>{city(t.d)} · from {t.o}</span><b>{t.p.toFixed(2)} EUR/kg</b></div>)}</div></>);
  }
  const cnt = (f: (t: { o: string; d: string; al: string; r: string }) => boolean) => tri.filter(f).length;
  return (
    <div className="dk-nw">
      <div className="dk-nd">
        <header><span>German airports</span><span>Airlines</span><span>Regions</span></header>
        <svg viewBox={"0 0 900 " + (H + 10)} role="img" aria-label="Airports, airlines and regions">
          {ORIGINS.flatMap((o, i) => als.map((al, j) => { const n = cnt((t) => t.o === o && t.al === al); if (!n) return null; const on = !!sel && hit.some((t) => t.o === o && t.al === al);
            return <path key={o + al} pathLength={1} className={"dk-lk" + (sel ? (on ? " on" : " dim") : "")} d={curve(X[0] + cw, ya(i) + 29, X[1], yl(j) + 20)} strokeWidth={on ? Math.min(3.4, 1 + n * 0.3) : Math.min(6, 1 + n * 0.5)} />; }))}
          {als.flatMap((al, j) => regs.map((r, k) => { const n = cnt((t) => t.al === al && t.r === r); if (!n) return null; const m = hit.filter((t) => t.al === al && t.r === r).length, on = !!sel && m > 0;
            return <path key={al + r} pathLength={1} className={"dk-lk" + (sel ? (on ? " on" + (sel[0] === "a" ? " h2" : "") : " dim") : "")} d={curve(X[1] + cw, yl(j) + 20, X[2], yr(k) + 29)} strokeWidth={on ? Math.min(3.4, 0.9 + m * 0.35) : Math.min(6, 1 + n * 0.5)} />; }))}
          {ORIGINS.map((o, i) => { const mine = live(o); return node("a:" + o, X[0], ya(i), 58, city(o) + " " + o, mine.length ? mine.length + (mine.length === 1 ? " open shipment" : " open shipments") : "no open shipment", LANES.filter((l) => l[0] === o).length + " routes", mine.length ? (mine.some((d) => groupOf(d) === "needs") ? "h" : "d") : undefined); })}
          {als.map((al, j) => node("l:" + al, X[1], yl(j), 40, al, "", cnt((t) => t.al === al) + " routes"))}
          {regs.map((r, k) => node("r:" + r, X[2], yr(k), 58, r, REGION[r].length + " destinations", cnt((t) => t.r === r) + " offers"))}
        </svg>
      </div>
      <aside className="dk-np">{panel}{pin ? <button className="dk-link" onClick={() => { setPin(""); setClosed(""); }}>Show everything</button> : !sel ? null : <p className="dk-fine" style={{ textAlign: "left" }}>Click to keep it open.</p>}</aside>
    </div>
  );
}


function Help() {
  const L: [string, string, string][] = [
    ["mail", "A customer writes", "The AI Worker reads the mail and every attachment, also a scan or a voice message. When something is missing it asks the customer once."],
    ["tag", "It prices the request", "It asks the airlines that fly the route, reads the rate sheets and the rate portal, and a calculator adds up each offer. The model never does the sums."],
    ["send", "The quote goes out", "One price, all in, written the way the customer wrote. Most quotes leave within a minute."],
    ["plane", "It books and keeps track", "After the customer's yes it books the flight. When they ask where the shipment is, it answers from our own record."],
    ["flag", "It decides the odd cases too", "It never waits for a person. When something is unusual it decides, tells the customer, and flags the shipment with a note so you can read why."],
    ["search", "You can ask instead of clicking", "The field at the top answers from the record: what is flagged, a customer, a carrier, a price to a city. It can also pass your instruction to the AI Worker."],
    ["user", "Your word wins", "Tell it something on any shipment and it follows that from then on. You can also answer the customer yourself."],
  ];
  return (
    <div className="dk-help">
      <h2>How this desk works</h2>
      <p>This is an air export desk that runs on its own. The AI Worker reads every mail, quotes, books and answers where a shipment is. The desk shows you what it did and what it flagged.</p>
      <ul>{L.map((l) => <li key={l[1]}><span className="dk-sq q"><Icon n={l[0]} size={15} /></span><span><b>{l[1]}</b>{l[2]}</span></li>)}</ul>
    </div>
  );
}

function Timeline({ steps }: { steps: Step[] }) {
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => setOpen(null), [steps.length]);
  return (
    <ol className="dk-tl">
      {steps.map((s, i) => {
        const more = !!(s.body || s.rows);
        return (
          <li key={i} className={s.tone}>
            <span className="dk-dot"><Icon n={s.icon} size={12} /></span>
            <button className="dk-step" disabled={!more} onClick={() => setOpen(open === i ? null : i)} aria-expanded={more ? open === i : undefined}>
              <b>{s.title}{more ? <Icon n={open === i ? "chevronDown" : "chevronRight"} size={14} /> : null}</b>
              {s.sub ? <small>{s.sub}</small> : null}
            </button>
            <time>{s.at ? when(s.at) : ""}</time>
            {open === i && s.body ? <pre className="dk-body">{s.body}</pre> : null}
            {open === i && s.rows ? <div className="dk-offers">{s.rows.map((r) => <div key={r[0] + r[2]} className={r[3] ? "pick" : ""}><span>{r[0]}{r[3] ? <em>chosen</em> : null}</span><span>{r[1]}</span><b>{r[2]}</b></div>)}</div> : null}
          </li>
        );
      })}
      {!steps.length ? <li className="work"><span className="dk-dot"><Icon n="loader" size={12} /></span><span className="dk-step"><b>Nothing yet</b><small>The first step shows up as soon as the AI Worker starts.</small></span></li> : null}
    </ol>
  );
}

function Sheet({ row, deal, hint, reload, close, seen, markSeen }: { row: DealRow; deal: Deal | null; hint: string; reload: () => void; close: () => void; seen: boolean; markSeen: () => void }) {
  const [full, setFull] = useState(false);
  const [busy, setBusy] = useState(false);
  const mine = deal?.id === row.id ? deal : null;
  const g = groupOf(row), e = ends(row);
  const flag = g === "needs" ? (mine?.data.notes ?? []).filter((n) => n.flag === "red" || n.flag === "yellow").map((n) => n.text).pop() ?? flagNote(row) : null;
  const steps = useMemo(() => mine ? timeline(mine) : [], [mine]);
  const [passed, setPassed] = useState("");
  const tell = (text: string) => { if (!mine || busy) return; setBusy(true); setPassed(""); post("/api/sessions/session-" + mine.data.root + "/message", { text, who: ME }).then(() => { setPassed("Passed on. The AI Worker reads it on its next step."); reload(); }).catch(() => setPassed("That did not go through. Try again.")).finally(() => setBusy(false)); };
  useEffect(() => { setFull(false); setPassed(""); }, [row.id]);
  const changed = mine?.data.booking?.price_changed;
  return (
    <div className="dk-veil" onClick={(ev) => { if (ev.target === ev.currentTarget) close(); }}>
      <aside className="dk-sheet" role="dialog" aria-label={name(row)}>
        <header className="dk-sh"><Avatar name={name(row)} /><div><h3>{name(row)}</h3><small>{lane(row) || row.subject}</small></div><Pill g={g} /><button className="dk-x" onClick={close} aria-label="Close"><Icon n="x" /></button></header>
        <div className="dk-sb" data-soft>
          {g === "needs" ? (
            <div className={"dk-warn" + (row.flag === "red" ? "" : " soft")}>
              <b><Icon n="flag" />The AI Worker flagged this</b>
              <p>{flag ?? "It left a flag on this shipment. The steps below show what it did."}</p>
              <div className="dk-acts">
                <span className="dk-quiet">It already acted. Tell it below if you want it done differently.</span>
                <button className="dk-btn" disabled={seen} onClick={markSeen}><Icon n="check" />{seen ? "Seen" : "Mark as seen"}</button>
              </div>
            </div>
          ) : null}
          <div className="dk-facts">
            <div><Icon n="mapPin" /><span><small>Route</small><b>{e ? e[0] + " → " + e[1] : "not read yet"}</b></span></div>
            <div><Icon n="weight" /><span><small>Freight</small><b>{kg(row) || "–"}{row.preference ? " · " + row.preference : ""}</b></span></div>
            <div><Icon n="tag" /><span><small>Our quote</small><b>{row.quote ? money(row.quote) : "none yet"}</b></span></div>
            <div className={changed ? "hot" : ""}><Icon n="plane" /><span><small>{changed ? "Airline booked at" : "Booking"}</small><b>{changed ? money(changed.booked) : row.booking ?? (row.status === "booked" ? "booked" : "not booked")}</b></span></div>
          </div>
          {hint ? <p className="dk-expect"><Icon n="brain" size={14} />{hint}</p> : null}
          <p className="dk-lab">{full ? "The full record" : "What happened"}<button className="dk-btn sm" onClick={() => setFull(!full)}>{full ? "Back to the short version" : "Open the full record"}</button></p>
          {!mine ? <p style={{ color: "var(--d-muted)" }}>Loading the record.</p> : full ? <div className="dk-mt rec"><DealView deal={mine} onSent={reload} /></div> : (
            <>
              <Timeline steps={steps} />
              {CAN.tell ? <div className="dk-tell"><Composer line hint="Tell the AI Worker something about this shipment" send={tell} />{passed ? <p className="dk-fine" style={{ textAlign: "left", marginTop: 8 }}>{passed}</p> : null}</div> : <p className="dk-fine" style={{ textAlign: "left" }}>Writing to the AI Worker is switched off for you.</p>}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

export function Desk({ deals, online, worker, board, selected, select, deal, reload }: {
  deals: DealRow[]; online: boolean; worker: boolean; board: Board | null; selected: string | null; select: (id: string | null) => void; deal: Deal | null; reload: () => void;
}) {
  const initial = (location.hash.slice(1) || "home") as Page;
  const [page, setPage] = useState<Page>(["home", "ship", "cust", "net", "sess", "help", "setup", "eff"].includes(initial) ? initial : "home");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [who, setWho] = useState(() => { try { return localStorage.getItem("desk_me") ?? "sam"; } catch { return "sam"; } });
  const [menu, setMenu] = useState(false);
  useEffect(() => { // the account menu closes on a click anywhere else, and on Escape
    if (!menu) return;
    const out = (e: Event) => { if (!(e.target as HTMLElement).closest?.(".dk-acct")) setMenu(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    document.addEventListener("pointerdown", out); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", out); document.removeEventListener("keydown", key); };
  }, [menu]);
  const [roles, setRoles] = useState<Record<string, Role>>(() => { const d = Object.fromEntries(PEOPLE.map((p) => [p.id, p.role])); try { return { ...d, ...JSON.parse(localStorage.getItem("desk_roles") ?? "{}") }; } catch { return d; } });
  const setRole = (id: string, r: Role) => setRoles((x) => { const n = { ...x, [id]: r }; try { localStorage.setItem("desk_roles", JSON.stringify(n)); } catch { /* this browser keeps nothing */ } return n; });
  // people added here and everyone's rights are kept in this browser: a draft, there is no sign-in
  const keep = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* this browser keeps nothing */ } };
  const [added, setAdded] = useState<Person[]>(() => { try { return (JSON.parse(localStorage.getItem("desk_people") ?? "[]") as Person[]).filter((p) => p && p.id && p.name).map((p) => ({ ...p, added: true, photo: false })); } catch { return []; } });
  const [rights, setRights] = useState<Record<string, Partial<Rights>>>(() => { try { return JSON.parse(localStorage.getItem("desk_rights") ?? "{}"); } catch { return {}; } });
  const people = [...PEOPLE, ...added];
  const rightsOf = (p: Person): Rights => ({ tell: true, sessions: !p.added, setup: !p.added, ...rights[p.id] });
  const setRight = (id: string, k: keyof Rights, v: boolean) => setRights((x) => { const n = { ...x, [id]: { ...x[id], [k]: v } }; keep("desk_rights", n); return n; });
  const addPerson = (name: string, role: Role) => setAdded((x) => { const n = [...x, { id: "p" + Date.now().toString(36), name, role, title: ROLE_NAME[role], cares: "", added: true }]; keep("desk_people", n); return n; });
  const removePerson = (id: string) => { setAdded((x) => { const n = x.filter((p) => p.id !== id); keep("desk_people", n); return n; }); if (who === id) setWho("sam"); };
  const rolesAll = Object.fromEntries(people.map((p) => [p.id, roles[p.id] ?? p.role])) as Record<string, Role>;
  const base = people.find((p) => p.id === who) ?? PEOPLE[0];
  const me = { ...base, role: rolesAll[base.id] };
  ME = me.name; CAN = rightsOf(base);
  useSoftScroll();
  const [open, setOpen] = useState(false);
  const [cust, setCust] = useState<string | null>(null);
  const [seenIds, setSeenIds] = useState<Set<string>>(() => { try { return new Set(JSON.parse(localStorage.getItem("desk_seen") ?? "[]") as string[]); } catch { return new Set(); } });
  const markSeen = (id: string) => setSeenIds((s) => { const n = new Set(s).add(id); try { localStorage.setItem("desk_seen", JSON.stringify([...n])); } catch { /* this browser keeps nothing */ } return n; });
  const [toast, setToast] = useState("");
  const go = (p: Page) => { setPage(p); setOpen(false); if (p !== "cust") setCust(null); try { history.replaceState(null, "", "#" + p); } catch { /* none */ } };
  const show = (id: string) => { select(id); setOpen(true); };
  useEffect(() => { if (page === "sess" && !CAN.sessions) go("home"); });
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(""), 2800); return () => clearTimeout(t); }, [toast]);
  const needs = deals.filter((d) => groupOf(d) === "needs" && !seenIds.has(d.id));
  const row = deals.find((d) => d.id === selected) ?? null;
  const list = useMemo(() => customers(deals), [deals]);
  const { seen } = useKnowledge(deals);
  const picked = cust ? list.find((c) => c.email === cust) ?? null : null;
  const TITLE: Record<Page, string> = { home: "Desk", ship: "Shipments", cust: picked ? picked.name : "Customers", net: "Network", sess: "Sessions", help: "How it works", ask: "Ask", setup: "AI Worker", eff: "Efficiency" };
  const hour = new Date().getHours(), greet = hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening";
  const nv = (p: Page, icon: string, label: string, count?: number) => (
    <button className="dk-nv" aria-current={page === p ? "page" : undefined} onClick={() => go(p)}><Icon n={icon} size={17} />{label}{count ? <b>{count}</b> : null}</button>
  );
  const tell = (a: Act): Promise<string> => post("/api/sessions/" + a.deal.replace(/^deal-/, "session-") + "/message", { text: a.text, who: ME }).then(() => { reload(); return "Passed on to the AI Worker."; });
  const send = (q: string) => {
    const earlier = turns.filter((t) => t.a).slice(-3).map((t) => ({ q: t.q, a: t.a!.text }));
    setTurns((ts) => [...ts, { q, a: null }]);
    setPage("ask"); setOpen(false); setCust(null);
    askModel(q, deals, context(deals, seen), earlier).catch(() => ({ ...answer(q, deals), via: "record" as const }))
      .then((a) => setTurns((ts) => { const i = ts.findIndex((t) => t.q === q && !t.a); return i < 0 ? ts : ts.map((t, k) => k === i ? { ...t, a } : t); }));
  };
  const runTurn = (i: number) => { const a = turns[i]?.a?.act; if (a && CAN.tell) tell(a).then((done) => setTurns((ts) => ts.map((t, k) => k === i ? { ...t, done } : t))); };
  useEffect(() => { const key = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPage("ask"); setOpen(false); } }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); }, []);
  // the ground says how the desk is doing: green while it runs alone, warmer with notes to read, dusk when something is wrong
  const mood: Mood = !online || !worker || needs.some((d) => d.flag === "red") ? "alert" : needs.length ? "watch" : "calm";
  const red = needs.filter((x) => x.flag === "red").length, answered = deals.filter((x) => x.quote).length;
  const stateLabel = !online ? "No connection" : !worker ? "AI Worker is stopped" : mood === "calm" ? "All quiet" : mood === "alert" ? red + " to check" : needs.length + (needs.length === 1 ? " note to read" : " notes to read");
  return (
    <div className="dk-app" data-mood={mood}>
      <Ground mood={mood} />
      <div className="dk-win">
        <aside className="dk-side">
          <div className="dk-logo"><Mark size={34} />Milan Forwarding</div>
          {nv("home", "layoutDashboard", "Desk", needs.length)}
          {nv("ship", "package", "Shipments")}
          {nv("cust", "users", "Customers")}
          {nv("net", "network", "Network")}
          {nv("eff", "chartColumn", "Efficiency")}
          {CAN.sessions ? nv("sess", "messagesSquare", "Sessions") : null}
          <button className={"dk-state " + (online && worker ? mood : "off")} aria-current={page === "setup" ? "page" : undefined} aria-label={"AI Worker: " + stateLabel + ". Open its status and setup"} onClick={() => go("setup")}>
            <span className="dk-orb m" />
            <span><b>{stateLabel}</b><small>{answered} of {deals.length} on its own</small></span>
            <Icon n="chevronRight" size={15} />
          </button>
        </aside>
        <div className="dk-main">
          <header className="dk-bar">
            <div><small>{greet}, <b>{ME}</b></small><h1>{TITLE[page]}</h1></div>
            <div className="dk-rt">
              {DEMO ? <span className="dk-demo">Example data</span> : null}
              {page !== "ask" ? <button className="dk-btn" onClick={() => go("ask")}><Icon n="search" size={15} />Ask<kbd>⌘K</kbd></button> : turns.length ? <button className="dk-btn" onClick={() => setTurns([])}>New question</button> : null}
<div className="dk-acct">
                <button className="dk-face-b" onClick={() => setMenu(!menu)} aria-label={"Signed in as " + me.name + ". Switch account"} aria-expanded={menu}><Face p={me} /></button>
                {menu ? (
                  <div className="dk-menu" role="menu">
                    {people.map((p) => (
                      <button key={p.id} role="menuitem" onClick={() => { setWho(p.id); setMenu(false); try { localStorage.setItem("desk_me", p.id); } catch { /* this browser keeps nothing */ } go("home"); }}>
                        <Face p={p} /><span><b>{p.name}</b><small>{ROLE_NAME[rolesAll[p.id]]} · {ROLE_SEES[rolesAll[p.id]]}</small></span>{p.id === me.id ? <Icon n="check" size={15} /> : null}
                      </button>
                    ))}
                    <button role="menuitem" className="plain" onClick={() => { setMenu(false); go("help"); }}><span className="dk-sq q"><Icon n="circleHelp" size={15} /></span><span><b>How it works</b></span></button>
                  </div>
                ) : null}
              </div>
            </div>
          </header>
          {page === "sess" ? (
            <div className="dk-sess dk-mt">
              <OperatorStrip deals={deals} onOpen={(id) => select(id)} />
              <main className="grid">
                <DealList deals={deals} selected={selected} onSelect={(id) => select(id)} />
                {deal ? <DealView deal={deal} onSent={reload} /> : <section className="deal placeholder"><p>Pick a shipment on the left to read its mails and every step the AI Worker took.</p></section>}
                <BoardPane board={board} team={TEAM} />
              </main>
            </div>
          ) : (
            <div className={"dk-cont" + (page === "ask" ? " ask" : "")} data-soft key={page + (cust ?? "") + who}>
              {page === "home" ? <Home role={me.role} deals={deals} list={list} seen={seen} open={show} pick={(email) => { setPage("cust"); setCust(email); }} seenIds={seenIds} send={send} /> : null}
              {page === "ship" ? <Shipments deals={deals} open={show} /> : null}
              {page === "cust" ? (picked ? <CustomerPage c={picked} seen={seen} open={show} back={() => setCust(null)} teach={(deal, text) => tell({ label: "", kind: "tell", deal, text })} /> : <Customers deals={deals} pick={setCust} />) : null}
              {page === "net" ? <><Watch deals={deals} open={show} /><Network deals={deals} /><Carriers learned={carrierFacts(seen)} /></> : null}
              {page === "help" ? <Help /> : null}
              {page === "eff" ? <Numbers deals={deals} board={board} /> : null}
              {page === "setup" ? <Setup status={{ mood: online && worker ? mood : "off", title: !online ? "No connection to the desk." : !worker ? "The AI Worker is stopped." : mood === "calm" ? "The AI Worker is running on its own." : mood === "alert" ? red + (red === 1 ? " shipment looks wrong." : " shipments look wrong.") : needs.length + (needs.length === 1 ? " note is waiting for you." : " notes are waiting for you."), sub: answered + " of " + deals.length + " requests answered without a person.", flagged: needs.length, openFlagged: () => { const f = needs.find((x) => x.flag === "red") ?? needs[0]; if (f) show(f.id); } }}
                people={people} roles={rolesAll} setRole={setRole} rights={Object.fromEntries(people.map((p) => [p.id, rightsOf(p)]))} setRight={setRight} add={addPerson} remove={removePerson} meId={me.id}
                face={(id) => <Face p={people.find((p) => p.id === id) ?? PEOPLE[0]} />} notes={{ count: new Set(seen.flatMap((x) => x.notes.map((n) => x.customer + n))).size, customers: new Set(seen.filter((x) => x.notes.length).map((x) => x.customer)).size }} openCustomers={() => go("cust")} /> : null}
              {page === "ask" ? <AskPage role={me.role} turns={turns} send={send} open={show} go={go} pickCustomer={(email) => { setPage("cust"); setCust(email); }} run={runTurn} /> : null}
            </div>
          )}
        </div>
      </div>
      {open && row && page !== "sess" ? <Sheet row={row} deal={deal} hint={expect(row, list, seen)} reload={reload} close={() => setOpen(false)} seen={seenIds.has(row.id)}
        markSeen={() => { markSeen(row.id); const n = needs.find((d) => d.id !== row.id); if (n) select(n.id); else setOpen(false); }} /> : null}
      {toast ? <div className="dk-toast" role="status"><Icon n="circleCheck" />{toast}</div> : null}
    </div>
  );
}
