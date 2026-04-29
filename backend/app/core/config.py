from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_KEY = "changeme-in-production-use-long-random-string-min-32-chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite+aiosqlite:///./statdash.db"
    secret_key: str = _INSECURE_KEY
    valkey_url: str = "redis://localhost:6379"
    config_path: str = "../config/config.yaml"
    cors_origins: list[str] = ["http://localhost:5173"]
    api_token: str | None = None

    @field_validator("secret_key")
    @classmethod
    def warn_insecure_key(cls, v: str) -> str:
        if v == _INSECURE_KEY:
            import warnings
            warnings.warn(
                "SECRET_KEY is set to the default insecure value. "
                "Set SECRET_KEY in your .env file before deploying.",
                stacklevel=2,
            )
        return v


settings = Settings()
