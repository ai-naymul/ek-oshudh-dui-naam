"""A brand that is not in the registry snapshot: look it up on MedEx (medex.com.bd, the listing the registry was built
from), through MedEx's own search, with DuckDuckGo as a fallback. Only the medicine name is sent, never anything about
the patient. A brand page is read into brand, form, ingredients, strength and maker; it is used only after the family
taps it, and the server fetches the page itself (only medex.com.bd brand pages are accepted)."""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from rapidfuzz import fuzz

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
BRAND_URL = re.compile(r"https://medex\.com\.bd/brands/\d+/[a-z0-9-]+")
TIMEOUT = 8


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_brand_page(page: str, url: str) -> dict | None:
    h1 = re.search(r'<h1[^>]*class="[^"]*\bbrand\b[^"]*"[^>]*>(.*?)</h1>', page, re.S)
    gen = re.search(r'title="Generic Name">\s*<a[^>]*>(.*?)</a>', page, re.S)
    if not h1 or not gen:
        return None
    form = re.search(r'title="Dosage Form">([^<]+)<', h1.group(1))
    strength = re.search(r'title="Strength">(.*?)</div>', page, re.S)
    maker = re.search(r'title="Manufactured by">\s*<a[^>]*>(.*?)</a>', page, re.S)
    brand = _clean(re.sub(r"<small.*", "", h1.group(1), flags=re.S))
    return {"brand": brand, "form": _clean(form.group(1)) if form else "", "generic": _clean(gen.group(1)),
            "strength": _clean(strength.group(1)) if strength else "", "maker": _clean(maker.group(1)) if maker else "",
            "url": url} if brand else None


def fetch_brand(url: str) -> dict | None:
    return parse_brand_page(_get(url), url) if BRAND_URL.fullmatch(url) else None


def search_urls(name: str) -> tuple[list[str], str]:
    """Brand page links for a name: MedEx search first, DuckDuckGo (site:medex.com.bd) if MedEx gives nothing."""
    tries = [("medex", f"https://medex.com.bd/search?search={urllib.parse.quote(name)}"),
             ("duckduckgo", "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(f"site:medex.com.bd/brands {name}"))]
    for via, url in tries:
        try:
            urls = list(dict.fromkeys(BRAND_URL.findall(urllib.parse.unquote(_get(url)))))
        except Exception:   # network down, blocked, slow: try the next source
            urls = []
        if urls:
            return urls, via
    return [], ""


def lookup(name: str, k: int = 3) -> dict:
    """-> {'results': [brand dicts, closest name first], 'via': 'medex' | 'duckduckgo' | ''}."""
    urls, via = search_urls(name)
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    urls = sorted(urls, key=lambda u: -fuzz.partial_ratio(key, re.sub(r"[^a-z0-9]", "", u.rsplit("/", 1)[1])))[:k]

    def one(u):
        try:
            return fetch_brand(u)
        except Exception:
            return None
    with ThreadPoolExecutor(max(1, len(urls))) as ex:
        results = [r for r in ex.map(one, urls) if r]
    return {"results": results, "via": via}
