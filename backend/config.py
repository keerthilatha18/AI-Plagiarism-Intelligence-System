"""
config.py
---------
Single source of truth for all environment-variable-backed configuration.
Uses Pydantic v2 BaseSettings so every missing required var raises a clear
ValidationError at startup — no silent fallbacks.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── IBM watsonx.ai ────────────────────────────────────────────────────────
    watsonx_api_key: str = Field(..., alias="WATSONX_API_KEY")
    watsonx_project_id: str = Field(..., alias="WATSONX_PROJECT_ID")
    watsonx_url: str = Field(..., alias="WATSONX_URL")

    # ── IBM Cloudant ──────────────────────────────────────────────────────────
    cloudant_url: str = Field(..., alias="CLOUDANT_URL")
    cloudant_apikey: str = Field(..., alias="CLOUDANT_APIKEY")

    # ── IBM Cloud Object Storage ──────────────────────────────────────────────
    cos_api_key: str = Field(..., alias="COS_API_KEY")
    cos_instance_crn: str = Field(..., alias="COS_INSTANCE_CRN")
    cos_bucket: str = Field(..., alias="COS_BUCKET")
    cos_endpoint_url: str = Field(
        "https://s3.us-south.cloud-object-storage.appdomain.cloud",
        alias="COS_ENDPOINT_URL",
    )

    # ── Scoring thresholds (tunable per-deployment) ───────────────────────────
    paraphrase_cosine_threshold: float = Field(0.82, alias="PARAPHRASE_COSINE_THRESHOLD")
    style_drift_threshold: float = Field(0.40, alias="STYLE_DRIFT_THRESHOLD")

    # ── App ───────────────────────────────────────────────────────────────────
    app_cors_origins: list[str] = Field(
        ["http://localhost:5173", "http://localhost:3000"],
        alias="APP_CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton.  Import this; never import Settings directly."""
    return Settings()
