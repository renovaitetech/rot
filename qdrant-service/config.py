from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    documents_collection: str = "documents"
    chunks_collection: str = "chunks"
    embedding_dimensions: int = 2048


settings = Settings()
