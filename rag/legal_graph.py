"""
legal_graph.py — Polish Legal Knowledge Graph from ISAP/SAOS.

Builds a citation graph over Polish legislation by extracting cross-references
between acts (e.g. "art. 15 ustawy z dnia 11 marca 2004 r. o podatku od towarów i usług").
Enables GraphRAG-style queries: "jak ustawa o VAT odnosi się do kodeksu spółek handlowych?"

Graph schema (neo4j or in-memory networkx):
  Nodes: Act(act_id, title, year, publisher)
  Edges: CITES(from_act_id, to_act_id, article_ref, count)
         AMENDS(amending_act_id, amended_act_id, date)
         REPEALS(repealing_act_id, repealed_act_id, date)

Usage:
    # Build graph from chunks JSONL (no Neo4j required — uses networkx in-memory):
    python rag/legal_graph.py \\
        --input data/processed/chunks.jsonl \\
        --output data/graph/isap_graph.json

    # Export to Cypher for Neo4j import:
    python rag/legal_graph.py \\
        --input data/processed/chunks.jsonl \\
        --output data/graph/isap_graph.json \\
        --cypher data/graph/isap_graph.cypher

Requirements:
    pip install networkx
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Patterns to extract cross-references in Polish legal text
_YEAR_ACT_RE = re.compile(
    r"ustaw[aą]\s+z\s+dnia\s+\d+\s+\w+\s+(\d{4})\s+r[.\s]",
    re.IGNORECASE,
)
_ROZP_RE = re.compile(
    r"rozporządzen\w+\s+(?:Ministra\s+\w+\s+)?z\s+dnia\s+\d+\s+\w+\s+(\d{4})\s+r[.\s]",
    re.IGNORECASE,
)
_DZ_U_RE = re.compile(
    r"Dz\.\s*U\.\s+(?:z\s+)?(\d{4})\s+r\.",
    re.IGNORECASE,
)
_AMENDS_RE = re.compile(
    r"(?:zmienia|nowelizuje|zmieniona przez|w brzmieniu nadanym przez)\s+"
    r"ustaw[aą]\s+z\s+dnia\s+\d+\s+\w+\s+(\d{4})",
    re.IGNORECASE,
)
_REPEALS_RE = re.compile(
    r"(?:uchyla|traci moc|zastępuje)\s+ustaw[aą]\s+z\s+dnia\s+\d+\s+\w+\s+(\d{4})",
    re.IGNORECASE,
)

# Known act fingerprints for year-based resolution
_KNOWN_ACTS = {
    "2004": "podatku od towarów i usług (VAT)",
    "2000": "kodeksu spółek handlowych",
    "1974": "kodeksu pracy",
    "1964": "kodeksu cywilnego",
    "1997": "ordynacji podatkowej",
}


class LegalGraph:
    """In-memory citation graph for Polish legal acts."""

    def __init__(self) -> None:
        self.acts: dict[str, dict] = {}          # act_id → metadata
        self.citations: list[dict] = []           # {from, to, ref, count}
        self.amendments: list[dict] = []          # {amending, amended}
        self.repeals: list[dict] = []             # {repealing, repealed}
        self._citation_counts: dict[tuple, int] = defaultdict(int)

    def add_act(self, act_id: str, title: str, year: str, publisher: str) -> None:
        if act_id not in self.acts:
            self.acts[act_id] = {
                "act_id": act_id,
                "title": title,
                "year": year,
                "publisher": publisher,
            }

    def add_citation(self, from_act: str, year_ref: str, ref_text: str) -> None:
        """Record that from_act cites another act identified by its publication year."""
        key = (from_act, year_ref)
        self._citation_counts[key] += 1

    def add_amendment(self, amending: str, amended_year: str) -> None:
        self.amendments.append({"amending": amending, "amended_year": amended_year})

    def add_repeal(self, repealing: str, repealed_year: str) -> None:
        self.repeals.append({"repealing": repealing, "repealed_year": repealed_year})

    def finalize(self) -> None:
        """Freeze citation counts into the citations list."""
        self.citations = [
            {"from": from_act, "to_year": year, "count": count}
            for (from_act, year), count in self._citation_counts.items()
        ]

    def stats(self) -> dict:
        return {
            "acts": len(self.acts),
            "citations": len(self.citations),
            "amendments": len(self.amendments),
            "repeals": len(self.repeals),
            "top_cited_years": sorted(
                defaultdict(int, {edge["to_year"]: edge["count"] for edge in self.citations}).items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10],
        }

    def to_dict(self) -> dict:
        return {
            "acts": list(self.acts.values()),
            "citations": self.citations,
            "amendments": self.amendments,
            "repeals": self.repeals,
        }

    def export_cypher(self) -> Iterator[str]:
        """Yield Cypher statements for Neo4j import."""
        for act in self.acts.values():
            yield (
                f"MERGE (a:Act {{act_id: {json.dumps(act['act_id'])}}}) "
                f"SET a.title = {json.dumps(act['title'])}, "
                f"a.year = {json.dumps(act['year'])}, "
                f"a.publisher = {json.dumps(act['publisher'])};"
            )
        for edge in self.citations:
            yield (
                f"MATCH (a:Act {{act_id: {json.dumps(edge['from'])}}}) "
                f"MERGE (b:YearRef {{year: {json.dumps(edge['to_year'])}}}) "
                f"MERGE (a)-[r:CITES {{count: {edge['count']}}}]->(b);"
            )
        for edge in self.amendments:
            yield (
                f"MATCH (a:Act {{act_id: {json.dumps(edge['amending'])}}}) "
                f"MERGE (b:YearRef {{year: {json.dumps(edge['amended_year'])}}}) "
                f"MERGE (a)-[:AMENDS]->(b);"
            )

    def get_most_cited(self, top_n: int = 20) -> list[dict]:
        """Return the most frequently cited years (proxy for most cited acts)."""
        year_counts: dict[str, int] = defaultdict(int)
        for edge in self.citations:
            year_counts[edge["to_year"]] += edge["count"]
        return [
            {"year": year, "citations": count, "known_as": _KNOWN_ACTS.get(year, "")}
            for year, count in sorted(year_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        ]


def extract_citations_from_chunk(graph: LegalGraph, chunk: dict) -> None:
    """Parse a single chunk's text and update the graph with found references."""
    act_id = chunk.get("act_id", "")
    title = chunk.get("title", "")
    year = str(chunk.get("year", ""))
    publisher = chunk.get("publisher", "WDU")
    text = chunk.get("text", "")

    graph.add_act(act_id, title, year, publisher)

    # Extract cross-references to other acts by year
    for m in _YEAR_ACT_RE.finditer(text):
        cited_year = m.group(1)
        if cited_year != year:  # skip self-references
            graph.add_citation(act_id, cited_year, m.group(0)[:80])

    for m in _ROZP_RE.finditer(text):
        cited_year = m.group(1)
        if cited_year != year:
            graph.add_citation(act_id, cited_year, m.group(0)[:80])

    for m in _DZ_U_RE.finditer(text):
        cited_year = m.group(1)
        if cited_year != year:
            graph.add_citation(act_id, cited_year, m.group(0)[:60])

    for m in _AMENDS_RE.finditer(text):
        graph.add_amendment(act_id, m.group(1))

    for m in _REPEALS_RE.finditer(text):
        graph.add_repeal(act_id, m.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Polish Legal Citation Graph from ISAP/SAOS chunks."
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/graph/isap_graph.json"))
    parser.add_argument("--cypher", type=Path, default=None, help="Export to Cypher for Neo4j")
    parser.add_argument("--isap-only", action="store_true", help="Only process ISAP legislation")
    parser.add_argument("--max-chunks", type=int, default=None)
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input not found: %s", args.input)
        sys.exit(1)

    SAOS_PUBLISHERS = {"ADMINISTRATIVE", "SUPREME", "CONSTITUTIONAL_TRIBUNAL", "COMMON", "NATIONAL_APPEAL_CHAMBER"}
    graph = LegalGraph()
    processed = 0

    log.info("Building citation graph from %s …", args.input)
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.isap_only and chunk.get("publisher", "WDU") in SAOS_PUBLISHERS:
                continue
            extract_citations_from_chunk(graph, chunk)
            processed += 1
            if args.max_chunks and processed >= args.max_chunks:
                break

    graph.finalize()
    log.info("Processed %d chunks. Graph stats: %s", processed, graph.stats())

    log.info("Top cited acts:")
    for entry in graph.get_most_cited(15):
        known = f" ({entry['known_as']})" if entry["known_as"] else ""
        log.info("  Year %s%s: cited %d times", entry["year"], known, entry["citations"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(graph.to_dict(), f, ensure_ascii=False, indent=2)
    log.info("Graph saved to %s", args.output)

    if args.cypher:
        args.cypher.parent.mkdir(parents=True, exist_ok=True)
        with args.cypher.open("w", encoding="utf-8") as f:
            for stmt in graph.export_cypher():
                f.write(stmt + "\n")
        log.info("Cypher export saved to %s", args.cypher)
        log.info(
            "Import with: cypher-shell -u neo4j -p <password> --file %s", args.cypher
        )


if __name__ == "__main__":
    main()
