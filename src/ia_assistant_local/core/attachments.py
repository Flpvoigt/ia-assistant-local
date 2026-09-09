from __future__ import annotations

import base64
import binascii
import io
from pathlib import Path

from pypdf import PdfReader

MAX_ATTACHMENT_BYTES = 5_000_000
MAX_EXTRACTED_CHARS = 12_000
TEXT_SUFFIXES = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".html", ".css",
    ".js", ".ts", ".py", ".java", ".c", ".cpp", ".h", ".sql", ".log",
}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def decode_attachment(data: str) -> bytes:
    if not isinstance(data, str) or not data:
        raise ValueError("Anexo vazio.")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Anexo inválido.") from exc
    if not raw or len(raw) > MAX_ATTACHMENT_BYTES:
        raise ValueError("O anexo deve ter no máximo 5 MB.")
    return raw


def extract_attachment(name: str, mime_type: str, data: str) -> dict[str, object]:
    safe_name = Path(name).name[:180]
    suffix = Path(safe_name).suffix.casefold()
    raw = decode_attachment(data)
    if mime_type == "application/pdf" or suffix == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for page in reader.pages[:40]:
            pages.append(page.extract_text() or "")
            if sum(map(len, pages)) >= MAX_EXTRACTED_CHARS:
                break
        text = "\n\n".join(pages).strip()[:MAX_EXTRACTED_CHARS]
        if not text:
            raise ValueError("O PDF não contém texto extraível.")
        return {"name": safe_name, "kind": "text", "content": text, "truncated": len(text) >= MAX_EXTRACTED_CHARS}
    if mime_type.startswith("text/") or suffix in TEXT_SUFFIXES:
        text = raw.decode("utf-8-sig", errors="replace").strip()
        return {"name": safe_name, "kind": "text", "content": text[:MAX_EXTRACTED_CHARS], "truncated": len(text) > MAX_EXTRACTED_CHARS}
    if mime_type in IMAGE_MIME_TYPES:
        return {"name": safe_name, "kind": "image", "mime_type": mime_type, "size": len(raw)}
    raise ValueError("Formato não permitido. Use PDF, texto, código, PNG, JPG ou WebP.")


def validate_image(data_url: str) -> str:
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise ValueError("Imagem inválida.")
    header, separator, encoded = data_url.partition(",")
    if not separator or ";base64" not in header:
        raise ValueError("Imagem inválida.")
    mime_type = header[5:].split(";", 1)[0]
    if mime_type not in IMAGE_MIME_TYPES:
        raise ValueError("Formato de imagem não permitido.")
    raw = decode_attachment(encoded)
    valid_signature = (
        (mime_type == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime_type == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"))
        or (mime_type == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
    )
    if not valid_signature:
        raise ValueError("O conteúdo não corresponde ao formato da imagem.")
    return data_url
