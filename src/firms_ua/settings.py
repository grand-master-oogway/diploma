"""
Environment-driven settings.
"""

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration read from environment / `.env`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FIRMS_", extra="ignore")

    map_key: SecretStr = Field(validation_alias=AliasChoices("FIRMS_MAP_KEY", "MAP_KEY"))
    storage_root: str = "./data"
    max_day_range: int = 5
    # Ukraine bbox (west, south, east, north), slightly buffered; clipped to polygon in silver.
    bbox: tuple[float, float, float, float] = (22.1, 44.4, 40.2, 52.4)
    request_timeout_s: float = 60.0
    max_retries: int = 5
