"""
services/cloudant_service.py
-----------------------------
CRUD wrappers for all four Cloudant collections:
  - submissions
  - instructor_baselines
  - flags
  - audit_log

Uses the ibmcloudant Python SDK (CloudantV1).
Each public method translates between Pydantic models and raw Cloudant JSON.

Design note: Cloudant uses `_id` / `_rev` internally.  We store our own
`submission_id`, `flag_id` etc. as top-level fields AND as `_id` so we can
do O(1) lookups without a secondary index.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Collection names
COL_SUBMISSIONS = "submissions"
COL_BASELINES = "instructor_baselines"
COL_FLAGS = "flags"
COL_AUDIT_LOG = "audit_log"


def _get_cloudant_client(url: str, apikey: str):
    """Return an authenticated CloudantV1 client."""
    try:
        from ibmcloudant.cloudant_v1 import CloudantV1
        from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
    except ImportError as exc:
        raise RuntimeError(
            "ibmcloudant package is not installed. Run: pip install ibmcloudant"
        ) from exc

    authenticator = IAMAuthenticator(apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(url)
    return client


class CloudantService:
    """
    Wraps all Cloudant operations for Plagiarism Intelligence.

    One instance should be created at startup and shared across requests
    (use FastAPI dependency injection or a module-level singleton).
    """

    def __init__(self, url: str, apikey: str) -> None:
        self._client = _get_cloudant_client(url, apikey)
        self._ensure_databases()

    # ── Database bootstrap ────────────────────────────────────────────────────

    def _ensure_databases(self) -> None:
        """Create collections if they don't exist yet (idempotent)."""
        for db_name in (COL_SUBMISSIONS, COL_BASELINES, COL_FLAGS, COL_AUDIT_LOG):
            try:
                self._client.put_database(db=db_name).get_result()
                logger.info("Cloudant: created database '%s'", db_name)
            except Exception as exc:  # noqa: BLE001
                # 412 = already exists — that's fine
                if "already exists" in str(exc).lower() or "412" in str(exc):
                    logger.debug("Cloudant: database '%s' already exists", db_name)
                else:
                    logger.warning("Cloudant: could not ensure database '%s': %s", db_name, exc)

    # ── Submissions ───────────────────────────────────────────────────────────

    def create_submission(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Insert a new submission document.  `doc` must have `submission_id`."""
        doc["_id"] = doc["submission_id"]
        result = self._client.post_document(
            db=COL_SUBMISSIONS, document=doc
        ).get_result()
        return result

    def get_submission(self, submission_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a submission by its submission_id.  Returns None if not found."""
        try:
            return self._client.get_document(
                db=COL_SUBMISSIONS, doc_id=submission_id
            ).get_result()
        except Exception as exc:  # noqa: BLE001
            if "404" in str(exc) or "not found" in str(exc).lower():
                return None
            raise

    def update_submission(self, submission_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge `updates` into the existing submission document."""
        existing = self.get_submission(submission_id)
        if existing is None:
            raise KeyError(f"Submission '{submission_id}' not found")
        existing.update(updates)
        result = self._client.put_document(
            db=COL_SUBMISSIONS, doc_id=submission_id, document=existing
        ).get_result()
        return result

    def query_submissions(self, selector: dict[str, Any]) -> list[dict[str, Any]]:
        """Run a Cloudant selector query against the submissions collection."""
        result = self._client.post_find(
            db=COL_SUBMISSIONS,
            selector=selector,
            limit=200,
        ).get_result()
        return result.get("docs", [])

    # ── Flags ─────────────────────────────────────────────────────────────────

    def create_flag(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Insert a new flag document.  `doc` must have `flag_id`."""
        doc["_id"] = doc["flag_id"]
        return self._client.post_document(
            db=COL_FLAGS, document=doc
        ).get_result()

    def get_flag(self, flag_id: str) -> Optional[dict[str, Any]]:
        try:
            return self._client.get_document(
                db=COL_FLAGS, doc_id=flag_id
            ).get_result()
        except Exception as exc:  # noqa: BLE001
            if "404" in str(exc) or "not found" in str(exc).lower():
                return None
            raise

    def update_flag(self, flag_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_flag(flag_id)
        if existing is None:
            raise KeyError(f"Flag '{flag_id}' not found")
        existing.update(updates)
        return self._client.put_document(
            db=COL_FLAGS, doc_id=flag_id, document=existing
        ).get_result()

    def get_flags_for_submission(self, submission_id: str) -> list[dict[str, Any]]:
        result = self._client.post_find(
            db=COL_FLAGS,
            selector={"submission_id": {"$eq": submission_id}},
            limit=100,
        ).get_result()
        return result.get("docs", [])

    # ── Instructor Baselines ──────────────────────────────────────────────────

    def get_baseline(self, instructor_id: str, assignment_id: str) -> Optional[dict[str, Any]]:
        doc_id = f"{instructor_id}::{assignment_id}"
        try:
            return self._client.get_document(
                db=COL_BASELINES, doc_id=doc_id
            ).get_result()
        except Exception as exc:  # noqa: BLE001
            if "404" in str(exc) or "not found" in str(exc).lower():
                return None
            raise

    def upsert_baseline(self, instructor_id: str, assignment_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        doc_id = f"{instructor_id}::{assignment_id}"
        doc["_id"] = doc_id
        doc["instructor_id"] = instructor_id
        doc["assignment_id"] = assignment_id

        existing = self.get_baseline(instructor_id, assignment_id)
        if existing:
            doc["_rev"] = existing["_rev"]
            return self._client.put_document(
                db=COL_BASELINES, doc_id=doc_id, document=doc
            ).get_result()
        else:
            return self._client.post_document(
                db=COL_BASELINES, document=doc
            ).get_result()

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def append_audit_entry(self, entry: dict[str, Any]) -> None:
        """
        Append an immutable audit record.  Called by the scoring engine for
        every run — never deleted, only appended.
        """
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            self._client.post_document(db=COL_AUDIT_LOG, document=entry).get_result()
        except Exception as exc:  # noqa: BLE001
            # Audit failures should never block the main pipeline
            logger.error("Failed to write audit log entry: %s", exc)


def get_cloudant_service() -> CloudantService:
    """FastAPI dependency / module-level factory."""
    from config import get_settings
    s = get_settings()
    return CloudantService(url=s.cloudant_url, apikey=s.cloudant_apikey)
