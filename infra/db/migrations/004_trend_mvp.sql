CREATE TABLE IF NOT EXISTS role_taxonomy (
  role_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  canonical_role TEXT NOT NULL UNIQUE,
  aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
  top_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
  existing_jd_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_jd_jobs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  source_job_id TEXT NOT NULL,
  query_role TEXT,
  raw_job_title TEXT NOT NULL,
  raw_jd_text TEXT,
  salary_mid DOUBLE PRECISION,
  post_date TIMESTAMP,
  education_required TEXT,
  experience_required_years DOUBLE PRECISION,
  company_name TEXT,
  work_arrangement TEXT,
  job_url TEXT,
  raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (source, source_job_id)
);

CREATE TABLE IF NOT EXISTS processed_jd_jobs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  source_job_id TEXT NOT NULL,
  canonical_role TEXT NOT NULL,
  role_id TEXT,
  raw_job_title TEXT NOT NULL,
  raw_jd_text TEXT,
  salary_mid DOUBLE PRECISION,
  post_date TIMESTAMP,
  month DATE NOT NULL,
  education_required TEXT,
  experience_required_years DOUBLE PRECISION,
  company_name TEXT,
  work_arrangement TEXT,
  job_url TEXT,
  role_match_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  matched_by TEXT NOT NULL,
  matched_alias TEXT,
  matched_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
  jd_demand_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  raw_job_ref BIGINT,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (source, source_job_id)
);

CREATE TABLE IF NOT EXISTS jd_role_month_features (
  canonical_role TEXT NOT NULL,
  month DATE NOT NULL,
  job_post_count INT NOT NULL DEFAULT 0,
  unique_company_count INT NOT NULL DEFAULT 0,
  avg_salary_mid DOUBLE PRECISION,
  median_salary_mid DOUBLE PRECISION,
  remote_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  avg_experience_required_years DOUBLE PRECISION,
  education_bachelor_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  education_master_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  jd_skill_hit_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  jd_demand_index DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  source_count INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (canonical_role, month)
);

CREATE TABLE IF NOT EXISTS tech_keyword_month_features (
  canonical_role TEXT NOT NULL,
  keyword TEXT NOT NULL,
  month DATE NOT NULL,
  google_trend_index DOUBLE PRECISION,
  github_repo_count INT,
  github_repo_stars DOUBLE PRECISION,
  arxiv_paper_count INT,
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (canonical_role, keyword, month)
);

CREATE TABLE IF NOT EXISTS role_month_features (
  canonical_role TEXT NOT NULL,
  month DATE NOT NULL,
  jd_demand_index DOUBLE PRECISION,
  job_post_count DOUBLE PRECISION,
  unique_company_count DOUBLE PRECISION,
  avg_salary_mid DOUBLE PRECISION,
  median_salary_mid DOUBLE PRECISION,
  remote_ratio DOUBLE PRECISION,
  avg_experience_required_years DOUBLE PRECISION,
  education_bachelor_ratio DOUBLE PRECISION,
  education_master_ratio DOUBLE PRECISION,
  jd_skill_hit_rate DOUBLE PRECISION,
  gdelt_article_count DOUBLE PRECISION,
  gdelt_sentiment_mean DOUBLE PRECISION,
  gdelt_positive_ratio DOUBLE PRECISION,
  gdelt_negative_ratio DOUBLE PRECISION,
  gdelt_opportunity_index DOUBLE PRECISION,
  gdelt_risk_index DOUBLE PRECISION,
  google_trend_index DOUBLE PRECISION,
  github_repo_count DOUBLE PRECISION,
  github_repo_stars DOUBLE PRECISION,
  arxiv_paper_count DOUBLE PRECISION,
  available_source_count INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (canonical_role, month)
);

CREATE TABLE IF NOT EXISTS role_trend_scores (
  canonical_role TEXT NOT NULL,
  month DATE NOT NULL,
  horizon_months INT NOT NULL DEFAULT 3,
  trend_direction TEXT NOT NULL,
  predicted_demand_index DOUBLE PRECISION NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  main_factors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_urls_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  score_breakdown_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  model_version TEXT NOT NULL DEFAULT 'trend-score-v1',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (canonical_role, month, horizon_months)
);

CREATE INDEX IF NOT EXISTS idx_role_taxonomy_canonical_role ON role_taxonomy(canonical_role);
CREATE INDEX IF NOT EXISTS idx_raw_jd_jobs_post_date ON raw_jd_jobs(post_date);
CREATE INDEX IF NOT EXISTS idx_processed_jd_jobs_role_month ON processed_jd_jobs(canonical_role, month);
CREATE INDEX IF NOT EXISTS idx_raw_gdelt_articles_role_month ON raw_gdelt_articles(canonical_role, publish_date);
CREATE INDEX IF NOT EXISTS idx_gdelt_role_month_features_role_month ON gdelt_role_month_features(canonical_role, month);
CREATE INDEX IF NOT EXISTS idx_tech_keyword_month_features_role_month ON tech_keyword_month_features(canonical_role, month);
CREATE INDEX IF NOT EXISTS idx_role_month_features_role_month ON role_month_features(canonical_role, month);
CREATE INDEX IF NOT EXISTS idx_role_trend_scores_role_month ON role_trend_scores(canonical_role, month DESC);
