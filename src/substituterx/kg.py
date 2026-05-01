"""Knowledge graph store. DuckDB-backed, loaded from seed JSON.

Per SPEC §5: edges carry constraint_items that the validator evaluates against the
resident context vector P. The store is read-only after ingest — the agent layer
is what makes substitution decisions context-conditional, not the store.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb


SEED_DIR = Path(__file__).parent.parent.parent / "data"


@dataclass(frozen=True)
class Drug:
    rxcui: str
    name: str
    tty: str
    ingredient_in: str
    strength: str
    dose_form: str
    te_code: str | None
    is_brand: bool
    appl_no: str | None
    nti: bool


@dataclass(frozen=True)
class Edge:
    edge_id: str
    relation: str
    subject: str
    object: str
    constraint_items: list[dict[str, Any]]
    citations: list[dict[str, str]]


class KGStore:
    """In-memory DuckDB. Fast enough for the prototype scale (~50 drugs, ~30 edges)."""

    def __init__(self, db_path: str | None = None) -> None:
        self.con = duckdb.connect(db_path or ":memory:")
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS drugs (
                rxcui TEXT PRIMARY KEY,
                name TEXT, tty TEXT, ingredient_in TEXT,
                strength TEXT, dose_form TEXT,
                te_code TEXT, is_brand BOOLEAN,
                appl_no TEXT, nti BOOLEAN
            );
            CREATE TABLE IF NOT EXISTS edges (
                edge_id TEXT PRIMARY KEY,
                relation TEXT, subject TEXT, object TEXT,
                constraint_items JSON, citations JSON
            );
            CREATE INDEX IF NOT EXISTS edges_subject ON edges(subject);
            CREATE INDEX IF NOT EXISTS edges_relation ON edges(relation);
            """
        )

    def load_seed(self, drugs_path: Path | None = None, edges_path: Path | None = None) -> dict:
        drugs_path = drugs_path or (SEED_DIR / "seed_drugs.json")
        edges_path = edges_path or (SEED_DIR / "seed_edges.json")
        drugs = json.loads(drugs_path.read_text())["drugs"]
        edges = json.loads(edges_path.read_text())["edges"]
        for d in drugs:
            self.con.execute(
                "INSERT OR REPLACE INTO drugs VALUES (?,?,?,?,?,?,?,?,?,?)",
                [d["rxcui"], d["name"], d["tty"], d["ingredient_in"], d["strength"],
                 d["dose_form"], d.get("te_code"), d["is_brand"], d.get("appl_no"), d["nti"]],
            )
        for e in edges:
            self.con.execute(
                "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?)",
                [e["edge_id"], e["relation"], e["subject"], e["object"],
                 json.dumps(e["constraint_items"]), json.dumps(e["citations"])],
            )
        return {"drugs": len(drugs), "edges": len(edges)}

    # ---------- query API used by the agents ----------

    def get_drug(self, rxcui: str) -> Drug | None:
        row = self.con.execute("SELECT * FROM drugs WHERE rxcui = ?", [rxcui]).fetchone()
        if not row:
            return None
        return Drug(*row)

    # Known brand keywords for the curated 22-drug seed. Production replaces this with
    # RxNav approximateTerm + tradename_of/has_tradename relations.
    _BRAND_KEYWORDS = (
        "toprol", "lipitor", "norvasc", "coumadin", "synthroid", "wellbutrin",
        "cardizem", "tiazac", "dilacor", "bactrim", "prinivil", "eliquis", "lopressor",
    )

    @staticmethod
    def _expand_unit_tokens(tokens: list[str]) -> list[str]:
        """100 mcg → also try 0.1 mg. Same for mg ↔ g."""
        extra: list[str] = []
        for i, t in enumerate(tokens):
            if i == 0:
                continue
            try:
                n = float(tokens[i - 1])
            except ValueError:
                continue
            if t == "mcg":
                extra.extend(re.split(r"\W+", f"{n / 1000.0:g}"))
                extra.append("mg")
            elif t == "mg":
                if n >= 1000:
                    extra.extend(re.split(r"\W+", f"{n / 1000.0:g}"))
                    extra.append("g")
                # mg → mcg upscale (e.g., 0.1 mg → 100 mcg)
                if n < 1:
                    extra.extend(re.split(r"\W+", f"{int(round(n * 1000))}"))
                    extra.append("mcg")
        return tokens + [e for e in extra if e]

    def find_by_name(self, label_text: str) -> Drug | None:
        """Score-based word-token match. Returns None if no candidate clears the bar —
        the orchestrator's abstain path handles missing RxCUI."""
        raw = [t for t in re.split(r"\W+", label_text.lower()) if len(t) > 1]
        if not raw:
            return None
        tokens = self._expand_unit_tokens(raw)
        rows = self.con.execute("SELECT * FROM drugs").fetchall()

        def name_words(name: str) -> set[str]:
            return {w for w in re.split(r"\W+", name.lower()) if w}

        threshold = max(2, int(0.6 * len(tokens)))
        scored: list[tuple[int, Drug]] = []
        for row in rows:
            d = Drug(*row)
            nw = name_words(d.name)
            score = sum(1 for t in tokens if t in nw)
            if score >= threshold:
                scored.append((score, d))
        if not scored:
            return None

        ltl = label_text.lower()
        is_brand_query = any(re.search(rf"\b{b}\b", ltl) for b in self._BRAND_KEYWORDS)
        scored.sort(key=lambda sd: (
            -sd[0],
            0 if sd[1].is_brand == is_brand_query else 1,
            len(sd[1].name),
        ))
        return scored[0][1]

    def edges_between(self, a: str, b: str) -> list[Edge]:
        rows = self.con.execute(
            "SELECT * FROM edges WHERE (subject=? AND object=?) OR (subject=? AND object=?)",
            [a, b, b, a],
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def edges_from(self, subject: str, relations: list[str] | None = None) -> list[Edge]:
        if relations:
            placeholders = ",".join(["?"] * len(relations))
            rows = self.con.execute(
                f"SELECT * FROM edges WHERE subject=? AND relation IN ({placeholders})",
                [subject, *relations],
            ).fetchall()
        else:
            rows = self.con.execute("SELECT * FROM edges WHERE subject=?", [subject]).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def all_edges_touching(self, rxcui: str) -> list[Edge]:
        rows = self.con.execute(
            "SELECT * FROM edges WHERE subject=? OR object=?", [rxcui, rxcui]
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    @staticmethod
    def _row_to_edge(row: tuple) -> Edge:
        edge_id, relation, subject, object_, constraint_items, citations = row
        return Edge(
            edge_id=edge_id, relation=relation, subject=subject, object=object_,
            constraint_items=json.loads(constraint_items) if isinstance(constraint_items, str) else constraint_items,
            citations=json.loads(citations) if isinstance(citations, str) else citations,
        )
