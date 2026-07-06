from app.core.config import Settings


def test_default_embedding_configuration_targets_zhipu() -> None:
    settings = Settings(_env_file=None)
    assert settings.embedding_provider == "api"
    assert settings.embedding_model == "embedding-3"
    assert settings.embedding_base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert settings.embedding_dimensions == 1024
