from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_service_url: str = "http://storage-service:8002"
    qdrant_service_url: str = "http://qdrant-service:8006"
    embedding_service_url: str = "http://embedding-service:8005"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    target_long_side: int = 2048


settings = Settings()
