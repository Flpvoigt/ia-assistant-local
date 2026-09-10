from __future__ import annotations

import io
import shutil
import warnings

from PIL import Image, ImageOps
from PIL.Image import DecompressionBombWarning

from .attachments import decode_attachment


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def extract_image_text(data: str, language: str = "por+eng") -> str:
    if not ocr_available():
        raise RuntimeError(
            "OCR local indisponível. Instale o Tesseract; no macOS: brew install tesseract tesseract-lang."
        )
    import pytesseract

    raw = decode_attachment(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.width * original.height > 20_000_000:
                    raise ValueError("A imagem para OCR deve ter no máximo 20 megapixels.")
                image = ImageOps.exif_transpose(original).convert("RGB")
                available = set(pytesseract.get_languages(config=""))
                requested = [item for item in language.split("+") if item in available]
                selected = "+".join(requested) or (
                    "eng" if "eng" in available else next(iter(available), "")
                )
                if not selected:
                    raise RuntimeError("Nenhum idioma OCR foi encontrado no Tesseract.")
                text = pytesseract.image_to_string(image, lang=selected, timeout=90)
    except (
        Image.UnidentifiedImageError,
        Image.DecompressionBombError,
        DecompressionBombWarning,
    ) as exc:
        raise ValueError("Imagem inválida para OCR.") from exc
    clean = text.strip()
    if not clean:
        raise ValueError("Nenhum texto legível foi encontrado na imagem.")
    return clean[:40_000]
