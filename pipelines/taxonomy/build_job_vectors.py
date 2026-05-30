"""
构建岗位向量并写入 pgvector（pgvector 三件套之二）

流程:读 fine_grained_roles_v1.json (69 岗位) -> JobBERT-v3 编码 ->
      UPSERT 进 postgres 的 job_roles 表(含 embedding 列)
运行:python -m pipelines.taxonomy.build_job_vectors

关键约束(必须和 recall.py / recommender._load_engine 完全一致,否则
库里向量与线上 query 向量不在同一语义空间,ANN 召回会错):
  - 模型:TechWolf/JobBERT-v3
  - 文本拼法:f"{role_name}. Required skills: {required_skills 去(方向)}"
    用 required_skills(15个宽画像),不是 core_skills
  - normalize_embeddings=True(余弦用)
"""

import json
import os

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

ROLES_JSON = "data/gold/fine_grained_roles_v1.json"
MODEL_NAME = "TechWolf/JobBERT-v3"
EXPECTED_DIM = 1024  # JobBERT-v3;与 001_init.sql 的 VECTOR(1024) 对齐

# 默认连本机映射出来的 5432;Docker compose 里 postgres 服务对外暴露 5432。
# 在容器/CI 里跑时用 JOBNAV_POSTGRES_DSN 覆盖(指向 postgres:5432)。
DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)


def _clean_skills(skills):
    return [s.replace("(方向)", "").strip() for s in skills if s and s.strip()]


def role_to_text(role: dict) -> str:
    """与 recall.py / recommender 完全一致的岗位文本拼法。"""
    name = role.get("role_name", "")
    skills = _clean_skills(role.get("required_skills", []))
    return f"{name}. Required skills: {', '.join(skills)}"


def main():
    print(">>> 加载岗位库 ...")
    with open(ROLES_JSON, encoding="utf-8") as f:
        roles = json.load(f)
    print(f"    岗位数: {len(roles)}")

    print(">>> 向量化岗位 ...")
    model = SentenceTransformer(MODEL_NAME)
    texts = [role_to_text(r) for r in roles]
    vecs = model.encode(texts, normalize_embeddings=True)
    vecs = np.asarray(vecs, dtype=np.float32)
    dim = vecs.shape[1]
    print(f"    向量维度: {dim}")
    if dim != EXPECTED_DIM:
        raise SystemExit(
            f"[FATAL] 向量维度 {dim} != 预期 {EXPECTED_DIM}。"
            f"检查 001_init.sql 的 VECTOR({EXPECTED_DIM}) 是否与模型一致。"
        )

    print(">>> 写入 pgvector ...")
    with psycopg.connect(DSN) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # 防御:库里维度必须和我们要写的一致(防止用了未重灌的旧 384 表)
            cur.execute(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'job_roles'::regclass AND attname = 'embedding';"
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[0] != EXPECTED_DIM:
                raise SystemExit(
                    f"[FATAL] job_roles.embedding 列维度是 {row[0]},不是 {EXPECTED_DIM}。"
                    f"说明 migration 没用新版重灌。请 `docker compose down -v` 删卷后重起。"
                )

            for r, v in zip(roles, vecs):
                cur.execute(
                    """
                    INSERT INTO job_roles
                        (job_id, title, fine_role, coarse_role,
                         city, salary_min_k, salary_max_k,
                         required_skills, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET
                        title          = EXCLUDED.title,
                        fine_role      = EXCLUDED.fine_role,
                        coarse_role    = EXCLUDED.coarse_role,
                        required_skills = EXCLUDED.required_skills,
                        embedding      = EXCLUDED.embedding;
                    """,
                    (
                        r.get("role_id", "unknown"),
                        r.get("role_name", ""),
                        r.get("fine_role", r.get("role_name", "")),
                        r.get("coarse_role", ""),
                        None,  # city: 岗位库暂无(TODO-4)
                        None,  # salary_min_k
                        None,  # salary_max_k
                        json.dumps(_clean_skills(r.get("required_skills", [])), ensure_ascii=False),
                        v,
                    ),
                )
        conn.commit()

    print(f">>> 完成:已 upsert {len(roles)} 个岗位到 job_roles(含 {EXPECTED_DIM} 维向量)")


if __name__ == "__main__":
    main()