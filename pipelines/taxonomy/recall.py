"""
岗位召回 - 第二版(pgvector ANN 持久化)

流程:用户画像 -> JobBERT 编码 -> pgvector 用 <=> 余弦距离 ANN 召回 TopN
对比第一版(内存版):岗位向量不再每次现算,改为离线 build_job_vectors.py
写进 job_roles.embedding,线上只编码 query 向量 + 一次 ANN 查询。

冒烟测试:python -m pipelines.taxonomy.recall
  (需要 postgres 已起 + 已跑过 build_job_vectors.py)

关键约束:query 文本拼法、模型、normalize 必须与 build_job_vectors.py 一致。
"""

import json
import os

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

MODEL_NAME = "TechWolf/JobBERT-v3"
TOP_N = 5

DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)


def profile_to_text(profile: dict) -> str:
    """用户画像文本拼法(与第一版一致)。"""
    skills = profile.get("skills", [])
    target = profile.get("target_role", "")
    return f"Target role: {target}. My skills: {', '.join(skills)}"


def recall_topn(user_vec: np.ndarray, n: int = TOP_N, dsn: str = DSN):
    """用 pgvector <=> (余弦距离) ANN 召回 TopN 岗位。

    返回 list[dict],每条含 job_id/title/coarse_role/required_skills/score,
    其中 score = 余弦相似度 = 1 - 余弦距离(与内存版点积口径一致,越大越相似)。
    """
    user_vec = np.asarray(user_vec, dtype=np.float32)
    with psycopg.connect(dsn) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # <=> 是余弦距离;1 - 距离 = 余弦相似度。ORDER BY 距离升序 = 最相似在前。
            cur.execute(
                """
                SELECT job_id, title, coarse_role, required_skills,
                       1 - (embedding <=> %s) AS score
                FROM job_roles
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s
                LIMIT %s;
                """,
                (user_vec, user_vec, n),
            )
            rows = cur.fetchall()

    results = []
    for job_id, title, coarse_role, required_skills, score in rows:
        # required_skills 列是 JSONB,psycopg 取出来可能是 str 或已解析的 list
        if isinstance(required_skills, str):
            required_skills = json.loads(required_skills)
        results.append(
            {
                "job_id": job_id,
                "title": title,
                "coarse_role": coarse_role,
                "required_skills": required_skills or [],
                "score": float(score),
            }
        )
    return results


def main():
    print(">>> 加载模型 ...")
    model = SentenceTransformer(MODEL_NAME)

    test_user = {
        "skills": ["Python", "SQL", "Machine Learning"],
        "target_role": "AI / Machine Learning Engineer",
    }
    print(f">>> 测试用户: {test_user}")

    user_vec = model.encode(profile_to_text(test_user), normalize_embeddings=True)
    results = recall_topn(user_vec, TOP_N)

    print(f"\n>>> ANN 召回 Top-{TOP_N} 岗位:\n")
    for rank, r in enumerate(results, 1):
        skills = [s.replace("(方向)", "") for s in r["required_skills"]]
        print(f"  #{rank}  [{r['job_id']}] {r['title']}   相似度={r['score']:.3f}")
        print(f"        技能: {', '.join(skills[:6])}")
        print()


if __name__ == "__main__":
    main()