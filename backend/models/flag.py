"""
models/flag.py
--------------
Pydantic v2 data models for the Flag resource.
Flags are created by the scoring engine and stored in the Cloudant `flags`
collection.  They require human review (PATCH /flags/{id}/decision) before
any downstream action is taken — this is a core ethical guardrail.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class FlagType(str, Enum):
    paraphrase = "paraphrase"
    ai_generated = "ai_generated"
    style_drift = "style_drift"
    grade_mismatch = "grade_mismatch"


class Flag(BaseModel):
    """
    A single integrity concern raised against a submission.

    Every flag carries:
    - `confidence`         — 0-1 score so the instructor can calibrate.
    - `granite_explanation` — human-readable evidence sentence(s) from the
                              Granite model; never a bare boolean or score.
    - `reviewed` / `instructor_decision` — enforce the human-in-the-loop
                              requirement before any downstream action.
    """

    flag_id: str = Field(default_factory=lambda: str(uuid4()))
    submission_id: str
    flag_type: FlagType
    confidence: float = Field(ge=0.0, le=1.0)

    # Human-readable explanation with specific evidence — required by spec
    granite_explanation: str

    # Workflow state — flags start unreviewed with no decision
    reviewed: bool = False
    instructor_decision: Optional[str] = None  # "confirmed" | "dismissed" | None

    model_config = {"use_enum_values": True}


class FlagDecisionPatch(BaseModel):
    """Request body for PATCH /flags/{id}/decision."""

    decision: str  # "confirmed" | "dismissed"

    def is_confirmed(self) -> bool:
        return self.decision == "confirmed"

    def is_dismissed(self) -> bool:
        return self.decision == "dismissed"
