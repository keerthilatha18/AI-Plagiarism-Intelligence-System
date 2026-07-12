"""
routers/instructors.py
-----------------------
Instructor baseline endpoints:

  POST /instructors/{id}/baseline/rebuild?assignment_id=
  GET  /instructors/{id}/baseline?assignment_id=
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from services.cloudant_service import CloudantService, get_cloudant_service
from services.scoring import rebuild_instructor_baseline

router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.post("/{instructor_id}/baseline/rebuild")
def rebuild_baseline(
    instructor_id: str,
    assignment_id: str = Query(..., description="Assignment to rebuild baseline for"),
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    """
    Recompute the InstructorBaseline for this instructor + assignment from all
    confirmed-clean historical submissions.

    "Clean" = submissions with no confirmed flags.
    The rebuilt baseline updates expected_style_profile and historical_flag_rate.
    Adaptive threshold adjustments accumulated from flag decisions are preserved.
    """
    new_baseline = rebuild_instructor_baseline(
        instructor_id=instructor_id,
        assignment_id=assignment_id,
        cloudant=cloudant,
    )
    return {
        "instructor_id": instructor_id,
        "assignment_id": assignment_id,
        "baseline": new_baseline,
        "status": "rebuilt",
    }


@router.get("/{instructor_id}/baseline")
def get_baseline(
    instructor_id: str,
    assignment_id: str = Query(..., description="Assignment to retrieve baseline for"),
    cloudant: CloudantService = Depends(get_cloudant_service),
) -> dict:
    """
    Retrieve the current InstructorBaseline for this instructor + assignment.
    Returns 404 if no baseline has been built yet.
    """
    baseline = cloudant.get_baseline(instructor_id, assignment_id)
    if not baseline:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No baseline found for instructor '{instructor_id}' / "
                f"assignment '{assignment_id}'. "
                "Run POST /instructors/{id}/baseline/rebuild first."
            ),
        )
    return baseline
