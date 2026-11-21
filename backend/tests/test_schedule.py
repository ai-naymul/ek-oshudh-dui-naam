import pytest

from app.core.schedule import parse


@pytest.mark.parametrize("text,morning,noon,night,per_day", [
    ("1+0+1", 1, 0, 1, 2),
    ("1-0-1", 1, 0, 1, 2),
    ("১+০+১", 1, 0, 1, 2),
    ("1+1+1", 1, 1, 1, 3),
    ("½+0+½", 0.5, 0, 0.5, 1),
    ("0 + 0 + 1", 0, 0, 1, 1),
])
def test_plus_patterns(text, morning, noon, night, per_day):
    s = parse(text)
    assert (s.morning, s.noon, s.night, s.per_day) == (morning, noon, night, per_day)


@pytest.mark.parametrize("text,per_day", [("দিনে ২ বার", 2), ("দিনে ৩ বার", 3), ("BD", 2), ("TDS", 3), ("OD", 1), ("2 times a day", 2)])
def test_times_per_day(text, per_day):
    assert parse(text).per_day == per_day


def test_slots_in_bangla():
    s = parse("সকালে ১টা রাতে ১টা")
    assert (s.morning, s.night, s.per_day) == (1, 1, 2)


def test_meal_duration_and_flags():
    s = parse("১+০+১ খাবারের পরে ৭ দিন")
    assert s.meal == "after" and s.days == 7
    assert parse("1+0+0 before meal x 14 days").meal == "before"
    assert parse("0+0+1 ১ মাস চলবে").days == 30
    assert parse("0+0+1 চলবে").continuing
    assert parse("SOS").as_needed


def test_empty_is_unknown_not_zero():
    s = parse("")
    assert s.per_day is None and s.meal is None
