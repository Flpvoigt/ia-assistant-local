import base64

import pytest

from ia_assistant_local.core.attachments import extract_attachment, validate_image
from ia_assistant_local.integrations.extensions import extension_catalog


def encoded(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def test_text_attachment_is_extracted_locally():
    result = extract_attachment("notes.md", "text/markdown", encoded(b"private preview"))
    assert result["kind"] == "text"
    assert result["content"] == "private preview"


def test_image_validation_only_accepts_safe_data_urls():
    image = "data:image/png;base64," + encoded(b"\x89PNG\r\n\x1a\nsmall-image")
    assert validate_image(image) == image
    with pytest.raises(ValueError):
        validate_image("data:image/svg+xml;base64," + encoded(b"<svg/>"))


def test_extension_catalog_reports_configuration_state():
    disabled = extension_catalog(False)
    enabled = extension_catalog(True)
    assert (
        next(item for item in disabled if item["id"] == "home_assistant")["status"]
        == "setup_required"
    )
    assert next(item for item in enabled if item["id"] == "home_assistant")["status"] == "active"
