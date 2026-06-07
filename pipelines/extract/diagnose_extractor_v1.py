from __future__ import annotations

import json
import sys

from app.services.extractor import ExtractorService


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "Python, SQL, machine learning, PyTorch and Docker"
    diagnostics = ExtractorService.diagnose(text)
    print(
        json.dumps(
            {
                "text": text,
                "rule_skills": diagnostics.rule_skills,
                "model_skills": diagnostics.model_skills,
                "merged_skills": diagnostics.merged_skills,
                "model_attempted": diagnostics.model_attempted,
                "model_empty": diagnostics.model_empty,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
