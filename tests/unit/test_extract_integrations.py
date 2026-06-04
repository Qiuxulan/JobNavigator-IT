from pipelines.extract.model_extractor import safe_extract_model_skills
from pipelines.extract.prepare_skillspan import build_outputs, spans_from_bio
from pipelines.extract.rule_extractor import extract_skills_hybrid, load_skill_vocab


def test_skillspan_bio_span_reconstruction():
    tokens = ["strong", "Python", "and", "machine", "learning", "skills"]
    tags = ["O", "B", "O", "B", "I", "O"]
    assert spans_from_bio(tokens, tags) == ["Python", "machine learning"]


def test_skillspan_build_outputs_from_rows():
    rows = [
        {
            "tokens": ["Python", "SQL", "and", "data", "analysis"],
            "tags_skill": ["B", "B", "O", "B", "I"],
            "source": "unit",
        }
    ]
    summary, eval_rows = build_outputs(rows)
    assert summary["rows_read"] == 1
    assert summary["unique_skills"] == 3
    assert eval_rows[0]["gold_skills"] == ["data analysis", "Python", "SQL"]


def test_model_extractor_optional_fallback_without_dependencies():
    assert isinstance(safe_extract_model_skills("Python and SQL"), list)


def test_hybrid_extractor_keeps_rule_output_when_model_unavailable():
    vocab = load_skill_vocab()
    skills = extract_skills_hybrid("I use Python and SQL.", vocab, use_model=True)
    assert "Python" in skills
    assert "SQL" in skills
