"""
models/submission.py
--------------------
Pydantic v2 data models for the Submission resource.
These are used both for API request/response validation and as the shape of
documents stored in the Cloudant `submissions` collection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class StyleFingerprint(BaseModel):
    """Stylometric measurements derived from spaCy analysis."""

    avg_sentence_len: float = 0.0
    vocab_richness: float = 0.0       # type-token ratio
    passive_voice_ratio: float = 0.0  # fraction of sentences with passive construction


class SubmissionCreate(BaseModel):
    """Fields supplied by the client when uploading a new submission."""

    student_id: str
    assignment_id: str
    instructor_id: str


class Submission(BaseModel):
    """Full submission document — matches the Cloudant JSON shape."""

    submission_id: str = Field(default_factory=lambda: str(uuid4()))
    student_id: str
    assignment_id: str
    instructor_id: str

    # Set after text extraction
    raw_text: str = ""
    file_url: str = ""
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Set after the /process step
    embedding_vector: list[float] = Field(default_factory=list)
    readability_score: float = 0.0
    style_fingerprint: StyleFingerprint = Field(default_factory=StyleFingerprint)

    model_config = {"arbitrary_types_allowed": True}


class SubmissionUpdate(BaseModel):
    """Partial update payload — all fields optional."""

    raw_text: Optional[str] = None
    file_url: Optional[str] = None
    embedding_vector: Optional[list[float]] = None
    readability_score: Optional[float] = None
    style_fingerprint: Optional[StyleFingerprint] = None
