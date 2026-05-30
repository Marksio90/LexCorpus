"""
sat_graph.py — SAT-Graph temporal versioning for Polish legislation.

Implements the Work/Expression model from FRBR (Functional Requirements for
Bibliographic Records) adapted for Polish legal acts, as described in:
  "SAT-Graph: Temporal Knowledge Graphs for Legal RAG" (arXiv:2505.00039, JURIX 2025).

Polish laws are amended frequently. The same legislative "Work" (e.g. ustawa o VAT,
WDU20040540535) has multiple time-stamped "Expressions" — one per amendment cycle.
When a user asks "jaki był stan prawny art. 15 ustawy o VAT w 2019 roku?" we need the
expression valid on that exact date, not the current consolidated text.

Core concepts
─────────────
  LegalWork       — abstract act, version-independent (act_id, title, publisher)
  LegalExpression — concrete time-stamped version of a Work (valid_from … valid_to)
  SATGraph        — manages the Work→Expression temporal graph; supports point-in-time
                    queries: "which version of act X was valid on date D?"

Build the graph from chunks.jsonl (populated by ingest.py), then query it at
retrieval time to filter Qdrant to the correct expression_id before searching.

Usage as module:
    from rag.sat_graph import SATGraph
    g = SATGraph()
    g.load(Path("data/graph/sat_graph.json"))
    expr = g.get_expression_at("WDU20040540535", "2019-01-01")
    if expr:
        print(expr.valid_from, "→", expr.valid_to or "current")

Usage as script:
    python rag/sat_graph.py --input data/processed/chunks.jsonl \\
                            --output data/graph/sat_graph.json

    # point-in-time query:
    python rag/sat_graph.py --output data/graph/sat_graph.json \\
                            --query WDU20040540535 --date 2019-01-01

    # print amendment chain:
    python rag/sat_graph.py --output data/graph/sat_graph.json \\
                            --query WDU20040540535 --chain
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── date helpers ──────────────────────────────────────────────────────────────

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_RE = re.compile(r"^\d{4}$")

# Regex to detect amendment/change markers in text used to infer version boundaries
_AMENDS_TEXT_RE = re.compile(
    r"(?:zmienion\w+|nowelizacj\w+|zmian\w+\s+wniesion\w+|w\s+brzmieniu\s+nadanym)\s+"
    r"(?:przez\s+)?ustaw[aą]\s+z\s+dnia\s+\d+[^\d]+(\d{4})",
    re.IGNORECASE,
)

# Dz.U. reference pattern: "Dz.U. 2019 poz. 675"
_DZ_U_RE = re.compile(
    r"Dz\.\s*U\.\s+(?:z\s+)?(\d{4})\s+(?:r\.\s+)?(?:Nr\s+\d+[,\s]+)?poz\.\s+(\d+)",
    re.IGNORECASE,
)


def _date_from_year(year: int | str, month: int = 1, day: int = 1) -> str:
    """Build ISO date string from a year int/str and optional month/day."""
    return f"{int(year):04d}-{month:02d}-{day:02d}"


def _compare_dates(a: str, b: str) -> int:
    """Return -1, 0, +1 for a < b, a == b, a > b (ISO date strings)."""
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _date_in_range(date: str, valid_from: str, valid_to: str | None) -> bool:
    """Return True if date falls within [valid_from, valid_to)."""
    if date < valid_from:
        return False
    if valid_to is not None and date >= valid_to:
        return False
    return True


# ── data classes ──────────────────────────────────────────────────────────────


@dataclass
class LegalExpression:
    """
    A concrete time-stamped version of a LegalWork.

    Each Expression covers the period [valid_from, valid_to) during which the
    act had the textual content described by this record. valid_to=None means
    the expression is still current (no subsequent amendment known in corpus).

    expression_id is a stable surrogate key: "{act_id}_{valid_from}".
    """

    act_id: str
    expression_id: str          # "{act_id}_{valid_from}"
    valid_from: str             # ISO YYYY-MM-DD
    valid_to: str | None        # ISO YYYY-MM-DD or None (currently valid)
    amendment_source: str = ""  # act_id of the amending act, if known
    dz_u_reference: str = ""    # "Dz.U. YYYY poz. NNN" of the consolidation

    def as_dict(self) -> dict:
        return asdict(self)

    def is_current(self) -> bool:
        return self.valid_to is None

    def covers(self, date: str) -> bool:
        return _date_in_range(date, self.valid_from, self.valid_to)

    def __repr__(self) -> str:
        to = self.valid_to or "∞"
        return f"<Expression {self.expression_id} [{self.valid_from}–{to}]>"


@dataclass
class LegalWork:
    """
    Abstract legislative work (ustawa, rozporządzenie) — version-independent.

    Carries metadata that is stable across all versions, plus the ordered list
    of known Expressions (versions) sorted ascending by valid_from.
    """

    act_id: str
    title: str
    publisher: str
    expressions: list[LegalExpression] = field(default_factory=list)

    # convenience: set of years the corpus has chunks for this act
    _known_years: set[int] = field(default_factory=set, repr=False, compare=False)

    def sort_expressions(self) -> None:
        """Sort expressions ascending by valid_from date."""
        self.expressions.sort(key=lambda e: e.valid_from)
        # Plug valid_to gaps: each expression's valid_to = next expression's valid_from
        for i, expr in enumerate(self.expressions[:-1]):
            if expr.valid_to is None:
                expr.valid_to = self.expressions[i + 1].valid_from

    def get_expression_at(self, date: str) -> LegalExpression | None:
        """Return the expression valid on *date* (ISO string). None if unknown."""
        for expr in reversed(self.expressions):   # latest first → fast early exit
            if expr.valid_from <= date:
                if expr.valid_to is None or date < expr.valid_to:
                    return expr
        return None

    def get_current_expression(self) -> LegalExpression | None:
        """Return the last known expression (currently valid)."""
        if not self.expressions:
            return None
        return self.expressions[-1]  # already sorted ascending

    def as_dict(self) -> dict:
        return {
            "act_id": self.act_id,
            "title": self.title,
            "publisher": self.publisher,
            "expressions": [e.as_dict() for e in self.expressions],
        }


# ── main graph class ──────────────────────────────────────────────────────────


class SATGraph:
    """
    SAT-Graph: temporal Work→Expression graph for Polish legislation.

    Manages a registry of LegalWorks and their time-stamped Expressions.
    Supports point-in-time lookup ("which version was valid on date D?"),
    amendment chain traversal, and serialisation to/from JSON.

    Building from chunks
    ────────────────────
    The graph is built from chunks.jsonl metadata. Each chunk carries:
      act_id, year, publisher, title, status (uchylony/obowiązujący), pos, url

    When multiple chunks share the same act_id but different years, we treat
    each distinct year as a separate Expression (approximation; ideally the
    pipeline would extract the exact valid_from date from the amendment text).

    The valid_from date is approximated as YYYY-01-01 for the first chunk year
    found for an act, and YYYY-03-01 for subsequent amendment years (heuristic:
    Polish legislative calendar — most amendments published in spring).

    Point-in-time query
    ───────────────────
    Given an act_id and a date, find the expression that was valid on that date:

        expr = graph.get_expression_at("WDU20040540535", "2019-06-15")

    The returned LegalExpression carries the valid_from/valid_to window that
    the Qdrant filter should use (filter by `valid_from_year <= year`).
    """

    def __init__(self) -> None:
        self._works: dict[str, LegalWork] = {}    # act_id → LegalWork
        self._built: bool = False

    # ── accessors ─────────────────────────────────────────────────────────────

    @property
    def works(self) -> dict[str, LegalWork]:
        return self._works

    def get_work(self, act_id: str) -> LegalWork | None:
        return self._works.get(act_id)

    def get_expression_at(self, act_id: str, date: str) -> LegalExpression | None:
        """
        Return the Expression of *act_id* valid on *date* (ISO YYYY-MM-DD).

        Accepts bare year strings ("2019") as a convenience; they are expanded to
        "2019-01-01" (start of year — conservative choice for historical queries).

        Returns None if the act is not in the graph or no expression covers the date.
        """
        if _YEAR_RE.match(date):
            date = _date_from_year(date)
        work = self._works.get(act_id)
        if work is None:
            return None
        return work.get_expression_at(date)

    def get_current_expression(self, act_id: str) -> LegalExpression | None:
        """Return the currently valid expression for *act_id*."""
        work = self._works.get(act_id)
        if work is None:
            return None
        return work.get_current_expression()

    def get_amendment_chain(self, act_id: str) -> list[LegalExpression]:
        """Return all historical versions of *act_id* in chronological order."""
        work = self._works.get(act_id)
        if work is None:
            return []
        return list(work.expressions)  # already sorted

    def iter_works(self) -> Iterator[LegalWork]:
        yield from self._works.values()

    # ── building ──────────────────────────────────────────────────────────────

    def build_from_chunks(self, chunks: list[dict]) -> None:
        """
        Build the temporal graph from chunk metadata.

        Each dict in *chunks* must have at minimum: act_id, year, publisher, title.
        Optional: pos (Dz.U. position), url, status, amendment_source.

        Algorithm:
          1. Collect distinct (act_id, year) pairs from all chunks.
          2. For each act, create one Expression per distinct year observed.
          3. Sort expressions; fill in valid_to gaps.
          4. Mark repealed acts: latest expression valid_to = repealed date (approx).
        """
        log.info("Building SAT-Graph from %d chunks …", len(chunks))

        # Gather per-act metadata keyed by (act_id, year)
        # We track: title, publisher, pos, url, status, amendment_source, dz_u_ref
        act_meta: dict[str, dict] = {}   # act_id → stable metadata (title, publisher)
        # (act_id, year_str) → expression-level metadata
        expr_data: dict[tuple[str, str], dict] = {}

        for chunk in chunks:
            act_id = chunk.get("act_id", "").strip()
            if not act_id:
                continue
            year_raw = str(chunk.get("year", "")).strip()
            if not year_raw:
                continue
            # Normalise year: take first 4 digits in case it's "2019/05/..." or similar
            m = re.match(r"(\d{4})", year_raw)
            if not m:
                continue
            year = m.group(1)

            title = chunk.get("title", "")
            publisher = chunk.get("publisher", "WDU")

            if act_id not in act_meta:
                act_meta[act_id] = {"title": title, "publisher": publisher}

            key = (act_id, year)
            if key not in expr_data:
                expr_data[key] = {
                    "pos": str(chunk.get("pos", "")),
                    "url": chunk.get("url", ""),
                    "status": str(chunk.get("status", "")).lower().strip(),
                    "amendment_source": chunk.get("amendment_source", ""),
                }
            else:
                # Prefer richer data (non-empty pos)
                if not expr_data[key]["pos"] and chunk.get("pos"):
                    expr_data[key]["pos"] = str(chunk["pos"])
                if not expr_data[key]["amendment_source"] and chunk.get("amendment_source"):
                    expr_data[key]["amendment_source"] = chunk["amendment_source"]

        # Build LegalWork objects
        # Group (act_id, year) pairs by act_id
        from collections import defaultdict
        years_by_act: dict[str, list[str]] = defaultdict(list)
        for (act_id, year) in expr_data:
            years_by_act[act_id].append(year)

        created_works = 0
        created_expressions = 0

        for act_id, years in years_by_act.items():
            meta = act_meta[act_id]
            work = LegalWork(
                act_id=act_id,
                title=meta["title"],
                publisher=meta["publisher"],
            )

            sorted_years = sorted(set(years))
            work._known_years = {int(y) for y in sorted_years}

            for i, year in enumerate(sorted_years):
                edata = expr_data[(act_id, year)]
                # Approximate valid_from: first year → Jan 1; later amendments → Mar 1
                # (Polish legislative practice: most amendments enacted in spring)
                month = 1 if i == 0 else 3
                valid_from = _date_from_year(year, month=month)

                # Build Dz.U. reference from pos and year
                dz_u_ref = ""
                if edata["pos"]:
                    dz_u_ref = f"Dz.U. {year} poz. {edata['pos']}"

                expr = LegalExpression(
                    act_id=act_id,
                    expression_id=f"{act_id}_{valid_from}",
                    valid_from=valid_from,
                    valid_to=None,   # filled in by sort_expressions()
                    amendment_source=edata.get("amendment_source", ""),
                    dz_u_reference=dz_u_ref,
                )
                work.expressions.append(expr)
                created_expressions += 1

            work.sort_expressions()

            # If any chunk for this act is marked repealed, set valid_to on last expression
            # to a plausible repeal date (approximated as end of the latest known year + 1)
            statuses = {expr_data[(act_id, y)]["status"] for y in sorted_years}
            _REPEALED = {"uchylony", "nieobowiązujący", "uchylona", "utraciła moc"}
            if statuses & _REPEALED and work.expressions:
                last = work.expressions[-1]
                if last.valid_to is None:
                    # Approximate: act was repealed sometime after its last known year
                    try:
                        repeal_year = max(int(y) for y in sorted_years) + 1
                    except ValueError:
                        repeal_year = 9999
                    last.valid_to = _date_from_year(repeal_year)

            self._works[act_id] = work
            created_works += 1

        self._built = True
        log.info(
            "SAT-Graph built: %d works, %d expressions (%.1f avg versions/act)",
            created_works,
            created_expressions,
            created_expressions / max(created_works, 1),
        )

    # ── serialisation ─────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        """Serialise the entire graph to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "works": [w.as_dict() for w in self._works.values()],
        }
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        log.info("SAT-Graph saved to %s (%d works)", path, len(self._works))

    def load(self, path: Path) -> None:
        """Load a previously saved graph from JSON."""
        if not path.exists():
            raise FileNotFoundError(f"SAT-Graph file not found: {path}")
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        version = data.get("version", 1)
        if version != 1:
            log.warning("SAT-Graph version mismatch (expected 1, got %s) — loading anyway", version)

        self._works.clear()
        for wdict in data.get("works", []):
            expressions = []
            for edict in wdict.get("expressions", []):
                expressions.append(LegalExpression(
                    act_id=edict["act_id"],
                    expression_id=edict["expression_id"],
                    valid_from=edict["valid_from"],
                    valid_to=edict.get("valid_to"),
                    amendment_source=edict.get("amendment_source", ""),
                    dz_u_reference=edict.get("dz_u_reference", ""),
                ))
            work = LegalWork(
                act_id=wdict["act_id"],
                title=wdict["title"],
                publisher=wdict["publisher"],
                expressions=expressions,
            )
            self._works[wdict["act_id"]] = work

        self._built = True
        log.info("SAT-Graph loaded from %s (%d works)", path, len(self._works))

    # ── statistics ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return a summary statistics dict."""
        total_expr = sum(len(w.expressions) for w in self._works.values())
        multi_version = sum(1 for w in self._works.values() if len(w.expressions) > 1)
        repealed = sum(
            1 for w in self._works.values()
            if w.expressions and w.expressions[-1].valid_to is not None
        )
        max_versions = max((len(w.expressions) for w in self._works.values()), default=0)
        avg_versions = total_expr / max(len(self._works), 1)

        return {
            "total_works": len(self._works),
            "total_expressions": total_expr,
            "multi_version_works": multi_version,
            "repealed_works": repealed,
            "avg_versions_per_work": round(avg_versions, 2),
            "max_versions_single_work": max_versions,
        }


