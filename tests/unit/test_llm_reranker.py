"""llm_reranker 单元测试:输出解析、排列校验与降级行为(matching v4)。"""

import json

from app.services.llm_reranker import _parse_ranking, apply_rerank


def _rows(ids):
    return [{"job_id": i, "role_score": 0.9 - n * 0.1} for n, i in enumerate(ids)]


def test_parse_ranking_accepts_full_permutation():
    payload = json.dumps(
        {"ranking": ["b", "a"], "reasons": {"a": "ok", "b": "better"}}
    )
    out = _parse_ranking(payload, ["a", "b"])
    assert out is not None
    assert out["ranking"] == ["b", "a"]
    assert out["reasons"]["b"] == "better"


def test_parse_ranking_rejects_missing_or_extra_ids():
    assert _parse_ranking(json.dumps({"ranking": ["a"]}), ["a", "b"]) is None
    assert _parse_ranking(json.dumps({"ranking": ["a", "b", "c"]}), ["a", "b"]) is None
    assert _parse_ranking("not json", ["a", "b"]) is None
    assert _parse_ranking(json.dumps({"reasons": {}}), ["a", "b"]) is None


def test_apply_rerank_reorders_head_and_keeps_tail():
    ranked = _rows(["a", "b", "c"])
    out = apply_rerank(ranked, {"ranking": ["b", "a", "c"], "reasons": {"b": "why"}})
    assert [r["job_id"] for r in out] == ["b", "a", "c"]
    assert out[0]["llm_reason"] == "why"


def test_apply_rerank_none_is_noop():
    ranked = _rows(["a", "b"])
    assert apply_rerank(ranked, None) is ranked


def test_llm_rerank_returns_none_without_api_key(monkeypatch):
    from app.core.config import settings
    from app.services.llm_reranker import llm_rerank

    monkeypatch.setattr(settings, "llm_api_key", "")
    assert llm_rerank(None, _rows(["a", "b"]), {}) is None
