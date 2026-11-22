"""Build the stage deck: the room deck plus the slides only the big pitch has.

The stage deck is never edited by hand. It is the room deck (deck/index.html, bundled by
bundle.py) with the sections of stage/slides.html added, so every fix to the room deck
reaches the stage deck on the next build.

    python3 stage.py <out dir>      then open <out dir>/index.html

Added slides play by their data-o number: 0.5 the sung opener, 2.5 the challenge slide.
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
out = Path(sys.argv[1])

subprocess.run([sys.executable, HERE / "bundle.py", out], check=True, stdout=subprocess.DEVNULL)

page = (out / "index.html").read_text()
slides = (HERE / "stage/slides.html").read_text()
slides = slides[slides.index("<section"):]  # the bundle carries no comments

# A slide with a video: the first key or click plays it, the next one moves on.
script = """<script>
(function(){
  const cur=()=>document.querySelector('.st:not([hidden]) video');
  function start(){const v=cur();if(!v||v.dataset.played)return false;v.dataset.played=1;
    v.nextElementSibling.hidden=true;v.play();return true}
  addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)&&start()){e.preventDefault();e.stopImmediatePropagation()}},true);
  document.getElementById('x').addEventListener('click',e=>{if(start())e.stopImmediatePropagation()},true);
  document.querySelectorAll('.sing .play').forEach(b=>b.onclick=start);
  new MutationObserver(()=>document.querySelectorAll('.st[hidden] video').forEach(v=>{v.pause();v.currentTime=0;
    delete v.dataset.played;v.nextElementSibling.hidden=false})).observe(document.body,{subtree:true,attributes:true,attributeFilter:['hidden']});
})();
</script>"""

marker = '<div class="nav">'
assert page.count(marker) == 1, "the room deck's nav moved"
page = page.replace(marker, slides + "\n" + marker)
page = page.replace('<link rel="stylesheet" href="deck.css">', '<link rel="stylesheet" href="deck.css">\n<link rel="stylesheet" href="stage.css">')
assert "stage.css" in page, "the room deck's stylesheet link moved"
page = page.replace("stage/despair.jpg", "despair.jpg").replace("stage/sings.mp4", "sings.mp4")
page = page.rstrip() + "\n" + script + "\n"
page = page.replace("<title>Giulia Pitch Deck</title>", "<title>Giulia Stage Deck</title>")
(out / "index.html").write_text(page)

css = (HERE / "stage/stage.css").read_text().replace("stage/despair.jpg", "despair.jpg")
(out / "stage.css").write_text(css)
for name in ("despair.jpg", "sings.mp4"):
    shutil.copy(HERE / "stage" / name, out / name)

for f in sorted(p for p in out.rglob("*") if p.is_file()):
    print(f.relative_to(out), f.stat().st_size)
