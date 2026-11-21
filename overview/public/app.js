// Read-only overview: 5U leaderboard + our results + mailbox, via the Worker's /api/5u proxy.
// Field names of /v1/board/me requests are not documented in detail, so every read is tolerant.
import { CARRIERS } from "./carriers.js";

const US = "start-milan";
const ROUND = 360;
const state = { mails: [], since: 0, me: null, board: null, tab: "requests", q: "" };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pick = (o, ...keys) => { for (const k of keys) if (o && o[k] !== undefined && o[k] !== null && o[k] !== "") return o[k]; return undefined; };
const ts = (s) => (s ? new Date(s).getTime() / 1000 : NaN);
const clock = (sec) => new Date(sec * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin" });
const dur = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const now = () => Date.now() / 1000;

async function get(path) {
  const r = await fetch("/api/5u" + path, { cache: "no-store" });
  if (r.status === 401) { location.href = "/login"; throw new Error("login required"); }
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function kindOf(m) {
  const f = (m.from || "").toLowerCase();
  if (f.startsWith("ratedesk@")) return "rate desk";
  if (f.startsWith("tracking@")) return "tracking";
  if (/booking .* confirmed/i.test(m.subject || "")) return "booking";
  if (CARRIERS[f]) return CARRIERS[f].kind === "airline" ? "airline" : "trucker";
  return "customer";
}
function lane(text) {
  const m = /([A-Z]{3})\s*(?:-|–|—|to|→|>)\s*([A-Z]{3})/.exec(text || "");
  return m ? `${m[1]} → ${m[2]}` : "";
}
function kg(text) { const m = /(\d[\d.,]*)\s*kg/i.exec(text || ""); return m ? `${m[1]} kg` : ""; }
function wants(text) {
  const t = (text || "").toLowerCase();
  if (/(fastest|urgent|asap|express|schnell|dringend|eilig|urgente|più veloce|najszybsz)/.test(t)) return "fastest";
  if (/(cheapest|lowest|best price|budget|günstig|billig|más barato|economico|najtańsz)/.test(t)) return "cheapest";
  return "—";
}
function customerName(m) { return (m.from || "").split("@")[0].replace(/[._-]+/g, " "); }

async function loadMail() {
  for (let i = 0; i < 20; i++) {
    const page = await get(`/v1/mailbox/messages?since_id=${state.since}&limit=200`);
    const items = page.messages || page.items || [];
    state.mails.push(...items);
    const next = page.next_since_id ?? (items.length ? items[items.length - 1].id : state.since);
    if (!items.length || next === state.since) break;
    state.since = next;
  }
}

function rfqs() {
  return state.mails.filter((m) => kindOf(m) === "customer" && !m.in_reply_to)
    .map((m) => ({ id: m.id, at: ts(m.received_at), from: m.from, customer: customerName(m), lane: lane(`${m.subject} ${m.body}`),
      kg: kg(`${m.subject} ${m.body}`), wants: wants(`${m.subject} ${m.body}`) }))
    .sort((a, b) => b.at - a.at);
}

function verdictTag(v) {
  const s = String(v || "").toLowerCase();
  if (s === "accepted") return ["Accepted", "t-green"];
  if (s === "rejected") return ["Rejected", "t-red"];
  if (s === "no answer") return ["Missed", "t-red"];
  if (s === "voided") return ["Voided", "t-grey"];
  if (s === "pending" || s === "open") return [s === "open" ? "Open" : "Pending", "t-yellow"];
  return [s || "Open", "t-yellow"];
}

function requests() {
  const scored = (state.me?.requests || []).map((r) => {
    const pts = pick(r, "points", "points_by_kind") || {};
    return {
      round: pick(r, "round", "round_no", "n"), sent: ts(pick(r, "sent_at", "sent", "received_at")),
      answered: ts(pick(r, "answered_at", "answered")), verdict: pick(r, "verdict", "status"),
      reason: pick(r, "reason", "reason_code", "code") || "", total: Number(pick(r, "total", "points_total") ?? (typeof pts === "number" ? pts : 0)) || 0,
      booked: !!pick(r, "booked"), subject: pick(r, "subject", "title") || "", raw: r,
    };
  });
  const mails = rfqs();
  return scored.map((s) => {
    const m = mails.find((x) => (s.subject && lane(s.subject) && lane(s.subject) === x.lane && Math.abs(x.at - s.sent) < 600))
      || mails.find((x) => Math.abs(x.at - s.sent) < 90);
    return { ...s, mail: m };
  });
}

function renderHeader() {
  const me = state.me, teams = state.board?.overview?.teams ?? state.board?.ranking?.length;
  $("points").textContent = me ? Math.round(me.total ?? 0).toLocaleString("en-US") : "—";
  $("rank").innerHTML = me?.rank ? `${esc(me.rank)}<span class="muted" style="font-size:16px">/${esc(teams ?? "?")}</span>` : "—";
  const last = rfqs()[0];
  const next = last ? last.at + ROUND - now() : NaN;
  const start = ts("2026-11-21T16:00:00+01:00");
  const nextTxt = now() < start ? `first request at 16:00` : next > 0 ? `next in ${dur(next)}` : `next any moment`;
  $("sub").textContent = `Saturday, 21 November · ${nextTxt}`;
  $("inboxCount").textContent = state.mails.length ? String(state.mails.length) : "";
  $("updated").textContent = `updated ${new Date().toLocaleTimeString("de-DE", { timeZone: "Europe/Berlin" })}`;
}

function renderAttention(reqs) {
  const rows = [];
  for (const m of rfqs()) {
    const age = now() - m.at;
    if (age > ROUND) continue;
    const scored = reqs.find((r) => r.mail?.id === m.id);
    if (scored && String(scored.verdict).toLowerCase() === "accepted") continue;
    const left = ROUND - age;
    rows.push({ lane: m.lane || "—", why: `${m.customer} · ${m.kg || "?"} · ${m.wants}`, tag: `${dur(left)} left`, cls: left < 90 ? "t-red" : "t-yellow" });
  }
  for (const r of reqs.slice().sort((a, b) => b.sent - a.sent)) {
    const v = String(r.verdict || "").toLowerCase();
    if (!["rejected", "no answer"].includes(v) || now() - r.sent > 3600) continue;
    rows.push({ lane: r.mail?.lane || `Round ${r.round ?? "?"}`, why: r.reason || (v === "no answer" ? "no answer sent" : "rejected"), tag: verdictTag(v)[0], cls: "t-red" });
  }
  $("attnSummary").textContent = rows.length ? `${rows.filter((x) => x.cls === "t-red").length} red · ${rows.filter((x) => x.cls === "t-yellow").length} yellow` : "";
  $("attention").innerHTML = rows.length
    ? rows.slice(0, 6).map((x) => `<div class="attn"><b>${esc(x.lane)}</b><span class="why">${esc(x.why)}</span><span class="tag ${x.cls}">${esc(x.tag)}</span></div>`).join("")
    : `<p class="empty">Nothing open. Everything is green.</p>`;
}

function renderChart(reqs) {
  const pts = reqs.filter((r) => Number.isFinite(r.sent)).sort((a, b) => a.sent - b.sent).slice(-30);
  if (pts.length < 2) { $("chart").innerHTML = `<p class="empty">The line starts with the first scored requests.</p>`; return; }
  const W = 520, H = 140, step = W / (pts.length - 1);
  const y = (v) => H - 6 - (Math.max(0, Math.min(100, v)) / 100) * (H - 12);
  const line = pts.map((r, i) => `${(i * step).toFixed(1)},${y(r.total).toFixed(1)}`).join(" ");
  const dots = pts.map((r, i) => (["rejected", "no answer"].includes(String(r.verdict).toLowerCase()) ? `<circle cx="${(i * step).toFixed(1)}" cy="${y(r.total).toFixed(1)}" r="4.5" fill="#f26d6d"></circle>` : "")).join("");
  $("chart").innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Points per request, last ${pts.length}"><polyline fill="none" stroke="#ededed" stroke-width="1.6" stroke-linejoin="round" points="${line}"></polyline>${dots}</svg>`;
}

function renderRequests(reqs) {
  const q = state.q.toLowerCase();
  let rows = reqs.length
    ? reqs.map((r) => {
        const [label, cls] = verdictTag(r.verdict);
        return { id: r.round != null ? `R${r.round}` : "", customer: r.mail?.customer || "", lane: r.mail?.lane || lane(r.subject), wants: r.mail?.wants || "",
          time: Number.isFinite(r.sent) ? clock(r.sent) : "", label: r.booked ? "Booked" : label, cls: r.booked ? "t-green" : cls, reason: r.reason, points: r.total ? Math.round(r.total) : (label === "Accepted" ? "0" : "…") };
      })
    : rfqs().map((m) => ({ id: `#${m.id}`, customer: m.customer, lane: m.lane, wants: m.wants, time: clock(m.at), label: "Not scored yet", cls: "t-yellow", reason: m.kg, points: "…" }));
  if (q) rows = rows.filter((r) => Object.values(r).join(" ").toLowerCase().includes(q));
  const head = `<div class="tr req th"><span>Request</span><span>Customer</span><span>Lane</span><span>Wants</span><span>Time</span><span>Status</span><span>Reason</span><span class="num">Points</span></div>`;
  $("requests").innerHTML = head + (rows.length ? rows.slice(0, 80).map((r) =>
    `<div class="tr req"><span class="muted">${esc(r.id)}</span><span>${esc(r.customer)}</span><b>${esc(r.lane)}</b><span class="muted">${esc(r.wants)}</span><span class="muted">${esc(r.time)}</span><span><span class="tag ${r.cls}">${esc(r.label)}</span></span><span class="muted">${esc(r.reason)}</span><b class="num">${esc(r.points)}</b></div>`).join("")
    : `<div class="tr req"><span class="empty" style="grid-column:1/-1">No requests yet. The first one arrives at 16:00.</span></div>`);
}

function renderInbox() {
  const q = state.q.toLowerCase();
  let rows = state.mails.slice().sort((a, b) => b.id - a.id);
  if (q) rows = rows.filter((m) => `${m.from} ${m.subject}`.toLowerCase().includes(q));
  const head = `<div class="tr mail th"><span>Time</span><span>Kind</span><span>From</span><span>Subject</span></div>`;
  const cls = { customer: "t-yellow", airline: "t-grey", trucker: "t-grey", "rate desk": "t-grey", tracking: "t-green", booking: "t-green" };
  $("inbox").innerHTML = head + rows.slice(0, 200).map((m) => {
    const k = kindOf(m), name = CARRIERS[(m.from || "").toLowerCase()]?.name || m.from;
    return `<div class="tr mail"><span class="muted">${esc(clock(ts(m.received_at)))}</span><span><span class="tag ${cls[k]}">${esc(k)}</span></span><span>${esc(name)}</span><span class="subj">${esc(m.subject)}</span></div>`;
  }).join("");
}

function renderStandings() {
  const rows = state.board?.ranking || [];
  const head = `<div class="tr std th"><span>#</span><span>Team</span><span class="num">Points</span><span class="num">Accepted</span><span class="num">Rate</span><span class="num">Booked</span><span class="num">Human</span></div>`;
  $("standings").innerHTML = head + rows.map((r) =>
    `<div class="tr std ${r.name === US ? "us" : ""}"><span class="muted">${esc(r.rank)}</span><span>${esc(r.team)}${r.name === US ? " (us)" : ""}</span><span class="num">${esc(Math.round(r.total))}</span><span class="num">${esc(r.accepted)}/${esc(r.answered)}</span><span class="num">${r.accept_rate == null ? "—" : esc(Math.round(r.accept_rate * 100)) + " %"}</span><span class="num">${esc(r.bookings)}</span><span class="num">${esc(r.human)}</span></div>`).join("");
}

function render() {
  const reqs = requests();
  renderHeader(); renderAttention(reqs); renderChart(reqs); renderRequests(reqs); renderInbox(); renderStandings();
}

let busy = false;
async function tick() {
  if (busy) return;
  busy = true;
  try {
    const [me, board] = await Promise.all([get("/v1/board/me"), get("/v1/board"), loadMail()]);
    state.me = me; state.board = board;
  } catch (e) {
    $("updated").textContent = `offline: ${e.message}`;
  } finally {
    busy = false;
  }
  render();
}

document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
  state.tab = b.dataset.tab;
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  for (const t of ["requests", "inbox", "standings"]) $(`tab-${t}`).hidden = t !== state.tab;
}));
$("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });

fetch("/api/me").then((r) => r.ok ? r.json() : null).then((m) => { if (m?.email) $("who").textContent = `Read-only · ${m.email}`; }).catch(() => {});
tick();
setInterval(tick, 10000);
setInterval(renderHeader, 1000);
