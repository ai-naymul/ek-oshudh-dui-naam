"""Spoken medicine names. The voice note goes straight to the reader model (it hears the sound, not a transcript),
and our own code double-checks the English spelling it returns: a model once wrote 'Esomep' for a spoken
'এক্সিয়াম' (Exium) and 'Deslor' for 'ডেস' (Des), other brands of the same medicine, the very thing this app tells
apart. Every spoken item still waits for the family's tap."""
import os

import pytest

from app.core import graph as g
from app.core.candidates import parse_hints, transliterate

needs_graph = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


def test_bangla_ya_and_nukta_letters_transliterate_cleanly():
    # য় is stored as য + a dot below; the dot used to stay in the text and split the word in two ('eksij am')
    assert parse_hints("এক্সিয়াম")[0] == "exiam"
    # brand names are English words in Bangla letters: ক্স is x, িয়া is ia, অ্যা is a
    assert transliterate("এক্সিয়াম") == "exiam"
    assert transliterate("ম্যাক্সপ্রো") == "maxpro"
    assert transliterate("অ্যালাট্রল") == "alatrl"


def test_spoken_bangla_units_are_units_not_letters_of_the_name():
    assert parse_hints("Tess 5 এমজি") == ("tess", "5", None)
    assert parse_hints("এক্সিয়াম ২০ মিলিগ্রাম") == ("exiam", "20", None)


def test_sound_alikes_swap_the_first_voiced_or_voiceless_letter():
    from app.conversation import sound_alikes
    assert "des" in sound_alikes("tes")
    assert "gabapentin" in sound_alikes("kabapentin")
    assert sound_alikes("ace") == []


@needs_graph
def test_a_misheard_first_letter_still_offers_the_right_brand_first():
    from app.conversation import Engine
    chosen, conf, method, confirm, cands = Engine().match_voice("টেস", "Tess", "5 এমজি")
    assert chosen.brand == "Des" and confirm is True
    assert [c.brand for c in cands[:3]].count("Des") == 1


@needs_graph
def test_a_brand_the_model_swapped_in_does_not_hide_what_was_said():
    from app.conversation import Engine
    chosen, conf, method, confirm, cands = Engine().match_voice("এক্সিয়াম", "Esomep", "20 এমজি")
    top3 = [c.brand for c in cands[:3]]
    assert "Exium" in top3 and "Esomep" in top3 and confirm is True


@needs_graph
def test_a_correctly_heard_name_is_still_first():
    from app.conversation import Engine
    for said, latin, strength, brand in [("এক্সিয়াম", "Exium", "20 mg", "Exium"), ("নাপা", "Napa", "500", "Napa"),
                                         ("সেকলো", "Seclo", "20", "Seclo")]:
        chosen, *_ = Engine().match_voice(said, latin, strength)
        assert chosen.brand == brand, (said, chosen.brand)


def test_voice_note_goes_to_the_reader_as_audio(monkeypatch):
    import app.ai.speech as speech
    seen = {}

    def fake_generate(parts, model, schema, *a, **k):
        seen["parts"], seen["model"] = parts, model
        return {"transcript": "আমি ডেস খাই", "items": [{"name_as_said": "ডেস", "name_english_letters": "Des"}]}, {"model": model}
    monkeypatch.setattr(speech, "generate", fake_generate)
    transcript, items, meta = speech.hear(b"RIFF....WAVE", "audio/wav")
    assert transcript == "আমি ডেস খাই" and items[0]["name_english_letters"] == "Des"
    assert seen["model"] == speech.HEAR_MODEL and any("inline_data" in p for p in seen["parts"])
    assert "never replace" in speech.HEAR_PROMPT.lower()


def test_the_transcript_is_written_before_the_medicine_list():
    # Gemini fills JSON fields alphabetically unless told: 'items' came before 'transcript' and medicines were dropped
    # (v2 test note: 1 of 3 names in 3 of 8 runs; with the transcript first, 3 of 3 in 12 of 12)
    import app.ai.speech as speech
    assert speech.HEAR_SCHEMA["propertyOrdering"] == ["transcript", "items"]
    assert speech.HEAR_SCHEMA["properties"]["items"]["items"]["propertyOrdering"][0] == "name_as_said"


def test_a_runaway_strength_or_schedule_is_cut_to_what_was_said(monkeypatch):
    import app.ai.speech as speech
    junk = "২০ এমজি, 20 mg, 20mg, ২০mg, " * 80
    monkeypatch.setattr(speech, "generate", lambda *a, **k: ({"transcript": "এক্সিয়াম ২০ এমজি", "items": [
        {"name_as_said": "এক্সিয়াম", "name_english_letters": "Exium", "strength_text": junk, "schedule_text": "রাতে " * 200}]},
        {"model": "m"}))
    _, items, _ = speech.hear(b"RIFF....WAVE", "audio/wav")
    assert items[0]["strength_text"] == "২০ এমজি"
    assert len(items[0]["schedule_text"]) <= 60


def test_voice_falls_back_to_transcribe_then_extract_when_the_reader_refuses(monkeypatch):
    import app.ai.speech as speech
    from app.ai.gemini import GeminiError

    def refuse(*a, **k):
        raise GeminiError("blocked: OTHER")
    monkeypatch.setattr(speech, "generate", refuse)
    monkeypatch.setattr(speech, "audio_to_text", lambda data, mime: ("আমি নাপা খাই", {"model": "t"}))
    monkeypatch.setattr(speech, "mentions", lambda text: ([{"name_as_said": "নাপা", "name_english_letters": "Napa"}], {"model": "x"}))
    transcript, items, meta = speech.hear(b"RIFF....WAVE", "audio/wav")
    assert transcript == "আমি নাপা খাই" and items[0]["name_english_letters"] == "Napa" and meta["fallback"] is True


def test_extract_prompt_forbids_swapping_in_another_brand():
    import app.ai.speech as speech
    assert "never replace" in speech.EXTRACT_PROMPT.lower()
