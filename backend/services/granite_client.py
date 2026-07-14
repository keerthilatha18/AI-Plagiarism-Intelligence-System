"""
services/granite_client.py
---------------------------
Wraps the ibm-watsonx-ai ModelInference SDK to provide three high-level
methods used throughout the scoring pipeline:

    get_embedding(text)           → list[float]
    classify_ai_text(paragraph)   → {"confidence": float, "explanation": str}
    explain_flags(submission, sub_scores) → str

Retry policy: 3 attempts with exponential back-off (1 s, 2 s, 4 s).
Any missing env var raises RuntimeError at construction time — never silently
falls back to a default key.
"""
from __future__ import annotations

import json
import logging
import time
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# ── Retry decorator ────────────────────────────────────────────────────────────

# Keywords that indicate a permanent failure — no point retrying
_PERMANENT_ERRORS = ("api key could not be found", "unauthorized", "forbidden", "invalid credentials")

def _with_retry(max_attempts: int = 2, base_delay: float = 0.5):
    """Decorator: retry `max_attempts` times with exponential back-off.
    Bails immediately on permanent auth errors (bad API key etc.)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 – intentional broad catch
                    last_exc = exc
                    # Don't retry permanent errors (wrong API key, etc.)
                    if any(p in str(exc).lower() for p in _PERMANENT_ERRORS):
                        raise RuntimeError(
                            f"Granite call '{fn.__name__}' failed with permanent error: {exc}"
                        ) from exc
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Granite call %s failed (attempt %d/%d): %s — retrying in %.1fs",
                        fn.__name__, attempt + 1, max_attempts, exc, delay,
                    )
                    time.sleep(delay)
            raise RuntimeError(
                f"Granite call '{fn.__name__}' failed after {max_attempts} attempts"
            ) from last_exc
        return wrapper
    return decorator


# ── Client class ───────────────────────────────────────────────────────────────

class GraniteClient:
    """
    Thin wrapper around ibm-watsonx-ai ModelInference.

    Instantiate once at application startup (see services/__init__.py) and
    inject via FastAPI dependency injection or direct import.
    """

    # Granite models used
    EMBEDDING_MODEL = "ibm/slate-125m-english-rtrvr"
    GENERATION_MODEL = "ibm/granite-13b-instruct-v2"

    def __init__(self, api_key: str, project_id: str, url: str) -> None:
        if not api_key:
            raise RuntimeError(
                "WATSONX_API_KEY is not set. "
                "Add it to your .env file before starting the server."
            )
        if not project_id:
            raise RuntimeError(
                "WATSONX_PROJECT_ID is not set. "
                "Add it to your .env file before starting the server."
            )
        if not url:
            raise RuntimeError(
                "WATSONX_URL is not set. "
                "Add it to your .env file before starting the server."
            )

        try:
            from ibm_watsonx_ai import APIClient, Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
        except ImportError as exc:
            raise RuntimeError(
                "ibm-watsonx-ai package is not installed. "
                "Run: pip install ibm-watsonx-ai"
            ) from exc

        # Store credentials — defer authentication to first actual API call
        # so a bad key produces a clear per-call error rather than crashing startup.
        self._credentials = Credentials(url=url, api_key=api_key)
        self._api_key = api_key
        self._project_id = project_id
        self._ModelInference = ModelInference
        self._client: Any = None  # lazily initialised on first use

    def _get_client(self):
        """Return (or lazily create) the authenticated APIClient."""
        if self._client is None:
            from ibm_watsonx_ai import APIClient
            self._client = APIClient(self._credentials)
        return self._client

    # ── Embedding ──────────────────────────────────────────────────────────────

    @_with_retry(max_attempts=2, base_delay=0.5)
    def get_embedding(self, text: str) -> list[float]:
        """
        Return a dense embedding vector for `text` using Slate-125M.
        The vector is used for cosine similarity comparisons in the scoring engine.
        """
        model = self._ModelInference(
            model_id=self.EMBEDDING_MODEL,
            api_client=self._get_client(),
            project_id=self._project_id,
        )
        result = model.generate(prompt=text)
        # ibm-watsonx-ai embedding response shape: {"results": [{"embedding": [...]}]}
        try:
            return result["results"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected embedding response shape: {result}"
            ) from exc

    # ── AI-text classifier ─────────────────────────────────────────────────────

    @_with_retry(max_attempts=2, base_delay=0.5)
    def classify_ai_text(self, paragraph: str) -> dict[str, Any]:
        """
        Ask Granite to assess whether `paragraph` shows characteristics of
        AI-generated text (uniformity / low burstiness).

        Returns
        -------
        {"confidence": float (0-1), "explanation": str}
        """
        prompt = (
            "You are an academic integrity assistant. "
            "Analyze the following paragraph and determine whether it was likely "
            "written by an AI language model (characteristics: unusually uniform "
            "sentence length, lack of personal style, low burstiness, generic phrasing).\n\n"
            f"Paragraph:\n\"\"\"\n{paragraph}\n\"\"\"\n\n"
            "Respond ONLY with a JSON object in this exact format — no preamble:\n"
            '{"confidence": <0.0 to 1.0>, "explanation": "<one sentence citing specific evidence>"}'
        )
        model = self._ModelInference(
            model_id=self.GENERATION_MODEL,
            api_client=self._get_client(),
            project_id=self._project_id,
        )
        result = model.generate(prompt=prompt)
        raw_text = result["results"][0]["generated_text"].strip()

        # Parse the JSON; if the model adds markdown fences, strip them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        try:
            parsed = json.loads(raw_text)
            confidence = float(parsed["confidence"])
            explanation = str(parsed["explanation"])
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning("Could not parse classify_ai_text response: %s", raw_text)
            # Graceful fallback — low confidence, preserve raw text as explanation
            confidence = 0.0
            explanation = raw_text[:300]

        return {"confidence": min(max(confidence, 0.0), 1.0), "explanation": explanation}

    # ── Explanation generator ──────────────────────────────────────────────────

    @_with_retry(max_attempts=2, base_delay=0.5)
    def explain_flags(self, submission_id: str, sub_scores: dict[str, Any]) -> str:
        """
        Produce a 2-3 sentence human-readable explanation for all flags raised
        on a submission.  The explanation MUST cite specific evidence (paragraph
        numbers, similarity percentages, comparison dates).

        Parameters
        ----------
        submission_id : str
            Used so the model can reference it.
        sub_scores : dict
            Structured evidence dict assembled by the scoring engine, e.g.:
            {
              "paraphrase_hits": [{"paragraph": 3, "similarity": 0.91, "matched_date": "..."}],
              "ai_confidence": 0.78,
              "style_drift_score": 0.55,
            }
        """
        evidence_json = json.dumps(sub_scores, indent=2, default=str)
        prompt = (
            "You are an academic integrity assistant writing a concise report for an instructor.\n"
            f"Submission ID: {submission_id}\n\n"
            "Evidence summary (JSON):\n"
            f"{evidence_json}\n\n"
            "Write a 2-3 sentence explanation that:\n"
            "1. Cites specific paragraphs, similarity percentages, and dates where available.\n"
            "2. States the nature of each concern (paraphrase / AI-generated / style drift).\n"
            "3. Recommends instructor review without making a final determination.\n"
            "Do NOT just repeat the numbers — turn them into readable English sentences."
        )
        model = self._ModelInference(
            model_id=self.GENERATION_MODEL,
            api_client=self._get_client(),
            project_id=self._project_id,
        )
        result = model.generate(prompt=prompt)
        return result["results"][0]["generated_text"].strip()


# ── Module-level singleton factory ────────────────────────────────────────────

def get_granite_client() -> GraniteClient:
    """
    FastAPI dependency / module-level factory.
    Reads credentials from the cached Settings singleton.
    """
    from config import get_settings
    s = get_settings()
    return GraniteClient(
        api_key=s.watsonx_api_key,
        project_id=s.watsonx_project_id,
        url=s.watsonx_url,
    )
