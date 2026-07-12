"""
routers/flags.py
-----------------
Flag endpoints:

  GET   /flags/{id}               — retrieve a single flag
  PATCH /flags/{id}/decision      — record instructor decision and nudge baseline
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from models.flag import FlagDecisionPatch
from services.cloudant_service import CloudantService, get_cloudant_service
from services.scoring import apply_flag_decision_feedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flags", tags=["flags"])


@router.get("/{flag_id}")
def get_flag(
    flag_id: str,
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    """Retrieve a single flag by ID.  Includes confidence and granite_explanation."""
    flag = cloudant.get_flag(flag_id)
    if not flag:
        raise HTTPException(status_code=404, detail=f"Flag '{flag_id}' not found")
    return flag


@router.patch("/{flag_id}/decision")
def set_flag_decision(
    flag_id: str,
    body: FlagDecisionPatch,
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    """
    Record the instructor's decision on a flag.

    ETHICAL GUARDRAIL: this is the required human-in-the-loop step.
    No grade changes or student notifications happen automatically — the flag
    is simply marked reviewed with the instructor's decision.

    After recording the decision, the adaptive feedback loop nudges the
    instructor's threshold for this flag type so future runs are better calibrated.

    Body:
        {"decision": "confirmed" | "dismissed"}
    """
    if body.decision not in ("confirmed", "dismissed"):
        raise HTTPException(
            status_code=422,
            detail="decision must be 'confirmed' or 'dismissed'",
        )

    flag = cloudant.get_flag(flag_id)
    if not flag:
        raise HTTPException(status_code=404, detail=f"Flag '{flag_id}' not found")

    if flag.get("reviewed"):
        raise HTTPException(
            status_code=409,
            detail=f"Flag '{flag_id}' has already been reviewed with decision '{flag.get('instructor_decision')}'",
        )

    # ── Update the flag document ──────────────────────────────────────────
    cloudant.update_flag(
        flag_id,
        {"reviewed": True, "instructor_decision": body.decision},
    )

    # ── Adaptive baseline nudge ────────────────────────────────────────────
    # Adjust the instructor's threshold for this flag type based on the decision.
    # This is the "learns from instructor feedback" feature — see scoring.py for
    # the nudge logic.
    try:
        apply_flag_decision_feedback(
            flag=flag,
            decision=body.decision,
            cloudant=cloudant,
        )
    except Exception as exc:  # noqa: BLE001
        # Nudging failure should not block the decision from being recorded
        logger.warning("Threshold nudge failed for flag %s: %s", flag_id, exc)

    return {
        "flag_id": flag_id,
        "decision": body.decision,
        "reviewed": True,
        "status": "decision recorded — no automatic action taken",
    }
