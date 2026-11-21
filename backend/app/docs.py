"""Attachments to text, so the model reads what a person would see. pdf, xlsx, docx, txt/csv; images are named."""
import io


def text(filename: str, raw: bytes) -> str:
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
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
        if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return f"[image attachment {filename}: not read as text]"
        if name.endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")):
            return f"[audio attachment {filename}: not read as text]"
        text = raw.decode("utf-8", errors="replace")
        if text.count("\ufffd") > max(8, len(text) // 50):  # binary, not text: say so instead of passing noise on
            return f"[binary attachment {filename}: not read as text]"
        return text
    except Exception as e:
        return f"[could not read {filename}: {e!r}]"
