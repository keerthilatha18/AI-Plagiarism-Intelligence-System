"""
routers/submissions.py
-----------------------
Submission endpoints:

  POST   /submissions/upload                 — multipart file + metadata
  POST   /submissions/{id}/process           — stylometrics + embedding
  GET    /submissions/{id}                   — retrieve single submission
  GET    /submissions?assignment_id=&instructor_id= — filtered list
  POST   /submissions/{id}/score             — run scoring pipeline
  GET    /submissions/{id}/flags             — list flags for a submission
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from config import Settings, get_settings
from models.submission import Submission, StyleFingerprint, SubmissionCreate
from services.cloudant_service import CloudantService, get_cloudant_service
from services.cos_service import COSService, get_cos_service
from services.granite_client import GraniteClient, get_granite_client
from services.scoring import run_scoring_pipeline
from services.stylometrics import compute_readability_score, compute_style_fingerprint
from utils.text_extraction import extract_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/submissions", tags=["submissions"])


# ── POST /submissions/upload ──────────────────────────────────────────────────

@router.post("/upload", status_code=201)
async def upload_submission(
    file: UploadFile = File(...),
    student_id: str = Form(...),
    assignment_id: str = Form(...),
    instructor_id: str = Form(...),
    cloudant: CloudantService = Depends(get_cloudant_service),
    cos: COSService = Depends(get_cos_service),
) -> dict:
    """
    Accept a multipart file (.txt / .docx / .pdf) plus form metadata,
    extract text, store the raw file in COS, write a Submission document
    to Cloudant, and return the submission_id.
    """
    file_bytes = await file.read()
    filename = file.filename or "upload.txt"

    # ── Text extraction ────────────────────────────────────────────────────
    try:
        raw_text = extract_text(file_bytes, filename)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))

    # ── Store raw file in COS ──────────────────────────────────────────────
    sub = Submission(
        student_id=student_id,
        assignment_id=assignment_id,
        instructor_id=instructor_id,
        raw_text=raw_text,
    )
    cos_key = f"submissions/{sub.submission_id}/{filename}"
    try:
        file_url = cos.upload_file(file_bytes, cos_key, content_type=file.content_type or "application/octet-stream")
    except Exception as exc:  # noqa: BLE001
        logger.error("COS upload failed: %s", exc)
        file_url = ""  # Don't fail the whole upload if COS is unavailable

    sub.file_url = file_url

    # ── Persist to Cloudant ────────────────────────────────────────────────
    doc = sub.model_dump(mode="json")
    cloudant.create_submission(doc)

    logger.info("Created submission %s for student %s", sub.submission_id, student_id)
    return {"submission_id": sub.submission_id, "status": "uploaded"}


# ── POST /submissions/{id}/process ────────────────────────────────────────────

@router.post("/{submission_id}/process")
def process_submission(
    submission_id: str,
    cloudant: CloudantService = Depends(get_cloudant_service),
    granite: GraniteClient = Depends(get_granite_client),
) -> dict:
    """
    Run the processing pipeline on a previously uploaded submission:
      1. Compute spaCy style fingerprint
      2. Compute Flesch readability score
      3. Generate Granite embedding vector
      4. Persist results back to the Cloudant document
    """
    submission = cloudant.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission '{submission_id}' not found")

    raw_text: str = submission.get("raw_text", "")

    # ── Stylometrics (spaCy) ───────────────────────────────────────────────
    fingerprint_dict = compute_style_fingerprint(raw_text)
    readability = compute_readability_score(raw_text)

    # ── Embedding (Granite) ────────────────────────────────────────────────
    try:
        embedding = granite.get_embedding(raw_text[:4096])  # Truncate to token limit
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding failed for submission %s: %s", submission_id, exc)
        embedding = []

    # ── Persist back to Cloudant ──────────────────────────────────────────
    cloudant.update_submission(
        submission_id,
        {
            "style_fingerprint": fingerprint_dict,
            "readability_score": readability,
            "embedding_vector": embedding,
        },
    )

    return {
        "submission_id": submission_id,
        "style_fingerprint": fingerprint_dict,
        "readability_score": readability,
        "embedding_vector_length": len(embedding),
        "status": "processed",
    }


# ── GET /submissions/{id} ─────────────────────────────────────────────────────

@router.get("/{submission_id}")
def get_submission(
    submission_id: str,
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    submission = cloudant.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission '{submission_id}' not found")
    return submission


# ── GET /submissions ──────────────────────────────────────────────────────────

@router.get("")
def list_submissions(
    assignment_id: Optional[str] = None,
    instructor_id: Optional[str] = None,
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    selector: dict = {}
    if assignment_id:
        selector["assignment_id"] = {"$eq": assignment_id}
    if instructor_id:
        selector["instructor_id"] = {"$eq": instructor_id}
    if not selector:
        selector["submission_id"] = {"$gt": ""}  # Fetch all

    docs = cloudant.query_submissions(selector)
    return {"submissions": docs, "count": len(docs)}


# ── POST /submissions/{id}/score ──────────────────────────────────────────────

@router.post("/{submission_id}/score")
def score_submission(
    submission_id: str,
    cloudant: CloudantService = Depends(get_cloudant_service),
    granite: GraniteClient = Depends(get_granite_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Run the full scoring engine against the submission and return all flags
    produced.

    ETHICAL GUARDRAIL: every flag in the response includes `confidence` and
    `granite_explanation`.  No bare booleans, no automatic grade changes.
    """
    submission = cloudant.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission '{submission_id}' not found")

    if not submission.get("embedding_vector"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Submission '{submission_id}' has not been processed yet. "
                "Call POST /submissions/{id}/process first."
            ),
        )

    try:
        flags = run_scoring_pipeline(
            submission=submission,
            cloudant=cloudant,
            granite=granite,
            paraphrase_threshold=settings.paraphrase_cosine_threshold,
            style_drift_threshold=settings.style_drift_threshold,
        )
    except Exception as exc:
        logger.error("Scoring pipeline failed for %s: %s", submission_id, exc)
        raise HTTPException(status_code=502, detail=f"Scoring pipeline error: {exc}")

    return {
        "submission_id": submission_id,
        "flags": [f.model_dump() for f in flags],
        "flag_count": len(flags),
    }


# ── GET /submissions/{id}/flags ───────────────────────────────────────────────

@router.get("/{submission_id}/flags")
def get_submission_flags(
    submission_id: str,
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    """Return all flags for a submission, including confidence and explanation."""
    submission = cloudant.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission '{submission_id}' not found")

    flags = cloudant.get_flags_for_submission(submission_id)
    return {"submission_id": submission_id, "flags": flags, "count": len(flags)}
