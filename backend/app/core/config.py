from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./research_code_agent.db"
    max_source_bytes: int = 2 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RCA_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
