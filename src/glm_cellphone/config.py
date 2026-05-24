from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PHONE_AGENT_API_KEY", "ZAI_API_KEY", "ZAI_KEY"),
    )
    base_url: str = Field(
        default="https://api.z.ai/api/coding/paas/v4",
        validation_alias=AliasChoices("PHONE_AGENT_BASE_URL", "ZAI_BASE_URL"),
    )
    model_name: str = Field(
        default="autoglm-phone-multilingual",
        validation_alias=AliasChoices("PHONE_AGENT_MODEL", "ZAI_MODEL"),
    )
    default_max_steps: int = Field(default=40, validation_alias="PHONE_AGENT_MAX_STEPS")
    default_lang: str = Field(default="en", validation_alias="PHONE_AGENT_LANG")
    adb_path: str | None = Field(default=None, validation_alias="ADB_PATH")
    adb_extra_paths: str = Field(default="", validation_alias="ADB_EXTRA_PATHS")
    state_dir: str = Field(default="data", validation_alias="GLM_CELLPHONE_STATE_DIR")
    public_base_url: str | None = Field(
        default=None,
        validation_alias="GLM_CELLPHONE_PUBLIC_BASE_URL",
    )

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key is None:
            return None
        value = self.api_key.get_secret_value().strip()
        return value or None

    @property
    def extra_adb_paths(self) -> list[str]:
        return [item.strip() for item in self.adb_extra_paths.split(":") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
