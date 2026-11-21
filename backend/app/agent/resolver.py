"""Agent that helps with ONE unclear item, using the rest of the case as evidence.

Why an agent here: a handwritten line like 'Nap? 500' is unclear on its own, but the same case may hold a strip
photo of Napa 500, another doctor's prescription, or a typed name. Looking that up is open-ended (which tool,
in what order), so a small tool-using loop fits; everything that decides safety stays in the fixed rules.

Guardrails (all enforced in code, not by the prompt):
- step budget: at most MAX_STEPS tool calls, then it must answer
- tools are read-only lookups on our own registry and this case; there is no tool that changes anything
- grounding: the suggested product must be one that a tool returned during this run; otherwise it is dropped
- banned phrases: the Bangla reason may not tell anyone to stop/start a medicine or call anything safe
- it only SUGGESTS: the item still needs the user's confirmation, and every step goes into the case trace
"""
from __future__ import annotations

import time

from app.ai.gemini import LITE_MODEL, GeminiError, chat

MAX_STEPS = 4
BANNED = ("বন্ধ করুন", "খাবেন না", "নিরাপদ", "খেতে পারেন", "stop taking", "safe to")

TOOLS = [
    {"name": "find_brand", "description": "Search the Bangladesh medicine registry for a brand name (any spelling). "
     "Returns up to 5 products with product_id, brand, strength, form, maker.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "get_ingredients", "description": "Ingredients and drug class of a registry product.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}}, "required": ["product_id"]}},
    {"name": "check_bag", "description": "Other medicines already in this case (from strips, other prescriptions, "
     "typed or spoken), with how sure each one is.", "parameters": {"type": "object", "properties": {}}},
    {"name": "compare_prices", "description": "Unit price of a registry product and its maker.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}}, "required": ["product_id"]}},
    {"name": "answer", "description": "Finish. Give the product_id you think the unclear line is (0 if unsure) and "
     "a one-sentence reason in simple Bangla for the family, based only on tool results.",
     "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}, "reason_bn": {"type": "string"}},
                    "required": ["product_id", "reason_bn"]}},
]

PROMPT = ("You help a Bangladeshi family check their medicines. One line could not be read with confidence.\n"
          "Unclear line as read: {reading!r} (other possible readings: {alts}).\n"
          "Registry candidates so far: {options}.\n"
          "Use the tools to look for evidence, especially other medicines in the same case (check_bag): a clear strip "
          "photo of a candidate is strong evidence. Never guess beyond the evidence; if unsure answer product_id 0. "
          "You may call at most {max_steps} tools, then call answer.")


class Resolver:
    def __init__(self, engine, model: str = LITE_MODEL):
        self.e, self.model = engine, model

    # ---------- tools: read-only lookups ----------
    def _find_brand(self, name: str) -> dict:
        return {"products": self.e._options(self.e.index.search(name, 20), 5)}

    def _get_ingredients(self, product_id: int) -> dict:
        return self.e.graph.path(int(product_id)) or {"error": "unknown product"}

    def _check_bag(self, case, item) -> dict:
        return {"medicines": [{"brand": self.e.options_brand(i), "source": i.source, "confirmed": not i.needs_confirm,
                               "product_id": i.product_id}
                              for i in case.items if i is not item and i.product_id]}

    def _compare_prices(self, product_id: int) -> dict:
        p = self.e.graph.product(int(product_id))
        return {"brand": p.brand, "strength": p.strength, "maker": p.manufacturer, "unit_price": p.unit_price} if p else {"error": "unknown"}

    def resolve(self, case, item) -> dict:
        """-> {"product_id": int|None, "reason_bn": str, "steps": [...], "grounded": bool}"""
        seen_ids = {o["product_id"] for o in item.options}
        contents = [{"role": "user", "parts": [{"text": PROMPT.format(
            reading=item.reading, alts=item.alternatives[:3], max_steps=MAX_STEPS,
            options=[f"{o['product_id']}: {o['brand']} {o['strength']} {o['form']}" for o in item.options])}]}]
        steps: list[dict] = []
        for _ in range(MAX_STEPS + 1):
            t0 = time.time()
            content, meta = chat(contents, TOOLS, self.model)
            contents.append(content)
            calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
            if not calls:
                break
            responses = []
            for call in calls:
                name, args = call["name"], call.get("args", {}) or {}
                if name == "answer" or len(steps) >= MAX_STEPS:
                    return self._finish(args if name == "answer" else {"product_id": 0, "reason_bn": ""}, seen_ids, steps)
                if name == "find_brand":
                    out = self._find_brand(str(args.get("name", "")))
                    seen_ids |= {p["product_id"] for p in out["products"]}
                elif name == "get_ingredients":
                    out = self._get_ingredients(args.get("product_id", 0))
                elif name == "check_bag":
                    out = self._check_bag(case, item)
                    seen_ids |= {m["product_id"] for m in out["medicines"]}
                elif name == "compare_prices":
                    out = self._compare_prices(args.get("product_id", 0))
                else:
                    out = {"error": f"unknown tool {name}"}
                steps.append({"tool": name, "args": args, "ms": round((time.time() - t0) * 1000, 1)})
                responses.append({"functionResponse": {"name": name, "response": out}})
            contents.append({"role": "user", "parts": responses})
        return self._finish({"product_id": 0, "reason_bn": ""}, seen_ids, steps)

    @staticmethod
    def _finish(args: dict, seen_ids: set, steps: list) -> dict:
        pid = int(args.get("product_id") or 0)
        reason = str(args.get("reason_bn") or "").strip()
        grounded = pid in seen_ids
        if not grounded or any(b in reason.lower() for b in BANNED):
            return {"product_id": None, "reason_bn": "", "steps": steps, "grounded": False, "dropped": pid != 0}
        return {"product_id": pid, "reason_bn": reason, "steps": steps, "grounded": True}


def safe_resolve(engine, case, item) -> dict:
    try:
        return Resolver(engine).resolve(case, item)
    except GeminiError as e:
        return {"product_id": None, "reason_bn": "", "steps": [], "grounded": False, "error": str(e)[:120]}
