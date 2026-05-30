"""
ner.py — Polish Legal Named Entity Recognition (NER) using HerBERT.

Extracts the following entity types from Polish court decisions and legislation:

    PERSON       — judge names, party names
    ORGANIZATION — court names, company names, public bodies
    LAW          — referenced acts, e.g. "ustawa z dnia 11 marca 2004 r."
    ARTICLE      — article references, e.g. "art. 415 k.c.", "§ 7 ust. 2"
    DATE         — dates of rulings, entry-into-force dates, deadlines
    CASE_ID      — case numbers, e.g. "IV CSK 123/20", "II SA/Wa 1234/21"

Public API
----------
Both classes share the same interface:

    result = ner.extract(text)          # returns NERResult
    result.entities                     # list[Entity]

Each Entity has: .text, .label, .score (confidence in [0, 1]), .start, .end

Classes
-------
    RegexLegalNER      — pure-regex, no dependencies; high precision for
                         LAW / ARTICLE / DATE / CASE_ID; no PERSON / ORG.
    PolishLegalNER     — adds PERSON / ORGANIZATION via a HerBERT transformer
                         pipeline when a model is available; falls back to
                         RegexLegalNER otherwise.

Usage as module:
    from rag.ner import PolishLegalNER, RegexLegalNER

    # Regex only (always available):
    ner = RegexLegalNER()
    result = ner.extract("Wyrokiem z dnia 15 marca 2021 r. (sygn. II CSK 45/21) …")
    for e in result.entities:
        print(e.label, repr(e.text), e.score)

    # Transformer-powered (loads model lazily):
    ner = PolishLegalNER(model_path="output/herbert-legal-ner", device="cpu")
    result = ner.extract(text)

    # Batch enrichment:
    enriched_chunks = ner.enrich_chunks(chunks)
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "allegro/herbert-base-cased"
DEFAULT_MODEL_PATH = "output/herbert-legal-ner"
MAX_LENGTH = 512          # max sub-word tokens per transformer call
MIN_TRANSFORMER_SCORE = 0.70  # discard transformer predictions below this threshold


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class Entity:
    """A single named entity extracted from a legal text."""

    text: str
    """Surface form of the entity as it appears in the text."""

    label: str
    """Entity type: PERSON | ORGANIZATION | LAW | ARTICLE | DATE | CASE_ID"""

    start: int
    """Character-level start offset (inclusive)."""

    end: int
    """Character-level end offset (exclusive)."""

    score: float
    """Confidence score in [0, 1]. Rule-based matches report 1.0."""

    # Legacy alias so callers that use .confidence also work
    @property
    def confidence(self) -> float:
        return self.score

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "score": round(self.score, 4),
        }


@dataclass
class NERResult:
    """Result of a single NER call."""

    entities: list[Entity] = field(default_factory=list)
    """All extracted entities, sorted by start offset."""

    text: str = ""
    """The original text that was processed."""


# ── Regex patterns ─────────────────────────────────────────────────────────────
# All patterns are compile-once at module load.

_LAW_PATTERNS: list[re.Pattern] = [
    # "ustawa z dnia 11 marca 2004 r. o podatku od towarów i usług"
    re.compile(
        r"(?:ustawa|ustawy|ustawie|ustawą)\s+z\s+dnia\s+\d{1,2}\s+\w+\s+\d{4}\s+r\.?"
        r"(?:\s+o\s+[^,;\n(]{5,60})?",
        re.IGNORECASE,
    ),
    # "rozporządzenie Ministra … z dnia …"
    re.compile(
        r"rozporządzeni[ae]\s+(?:Ministra|Rady\s+Ministrów|Prezesa\s+Rady\s+Ministrów"
        r"|[A-ZŁŚŻŹ][a-złśżźćńóę]+)\s+z\s+dnia\s+\d{1,2}\s+\w+\s+\d{4}\s+r\.?",
        re.IGNORECASE,
    ),
    # Named codes: "Kodeks cywilny", "Kodeks spółek handlowych", etc.
    re.compile(
        r"Kodeks\s+(?:cywilny|postępowania\s+cywilnego|karny|postępowania\s+karnego|"
        r"pracy|spółek\s+handlowych|rodzinny\s+i\s+opiekuńczy|"
        r"wykroczeń|postępowania\s+administracyjnego|postępowania\s+karnego\s+skarbowego)\b",
        re.IGNORECASE,
    ),
    # EU directives: "dyrektywa 2006/112/WE"
    re.compile(
        r"dyrektywa\s+(?:\d{4}/\d+/(?:WE|UE|EWG|EURATOM)|Parlamentu\s+Europejskiego)",
        re.IGNORECASE,
    ),
    # Journal of Laws reference: "Dz. U. z 2004 r. Nr 54, poz. 535"
    re.compile(
        r"Dz\.?\s*U\.?\s*(?:z\s+\d{4}\s+r\.?)?\s*(?:Nr\s+\d+,?\s*poz\.\s*\d+|poz\.\s*\d+)",
        re.IGNORECASE,
    ),
]

_ARTICLE_PATTERNS: list[re.Pattern] = [
    # "art. 86 ust. 1 pkt 2 lit. a"
    re.compile(
        r"art\.\s*\d+[a-z]?(?:\s+ust\.\s*\d+[a-z]?)?(?:\s+pkt\s*\d+[a-z]?)?(?:\s+lit\.\s*[a-z])?",
        re.IGNORECASE,
    ),
    # "§ 3 ust. 2"
    re.compile(
        r"§\s*\d+[a-z]?(?:\s+ust\.\s*\d+[a-z]?)?(?:\s+pkt\s*\d+[a-z]?)?",
        re.IGNORECASE,
    ),
    # "ust. 5 pkt 3 lit. b"
    re.compile(
        r"ust\.\s*\d+[a-z]?\s+pkt\s*\d+[a-z]?(?:\s+lit\.\s*[a-z])?",
        re.IGNORECASE,
    ),
]

_DATE_PATTERNS: list[re.Pattern] = [
    # "11 marca 2004 r."
    re.compile(
        r"\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|"
        r"września|października|listopada|grudnia)\s+\d{4}\s+r\.?",
        re.IGNORECASE,
    ),
    # ISO: "2021-03-15"
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # Numeric: "15.03.2021" or "15/03/2021"
    re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\b"),
]

_CASE_ID_PATTERNS: list[re.Pattern] = [
    # "IV CSK 123/20"
    re.compile(
        r"\b(?:I{1,3}V?|V?I{0,3}|[IVXLC]+)\s+"
        r"(?:CSK|CKN|CZ|ACa|ACz|AKa|APa|Ap|Ca|GC|GCo|SK|KC|KZ|KZP|KK|KO|"
        r"KSP|KSKP|OPS|FPS|GPS|OSK|SA/[A-Z]{2}|WSA|FSK|Po|Ps|NSA|"
        r"SO|SR|SW|SC|SN|TK|PA|SDI|WSD|DSP|DSI|P[A-Z]?|U[A-Z]?|K[A-Z]?|S[A-Z]?|[A-Z]{1,4})\s+"
        r"\d+/\d{2,4}\b",
        re.IGNORECASE,
    ),
    # "II SA/Wa 1234/21"
    re.compile(
        r"\b(?:I{1,3}V?|V?I{0,3}|[IVXLC]+)\s+[A-Z]{1,4}/[A-Z]{2}\s+\d+/\d{2,4}\b",
        re.IGNORECASE,
    ),
    # "sygn. akt IV CSK 123/20" — anchored to end with /YYYY pattern to avoid greediness
    re.compile(
        r"sygn\.?\s+(?:akt\s+)?(?:[A-ZŁŚŻŹ0-9]{1,8}(?:\s+[A-ZŁŚŻŹ0-9]{1,10}){0,3}\s+\d+/\d{2,4})",
        re.IGNORECASE,
    ),
    # "KIO 1234/20"
    re.compile(r"\bKIO\s+\d+/\d{2,4}\b", re.IGNORECASE),
]


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _extract_by_patterns(
    text: str, patterns: list[re.Pattern], label: str
) -> list[Entity]:
    entities: list[Entity] = []
    for pattern in patterns:
        for m in pattern.finditer(text):
            surface = m.group(0).strip()
            if len(surface) < 3:
                continue
            entities.append(Entity(
                text=surface,
                label=label,
                start=m.start(),
                end=m.start() + len(surface),
                score=1.0,
            ))
    return entities


def _resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """
    Remove overlapping entity spans.

    Tie-breaking:
    1. Higher score wins.
    2. For equal score, longer span wins.
    3. Rule-based (score=1.0) always beats transformer predictions.
    """
    if not entities:
        return entities
    sorted_ents = sorted(
        entities,
        key=lambda e: (e.start, -e.score, -(e.end - e.start)),
    )
    result: list[Entity] = []
    last_end = -1
    for ent in sorted_ents:
        if ent.start >= last_end:
            result.append(ent)
            last_end = ent.end
        else:
            prev = result[-1]
            if (ent.score, ent.end - ent.start) > (prev.score, prev.end - prev.start):
                result[-1] = ent
                last_end = ent.end
    return result


def _normalise_transformer_label(label: str) -> str:
    """Map HuggingFace / HerBERT label variants to our entity schema."""
    label = label.upper().strip()
    # Strip IOB prefix
    for prefix in ("B-", "I-", "B_", "I_"):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    mapping = {
        "PERSNAME": "PERSON", "PER": "PERSON", "PERSON": "PERSON",
        "ORGNAME": "ORGANIZATION", "ORG": "ORGANIZATION", "ORGANIZATION": "ORGANIZATION",
        "DATE": "DATE", "TIME": "DATE",
        "LAW": "LAW",
        "ART": "ARTICLE", "ARTICLE": "ARTICLE",
        "CAS": "CASE_ID", "CASE_ID": "CASE_ID",
        "INS": "ORGANIZATION",  # institution → organisation
    }
    return mapping.get(label, label)


def _sliding_window(text: str, window_chars: int = 1000, overlap: int = 100) -> list[tuple[str, int]]:
    """Yield (window_text, char_offset) tuples for long texts."""
    windows: list[tuple[str, int]] = []
    start = 0
    while start < len(text):
        end = min(start + window_chars, len(text))
        windows.append((text[start:end], start))
        if end >= len(text):
            break
        start = end - overlap
    return windows


# ── RegexLegalNER ──────────────────────────────────────────────────────────────


class RegexLegalNER:
    """
    Pure-regex Named Entity Recognition for Polish legal texts.

    No ML dependencies — works without any model download.
    Covers: LAW, ARTICLE, DATE, CASE_ID with high precision.
    Does NOT extract PERSON or ORGANIZATION (use PolishLegalNER for those).
    """

    def extract(self, text: str) -> NERResult:
        """Extract entities from text using regular expressions only."""
        if not text:
            return NERResult(entities=[], text=text)

        entities: list[Entity] = []
        entities.extend(_extract_by_patterns(text, _LAW_PATTERNS, "LAW"))
        entities.extend(_extract_by_patterns(text, _ARTICLE_PATTERNS, "ARTICLE"))
        entities.extend(_extract_by_patterns(text, _DATE_PATTERNS, "DATE"))
        entities.extend(_extract_by_patterns(text, _CASE_ID_PATTERNS, "CASE_ID"))

        entities = _resolve_overlaps(entities)
        entities.sort(key=lambda e: e.start)
        return NERResult(entities=entities, text=text)

    def enrich_chunks(self, chunks: list[dict]) -> list[dict]:
        """Add 'entities' field (and convenience aggregation keys) to each chunk dict."""
        return _enrich_chunks_with_ner(chunks, self)


# ── PolishLegalNER ─────────────────────────────────────────────────────────────


class PolishLegalNER:
    """
    Named Entity Recognition for Polish legal texts using HerBERT.

    Strategy:
    1. Rule-based extraction for LAW, ARTICLE, DATE, CASE_ID (always runs).
    2. Transformer pipeline (HerBERT) for PERSON / ORGANIZATION — loaded lazily.
       - Fine-tuned model at `model_path` is preferred when available.
       - Falls back to base HerBERT (allegro/herbert-base-cased) if not found.
       - If transformers package is not installed, silently omits PERSON/ORG.

    Constructor args:
        model_path:    Path to fine-tuned model directory, or HuggingFace model name.
                       Defaults to 'output/herbert-legal-ner'.
        device:        "cpu" | "cuda" | "mps" (auto-detected if not set).
        min_score:     Minimum confidence for transformer predictions (default 0.70).
    """

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        device: str | int = "cpu",
        min_score: float = MIN_TRANSFORMER_SCORE,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.min_score = min_score
        self._pipeline: Any = None
        self._pipeline_loaded = False
        self._regex_ner = RegexLegalNER()

    # ── Public API ─────────────────────────────────────────────────────────────

    def extract(self, text: str) -> NERResult:
        """
        Extract named entities from a Polish legal text.

        Returns a NERResult with entities sorted by start offset.
        """
        if not text:
            return NERResult(entities=[], text=text)

        # Rule-based pass (always runs)
        regex_result = self._regex_ner.extract(text)
        entities = list(regex_result.entities)

        # Transformer pass for PERSON / ORGANIZATION
        transformer_entities = self._extract_with_transformer(text)
        entities.extend(transformer_entities)

        entities = _resolve_overlaps(entities)
        entities.sort(key=lambda e: e.start)
        return NERResult(entities=entities, text=text)

    def enrich_chunks(self, chunks: list[dict]) -> list[dict]:
        """Add 'entities' and entity-aggregation fields to each chunk dict."""
        return _enrich_chunks_with_ner(chunks, self)

    # ── Transformer helpers ────────────────────────────────────────────────────

    def _load_pipeline(self) -> Any:
        """Lazy-load the HuggingFace NER pipeline. Returns None on failure."""
        if self._pipeline_loaded:
            return self._pipeline
        self._pipeline_loaded = True  # set early to avoid repeated failure attempts

        try:
            from transformers import (
                AutoTokenizer,
                AutoModelForTokenClassification,
                pipeline,
            )
        except ImportError:
            log.info(
                "transformers not installed — PERSON/ORGANIZATION extraction disabled."
            )
            return None

        # Determine which model to load
        ft_path = Path(self.model_path)
        if ft_path.exists() and any(ft_path.iterdir()):
            model_id = str(ft_path)
            log.info("Loading fine-tuned NER model from %s", model_id)
        else:
            # Treat model_path as a HuggingFace model hub ID if it's not a local path
            if "/" in self.model_path or self.model_path.startswith("allegro"):
                model_id = self.model_path
                log.info("Loading NER model from HuggingFace hub: %s", model_id)
            else:
                log.info(
                    "Fine-tuned model not found at %s — "
                    "PERSON/ORGANIZATION extraction disabled (run scripts/train_ner.py first).",
                    self.model_path,
                )
                return None

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModelForTokenClassification.from_pretrained(model_id)
            self._pipeline = pipeline(
                "ner",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
                device=self.device,
            )
            log.info("NER pipeline ready (%s)", model_id)
        except Exception as exc:
            log.warning(
                "NER pipeline load failed (%s): %s — PERSON/ORG disabled.",
                model_id, exc,
            )
            self._pipeline = None

        return self._pipeline

    def _extract_with_transformer(self, text: str) -> list[Entity]:
        """Run the transformer pipeline; return PERSON and ORGANIZATION entities."""
        pipe = self._load_pipeline()
        if pipe is None:
            return []

        entities: list[Entity] = []
        # Process text in windows to respect transformer token limits
        for window_text, offset in _sliding_window(text, window_chars=1000, overlap=100):
            try:
                predictions = pipe(window_text[: MAX_LENGTH * 5])
            except Exception as exc:
                log.warning("NER pipeline prediction failed: %s", exc)
                continue

            for pred in predictions:
                raw_label = pred.get("entity_group", pred.get("entity", ""))
                label = _normalise_transformer_label(raw_label)
                if label not in ("PERSON", "ORGANIZATION"):
                    continue
                score = float(pred.get("score", 0.0))
                if score < self.min_score:
                    continue
                word = pred.get("word", "").replace("##", "").strip()
                if len(word) < 2:
                    continue
                start = pred.get("start", 0) + offset
                end = pred.get("end", start + len(word)) + offset
                entities.append(Entity(
                    text=word,
                    label=label,
                    start=start,
                    end=end,
                    score=round(score, 4),
                ))
        return entities


# ── Shared chunk enrichment ────────────────────────────────────────────────────


def _enrich_chunks_with_ner(
    chunks: list[dict], ner: RegexLegalNER | PolishLegalNER
) -> list[dict]:
    """
    Add NER fields to each chunk dict.

    Added keys:
        entities         — list of entity dicts (text, label, score, start, end)
        entity_laws      — unique LAW surface forms
        entity_articles  — unique ARTICLE references
        entity_cases     — unique CASE_ID strings
        entity_persons   — unique PERSON names
        entity_orgs      — unique ORGANIZATION names
    """
    enriched: list[dict] = []
    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        if not text:
            enriched.append({**chunk, "entities": []})
            continue
        try:
            result = ner.extract(text)
            entities = result.entities
        except Exception as exc:
            log.warning("NER failed for chunk %d (%s[%s]): %s",
                        i, chunk.get("act_id", "?"), chunk.get("chunk_index", "?"), exc)
            entities = []

        chunk_copy = dict(chunk)
        chunk_copy["entities"] = [e.as_dict() for e in entities]
        chunk_copy["entity_laws"] = _unique(e.text for e in entities if e.label == "LAW")
        chunk_copy["entity_articles"] = _unique(e.text for e in entities if e.label == "ARTICLE")
        chunk_copy["entity_cases"] = _unique(e.text for e in entities if e.label == "CASE_ID")
        chunk_copy["entity_persons"] = _unique(e.text for e in entities if e.label == "PERSON")
        chunk_copy["entity_orgs"] = _unique(e.text for e in entities if e.label == "ORGANIZATION")
        enriched.append(chunk_copy)

        if (i + 1) % 500 == 0:
            log.info("NER: enriched %d/%d chunks", i + 1, len(chunks))

    return enriched


def _unique(items) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        s = item.strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


# ── BIO dataset generation (used by scripts/train_ner.py) ─────────────────────


def text_to_bio(text: str, entities: list[Entity]) -> list[tuple[str, str]]:
    """
    Convert text + entity list to BIO-tagged word sequence.

    Returns [(word, BIO-tag), …] using whitespace tokenisation.
    Tags use the short IOB scheme expected by train_ner.py:
        B-LAW / I-LAW / B-ART / I-ART / B-DAT / I-DAT / B-CAS / I-CAS /
        B-PER / I-PER / B-INS / I-INS / O
    """
    _LABEL_TO_IOB = {
        "LAW": "LAW", "ARTICLE": "ART", "DATE": "DAT",
        "CASE_ID": "CAS", "PERSON": "PER", "ORGANIZATION": "INS",
    }
    char_labels = ["O"] * len(text)
    for ent in sorted(entities, key=lambda e: e.start):
        iob_base = _LABEL_TO_IOB.get(ent.label, "")
        if not iob_base:
            continue
        for i in range(ent.start, min(ent.end, len(text))):
            char_labels[i] = f"B-{iob_base}" if i == ent.start else f"I-{iob_base}"

    bio: list[tuple[str, str]] = []
    for m in re.finditer(r"\S+", text):
        word = m.group()
        tag = char_labels[m.start()]
        bio.append((word, tag))
    return bio


def generate_bio_dataset_from_chunks(
    chunks: list[dict],
    output_path: str | None = None,
) -> list[list[tuple[str, str]]]:
    """
    Auto-generate a BIO dataset from chunk dicts using the regex NER.

    Only labels LAW, ARTICLE, DATE, CASE_ID (high-precision regex).
    PERSON / ORGANIZATION are omitted — use manually annotated data for them.

    If output_path is provided, writes a CoNLL-2003 format file.
    """
    ner = RegexLegalNER()
    dataset: list[list[tuple[str, str]]] = []

    for chunk in chunks:
        text = chunk.get("text", "")
        if not text:
            continue
        result = ner.extract(text)
        bio = text_to_bio(text, result.entities)
        if bio:
            dataset.append(bio)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fout:
            for sentence in dataset:
                for word, tag in sentence:
                    fout.write(f"{word} {tag}\n")
                fout.write("\n")
        log.info("Wrote %d BIO sentences to %s", len(dataset), output_path)

    return dataset
