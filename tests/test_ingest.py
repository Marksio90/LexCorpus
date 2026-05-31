"""Testy jednostkowe dla rag/ingest.py — build_payload i logika is_repealed."""
import sys
from unittest.mock import MagicMock

# Mockujemy ciężkie zależności ML przed importem modułu
for mod in ("fastembed", "fastembed.sparse", "fastembed.sparse.bm25",
            "qdrant_client", "qdrant_client.http", "qdrant_client.http.models",
            "sentence_transformers", "tqdm"):
    sys.modules.setdefault(mod, MagicMock())

from rag.ingest import build_payload  # noqa: E402


class TestBuildPayload:
    def _chunk(self, **kwargs):
        base = {
            "act_id": "WDU20240001",
            "title": "Ustawa testowa",
            "year": "2024",
            "publisher": "WDU",
            "pos": "1",
            "url": "https://isap.sejm.gov.pl/test",
            "chunk_index": 0,
            "total_chunks": 3,
            "text": "Treść przepisu.",
            "approx_tokens": 10,
            "status": "",
        }
        base.update(kwargs)
        return base

    def test_obowiazujacy_not_repealed(self):
        p = build_payload(self._chunk(status="obowiązujący"))
        assert p["is_repealed"] is False

    def test_uchylony_is_repealed(self):
        p = build_payload(self._chunk(status="uchylony"))
        assert p["is_repealed"] is True

    def test_nieobowiazujacy_is_repealed(self):
        p = build_payload(self._chunk(status="nieobowiązujący"))
        assert p["is_repealed"] is True

    def test_empty_status_not_repealed(self):
        p = build_payload(self._chunk(status=""))
        assert p["is_repealed"] is False

    def test_status_case_insensitive(self):
        p = build_payload(self._chunk(status="UCHYLONY"))
        assert p["is_repealed"] is True

    def test_valid_from_year_extracted(self):
        p = build_payload(self._chunk(year="2019"))
        assert p["valid_from_year"] == 2019

    def test_valid_from_year_zero_on_missing(self):
        p = build_payload(self._chunk(year=""))
        assert p["valid_from_year"] == 0

    def test_valid_from_year_zero_on_invalid(self):
        p = build_payload(self._chunk(year="brak"))
        assert p["valid_from_year"] == 0

    def test_source_type_wdu(self):
        p = build_payload(self._chunk(publisher="WDU"))
        assert p["source_type"] == "legislation"

    def test_source_type_kis(self):
        p = build_payload(self._chunk(publisher="KIS"))
        assert p["source_type"] == "tax_interpretation"

    def test_source_type_supreme(self):
        p = build_payload(self._chunk(publisher="SUPREME"))
        assert p["source_type"] == "judgment_sn"

    def test_required_fields_present(self):
        p = build_payload(self._chunk())
        for field in ("act_id", "title", "year", "publisher", "source_type",
                      "pos", "url", "chunk_index", "total_chunks", "text",
                      "approx_tokens", "is_repealed", "valid_from_year"):
            assert field in p, f"Brakuje pola: {field}"

    def test_parent_child_fields_optional(self):
        chunk = self._chunk()
        chunk["chunk_type"] = "child"
        chunk["parent_text"] = "Tekst rodzica."
        chunk["parent_chunk_id"] = "abc123"
        p = build_payload(chunk)
        assert p["chunk_type"] == "child"
        assert p["parent_text"] == "Tekst rodzica."

    def test_parent_child_fields_absent_when_not_set(self):
        p = build_payload(self._chunk())
        assert "chunk_type" not in p
        assert "parent_text" not in p
