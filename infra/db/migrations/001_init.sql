CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS job_roles (
  job_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  fine_role TEXT NOT NULL,
  coarse_role TEXT NOT NULL,
  city TEXT,
  salary_min_k INT,
  salary_max_k INT,
  required_skills JSONB DEFAULT '[]'::jsonb,
  -- JobBERT-v3 输出 1024 维（旧的 384 是 SBERT 的维度，是 bug）
  embedding VECTOR(1024),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skills (
  skill_id TEXT PRIMARY KEY,
  skill_name TEXT NOT NULL UNIQUE,
  aliases JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS user_profiles (
  user_id TEXT PRIMARY KEY,
  profile_json JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS learning_resources (
  resource_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  provider TEXT NOT NULL,
  level TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trend_events (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  event_date DATE NOT NULL,
  summary TEXT NOT NULL,
  impact TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
  edge_id BIGSERIAL PRIMARY KEY,
  src_type TEXT NOT NULL,
  src_id TEXT NOT NULL,
  dst_type TEXT NOT NULL,
  dst_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  weight DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7,
  source_time TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_roles_embedding ON job_roles USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(src_type, src_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_dst ON graph_edges(dst_type, dst_id);