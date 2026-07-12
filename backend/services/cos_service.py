"""
services/cos_service.py
------------------------
IBM Cloud Object Storage (COS) helpers using the ibm-cos-sdk (boto3-compatible).

Provides:
    upload_file(file_bytes, key)    → public/presigned URL string
    get_presigned_url(key)          → short-lived download URL
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class COSService:
    """Wraps IBM COS S3-compatible API for raw file storage."""

    def __init__(
        self,
        api_key: str,
        instance_crn: str,
        endpoint_url: str,
        bucket: str,
    ) -> None:
        try:
            import ibm_boto3
            from ibm_botocore.client import Config
        except ImportError as exc:
            raise RuntimeError(
                "ibm-cos-sdk is not installed. Run: pip install ibm-cos-sdk"
            ) from exc

        self._bucket = bucket
        self._client = ibm_boto3.client(
            "s3",
            ibm_api_key_id=api_key,
            ibm_service_instance_id=instance_crn,
            config=Config(signature_version="oauth"),
            endpoint_url=endpoint_url,
        )

    def upload_file(self, file_bytes: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        """
        Upload `file_bytes` to COS under `key` and return the object URL.

        The URL is stored in the Submission document as `file_url` and can be
        used to retrieve the raw file later.  It is NOT a presigned URL —
        it is the canonical public endpoint URL (access depends on bucket policy).
        """
        import io
        self._client.upload_fileobj(
            io.BytesIO(file_bytes),
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        endpoint = self._client.meta.endpoint_url
        url = f"{endpoint}/{self._bucket}/{key}"
        logger.info("Uploaded file to COS: %s", url)
        return url

    def get_presigned_url(self, key: str, expiry_seconds: int = 3600) -> str:
        """Return a time-limited presigned URL for downloading `key`."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiry_seconds,
        )


def get_cos_service() -> COSService:
    """FastAPI dependency / module-level factory."""
    from config import get_settings
    s = get_settings()
    return COSService(
        api_key=s.cos_api_key,
        instance_crn=s.cos_instance_crn,
        endpoint_url=s.cos_endpoint_url,
        bucket=s.cos_bucket,
    )
