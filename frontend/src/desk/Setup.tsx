import { useState } from "react";
import { Icon } from "./icons";

// The hub behind the status card: how Giulia is doing, and how the desk is set up, in the three levels
// forwarders run such a system on. Rules for the whole company (what Giulia may do on her own, and the
// guarantees that are never switched off), wishes per customer (the notes kept with that customer), and people
// with their rights. The switches and the people are a draft of the controls: kept in this browser, there is no
// sign-in, and the agent does not read them. The rights do apply inside this desk.
export type Role = "ops" | "sales" | "carriers";
export const ROLE_NAME: Record<Role, string> = { ops: "Operations", sales: "Sales", carriers: "Carriers and rates" };
export const ROLE_SEES: Record<Role, string> = { ops: "What Giulia flagged, and everything in progress", sales: "Quotes without a yes, customers to watch", carriers: "Shipments with one airline, where comparing pays" };
type Mode = "own" | "flag" | "off";
const MODES: [Mode, string][] = [["own", "On its own"], ["flag", "On its own, and tell me"], ["off", "Off"]];
const DOES: { id: string; icon: string; what: string; how: string; fence: string }[] = [
  { id: "quote", icon: "send", what: "Answer a request with a quote", how: "Asks the airlines, reads the rate sheets and the rate portal, and takes the option the customer asked for.", fence: "Every price is computed by code. One mail, one option, one total." },
  { id: "ask", icon: "circleHelp", what: "Ask the customer for what is missing", how: "A postcode, a weight, the papers for dangerous goods.", fence: "She asks once, then goes on with what she has." },
  { id: "book", icon: "plane", what: "Book after the customer says yes", how: "Books the option it quoted, by the rate portal or by mail to the airline.", fence: "A price that changed at booking goes into the confirmation." },
  { id: "cancel", icon: "x", what: "Cancel a booking the customer withdraws", how: "Cancels with the airline and says so in our record.", fence: "Only that customer's own booking." },
  { id: "carrier", icon: "mail", what: "Write to airlines and truckers", how: "Asks for a price, a status or a booking.", fence: "Only carriers on our list, at most two mails per carrier and shipment in ten minutes." },
  { id: "portal", icon: "search", what: "Read a price on the rate portal", how: "Opens the page in a browser, fills the form and reads the result.", fence: "Only the portal's own pages. The key stays on the server." },
  { id: "track", icon: "mapPin", what: "Answer where a shipment is", how: "Looks it up and answers the customer.", fence: "From our own record of the booking." },
  { id: "note", icon: "brain", what: "Keep a note for next time", how: "A wish that holds for later requests, or something a person should read.", fence: "It stays with the customer and shows on the desk." },
];
const ALWAYS = ["Every price and date a customer reads is computed by code, never written by the model.", "A mail goes only to people in that thread and to carriers on our list.", "A customer's thread sees only that customer's shipments.", "After a restart nothing is lost and nothing is answered twice."];
const load = <T,>(k: string, d: T): T => { try { return { ...d, ...JSON.parse(localStorage.getItem(k) ?? "{}") }; } catch { return d; } };
const save = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* this browser keeps nothing */ } };

export type Rights = { tell: boolean; sessions: boolean; setup: boolean };
const RIGHTS: [keyof Rights, string][] = [["tell", "Write to Giulia"], ["sessions", "Open Sessions"], ["setup", "Change this page"]];
type Status = { mood: "calm" | "watch" | "alert" | "off"; title: string; sub: string; flagged: number; openFlagged: () => void };
type P = { id: string; name: string; added?: boolean };

