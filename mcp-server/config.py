from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    embedding_service_url: str = "http://embedding-service:8005"
    qdrant_service_url: str = "http://qdrant-service:8006"
    search_service_url: str = "http://search-service:8007"


settings = Settings()
