"""
tests/conftest.py
------------------
Shared pytest fixtures for all test modules.

Key fixture: `mock_granite` — a MagicMock that replaces GraniteClient so
tests run entirely offline without IBM watsonx.ai credentials.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_granite() -> MagicMock:
    """
    Returns a MagicMock that mimics GraniteClient's public interface.
    All three methods return sensible deterministic values.
    """
    client = MagicMock()

    # get_embedding: returns a fixed 768-dim vector (all 0.1)
    client.get_embedding.return_value = [0.1] * 768

    # classify_ai_text: returns low confidence by default
    client.classify_ai_text.return_value = {
        "confidence": 0.2,
        "explanation": "Paragraph shows typical human writing patterns.",
    }

    # explain_flags: returns a canned explanation
    client.explain_flags.return_value = (
        "Paragraph 1 is 91% similar to a submission dated 2024-01-10. "
        "The submission also shows low stylistic variation consistent with "
        "AI-generated text. Instructor review is recommended."
    )
    return client


@pytest.fixture
def mock_cloudant() -> MagicMock:
    """Returns a MagicMock mimicking CloudantService."""
    service = MagicMock()
    service.get_submission.return_value = None
    service.query_submissions.return_value = []
    service.get_flags_for_submission.return_value = []
    service.get_baseline.return_value = None
    service.append_audit_entry.return_value = None
    service.create_flag.return_value = {"ok": True}
    return service
