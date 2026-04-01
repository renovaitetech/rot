from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_service_url: str = "http://storage-service:8002"

    # Vision provider: "ollama" or "openrouter"
    vision_provider: str = "ollama"

    # Ollama settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"

    # OpenRouter settings
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3.5-122b-a10b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Rendering
    target_long_side: int = 2048


settings = Settings()
