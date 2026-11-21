"""Extract visible text, links and media URLs from a saved HTML file.

Usage: python3 -I extract.py <file.html> [base_url] [--text N] [--media] [--links]
"""
import re
import sys
import html as htmllib
from html.parser import HTMLParser
from urllib.parse import urljoin


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text = []
        self.links = []
        self.media = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("img", "video", "source", "iframe"):
            for k in ("src", "data-src", "poster", "srcset"):
                if a.get(k):
                    self.media.append((tag, a[k].split(" ")[0]))
        if tag == "meta" and a.get("content") and (a.get("property") or a.get("name")) in (
            "og:image", "og:video", "og:title", "og:description", "description", "twitter:image",
        ):
            self.media.append(("meta:" + (a.get("property") or a.get("name")), a["content"]))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            t = data.strip()
            if t:
                self.text.append(t)


def main():
    path = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else ""
    flags = [a for a in sys.argv[2:] if a.startswith("--")]
    raw = open(path, encoding="utf-8", errors="replace").read()
    p = P()
    p.feed(raw)
    n = 6000
    for f in flags:
        if f.startswith("--text="):
            n = int(f.split("=")[1])
    if not flags or any(f.startswith("--text") for f in flags):
        print("== TEXT ==")
        print(htmllib.unescape(" | ".join(p.text))[:n])
    if not flags or "--links" in flags:
        print("== LINKS ==")
        seen = []
        for l in p.links:
            l = urljoin(base, l)
            if l not in seen:
                seen.append(l)
        print("\n".join(seen[:150]))
    if not flags or "--media" in flags:
        print("== MEDIA ==")
        seen = []
        for tag, u in p.media:
            u = urljoin(base, u) if not tag.startswith("meta:og:t") and not tag.startswith("meta:des") and not tag.startswith("meta:og:d") else u
            if (tag, u) not in seen and not u.startswith("data:"):
                seen.append((tag, u))
        for tag, u in seen[:150]:
            print(tag, u[:300])
        # media urls hidden in scripts / json
        extra = sorted(set(re.findall(r"https?://[^\"'\\\s)]+\.(?:mp4|webm|m3u8|mov)", raw)))
        yt = sorted(set(re.findall(r"(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/|vimeo\.com/(?:video/)?|loom\.com/(?:share|embed)/|wistia\.[a-z]+/(?:medias|embed/iframe)/)[\w-]+", raw)))
        print("== VIDEO FILES ==")
        print("\n".join(extra[:60]))
        print("== VIDEO EMBEDS ==")
        print("\n".join(yt[:60]))


main()
