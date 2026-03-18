from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    elasticsearch_url: str = "http://elasticsearch:9200"
    index_name: str = "documents"


settings = Settings()
