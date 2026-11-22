import { useEffect, useState } from "react";
import { Account, get } from "../api";
import { Icon } from "./icons";

// The hub behind the status card: how Giulia is doing, what she does on her own and the guarantees under her,
// the wishes kept per customer, and who can open this desk. Everything here is read from the running system:
// what she does is what her tools do (backend/app/tools.py), the accounts are the ones in the register.
export type Role = "ops" | "sales" | "carriers";
export const ROLE_NAME: Record<Role, string> = { ops: "Operations", sales: "Sales", carriers: "Carriers and rates" };
export const ROLE_SEES: Record<Role, string> = { ops: "What Giulia flagged, and everything in progress", sales: "Quotes without a yes, customers to watch", carriers: "Shipments with one airline, where comparing pays" };
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
type Status = { mood: "calm" | "watch" | "alert" | "off"; title: string; sub: string; flagged: number; openFlagged: () => void };
type P = { id: string; name: string; role: Role };

export function Setup({ status, meId, face, notes, openCustomers }: {
  status: Status; meId: string; face: (p: P) => JSX.Element; notes: { count: number; customers: number }; openCustomers: () => void;
}) {
  const [people, setPeople] = useState<Account[] | null>(null);
  useEffect(() => { get<Account[]>("/api/accounts").then(setPeople).catch(() => setPeople([])); }, []);
  return (
    <>
      <section className="dk-hub">
        <span className="dk-orb l" />
        <div><h2>{status.title}</h2><p>{status.sub} She does the {DOES.length} things below on her own, and you can step into any shipment.</p></div>
        {status.flagged ? <button className="dk-btn k" onClick={status.openFlagged}>Read what it flagged</button> : null}
      </section>
      <p className="dk-layer">For the whole company</p>
      <section className="dk-box">
        <div className="dk-bh"><h2>What Giulia does on her own</h2></div>
        <p className="dk-bs">She decides how to handle each request. What must hold is held by the system under her, shown with each line.</p>
        {DOES.map((d) => (
          <div key={d.id} className="dk-set">
            <span className="dk-sq q"><Icon n={d.icon} size={15} /></span>
            <span style={{ minWidth: 0 }}><b>{d.what}</b><small>{d.how}</small><small className="dk-fence"><Icon n="shieldAlert" size={13} />{d.fence}</small></span>
          </div>
        ))}
      </section>
      <section className="dk-box">
        <div className="dk-bh"><h2>Always on</h2></div>
        <p className="dk-bs">These are built into the system under Giulia. They cannot be switched off.</p>
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
      <p className="dk-layer">People</p>
      <section className="dk-box">
        <div className="dk-bh"><h2>Who can open this desk</h2></div>
        <p className="dk-bs">Each person signs in with their own account. What they tell Giulia is recorded under their name. The role sets their start page.</p>
        {people === null ? null : people.length ? people.map((a) => (
          <div key={a.username} className="dk-set dk-person">
            {face({ id: a.username, name: a.name, role: a.role })}
            <span style={{ minWidth: 0 }}><b>{a.name}{a.username === meId ? " (you)" : ""}</b><small>{ROLE_NAME[a.role]} · {ROLE_SEES[a.role]}</small></span>
          </div>
        )) : <div className="dk-set"><span className="dk-sq q"><Icon n="users" size={15} /></span><span><b>No accounts on this server</b><small>The desk is open. The first account closes it: python -m app.accounts add.</small></span></div>}
      </section>
    </>
  );
}
