import type { Deal, Item } from "../api";
import { who } from "../format";

// One shipment as a short story: every mail and every tool the AI Worker used, in order, in plain words.
// It reads the same session the sessions view shows and leaves nothing out; that view stays the full record.
export type Step = { icon: string; tone: "in" | "out" | "work" | "ok" | "hot" | "you"; title: string; sub?: string; at?: string | null; body?: string; rows?: [string, string, string, boolean][] };

const MAIL = /New mail in this thread: id (\d+), from (\S+), at (\S+)\n(?:Their own words are in (\w+)\.\n)?Subject: (.*)\n\n([\s\S]*)$/;
const parse = (s: unknown): Record<string, any> | null => { if (typeof s !== "string" || !s) return null; try { return JSON.parse(s); } catch { return null; } };
const SENT: Record<string, string> = { quote: "Quote sent", question: "Asked the customer", reply: "Replied to the customer", booking_confirmation: "Told the customer it is booked", tracking_answer: "Answered where the shipment is", decline: "Declined the request" };
const eur = (t: unknown) => /[A-Z]{3}$/.test(String(t)) ? String(t) : t + " EUR";
const plain = (t: string) => t.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function languageOf(deal: Deal | null): string | null {
  for (const it of deal?.session?.items ?? []) { const m = typeof it.content === "string" ? it.content.match(/Their own words are in (\w+)\./) : null; if (m) return m[1]; }
  return null;
}

export function timeline(deal: Deal): Step[] {
  const items: Item[] = deal.session?.items ?? [], out: Step[] = [], outputs = new Map<string, Record<string, any> | null>();
  for (const it of items) if (it.type === "function_call_output" && it.call_id) outputs.set(it.call_id, parse(it.output));
  const timeOf = (id: unknown) => deal.mails.find((m) => m.id === Number(id))?.received_at ?? null;
  let mails = 0, quoted = false;
  for (const it of items) {
    if (it.role === "user" && typeof it.content === "string") {
      const m = it.content.match(MAIL);
      if (m) {
        const [text, ...att] = m[6].trim().split(/\n\n(?=\[attachment [^\]\n]+\]\n)/);
        const files = att.map((a) => (a.match(/^\[attachment ([^\]\n]+)\]/) ?? [])[1]).filter(Boolean);
        const cust = m[2] === deal.data.customer;
        out.push({ icon: "mail", tone: "in", title: mails === 0 ? "Request came in" : cust ? "The customer wrote back" : who(m[2]) + " wrote", sub: m[5] + (files.length ? " · read " + files.join(", ") : ""), at: m[3], body: text });
        mails++;
        continue;
      }
      for (const part of it.content.split(/\n\n(?=Message from |Update from the system)/)) {
        const op = part.match(/Message from (.+?) \(a person on our team[^)]*\): ([\s\S]*)/), sys = part.match(/Update from the system \(([^)]*)\): ([\s\S]*)/);
        if (op) out.push({ icon: "user", tone: "you", title: op[1] + " told the AI Worker", sub: op[2].trim() });
        else if (sys) out.push({ icon: "info", tone: "work", title: "News on this shipment", sub: sys[2].trim().split("\n")[0], body: sys[2].trim() });
      }
    } else if (it.type === "function_call" && it.name) {
      const a = parse(it.arguments) ?? {}, o = outputs.get(it.call_id ?? "") ?? null;
      if (o && "error" in o) { out.push({ icon: "triangleAlert", tone: "hot", title: plain(it.name) + " did not work", sub: String(o.error) }); continue; }
      if (it.name === "get_offers") {
        const opts: any[] = o?.options ?? [], rec = opts.find((x) => x.option === o?.recommended);
        if (o?.missing) out.push({ icon: "circleHelp", tone: "work", title: "Could not price it yet", sub: "Missing: " + o.missing.join(", ") });
        else if (!opts.length) out.push({ icon: "loader", tone: "work", title: "Asked the airlines for prices", sub: o?.still_waiting_for?.length ? "Waiting for " + o.still_waiting_for.join(", ") : "No offer yet" });
        else out.push({ icon: "tag", tone: "work", title: "Compared " + opts.length + (opts.length === 1 ? " offer" : " offers"), sub: rec ? rec.airline + " is the " + (a.preference ?? "best") + " one at " + eur(rec.total) : undefined,
          rows: opts.map((x) => [String(x.airline), x.transit_days + " days · " + x.source, eur(x.total), x.option === o?.recommended]) });
      } else if (it.name === "send_mail") {
        const first = a.kind === "quote" && !quoted; if (a.kind === "quote") quoted = true;
        out.push({ icon: "send", tone: "out", title: SENT[a.kind] ?? "Mail sent", at: timeOf(o?.sent),
          sub: (o?.recorded_quote ? o.recorded_quote : "") + (first && deal.data.quote && deal.data.quote.response_seconds >= 1 ? (o?.recorded_quote ? " · " : "") + Math.round(deal.data.quote.response_seconds) + " s after the request" : "") || undefined, body: String(a.body ?? "") });
      } else if (it.name === "book") {
        const changed = deal.data.booking?.price_changed;
        out.push({ icon: "plane", tone: changed ? "hot" : "ok", title: o?.booking_reference ? "Booked the flight" : "Asked the airline to book", sub: [deal.data.booking?.airline, o?.booking_reference ?? o?.team_reference, changed ? "at " + changed.booked + " instead of " + changed.quoted : null].filter(Boolean).join(" · ") });
      } else if (it.name === "mail_carrier") out.push({ icon: "send", tone: "work", title: "Wrote to " + who(String(a.to ?? "the carrier")), sub: String(a.subject ?? ""), body: String(a.body ?? "") });
      else if (it.name === "carrier_status") out.push({ icon: "plane", tone: "work", title: "Asked the airline where it is", sub: o?.carrier_reply ? String(o.carrier_reply).split("\n")[0] : undefined });
      else if (it.name === "crm") out.push({ icon: "search", tone: "work", title: "Looked up earlier shipments", sub: (o?.total_matches ?? 0) + " found for “" + a.query + "”" });
      else if (it.name === "note") out.push(a.flag === "red" || a.flag === "yellow" ? { icon: "flag", tone: "hot", title: "Flagged for the desk", sub: String(a.text ?? "") } : { icon: "brain", tone: "work", title: "Noted for next time", sub: String(a.text ?? "") });
      else if (it.name === "no_reply") out.push({ icon: "check", tone: "ok", title: "No answer needed", sub: String(a.reason ?? "") });
      else if (it.name === "browser") { if (out[out.length - 1]?.title !== "Read a price on the rate portal") out.push({ icon: "search", tone: "work", title: "Read a price on the rate portal", sub: a.airline ? String(a.airline) : undefined }); }
      else if (it.name === "ask_person") continue;
      else if (it.name !== "deal") out.push({ icon: "check", tone: "work", title: plain(it.name) });
    }
  }
  return out;
}
