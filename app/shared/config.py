from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Peppol Lookup API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_context_path: str = Field(default="/", validation_alias="APP_CONTEXT_PATH")
    log_level: str = "INFO"
    log_format: str = "json"
    allowed_origins_raw: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")
    json_pretty_print: bool = False

    @property
    def normalized_context_path(self) -> str:
        value = self.app_context_path.strip()
        if not value or value == "/":
            return ""
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")

    @property
    def allowed_origins(self) -> list[str]:
        value = self.allowed_origins_raw.strip()
        if not value or value == "*":
            return ["*"]
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    @property
    def allow_credentials(self) -> bool:
        return self.allowed_origins != ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

