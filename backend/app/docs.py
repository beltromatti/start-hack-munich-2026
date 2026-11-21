"""Attachments to text, so the model reads what a person would see, whatever the file: pdf (scanned pages too),
xlsx, docx, text in any common encoding, zip and eml (what is inside them), pictures (read by a model through the
gateway) and voice messages (transcribed). One reader for every mail: customers, carriers, the rate desk.
What cannot be read is named, with why, never passed on as noise."""
import io

AUDIO = (".mp3", ".wav", ".m4a", ".ogg", ".oga", ".aac", ".flac", ".webm", ".mp4", ".mpga", ".mpeg")
PICTURE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


def text(filename: str, raw: bytes, run_id: str | None = None, depth: int = 0) -> str:
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            return _pdf(filename, raw, run_id)
        if name.endswith((".xlsx", ".xlsm")):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
            rows = []
            for ws in wb.worksheets:
                rows.append(f"# sheet {ws.title}")
                for r in ws.iter_rows(values_only=True):
                    if any(c is not None for c in r):
                        rows.append("\t".join("" if c is None else str(c) for c in r))
            return "\n".join(rows)
        if name.endswith(".docx"):
            from docx import Document
            d = Document(io.BytesIO(raw))
            parts = [p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    parts.append("\t".join(c.text for c in row.cells))
            return "\n".join(parts)
        ext = name[name.rfind("."):] if "." in name else ""
        if ext in PICTURE:
            from . import llm
            return f"[picture {filename}, as read]\n" + llm.look(PICTURE[ext], raw, run_id=run_id)
        if name.endswith(AUDIO):
            from . import llm
            return f"[voice message {filename}, transcribed]\n" + llm.transcribe(raw, filename, run_id=run_id)
        if name.endswith(".zip") and depth < 2:
            return _zip(raw, run_id, depth)
        if name.endswith(".eml") and depth < 2:
            return _eml(raw, run_id, depth)
        return _plain(filename, raw)
    except Exception as e:
        return f"[could not read {filename}: {e!r}]"


def _pdf(filename: str, raw: bytes, run_id: str | None) -> str:
    """A pdf's text; a page without text (a scan) is read from its pictures, like a photo."""
    from pypdf import PdfReader
    out = []
    for i, page in enumerate(PdfReader(io.BytesIO(raw)).pages, 1):
        t = (page.extract_text() or "").strip()
        if len(t) < 20:  # a scanned page: its text is in its pictures
            from . import llm
            for img in getattr(page, "images", []) or []:
                mime = "image/png" if img.name.lower().endswith(".png") else "image/jpeg"
                t += f"\n[page {i}, scanned, as read]\n" + llm.look(mime, img.data, run_id=run_id)
        out.append(t)
    return "\n".join(out)


def _plain(filename: str, raw: bytes) -> str:
    """Text as it was written: UTF-8, UTF-16 (with its mark, as Windows writes it) or Windows' western encoding."""
    encodings = (("utf-16",) if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ()) + ("utf-8-sig", "cp1252", "latin-1")
    t = ""
    for enc in encodings:
        try:
            t = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    control = sum(1 for c in t if ord(c) < 32 and c not in "\n\r\t\f")
    if control > max(8, len(t) // 50):  # binary, not text: say so instead of passing noise on
        return f"[binary attachment {filename}: not read as text]"
    return t


def _zip(raw: bytes, run_id: str | None, depth: int) -> str:
    import zipfile
    parts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            if not info.is_dir():
                parts.append(f"[{info.filename}]\n" + text(info.filename, z.read(info), run_id, depth + 1))
    return "\n\n".join(parts)


def _eml(raw: bytes, run_id: str | None, depth: int) -> str:
    from email import policy
    from email.parser import BytesParser
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    body = msg.get_body(preferencelist=("plain", "html"))
    parts = [f"From: {msg['from']}\nSubject: {msg['subject']}\n\n" + (body.get_content() if body else "")]
    for a in msg.iter_attachments():
        parts.append(f"[{a.get_filename()}]\n" + text(a.get_filename() or "", a.get_payload(decode=True) or b"",
                                                      run_id, depth + 1))
    return "\n\n".join(parts)
