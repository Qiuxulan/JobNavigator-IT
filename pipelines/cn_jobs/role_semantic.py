"""岗位归类的语义兜底：规则表没命中的标题，用 Qwen3-Embedding 与 99 个岗位画像做近邻匹配。

    from pipelines.cn_jobs.role_semantic import SemanticRoleAssigner
    assigner = SemanticRoleAssigner(role_by_id)
    extra = assigner.assign(titles)   # {title: (role_id, similarity)}

- 角色锚点向量与“标题 -> 角色”结果都缓存在 data/gold/ 下，每日 build_market 只对
  新出现的标题做编码，常规运行零 GPU 开销。
- 相似度低于阈值（默认 0.50，按 2026-11 校准，见 reports/eval/role_semantic_fallback_eval.json）
  的标题继续回退到 role_071（General Engineering 兜底）。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
CACHE_PATH = GOLD / "cn_role_semantic_fallback.json"
ANCHOR_PATH = GOLD / "cn_role_anchor_emb.npz"
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"
SIM_THRESHOLD = 0.50


def job_key_text(job: dict) -> tuple[str, str]:
    """(缓存 key, 编码文本)：标题 + 职能类别 + JD 前 200 字。"""
    import hashlib

    text = " ".join([job.get("title") or "", job.get("category") or "",
                     (job.get("description") or "")[:200]]).strip()
    return hashlib.md5(text.encode("utf-8")).hexdigest(), text


def _device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            free_b, _ = torch.cuda.mem_get_info()
            if free_b > 9 * 1024**3:
                return "cuda"
    except Exception:
        pass
    return "cpu"


def _anchor_text(role: dict, role_zh) -> str:
    skills = role.get("core_skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.strip("[]").split(",") if s.strip()]
    zh = role_zh(role.get("role_name", ""))
    return f"{role.get('role_name', '')}（{zh}）：{role.get('fine_role', '')}，核心技能 {', '.join(skills[:8])}"


class SemanticRoleAssigner:
    def __init__(self, role_by_id: dict, threshold: float = SIM_THRESHOLD):
        self.role_by_id = role_by_id
        self.threshold = threshold
        self.cache: dict[str, dict] = {}
        if CACHE_PATH.exists():
            self.cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        self._model = None
        self._role_ids: list[str] | None = None
        self._anchors: np.ndarray | None = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(MODEL_NAME, device=_device(), model_kwargs={"dtype": "bfloat16"})
        return self._model

    def _role_anchors(self) -> tuple[list[str], np.ndarray]:
        if self._anchors is not None:
            return self._role_ids, self._anchors
        from app.services.role_i18n import role_zh

        role_ids = sorted(self.role_by_id)
        if ANCHOR_PATH.exists():
            saved = np.load(ANCHOR_PATH, allow_pickle=True)
            if list(saved["role_ids"]) == role_ids:
                self._role_ids, self._anchors = role_ids, saved["vecs"].astype(np.float32)
                return self._role_ids, self._anchors
        model = self._load_model()
        texts = [_anchor_text(self.role_by_id[rid], role_zh) for rid in role_ids]
        vecs = np.asarray(model.encode(texts, normalize_embeddings=True, batch_size=8), dtype=np.float32)
        np.savez(ANCHOR_PATH, role_ids=role_ids, vecs=vecs)
        self._role_ids, self._anchors = role_ids, vecs
        return role_ids, vecs

    def assign(self, items: dict[str, str]) -> dict[str, tuple[str, float]]:
        """items: {cache_key: 待编码文本(标题+职能+JD 前 200 字)}。
        返回 {cache_key: (role_id, sim)}，只含相似度过阈值的项。"""
        todo = [k for k in items if k not in self.cache]
        if todo:
            model = self._load_model()
            role_ids, anchors = self._role_anchors()
            texts = [items[k] for k in todo]
            vecs = np.asarray(model.encode(texts, normalize_embeddings=True, batch_size=16), dtype=np.float32)
            sims = vecs @ anchors.T
            best = sims.argmax(axis=1)
            for i, k in enumerate(todo):
                j = int(best[i])
                self.cache[k] = {"role_id": role_ids[j], "sim": round(float(sims[i, j]), 4)}
            CACHE_PATH.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
        out = {}
        for k in items:
            hit = self.cache.get(k)
            if hit and hit["sim"] >= self.threshold:
                out[k] = (hit["role_id"], hit["sim"])
        return out
