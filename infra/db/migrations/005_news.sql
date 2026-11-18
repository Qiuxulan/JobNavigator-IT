-- 005_news.sql — 实时新闻情报层：news_items 表
-- 迁移执行：psql -h localhost -U jobnav -d jobnavigator -f infra/db/migrations/005_news.sql

CREATE TABLE IF NOT EXISTS news_items (
  id BIGSERIAL PRIMARY KEY,
  news_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  url_resolved BOOLEAN DEFAULT FALSE,
  source TEXT,
  lang TEXT CHECK (lang IN ('zh', 'en')),
  published_at TIMESTAMPTZ,
  summary TEXT,
  content_text TEXT,
  category TEXT CHECK (category IN (
    'hiring', 'layoff', 'funding', 'product_release',
    'research', 'policy', 'security', 'tech_general'
  )),
  skills TEXT[],
  role_ids TEXT[],
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_items_published_at ON news_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_items_category ON news_items(category);
CREATE INDEX IF NOT EXISTS idx_news_items_source ON news_items(source);
CREATE INDEX IF NOT EXISTS idx_news_items_skills ON news_items USING GIN (skills);
