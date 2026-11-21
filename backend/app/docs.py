"""Attachments to text, so the model reads what a person would see, whatever the file: pdf (scanned pages too),
xlsx, xls, docx, slides and OpenDocument, rtf, old Word and Outlook files (their text runs), text in any common
encoding, zip and eml (what is inside them), pictures (png, jpg, gif, webp as they are; tiff, bmp, heic made png;
read by a model through the gateway) and voice messages (transcribed). What a file is comes from its first bytes
before its name. One reader for every mail: customers, carriers, the rate desk.
What cannot be read is named, with why, never passed on as noise."""
import io

AUDIO = (".mp3", ".wav", ".m4a", ".ogg", ".oga", ".aac", ".flac", ".webm", ".mp4", ".mpga", ".mpeg")
PICTURE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
CONVERTED = (".tif", ".tiff", ".bmp", ".heic", ".heif")  # pictures the model does not take as they are: made png first


def kind(filename: str, raw: bytes) -> str:
    """What a file is: its first bytes, when they say it, and the name's ending only when they do not. The name is
    what the sender typed: a pdf called `offer.dat`, a scan called `rates.txt`, a file with no ending at all are
    still a pdf, a picture, a workbook. 5U said the files get stranger; the reader used to go by the ending alone
    and passed everything else on as "binary attachment"."""
    name = (filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""
    h = raw[:16]
    if h.startswith(b"%PDF"):
        return ".pdf"
    if h.startswith(b"\x89PNG"):
        return ".png"
    if h.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if h.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if h[:4] == b"RIFF" and raw[8:12] in (b"WEBP", b"WAVE"):
        return ".webp" if raw[8:12] == b"WEBP" else ".wav"
    if h.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if h[:2] == b"BM" and int.from_bytes(raw[2:6], "little") == len(raw):
        return ".bmp"
    if raw[4:8] == b"ftyp":
        return ".heic" if raw[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis") else \
            ext if ext in AUDIO else ".m4a"
    if h.startswith((b"ID3", b"OggS", b"fLaC")):
        return ext if ext in AUDIO else ".mp3"
    if h.startswith(b"{\\rtf"):
        return ".rtf"
    if h.startswith(b"PK\x03\x04"):  # a zip: an office file is one, told apart by what is inside
        import zipfile
        try:
            names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
        except Exception:
            return ext
        for inside, what in (("word/document.xml", ".docx"), ("xl/workbook.xml", ".xlsx"), ("ppt/presentation.xml", ".pptx")):
            if inside in names:
                return what
        return ".odf" if "content.xml" in names and "mimetype" in names else ".zip"
    if h.startswith(b"\xd0\xcf\x11\xe0"):  # the old Office container: a workbook, or a Word file or an Outlook mail
        return ".xls" if b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k" in raw or b"B\x00o\x00o\x00k\x00" in raw else ".ole"
    return ext


def text(filename: str, raw: bytes, run_id: str | None = None, depth: int = 0) -> str:
    name = kind(filename, raw)
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
        if name.endswith(".xls"):  # the old Excel format, on 5U's list of attachment types (Sam, Sun 00:33)
            import xlrd
            wb = xlrd.open_workbook(file_contents=raw)
            rows = []
            for ws in wb.sheets():
                rows.append(f"# sheet {ws.name}")
                for i in range(ws.nrows):
                    cells = ["" if c in ("", None) else str(int(c)) if isinstance(c, float) and c == int(c) else str(c)
                             for c in ws.row_values(i)]
                    if any(cells):
                        rows.append("\t".join(cells))
            return "\n".join(rows)
        if name.endswith(".docx"):
            from docx import Document
            d = Document(io.BytesIO(raw))
            parts = [p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    parts.append("\t".join(c.text for c in row.cells))
            return "\n".join(parts)
        ext = name
        if ext in PICTURE:
            from . import llm
            return f"[picture {filename}, as read]\n" + llm.look(PICTURE[ext], raw, run_id=run_id)
        if ext in CONVERTED:
            from . import llm
            return f"[picture {filename}, as read]\n" + llm.look("image/png", _png(raw, ext), run_id=run_id)
        if name.endswith(AUDIO):
            from . import llm
            return f"[voice message {filename}, transcribed]\n" + llm.transcribe(raw, filename, run_id=run_id)
        if name.endswith(".zip") and depth < 2:
            return _zip(raw, run_id, depth)
        if name.endswith(".eml") and depth < 2:
            return _eml(raw, run_id, depth)
        if ext in (".pptx", ".odf", ".odt", ".ods", ".odp"):
            return _office_xml(raw)
        if ext == ".rtf":
            return _rtf(raw)
        if ext in (".ole", ".doc", ".msg", ".ppt"):
            return _runs(filename, raw)
        return _plain(filename, raw)
    except Exception as e:
        return f"[could not read {filename}: {e!r}]"


def pdf(title: str, lines: list[str]) -> bytes:
    """A one-page pdf of plain text lines (a title in bold, then the lines), written by hand: no library for it.
    Western text (cp1252, as Helvetica holds it); a character outside it becomes '?'."""
    def esc(s: str) -> str:
        b = s.encode("cp1252", "replace").decode("latin-1")
        return b.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT", "/F2 15 Tf", "56 790 Td", f"({esc(title)}) Tj", "/F1 10.5 Tf", "15 TL", "0 -10 Td"]
    ops += [f"T* ({esc(line)}) Tj" for line in lines[:46]]
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % x for x in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def _pdf(filename: str, raw: bytes, run_id: str | None) -> str:
    """A pdf's text; a page without text (a scan) is read from its pictures, like a photo."""
    from pypdf import PdfReader
    out = []
    for i, page in enumerate(PdfReader(io.BytesIO(raw)).pages, 1):
        t = (page.extract_text() or "").strip()
        if len(t) < 200:  # a scan: its text is in its pictures, also under a letterhead (pypdf needs Pillow for them)
            from . import llm
            try:
                for img in page.images:
                    mime = "image/png" if img.name.lower().endswith(".png") else "image/jpeg"
                    t += f"\n[page {i}, scanned, as read]\n" + llm.look(mime, img.data, run_id=run_id)
            except Exception as e:  # one page we cannot see does not cost the pages we can
                t += f"\n[page {i}: could not read its pictures: {e!r}]"
        out.append(t)
    return "\n".join(out)


def _png(raw: bytes, ext: str) -> bytes:
    """A picture in a format the model does not take (tiff from a scanner, bmp, a phone's heic), as png."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        if ext not in (".heic", ".heif"):
            raise
        return _heic(raw)  # Pillow has no heic of its own
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()


def _heic(raw: bytes) -> bytes:
    """A phone photo (heic): with pillow-heif when it is installed, else with macOS' own converter (production runs
    on a Mac). Anywhere else it is named as unreadable by the caller."""
    try:
        import pillow_heif
        from PIL import Image
        pillow_heif.register_heif_opener()
        out = io.BytesIO()
        Image.open(io.BytesIO(raw)).convert("RGB").save(out, "PNG")
        return out.getvalue()
    except ImportError:
        pass
    import os
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("sips"):
        raise RuntimeError("heic picture: no converter on this machine")
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.heic"), os.path.join(d, "out.png")
        with open(src, "wb") as f:
            f.write(raw)
        subprocess.run(["sips", "-s", "format", "png", src, "--out", dst], check=True, capture_output=True, timeout=30)
        with open(dst, "rb") as f:
            return f.read()


def _office_xml(raw: bytes) -> str:
    """Slides and OpenDocument files: the words in their xml, in order, one paragraph a line."""
    import re
    import zipfile
    parts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for n in sorted(z.namelist()):
            if n == "content.xml" or (n.startswith("ppt/slides/slide") and n.endswith(".xml")):
                x = z.read(n).decode("utf-8", "replace")
                x = re.sub(r"</(?:a:p|text:p|text:h|table:table-row)>", "\n", x)
                x = re.sub(r"</(?:table:table-cell|a:tc)>", "\t", x)
                parts.append(re.sub(r"[ \t]*\n\s*", "\n", _unescape(re.sub(r"<[^>]+>", "", x))).strip())
    return "\n\n".join(p for p in parts if p)


def _unescape(t: str) -> str:
    import html
    return html.unescape(t)


def _rtf(raw: bytes) -> str:
    """A rich text file as its words: control words dropped, \\par a new line, \\'e4 the character it encodes."""
    import re
    t = raw.decode("cp1252", "replace")
    t = re.sub(r"\{\\\*[^{}]*\}|\{\\(?:fonttbl|colortbl|stylesheet|info)(?:[^{}]|\{[^{}]*\})*\}", "", t)
    t = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), t)
    t = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), t)
    t = re.sub(r"\\\r?\n|\\(?:par|line|row)\b ?", "\n", t)  # a backslash at the line's end is a line break too
    t = re.sub(r"\\(?:tab|cell)\b ?", "\t", t)
    t = re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", "", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def _runs(filename: str, raw: bytes) -> str:
    """An old Word file or an Outlook mail (.doc, .msg): no parser here, but their text sits in the file as plain
    runs of characters, one or two bytes each. The runs a person could read are passed on, the rest is format."""
    import re
    wide = [m.group(0).decode("utf-16-le", "replace")
            for m in re.finditer(rb"(?:[\x20-\x7e\xa0-\xff\t\r\n]\x00){6,}", raw)]
    narrow = [m.group(0).decode("cp1252", "replace") for m in re.finditer(rb"[\x20-\x7e\xa0-\xff\t\r\n]{8,}", raw)]
    seen, out = set(), []
    for run in wide + narrow:
        run = run.replace("\r", "\n").strip()
        letters = sum(c.isascii() and (c.isalnum() or c in " .,:;/-()@") for c in run)  # accents are the few, not the most
        if len(run) >= 6 and letters >= len(run) * 0.7 and run not in seen:
            seen.add(run)
            out.append(run)
    if not out:
        return f"[binary attachment {filename}: not read as text]"
    return f"[{filename}: read as raw text runs, the layout is lost]\n" + "\n".join(out)[:20000]


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
