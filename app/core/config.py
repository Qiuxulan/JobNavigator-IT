from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JobNavigator-IT API"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    postgres_dsn: str = "postgresql://jobnav:jobnav@postgres:5432/jobnavigator"
    redis_url: str = "redis://redis:6379/0"

    recommendation_top_k: int = 5
    ann_recall_top_n: int = 50

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_sec: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_prefix="JOBNAV_")


settings = Settings()

