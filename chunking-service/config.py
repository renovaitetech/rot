from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_service_url: str = "http://storage-service:8002"
    deepseek_api_key: str = ""
    deepseek_api_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    chunk_size: int = 512
    default_strategy: str = "agentic"


settings = Settings()
