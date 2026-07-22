from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Peppol Lookup API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_context_path: str = Field(default="/", validation_alias="APP_CONTEXT_PATH")
    log_level: str = "INFO"
    log_format: str = "json"
    allowed_origins_raw: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")
    json_pretty_print: bool = False
    peppol_lookup_environments_raw: str = Field(
        default="prod,test", validation_alias="PEPPOL_LOOKUP_ENVIRONMENTS"
    )
    peppol_directory_prod_url: str = Field(
        default="https://directory.peppol.eu", validation_alias="PEPPOL_DIRECTORY_PROD_URL"
    )
    peppol_directory_test_url: str = Field(
        default="https://test-directory.peppol.eu", validation_alias="PEPPOL_DIRECTORY_TEST_URL"
    )
    peppol_lookup_service_url: str = Field(
        default="https://api-lookup.peppol.org", validation_alias="PEPPOL_LOOKUP_SERVICE_URL"
    )
    peppol_sml_prod_dns_zone: str = Field(
        default="participant.sml.prod.tech.peppol.org", validation_alias="PEPPOL_SML_PROD_DNS_ZONE"
    )
    peppol_sml_test_dns_zone: str = Field(
        default="participant.sml.test.tech.peppol.org",
        validation_alias="PEPPOL_SML_TEST_DNS_ZONE",
    )
    peppol_source_timeout_ms: int = Field(default=8000, validation_alias="PEPPOL_SOURCE_TIMEOUT_MS")
    peppol_cache_ttl_seconds: int = Field(default=900, validation_alias="PEPPOL_CACHE_TTL_SECONDS")
    peppol_include_raw_max_bytes: int = Field(
        default=65536, validation_alias="PEPPOL_INCLUDE_RAW_MAX_BYTES"
    )
    peppol_codelist_source_url: str = Field(
        default="https://docs.peppol.eu/edelivery/codelists/",
        validation_alias="PEPPOL_CODELIST_SOURCE_URL",
    )
    peppol_codelist_cache_dir: str = Field(
        default="data/codelists", validation_alias="PEPPOL_CODELIST_CACHE_DIR"
    )
    peppol_codelist_refresh_seconds: int = Field(
        default=86400, validation_alias="PEPPOL_CODELIST_REFRESH_SECONDS"
    )
    peppol_codelist_required: bool = Field(
        default=True, validation_alias="PEPPOL_CODELIST_REQUIRED"
    )
    peppol_codelist_auto_refresh: bool = Field(
        default=False, validation_alias="PEPPOL_CODELIST_AUTO_REFRESH"
    )
    peppol_rate_limit_requests: int = Field(
        default=60, validation_alias="PEPPOL_RATE_LIMIT_REQUESTS"
    )
    peppol_rate_limit_window_seconds: int = Field(
        default=60, validation_alias="PEPPOL_RATE_LIMIT_WINDOW_SECONDS"
    )
    peppol_directory_enabled: bool = Field(
        default=True, validation_alias="PEPPOL_DIRECTORY_ENABLED"
    )
    peppol_sml_enabled: bool = Field(default=True, validation_alias="PEPPOL_SML_ENABLED")
    peppol_smp_enabled: bool = Field(default=True, validation_alias="PEPPOL_SMP_ENABLED")
    peppol_lookup_service_enabled: bool = Field(
        default=True, validation_alias="PEPPOL_LOOKUP_SERVICE_ENABLED"
    )

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

    @property
    def peppol_lookup_environments(self) -> list[str]:
        return [
            environment.strip().lower()
            for environment in self.peppol_lookup_environments_raw.split(",")
            if environment.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

