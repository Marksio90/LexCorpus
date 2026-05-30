"""
classify_eurovoc.py — EuroVoc multi-label classification for Polish legal documents.

Assigns EuroVoc thesaurus descriptors to text chunks using a hybrid approach:

1. Pattern-based classifier (always available): keyword matching against a curated
   dictionary of ~200 Polish legal terms mapped to EuroVoc domain descriptors.
2. Model-based classifier (optional): fine-tuned allegro/herbert-base-cased model,
   loaded only when --use-model is passed and the model is available.

EuroVoc is the multilingual thesaurus used by the EU Publications Office:
  https://eur-lex.europa.eu/browse/eurovoc.html

Usage:
    python scripts/classify_eurovoc.py --input data/processed/chunks.jsonl \\
                                       --output data/processed/chunks_eurovoc.jsonl
    python scripts/classify_eurovoc.py --input data/processed/chunks.jsonl \\
                                       --output data/processed/chunks_eurovoc.jsonl \\
                                       --use-model
    python scripts/classify_eurovoc.py --input data/processed/chunks.jsonl \\
                                       --output data/processed/chunks_eurovoc.jsonl \\
                                       --min-confidence 0.3
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── EuroVoc taxonomy ──────────────────────────────────────────────────────────
# Maps Polish legal domains to EuroVoc concept IDs and matching keywords.
# EuroVoc concept IDs from: https://op.europa.eu/en/web/eu-vocabularies/eurovoc
#
# Strategy: each domain has primary keywords (high weight) and secondary keywords
# (lower weight). Confidence is proportional to the fraction of matched keywords,
# capped at 1.0.

EUROVOC_TAXONOMY: dict[str, dict] = {
    "prawo pracy": {
        "eurovoc_ids": ["1252", "4", "5543", "1406"],
        "labels": ["zatrudnienie", "stosunek pracy", "pracownik", "prawo pracy"],
        "keywords_primary": [
            "pracodawca", "pracownik", "umowa o pracę", "stosunek pracy",
            "Kodeks pracy", "wynagrodzenie za pracę",
        ],
        "keywords_secondary": [
            "wypowiedzenie", "wynagrodzenie", "urlop", "zwolnienie", "praca",
            "zatrudnienie", "urlop wypoczynkowy", "nadgodziny", "premia",
            "regulamin pracy", "regulamin wynagradzania", "zakaz konkurencji",
            "mobbing", "dyskryminacja w zatrudnieniu", "świadectwo pracy",
            "zwolnienie grupowe", "odprawa", "czas pracy", "zmianowy",
        ],
    },
    "prawo podatkowe": {
        "eurovoc_ids": ["861", "4258", "1015", "2300"],
        "labels": ["podatek", "prawo podatkowe", "zobowiązanie podatkowe"],
        "keywords_primary": [
            "VAT", "PIT", "CIT", "podatek", "ordynacja podatkowa",
            "zobowiązanie podatkowe", "urząd skarbowy",
        ],
        "keywords_secondary": [
            "deklaracja podatkowa", "faktura", "faktura VAT", "podstawa opodatkowania",
            "zwolnienie podatkowe", "stawka podatku", "podatek dochodowy",
            "podatek od towarów i usług", "podatek akcyzowy", "cło",
            "interpretacja podatkowa", "KIS", "izba skarbowa", "postępowanie podatkowe",
            "zaległość podatkowa", "nadpłata", "korekta deklaracji",
        ],
    },
    "prawo handlowe": {
        "eurovoc_ids": ["1449", "441", "3086", "1137"],
        "labels": ["prawo handlowe", "spółka", "działalność gospodarcza"],
        "keywords_primary": [
            "spółka", "kodeks spółek handlowych", "KRS",
            "rejestr przedsiębiorców", "udziałowiec", "akcjonariusz",
        ],
        "keywords_secondary": [
            "akcja", "zarząd", "rada nadzorcza", "walne zgromadzenie",
            "przekształcenie", "fuzja", "podział spółki", "upadłość",
            "restrukturyzacja", "likwidacja", "prokura", "jednoosobowa spółka",
            "spółka z o.o.", "spółka akcyjna", "spółka jawna", "spółka komandytowa",
            "dywidenda", "kapitał zakładowy", "aport",
        ],
    },
    "zamówienia publiczne": {
        "eurovoc_ids": ["6094", "3499"],
        "labels": ["zamówienia publiczne", "przetarg"],
        "keywords_primary": [
            "zamówienie publiczne", "przetarg", "zamawiający", "wykonawca",
            "PZP", "ustawa Prawo zamówień publicznych",
        ],
        "keywords_secondary": [
            "oferta", "SIWZ", "specyfikacja warunków zamówienia", "KIO",
            "Krajowa Izba Odwoławcza", "odwołanie od przetargu", "wykluczenie wykonawcy",
            "kryterium oceny ofert", "przetarg nieograniczony", "przetarg ograniczony",
            "negocjacje z ogłoszeniem", "zamówienie z wolnej ręki", "umowa w sprawie zamówienia",
            "protokół postępowania", "wartość szacunkowa",
        ],
    },
    "prawo administracyjne": {
        "eurovoc_ids": ["6", "920", "3051", "1044"],
        "labels": ["prawo administracyjne", "postępowanie administracyjne"],
        "keywords_primary": [
            "decyzja administracyjna", "KPA", "kodeks postępowania administracyjnego",
            "NSA", "WSA", "organ administracji",
        ],
        "keywords_secondary": [
            "postępowanie administracyjne", "odwołanie", "skarga do WSA",
            "skarga kasacyjna", "uchylenie decyzji", "zmiana decyzji",
            "decyzja ostateczna", "postanowienie", "zażalenie", "bezczynność organu",
            "przewlekłość postępowania", "wniosek o ponowne rozpatrzenie",
            "administracja publiczna", "samorząd", "gmina", "powiat",
        ],
    },
    "prawo karne": {
        "eurovoc_ids": ["1300", "1025", "3520", "1486"],
        "labels": ["prawo karne", "postępowanie karne"],
        "keywords_primary": [
            "przestępstwo", "kodeks karny", "KK", "prokurator",
            "Kodeks postępowania karnego", "KPK",
        ],
        "keywords_secondary": [
            "kara", "skazanie", "oskarżony", "wyrok skazujący", "areszt", "więzienie",
            "kara pozbawienia wolności", "warunkowe zawieszenie", "grzywna karna",
            "recydywa", "pomocnictwo", "podżeganie", "usiłowanie", "nieumyślność",
            "umyślność", "ofiara", "pokrzywdzony", "oskarżyciel posiłkowy",
            "akт oskarżenia", "umorzenie postępowania karnego",
        ],
    },
    "prawo cywilne": {
        "eurovoc_ids": ["891", "3545", "1060"],
        "labels": ["prawo cywilne", "zobowiązania"],
        "keywords_primary": [
            "kodeks cywilny", "KC", "umowa", "zobowiązanie",
            "odpowiedzialność cywilna", "odszkodowanie",
        ],
        "keywords_secondary": [
            "własność", "dziedziczenie", "testament", "wierzytelność", "dług",
            "rękojmia", "gwarancja", "przedawnienie", "kara umowna", "zadatek",
            "zaliczka", "umowa sprzedaży", "umowa najmu", "umowa dzierżawy",
            "umowa zlecenia", "umowa o dzieło", "darowizna", "pożyczka",
            "hipoteka", "zastaw", "służebność", "zasiedzenie",
        ],
    },
    "prawo konstytucyjne": {
        "eurovoc_ids": ["2243", "824", "2344"],
        "labels": ["prawo konstytucyjne", "prawa podstawowe"],
        "keywords_primary": [
            "Konstytucja", "Konstytucja RP", "Trybunał Konstytucyjny",
            "prawa podstawowe", "Sejm", "Senat",
        ],
        "keywords_secondary": [
            "wolność", "równość wobec prawa", "Rzeczpospolita", "godność człowieka",
            "skarga konstytucyjna", "niezgodność z Konstytucją", "przepis niekonstytucyjny",
            "Prezydent RP", "Rada Ministrów", "Prezes Rady Ministrów",
            "RPO", "Rzecznik Praw Obywatelskich", "Naczelny Sąd Administracyjny",
            "Sąd Najwyższy", "niezawisłość sądu",
        ],
    },
    "prawo UE": {
        "eurovoc_ids": ["5765", "3589", "3028"],
        "labels": ["prawo Unii Europejskiej", "transpozycja prawa UE"],
        "keywords_primary": [
            "dyrektywa", "rozporządzenie UE", "Trybunał Sprawiedliwości UE",
            "TSUE", "implementacja dyrektywy",
        ],
        "keywords_secondary": [
            "transpozycja", "acquis communautaire", "Unia Europejska",
            "prawo unijne", "traktat", "TFUE", "TUE", "Karta Praw Podstawowych UE",
            "Europejski Trybunał Praw Człowieka", "ETPC", "EKPC",
            "zasada pierwszeństwa prawa UE", "skutek bezpośredni",
            "naruszenie prawa UE", "odpowiedzialność odszkodowawcza państwa",
        ],
    },
    "ochrona środowiska": {
        "eurovoc_ids": ["2825", "3821", "1115"],
        "labels": ["ochrona środowiska", "prawo ochrony środowiska"],
        "keywords_primary": [
            "ochrona środowiska", "ustawa o ochronie środowiska",
            "emisja zanieczyszczeń", "odpady", "gospodarka odpadami",
        ],
        "keywords_secondary": [
            "zanieczyszczenie", "ochrona przyrody", "klimat", "CO2",
            "gospodarka wodno-ściekowa", "woda", "powietrze", "gleba",
            "hałas", "promieniowanie", "Inspekcja Ochrony Środowiska",
            "opłata środowiskowa", "ocena oddziaływania na środowisko",
            "OOŚ", "pozwolenie zintegrowane", "IPPC",
        ],
    },
    "prawo finansowe": {
        "eurovoc_ids": ["2440", "310", "3829"],
        "labels": ["prawo finansowe", "rynek finansowy"],
        "keywords_primary": [
            "prawo bankowe", "ustawa o rachunkowości", "KNF",
            "Komisja Nadzoru Finansowego", "NBP",
        ],
        "keywords_secondary": [
            "bank", "kredyt", "pożyczka bankowa", "depozyt", "rachunek bankowy",
            "ubezpieczenie", "rynek kapitałowy", "giełda", "GPW",
            "instrument finansowy", "fundusz inwestycyjny", "fundusz emerytalny",
            "OFE", "ZUS", "ubezpieczenie społeczne", "składka",
        ],
    },
    "prawo nieruchomości": {
        "eurovoc_ids": ["3199", "4786"],
        "labels": ["prawo nieruchomości", "gospodarka nieruchomościami"],
        "keywords_primary": [
            "nieruchomość", "ustawa o gospodarce nieruchomościami",
            "księga wieczysta", "własność nieruchomości",
        ],
        "keywords_secondary": [
            "grunt", "działka", "budynek", "lokal", "mieszkanie",
            "użytkowanie wieczyste", "zarząd nieruchomością", "wspólnota mieszkaniowa",
            "spółdzielnia mieszkaniowa", "najem lokalu", "eksmisja",
            "wywłaszczenie", "odszkodowanie za wywłaszczenie", "plan zagospodarowania",
            "miejscowy plan zagospodarowania przestrzennego", "MPZP",
        ],
    },
    "prawo rodzinne": {
        "eurovoc_ids": ["3020", "822"],
        "labels": ["prawo rodzinne", "kodeks rodzinny"],
        "keywords_primary": [
            "Kodeks rodzinny i opiekuńczy", "KRO", "małżeństwo", "władza rodzicielska",
        ],
        "keywords_secondary": [
            "rozwód", "separacja", "alimenty", "opieka nad dzieckiem",
            "przysposobienie", "adopcja", "intercyza", "majątek wspólny",
            "rozdzielność majątkowa", "ubezwłasnowolnienie", "kuratela",
            "opieka prawna", "rodzina zastępcza",
        ],
    },
    "prawo własności intelektualnej": {
        "eurovoc_ids": ["3878", "2349"],
        "labels": ["prawo własności intelektualnej", "prawo autorskie"],
        "keywords_primary": [
            "prawo autorskie", "ustawa o prawie autorskim", "własność intelektualna",
            "patent", "znak towarowy",
        ],
        "keywords_secondary": [
            "utwór", "prawa pokrewne", "licencja", "dozwolony użytek",
            "ochrona praw autorskich", "naruszenie praw autorskich",
            "wynalazek", "wzór użytkowy", "wzór przemysłowy",
            "Urząd Patentowy RP", "EUIPO", "EPO",
        ],
    },
    "prawo pracy zbiorowe": {
        "eurovoc_ids": ["3552", "2352"],
        "labels": ["prawo pracy zbiorowe", "związki zawodowe"],
        "keywords_primary": [
            "związek zawodowy", "układ zbiorowy pracy", "strajk",
            "rada pracowników",
        ],
        "keywords_secondary": [
            "zbiorowy spór pracy", "mediacja", "arbitraż pracowniczy",
            "organizacja pracodawców", "porozumienie zbiorowe",
            "zakładowy układ zbiorowy", "ponadzakładowy układ zbiorowy",
        ],
    },
}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class EuroVocLabel:
    domain: str
    eurovoc_ids: list[str]
    confidence: float
    matched_keywords: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


# ── Pattern-based classifier ─────────────────────────────────────────────────

class PatternClassifier:
    """
    Keyword-based EuroVoc classifier using the EUROVOC_TAXONOMY dictionary.

    Scoring:
    - Each primary keyword match contributes 2.0 / (total primary keywords) to score
    - Each secondary keyword match contributes 1.0 / (total secondary keywords) to score
    - Raw scores are normalised to [0, 1] per domain
    - A domain is returned only if score >= min_confidence

    The classifier is case-insensitive and uses whole-word matching to avoid
    false positives (e.g. "KK" should not match inside "UOKIK").
    """

    def __init__(self) -> None:
        # Pre-compile regex patterns for each domain to avoid recompilation in classify()
        self._patterns: dict[str, list[tuple[re.Pattern, float]]] = {}
        for domain, spec in EUROVOC_TAXONOMY.items():
            patterns = []
            primary = spec.get("keywords_primary", [])
            secondary = spec.get("keywords_secondary", [])
            n_primary = len(primary) or 1
            n_secondary = len(secondary) or 1

            for kw in primary:
                weight = 2.0 / n_primary
                patterns.append((self._compile_keyword(kw), weight))
            for kw in secondary:
                weight = 1.0 / n_secondary
                patterns.append((self._compile_keyword(kw), weight))

            self._patterns[domain] = patterns

        # Max possible score per domain (sum of all weights)
        self._max_scores: dict[str, float] = {
            domain: sum(w for _, w in patterns)
            for domain, patterns in self._patterns.items()
        }

    @staticmethod
    def _compile_keyword(kw: str) -> re.Pattern:
        """
        Compile a keyword to a case-insensitive regex that handles Polish inflection.

        Single-word keywords use a prefix stem strategy: we strip the last 3 characters
        (typically a Polish inflectional suffix like -ego, -emu, -owi, -iem, -ach) and
        match that stem at a word boundary. This catches forms like:
          kara → kar(a/ę/ze/y/…)
          oskarżony → oskarżon(ego/emu/ych/…)
          skazanie → skazan(ia/iu/iem/…)

        Multi-word keywords (phrases) keep whole-phrase matching to avoid false positives:
          e.g. "kara pozbawienia wolności" stays as-is.

        All patterns are preceded by a non-word-character lookbehind so we don't
        match inside longer words.
        """
        words = kw.split()
        if len(words) == 1 and len(kw) > 5:
            # Single word: match stem (first N-3 chars) to catch inflected forms.
            # Minimum stem length is 3 to avoid matching too broadly.
            stem_len = max(3, len(kw) - 3)
            stem = re.escape(kw[:stem_len])
            return re.compile(r"(?<!\w)" + stem + r"\w{0,5}", re.IGNORECASE | re.UNICODE)
        else:
            # Multi-word phrase: exact match with leading non-word-char guard.
            escaped = re.escape(kw)
            return re.compile(r"(?<!\w)" + escaped + r"(?!\w)", re.IGNORECASE | re.UNICODE)

    def classify(
        self,
        text: str,
        title: str = "",
        min_confidence: float = 0.1,
    ) -> list[EuroVocLabel]:
        # Combine title with text — title often has the best signal
        full_text = (title + " " + text) if title else text

        labels: list[EuroVocLabel] = []
        for domain, patterns in self._patterns.items():
            raw_score = 0.0
            matched: list[str] = []
            all_keywords = (
                EUROVOC_TAXONOMY[domain].get("keywords_primary", [])
                + EUROVOC_TAXONOMY[domain].get("keywords_secondary", [])
            )
            # We track matched original keywords (not regex pattern strings)
            pattern_kw_pairs = list(zip(patterns, all_keywords))
            for (pattern, weight), kw in pattern_kw_pairs:
                if pattern.search(full_text):
                    raw_score += weight
                    matched.append(kw)

            if not matched:
                continue

            max_score = self._max_scores[domain]
            confidence = round(min(raw_score / max_score, 1.0), 4) if max_score > 0 else 0.0

            if confidence >= min_confidence:
                labels.append(EuroVocLabel(
                    domain=domain,
                    eurovoc_ids=EUROVOC_TAXONOMY[domain]["eurovoc_ids"],
                    confidence=confidence,
                    matched_keywords=matched,
                ))

        # Sort by descending confidence
        labels.sort(key=lambda x: x.confidence, reverse=True)
        return labels


# ── Model-based classifier (optional) ────────────────────────────────────────

class ModelClassifier:
    """
    Optional transformer-based EuroVoc classifier using HerBERT.

    Uses zero-shot or fine-tuned allegro/herbert-base-cased for multi-label
    classification. Falls back gracefully if the model is unavailable.

    Note: without a fine-tuned checkpoint this uses sentence embeddings
    compared against class label embeddings (a "label embedding" approach),
    which gives reasonable zero-shot quality on Polish legal text.
    """

    # EuroVoc domain descriptions (for zero-shot label embedding matching)
    DOMAIN_DESCRIPTIONS = {
        "prawo pracy": "stosunek pracy, pracownicy, pracodawcy, zatrudnienie, Kodeks pracy",
        "prawo podatkowe": "podatki, VAT, PIT, CIT, zobowiązania podatkowe, ordynacja podatkowa",
        "prawo handlowe": "spółki handlowe, KRS, akcje, udziały, fuzje i przejęcia",
        "zamówienia publiczne": "przetargi, zamówienia publiczne, KIO, oferty, zamawiający",
        "prawo administracyjne": "decyzje administracyjne, KPA, NSA, WSA, organy administracji",
        "prawo karne": "przestępstwa, kary, skazanie, prokuratura, kodeks karny",
        "prawo cywilne": "umowy, zobowiązania, odszkodowania, własność, kodeks cywilny",
        "prawo konstytucyjne": "Konstytucja, Trybunał Konstytucyjny, prawa podstawowe",
        "prawo UE": "dyrektywy UE, rozporządzenia UE, TSUE, transpozycja prawa europejskiego",
        "ochrona środowiska": "środowisko, emisje, odpady, zanieczyszczenia, natura",
        "prawo finansowe": "banki, kredyty, ubezpieczenia, rynek finansowy, KNF",
        "prawo nieruchomości": "nieruchomości, grunty, księgi wieczyste, użytkowanie wieczyste",
        "prawo rodzinne": "małżeństwo, rozwód, alimenty, władza rodzicielska, kodeks rodzinny",
        "prawo własności intelektualnej": "prawo autorskie, patenty, znaki towarowe, licencje",
        "prawo pracy zbiorowe": "związki zawodowe, układy zbiorowe, strajki, rady pracowników",
    }

    def __init__(self, model_path: str | None = None) -> None:
        self._model_name = model_path or "allegro/herbert-base-cased"
        self._model = None
        self._tokenizer = None
        self._label_embeddings: dict[str, list[float]] | None = None
        self._loaded = False

    def _load(self) -> bool:
        """Lazy-load the model. Returns True if successful."""
        if self._loaded:
            return self._model is not None
        self._loaded = True
        try:
            from sentence_transformers import SentenceTransformer
            log.info("Loading model classifier '%s' …", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            # Pre-compute label embeddings
            domains = list(self.DOMAIN_DESCRIPTIONS.keys())
            descriptions = [self.DOMAIN_DESCRIPTIONS[d] for d in domains]
            import numpy as np
            label_vecs = self._model.encode(
                descriptions, normalize_embeddings=True, convert_to_numpy=True
            )
            self._label_embeddings = {d: label_vecs[i].tolist() for i, d in enumerate(domains)}
            log.info("Model classifier loaded with %d domain label embeddings", len(domains))
            return True
        except Exception as exc:
            log.warning("Model classifier unavailable: %s — falling back to pattern-only", exc)
            self._model = None
            return False

    def classify(
        self,
        text: str,
        title: str = "",
        min_confidence: float = 0.2,
    ) -> list[EuroVocLabel]:
        if not self._load() or self._model is None:
            return []

        import numpy as np

        full_text = (title + " " + text[:512]) if title else text[:512]
        try:
            query_vec = self._model.encode(
                full_text, normalize_embeddings=True, convert_to_numpy=True
            )
        except Exception as exc:
            log.warning("Encoding failed: %s", exc)
            return []

        labels: list[EuroVocLabel] = []
        for domain, label_vec in self._label_embeddings.items():  # type: ignore[union-attr]
            cos_sim = float(np.dot(query_vec, np.array(label_vec)))
            # Cosine similarity for sentence embeddings is typically in [0.1, 0.95].
            # Normalise to [0, 1] using a soft min of 0.0
            confidence = round(max(0.0, cos_sim), 4)
            if confidence >= min_confidence:
                labels.append(EuroVocLabel(
                    domain=domain,
                    eurovoc_ids=EUROVOC_TAXONOMY.get(domain, {}).get("eurovoc_ids", []),
                    confidence=confidence,
                    matched_keywords=[],
                ))

        labels.sort(key=lambda x: x.confidence, reverse=True)
        return labels


# ── EuroVocClassifier (public API) ────────────────────────────────────────────

class EuroVocClassifier:
    """
    Hybrid EuroVoc multi-label classifier for Polish legal documents.

    When use_model=True, fuses pattern scores and model scores using a weighted
    average (60% model, 40% pattern) to get the final confidence. This typically
    outperforms either approach alone.

    When use_model=False (default), only the pattern-based classifier runs —
    no GPU or internet access required.
    """

    def __init__(
        self,
        use_model: bool = False,
        model_path: str | None = None,
        min_confidence: float = 0.1,
        max_labels: int = 5,
    ) -> None:
        self.min_confidence = min_confidence
        self.max_labels = max_labels
        self._pattern_clf = PatternClassifier()
        self._model_clf: ModelClassifier | None = None
        if use_model:
            self._model_clf = ModelClassifier(model_path=model_path)

    def classify(self, text: str, title: str = "") -> list[EuroVocLabel]:
        """
        Return top EuroVoc descriptors for a text chunk, sorted by confidence.

        When both classifiers are active their scores are fused per domain.
        Returns at most max_labels labels with confidence >= min_confidence.
        """
        pattern_labels = self._pattern_clf.classify(text, title, min_confidence=0.0)

        if self._model_clf is None:
            results = [l for l in pattern_labels if l.confidence >= self.min_confidence]
            return results[: self.max_labels]

        # Model-based labels
        model_labels = self._model_clf.classify(text, title, min_confidence=0.0)

        # Fuse: build a dict of domain → score from each classifier
        pattern_map = {l.domain: l for l in pattern_labels}
        model_map = {l.domain: l for l in model_labels}
        all_domains = set(pattern_map) | set(model_map)

        fused: list[EuroVocLabel] = []
        for domain in all_domains:
            p_score = pattern_map[domain].confidence if domain in pattern_map else 0.0
            m_score = model_map[domain].confidence if domain in model_map else 0.0
            # Weighted fusion — model gets more weight when present
            fused_score = round(0.6 * m_score + 0.4 * p_score, 4)
            if fused_score < self.min_confidence:
                continue
            # Prefer matched_keywords from the pattern classifier
            matched = pattern_map[domain].matched_keywords if domain in pattern_map else []
            fused.append(EuroVocLabel(
                domain=domain,
                eurovoc_ids=EUROVOC_TAXONOMY.get(domain, {}).get("eurovoc_ids", []),
                confidence=fused_score,
                matched_keywords=matched,
            ))

        fused.sort(key=lambda x: x.confidence, reverse=True)
        return fused[: self.max_labels]

    def classify_batch(
        self,
        chunks: list[dict],
        batch_size: int = 32,
    ) -> list[dict]:
        """
        Enrich each chunk dict with a 'eurovoc_labels' field (list of domain strings)
        and 'eurovoc_details' (list of dicts with full label info).

        Returns a new list of chunk dicts — originals are not mutated.
        """
        enriched = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            for chunk in batch:
                text = chunk.get("text", "")
                title = chunk.get("title", "")
                labels = self.classify(text, title)
                new_chunk = dict(chunk)
                new_chunk["eurovoc_labels"] = [l.domain for l in labels]
                new_chunk["eurovoc_details"] = [l.as_dict() for l in labels]
                enriched.append(new_chunk)
            log.info(
                "EuroVoc classified %d/%d chunks …",
                min(i + batch_size, len(chunks)),
                len(chunks),
            )
        return enriched


# ── Streaming helpers ─────────────────────────────────────────────────────────

def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                log.warning("Skipping invalid JSON at line %d", lineno)


def process_file(
    input_path: Path,
    output_path: Path,
    classifier: EuroVocClassifier,
    max_chunks: int | None = None,
) -> int:
    """Stream-process a JSONL file, enriching each chunk in place."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with output_path.open("w", encoding="utf-8") as out_fh:
        for chunk in _iter_jsonl(input_path):
            if max_chunks is not None and total >= max_chunks:
                break
            text = chunk.get("text", "")
            title = chunk.get("title", "")
            labels = classifier.classify(text, title)
            chunk["eurovoc_labels"] = [l.domain for l in labels]
            chunk["eurovoc_details"] = [l.as_dict() for l in labels]
            out_fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            total += 1
            if total % 1000 == 0:
                log.info("Processed %d chunks …", total)
    return total


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="EuroVoc multi-label classification for Polish legal chunks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/chunks.jsonl"),
        help="Input JSONL file (chunks)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/chunks_eurovoc.jsonl"),
        help="Output JSONL file (chunks + eurovoc_labels)",
    )
    parser.add_argument(
        "--use-model",
        action="store_true",
        default=False,
        help="Enable model-based classifier (allegro/herbert-base-cased). Requires sentence-transformers.",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Path or HuggingFace id for the sentence-transformer model (default: allegro/herbert-base-cased)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.1,
        help="Minimum confidence threshold for including a label",
    )
    parser.add_argument(
        "--max-labels",
        type=int,
        default=5,
        help="Maximum EuroVoc labels per chunk",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Process at most N chunks (useful for testing)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        sys.exit(1)

    log.info(
        "Initialising EuroVoc classifier (use_model=%s, min_confidence=%.2f, max_labels=%d)",
        args.use_model,
        args.min_confidence,
        args.max_labels,
    )
    classifier = EuroVocClassifier(
        use_model=args.use_model,
        model_path=args.model_path,
        min_confidence=args.min_confidence,
        max_labels=args.max_labels,
    )

    log.info("Processing %s → %s …", args.input, args.output)
    n = process_file(args.input, args.output, classifier, max_chunks=args.max_chunks)
    log.info("Done. Classified %d chunks. Output: %s", n, args.output)


if __name__ == "__main__":
    main()
