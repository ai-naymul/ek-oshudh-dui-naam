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

    def fake_generate(parts, model, schema=None, thinking=None, retries=0, timeout=0, optional=False):
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

    def spy(parts, model, schema=None, thinking=None, retries=3, timeout=120, optional=False):
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


def test_the_lines_of_one_photo_are_matched_at_the_same_time(monkeypatch):
    # 24 Nov: a photo of 8 strips took 122 s when 3 were unsure, because each unsure line asked the AI for a second
    # look one after another. The lines of one photo are now matched together, in their original order.
    import os
    import time
    import pytest
    from app.core import graph as g
    if not os.path.exists(g.DB_PATH):
        pytest.skip("graph not built")
    import app.ai.perceive as perceive
    from app.conversation import Engine
    from tests.test_api import fake_read
    e = Engine()
    monkeypatch.setattr(perceive, "read_image", fake_read([("Aec 50O", "", ""), ("Npaa 5OO", "", ""), ("Secl0 2O", "", ""),
                                                          ("Maxpr0 2O", "", "")], kind="strip"))
    monkeypatch.setattr(e, "_safe_r3", lambda parts, cands: (time.sleep(1), None)[1])
    t0 = time.time()
    out = e.add_image(e.new_case(), b"x")
    took = time.time() - t0
    assert [i["reading"] for i in out["items"]][:1] == ["Aec 50O"]
    assert took < 2.5, f"lines matched one after another ({took:.1f}s)"


def test_a_stalled_main_reader_gives_way_to_the_second_reader(monkeypatch):
    # 24 Nov: on the venue network a photo once waited 96 s (the main reader hung to its time limit, then retried).
    # When the main reader has not answered after MAIN_WAIT seconds and the second reader has, its reading is used.
    import time
    import app.ai.perceive as perceive
    from tests.test_api import png

    def fake_generate(parts, model, schema=None, thinking=None, retries=0, timeout=0, optional=False):
        if model == perceive.READ_MODEL:
            time.sleep(3)
        return {"kind": "strip", "items": [{"brand_text": "Napa", "alternatives": [], "handwritten": False}]}, {"model": model}
    monkeypatch.setattr(perceive, "generate", fake_generate)
    monkeypatch.setattr(perceive, "MAIN_WAIT", 0.5)
    t0 = time.time()
    out = perceive.read_image(png())
    assert time.time() - t0 < 1.5
    assert out["items"][0]["brand_text"] == "Napa" and out["items"][0]["agree"] is None
    assert out["meta"]["model"] == perceive.LITE_MODEL and out["meta"]["fallback"] == "main reader slow"
