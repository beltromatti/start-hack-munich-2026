"""Build index.html: a local picture gallery of the competitor screenshots.

Usage: python3 -I scripts/gallery.py   (run from the research folder)
"""
import glob
import html
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOP = [
    ("scroll/5u-product-06.jpg", "5U AI", "Freight Data Summary card: route, goods, weight, date"),
    ("scroll/5u-product-07.jpg", "5U AI", "Observe your AI Worker: name, SOP, connections, capabilities, preferences"),
    ("scroll/5u-product-08.jpg", "5U AI", "Building blocks: Email Listener, AI Worker, Human in the Loop, Communicator"),
    ("scroll/5u-product-09.jpg", "5U AI", "Waiting Offer Approval: urgent tag, route, weight, price, Edit and Send Offer"),
    ("scroll/nexcade-00.jpg", "Nexcade", "Inbox card with the request and 'Follow this request'"),
    ("scroll/nexcade-01.jpg", "Nexcade", "The answer exists. It's in seven places."),
    ("scroll/nexcade-02.jpg", "Nexcade", "Timeline with a clock per step, agent steps, your calls, elapsed"),
    ("scroll/nexcade-03.jpg", "Nexcade", "Held for review, and account memory carried into the next request"),
    ("scroll/cargoone-ai-00.jpg", "cargo.one", "AI mode switch, Parsing Agent with extracted chips"),
    ("scroll/cargoone-ai-03.jpg", "cargo.one", "You control the pace: Co-pilot, Supervised, Autonomous"),
    ("scroll/zauber-product-06.jpg", "Zauber", "One thread: request, rates checked, draft ready, reply"),
    ("scroll/pallet-04.jpg", "Pallet", "Alert, options compared, rule applied, Approve"),
    ("scroll/pallet-05.jpg", "Pallet", "Action checklist with the system next to each step"),
]

SITES = [
    ("5U AI", ["sheets/5u-home.jpg", "sheets/5u-product.jpg", "sheets/5u-about.jpg"]),
    ("Zauber", ["sheets/zauber-home.jpg", "sheets/zauber-product.jpg", "sheets/zauber-whyus.jpg", "video/sheets/zauber-pe-walkthrough.jpg"]),
    ("Nexcade", ["sheets/nexcade.jpg"]),
    ("cargo.one", ["sheets/cargoone-ai.jpg"]),
    ("Wisor", ["sheets/wisor.jpg", "video/sheets/wisor-webinar-demo.jpg", "video/sheets/wisor-rate-mgmt-demo.jpg", "video/sheets/wisor-cargowise.jpg", "video/sheets/wisor-ignite.jpg"]),
    ("Raft", ["sheets/raft.jpg", "video/sheets/raft-first-look.jpg"]),
    ("CargoAi", ["sheets/cargoai.jpg", "video/sheets/cargoai-interview.jpg"]),
    ("Pallet", ["sheets/pallet.jpg"]),
    ("Vooma", ["sheets/vooma.jpg", "video/sheets/vooma-schedule.jpg"]),
    ("Augment", ["sheets/augment.jpg", "video/sheets/augment-augie-overview.jpg"]),
    ("HappyRobot", ["sheets/happyrobot.jpg", "video/sheets/happyrobot-agents.jpg"]),
    ("Levity", ["sheets/levity.jpg"]),
    ("Freightmate AI", ["sheets/freightmate.jpg"]),
    ("Nimble", ["sheets/nimble.jpg"]),
    ("Burt", ["sheets/burt.jpg"]),
    ("Fretie, FreighAI", ["video/sheets/fretie-quoting.jpg", "video/sheets/freighai.jpg"]),
]

parts = [
    "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
    "<meta name='viewport' content='width=device-width,initial-scale=1'>",
    "<title>Competitor gallery</title><style>",
    "body{margin:0;font:15px/1.5 -apple-system,system-ui,sans-serif;background:#f6f5f2;color:#1c2033}",
    "main{max-width:1500px;margin:0 auto;padding:24px 16px 80px}",
    "h1{font-size:26px;margin:8px 0 4px}h2{font-size:20px;margin:48px 0 12px;padding-top:12px;border-top:1px solid #d9d6cf}",
    "p{margin:4px 0 16px;color:#555b70}nav a{display:inline-block;margin:0 10px 6px 0;color:#2b3154}",
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:16px}",
    "figure{margin:0;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}",
    "figure img{display:block;width:100%;height:auto}figcaption{padding:10px 12px;font-size:14px}",
    "figcaption b{color:#d9512c}img.sheet{width:100%;height:auto;border-radius:10px;margin:0 0 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}",
    "</style></head><body><main>",
    "<h1>Competitor gallery</h1>",
    "<p>5U AI and its field, collected 21 Nov 2026. Text and pitch notes are in BRIEF.md. Click a picture for full size.</p><nav>",
]
parts.append("<a href='#top'>Screens to copy</a>")
for name, _ in SITES:
    parts.append(f"<a href='#{html.escape(name.split(',')[0].replace(' ', '-').lower())}'>{html.escape(name)}</a>")
parts.append("</nav><h2 id='top'>Screens to copy</h2><div class='grid'>")
for path, who, note in TOP:
    if os.path.exists(os.path.join(ROOT, path)):
        parts.append(
            f"<figure><a href='{path}'><img loading='lazy' src='{path}' alt='{html.escape(who)}: {html.escape(note)}'></a>"
            f"<figcaption><b>{html.escape(who)}</b> · {html.escape(note)}</figcaption></figure>"
        )
parts.append("</div>")
for name, sheets in SITES:
    anchor = name.split(",")[0].replace(" ", "-").lower()
    parts.append(f"<h2 id='{html.escape(anchor)}'>{html.escape(name)}</h2>")
    for s in sheets:
        if os.path.exists(os.path.join(ROOT, s)):
            label = "video frames" if s.startswith("video/") else "website, top to bottom"
            parts.append(f"<p>{html.escape(os.path.basename(s))} · {label}</p>")
            parts.append(f"<a href='{s}'><img class='sheet' loading='lazy' src='{s}' alt='{html.escape(name)} {label}'></a>")
parts.append("</main></body></html>")

out = os.path.join(ROOT, "index.html")
open(out, "w", encoding="utf-8").write("\n".join(parts))
print(out, len(glob.glob(os.path.join(ROOT, "scroll", "*.jpg"))), "scroll tiles")
