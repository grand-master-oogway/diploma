"""
Environment-driven settings.
"""

from datetime import date

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from firms_ua.common.secrets import clean_secret, read_secret
from firms_ua.common.sources import SNPP_DEFAULT_LAST_DAY


class Settings(BaseSettings):
    """
    Runtime configuration read from environment / `.env`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FIRMS_", extra="ignore")

    map_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("FIRMS_MAP_KEY", "MAP_KEY"))
    # Secret Manager resource ("projects/<project>/secrets/<name>"), used when no key is set in the environment.
    map_key_secret: str | None = None
    # Local folder ("./data": layers are sub-folders) or a bucket prefix ("gs://firms-ua-dev": the layer is appended).
    storage_root: str = "./data"
    gcp_project: str | None = None  # only needed for gs:// storage roots
    max_day_range: int = 5
    # Ukraine bbox (west, south, east, north), slightly buffered; silver keeps only points within `border_buffer_km`.
    bbox: tuple[float, float, float, float] = (22.1, 44.4, 40.2, 52.4)
    request_timeout_s: float = 60.0
    max_retries: int = 5
    log_level: str = "INFO"
    # Client-side MAP_KEY budget: FIRMS allows 5,000 transactions per 10 minutes; keep a safety margin.
    budget_transactions: int = 4500
    budget_period_s: float = 600.0
    # Last day Suomi NPP delivers data (delivery ceased); later days are not requested.
    snpp_last_day: date = SNPP_DEFAULT_LAST_DAY
    # Service account the silver assets act as (impersonation; gs:// roots only). Unset: the process's own credentials.
    silver_service_account: str | None = None
    # Silver keeps detections inside Ukraine plus this strip outside the border (flagged by `in_ukraine`).
    border_buffer_km: float = 30.0

    @field_validator("map_key", mode="before")
    @classmethod
    def _strip_key(cls, value: object) -> object:
        """
        Drop whitespace, a byte-order mark and surrounding quotes that stick to a pasted key.
        """
        return clean_secret(value) if isinstance(value, str) else value

    def get_map_key(self) -> str:
        """
        Return the MAP_KEY: from the environment if set, otherwise from Secret Manager.

        Raises:
            ValueError: If neither `FIRMS_MAP_KEY` nor `FIRMS_MAP_KEY_SECRET` is set.
        """
        if self.map_key is not None:
            return self.map_key.get_secret_value()
        if self.map_key_secret:
            return read_secret(self.map_key_secret)
        msg = "set FIRMS_MAP_KEY (local) or FIRMS_MAP_KEY_SECRET (Secret Manager)"
        raise ValueError(msg)
