import hashlib
from pathlib import Path

import pytest

from ia_assistant_local import updater_app
from ia_assistant_local.updater_app import installer_matches, validate_manifest, version_key


def test_version_key_orders_desktop_versions():
    assert version_key("v0.2.0") > version_key("0.1.9")
    assert version_key("1.0.0") == (1, 0, 0)
    with pytest.raises(ValueError):
        version_key("release-next")


def test_manifest_requires_https_and_sha256():
    valid = {
        "version": "0.2.0",
        "url": "https://oraculo-desktop.vercel.app/downloads/Oraculo-Setup.exe",
        "sha256": "a" * 64,
        "size": 7,
        "notes": ["Atualização automática"],
    }
    assert validate_manifest(valid)["version"] == "0.2.0"
    with pytest.raises(ValueError, match="HTTPS"):
        validate_manifest({**valid, "url": "http://example.test/setup.exe"})
    with pytest.raises(ValueError, match="SHA-256"):
        validate_manifest({**valid, "sha256": "invalido"})


def test_installer_hash_and_size_are_verified(tmp_path: Path):
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"oraculo")
    digest = hashlib.sha256(b"oraculo").hexdigest()
    assert installer_matches(installer, digest, 7)
    assert not installer_matches(installer, "0" * 64, 7)
    assert not installer_matches(installer, digest, 8)


def test_current_version_does_not_download(monkeypatch):
    manifest = {
        "version": "0.2.0",
        "url": "https://example.test/setup.exe",
        "sha256": "a" * 64,
        "size": 10,
        "notes": [],
    }
    monkeypatch.setattr(updater_app, "fetch_manifest", lambda: manifest)
    monkeypatch.setattr(
        updater_app,
        "download_installer",
        lambda _manifest: pytest.fail("não deveria baixar"),
    )
    assert updater_app.check_for_update() == "up-to-date"


def test_future_version_is_left_pending_while_app_is_open(monkeypatch, tmp_path):
    manifest = {
        "version": "0.3.0",
        "url": "https://example.test/setup.exe",
        "sha256": "a" * 64,
        "size": 10,
        "notes": [],
    }
    installer = tmp_path / "setup.exe"
    monkeypatch.setattr(updater_app, "fetch_manifest", lambda: manifest)
    monkeypatch.setattr(updater_app, "download_installer", lambda _manifest: installer)
    monkeypatch.setattr(updater_app, "_save_pending", lambda *_args: None)
    monkeypatch.setattr(updater_app, "app_is_running", lambda: True)
    monkeypatch.setattr(updater_app, "_log", lambda _message: None)
    assert updater_app.check_for_update() == "pending"
