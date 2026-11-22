import { DEMO, demo } from "./demo";

export type BrowserActivity = { since: number; updated_at: number; active: boolean; action: string; airline: string | null; note: string };

export type DealRow = {
  id: string; status: string; updated_at: number; customer: string | null; subject: string | null;
  route: string | null; weight_kg: string | null; preference: string | null; quote: string | null;
  response_seconds: number | null; booking: string | null; flag: string | null; cost_usd: number;
  browser_activity?: BrowserActivity | null;
  needs_person?: { since: number; kind: "page" | "answer"; note: string; airline: string | null } | null;
};

export type Attachment = { id: number; filename: string; content_type?: string; size?: number };

export type Mail = {
  id: number; direction: "in" | "out"; sender: string; recipient: string; subject: string; body: string;
  received_at: string | null; kind: string | null; attachments?: Attachment[] | null; read?: string | null;
};

export type Item = {
  type?: string; role?: string; content?: unknown; name?: string; arguments?: string; call_id?: string;
  output?: string | { type: string; text?: string; image_url?: string }[];
};

export type Option = {
  option: string; airline: string; transit_days: number; total: string; source: string;
  pickup: { trucker: string; pickup_hours: number } | null; bookable_reference: string | null;
  carrier_note: string | null;
};

export type EventRow = {
  id: number; ts: number; run_id: string | null; agent: string; kind: string; summary: string;
  tokens_in: number; tokens_out: number; cost_usd: number | null;
};

export type Deal = {
  id: string; status: string; updated_at: number;
  data: {
    root: number; customer: string; subject: string; received_at: string; preference?: string;
    request?: Record<string, string | number | null>; quote?: { amount: string; option: string; response_seconds: number };
    booking?: { booking_reference?: string; team_reference: string; status: string; airline: string; route: string;
      via?: string; amount?: string; price_changed?: { quoted: string; booked: string };
      carrier_status?: { text: string; at: string } };
    notes?: { at: number; text: string; flag: string }[]; flag?: string;
    browser_activity?: BrowserActivity | null;
    person_needed?: { since: number; kind: "page" | "answer"; note: string; airline: string | null } | null;
  };
  mails: Mail[]; carrier_mails?: Mail[]; events: EventRow[];
  usage: { tokens_in: number; tokens_out: number; llm_calls: number; cost_usd: number };
  session: { status: string; items: Item[] } | null;
};

export type Board = {
  me: {
    team?: string; rank?: number; total?: number; scores_revealed?: boolean;
    requests?: Record<string, unknown>[]; bookings?: Record<string, unknown>[];
  };
  public: {
    overview?: { rounds_sent: number; teams: number; accepted: number; bookings: number };
    ranking?: { rank: number; team: string; name: string; total: number; accepted: number; answered: number;
      accept_rate: number | null; bookings: number; reference_team: boolean; human: number }[];
    rounds?: Record<string, unknown>[];
  };
};

export type Health = { ok: boolean; worker: boolean; llm: string; models: { agent: string; effort: string } };
export type Usage = { tokens_in: number; tokens_out: number; llm_calls: number; cost_usd: number };

export type Account = { username: string; name: string; role: "ops" | "sales" | "carriers" };
export type Me = { account: Account | null; open: boolean };

// A 401 means the session ended (signed out, expired): the app goes back to the sign-in.
const gone = (r: Response) => { if (r.status === 401) window.dispatchEvent(new Event("desk:signed-out")); };

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (DEMO) return demo<T>(path);
  const r = await fetch(path, { signal, credentials: "same-origin" });
  if (!r.ok) { gone(r); throw new Error(`${r.status} ${path}`); }
  return r.json();
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  if (DEMO) return demo<T>(path, body);
  const r = await fetch(path, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { if (path !== "/api/login") gone(r); throw new Error(`${r.status} ${await r.text()}`); }
  return r.json();
}