# ── CLI ───────────────────────────────────────────────────────────────────────


def _load_chunks_jsonl(path: Path) -> list[dict]:
    chunks = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("Skipping invalid JSON at line %d: %s", lineno, exc)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "SAT-Graph: build/query temporal versioning graph for Polish legislation.\n\n"
            "Build mode (requires --input):\n"
            "  python rag/sat_graph.py --input data/processed/chunks.jsonl "
            "--output data/graph/sat_graph.json\n\n"
            "Query mode (requires --output with existing file + --query):\n"
            "  python rag/sat_graph.py --output data/graph/sat_graph.json "
            "--query WDU20040540535 --date 2019-01-01"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", type=Path, default=None,
        help="chunks.jsonl input file (required for build mode)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/graph/sat_graph.json"),
        help="Path to save/load the graph JSON (default: data/graph/sat_graph.json)",
    )
    parser.add_argument(
        "--query", default=None,
        help="act_id to query (e.g. WDU20040540535)",
    )
    parser.add_argument(
        "--date", default=None,
        help="ISO date (YYYY-MM-DD) or year for point-in-time query",
    )
    parser.add_argument(
        "--chain", action="store_true",
        help="Print full amendment chain for --query act",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print graph statistics",
    )
    parser.add_argument(
        "--max-chunks", type=int, default=None,
        help="Limit number of chunks processed (for testing)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    graph = SATGraph()

    # ── Build mode ────────────────────────────────────────────────────────────
    if args.input is not None:
        if not args.input.exists():
            log.error("Input file not found: %s", args.input)
            sys.exit(1)

        log.info("Loading chunks from %s …", args.input)
        chunks = _load_chunks_jsonl(args.input)
        log.info("Loaded %d chunks", len(chunks))

        if args.max_chunks:
            chunks = chunks[: args.max_chunks]
            log.info("Limiting to %d chunks", len(chunks))

        graph.build_from_chunks(chunks)
        graph.save(args.output)
        log.info("Graph saved to %s", args.output)

    elif args.output.exists():
        # ── Load existing graph for query mode ────────────────────────────────
        graph.load(args.output)
    else:
        log.error(
            "No --input given and --output file '%s' does not exist. "
            "Run with --input to build the graph first.",
            args.output,
        )
        sys.exit(1)

    # ── Stats ─────────────────────────────────────────────────────────────────
    if args.stats or (not args.query):
        s = graph.stats()
        if args.json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            print("\nSAT-Graph statistics:")
            for k, v in s.items():
                print(f"  {k}: {v}")

    if not args.query:
        return

    # ── Query mode ────────────────────────────────────────────────────────────
    act_id = args.query
    work = graph.get_work(act_id)
    if work is None:
        log.error("Act '%s' not found in graph. Check act_id.", act_id)
        sys.exit(1)

    # Point-in-time query
    if args.date:
        expr = graph.get_expression_at(act_id, args.date)
        if expr is None:
            print(f"No expression found for {act_id!r} on {args.date!r}.")
            print("Known versions:")
            for e in graph.get_amendment_chain(act_id):
                print(f"  {e}")
        else:
            if args.json:
                print(json.dumps(expr.as_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"\nExpression of '{act_id}' valid on {args.date}:")
                print(f"  expression_id : {expr.expression_id}")
                print(f"  valid_from    : {expr.valid_from}")
                print(f"  valid_to      : {expr.valid_to or '(currently valid)'}")
                print(f"  dz_u_ref      : {expr.dz_u_reference or '—'}")
                print(f"  amendment_src : {expr.amendment_source or '—'}")
        return

    # Full amendment chain
    if args.chain:
        chain = graph.get_amendment_chain(act_id)
        if args.json:
            print(json.dumps([e.as_dict() for e in chain], ensure_ascii=False, indent=2))
        else:
            print(f"\nAmendment chain for '{act_id}' ({work.title}):")
            print(f"  Publisher: {work.publisher}")
            print(f"  {len(chain)} known version(s):\n")
            for i, expr in enumerate(chain, 1):
                to = expr.valid_to or "∞ (current)"
                src = f"  (amended by {expr.amendment_source})" if expr.amendment_source else ""
                ref = f"  [{expr.dz_u_reference}]" if expr.dz_u_reference else ""
                print(f"  [{i:>3}] {expr.valid_from} – {to}{src}{ref}")
        return

    # Default: show current expression
    current = graph.get_current_expression(act_id)
    if current is None:
        print(f"No expressions found for '{act_id}'.")
    else:
        if args.json:
            print(json.dumps(current.as_dict(), ensure_ascii=False, indent=2))
        else:
            to = current.valid_to or "(currently valid)"
            print(f"\nCurrent expression of '{act_id}':")
            print(f"  Title      : {work.title}")
            print(f"  Publisher  : {work.publisher}")
            print(f"  valid_from : {current.valid_from}")
            print(f"  valid_to   : {to}")
            print(f"  dz_u_ref   : {current.dz_u_reference or '—'}")
            print(f"  Total versions in graph: {len(work.expressions)}")


if __name__ == "__main__":
    main()
