"""Bangladesh medicine knowledge graph, stored in SQLite.

Nodes: product (a brand at a strength and form), ingredient, drug class.
Edges: product -contains-> ingredient (with per-ingredient strength), ingredient -in_class-> class.
Also kept: unit price per product, and the monograph text (dosage, interactions, ...) per generic.

Build once from the registry CSVs (scripts/get_data.sh), then query read-only.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RAW = os.path.join(ROOT, "data", "raw")
# Brands missing from the registry snapshot, each row with its source (a pharmacy listing): data/curated/products_local.csv
LOCAL_PRODUCTS = os.path.join(ROOT, "data", "curated", "products_local.csv")
DB_PATH = os.path.join(ROOT, "data", "build", "graph.sqlite")

SCHEMA = """
CREATE TABLE product (
  id INTEGER PRIMARY KEY, brand TEXT NOT NULL, brand_key TEXT NOT NULL, generic TEXT NOT NULL,
  strength TEXT, form TEXT, manufacturer TEXT, unit_price REAL, package TEXT,
  source TEXT NOT NULL DEFAULT 'registry');
CREATE TABLE ingredient (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE product_ingredient (
  product_id INTEGER NOT NULL, ingredient_id INTEGER NOT NULL, strength TEXT, mg REAL,
  PRIMARY KEY (product_id, ingredient_id));
CREATE TABLE generic_info (
  generic TEXT PRIMARY KEY, drug_class TEXT, indication TEXT, dosage TEXT, interaction TEXT,
  contraindications TEXT, precautions TEXT, overdose TEXT);
CREATE INDEX idx_product_brand_key ON product(brand_key);
CREATE INDEX idx_pi_ingredient ON product_ingredient(ingredient_id);
"""

_TAG = re.compile(r"<[^>]+>")
_PRICE = re.compile(r"Unit Price:\s*৳\s*([\d.]+)")
_MG = re.compile(r"([\d.]+)\s*(mg|gm|g|mcg|µg)\b", re.I)


def brand_key(text: str) -> str:
    """Normalise a brand name for exact lookup: NFC, lower case, letters and digits only."""
    t = unicodedata.normalize("NFC", text or "").lower()
    return re.sub(r"[^0-9a-zঀ-৿]+", "", t)


def clean_html(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", text or "")).strip()


def split_combination(generic: str, strength: str) -> list[tuple[str, str]]:
    """'Paracetamol + Caffeine', '500 mg+65 mg' -> [('Paracetamol','500 mg'), ('Caffeine','65 mg')]."""
    names = [g.strip() for g in generic.split("+") if g.strip()]
    s = (strength or "").strip().strip("()")
    parts = [p.strip() for p in re.split(r"\+", s.split(")")[0]) if p.strip()] if len(names) > 1 else [s]
    if len(parts) != len(names):
        parts = [s] + [""] * (len(names) - 1) if len(names) > 1 else [s]
    return list(zip(names, parts))


def to_mg(strength: str) -> float | None:
    """'500 mg' -> 500.0, '1 gm' -> 1000.0, '250 mcg' -> 0.25. Per-volume strengths ('120 mg/5 ml') are not per unit -> None."""
    if not strength or "/" in strength:
        return None
    m = _MG.search(strength)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return value * {"mg": 1, "gm": 1000, "g": 1000, "mcg": 0.001, "µg": 0.001}[unit]


def build(raw_dir: str = RAW, db_path: str = DB_PATH) -> dict:
    """Build into a temporary file, then swap it in atomically: a running server or eval that has the old file
    open keeps reading it safely, and never sees a half-built database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    final, db_path = db_path, db_path + f".building-{os.getpid()}"
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    ing_ids: dict[str, int] = {}
    with open(os.path.join(raw_dir, "medicine.csv"), encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            if r["type"].strip() != "allopathic":
                continue
            m = _PRICE.search(r.get("package container", "") or "")
            cur = con.execute(
                "INSERT INTO product (brand, brand_key, generic, strength, form, manufacturer, unit_price, package) VALUES (?,?,?,?,?,?,?,?)",
                (r["brand name"].strip(), brand_key(r["brand name"]), r["generic"].strip(), r["strength"].strip(),
                 r["dosage form"].strip(), r["manufacturer"].strip(), float(m.group(1)) if m else None,
                 (r.get("package container") or "").strip()))
            pid = cur.lastrowid
            for name, strength in split_combination(r["generic"], r["strength"]):
                if name not in ing_ids:
                    ing_ids[name] = con.execute("INSERT INTO ingredient (name) VALUES (?)", (name,)).lastrowid
                con.execute("INSERT OR IGNORE INTO product_ingredient VALUES (?,?,?,?)",
                            (pid, ing_ids[name], strength, to_mg(strength)))
    if os.path.exists(LOCAL_PRODUCTS):
        with open(LOCAL_PRODUCTS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cur = con.execute(
                    "INSERT INTO product (brand, brand_key, generic, strength, form, manufacturer, unit_price, package, source) "
                    "VALUES (?,?,?,?,?,?,NULL,'',?)",
                    (r["brand name"].strip(), brand_key(r["brand name"]), r["generic"].strip(), r["strength"].strip(),
                     r["dosage form"].strip(), r["manufacturer"].strip(), "local"))
                for name, strength in split_combination(r["generic"], r["strength"]):
                    if name not in ing_ids:
                        ing_ids[name] = con.execute("INSERT INTO ingredient (name) VALUES (?)", (name,)).lastrowid
                    con.execute("INSERT OR IGNORE INTO product_ingredient VALUES (?,?,?,?)",
                                (cur.lastrowid, ing_ids[name], strength, to_mg(strength)))
    with open(os.path.join(raw_dir, "generic.csv"), encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            con.execute("INSERT OR REPLACE INTO generic_info VALUES (?,?,?,?,?,?,?,?)",
                        (r["generic name"].strip(), r["drug class"].strip(), clean_html(r["indication description"]),
                         clean_html(r["dosage description"]), clean_html(r["interaction description"]),
                         clean_html(r["contraindications description"]), clean_html(r["precautions description"]),
                         clean_html(r["overdose effects description"])))
    con.commit()
    stats = dict(
        products=con.execute("SELECT COUNT(*) FROM product WHERE source = 'registry'").fetchone()[0],
        brand_names=con.execute("SELECT COUNT(DISTINCT brand) FROM product WHERE source = 'registry'").fetchone()[0],
        generics=con.execute("SELECT COUNT(DISTINCT generic) FROM product WHERE source = 'registry'").fetchone()[0],
        local_products=con.execute("SELECT COUNT(*) FROM product WHERE source = 'local'").fetchone()[0],
        ingredients=con.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0],
        priced=con.execute("SELECT COUNT(*) FROM product WHERE unit_price IS NOT NULL").fetchone()[0],
    )
    con.close()
    os.replace(db_path, final)
    return stats


@dataclass
class Product:
    id: int
    brand: str
    generic: str
    strength: str
    form: str
    manufacturer: str
    unit_price: float | None


class Graph:
    """Read-only queries over the built graph."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self._lock = threading.RLock()  # one connection shared by web/eval threads: serialise access

    def _q(self, sql: str, params: tuple = ()) -> list:
        with self._lock:
            return self.con.execute(sql, params).fetchall()

    def add_product(self, brand: str, generic: str, strength: str, form: str, maker: str, source: str) -> int:
        """A brand found outside the registry snapshot (a MedEx page) and tapped by the family. source = the page URL.
        Written through its own connection; the shared read-only one sees it at once. Same brand+strength+form: reused."""
        with self._lock:
            con = sqlite3.connect(self.db_path)
            try:
                row = con.execute("SELECT id FROM product WHERE brand_key = ? AND strength = ? AND form = ?",
                                  (brand_key(brand), strength, form)).fetchone()
                if row:
                    return row[0]
                pid = con.execute(
                    "INSERT INTO product (brand, brand_key, generic, strength, form, manufacturer, unit_price, package, source) "
                    "VALUES (?,?,?,?,?,?,NULL,'',?)", (brand, brand_key(brand), generic, strength, form, maker, source)).lastrowid
                for name, st in split_combination(generic, strength):
                    r = con.execute("SELECT id FROM ingredient WHERE name = ?", (name,)).fetchone()
                    iid = r[0] if r else con.execute("INSERT INTO ingredient (name) VALUES (?)", (name,)).lastrowid
                    con.execute("INSERT OR IGNORE INTO product_ingredient VALUES (?,?,?,?)", (pid, iid, st, to_mg(st)))
                con.commit()
                return pid
            finally:
                con.close()

    def source(self, pid: int) -> str:
        rows = self._q("SELECT source FROM product WHERE id = ?", (pid,))
        return rows[0][0] if rows else ""

    def products_by_brand(self, brand: str) -> list[Product]:
        rows = self._q(
            "SELECT id, brand, generic, strength, form, manufacturer, unit_price FROM product WHERE brand_key = ?",
            (brand_key(brand),))
        return [Product(*r) for r in rows]

    def has_product(self, product_id: int) -> bool:
        return bool(self._q("SELECT 1 FROM product WHERE id = ?", (int(product_id),)))

    def product(self, pid: int) -> Product:
        return Product(*self._q(
            "SELECT id, brand, generic, strength, form, manufacturer, unit_price FROM product WHERE id = ?", (pid,))[0])

    def ingredients(self, pid: int) -> list[tuple[str, str, float | None]]:
        return self._q(
            "SELECT i.name, pi.strength, pi.mg FROM product_ingredient pi JOIN ingredient i ON i.id = pi.ingredient_id "
            "WHERE pi.product_id = ? ORDER BY i.name", (pid,))

    def drug_class(self, generic: str) -> str | None:
        rows = self._q("SELECT drug_class FROM generic_info WHERE generic = ?", (generic,))
        return rows[0][0] if rows and rows[0][0] else None

    def path(self, pid: int) -> dict:
        """Brand -> ingredient(s) -> class: the explanation shown on the Proof screen."""
        p = self.product(pid)
        return {"brand": p.brand, "strength": p.strength, "form": p.form, "maker": p.manufacturer,
                "ingredients": [{"name": n, "strength": s, "class": self.drug_class(n)} for n, s, _ in self.ingredients(pid)]}

    def all_brands(self) -> list[str]:
        return [r[0] for r in self._q("SELECT DISTINCT brand FROM product")]


if __name__ == "__main__":
    print(build())
