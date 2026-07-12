"""
services/stylometrics.py
------------------------
Computes a StyleFingerprint from raw text using spaCy's en_core_web_sm model.

Metrics:
  avg_sentence_len     — mean number of tokens per sentence
  vocab_richness       — type-token ratio (unique tokens / total tokens)
  passive_voice_ratio  — fraction of sentences containing a passive construction
                         (detected via dependency label "nsubjpass" or "auxpass")
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Lazy-load the spaCy model so import doesn't fail during testing without it.
_nlp = None


def _get_nlp():
    global _nlp  # noqa: PLW0603
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning(
                "spaCy model 'en_core_web_sm' not available — "
                "stylometrics will return zero values."
            )
            _nlp = None
    return _nlp


def compute_style_fingerprint(text: str) -> dict[str, float]:
    """
    Analyse `text` and return a style_fingerprint dict.

    Returns a dict with keys: avg_sentence_len, vocab_richness, passive_voice_ratio.
    Returns zeros if text is empty or spaCy is unavailable.
    """
    if not text or not text.strip():
        return {"avg_sentence_len": 0.0, "vocab_richness": 0.0, "passive_voice_ratio": 0.0}

    nlp = _get_nlp()
    if nlp is None:
        return {"avg_sentence_len": 0.0, "vocab_richness": 0.0, "passive_voice_ratio": 0.0}

    doc = nlp(text)
    sentences = list(doc.sents)

    if not sentences:
        return {"avg_sentence_len": 0.0, "vocab_richness": 0.0, "passive_voice_ratio": 0.0}

    # ── Average sentence length (tokens, excluding punctuation) ────────────────
    token_counts = [
        sum(1 for t in sent if not t.is_punct and not t.is_space)
        for sent in sentences
    ]
    avg_sentence_len = sum(token_counts) / len(token_counts)

    # ── Vocabulary richness (type-token ratio) ─────────────────────────────────
    all_tokens = [
        t.lower_ for t in doc if not t.is_punct and not t.is_space and t.is_alpha
    ]
    if all_tokens:
        vocab_richness = len(set(all_tokens)) / len(all_tokens)
    else:
        vocab_richness = 0.0

    # ── Passive voice ratio ────────────────────────────────────────────────────
    # A sentence is considered passive if it contains a token with dep label
    # "nsubjpass" (nominal subject of passive) or "auxpass" (passive auxiliary).
    passive_count = 0
    for sent in sentences:
        has_passive = any(
            tok.dep_ in ("nsubjpass", "auxpass") for tok in sent
        )
        if has_passive:
            passive_count += 1
    passive_voice_ratio = passive_count / len(sentences)

    return {
        "avg_sentence_len": round(avg_sentence_len, 4),
        "vocab_richness": round(vocab_richness, 4),
        "passive_voice_ratio": round(passive_voice_ratio, 4),
    }


def compute_readability_score(text: str) -> float:
    """
    Simple Flesch Reading Ease approximation without external libraries.
    Returns a value in [0, 100].  Higher = easier to read.
    """
    if not text.strip():
        return 0.0

    import re

    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        return 0.0

    words = re.findall(r"\b[a-zA-Z']+\b", text)
    if not words:
        return 0.0

    # Count syllables naively: groups of consecutive vowels per word
    def count_syllables(word: str) -> int:
        word = word.lower()
        count = len(re.findall(r"[aeiouy]+", word))
        return max(count, 1)

    total_syllables = sum(count_syllables(w) for w in words)
    avg_sentence_len = len(words) / len(sentences)
    avg_syllables_per_word = total_syllables / len(words)

    score = 206.835 - (1.015 * avg_sentence_len) - (84.6 * avg_syllables_per_word)
    return round(max(0.0, min(100.0, score)), 2)
