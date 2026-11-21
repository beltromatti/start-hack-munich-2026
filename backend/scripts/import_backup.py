"""Fill a local register from the 5U backup (personal/backup5u), so the CRM runs on a machine that is not live.

Mails in and out go in as the forwarder stores them, board snapshots as `board` records. Insert-once: run it again
after the backup grew. Never point it at the live register.
Usage: DB_PATH=backend/data/crm-local.db uv run --project backend python backend/scripts/import_backup.py [backup dir]
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import store  # noqa: E402


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def main(src: Path) -> None:
    new = 0
    for m in load(src / "mails.jsonl"):
        new += store.save_mail(m, "in", "backup", handled=True)
    for m in load(src / "sent.jsonl"):
        new += store.save_mail(m, "out", "sent", handled=True)
    snaps = 0
    for f in sorted((src / "board").glob("*.json")):
        s = json.loads(f.read_text())
        at = time.mktime(time.strptime(s["at"], "%Y%m%d-%H%M%S"))
        rid = f"board-{int(at)}"
        if store.get(rid) is None:
            store.put(rid, "board", "snapshot", {"me": s["me"], "public": s["board"], "at": at})
            snaps += 1
    if snaps:
        store.kv_set("board_me", json.dumps(s["me"]))
        store.kv_set("board", json.dumps(s["board"]))
    print(f"{new} new mails, {snaps} new board snapshots into {store.settings.db_path}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "personal" / "backup5u")
