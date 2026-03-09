from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    storage_service_url: str = "http://storage-service:8002"


settings = Settings()
