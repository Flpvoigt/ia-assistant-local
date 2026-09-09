"""Conversão local: sem executar documentos, macros ou buscar recursos externos."""
from __future__ import annotations

import io
import textwrap
import warnings
from pathlib import Path

from pypdf import PdfReader

from .attachments import TEXT_SUFFIXES, decode_attachment, document_text


def convert_to_pdf(name: str, mime_type: str, data: str) -> bytes:
    raw = decode_attachment(data)
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted or not reader.pages:
                raise ValueError("PDF protegido ou vazio.")
        except Exception as exc:
            raise ValueError("PDF inválido ou protegido.") from exc
        return raw
    try:
        from PIL import Image, ImageOps
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError("Instale as dependências atualizadas: python -m pip install -r requirements.txt") from exc

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as original:
                    if original.width * original.height > 20_000_000:
                        raise ValueError("Imagem excede 20 megapixels.")
                    picture = ImageOps.exif_transpose(original).convert("RGB")
                    scale = min((width - 80) / picture.width, (height - 80) / picture.height)
                    w, h = picture.width * scale, picture.height * scale
                    pdf.drawImage(ImageReader(picture), (width-w)/2, (height-h)/2, w, h)
        except Exception as exc:
            raise ValueError("Imagem inválida ou grande demais para converter.") from exc
        pdf.showPage()
    elif suffix in TEXT_SUFFIXES or suffix == ".docx" or mime_type.startswith("text/"):
        text = document_text(name, raw)
        if not text.strip() or len(text) > 200_000:
            raise ValueError("Converta documentos com texto entre 1 e 200.000 caracteres.")
        # Fixed-width wrapping preserves code indentation; HTML is printed, never executed.
        pdf.setTitle(Path(name).name[:180])
        page = 0
        y = 0
        for paragraph in text.splitlines():
            for line in textwrap.wrap(paragraph.expandtabs(4), width=88, replace_whitespace=False,
                                      drop_whitespace=False) or [""]:
                if y < 48:
                    if page:
                        pdf.showPage()
                    page += 1
                    pdf.setFont("Helvetica", 8)
                    pdf.drawString(40, 26, f"Oráculo - página {page}")
                    pdf.setFont("Courier", 9.5)
                    y = height - 45
                pdf.drawString(40, y, line)
                y -= 13
        pdf.showPage()
    else:
        raise ValueError("Conversão disponível para texto, código, DOCX, PNG, JPG, WebP e PDF.")
    pdf.save()
    return output.getvalue()
