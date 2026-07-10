from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".log", ".yaml", ".yml", ".xml",
    ".pdf", ".docx", ".rtf", ".csv", ".tsv", ".xlsx", ".xls",
    ".json", ".jsonl", ".html", ".htm", ".pptx",
}

UPLOAD_TYPES = sorted(extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS)


def load_document(path: str | Path) -> dict:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    text = extract_document_bytes(file_path.name, file_path.read_bytes())

    return {
        "filename": file_path.name,
        "path": str(file_path),
        "text": text.strip(),
    }


def load_documents(paths: list[str | Path]) -> list[dict]:
    return [load_document(path) for path in paths]


def load_uploaded_document(uploaded) -> dict:
    text = extract_document_bytes(uploaded.name, uploaded.getvalue())
    return {"filename": uploaded.name, "path": uploaded.name, "text": text}


def extract_document_bytes(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        raise ValueError("Legacy .doc files are not supported reliably. Save the file as .docx and upload it again.")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix or 'no extension'}")

    if suffix in {".txt", ".md", ".markdown", ".log", ".yaml", ".yml", ".xml"}:
        text = _decode_text(data)
    elif suffix == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
    elif suffix == ".docx":
        import docx
        document = docx.Document(BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        text = "\n".join(parts)
    elif suffix == ".rtf":
        from striprtf.striprtf import rtf_to_text
        text = rtf_to_text(_decode_text(data))
    elif suffix in {".csv", ".tsv"}:
        import pandas as pd
        frame = pd.read_csv(BytesIO(data), sep="\t" if suffix == ".tsv" else ",")
        text = _frame_to_text(frame, filename)
    elif suffix in {".xlsx", ".xls"}:
        import pandas as pd
        sheets = pd.read_excel(BytesIO(data), sheet_name=None)
        text = "\n\n".join(_frame_to_text(frame, sheet) for sheet, frame in sheets.items())
    elif suffix in {".json", ".jsonl"}:
        raw = _decode_text(data)
        if suffix == ".jsonl":
            values = [json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            values = json.loads(raw)
        text = json.dumps(values, indent=2, ensure_ascii=False)
    elif suffix in {".html", ".htm"}:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(data, "html.parser").get_text("\n", strip=True)
    else:  # .pptx
        from pptx import Presentation
        presentation = Presentation(BytesIO(data))
        slides = []
        for index, slide in enumerate(presentation.slides, start=1):
            parts = [f"Slide {index}"]
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    parts.append(shape.text.strip())
                if getattr(shape, "has_table", False):
                    parts.extend(" | ".join(cell.text for cell in row.cells) for row in shape.table.rows)
            slides.append("\n".join(parts))
        text = "\n\n".join(slides)

    text = text.strip()
    if not text:
        raise ValueError(
            f"No readable text was found in {filename}. Scanned PDFs and image-only files require OCR, which is not included yet."
        )
    return text


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _frame_to_text(frame, label: str) -> str:
    frame = frame.fillna("")
    return f"Table: {label}\n{frame.to_csv(index=False)}"
