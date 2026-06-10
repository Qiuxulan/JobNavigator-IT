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

    trend_horizon_months: int = 3
    trend_export_dir: str = "data/gold"
    trend_hf_recruitment_dataset: str = "lang-uk/recruitment-dataset-job-descriptions-english"
    trend_hf_local_arrow_path: str = "data/raw/recruitment-dataset-job-descriptions-english-train.arrow"
    trend_hf_local_info_path: str = "data/raw/dataset_info.json"
    trend_hf_sample_limit: int = 0
    trend_jd_min_date: str = "2020-01-01"
    trend_enable_hf_recruitment: bool = True
    trend_hf_local_csv_path: str = "data/raw/recruitment-dataset-job-descriptions-english-train.csv"
    trend_enable_kaggle_linkedin: bool = False
    trend_kaggle_data_dir: str = "data/raw"
    trend_kaggle_sample_limit: int = 0
    trend_kaggle_chunk_size: int = 50000
    trend_enable_linkedin_postings: bool = False
    trend_linkedin_postings_path: str = "data/raw/linkedin_job_postings.csv"
    trend_linkedin_skills_path: str = "data/raw/job_skills.csv"
    trend_linkedin_chunk_size: int = 50000
    trend_linkedin_sample_limit: int = 0
    trend_enable_ai_job_dataset: bool = True
    trend_ai_job_dataset_path: str = "data/raw/ai_job_dataset1.csv"
    trend_ai_job_sample_limit: int = 0
    trend_standardize_max_rows: int = 0
    trend_enable_gdelt: bool = True
    trend_gdelt_role_limit: int = 0
    trend_gdelt_max_records: int = 30
    trend_gdelt_sleep_sec: float = 0.2
    trend_gdelt_batch_size: int = 5
    trend_gdelt_retry_attempts: int = 4
    trend_gdelt_retry_backoff_sec: float = 2.0
    trend_gdelt_bigquery_enabled: bool = True
    trend_gdelt_bigquery_project: str = "jobnavigator-it-bigquery"
    trend_gdelt_bigquery_credentials_path: str = "secrets/service-account-key.json"
    trend_gdelt_bigquery_months: int = 6
    trend_gdelt_bigquery_role_limit: int = 10
    trend_gdelt_bigquery_top_skills: int = 10
    trend_gdelt_bigquery_max_docs_per_role: int = 500
    trend_gdelt_bigquery_events_enabled: bool = False
    trend_gdelt_local_dir: str = "data/GDELT"
    trend_gdelt_local_batch_size: int = 10
    trend_gdelt_local_max_files: int = 0
    trend_gdelt_local_processed_dir: str = "data/gold/gdelt_gkg_processed"
    trend_gdelt_raw_export_limit: int = 20000
    trend_enable_google_trends: bool = False
    trend_enable_github: bool = True
    trend_enable_arxiv: bool = True
    trend_github_token: str = ""
    trend_google_trends_geo: str = ""
    trend_tech_role_limit: int = 0
    trend_tech_skill_limit: int = 20
    trend_github_months: int = 6
    trend_github_top_items: int = 5
    trend_arxiv_months: int = 6
    trend_arxiv_max_results: int = 50
    trend_patchtst_lookback_months: int = 77

    model_config = SettingsConfigDict(env_file=".env", env_prefix="JOBNAV_")


settings = Settings()
