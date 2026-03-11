from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jina_embedding_api_key: str = ""
    jina_embedding_base_url: str = "https://api.jina.ai/v1"
    jina_embedding_model: str = "jina-embeddings-v4"
    embedding_dimensions: int = 2048
    redis_url: str = "redis://redis:6379"
    cache_ttl: int = 86400 * 30  # 30 days


settings = Settings()
