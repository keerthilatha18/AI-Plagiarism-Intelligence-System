"""
services/scoring.py
--------------------
The core scoring pipeline for Plagiarism Intelligence.

Pipeline steps (in order):
  1. Paraphrase detection      — cosine similarity between paragraph embeddings
  2. AI-text detection         — Granite classifier on each paragraph
  3. Style drift detection     — deviation from InstructorBaseline style profile
  4. Grade mismatch (stub)     — placeholder for when grade data is present
  5. Final Granite explanation — 2-3 sentence human-readable summary per flag
  6. Audit log                 — append a transparency record to Cloudant

ETHICAL GUARDRAILS (baked in, not just documented):
  - Every Flag includes `confidence` and `granite_explanation` — no bare booleans.
  - No automatic grade changes or student notifications — flags require the
    PATCH /flags/{id}/decision human step before any downstream action.
  - Every run writes to the audit_log collection with timestamp, submission_id,
    and the exact thresholds used.

ADAPTIVE FEEDBACK:
  See `apply_flag_decision_feedback()` at the bottom of this module.
  Called by PATCH /flags/{id}/decision via the flags router.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from models.flag import Flag, FlagType
from services.cloudant_service import CloudantService
from services.granite_client import GraniteClient

logger = logging.getLogger(__name__)

# ── Threshold defaults (overridable via Settings) ────────────────────────────
DEFAULT_PARAPHRASE_THRESHOLD = 0.82
DEFAULT_STYLE_DRIFT_THRESHOLD = 0.40
# Nudge magnitude applied to per-instructor thresholds on each decision
THRESHOLD_NUDGE_AMOUNT = 0.01


# ── Public entry point ────────────────────────────────────────────────────────

def run_scoring_pipeline(
    submission: dict[str, Any],
    cloudant: CloudantService,
    granite: GraniteClient,
    paraphrase_threshold: float = DEFAULT_PARAPHRASE_THRESHOLD,
    style_drift_threshold: float = DEFAULT_STYLE_DRIFT_THRESHOLD,
) -> list[Flag]:
    """
    Run the full scoring pipeline for a single submission.

    Parameters
    ----------
    submission          : raw Cloudant document for the submission being scored
    cloudant            : CloudantService instance
    granite             : GraniteClient instance
    paraphrase_threshold: cosine similarity above which a paragraph pair is flagged
    style_drift_threshold: normalised deviation above which style drift is flagged

    Returns
    -------
    List of Flag objects.  Each Flag is also written to the Cloudant `flags`
    collection before being returned.
    """
    submission_id = submission["submission_id"]
    assignment_id = submission["assignment_id"]
    instructor_id = submission["instructor_id"]
    raw_text: str = submission.get("raw_text", "")

    # ── Retrieve instructor baseline for personalised thresholds ───────────────
    baseline = cloudant.get_baseline(instructor_id, assignment_id) or {}
    threshold_adjustments = baseline.get("threshold_adjustments", {})

    # Apply per-instructor adjustments on top of deployment defaults
    effective_paraphrase_threshold = paraphrase_threshold + threshold_adjustments.get(
        "paraphrase", 0.0
    )
    effective_style_drift_threshold = style_drift_threshold + threshold_adjustments.get(
        "style_drift", 0.0
    )

    logger.info(
        "Scoring submission=%s  paraphrase_threshold=%.3f  style_threshold=%.3f",
        submission_id,
        effective_paraphrase_threshold,
        effective_style_drift_threshold,
    )

    paragraphs = _split_paragraphs(raw_text)
    flags: list[Flag] = []
    sub_scores: dict[str, Any] = {
        "paraphrase_hits": [],
        "ai_generated_hits": [],
        "style_drift_score": None,
        "grade_mismatch": None,
    }

    # ── Step 1: Paraphrase detection ──────────────────────────────────────────
    try:
        para_flags, para_evidence = _detect_paraphrase(
            paragraphs=paragraphs,
            submission_id=submission_id,
            assignment_id=assignment_id,
            threshold=effective_paraphrase_threshold,
            cloudant=cloudant,
            granite=granite,
        )
        flags.extend(para_flags)
        sub_scores["paraphrase_hits"] = para_evidence
    except Exception as exc:
        logger.warning("Paraphrase detection skipped (Granite unavailable): %s", exc)

    # Step 2: AI-text detection
    try:
        ai_flags, ai_evidence = _detect_ai_generated(
            paragraphs=paragraphs,
            submission_id=submission_id,
            granite=granite,
        )
        flags.extend(ai_flags)
        sub_scores["ai_generated_hits"] = ai_evidence
    except Exception as exc:
        logger.warning("AI-text detection skipped (Granite unavailable): %s", exc)

    # ── Step 3: Style drift ────────────────────────────────────────────────────
    style_flag, drift_score = _detect_style_drift(
        submission=submission,
        baseline=baseline,
        submission_id=submission_id,
        threshold=effective_style_drift_threshold,
    )
    if style_flag:
        flags.append(style_flag)
    sub_scores["style_drift_score"] = drift_score

    # ── Step 4: Grade mismatch (stub) ─────────────────────────────────────────
    grade_flag = _detect_grade_mismatch(submission, baseline)
    if grade_flag:
        flags.append(grade_flag)
        sub_scores["grade_mismatch"] = "grade deviation detected"

    # ── Step 5: Final Granite explanation for each flag ───────────────────────
    flags = _attach_explanations(flags, submission_id, sub_scores, granite)

    # ── Step 6: Persist flags to Cloudant ────────────────────────────────────
    for flag in flags:
        cloudant.create_flag(flag.model_dump())

    # ── Step 7: Write audit log (transparency requirement) ───────────────────
    cloudant.append_audit_entry(
        {
            "run_id": str(uuid4()),
            "submission_id": submission_id,
            "assignment_id": assignment_id,
            "instructor_id": instructor_id,
            "thresholds_used": {
                "paraphrase": effective_paraphrase_threshold,
                "style_drift": effective_style_drift_threshold,
            },
            "flags_produced": len(flags),
            "flag_types": [f.flag_type for f in flags],
        }
    )

    return flags


# ── Step 1 helpers ────────────────────────────────────────────────────────────

def _detect_paraphrase(
    paragraphs: list[str],
    submission_id: str,
    assignment_id: str,
    threshold: float,
    cloudant: CloudantService,
    granite: GraniteClient,
) -> tuple[list[Flag], list[dict[str, Any]]]:
    """
    For each paragraph of the submission, retrieve other submissions for the
    same assignment and compare cosine similarity of embeddings.

    Returns
    -------
    (list of Flag objects, list of evidence dicts for the explanation step)
    """
    flags: list[Flag] = []
    evidence: list[dict[str, Any]] = []

    # Retrieve peer submissions for the same assignment (excluding self)
    peers = cloudant.query_submissions({"assignment_id": {"$eq": assignment_id}})
    peers = [p for p in peers if p.get("submission_id") != submission_id]

    for para_idx, para_text in enumerate(paragraphs):
        if not para_text.strip():
            continue

        try:
            para_embedding = granite.get_embedding(para_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding failed for paragraph %d: %s", para_idx + 1, exc)
            continue

        for peer in peers:
            peer_embedding: list[float] = peer.get("embedding_vector", [])
            if not peer_embedding:
                continue
            similarity = cosine_similarity(para_embedding, peer_embedding)
            if similarity >= threshold:
                peer_date = peer.get("submitted_at", "unknown date")
                hit = {
                    "paragraph": para_idx + 1,
                    "similarity": round(similarity, 4),
                    "matched_submission_id": peer.get("submission_id", "unknown"),
                    "matched_date": peer_date,
                }
                evidence.append(hit)
                flags.append(
                    Flag(
                        submission_id=submission_id,
                        flag_type=FlagType.paraphrase,
                        confidence=round(similarity, 4),
                        # Placeholder explanation — enriched by Granite in Step 5
                        granite_explanation=(
                            f"Paragraph {para_idx + 1} shows {similarity:.0%} similarity "
                            f"to a submission from {peer_date}. Awaiting final analysis."
                        ),
                    )
                )

    return flags, evidence


# ── Step 2 helpers ────────────────────────────────────────────────────────────

def _detect_ai_generated(
    paragraphs: list[str],
    submission_id: str,
    granite: GraniteClient,
) -> tuple[list[Flag], list[dict[str, Any]]]:
    """
    Send each paragraph to the Granite AI-text classifier.
    Flag any paragraph with AI confidence above 0.60.
    """
    AI_CONFIDENCE_THRESHOLD = 0.60
    flags: list[Flag] = []
    evidence: list[dict[str, Any]] = []

    for para_idx, para_text in enumerate(paragraphs):
        if not para_text.strip():
            continue
        try:
            result = granite.classify_ai_text(para_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI classification failed for paragraph %d: %s", para_idx + 1, exc)
            continue

        confidence = result["confidence"]
        explanation = result["explanation"]

        if confidence >= AI_CONFIDENCE_THRESHOLD:
            hit = {
                "paragraph": para_idx + 1,
                "ai_confidence": confidence,
                "classifier_note": explanation,
            }
            evidence.append(hit)
            flags.append(
                Flag(
                    submission_id=submission_id,
                    flag_type=FlagType.ai_generated,
                    confidence=confidence,
                    granite_explanation=explanation,
                )
            )

    return flags, evidence


# ── Step 3 helpers ────────────────────────────────────────────────────────────

def _detect_style_drift(
    submission: dict[str, Any],
    baseline: dict[str, Any],
    submission_id: str,
    threshold: float,
) -> tuple[Flag | None, float | None]:
    """
    Compare the submission's style_fingerprint against the instructor baseline.

    Computes the mean absolute normalised deviation across the three fingerprint
    dimensions.  Returns (Flag, deviation_score) or (None, deviation_score).
    """
    submission_fp = submission.get("style_fingerprint", {})
    expected_fp = baseline.get("expected_style_profile", {})

    if not submission_fp or not expected_fp:
        return None, None

    dimensions = ["avg_sentence_len", "vocab_richness", "passive_voice_ratio"]
    deviations: list[float] = []

    for dim in dimensions:
        sub_val = float(submission_fp.get(dim, 0.0))
        exp_val = float(expected_fp.get(dim, 0.0))
        if exp_val == 0.0:
            continue
        # Normalised absolute deviation
        deviations.append(abs(sub_val - exp_val) / exp_val)

    if not deviations:
        return None, None

    drift_score = sum(deviations) / len(deviations)

    if drift_score >= threshold:
        return (
            Flag(
                submission_id=submission_id,
                flag_type=FlagType.style_drift,
                confidence=min(drift_score, 1.0),
                granite_explanation=(
                    f"Submission style deviates {drift_score:.0%} from the instructor "
                    "baseline on average across sentence length, vocabulary richness, "
                    "and passive voice ratio. Awaiting final analysis."
                ),
            ),
            drift_score,
        )
    return None, drift_score


# ── Step 4 helpers (stub) ─────────────────────────────────────────────────────

def _detect_grade_mismatch(
    submission: dict[str, Any],
    baseline: dict[str, Any],
) -> Flag | None:
    """
    Grade mismatch detection — stub implementation.

    When grade data is available on the submission document, compare it against
    what the style/paraphrase profile would predict using the baseline
    grade_distribution.  For now, returns None until grade data is plumbed in.
    """
    # TODO: implement when grade field is added to submissions
    return None


# ── Step 5 helpers ────────────────────────────────────────────────────────────

def _attach_explanations(
    flags: list[Flag],
    submission_id: str,
    sub_scores: dict[str, Any],
    granite: GraniteClient,
) -> list[Flag]:
    """
    Make ONE Granite call to replace placeholder explanations with a
    fully-evidenced human-readable string.  Applies the result to all flags
    from this run so the explanation covers the holistic picture.
    """
    if not flags:
        return flags

    try:
        full_explanation = granite.explain_flags(
            submission_id=submission_id,
            sub_scores=sub_scores,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Granite explanation call failed: %s — keeping placeholder text", exc)
        return flags

    # Assign the shared explanation to all flags in this run
    updated: list[Flag] = []
    for flag in flags:
        updated.append(flag.model_copy(update={"granite_explanation": full_explanation}))
    return updated


# ── Adaptive threshold nudging ────────────────────────────────────────────────

def apply_flag_decision_feedback(
    flag: dict[str, Any],
    decision: str,
    cloudant: CloudantService,
) -> None:
    """
    Adjust the instructor's threshold for the relevant flag type based on
    their decision.

    Logic (simple and clearly commented — this is the "learns from feedback"
    requirement; no ML model needed):

    - "dismissed" → the instructor considers this a false positive, so we
      raise the threshold slightly so future similar submissions are less
      likely to be flagged.  nudge = +THRESHOLD_NUDGE_AMOUNT

    - "confirmed" → the instructor considers this a true positive, so we
      lower the threshold slightly so future borderline cases are caught.
      nudge = -THRESHOLD_NUDGE_AMOUNT

    The adjustment is stored in InstructorBaseline.threshold_adjustments[flag_type]
    and applied at the start of run_scoring_pipeline().
    """
    submission_id = flag.get("submission_id")
    flag_type: str = flag.get("flag_type", "")

    if flag_type not in ("paraphrase", "ai_generated", "style_drift"):
        return  # No threshold to nudge for grade_mismatch

    # Retrieve the parent submission to find instructor_id and assignment_id
    submission = cloudant.get_submission(submission_id)
    if not submission:
        logger.warning("Cannot apply feedback: submission '%s' not found", submission_id)
        return

    instructor_id = submission["instructor_id"]
    assignment_id = submission["assignment_id"]

    baseline = cloudant.get_baseline(instructor_id, assignment_id) or {}
    adjustments: dict[str, float] = baseline.get(
        "threshold_adjustments",
        {"paraphrase": 0.0, "ai_generated": 0.0, "style_drift": 0.0},
    )

    if decision == "dismissed":
        # False positive → raise threshold (less sensitive)
        adjustments[flag_type] = round(
            adjustments.get(flag_type, 0.0) + THRESHOLD_NUDGE_AMOUNT, 4
        )
        logger.info(
            "Threshold nudge UP for %s/%s/%s: new adjustment=%.4f",
            instructor_id, assignment_id, flag_type, adjustments[flag_type],
        )
    elif decision == "confirmed":
        # True positive → lower threshold (more sensitive)
        adjustments[flag_type] = round(
            adjustments.get(flag_type, 0.0) - THRESHOLD_NUDGE_AMOUNT, 4
        )
        logger.info(
            "Threshold nudge DOWN for %s/%s/%s: new adjustment=%.4f",
            instructor_id, assignment_id, flag_type, adjustments[flag_type],
        )

    # Persist the updated adjustments back to the baseline
    baseline["threshold_adjustments"] = adjustments
    # Preserve all other baseline fields; upsert handles create-or-update
    cloudant.upsert_baseline(instructor_id, assignment_id, baseline)


# ── Baseline rebuild ──────────────────────────────────────────────────────────

def rebuild_instructor_baseline(
    instructor_id: str,
    assignment_id: str,
    cloudant: CloudantService,
) -> dict[str, Any]:
    """
    Recompute InstructorBaseline from confirmed-clean submissions.

    "Confirmed clean" = submissions for this instructor+assignment that have NO
    confirmed flags (i.e., all flags dismissed or no flags at all).

    Returns the new baseline dict (already upserted to Cloudant).
    """
    # All submissions for this instructor/assignment
    submissions = cloudant.query_submissions(
        {
            "instructor_id": {"$eq": instructor_id},
            "assignment_id": {"$eq": assignment_id},
        }
    )

    clean_fingerprints: list[dict[str, float]] = []

    for sub in submissions:
        sub_id = sub["submission_id"]
        flags_for_sub = cloudant.get_flags_for_submission(sub_id)

        # A submission is "clean" if it has no confirmed flags
        has_confirmed = any(f.get("instructor_decision") == "confirmed" for f in flags_for_sub)
        if not has_confirmed:
            fp = sub.get("style_fingerprint", {})
            if fp:
                clean_fingerprints.append(fp)

    # Average the style fingerprints across clean submissions
    if clean_fingerprints:
        avg_fp = {
            dim: round(
                sum(fp.get(dim, 0.0) for fp in clean_fingerprints) / len(clean_fingerprints),
                4,
            )
            for dim in ("avg_sentence_len", "vocab_richness", "passive_voice_ratio")
        }
    else:
        avg_fp = {"avg_sentence_len": 0.0, "vocab_richness": 0.0, "passive_voice_ratio": 0.0}

    # Compute historical flag rate
    total = len(submissions)
    flagged = sum(
        1
        for sub in submissions
        if cloudant.get_flags_for_submission(sub["submission_id"])
    )
    historical_flag_rate = round(flagged / total, 4) if total else 0.0

    existing_baseline = cloudant.get_baseline(instructor_id, assignment_id) or {}
    new_baseline = {
        **existing_baseline,
        "instructor_id": instructor_id,
        "assignment_id": assignment_id,
        "expected_style_profile": avg_fp,
        "historical_flag_rate": historical_flag_rate,
        # Preserve adaptive adjustments if they exist
        "threshold_adjustments": existing_baseline.get(
            "threshold_adjustments",
            {"paraphrase": 0.0, "ai_generated": 0.0, "style_drift": 0.0},
        ),
    }

    cloudant.upsert_baseline(instructor_id, assignment_id, new_baseline)
    return new_baseline


# ── Utility ───────────────────────────────────────────────────────────────────

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    Returns 0.0 if either vector is empty or zero-magnitude.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _split_paragraphs(text: str) -> list[str]:
    """Split raw text into paragraphs on blank lines."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]
