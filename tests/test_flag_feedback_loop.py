"""
tests/test_flag_feedback_loop.py
---------------------------------
Tests for the adaptive threshold nudging logic in services/scoring.py

Covers:
  - "dismissed" decision raises the instructor's threshold for that flag type
  - "confirmed" decision lowers it
  - Unknown flag type is ignored (grade_mismatch has no threshold)
  - Nudges accumulate correctly across multiple decisions
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from services.scoring import (
    apply_flag_decision_feedback,
    THRESHOLD_NUDGE_AMOUNT,
)


def _make_flag(flag_type: str = "paraphrase") -> dict:
    return {
        "flag_id": "flag-001",
        "submission_id": "sub-001",
        "flag_type": flag_type,
        "confidence": 0.85,
        "granite_explanation": "Test explanation.",
        "reviewed": False,
        "instructor_decision": None,
    }


def _make_cloudant_mock(existing_adjustment: float = 0.0, flag_type: str = "paraphrase"):
    """Return a mock CloudantService wired with a baseline."""
    from unittest.mock import MagicMock

    cloudant = MagicMock()
    cloudant.get_submission.return_value = {
        "submission_id": "sub-001",
        "instructor_id": "inst-1",
        "assignment_id": "asgn-1",
    }
    cloudant.get_baseline.return_value = {
        "instructor_id": "inst-1",
        "assignment_id": "asgn-1",
        "threshold_adjustments": {
            "paraphrase": existing_adjustment,
            "ai_generated": 0.0,
            "style_drift": 0.0,
        },
    }
    return cloudant


class TestApplyFlagDecisionFeedback:
    def test_dismissed_raises_threshold(self):
        """Dismissing a flag should increase the paraphrase adjustment."""
        cloudant = _make_cloudant_mock(existing_adjustment=0.0)

        apply_flag_decision_feedback(
            flag=_make_flag("paraphrase"),
            decision="dismissed",
            cloudant=cloudant,
        )

        cloudant.upsert_baseline.assert_called_once()
        updated_doc = cloudant.upsert_baseline.call_args[0][2]
        new_adj = updated_doc["threshold_adjustments"]["paraphrase"]
        assert new_adj == pytest.approx(THRESHOLD_NUDGE_AMOUNT)

    def test_confirmed_lowers_threshold(self):
        """Confirming a flag should decrease the paraphrase adjustment."""
        cloudant = _make_cloudant_mock(existing_adjustment=0.0)

        apply_flag_decision_feedback(
            flag=_make_flag("paraphrase"),
            decision="confirmed",
            cloudant=cloudant,
        )

        cloudant.upsert_baseline.assert_called_once()
        updated_doc = cloudant.upsert_baseline.call_args[0][2]
        new_adj = updated_doc["threshold_adjustments"]["paraphrase"]
        assert new_adj == pytest.approx(-THRESHOLD_NUDGE_AMOUNT)

    def test_nudges_accumulate(self):
        """Repeated dismissals should accumulate adjustments correctly."""
        cloudant = _make_cloudant_mock(existing_adjustment=0.02)

        apply_flag_decision_feedback(
            flag=_make_flag("paraphrase"),
            decision="dismissed",
            cloudant=cloudant,
        )

        updated_doc = cloudant.upsert_baseline.call_args[0][2]
        new_adj = updated_doc["threshold_adjustments"]["paraphrase"]
        assert new_adj == pytest.approx(0.02 + THRESHOLD_NUDGE_AMOUNT)

    def test_grade_mismatch_no_nudge(self):
        """grade_mismatch flags have no associated threshold — should be a no-op."""
        cloudant = _make_cloudant_mock()

        apply_flag_decision_feedback(
            flag=_make_flag("grade_mismatch"),
            decision="dismissed",
            cloudant=cloudant,
        )

        cloudant.upsert_baseline.assert_not_called()

    def test_missing_submission_gracefully_skipped(self):
        """If the submission is not found, the function should not crash."""
        from unittest.mock import MagicMock

        cloudant = MagicMock()
        cloudant.get_submission.return_value = None

        # Should not raise
        apply_flag_decision_feedback(
            flag=_make_flag("paraphrase"),
            decision="dismissed",
            cloudant=cloudant,
        )
        cloudant.upsert_baseline.assert_not_called()

    def test_ai_generated_type_nudged(self):
        """Nudge should target the correct flag_type key."""
        cloudant = _make_cloudant_mock(flag_type="ai_generated")

        apply_flag_decision_feedback(
            flag=_make_flag("ai_generated"),
            decision="confirmed",
            cloudant=cloudant,
        )

        updated_doc = cloudant.upsert_baseline.call_args[0][2]
        assert updated_doc["threshold_adjustments"]["ai_generated"] == pytest.approx(
            -THRESHOLD_NUDGE_AMOUNT
        )
        # Other adjustments should be unchanged
        assert updated_doc["threshold_adjustments"]["paraphrase"] == 0.0
