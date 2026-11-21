// Read-only team overview. Password gate for every path; /api/5u/* proxies GETs to 5U with the team key.
// The key stays a Worker secret and never reaches the browser. Nothing here can send mail, book or post.
const ALLOWED = [
  /^\/v1\/board$/,
  /^\/v1\/board\/me$/,
  /^\/v1\/mailbox\/messages$/,
  /^\/v1\/mailbox\/messages\/\d+$/,
];

function authorized(req, env) {
  const h = req.headers.get("authorization") || "";
  if (!h.startsWith("Basic ") || !env.PASSWORD) return false;
  let decoded = "";
  try { decoded = atob(h.slice(6)); } catch { return false; }
  const pass = decoded.slice(decoded.indexOf(":") + 1);
  if (pass.length !== env.PASSWORD.length) return false;
  let diff = 0;
  for (let i = 0; i < pass.length; i++) diff |= pass.charCodeAt(i) ^ env.PASSWORD.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(req, env) {
    if (!authorized(req, env)) {
      return new Response("Login required", {
        status: 401,
        headers: { "WWW-Authenticate": 'Basic realm="Forwarder overview", charset="UTF-8"' },
      });
    }
    const url = new URL(req.url);
    if (url.pathname.startsWith("/api/5u/")) {
      if (req.method !== "GET") return new Response("read only", { status: 405 });
      const path = url.pathname.slice("/api/5u".length);
      if (!ALLOWED.some((r) => r.test(path))) return new Response("not allowed", { status: 404 });
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
