from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_service_url: str = "http://storage-service:8002"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    target_long_side: int = 2048


settings = Settings()
