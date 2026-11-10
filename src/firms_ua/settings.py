"""
Environment-driven settings.
"""

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration read from environment / `.env`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FIRMS_", extra="ignore")

    map_key: SecretStr = Field(validation_alias=AliasChoices("FIRMS_MAP_KEY", "MAP_KEY"))
    # Local folder ("./data": layers are sub-folders) or a bucket prefix ("gs://firms-ua-dev": the layer is appended).
    storage_root: str = "./data"
    gcp_project: str | None = None  # only needed for gs:// storage roots
    max_day_range: int = 5
    # Ukraine bbox (west, south, east, north), slightly buffered; clipped to polygon in silver.
    bbox: tuple[float, float, float, float] = (22.1, 44.4, 40.2, 52.4)
    request_timeout_s: float = 60.0
    max_retries: int = 5
    log_level: str = "INFO"

    @field_validator("map_key", mode="before")
    @classmethod
    def _strip_key(cls, value: object) -> object:
        """
        Drop surrounding whitespace (for example a trailing newline stored in Secret Manager).
        """
        return value.strip() if isinstance(value, str) else value
