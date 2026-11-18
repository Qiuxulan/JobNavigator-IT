"""
构建岗位向量并写入 pgvector(pgvector 三件套之二)

流程:读 role_profiles_v3.json(v3 真实画像:12 万 JD 近期加权技能频率 +
      趋势动量 + 薪资);缺文件回退 role_profiles_v2.json -> fine_grained_roles_v1.json
      -> Qwen3-Embedding-4B 编码 -> UPSERT 进 postgres 的 job_roles 表(含 embedding 列)
运行:python -m pipelines.taxonomy.build_job_vectors

v4(2026-11-05):模型从 TechWolf/JobBERT-v3(1024 维)升级为
Qwen/Qwen3-Embedding-4B(2560 维),配合 migration 006 与
infra/db/migrations/006_job_embedding_qwen3.sql 的列维度变更。

v3 文本拼法(替代 v2 的 "role_name + 技能名列表"):
  "{role_name}. This {coarse_role} role typically involves {top6 技能}.
   Required skills: {top15 技能}. Typical job titles: {top5 example_titles}."
使 embedding 承载真实 JD 语义(职责概括 + 技能 + 真实在招 title),
而不是干巴巴的技能词表。

关键约束(必须和 recall.py / career_pathway_service._profile_to_query_text
保持同一语义风格与同一编码配置,否则库里向量与线上 query 向量不在同一
语义空间,ANN 召回会错):
  - 模型:Qwen/Qwen3-Embedding-4B(matching v4 起;旧为 TechWolf/JobBERT-v3)
  - normalize_embeddings=True(余弦用)
"""

import json
import os
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
ROLE_PROFILES_V3 = GOLD_DIR / "role_profiles_v3.json"
ROLES_JSON_V3 = GOLD_DIR / "fine_grained_roles_v3.json"
ROLE_PROFILES_V2 = GOLD_DIR / "role_profiles_v2.json"
ROLES_JSON_V1 = GOLD_DIR / "fine_grained_roles_v1.json"
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"
EXPECTED_DIM = 2560  # Qwen3-Embedding-4B;与 006_job_embedding_qwen3.sql 的 VECTOR(2560) 对齐

# 默认连本机映射出来的 5432;Docker compose 里 postgres 服务对外暴露 5432。
# 在容器/CI 里跑时用 JOBNAV_POSTGRES_DSN 覆盖(指向 postgres:5432)。
DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)


def load_roles() -> tuple[list[dict], str]:
    """优先 v3 画像;缺文件回退 v2 画像 -> v3 岗位库 -> v1 小样本库。"""
    for path in (ROLE_PROFILES_V3, ROLE_PROFILES_V2, ROLES_JSON_V3, ROLES_JSON_V1):
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            roles = payload.get("roles", payload if isinstance(payload, list) else [])
            return roles, str(path)
    raise SystemExit("[FATAL] 找不到任何岗位库文件(role_profiles_v3/v2 ...)")


def _clean_skills(skills):
    return [s.replace("(方向)", "").strip() for s in skills if s and s.strip()]


def role_to_text(role: dict, source: str = "") -> str:
    """岗位 embedding 文本。v3 用真实画像拼 JD 风格文本;旧库回退保持原拼法。"""
    name = role.get("role_name", "")
    required = _clean_skills(role.get("required_skills", []))
    core = _clean_skills(role.get("core_skills", []))
    skills = list(dict.fromkeys([*required, *core]))

    if ROLE_PROFILES_V3.name in source:
        skill_names = _clean_skills(role.get("core_skills") or []) + [
            s for s in skills if s not in set(role.get("core_skills") or [])
        ]
        skill_names = list(dict.fromkeys(skill_names))[:15]
        involves = ", ".join(skill_names[:6]) or "modern software tooling"
        coarse = role.get("coarse_role") or "IT"
        titles = (role.get("example_titles") or [])[:5]
        title_str = ", ".join(str(t) for t in titles)
        text = (
            f"{name}. This {coarse} role typically involves {involves}. "
            f"Required skills: {', '.join(skill_names)}."
        )
        if title_str:
            text += f" Typical job titles: {title_str}."
        return text

    # v2 / v1 回退:沿用旧拼法
    return f"{name}. Required skills: {', '.join(skills)}"


def main():
    print(">>> 加载岗位库 ...")
    roles, source = load_roles()
    print(f"    岗位数: {len(roles)} (来源: {source})")

    print(">>> 向量化岗位 ...")
    import torch

    # 共享 GPU 每卡常被占 ~73GB、仅 ~7.6GB 空闲;4B bf16 权重 ~8GB 放不下,
    # 所以优先 CPU(bf16,机器内存充裕);只有检测到卡上剩余显存充足才上 GPU。
    device = "cpu"
    if torch.cuda.is_available():
        free_b, _total_b = torch.cuda.mem_get_info()
        if free_b > 9 * 1024**3:
            device = "cuda"
    print(f"    编码设备: {device}")
    model = SentenceTransformer(
        MODEL_NAME, device=device, model_kwargs={"dtype": "bfloat16"}
    )
    texts = [role_to_text(r, source) for r in roles]
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=8)
    vecs = np.asarray(vecs, dtype=np.float32)
    dim = vecs.shape[1]
    print(f"    向量维度: {dim}")
    print(f"    文本样例: {texts[0][:160]}")
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