function Add({ add }: { add: (name: string, role: Role) => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("ops");
  const go = () => { const n = name.trim().slice(0, 30); if (!n) return; add(n, role); setName(""); };
  return (
    <div className="dk-set dk-addp">
      <span className="dk-sq q"><Icon n="users" size={15} /></span>
      <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") go(); }} placeholder="Name of a new person" aria-label="Name of a new person" maxLength={30} />
      <span className="dk-ctl">
        <span className="dk-seg" role="group" aria-label="What the new person sees first">{(Object.keys(ROLE_NAME) as Role[]).map((r) => <button key={r} aria-pressed={role === r} onClick={() => setRole(r)}>{ROLE_NAME[r]}</button>)}</span>
        <button className="dk-btn k" disabled={!name.trim()} onClick={go}>Add</button>
      </span>
    </div>
  );
}

export function Setup({ status, people, roles, setRole, rights, setRight, add, remove, meId, face, notes, openCustomers }: {
  status: Status; people: P[]; roles: Record<string, Role>; setRole: (id: string, r: Role) => void; rights: Record<string, Rights>; setRight: (id: string, k: keyof Rights, v: boolean) => void;
  add: (name: string, role: Role) => void; remove: (id: string) => void; meId: string; face: (id: string) => JSX.Element; notes: { count: number; customers: number }; openCustomers: () => void;
}) {
  const [modes, setModes] = useState<Record<string, Mode>>(() => load("desk_modes", Object.fromEntries(DOES.map((d) => [d.id, "own" as Mode]))));
  const may = rights[meId]?.setup ?? false;
  const set = (id: string, m: Mode) => { if (!may) return; const n = { ...modes, [id]: m }; setModes(n); save("desk_modes", n); };
  const off = DOES.filter((d) => modes[d.id] === "off").length, flag = DOES.filter((d) => modes[d.id] === "flag").length;
  return (
    <>
      <section className="dk-hub">
        <span className="dk-orb l" />
        <div><h2>{status.title}</h2><p>{status.sub} {off || flag ? "She does " + (DOES.length - off) + " of " + DOES.length + " things, " + flag + " of them with a note to you." : "She does all " + DOES.length + " things below on her own."}</p></div>
        {status.flagged ? <button className="dk-btn k" onClick={status.openFlagged}>Read what it flagged</button> : null}
      </section>
      <p className="dk-bs" style={{ padding: "0 4px" }}><b>A draft of the controls.</b> The switches and people are kept in this browser, there is no sign-in yet, and Giulia does not read the switches.{may ? "" : " You can read this page. Changing it is switched off for you."}</p>
      <p className="dk-layer">For the whole company</p>
      <section className="dk-box">
        <div className="dk-bh"><h2>What Giulia may do</h2></div>
        {DOES.map((d) => (
          <div key={d.id} className={"dk-set" + (modes[d.id] === "off" ? " is-off" : "")}>
            <span className="dk-sq q"><Icon n={d.icon} size={15} /></span>
            <span style={{ minWidth: 0 }}><b>{d.what}</b><small>{d.how}</small><small className="dk-fence"><Icon n="shieldAlert" size={13} />{d.fence}</small></span>
            <span className="dk-seg" role="group" aria-label={d.what}>{MODES.map((m) => <button key={m[0]} disabled={!may} aria-pressed={modes[d.id] === m[0]} onClick={() => set(d.id, m[0])}>{m[1]}</button>)}</span>
          </div>
        ))}
      </section>
      <section className="dk-box">
        <div className="dk-bh"><h2>Always on</h2></div>
        <p className="dk-bs">These are built into the system under Giulia. They hold today and cannot be switched off.</p>
        {ALWAYS.map((a) => <div key={a} className="dk-set fixed"><span className="dk-sq g"><Icon n="check" size={15} /></span><span><b>{a}</b></span></div>)}
      </section>
      <p className="dk-layer">For one customer</p>
      <section className="dk-box">
        <div className="dk-set">
          <span className="dk-sq q"><Icon n="brain" size={15} /></span>
          <span style={{ minWidth: 0 }}><b>{notes.count ? notes.count + (notes.count === 1 ? " note" : " notes") + " on " + notes.customers + (notes.customers === 1 ? " customer" : " customers") : "No notes yet"}</b><small>What one customer wants differently is kept with that customer and used on their next request. You add to it on the customer's page.</small></span>
          <button className="dk-btn" onClick={openCustomers}>Open customers</button>
        </div>
      </section>
      <p className="dk-layer">People and rights</p>
      <section className="dk-box">
        <div className="dk-bh"><h2>Who works at this desk</h2></div>
        <p className="dk-bs">The role sets a person's start page. The rights set what they can do in this desk. Neither changes what Giulia does.</p>
        {people.map((p) => (
          <div key={p.id} className="dk-set dk-person">
            {face(p.id)}
            <span style={{ minWidth: 0 }}><b>{p.name}{p.id === meId ? " (you)" : ""}</b><small>{ROLE_SEES[roles[p.id]]}</small></span>
            <span className="dk-ctl col">
              <span className="dk-seg" role="group" aria-label={"What " + p.name + " sees first"}>{(Object.keys(ROLE_NAME) as Role[]).map((r) => <button key={r} disabled={!may} aria-pressed={roles[p.id] === r} onClick={() => setRole(p.id, r)}>{ROLE_NAME[r]}</button>)}</span>
              <span className="dk-togs">
                {RIGHTS.map(([k, label]) => <button key={k} className="dk-tog" aria-pressed={rights[p.id][k]} disabled={!may || (k === "setup" && p.id === meId)} onClick={() => setRight(p.id, k, !rights[p.id][k])}><Icon n={rights[p.id][k] ? "check" : "x"} size={13} />{label}</button>)}
                {p.added ? <button className="dk-tog rm" disabled={!may} onClick={() => remove(p.id)}>Remove</button> : null}
              </span>
            </span>
          </div>
        ))}
        {may ? <Add add={add} /> : null}
      </section>
    </>
  );
}
