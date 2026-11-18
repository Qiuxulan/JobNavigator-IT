"""evidence_v2 采集层单元测试：相关性过滤、事件分类、月份工具、分片幂等。

全部离线，无网络依赖。
"""

import json

from pipelines.evidence_v2.collect import (
    assess_relevance,
    build_anchor_re,
    build_skill_res,
    classify_event,
    is_noise,
    month_add,
    parse_pub_month,
    read_shard,
    recent_months,
    relevance_score,
    write_shard,
)

_ROLE = {
    "role_id": "role_002",
    "canonical_role": "AI Engineer",
    "aliases": ["AI Software Engineer", "AI Specialist"],
    "top_skills": ["Machine Learning", "LLM", "Python", "AWS"],
}


def _assess(title):
    role = dict(_ROLE)
    return assess_relevance(title, role, build_anchor_re(role), build_skill_res(role))


# ---- 月份工具 ----

def test_month_add_cross_year():
    assert month_add("2026-01", -1) == "2025-12"
    assert month_add("2026-12", 1) == "2027-01"
    assert month_add("2026-10", 0) == "2026-10"


def test_recent_months_ends_with_current():
    months = recent_months(3, today=None)
    assert len(months) == 3
    assert months[-1] == recent_months(1)[0]


def test_parse_pub_month():
    ym, iso = parse_pub_month("Wed, 14 Oct 2026 07:00:00 GMT")
    assert ym == "2026-10"
    assert "2026-10-14" in iso
    assert parse_pub_month("not a date") is None


# ---- 相关性 ----

def test_anchor_hit_passes():
    res = _assess("Anthropic hires Senior AI Engineer for software safety team")
    assert res is not None
    score, anchors, _ = res
    assert anchors == ["AI Engineer"]
    assert score >= 0.7


def test_anchor_without_it_context_dropped():
    """锚词命中但非 IT 语境（旧版失败点）：food & drink product manager 应被剔除。"""
    role = {"canonical_role": "Product Manager", "aliases": [], "top_skills": ["Agile"]}
    assert assess_relevance(
        "My food & drink job: product manager at a snack brand",
        role, build_anchor_re(role), build_skill_res(role),
    ) is None
    # 同名锚词 + 科技媒体来源 → 保留
    assert assess_relevance(
        "What great product managers do differently",
        role, build_anchor_re(role), build_skill_res(role),
        source_name="InfoWorld",
    ) is not None


def test_alias_anchor_hit_passes():
    res = _assess("What an AI Specialist actually does all day")
    assert res is not None
    assert "AI Specialist" in res[1]


def test_context_plus_skill_cooccurrence_passes():
    res = _assess("New startup launches developer platform powered by LLM tools")
    assert res is not None
    score, anchors, skills = res
    assert anchors == []
    assert "LLM" in skills
    assert 0.5 <= score < 0.7


def test_irrelevant_dropped():
    assert _assess("Local bakery wins best bread award") is None


def test_word_boundary_no_false_anchor():
    """'AI Engineering' 不应命中 'AI Engineer'（整短语匹配）。"""
    res = _assess("Advances in AI Engineering education")
    assert res is None or "AI Engineer" not in (res[1] if res else [])


def test_relevance_score_bounds():
    assert relevance_score("x", ["AI Engineer"], []) == 0.7
    assert relevance_score("x", [], ["LLM", "Python", "AWS"]) <= 1.0
    assert relevance_score(
        "x", ["AI Engineer", "AI Specialist"], ["LLM", "Python", "AWS", "AWS", "AWS"]
    ) == 1.0


def test_special_char_anchors():
    role = {
        "canonical_role": ".NET Backend Engineer",
        "aliases": [],
        "top_skills": ["C#"],
    }
    assert assess_relevance(
        "Senior .NET Backend Engineer role opens at fintech",
        role, build_anchor_re(role), build_skill_res(role),
    ) is not None
    role2 = {
        "canonical_role": "C++ Software Engineer",
        "aliases": [],
        "top_skills": ["Linux"],
    }
    assert assess_relevance(
        "C++ Software Engineer builds low-latency trading stack",
        role2, build_anchor_re(role2), build_skill_res(role2),
    ) is not None


# ---- 噪声 ----

def test_noise_domains():
    assert is_noise("Some tech story", "https://www.espn.com/tech/story")
    assert is_noise("Some tech story", "https://espn.com/x")
    assert not is_noise("Some tech story", "https://techcrunch.com/x")


def test_noise_titles():
    assert is_noise("NFL quarterback signs record deal", "https://example.com/a")
    assert is_noise("Senate passes new election bill", "https://example.com/b")
    assert not is_noise("Kubernetes 1.35 released", "https://example.com/c")


# ---- 事件分类 ----

def test_classify_event_priority():
    assert classify_event("Acme announces layoffs across engineering") == "layoff"
    assert classify_event("Acme lays off 200 workers in restructure") == "layoff"
    assert classify_event("Major data breach exposes user records") == "security_incident"
    assert classify_event("EU AI Act regulation passes") == "policy"
    assert classify_event("Startup raises $50M Series B funding") == "funding"
    assert classify_event("Acme is hiring 50 software engineers") == "hiring"
    assert classify_event("Bank deploys AI agents for customer service") == "ai_adoption"
    assert classify_event("Acme launches new cloud platform") == "product_release"
    assert classify_event("Quarterly earnings roundup") == "general"


# ---- 分片幂等 ----

def test_shard_roundtrip_and_dedupe(tmp_path):
    path = tmp_path / "role_000" / "2026-10.jsonl"
    items = [
        {"evidence_id": "a", "published_at": "2026-10-02T00:00:00+00:00"},
        {"evidence_id": "b", "published_at": "2026-10-01T00:00:00+00:00"},
    ]
    write_shard(path, items)
    again = read_shard(path)
    assert set(again) == {"a", "b"}
    # 幂等合并：同 evidence_id 不重复
    merged = {**again, "a": {"evidence_id": "a", "published_at": "x", "url_resolved": True}}
    write_shard(path, list(merged.values()))
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(lines) == 2
    assert any(l["url_resolved"] for l in lines)
