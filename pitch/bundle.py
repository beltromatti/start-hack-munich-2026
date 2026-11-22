"""Build the copy of the deck that is published as a claude.ai artifact.

The artifact host wraps the page in its own document and serves every file from one
folder, so the copy has no <html>/<head>/<body> tags and no "../" paths.

    python3 bundle.py <out dir>
"""
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
out = Path(sys.argv[1])
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)

page = (HERE / "deck/index.html").read_text()
page = re.sub(r"<!doctype html>|</?html[^>]*>|</?head>|</?body>|<meta (charset|name=\"viewport\")[^>]*>", "", page, flags=re.I)
page = re.sub(r"<title>.*?</title>", "<title>Giulia Pitch Deck</title>", page, count=1)
page = page.replace("../shots/", "shots/").replace("../swarm-overkill/", "swarm/")
page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
assert "../" not in page, "a path still leaves the folder"
(out / "index.html").write_text(page.lstrip())

shutil.copy(HERE / "deck/deck.css", out / "deck.css")
shutil.copytree(HERE / "deck/frames", out / "frames")
(out / "shots").mkdir()
for name in re.findall(r"shots/([\w.-]+)", page):
    shutil.copy(HERE / "shots" / name, out / "shots" / name)
(out / "swarm").mkdir()
shutil.copy(HERE / "swarm-overkill/index.html", out / "swarm/index.html")

for f in sorted(p for p in out.rglob("*") if p.is_file()):
    print(f.relative_to(out), f.stat().st_size)
