from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf", ".docx"}


def load_document(path: str | Path) -> dict:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix in {".md", ".markdown", ".txt"}:
        text = file_path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        text = _load_pdf(file_path)
    else:
        text = _load_docx(file_path)

    return {
        "filename": file_path.name,
        "path": str(file_path),
        "text": text.strip(),
    }


def load_documents(paths: list[str | Path]) -> list[dict]:
    return [load_document(path) for path in paths]


def _load_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PDF support requires pypdf. Install it or upload TXT/Markdown.") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _load_docx(path: Path) -> str:
    try:
        import docx
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("DOCX support requires python-docx. Install it or upload TXT/Markdown.") from exc

    doc = docx.Document(str(path))
    return "\n".join(paragraph.text for paragraph in doc.paragraphs)

