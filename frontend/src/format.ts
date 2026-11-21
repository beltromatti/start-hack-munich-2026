export function ago(ts: number | string | null | undefined): string {
  if (ts == null) return "";
  const t = typeof ts === "number" ? ts * 1000 : Date.parse(ts);
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(t).toLocaleDateString();
}

export function clock(ts: number | string | null | undefined): string {
  if (ts == null) return "";
  const t = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  return t.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function usd(x: number | null | undefined, digits = 4): string {
  return x == null ? "–" : `$${x.toFixed(digits)}`;
}

export function who(email: string | null | undefined): string {
  if (!email) return "–";
  const local = email.split("@")[0];
  return local.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const STATUS: Record<string, { label: string; tone: string }> = {
  new: { label: "New", tone: "neutral" },
  pricing: { label: "Pricing", tone: "live" },
  waiting_customer: { label: "Asked customer", tone: "warn" },
  quoted: { label: "Quoted", tone: "accent" },
  booked: { label: "Booked", tone: "ok" },
  lost: { label: "Lost", tone: "bad" },
};

export function parseJSON<T>(s: string | undefined): T | null {
  if (!s) return null;
  try { return JSON.parse(s) as T; } catch { return null; }
}
