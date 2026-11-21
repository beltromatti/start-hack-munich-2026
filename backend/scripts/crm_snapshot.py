"""The CRM as one HTML file: the built page with its JS, CSS and /api/crm data inlined. Opens in any browser,
offline, no server. Reads the register only.
Usage: DB_PATH=backend/data/crm-local.db uv run --project backend python backend/scripts/crm_snapshot.py <out.html>
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import main  # noqa: E402


def main_(out: Path) -> None:
    data = main.crm_all()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["npx", "vite", "build", "--outDir", tmp, "--emptyOutDir"], cwd=ROOT / "frontend", check=True,
                       env={**os.environ, "CRM_ONLY": "1"}, capture_output=True)
        html = (Path(tmp) / "crm.html").read_text()
        for href in re.findall(r'<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>', html):
            css = (Path(tmp) / href.lstrip("/")).read_text()
            html = re.sub(r'<link rel="stylesheet"[^>]*href="' + re.escape(href) + r'"[^>]*>', lambda _: f"<style>{css}</style>", html)
        html = re.sub(r'<link rel="modulepreload"[^>]*>', "", html)
        for src in re.findall(r'<script type="module" crossorigin src="([^"]+)"></script>', html):
            js = (Path(tmp) / src.lstrip("/")).read_text().replace("</script", "<\\/script")
            html = html.replace(f'<script type="module" crossorigin src="{src}"></script>', "")
            html = html.replace("</body>", f'<script type="module">{js}</script>\n</body>')
    blob = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    html = html.replace("</head>", f"<script>window.__CRM__ = {blob};</script>\n</head>")
    out.write_text(html)
    print(f"{out}: {len(html) // 1024} KB, {len(data['cases'])} cases")


if __name__ == "__main__":
    main_(Path(sys.argv[1]))
