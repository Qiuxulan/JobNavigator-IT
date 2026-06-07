from pipelines.graph.build_career_graph_v2 import build_graph_payload


def test_build_graph_payload_v2_has_expected_relations():
    payload = build_graph_payload()
    relations = {edge["relation"] for edge in payload["edges"]}

    assert payload["nodes"]
    assert {"JOB_REQUIRES", "SKILL_PREREQ", "SKILL_HAS_RESOURCE"} <= relations


def test_each_role_keeps_only_top_30_skills():
    payload = build_graph_payload()
    counts = {}
    for edge in payload["edges"]:
        if edge["relation"] != "JOB_REQUIRES":
            continue
        counts[edge["src_id"]] = counts.get(edge["src_id"], 0) + 1
    assert counts
    assert max(counts.values()) <= 30
