from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).parents[2]
REPORT_JSON = ROOT / "reports" / "summary" / "job_resource_rich_career_reports_api_output.json"
REPORT_MD = ROOT / "reports" / "summary" / "job_resource_rich_career_reports_summary.md"

SAMPLES = [
    {
        "sample_id": "resource_rich_rag",
        "resume_text": (
            "I have backend and AI application experience using Python, FastAPI, PostgreSQL, SQL, Docker and Git. "
            "I have already built RAG demos with LangChain, vector databases, embeddings, prompt engineering and OpenAI API. "
            "I also experimented with LLM evaluation, AI agents and retrieval workflows for internal knowledge assistants."
        ),
    },
    {
        "sample_id": "resource_rich_llm_inference",
        "resume_text": (
            "I work with Python, machine learning, PyTorch, NLP, SQL, Docker and Linux. "
            "I have explored LLM inference pipelines, prompt engineering, RAG, embeddings, fine-tuning basics and model deployment. "
            "I also studied AI agent workflows and evaluation for production LLM systems."
        ),
    },
    {
        "sample_id": "resource_rich_backend_python",
        "resume_text": (
            "I am a Python backend engineer using Django, FastAPI, PostgreSQL, SQL, Redis, Docker, AWS, Git and Linux. "
            "I build REST APIs, CI/CD pipelines and web services, and I also use JavaScript for admin dashboards. "
            "I want a role that strengthens Python backend depth while keeping learning resources concrete and actionable."
        ),
    },
]


def summarize(payload: dict) -> str:
    top = payload["ranked_results"][0]
    lines = [
        f"## {payload['profile']['user_id']}",
        "",
        f"- 鎶€鑳斤細{', '.join(payload['profile']['skills'])}",
        f"- Top1 宀椾綅锛歚{top['job']['title']}`",
        f"- final_score={top['final_score']:.4f}, semantic_score={top['semantic_score']:.4f}",
        f"- 瀛︿範璺緞姝ユ暟锛歿top['path']['total_steps']}",
        f"- 瀛︿範璺緞鎬诲鏃讹細{top['path']['total_estimated_hours']}",
        "",
        "**Top1 璺緞鍓?6 姝ヨ祫婧愭瑙?*",
    ]
    for step in top["path"]["steps"][:6]:
        resource_titles = [resource["title"] for resource in step["resources"][:2]]
        lines.append(f"- {step['step_no']}. {step['skill']} -> {', '.join(resource_titles) if resource_titles else '鏃犺祫婧?}")
    lines.extend(["", "**鎶ュ憡鎽樿**", "", payload["report_markdown"][:1800], ""])
    return "\n".join(lines)


def main() -> None:
    client = TestClient(app)
    outputs = []
    md_parts = ["# 楂樿祫婧愯鐩栨柟鍚戠殑 3 鏉℃ā鎷熺畝鍘嗘姤鍛?, ""]
    for sample in SAMPLES:
        resp = client.post(
            "/v1/careers/report",
            json={
                "resume_text": sample["resume_text"],
                "user_id": sample["sample_id"],
                "top_k": 3,
                "audience": "candidate",
                "language": "zh-CN",
            },
        )
        outputs.append(
            {
                "sample_id": sample["sample_id"],
                "resume_text": sample["resume_text"],
                "status_code": resp.status_code,
                "response": resp.json(),
            }
        )
        if resp.status_code == 200:
            md_parts.append(summarize(resp.json()))
        else:
            md_parts.extend(
                [
                    f"## {sample['sample_id']}",
                    "",
                    f"- status_code: {resp.status_code}",
                    f"- error: `{resp.text}`",
                    "",
                ]
            )
    REPORT_JSON.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text("\n".join(md_parts), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "samples": len(outputs),
                "json_report": str(REPORT_JSON),
                "md_report": str(REPORT_MD),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

