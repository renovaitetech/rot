from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_api_url: str = ""
    mcp_server_url: str = "http://mcp-server:8001"
    redis_url: str = "redis://redis:6379"
    max_retries: int = 7
    retry_base_delay: float = 2.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
