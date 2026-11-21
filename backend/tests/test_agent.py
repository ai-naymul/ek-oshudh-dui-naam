"""Agent guardrails with the model's tool calls scripted (no network): grounding, banned phrases, step budget."""
import os

import pytest

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def engine():
    from app.conversation import Engine
    return Engine()


def scripted(monkeypatch, turns):
    """Each turn is a list of (tool name, args) the 'model' calls; records what the agent sends back."""
    import app.agent.resolver as r
    sent = []

    def fake_chat(contents, tools, model):
        sent.append(contents[-1])
        calls = turns.pop(0)
        return {"role": "model", "parts": [{"functionCall": {"name": n, "args": a}} for n, a in calls]}, {"model": "fake"}
    monkeypatch.setattr(r, "chat", fake_chat)
    return sent


def case_with_strip_and_unclear_line(engine):
    case = engine.new_case()
    engine.add_text(case, "Napa 500")                 # stands in for a clear strip photo
    engine.add_text(case, "Nap")                      # the unclear line
    unclear = case.items[-1]
    unclear.needs_confirm = True
    napa = case.items[0].product_id
    return case, unclear, napa


def test_suggestion_backed_by_the_bag_is_kept_but_not_confirmed(engine, monkeypatch):
    case, item, napa = case_with_strip_and_unclear_line(engine)
    scripted(monkeypatch, [[("check_bag", {})], [("answer", {"product_id": napa, "reason_bn": "ব্যাগে Napa 500 এর স্ট্রিপ আছে।"})]])
    view = engine.resolve(case, item.item_id)
    assert view["agent"]["product_id"] == napa and view["options"][0]["product_id"] == napa
    assert view["needs_confirm"] is True                          # still the user's decision
    assert case.trace[-1]["step"] == "agent" and case.trace[-1]["tools"] == ["check_bag"]


def test_ungrounded_answer_is_dropped(engine, monkeypatch):
    case, item, _ = case_with_strip_and_unclear_line(engine)
    scripted(monkeypatch, [[("answer", {"product_id": 999999, "reason_bn": "এটা অন্য ওষুধ।"})]])
    view = engine.resolve(case, item.item_id)
    assert view["agent"]["product_id"] is None


def test_banned_phrase_is_dropped(engine, monkeypatch):
    case, item, napa = case_with_strip_and_unclear_line(engine)
    scripted(monkeypatch, [[("check_bag", {})], [("answer", {"product_id": napa, "reason_bn": "এটা নিরাপদ, খেতে পারেন।"})]])
    assert engine.resolve(case, item.item_id)["agent"]["product_id"] is None


def test_step_budget_stops_the_loop(engine, monkeypatch):
    from app.agent.resolver import MAX_STEPS
    case, item, _ = case_with_strip_and_unclear_line(engine)
    scripted(monkeypatch, [[("find_brand", {"name": "Nap"})] for _ in range(MAX_STEPS + 3)])
    view = engine.resolve(case, item.item_id)
    assert view["agent"]["product_id"] is None and len(view["agent"]["tools"]) == MAX_STEPS


def test_tool_results_go_back_to_the_model(engine, monkeypatch):
    case, item, napa = case_with_strip_and_unclear_line(engine)
    sent = scripted(monkeypatch, [[("check_bag", {})], [("answer", {"product_id": 0, "reason_bn": ""})]])
    engine.resolve(case, item.item_id)
    reply = sent[1]["parts"][0]["functionResponse"]
    assert reply["name"] == "check_bag" and any(m["brand"] == "Napa" for m in reply["response"]["medicines"])
