"""C 模块证据检索冒烟测试。

闸门逻辑用合成数据，无需索引，CI 可直接跑；
retrieve_evidence 结构测试在缺索引时自动跳过。
"""

import os

import pytest

from app.services.evidence import (
    EvidenceService,
    _is_relevant,
    _role_title_affinity,
    _strong_skill_terms,
)

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


def test_gate_ambiguous_needs_strict_theme_or_title_context():
    """歧义技能词(react)需明确技术主题，或标题里有岗位/技术上下文才放行。"""
    no_econ = {"matched_terms": ["react"], "matched_term_count": 1,
               "themes": "WB_652_ICT_APPLICATIONS;MEDIA_SOCIAL", "source_domain": "news.com"}
    broad_theme = {"matched_terms": ["react"], "matched_term_count": 1,
                   "themes": "WB_652_ICT_APPLICATIONS;ECON_STOCKMARKET", "source_domain": "news.com"}
    strict_theme = {"matched_terms": ["react"], "matched_term_count": 1,
                    "themes": "SOFTWARE;ECON_STOCKMARKET", "source_domain": "news.com"}
    title_context = {"matched_terms": ["react"], "matched_term_count": 1,
                     "themes": "MEDIA_SOCIAL", "source_domain": "jobs.example.com",
                     "url": "https://jobs.example.com/frontend-react-developer"}
    assert _is_relevant(no_econ) is False
    assert _is_relevant(broad_theme) is False
    assert _is_relevant(strict_theme) is True
    assert _is_relevant(title_context) is True


def test_gate_drops_python_animal_noise():
    """Python 动物/泛新闻标题不应进入干净样本。"""
    ev = {"matched_terms": ["python"], "matched_term_count": 1,
          "themes": "SOFTWARE;ECON_STOCKMARKET", "source_domain": "news.com",
          "url": "https://news.com/dumsor-theatricals-pythons-missing-containers"}
    assert _is_relevant(ev) is False


def test_role_title_affinity_requires_role_anchor():
    """标题像技术内容还不够，入图前要像目标岗位。"""
    info = {"aliases": ["AI Software Engineer"]}
    bad = _role_title_affinity("AI Engineer", info, "senior javascript developer postgresql python docker")
    good = _role_title_affinity("AI Engineer", info, "openai trades azure exclusivity for enterprise ai reach")
    assert bad == 0.0
    assert good >= 0.5


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
