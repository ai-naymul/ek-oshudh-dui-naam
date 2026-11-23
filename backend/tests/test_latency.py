"""A judge must never wait minutes for a photo (23 Nov: three strip photos took over 4 minutes because each AI call could
wait 120 s and retry 3 times, and the photo reader waited for its optional second reader)."""
import io
import time

from PIL import Image


def _jpg():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, "JPEG")
    return buf.getvalue()


def test_a_slow_second_reader_does_not_hold_up_the_photo(monkeypatch):
    import app.ai.perceive as perceive
    answer = {"kind": "strip", "items": [{"brand_text": "Napa", "box": [0, 0, 1000, 1000]}]}

    def fake_generate(parts, model, schema=None, thinking=None, retries=0, timeout=0):
        if model == perceive.LITE_MODEL:
            time.sleep(3)
        return answer, {"model": model}
    monkeypatch.setattr(perceive, "generate", fake_generate)
    monkeypatch.setattr(perceive, "SECOND_READER_WAIT", 0.3)
    t0 = time.time()
    out = perceive.read_image(_jpg())
    assert time.time() - t0 < 2
    assert out["items"][0]["agree"] is None          # agreement unknown: an exact name will be asked, not accepted


def test_the_photo_reader_and_the_second_opinion_have_short_time_limits(monkeypatch):
    import app.ai.perceive as perceive
    import app.core.rerank as rerank
    seen = []

    def spy(parts, model, schema=None, thinking=None, retries=3, timeout=120):
        seen.append((model, retries, timeout))
        return {"kind": "strip", "items": [], "choice": 0}, {}
    monkeypatch.setattr(perceive, "generate", spy)
    perceive.read_image(_jpg())
    assert all(r <= 1 and t <= 45 for _, r, t in seen) and len(seen) == 2
    import app.ai.gemini as gemini
    from app.core.candidates import Candidate
    monkeypatch.setattr(gemini, "generate", spy)            # r3 imports the client inside the function
    seen.clear()
    cand = Candidate(1, "Napa", "500 mg", "Tablet", "Beximco", "Paracetamol", 1.0, True, True, True)
    rerank.r3([{"text": "x"}], [cand], k=5)
    assert len(seen) == 1 and all(r == 0 and t <= 20 for _, r, t in seen)
