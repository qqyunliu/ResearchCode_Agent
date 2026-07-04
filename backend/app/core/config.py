from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./research_code_agent.db"
    max_source_bytes: int = 2 * 1024 * 1024
    embedding_provider: str = "local"
    embedding_model: str = (
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_path: str = "./qdrant_storage"
    search_default_limit: int = 10
    search_max_limit: int = 50
    chunk_max_content_chars: int = 4000

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RCA_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
