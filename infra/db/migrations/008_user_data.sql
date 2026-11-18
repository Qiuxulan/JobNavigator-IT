-- 008_user_data.sql — 用户个人数据：profiles / favorites / history
-- 微信小程序「我的」页面后端存储。无登录体系，按 X-Client-Id（客户端本地 UUID）隔离数据。
-- 迁移执行：psql -h localhost -U jobnav -d jobnavigator -f infra/db/migrations/008_user_data.sql

BEGIN;

-- 001_init.sql 遗留 user_profiles(user_id, profile_json)：无任何代码引用且 0 行，
-- 检测到旧结构（含 user_id 列）则改名让出表名（保留可回滚），新表按 client_id 主键重建。
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'user_profiles' AND column_name = 'user_id') THEN
    ALTER TABLE user_profiles RENAME TO user_profiles_legacy;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS user_profiles (
  client_id   TEXT PRIMARY KEY,
  nickname    TEXT,
  joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_favorites (
  client_id  TEXT NOT NULL REFERENCES user_profiles(client_id) ON DELETE CASCADE,
  item_type  TEXT NOT NULL,           -- job | news | path
  item_id    TEXT NOT NULL,
  title      TEXT NOT NULL DEFAULT '',
  payload    JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (client_id, item_type, item_id)
);

CREATE TABLE IF NOT EXISTS user_history (
  id         BIGSERIAL PRIMARY KEY,
  client_id  TEXT NOT NULL REFERENCES user_profiles(client_id) ON DELETE CASCADE,
  item_type  TEXT NOT NULL,           -- news | trend | match
  item_id    TEXT NOT NULL,
  title      TEXT NOT NULL DEFAULT '',
  payload    JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (client_id, item_type, item_id)
);

CREATE INDEX IF NOT EXISTS idx_user_history_client ON user_history(client_id, item_type, created_at DESC);

COMMIT;
