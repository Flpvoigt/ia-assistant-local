import base64
import io
import zipfile

import pytest
from PIL import Image
from pypdf import PdfReader

from ia_assistant_local.core.attachments import extract_attachment
from ia_assistant_local.core.pdf_export import convert_to_pdf


def encoded(raw):
    return base64.b64encode(raw).decode("ascii")


def test_text_pdf_includes_complete_document_and_accents():
    raw = ("Olá Felipe, ação e programação\n" * 600 + "FIM ORIGINAL").encode()
    result = convert_to_pdf("teste.txt", "text/plain", encoded(raw))
    reader = PdfReader(io.BytesIO(result))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) > 1
    assert "ação" in text
    assert "FIM ORIGINAL" in text


def test_image_pdf_and_existing_pdf():
    raw = io.BytesIO()
    Image.new("RGB", (240, 100), "#6f48ab").save(raw, format="PNG")
    result = convert_to_pdf("imagem.png", "image/png", encoded(raw.getvalue()))
    assert len(PdfReader(io.BytesIO(result)).pages) == 1
    assert convert_to_pdf("ja.pdf", "application/pdf", encoded(result)) == result


def test_docx_local_text_and_pdf():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            "Documento de teste</w:t></w:r></w:p></w:body></w:document>",
        )
    data = encoded(raw.getvalue())
    assert extract_attachment("exemplo.docx", "", data)["content"] == "Documento de teste"
    result = convert_to_pdf("exemplo.docx", "", data)
    assert "Documento de teste" in PdfReader(io.BytesIO(result)).pages[0].extract_text()


@pytest.mark.parametrize(
    "name,raw",
    [
        ("arquivo.exe", b"not executable"),
        ("broken.png", b"broken"),
        ("broken.docx", b"broken"),
        ("broken.pdf", b"broken"),
        ("grande.txt", b"x" * 200_001),
        ("vazio.txt", b" "),
    ],
    ids=["unsupported", "bad-image", "bad-docx", "bad-pdf", "too-large", "empty"],
)
def test_rejects_unsupported_broken_and_oversized_content(name, raw):
    with pytest.raises(ValueError):
        convert_to_pdf(name, "", encoded(raw))
