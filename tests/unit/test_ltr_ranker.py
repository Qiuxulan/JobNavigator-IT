"""ltr_ranker 单元测试:开关解析、特征对齐、模型缺失降级、单调性 sanity。"""

import numpy as np
import pytest

from app.services import ltr_ranker
from app.services.ltr_ranker import FEATURE_NAMES, extract_features, rank_mode, vectorize


def _fake_row(job_id: str, semantic_raw: float, overlap: int = 2, missing: int = 3):
    from app.schemas.domain import (
        JobRole,
        LearningPath,
        RecommendationItem,
        SkillGap,
    )

    gap = SkillGap(
        missing_skills=[f"m{i}" for i in range(missing)],
        overlap_skills=[f"o{i}" for i in range(overlap)],
    )
    path = LearningPath(target_job_id=job_id, total_steps=1, total_estimated_hours=100, score=0.8, steps=[])
    job = JobRole(job_id=job_id, title=f"Role {job_id}", fine_role="x", coarse_role="y")
    breakdown = {
        "coverage_weighted": 0.4,
        "semantic": semantic_raw,
        "trend_momentum_norm": 0.6,
        "learning_feasibility": 0.8,
    }
    rec = RecommendationItem(
        job=job,
        final_score=0.5,
        semantic_score=semantic_raw,
        constraint_score=0.4,
        path_cost_score=0.2,
        trend_reward_score=0.6,
        explanation="covered=2",
        skill_gap=gap,
    )
    return {
        "job_id": job_id,
        "job": job,
        "semantic_score": semantic_raw,
        "semantic_score_raw": semantic_raw,
        "role_score": 0.5,
        "score_breakdown": breakdown,
        "skill_gap": gap,
        "path": path,
        "recommendation": rec,
    }


class TestRankMode:
    def test_default_is_ltr(self, monkeypatch):
        monkeypatch.delenv("JOBNAV_RANKER", raising=False)
        assert rank_mode() == "ltr"

    def test_all_valid_modes(self, monkeypatch):
        for mode in ("ltr", "llm", "formula", "ltr_fallback_llm", "LTR"):
            monkeypatch.setenv("JOBNAV_RANKER", mode)
            assert rank_mode() == mode.lower()

    def test_unknown_mode_falls_back_to_ltr(self, monkeypatch):
        monkeypatch.setenv("JOBNAV_RANKER", "banana")
        assert rank_mode() == "ltr"


class TestFeatureExtraction:
    def test_extract_features_covers_all_feature_names(self):
        from app.schemas.domain import UserProfile

        row = _fake_row("role_000", semantic_raw=0.62)
        feats = extract_features(row, UserProfile(user_id="t", skills=["python"]))
        assert set(feats) == set(FEATURE_NAMES)
        for value in feats.values():
            assert isinstance(value, float)
        assert feats["n_overlap"] == 2.0
        assert feats["overlap_ratio"] == pytest.approx(2 / 5)
        assert feats["semantic_raw"] == pytest.approx(0.62)

    def test_vectorize_matches_feature_order(self):
        feats = {name: float(i) for i, name in enumerate(FEATURE_NAMES)}
        (vec,) = vectorize([feats])
        assert vec == [float(i) for i in range(len(FEATURE_NAMES))]

    def test_missing_salary_and_trend_become_nan(self):
        from app.schemas.domain import UserProfile

        row = _fake_row("role_000", semantic_raw=0.5)
        feats = extract_features(row, UserProfile(user_id="t", skills=[]), role_profile={})
        assert np.isnan(feats["salary_median_log"])
        assert np.isnan(feats["trend_momentum_clip"])
        assert np.isnan(feats["jd_count_6m_log"])

    def test_target_role_name_match(self):
        from app.schemas.domain import UserProfile

        row = _fake_row("role_000", semantic_raw=0.5)
        profile = UserProfile(user_id="t", skills=[], target_role="Role role_000")
        feats = extract_features(row, profile)
        assert feats["has_target_role"] == 1.0
        assert feats["target_role_name_match"] == 1.0


class TestMissingModelFallback:
    def test_load_model_returns_none_when_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ltr_ranker, "MODEL_PATH", tmp_path / "nope.txt")
        ltr_ranker._model_cache.update({"mtime": None, "booster": None})
        assert ltr_ranker.load_model() is None

    def test_apply_ltr_returns_none_when_model_missing(self, monkeypatch, tmp_path):
        from app.schemas.domain import UserProfile

        monkeypatch.setattr(ltr_ranker, "MODEL_PATH", tmp_path / "nope.txt")
        ltr_ranker._model_cache.update({"mtime": None, "booster": None})
        rows = [_fake_row("a", 0.6), _fake_row("b", 0.5)]
        assert ltr_ranker.apply_ltr(rows, UserProfile(user_id="t", skills=[])) is None


class TestMonotonicitySanity:
    """在合成数据上训一个微型 LambdaRank:semantic_raw 越高预测分越高。"""

    @pytest.fixture()
    def tiny_model_path(self, tmp_path):
        import lightgbm as lgb

        rng = np.random.RandomState(0)
        X, y, groups = [], [], []
        for q in range(20):
            sem = rng.rand(5)
            labels = (sem > 0.8).astype(int) * 3 + ((sem > 0.5) & (sem <= 0.8)).astype(int) * 2
            for s, lab in zip(sem, labels):
                row = {name: 0.5 for name in FEATURE_NAMES}
                row["semantic_raw"] = s
                row["semantic_cal"] = s
                X.append([row[n] for n in FEATURE_NAMES])
                y.append(lab)
            groups.append(5)
        ranker = lgb.LGBMRanker(
            objective="lambdarank", label_gain=[0, 1, 2, 3], n_estimators=50,
            num_leaves=8, min_child_samples=2, random_state=0, verbose=-1,
        )
        ranker.fit(np.array(X), np.array(y), group=np.array(groups))
        path = tmp_path / "tiny.txt"
        ranker.booster_.save_model(str(path))
        return path

    def test_higher_semantic_raw_ranks_first(self, monkeypatch, tiny_model_path):
        from app.schemas.domain import UserProfile

        monkeypatch.setattr(ltr_ranker, "MODEL_PATH", tiny_model_path)
        ltr_ranker._model_cache.update({"mtime": None, "booster": None})

        rows = [_fake_row("low", 0.40), _fake_row("high", 0.95)]
        out = ltr_ranker.apply_ltr(rows, UserProfile(user_id="t", skills=["python"]))
        assert out is not None
        assert out[0]["job_id"] == "high"
        scores = [r["recommendation"].final_score for r in out]
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert scores[0] == pytest.approx(1.0)  # min-max 归一化后最高分为 1

    def test_equal_predictions_normalize_to_half(self):
        scores = [0.3, 0.3, 0.3]
        assert ltr_ranker._normalize_display(scores) == [0.5, 0.5, 0.5]
        assert ltr_ranker._normalize_display([]) == []
        assert ltr_ranker._normalize_display([0.2, 0.6]) == [0.0, 1.0]
