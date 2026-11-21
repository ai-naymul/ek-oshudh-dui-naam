"""config/settings.json: the switches a judge can ask us to change on-site, without touching code."""
import json
import os

import pytest

from app.core import graph as g
from app.core.settings import load_settings

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


def test_settings_file_overrides_only_what_it_names(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"rules": {"dose_limits": True}}))
    s = load_settings(str(path))
    assert s["rules"]["dose_limits"] is True
    assert s["rules"]["not_on_rx_finding"] is False      # default kept
    assert s["matching"]["always_confirm"] is False      # default kept


def test_shipped_settings_keep_unreviewed_rules_off():
    s = load_settings()
    assert s["rules"]["dose_limits"] is False and s["matching"]["always_confirm"] is False


def test_always_confirm_makes_even_an_exact_typed_name_ask():
    from app.conversation import Engine
    e = Engine(settings={"matching": {"always_confirm": True}})
    case = e.new_case()
    item = e.add_text(case, "Napa 500")["items"][0]
    assert item["chosen"]["brand"] == "Napa" and item["needs_confirm"] is True


def test_threshold_and_rule_switches_reach_the_engine():
    from app.conversation import Engine
    e = Engine(settings={"matching": {"auto_accept_threshold": 0.5}, "rules": {"dose_limits": True}})
    assert e.policy["r2_accept"] == 0.5
    assert e.rules.settings["dose_limits"] is True
