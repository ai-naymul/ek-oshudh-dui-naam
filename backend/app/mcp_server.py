"""MCP server: the same offline engine as the web app, exposed as tools for any MCP client (e.g. Claude Desktop).

Tools work on medicine names (typed), so they need no API key and no network: catalog matching, the knowledge
graph and the deterministic rules. Each result carries the Bangla and English template text and the source line.

Run:  cd backend && uv run python -m app.mcp_server          (stdio transport)
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="ek-oshudh-dui-naam",
    title="Ek Oshudh, Dui Naam",
    instructions=("Checks a list of Bangladeshi medicines for the same medicine under two brand names, the same drug "
                  "family twice, daily dose over the limit, and listed risky pairs. Answers come from the Bangladesh "
                  "medicine registry and fixed rules, never from the model. Always tell the user to show the result "
                  "to a doctor or pharmacist; never tell them to stop a medicine."),
)
_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from app.conversation import Engine
        _ENGINE = Engine()
    return _ENGINE


@server.tool(description="Check a list of medicines a person takes now. Each line is a brand name, optionally with "
                         "strength and schedule, e.g. 'Napa 500 1+0+1'. Lines marked with a doctor (prefix 'Rx:') "
                         "count as prescribed; others as bought/at home.")
def check_medicines(lines: list[str]) -> dict:
    e = _engine()
    case = e.new_case()
    rx = [l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("rx:")]
    bag = [l for l in lines if not l.lower().startswith("rx:")]
    if bag:
        e.add_text(case, "\n".join(bag))
    for line in rx:
        before = len(case.items)
        e.add_text(case, line)
        for it in case.items[before:]:
            it.source, it.doc_id, it.doctor = "rx", "typed-rx", "typed prescription"
    for it in case.items:   # the caller lists what the person takes now
        it.taking = "current"
    unsure = [{"line": i.reading, "best_guess": e.options_brand(i), "options": [o["brand"] for o in i.options]}
              for i in case.items if i.needs_confirm]
    result = e.check(case)
    return {"findings": [{k: f[k] for k in ("severity", "title_en", "en", "bn", "source")} for f in result["findings"]],
            "medicines": [{"brand": m["brand"], "strength": m["strength"], "form": m["form"],
                           "ingredients": [x["name"] for x in m["path"]["ingredients"]], "prescribed": m["from_rx"]}
                          for m in result["medicines"]],
            "needs_confirmation": unsure,
            "note": "Show this to a doctor or pharmacist. This is not medical advice."}


@server.tool(description="Look up a Bangladeshi medicine brand (any spelling, Bangla or English, typos allowed). "
                         "Returns the closest registry products and the ingredient path of the best match.")
def find_brand(name: str) -> dict:
    e = _engine()
    cands = e.index.search(name, 20)
    opts = e._options(cands, 5)
    return {"query": name, "matches": opts, "path": e.graph.path(opts[0]["product_id"]) if opts else None}


if __name__ == "__main__":
    server.run("stdio")
