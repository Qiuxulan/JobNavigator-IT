"""C 模块证据检索冒烟测试。

闸门逻辑用合成数据，无需索引，CI 可直接跑；
retrieve_evidence 结构测试在缺索引时自动跳过。
"""

import os

import pytest

from app.services.evidence import EvidenceService, _is_relevant, _strong_skill_terms

_INDEX = "data/processed/evidence_index/events"
_needs_index = pytest.mark.skipif(
    not os.path.isdir(_INDEX),
    reason=f"缺证据索引 {_INDEX}（先跑 build_evidence_index.py），跳过检索结构测试",
)


# ---- 四重约束闸门（合成数据，无需索引） ----

def test_gate_drops_pure_url_artifact():
    """只靠 URL 伪词(html/.net)命中的事件应被丢弃。"""
    ev = {"matched_terms": ["html"], "matched_term_count": 1,
          "themes": "TAX_FNCACT;WB_652_ICT_APPLICATIONS", "source_domain": "x.com"}
    assert _is_relevant(ev) is False


def test_gate_keeps_strong_skill_term():
    """命中明确技能词(kubernetes)应保留。"""
    ev = {"matched_terms": ["kubernetes"], "matched_term_count": 1,
          "themes": "GENERAL_NEWS", "source_domain": "techblog.com"}
    assert _is_relevant(ev) is True
    assert "kubernetes" in _strong_skill_terms(["kubernetes", "html"])


def test_gate_drops_junk_domain():
    """垃圾来源(ticker 聚合站)即便有技能词也丢。"""
    ev = {"matched_terms": ["kubernetes"], "matched_term_count": 1,
          "themes": "SOFTWARE", "source_domain": "www.tickerreport.com"}
    assert _is_relevant(ev) is False


def test_gate_ambiguous_needs_theme_cooccurrence():
    """歧义技能词(react)需 科技∧经济 主题共现才放行。"""
    no_econ = {"matched_terms": ["react"], "matched_term_count": 1,
               "themes": "WB_652_ICT_APPLICATIONS;MEDIA_SOCIAL", "source_domain": "news.com"}
    with_econ = {"matched_terms": ["react"], "matched_term_count": 1,
                 "themes": "WB_652_ICT_APPLICATIONS;ECON_STOCKMARKET", "source_domain": "news.com"}
    assert _is_relevant(no_econ) is False
    assert _is_relevant(with_econ) is True


# ---- retrieve_evidence 契约结构（需索引） ----

@_needs_index
def test_retrieve_evidence_contract_shape():
    res = EvidenceService.retrieve_evidence(
        "Machine Learning Engineer", ("2026-01", "2026-06"), top_k=5, direction="up"
    )
    for key in ("role", "months", "direction", "aggregate", "events", "jobs", "note"):
        assert key in res
    assert isinstance(res["events"], list)
    assert isinstance(res["jobs"], list)
    for ev in res["events"]:
        for field in ("url", "source_domain", "tone", "themes", "match_weight"):
            assert field in ev          # 契约 §3 最小字段
    assert len(res["events"]) <= 5
