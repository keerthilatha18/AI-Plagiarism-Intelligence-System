"""
tests/test_scoring.py
----------------------
Unit tests for services/scoring.py

Tests:
  - cosine_similarity correctness
  - _split_paragraphs
  - run_scoring_pipeline with mocked Granite + Cloudant
  - Paraphrase flag is created when similarity exceeds threshold
  - No flags when similarity is below threshold
"""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from services.scoring import (
    cosine_similarity,
    _split_paragraphs,
    run_scoring_pipeline,
)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_vectors_return_zero(self):
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([1.0], []) == 0.0

    def test_mismatched_lengths_return_zero(self):
        assert cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_partial_similarity(self):
        sim = cosine_similarity([1.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        assert 0.0 < sim < 1.0


class TestSplitParagraphs:
    def test_splits_on_blank_line(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird."
        parts = _split_paragraphs(text)
        assert len(parts) == 3

    def test_strips_whitespace(self):
        text = "  Hello world.  \n\n  Goodbye.  "
        parts = _split_paragraphs(text)
        assert parts[0] == "Hello world."

    def test_empty_string(self):
        assert _split_paragraphs("") == []

    def test_single_paragraph(self):
        parts = _split_paragraphs("No blank lines here.")
        assert len(parts) == 1


class TestRunScoringPipeline:
    """Integration-style tests using mocked Granite and Cloudant."""

    def _make_submission(self, embedding=None):
        return {
            "submission_id": "sub-001",
            "student_id": "student-1",
            "assignment_id": "asgn-101",
            "instructor_id": "inst-42",
            "raw_text": "This is the first paragraph.\n\nThis is the second paragraph.",
            "embedding_vector": embedding or [0.1] * 768,
            "style_fingerprint": {
                "avg_sentence_len": 8.0,
                "vocab_richness": 0.6,
                "passive_voice_ratio": 0.1,
            },
            "submitted_at": "2024-01-15T10:00:00Z",
        }

    def test_no_flags_when_no_peers(self, mock_granite, mock_cloudant):
        """With no peer submissions, no paraphrase flags should be created."""
        mock_cloudant.query_submissions.return_value = []

        flags = run_scoring_pipeline(
            submission=self._make_submission(),
            cloudant=mock_cloudant,
            granite=mock_granite,
        )

        paraphrase_flags = [f for f in flags if f.flag_type == "paraphrase"]
        assert len(paraphrase_flags) == 0

    def test_paraphrase_flag_created_when_similarity_high(self, mock_granite, mock_cloudant):
        """When a peer has a near-identical embedding, a paraphrase flag should be raised."""
        peer = {
            "submission_id": "sub-002",
            "assignment_id": "asgn-101",
            "embedding_vector": [0.1] * 768,  # Identical to mock return value
            "submitted_at": "2024-01-10T09:00:00Z",
        }
        mock_cloudant.query_submissions.return_value = [peer]

        flags = run_scoring_pipeline(
            submission=self._make_submission(),
            cloudant=mock_cloudant,
            granite=mock_granite,
            paraphrase_threshold=0.82,
        )

        paraphrase_flags = [f for f in flags if f.flag_type == "paraphrase"]
        assert len(paraphrase_flags) >= 1
        # Confidence must be present (ethical guardrail)
        for flag in paraphrase_flags:
            assert 0.0 <= flag.confidence <= 1.0
            assert flag.granite_explanation  # Never a bare boolean

    def test_no_paraphrase_flag_below_threshold(self, mock_granite, mock_cloudant):
        """A peer with a low-similarity embedding should NOT trigger a paraphrase flag."""
        # Return a very different embedding for the peer
        peer_embedding = [0.0] * 384 + [1.0] * 384  # Orthogonal-ish
        mock_cloudant.query_submissions.return_value = [
            {
                "submission_id": "sub-003",
                "assignment_id": "asgn-101",
                "embedding_vector": peer_embedding,
                "submitted_at": "2024-01-12T08:00:00Z",
            }
        ]
        # Granite returns a different vector for this submission
        mock_granite.get_embedding.return_value = [1.0] * 384 + [0.0] * 384

        flags = run_scoring_pipeline(
            submission=self._make_submission(embedding=[1.0] * 384 + [0.0] * 384),
            cloudant=mock_cloudant,
            granite=mock_granite,
            paraphrase_threshold=0.82,
        )

        paraphrase_flags = [f for f in flags if f.flag_type == "paraphrase"]
        assert len(paraphrase_flags) == 0

    def test_style_drift_flag_when_large_deviation(self, mock_granite, mock_cloudant):
        """A submission that differs greatly from the baseline style should be flagged."""
        mock_cloudant.get_baseline.return_value = {
            "instructor_id": "inst-42",
            "assignment_id": "asgn-101",
            "expected_style_profile": {
                "avg_sentence_len": 8.0,
                "vocab_richness": 0.6,
                "passive_voice_ratio": 0.1,
            },
            "threshold_adjustments": {},
        }
        mock_cloudant.query_submissions.return_value = []

        # Submission with very different style (very short sentences, low vocab)
        sub = self._make_submission()
        sub["style_fingerprint"] = {
            "avg_sentence_len": 2.0,   # Was 8.0 — 75% deviation
            "vocab_richness": 0.15,    # Was 0.6 — 75% deviation
            "passive_voice_ratio": 0.9,  # Was 0.1 — 800% deviation
        }

        flags = run_scoring_pipeline(
            submission=sub,
            cloudant=mock_cloudant,
            granite=mock_granite,
            style_drift_threshold=0.40,
        )

        drift_flags = [f for f in flags if f.flag_type == "style_drift"]
        assert len(drift_flags) >= 1
        assert drift_flags[0].confidence > 0.0

    def test_audit_log_written(self, mock_granite, mock_cloudant):
        """Audit log entry must always be appended, even with zero flags."""
        mock_cloudant.query_submissions.return_value = []

        run_scoring_pipeline(
            submission=self._make_submission(),
            cloudant=mock_cloudant,
            granite=mock_granite,
        )

        mock_cloudant.append_audit_entry.assert_called_once()
        call_args = mock_cloudant.append_audit_entry.call_args[0][0]
        assert "submission_id" in call_args
        assert "thresholds_used" in call_args
