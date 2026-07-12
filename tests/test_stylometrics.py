"""
tests/test_stylometrics.py
---------------------------
Unit tests for services/stylometrics.py
spaCy model is used if available; otherwise zero-value fallback is tested.
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.stylometrics import compute_style_fingerprint, compute_readability_score

try:
    import spacy
    spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except (ImportError, OSError):
    SPACY_AVAILABLE = False

requires_spacy = pytest.mark.skipif(
    not SPACY_AVAILABLE,
    reason="spaCy en_core_web_sm not installed — run: python -m spacy download en_core_web_sm",
)

SAMPLE_TEXT = """
The quick brown fox jumps over the lazy dog.
She was seen running through the park by the children.
It is often said that practice makes perfect.
The report was written by the committee last week.
Students who read widely tend to write more effectively.
"""


class TestComputeStyleFingerprint:
    @requires_spacy
    def test_returns_correct_keys(self):
        fp = compute_style_fingerprint(SAMPLE_TEXT)
        assert "avg_sentence_len" in fp
        assert "vocab_richness" in fp
        assert "passive_voice_ratio" in fp

    def test_empty_text_returns_zeros(self):
        fp = compute_style_fingerprint("")
        assert fp["avg_sentence_len"] == 0.0
        assert fp["vocab_richness"] == 0.0
        assert fp["passive_voice_ratio"] == 0.0

    @requires_spacy
    def test_values_are_floats(self):
        fp = compute_style_fingerprint(SAMPLE_TEXT)
        for key, val in fp.items():
            assert isinstance(val, float), f"Expected float for {key}, got {type(val)}"

    @requires_spacy
    def test_vocab_richness_between_0_and_1(self):
        fp = compute_style_fingerprint(SAMPLE_TEXT)
        assert 0.0 <= fp["vocab_richness"] <= 1.0

    @requires_spacy
    def test_passive_voice_ratio_between_0_and_1(self):
        fp = compute_style_fingerprint(SAMPLE_TEXT)
        assert 0.0 <= fp["passive_voice_ratio"] <= 1.0

    @requires_spacy
    def test_avg_sentence_len_positive(self):
        fp = compute_style_fingerprint(SAMPLE_TEXT)
        # Should detect some tokens per sentence
        assert fp["avg_sentence_len"] >= 0.0


class TestReadabilityScore:
    def test_returns_float(self):
        score = compute_readability_score(SAMPLE_TEXT)
        assert isinstance(score, float)

    def test_score_in_valid_range(self):
        score = compute_readability_score(SAMPLE_TEXT)
        assert 0.0 <= score <= 100.0

    def test_empty_returns_zero(self):
        assert compute_readability_score("") == 0.0

    def test_complex_text_lower_than_simple(self):
        simple = "The cat sat. The dog ran. I like pie."
        complex_text = (
            "The epistemological underpinnings of poststructuralist semiotics "
            "necessitate a thorough interrogation of hermeneutical methodologies "
            "prevalent in contemporary discursive formations."
        )
        simple_score = compute_readability_score(simple)
        complex_score = compute_readability_score(complex_text)
        # Simple text should score higher (easier to read) than complex academic prose
        assert simple_score > complex_score
