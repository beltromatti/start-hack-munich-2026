"""Build deck/index.html, the click-through pitch, from the slides built in ../storyboard.html.

The storyboard stays the one source: a slide changed there changes here on the next run.
Run: uv run --with beautifulsoup4 python deck/build.py
"""
import re
import shutil
from pathlib import Path

from bs4 import BeautifulSoup

CI = Path(__file__).resolve().parent.parent
OUT = CI / "deck"
src = (CI / "storyboard.html").read_text()
soup = BeautifulSoup(src, "html.parser")

style = soup.find("style").decode_contents()
fonts = soup.find("link", rel="stylesheet")["href"]
mark = str(soup.find("filter", id="mk-goo").find_parent("svg"))
story = soup.find(id="story6")


def slide_under(h4_start: str):
    """The 16:9 slide that follows the h4 whose text starts with h4_start."""
    for h in story.find_all("h4"):
        if h.get_text().strip().startswith(h4_start):
            ts = h.find_parent("div").find(class_="ts")
            return ts
    raise SystemExit(f"no slide under h4 '{h4_start}'")


# (h4 in the storyboard or a special, the speaker note)
ORDER = [
    ("1 · Night", "2 a.m. Your forwarders sleep. Ships and planes do not."),
    ("2 · Money at stake", "This is the press on our industry. Slow quotes cost real money."),
    ("SWARM", "Click once: a mail comes in. Everyone builds this. That's not what you want."),
    ("3 · Calm", "One agent per deal. She decides. Code guarantees every number."),
    ("4 · Inputs to outputs", "Every channel in, one desk out."),
    ("5 · Why it fits", "Hyper individualised, kept simple."),
    ("6 · How you run her", "Two ways to run her."),
    ("7 · Day", "She gets better every night."),
    ("B · Backup", "Backup: what our agents saw."),
    ("B2 · How it works", "Backup: how Giulia works."),
]

slides = []
for key, note in ORDER:
    if key == "SWARM":
        html = ('<div class="ts swarm"><iframe data-src="swarm.html" title="The swarm" loading="lazy"></iframe>'
                '<button class="play" type="button">Play the swarm</button></div>')
    else:
        ts = slide_under(key)
        ts = BeautifulSoup(str(ts), "html.parser").find(class_="ts")
        ts["class"] = [c for c in ts["class"] if c != "ar"] + (["ar"] if "B2" in key else [])
        html = str(ts)
    slides.append((key, note, html))

frames = set(re.findall(r"frames/r/[\w.-]+\.jpg", "".join(h for _, _, h in slides)))
(OUT / "frames" / "r").mkdir(parents=True, exist_ok=True)
for f in frames:
    shutil.copy(CI / f, OUT / f)
shutil.copy(CI / "swarm-overkill" / "index.html", OUT / "swarm.html")

body = "\n".join(
    f'<section class="st" data-key="{k}" aria-label="Slide {i + 1}"{" hidden" if i else ""}>{h}'
    f'<p class="note">{n}</p></section>'
    for i, (k, n, h) in enumerate(slides)
)

DECK_CSS = """
html,body{margin:0;height:100%;background:#14161a;overflow:hidden}
.st{position:fixed;inset:0;display:grid;place-items:center;padding:0}
.st[hidden]{display:none!important}
h1.tt{margin:0}
.st>.ts{width:min(100vw,177.78vh);max-width:none;border:0;border-radius:0}
.ar{aspect-ratio:16/9!important;display:block!important;padding:0!important}
.ar .ab,.ar .tt,.ar .sm,.ar .lg{position:absolute!important}
.ar .ln{display:block!important}
.swarm{background:#0b0c0f}.swarm iframe{position:absolute;left:0;top:0;width:1920px;height:1080px;border:0;transform-origin:0 0}
.play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font:500 18px Inter,sans-serif;padding:14px 22px;border-radius:10px;border:1px solid #3a3f48;background:#1c1f25;color:#eceae2;cursor:pointer}
.note{position:fixed;left:max(16px,env(safe-area-inset-left,0px));bottom:12px;margin:0;font:400 13px Inter,sans-serif;color:#9a978c;opacity:0;transition:opacity .2s}
body.notes .note{opacity:1}
.nav{position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:10px;display:flex;gap:8px;align-items:center;font:400 13px Inter,sans-serif;color:#9a978c;z-index:9}
.nav button{font:inherit;color:#eceae2;background:#1c1f25;border:1px solid #3a3f48;border-radius:8px;padding:6px 12px;cursor:pointer}
@media (max-width:760px){.st>.ts{width:100vw}.fly:nth-of-type(n+3),.clip:nth-of-type(n+4){display:none}}
"""

JS = """
const S=[...document.querySelectorAll('.st')];let i=0;
const n=document.getElementById('n');
function go(k){i=Math.max(0,Math.min(S.length-1,k));S.forEach((s,j)=>s.hidden=j!==i);
  n.textContent=(i+1)+' / '+S.length;
  document.querySelectorAll('.swarm iframe').forEach(f=>{f.removeAttribute('src');f.nextElementSibling.hidden=false});
  try{history.replaceState(null,'','#s'+(i+1))}catch(e){}}
function play(){const f=S[i].querySelector('.swarm iframe');if(!f)return false;
  if(f.getAttribute('src'))return false;f.src=f.dataset.src;fit();f.nextElementSibling.hidden=true;return true}
document.addEventListener('keydown',e=>{
  if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();if(!play())go(i+1)}
  if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();go(i-1)}
  if(e.key==='n')document.body.classList.toggle('notes');
  if(e.key==='f'&&document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().catch(()=>{});});
document.getElementById('p').onclick=()=>go(i-1);document.getElementById('x').onclick=()=>{if(!play())go(i+1)};
document.querySelectorAll('.play').forEach(b=>b.onclick=play);
function fit(){document.querySelectorAll('.swarm').forEach(s=>{const w=s.clientWidth||innerWidth;s.querySelector('iframe').style.transform='scale('+(w/1920)+')'})}
addEventListener('resize',fit);
const h=parseInt((location.hash.match(/s(\\d+)/)||[])[1]);go(h?h-1:0);
"""

page = f"""<title>Milan Forwarding Pitch</title>
<meta name="page-kind" content="deck">
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="{fonts}">
<style>{style}{DECK_CSS}</style>
{mark}
{body}
<div class="nav"><button id="p" type="button">Back</button><span id="n"></span><button id="x" type="button">Next</button></div>
<script>{JS}</script>
"""
page = re.sub(r'<b class="tt([^"]*)"([^>]*)>(.*?)</b>', r'<h1 class="tt\1"\2>\3</h1>', page, count=1, flags=re.S)
(OUT / "index.html").write_text(page)
print(f"{len(slides)} slides, {len(frames)} frames -> {OUT / 'index.html'}")
