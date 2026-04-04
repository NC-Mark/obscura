"""
PIIEngine — core detection and placeholder assignment.

Key improvements over v6:
  - Parallel chunk processing via ThreadPoolExecutor (3-5x faster on long docs)
  - GPU auto-detection (CUDA → MPS → CPU)
  - Domain-aware stoplist filtering (legal / financial / healthcare / general)
  - User custom stoplist (~/.pii_shield/custom/stoplist.txt)
  - HITL-learned stoplist (~/.pii_shield/learned_stoplist.json)
  - User custom pattern recognizers (~/.pii_shield/custom/entities.json)
  - Named profile support (extra_stoplist + custom_patterns per call)
  - stdnum check-digit validation for ISIN / LEI / IBAN (eliminates FP patterns)
  - Bounded in-memory cache via storage module (no unbounded dict growth)
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import (
    SUPPORTED_ENTITIES, TAG_NAMES, NAMED_ENTITY_TYPES,
    NOISY_PATTERN_TYPES, get_min_score, get_gliner_model, Domain,
)
from ..stoplists import get_stoplist

log = logging.getLogger("pii-shield.engine")
_flog = logging.getLogger("pii-shield.ner")   # detailed NER debug log


def _detect_device() -> str:
    """Auto-detect best available compute device."""
    try:
        import torch
        if torch.cuda.is_available():
            log.info("GPU detected: CUDA")
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            log.info("GPU detected: Apple MPS")
            return "mps"
    except ImportError:
        pass
    return "cpu"


# ── Singleton engine ──────────────────────────────────────────────────────────

class PIIEngine:
    """
    Singleton PII detection engine.

    Usage:
        engine = PIIEngine(domain="financial")
        result = engine.anonymize_text("John Smith at Barclays...")
    """
    _instances: dict[str, "PIIEngine"] = {}

    def __new__(cls, domain: str = "general"):
        key = domain.lower()
        if key not in cls._instances:
            inst = super().__new__(cls)
            inst._initialized = False
            inst._domain = key
            cls._instances[key] = inst
        return cls._instances[key]

    def __init__(self, domain: str = "general"):
        # __new__ handles singleton; __init__ is called each time but we guard
        pass

    # ── Initialisation ────────────────────────────────────────────────────────

    def _ensure_ready(self):
        if self._initialized:
            return

        log.info(f"Initializing PIIEngine (domain={self._domain})...")
        device = _detect_device()
        gliner_model = get_gliner_model()

        from presidio_analyzer.nlp_engine import NlpEngineProvider
        try:
            nlp_engine = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }).create_engine()
        except Exception as e:
            raise RuntimeError(f"SpaCy engine failed: {e}") from e

        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()

        # Remove high-noise built-in recognizers
        _remove = {"DateRecognizer", "SpacyRecognizer"}
        registry.recognizers = [r for r in registry.recognizers
                                 if type(r).__name__ not in _remove]

        # Try GLiNER zero-shot NER; fall back to SpaCy-only
        self._backend = "spacy (en_core_web_sm) [FALLBACK]"
        try:
            from presidio_analyzer.predefined_recognizers import GLiNERRecognizer
            gliner_recognizer = GLiNERRecognizer(
                model_name=gliner_model,
                entity_mapping={
                    "person":       "PERSON",
                    "company":      "ORGANIZATION",
                    "organization": "ORGANIZATION",
                    "location":     "LOCATION",
                    "nationality":  "NRP",
                },
                flat_ner=False,
                multi_label=True,
                map_location=device,
            )
            registry.add_recognizer(gliner_recognizer)
            self._backend = f"gliner ({gliner_model}) on {device}"
            log.info(f"GLiNER loaded: {self._backend}")
        except Exception as e:
            log.warning(f"GLiNER failed ({e}), using SpaCy-only NER")

        self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)

        # Domain-specific + EU recognizers
        try:
            from ..recognizers import register_all_recognizers
            n = register_all_recognizers(self.analyzer, self._domain)
            log.info(f"Registered {n} custom recognizers for domain={self._domain}")
        except Exception as e:
            log.warning(f"Custom recognizers failed: {e}")

        # User custom pattern recognizers from ~/.pii_shield/custom/entities.json
        try:
            from ..custom.loader import load_custom_patterns, register_custom_patterns
            patterns = load_custom_patterns()
            if patterns:
                n = register_custom_patterns(self.analyzer, patterns)
                log.info(f"Registered {n} user custom pattern recognizers")
        except Exception as e:
            log.warning(f"User custom patterns failed: {e}")

        # Build combined stoplist: domain + user custom + HITL-learned
        self._reload_stoplist()

        # Track which profile-level custom patterns have been registered
        self._registered_profile_patterns: set[str] = set()

        self._initialized = True

        from ..storage import cleanup_old_mappings
        cleanup_old_mappings()

        log.info(f"PIIEngine ready — backend={self._backend}, domain={self._domain}, "
                 f"stoplist={len(self._stoplist)} terms")

    def _reload_stoplist(self):
        """Rebuild combined stoplist from domain + custom + learned sources.
        Call after adding new terms without reinitializing the NLP model.
        """
        from ..stoplists import get_stoplist
        from ..custom.loader import get_combined_stoplist
        domain_sl = get_stoplist(self._domain)
        self._stoplist = get_combined_stoplist(domain_sl, self._domain)

    def _ensure_profile_patterns(self, custom_patterns: list):
        """Register per-profile custom patterns that haven't been added yet.
        Uses pattern name as idempotency key.
        """
        if not custom_patterns:
            return
        from ..custom.loader import register_custom_patterns
        new = [p for p in custom_patterns
               if p.get("name") not in self._registered_profile_patterns]
        if new:
            n = register_custom_patterns(self.analyzer, new)
            for p in new:
                self._registered_profile_patterns.add(p.get("name", ""))
            log.info(f"Registered {n} profile-specific custom patterns")

    # ── Chunked analysis (parallel) ───────────────────────────────────────────

    def _analyze_chunked(self, text: str, language: str = "en",
                         chunk_size: int = 4000, overlap: int = 250) -> list:
        """Run analyzer on text chunks in parallel. Returns raw Presidio results."""
        if len(text) <= chunk_size:
            return self.analyzer.analyze(text=text, entities=SUPPORTED_ENTITIES,
                                         language=language)

        # Build chunk list
        chunks: list[tuple[str, int]] = []   # (chunk_text, start_offset)
        pos = 0
        while pos < len(text):
            end = min(pos + chunk_size, len(text))
            if end < len(text):
                ws = text.rfind(' ', pos + chunk_size - overlap, end)
                if ws > pos:
                    end = ws + 1
            chunks.append((text[pos:end], pos))
            pos = end - overlap if end < len(text) else len(text)

        _flog.info(f"Parallel chunked analysis: {len(chunks)} chunks, "
                   f"chunk_size={chunk_size}, overlap={overlap}")

        def _process(args):
            chunk_text, offset = args
            results = self.analyzer.analyze(text=chunk_text,
                                            entities=SUPPORTED_ENTITIES,
                                            language=language)
            for r in results:
                r.start += offset
                r.end += offset
            return results

        all_results = []
        max_workers = min(len(chunks), (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_process, c): c[1] for c in chunks}
            for future in as_completed(futures):
                all_results.extend(future.result())

        # Deduplicate by (start, end, type) — keep highest score
        seen: dict[tuple, float] = {}
        unique = []
        for r in sorted(all_results, key=lambda x: (x.start, -x.score)):
            key = (r.start, r.end, r.entity_type)
            if key not in seen or r.score > seen[key]:
                seen[key] = r.score
                unique.append(r)
        # Re-sort by position after dedup
        unique.sort(key=lambda x: x.start)
        return unique

    # ── Deduplication ─────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(results: list) -> list:
        """Remove overlapping detections, keeping highest-score span."""
        if not results:
            return []
        s = sorted(results, key=lambda r: (r.start, -r.score))
        d = [s[0]]
        for r in s[1:]:
            if r.start >= d[-1].end:
                d.append(r)
            elif r.score > d[-1].score:
                d[-1] = r
        return d

    # ── Boundary cleanup ──────────────────────────────────────────────────────

    @staticmethod
    def _snap_word_boundaries(text: str, entities: list) -> list:
        """Snap entity boundaries to word edges; split cross-newline spans."""
        tlen = len(text)
        _split_buf = []
        for e in entities:
            start, end = e["start"], e["end"]

            if end < tlen and end > 0 and text[end].isalnum() and text[end - 1].isalnum():
                while end < tlen and text[end].isalnum() and text[end] != '\n':
                    end += 1
            if start > 0 and start < end and text[start].isalnum() and text[start - 1].isalnum():
                while start > 0 and text[start - 1].isalnum() and text[start - 1] != '\n':
                    start -= 1

            while end > start and text[end - 1] in '.,;:)]\'" \t\n\r':
                end -= 1
            while start < end and text[start] in '([\'" \t\n\r#/':
                start += 1

            entity_text = text[start:end].strip()
            if len(entity_text) <= 2:
                e["_drop"] = True
            elif '\n' in entity_text:
                e["_drop"] = True
                lines = entity_text.split('\n')
                search_from = start
                for line in lines:
                    stripped = line.strip()
                    if len(stripped) > 2:
                        line_start = text.find(stripped, search_from)
                        if line_start != -1:
                            _split_buf.append({
                                "start": line_start,
                                "end": line_start + len(stripped),
                                "text": stripped,
                                "type": e.get("type", ""),
                                "score": e.get("score", 0),
                            })
                            search_from = line_start + len(stripped)
            elif start < end:
                e["start"] = start
                e["end"] = end
                e["text"] = entity_text

        entities.extend(_split_buf)
        return [e for e in entities if not e.get("_drop")]

    # ── False-positive filtering ──────────────────────────────────────────────

    _SKIP_WORDS = frozenset({
        "the", "a", "an", "of", "and", "or", "for", "in", "to", "by",
        "on", "at", "is", "it", "as", "if", "so", "no", "not", "its",
        "this", "that", "with", "from", "but", "all", "any", "each",
        "such", "than", "into", "upon", "per", "via", "re", "vs",
    })
    _CYRILLIC = str.maketrans(
        'СсАаЕеОоРрХхВвМмТтНн',
        'CcAaEeOoPpXxBbMmTtHh',
    )
    _ARTICLES = ("the ", "a ", "an ")
    _STRUCTURAL_REF = re.compile(
        r'^(schedule|clause|section|article|appendix|annex|exhibit|part|recital)\s+\d',
        re.I,
    )

    def _filter_false_positives(self, entities: list,
                                extra_stoplist: frozenset = frozenset()) -> list:
        """Remove false positives using stoplist, lowercase-single-word rule,
        structural reference rule, frequency filter, and cross-entity confirmation.
        """
        stoplist = self._stoplist | extra_stoplist

        # Collect high-confidence texts for cross-entity confirmation
        confirmed_texts: set[str] = set()
        for e in entities:
            if e.get("score", 0) >= 0.6:
                confirmed_texts.add(e["text"].lower())
                for w in e["text"].split():
                    confirmed_texts.add(w.lower())

        cleaned = []
        for e in entities:
            txt  = e["text"]
            etype = e.get("type", "")
            words = txt.split()
            norm  = txt.lower().strip()

            # Normalise Cyrillic homoglyphs + strip articles
            norm_lat = norm.translate(self._CYRILLIC)
            stripped = norm
            for art in self._ARTICLES:
                if stripped.startswith(art):
                    stripped = stripped[len(art):]
                    break
            stripped_lat = norm_lat
            for art in self._ARTICLES:
                if stripped_lat.startswith(art):
                    stripped_lat = stripped_lat[len(art):]
                    break

            # Rule 0: stoplist match
            if any(v in stoplist for v in (norm, norm_lat, stripped, stripped_lat)):
                _flog.info(f"FP drop (stoplist): '{txt}' ({etype})")
                continue

            # Rule 0b: all meaningful words are in stoplist
            meaningful = [w for w in norm.split() if w not in self._SKIP_WORDS]
            if not meaningful or all(w in stoplist for w in meaningful):
                _flog.info(f"FP drop (all-stoplist): '{txt}' ({etype})")
                continue

            # Rule 1: single lowercase word + named entity type
            if (len(words) == 1 and etype in NAMED_ENTITY_TYPES
                    and txt[0].islower()
                    and txt.lower() not in confirmed_texts):
                _flog.info(f"FP drop (single-lower): '{txt}' ({etype})")
                continue

            # Rule 2: noisy pattern recognizer + stoplist
            if etype in NOISY_PATTERN_TYPES and norm in stoplist:
                _flog.info(f"FP drop (noisy-pattern): '{txt}' ({etype})")
                continue

            # Rule 3: structural reference (Section 3, Clause 4, ...)
            if self._STRUCTURAL_REF.match(norm):
                _flog.info(f"FP drop (structural-ref): '{txt}' ({etype})")
                continue

            # Rule 4: ALL-CAPS short heading in stoplist
            if txt.isupper() and len(txt) <= 12 and norm in stoplist:
                _flog.info(f"FP drop (caps-heading): '{txt}' ({etype})")
                continue

            cleaned.append(e)

        # Rule 5: frequency filter — high-frequency named entities are structural terms.
        # Threshold is domain-adjusted: financial/healthcare docs legitimately repeat
        # client/patient names more than legal docs repeat "Company".
        freq_threshold = 12 if self._domain in ("financial", "healthcare") else 8
        from collections import Counter
        text_counts = Counter(
            e["text"].lower().strip() for e in cleaned
            if e.get("type") in NAMED_ENTITY_TYPES
        )
        high_freq = {t for t, c in text_counts.items() if c > freq_threshold}
        if high_freq:
            before = len(cleaned)
            cleaned = [e for e in cleaned
                       if e["text"].lower().strip() not in high_freq
                       or e.get("type") not in NAMED_ENTITY_TYPES]
            if len(cleaned) < before:
                _flog.info(f"FP drop (freq>{freq_threshold}): {high_freq}")

        return cleaned

    def _clean_boundaries(self, text: str, entities: list,
                          extra_stoplist: frozenset = frozenset()) -> list:
        entities = self._snap_word_boundaries(text, entities)
        entities = self._filter_false_positives(entities, extra_stoplist=extra_stoplist)
        return entities

    # ── stdnum validation ─────────────────────────────────────────────────────

    # Entity types that stdnum can validate by check digit
    _STDNUM_VALIDATORS: dict[str, str] = {
        "ISIN":      "stdnum.isin",
        "LEI":       "stdnum.lei",
        "IBAN_CODE": "stdnum.iban",
        "US_SSN":    "stdnum.us.ssn",
    }

    @staticmethod
    def _stdnum_valid(entity_type: str, text: str) -> bool:
        """Return True if stdnum validates the entity, or True if stdnum unavailable."""
        module_path = PIIEngine._STDNUM_VALIDATORS.get(entity_type)
        if not module_path:
            return True
        try:
            import importlib
            mod = importlib.import_module(module_path)
            result = mod.is_valid(text)
            if not result:
                _flog.info(f"  stdnum INVALID: {entity_type} '{text}' — dropping")
            return result
        except ImportError:
            return True   # stdnum not installed — pass through
        except Exception:
            return True   # validation error — pass through conservatively

    # ── Detect ────────────────────────────────────────────────────────────────

    def detect(self, text: str, language: str = "en",
               profile=None) -> list[dict]:
        """Detect PII in text. Returns list of entity dicts with 'verified' flag.

        Args:
            text:     Input text
            language: Language code (default "en")
            profile:  Optional ProfileContext — adds extra_stoplist and custom_patterns
        """
        self._ensure_ready()

        # Resolve min_score: profile > global config
        min_score = (profile.min_score if profile and profile.min_score is not None
                     else get_min_score())

        # Register any profile-specific custom patterns
        if profile and profile.custom_patterns:
            self._ensure_profile_patterns(profile.custom_patterns)

        t0 = time.time()
        _flog.info(f"--- detect() | len={len(text)} | min_score={min_score} | "
                   f"domain={self._domain} | profile={getattr(profile, 'name', None)} ---")

        raw = self._analyze_chunked(text, language)
        raw = self._deduplicate(raw)
        _flog.info(f"  Raw after dedup: {len(raw)} detections")

        entities = []
        skipped = []
        for r in raw:
            et = text[r.start:r.end]
            rname = getattr(r, 'recognition_metadata', {}).get('recognizer_name', 'unknown')
            if r.score < min_score:
                skipped.append(f"[{rname}] {r.entity_type}({r.score:.2f})='{et}'")
                continue
            # stdnum check-digit validation for financial/identity IDs
            if not self._stdnum_valid(r.entity_type, et):
                _flog.info(f"  stdnum drop: {r.entity_type} '{et}'")
                continue
            entities.append({
                "text": et, "type": r.entity_type,
                "start": r.start, "end": r.end,
                "score": round(r.score, 3),
                "verified": True, "reason": "NER",
                "_recognizer": rname,
            })

        if skipped:
            _flog.info(f"  Skipped (score<{min_score}): {len(skipped)}")

        # Extra stoplist from profile merged at filter time
        extra_sl = profile.extra_stoplist if profile else frozenset()
        entities = self._clean_boundaries(text, entities, extra_stoplist=extra_sl)

        for e in entities:
            e.pop("_recognizer", None)

        _flog.info(f"--- detect() done | {len(entities)} entities in {time.time()-t0:.2f}s ---")
        return entities

    # ── Placeholder assignment ────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'\s+', ' ', text.lower().strip().rstrip('.,;:'))

    def _get_or_create_placeholder(self, etype: str, text: str,
                                   type_counters: dict, seen_exact: dict,
                                   seen_family: dict, mapping: dict,
                                   prefix: str = "") -> str:
        norm = self._normalize(text)
        exact_key = (etype, norm)

        if exact_key in seen_exact:
            return seen_exact[exact_key]

        tag = TAG_NAMES.get(etype, etype)

        # Family match: "Acme" and "Acme Corp." share a family root
        family_key = None
        if len(norm) >= 4:
            for (ft, fn) in seen_family:
                if ft != etype:
                    continue
                if len(fn) >= 4 and (norm in fn or fn in norm):
                    family_key = (ft, fn)
                    break

        if family_key:
            fnum, vcounter = seen_family[family_key]
            vcounter += 1
            seen_family[family_key] = (fnum, vcounter)
            suffix = chr(ord('a') + vcounter - 1) if vcounter <= 26 else str(vcounter)
            placeholder = (f"<{prefix}_{tag}_{fnum}{suffix}>" if prefix
                           else f"<{tag}_{fnum}{suffix}>")
        else:
            type_counters[etype] += 1
            fnum = type_counters[etype]
            placeholder = f"<{prefix}_{tag}_{fnum}>" if prefix else f"<{tag}_{fnum}>"
            seen_family[(etype, norm)] = (fnum, 0)

        seen_exact[exact_key] = placeholder
        mapping[placeholder] = text
        log.info(f"  '{text}' → {placeholder}")
        return placeholder

    def _assign_placeholders(self, confirmed: list, prefix: str = "") -> dict:
        type_counters: dict = defaultdict(int)
        seen_exact: dict = {}
        seen_family: dict = {}
        mapping: dict = {}
        for e in sorted(confirmed, key=lambda x: x["start"]):
            e["placeholder"] = self._get_or_create_placeholder(
                e["type"], e["text"], type_counters, seen_exact, seen_family, mapping, prefix
            )
        return mapping

    # ── HITL override application ─────────────────────────────────────────────

    def _apply_overrides(self, confirmed: list, text: str,
                         overrides_json: str | dict) -> list:
        """Apply user corrections from HITL review (remove FPs, add missed entities)."""
        import json
        try:
            overrides = (json.loads(overrides_json)
                         if isinstance(overrides_json, str) else overrides_json)
        except (json.JSONDecodeError, TypeError):
            return confirmed

        # Remove: by index + all same text+type occurrences
        remove_set = set(overrides.get("remove", []))
        removed_sigs: set[tuple] = set()
        for i, e in enumerate(confirmed):
            if i in remove_set:
                removed_sigs.add((e["type"], e["text"].strip().lower()))
        confirmed = [
            e for i, e in enumerate(confirmed)
            if i not in remove_set
            and (e["type"], e["text"].strip().lower()) not in removed_sigs
        ]

        # Add: find ALL occurrences of the added text
        for addition in overrides.get("add", []):
            add_text = addition.get("text", "").strip()
            add_type = addition.get("type", "PERSON")
            if not add_text:
                continue
            search = 0
            while True:
                pos = text.find(add_text, search)
                if pos < 0:
                    break
                already = any(e["start"] <= pos and pos + len(add_text) <= e["end"]
                              for e in confirmed)
                if not already:
                    confirmed.append({
                        "type": add_type, "text": add_text,
                        "start": pos, "end": pos + len(add_text),
                        "score": 1.0, "verified": True, "reason": "user_added",
                    })
                search = pos + len(add_text)

        return sorted(confirmed, key=lambda x: x["start"])
