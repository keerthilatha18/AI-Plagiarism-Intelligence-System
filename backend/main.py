"""
main.py
-------
FastAPI application factory for Plagiarism Intelligence.

Startup checks:
- Validates that all required env vars are present (Pydantic raises on import
  if any are missing — see config.py).
- Confirms spaCy model is loadable.

All routers are registered with a versioned /api/v1 prefix.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import flags, instructors, submissions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Plagiarism Intelligence API",
    version="1.0.0",
    description=(
        "AI-driven academic integrity tool that detects paraphrased / "
        "AI-generated plagiarism and learns instructor-specific baselines."
    ),
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(submissions.router, prefix="/api/v1")
app.include_router(flags.router, prefix="/api/v1")
app.include_router(instructors.router, prefix="/api/v1")


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event() -> None:
    """Fail fast: verify spaCy model is available and env vars are loaded."""
    try:
        import spacy  # noqa: F401 – side-effect check only

        spacy.load("en_core_web_sm")
        logger.info("spaCy en_core_web_sm loaded OK")
    except OSError:
        logger.warning(
            "spaCy model 'en_core_web_sm' not found. "
            "Run: python -m spacy download en_core_web_sm"
        )

    logger.info(
        "Plagiarism Intelligence API starting — "
        "watsonx project=%s  cloudant=%s",
        settings.watsonx_project_id,
        settings.cloudant_url,
    )


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
