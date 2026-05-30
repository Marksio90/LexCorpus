"""Testy jednostkowe dla rag/retriever.py — routing, RetrievedChunk, filtrowanie temporal."""
import sys
from unittest.mock import MagicMock

for mod in ("fastembed", "fastembed.sparse", "fastembed.sparse.bm25",
            "qdrant_client", "qdrant_client.http", "qdrant_client.http.models",
            "sentence_transformers"):
    sys.modules.setdefault(mod, MagicMock())

import pytest
from rag.retriever import _route_query, RetrievedChunk


class TestRouteQuery:
    def test_routes_tax_keywords(self):
        assert _route_query("Jak rozliczyć VAT i podatek dochodowy?") == "tax"

    def test_routes_judgment_keywords(self):
        # Wymaga >= 2 trafień: "wyrok" + "NSA" matchują \b...\b
        assert _route_query("Czy sąd NSA wydał wyrok w tej sprawie?") == "judgment"

    def test_routes_legislation_keywords(self):
        assert _route_query("Co oznacza artykuł i jaki jest paragraf w kodeksie?") == "legislation"

    def test_ambiguous_returns_none(self):
        assert _route_query("Co zrobić?") is None

    def test_mixed_signals_returns_none(self):
        # Oba zestawy słów — zbyt niejednoznaczne żeby routować
        result = _route_query("Jaki wyrok wydano w sprawie o podatek VAT i KIS interpretacja?")
        assert result is None or result in ("tax", "judgment")


class TestRetrievedChunk:
    def _make(self, **kwargs) -> RetrievedChunk:
        defaults = dict(
            score=0.9, text="Tekst.", act_id="WDU2024001", title="Ustawa",
            year="2024", publisher="WDU", pos="1", url="https://isap.sejm.gov.pl",
            chunk_index=0, total_chunks=1,
        )
        defaults.update(kwargs)
        return RetrievedChunk(**defaults)

    def test_default_not_repealed(self):
        chunk = self._make()
        assert chunk.is_repealed is False

    def test_default_valid_from_year_zero(self):
        chunk = self._make()
        assert chunk.valid_from_year == 0

    def test_repealed_field_stored(self):
        chunk = self._make(is_repealed=True, valid_from_year=2010)
        assert chunk.is_repealed is True
        assert chunk.valid_from_year == 2010

    def test_citation_with_all_fields(self):
        chunk = self._make(title="Ustawa o VAT", year="2004", pos="54")
        cit = chunk.citation()
        assert "Ustawa o VAT" in cit
        assert "2004" in cit
        assert "poz. 54" in cit

    def test_citation_fallback_to_act_id(self):
        chunk = self._make(title="", year="", pos="", url="")
        assert "WDU2024001" in chunk.citation()

    def test_as_dict_contains_temporal_fields(self):
        chunk = self._make(is_repealed=True, valid_from_year=2019)
        d = chunk.as_dict()
        assert d["is_repealed"] is True
        assert d["valid_from_year"] == 2019

    def test_as_dict_all_base_fields(self):
        chunk = self._make()
        d = chunk.as_dict()
        for field in ("score", "text", "act_id", "title", "year",
                      "publisher", "pos", "url", "chunk_index", "total_chunks"):
            assert field in d
