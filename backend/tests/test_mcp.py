"""MCP tools: called through the MCP server's own tool dispatch (no network, no key)."""
import asyncio
import json
import os

import pytest

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


def call(name, args):
    from app.mcp_server import server
    res = asyncio.run(server.call_tool(name, args))
    data = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    if data is None:
        data = json.loads(res.content[0].text)
    return data.get("result", data)


def test_tools_are_listed():
    from app.mcp_server import server
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"check_medicines", "find_brand"} <= names


def test_check_medicines_finds_same_medicine_across_rx_and_bag():
    out = call("check_medicines", {"lines": ["Rx: Napa 500 1+0+1", "Ace 500 0+0+1"]})
    red = [f for f in out["findings"] if f["severity"] == "red"]
    assert red and "paracetamol" in red[0]["en"].lower()
    assert any(m["prescribed"] for m in out["medicines"]) and "not medical advice" in out["note"]


def test_find_brand_handles_bangla_and_typos():
    assert call("find_brand", {"name": "নাপা"})["matches"][0]["brand"] == "Napa"
    out = call("find_brand", {"name": "Seclo 20"})
    assert out["matches"][0]["brand"] == "Seclo" and out["path"]["ingredients"][0]["name"].lower().startswith("omeprazole")
