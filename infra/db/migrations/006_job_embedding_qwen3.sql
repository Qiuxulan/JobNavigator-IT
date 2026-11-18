-- 006_job_embedding_qwen3.sql
-- 2026-11-05 matching v4:岗位向量模型从 TechWolf/JobBERT-v3 (1024 维) 升级为
-- Qwen/Qwen3-Embedding-4B (2560 维)。
-- embedding 是 job_roles 的唯一向量列;旧向量在新语义空间下无意义,
-- 直接清空后由 pipelines.taxonomy.build_job_vectors 用新模型重灌。
-- HNSW 索引随列类型变更失效,需重建。

BEGIN;

-- 清空旧维度向量(语义空间已换,旧值不可复用)
UPDATE job_roles SET embedding = NULL;

-- 必须先删旧 HNSW 索引:pgvector 的 vector 类型索引维度上限 2000,
-- 带着索引无法把列改到 2560 维。
DROP INDEX IF EXISTS idx_job_roles_embedding;

-- 扩展列维度 1024 -> 2560
ALTER TABLE job_roles ALTER COLUMN embedding TYPE vector(2560);

-- 注意:2560 维超过 vector 类型 HNSW/IVFFlat 上限 2000。
-- 若改用 halfvec(上限 4000 维)需同时改 recall 的算子与写入类型。
-- 当前 job_roles 仅 99 行,ORDER BY embedding <=> $1 顺序扫是毫秒级,
-- 不建 ANN 索引;岗位规模上到万级时再切 halfvec + HNSW。

COMMIT;
