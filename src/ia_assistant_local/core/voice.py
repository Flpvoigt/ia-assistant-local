from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import io
import os
import re
import threading
import urllib.request
import wave
from collections.abc import Iterator
from pathlib import Path

from .config import PROJECT_ROOT

VOICE_NAME = "pm_alex"
VOICE_LANGUAGE = "pt-br"
VOICE_SPEED = 1.0
MODEL_DIRECTORY = PROJECT_ROOT / "data" / "kokoro"
MODEL_PATH = MODEL_DIRECTORY / "kokoro-v1.0.int8.onnx"
FALLBACK_MODEL_PATH = MODEL_DIRECTORY / "kokoro-v1.0.onnx"
VOICES_PATH = MODEL_DIRECTORY / "voices-v1.0.bin"
MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.int8.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"
)
MAX_TEXT_LENGTH = 2_000
STREAM_CHUNK_LENGTH = 80

_engine = None
_engine_lock = threading.Lock()


def _selected_model_path() -> tuple[Path, str]:
    int8_ready = MODEL_PATH.is_file() and MODEL_PATH.stat().st_size >= 50_000_000
    f32_ready = FALLBACK_MODEL_PATH.is_file() and FALLBACK_MODEL_PATH.stat().st_size >= 50_000_000
    preference = os.getenv("ORACULO_VOICE_MODEL", "auto").strip().lower()
    if preference == "int8" and int8_ready:
        return MODEL_PATH, "int8"
    if preference == "f32" and f32_ready:
        return FALLBACK_MODEL_PATH, "f32"
    if f32_ready:
        return FALLBACK_MODEL_PATH, "f32"
    return MODEL_PATH, "int8"


def voice_status() -> dict[str, object]:
    dependency = importlib.util.find_spec("kokoro_onnx") is not None
    int8_model = MODEL_PATH.is_file() and MODEL_PATH.stat().st_size >= 50_000_000
    full_model = FALLBACK_MODEL_PATH.is_file() and FALLBACK_MODEL_PATH.stat().st_size >= 50_000_000
    model = int8_model or full_model
    _, selected_variant = _selected_model_path()
    voices = VOICES_PATH.is_file() and VOICES_PATH.stat().st_size >= 5_000_000
    version = None
    if dependency:
        try:
            version = importlib.metadata.version("kokoro-onnx")
        except importlib.metadata.PackageNotFoundError:
            pass
    ready = dependency and model and voices
    return {
        "engine": "kokoro-onnx",
        "voice": VOICE_NAME,
        "language": VOICE_LANGUAGE,
        "ready": ready,
        "dependency": dependency,
        "dependency_version": version,
        "model": model,
        "model_variant": selected_variant if model else None,
        "int8_available": int8_model,
        "f32_available": full_model,
        "voices": voices,
        "fallback": "browser",
    }


def _load_engine():
    global _engine
    if _engine is not None:
        return _engine
    status = voice_status()
    if not status["dependency"]:
        raise RuntimeError(
            "A voz profissional ainda não foi instalada. Execute install.ps1 ou install.sh."
        )
    if not status["model"] or not status["voices"]:
        raise RuntimeError(
            "Os arquivos da voz pm_alex ainda não foram baixados. "
            "Execute python -m ia_assistant_local.core.voice --install."
        )
    with _engine_lock:
        if _engine is None:
            from kokoro_onnx import Kokoro

            selected_model, _ = _selected_model_path()
            _engine = Kokoro(str(selected_model), str(VOICES_PATH))
    return _engine


def _clean_text(text: str) -> str:
    clean = " ".join(str(text).split())
    if not clean:
        raise ValueError("Informe um texto para gerar a voz.")
    if len(clean) > MAX_TEXT_LENGTH:
        raise ValueError(f"O texto da voz deve ter no máximo {MAX_TEXT_LENGTH} caracteres.")
    return clean


def _wav_for(engine, text: str) -> bytes:
    with _engine_lock:
        samples, sample_rate = engine.create(
            text,
            VOICE_NAME,
            speed=VOICE_SPEED,
            lang=VOICE_LANGUAGE,
        )

    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(int(sample_rate))
        output.writeframes(pcm)
    return buffer.getvalue()


def synthesize_voice(text: str) -> bytes:
    clean = _clean_text(text)
    return _wav_for(_load_engine(), clean)


def _stream_segments(text: str) -> list[str]:
    segments: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?;:])\s+", text):
        words = sentence.split()
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > STREAM_CHUNK_LENGTH:
                segments.append(current)
                current = word
            else:
                current = candidate
    if current:
        segments.append(current)
    return segments


def synthesize_voice_chunks(text: str) -> Iterator[bytes]:
    clean = _clean_text(text)
    engine = _load_engine()

    def generate() -> Iterator[bytes]:
        for segment in _stream_segments(clean):
            yield _wav_for(engine, segment)

    return generate()


def warm_voice() -> bool:
    """Carrega o modelo em segundo plano para reduzir a espera da primeira fala."""
    try:
        _load_engine()
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _download(url: str, destination: Path, minimum_size: int) -> bool:
    if destination.is_file() and destination.stat().st_size >= minimum_size:
        print(f"[voz] {destination.name} já está instalado.")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"[voz] Baixando {destination.name}...")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if temporary.stat().st_size < minimum_size:
            raise RuntimeError(f"Download incompleto de {destination.name}.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(f"[voz] {destination.name} pronto.")
    return True


def install_voice_assets() -> None:
    _download(MODEL_URL, MODEL_PATH, 50_000_000)
    _download(VOICES_URL, VOICES_PATH, 5_000_000)
    print("[voz] Kokoro INT8 com pm_alex está pronto para uso local.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Instala e verifica a voz local do Oráculo.")
    parser.add_argument("--install", action="store_true", help="baixa o modelo e as vozes")
    parser.add_argument("--status", action="store_true", help="mostra o estado da instalação")
    args = parser.parse_args()
    try:
        if args.install:
            install_voice_assets()
        if args.status or not args.install:
            status = voice_status()
            print(
                f"Kokoro={status['dependency']} modelo={status['model']} "
                f"vozes={status['voices']} pm_alex={status['ready']}"
            )
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"[voz] Não foi possível concluir a instalação: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
