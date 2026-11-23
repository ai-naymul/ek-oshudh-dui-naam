from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_live_not_cached():
    a = client.get("/health").json()
    b = client.get("/health").json()
    assert a["status"] == "ok"
    assert a["request_id"] != b["request_id"]


def test_an_optional_ai_call_failing_does_not_say_the_ai_is_down(monkeypatch):
    # The optional second photo reader timed out in the background after the main reader had answered, and the screen
    # then said the reading service was down. Optional calls (second reader, R3 pick, direct voice) fail quietly.
    import urllib.request

    import pytest as _pytest

    from app.ai import gemini

    def boom(*a, **k):
        raise TimeoutError("The read operation timed out")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setitem(gemini.STATUS, "last_error_at", None)
    with _pytest.raises(gemini.GeminiError):
        gemini.generate([{"text": "x"}], gemini.LITE_MODEL, retries=0, timeout=1, optional=True)
    assert gemini.STATUS["last_error_at"] is None
    with _pytest.raises(gemini.GeminiError):
        gemini.generate([{"text": "x"}], gemini.READ_MODEL, retries=0, timeout=1)
    assert gemini.STATUS["last_error_at"] is not None


def test_the_optional_calls_are_marked_optional():
    import inspect

    from app.ai import perceive, speech
    from app.core import rerank
    assert "optional=True" in inspect.getsource(perceive.read_image)
    assert "optional=True" in inspect.getsource(rerank.r3)
    assert "optional=True" in inspect.getsource(speech.hear)
