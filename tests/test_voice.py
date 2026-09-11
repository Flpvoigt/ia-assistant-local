import pytest

from ia_assistant_local.core import voice


def test_voice_status_describes_local_engine():
    status = voice.voice_status()
    assert status["engine"] == "kokoro-onnx"
    assert status["voice"] == "pm_alex"
    assert status["language"] == "pt-br"
    assert status["fallback"] == "browser"
    assert status["ready"] == (status["dependency"] and status["model"] and status["voices"])


def test_voice_rejects_empty_and_oversized_text_before_loading_model():
    with pytest.raises(ValueError, match="Informe um texto"):
        voice.synthesize_voice("   ")
    with pytest.raises(ValueError, match="no máximo"):
        voice.synthesize_voice("x" * (voice.MAX_TEXT_LENGTH + 1))


def test_stream_segments_keep_text_in_small_ordered_chunks():
    text = "Primeira frase curta. " + "palavra " * 60 + "Fim."
    segments = voice._stream_segments(text)
    assert " ".join(segments) == " ".join(text.split())
    assert all(len(segment) <= voice.STREAM_CHUNK_LENGTH for segment in segments)
