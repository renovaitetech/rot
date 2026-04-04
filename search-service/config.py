from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    elasticsearch_url: str = "http://elasticsearch:9200"
    documents_index_name: str = "documents"
    chunks_index_name: str = "chunks"


settings = Settings()
