from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_service_url: str = "http://storage-service:8002"
    qdrant_service_url: str = "http://qdrant-service:8006"
    embedding_service_url: str = "http://embedding-service:8005"

    # Inference provider: "ollama" or "openrouter"
    inference_provider: str = "ollama"

    # Ollama settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"

    # OpenRouter settings
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3.5-9b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    target_long_side: int = 2048


settings = Settings()
