// Read-only team overview with an email login (allowlisted emails + team password, signed session cookie).
// /api/5u/* proxies GETs to 5U with the team key, which stays a Worker secret and never reaches the browser.
// Nothing here can send mail, book or touch the gateway.
const ALLOWED_PATHS = [
  /^\/v1\/board$/,
  /^\/v1\/board\/me$/,
  /^\/v1\/mailbox\/messages$/,
  /^\/v1\/mailbox\/messages\/\d+$/,
];
const COOKIE = "fo_session";
const DAYS = 3;
const enc = new TextEncoder();

const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
async function hmac(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}
function same(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
const allowed = (env) => (env.ALLOWED_EMAILS || "").toLowerCase().split(",").map((s) => s.trim()).filter(Boolean);

async function sessionEmail(req, env) {
  const c = (req.headers.get("cookie") || "").split(/;\s*/).find((x) => x.startsWith(COOKIE + "="));
  if (!c) return null;
  const [payload, sig] = c.slice(COOKIE.length + 1).split(".");
  if (!payload || !sig || !same(sig, await hmac(env.SESSION_SECRET, payload))) return null;
  const [email, exp] = atob(payload.replace(/-/g, "+").replace(/_/g, "/")).split("|");
  if (!email || Number(exp) < Date.now() / 1000 || !allowed(env).includes(email)) return null;
  return email;
}

function loginPage(error = "") {
  const msg = error ? `<p class="err">${error}</p>` : "";
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forwarder Overview · Sign in</title>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d0d0e;color:#ededed;font:15px/1.4 "Schibsted Grotesk",system-ui,sans-serif;padding:16px;box-sizing:border-box}
form{width:100%;max-width:360px;background:#141415;border:1px solid #1f1f20;border-radius:14px;padding:26px;display:flex;flex-direction:column;gap:14px}
h1{margin:0;font-size:24px}p{margin:0;color:#8c8c8c}label{display:flex;flex-direction:column;gap:6px;color:#a9a9a9;font-size:13px}
input{background:#1b1b1c;border:1px solid #2a2a2b;border-radius:10px;padding:12px;color:#ededed;font:inherit}
input:focus{outline:2px solid #ededed;outline-offset:1px}
button{background:#ededed;color:#0d0d0e;border:0;border-radius:99px;padding:12px;font:inherit;font-weight:700;cursor:pointer;min-height:44px}
.err{color:#f26d6d}
</style></head><body>
<form method="post" action="/login">
<h1>Forwarder Overview</h1><p>START Milan · read-only</p>${msg}
<label>Email<input name="email" type="email" autocomplete="username" required></label>
<label>Team password<input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">Sign in</button>
</form></body></html>`, { status: error ? 401 : 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    if (url.pathname === "/login" && req.method === "POST") {
      const form = await req.formData();
      const email = String(form.get("email") || "").trim().toLowerCase();
      const pass = String(form.get("password") || "");
      if (!allowed(env).includes(email) || !same(pass, env.PASSWORD || "")) return loginPage("Email or password is not right.");
      const payload = b64url(enc.encode(`${email}|${Math.floor(Date.now() / 1000) + DAYS * 86400}`));
      const token = `${payload}.${await hmac(env.SESSION_SECRET, payload)}`;
      return new Response(null, { status: 303, headers: {
        location: "/", "set-cookie": `${COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${DAYS * 86400}` } });
    }
    if (url.pathname === "/login") return loginPage();
    if (url.pathname === "/logout") {
      return new Response(null, { status: 303, headers: { location: "/login", "set-cookie": `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0` } });
    }

    const email = await sessionEmail(req, env);
    if (!email) {
      if (url.pathname.startsWith("/api/")) return Response.json({ error: "login required" }, { status: 401 });
      return Response.redirect(new URL("/login", url).toString(), 303);
    }

    if (url.pathname === "/api/me") return Response.json({ email });
    if (url.pathname.startsWith("/api/5u/")) {
      if (req.method !== "GET") return new Response("read only", { status: 405 });
      const path = url.pathname.slice("/api/5u".length);
      if (!ALLOWED_PATHS.some((r) => r.test(path))) return new Response("not allowed", { status: 404 });
      const upstream = await fetch(env.FIVEU_BASE_URL + path + url.search, {
        headers: { "X-API-Key": env.FIVEU_API_KEY, accept: "application/json" },
      });
      return new Response(upstream.body, {
        status: upstream.status,
        headers: { "content-type": "application/json", "cache-control": "no-store" },
      });
    }
    return env.ASSETS.fetch(req);
  },
};
