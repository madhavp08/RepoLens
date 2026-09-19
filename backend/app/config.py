from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://repolens:repolens@localhost:5432/repolens"
    github_token: str | None = None
    github_api_base: str = "https://api.github.com"
    cors_origins: str = "http://localhost:3000"
    wave0_max_doc_files: int = 200
    wave0_max_file_bytes: int = 1_000_000
    wave0_max_releases: int = 30


settings = Settings()
