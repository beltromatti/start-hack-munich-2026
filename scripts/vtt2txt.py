"""Turn a YouTube auto-caption .vtt into plain text with a timestamp every ~60 s.

Usage: python3 -I vtt2txt.py <in.vtt> <out.txt>
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8", errors="replace").read().splitlines()
out = []
last = None
cur_t = 0
next_mark = 0
for ln in lines:
    m = re.match(r"(\d+):(\d+):(\d+)\.\d+ -->", ln)
    if m:
        cur_t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        continue
    if not ln.strip() or ln.startswith(("WEBVTT", "Kind:", "Language:")):
        continue
    ln = re.sub(r"<[^>]+>", "", ln).strip()
    if not ln or ln == last:
        continue
    if cur_t >= next_mark:
        out.append(f"\n[{cur_t // 60:02d}:{cur_t % 60:02d}]")
        next_mark = cur_t + 60
    out.append(ln)
    last = ln
text = " ".join(out)
open(dst, "w", encoding="utf-8").write(text)
print(dst, len(text.split()), "words")
