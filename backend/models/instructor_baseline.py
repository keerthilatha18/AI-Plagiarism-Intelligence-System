"""
models/instructor_baseline.py
-------------------------------
Pydantic v2 data model for the InstructorBaseline resource.
One document per (instructor_id, assignment_id) pair is stored in the
Cloudant `instructor_baselines` collection.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InstructorBaseline(BaseModel):
    """
    Aggregated style + grading baseline derived from past clean submissions.

    `threshold_adjustments` holds per-flag-type nudges accumulated through
    instructor decisions (confirmed → lower threshold, dismissed → higher).
    Shape: {"paraphrase": 0.0, "ai_generated": 0.0, "style_drift": 0.0}
    """

    instructor_id: str
    assignment_id: str

    grade_distribution: dict[str, Any] = Field(default_factory=dict)
    common_feedback_terms: list[str] = Field(default_factory=list)

    # Averaged style_fingerprint across clean submissions
    expected_style_profile: dict[str, float] = Field(
        default_factory=lambda: {
            "avg_sentence_len": 0.0,
            "vocab_richness": 0.0,
            "passive_voice_ratio": 0.0,
        }
    )

    historical_flag_rate: float = 0.0

    # Adaptive threshold nudges — persisted between scoring runs.
    # A positive value means thresholds have been raised (instructor dismissed
    # many flags as false positives); negative means lowered.
    threshold_adjustments: dict[str, float] = Field(
        default_factory=lambda: {
            "paraphrase": 0.0,
            "ai_generated": 0.0,
            "style_drift": 0.0,
        }
    )
