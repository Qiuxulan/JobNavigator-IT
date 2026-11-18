"""skill_vocab_candidates_v3.json（910 条 O*NET/ESCO 候选）LLM 批量审核。

输入：data/gold/skill_vocab_candidates_v3.json
输出：data/gold/skill_vocab_review_v1.json
  {"generated_at": ..., "model": ..., "n_candidates": N,
   "reviews": [{"name", "source", "keep", "canonical", "aliases", "category", "reason"}]}

审核标准：keep=true 仅当候选是真实有效的 IT 技能/技术/工具/框架/平台/数据库/云/AI/方法；
宽泛软技能（如 "work in teams"）、非 IT 通用词、过短歧义词（go/c/r 等）判 false。
canonical 小写、去版本号；aliases 给常见别名/缩写（含原名小写形式）。

分批（默认 50 条/批）走 DeepSeek JSON mode；每批做 schema 校验，失败重试（默认 3 次，
指数退避）。进度增量落盘（.review_progress.json），中断可续跑。

用法：
  set -a && . ./.env && set +a
  /var/lib/jobnav-env/bin/python pipelines/foundation/review_skill_vocab_v3.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx

CANDIDATES_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/skill_vocab_candidates_v3.json")
OUTPUT_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/skill_vocab_review_v1.json")
PROGRESS_PATH = Path("/mnt/afs/JobNavigator-IT/data/gold/.review_progress.json")

CATEGORIES = [
    "language", "framework", "library", "tool", "platform", "database",
    "cloud", "ai", "devops", "os", "protocol", "method", "soft-skill", "other",
]

SYSTEM_PROMPT = (
    "You are a strict IT-skills vocabulary auditor for a tech job-board skill extractor. "
    "Respond with strict JSON only."
)


def build_user_prompt(batch: list[dict]) -> str:
    items = [
        {"index": i, "name": c["name"], "source": c["source"],
         "aliases_hint": c.get("aliases") or [],
         "element_name": (c.get("onet") or {}).get("element_name") or [],
         "skill_type": (c.get("esco") or {}).get("skill_type") or ""}
        for i, c in enumerate(batch)
    ]
    return (
        "Below is a list of candidate skill terms from O*NET/ESCO that may be added to an "
        "IT skill extraction dictionary used on tech job descriptions.\n\n"
        + json.dumps(items, ensure_ascii=False, indent=1)
        + "\n\nFor EACH candidate, decide:\n"
        '- "keep": true ONLY if it is a real, specific IT skill/technology/tool/framework/'
        'platform/database/cloud/AI-ML product/protocol/method that can appear in IT job '
        "descriptions (e.g. 'Splunk Enterprise', 'Apache Tomcat', 'Red Hat OpenShift'). "
        "false for: broad soft skills or generic competencies ('abide by business ethical "
        "code of conducts', 'adapt a script', 'work in teams'), non-IT generic words, "
        "overly short ambiguous words (like go/c/r/data/cv/rest), vague umbrella terms "
        "('web application software', 'computer programming'), and non-IT office/product "
        "skills unless they are IT-adjacent tools commonly required in IT roles.\n"
        '- "canonical": normalized lowercase name, no version numbers, dots/slashes kept '
        'only when essential (e.g. "React.js" -> "react", "Microsoft PowerPoint" -> '
        '"microsoft powerpoint"). Empty string if keep=false.\n'
        '- "aliases": list of common aliases/abbreviations in lowercase, INCLUDING the '
        'lowercased original name and useful hints (e.g. "Apache Subversion SVN" -> '
        '["subversion", "svn"]; "Kubernetes" -> ["kubernetes", "k8s"]). Empty list if '
        "keep=false.\n"
        '- "category": one of ' + ", ".join(CATEGORIES) + " (use \"soft-skill\" or \"other\" "
        "when keep=false). Prefer specific categories for keep=true.\n"
        '- "reason": one short sentence, in English.\n\n'
        "Return a JSON array with one object per candidate, in the same order, each with "
        'exactly these keys: "index" (integer, 0-based position in the batch), "keep" '
        '(boolean), "canonical" (string), "aliases" (array of strings), "category" '
        '(string), "reason" (string). The array length must equal the batch size.'
    )


def validate_batch(content: str, batch: list[dict]) -> list[dict] | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    # 部分模型会把数组包进 {"items": [...]} / {"value": [...]} 等对象里
    if isinstance(payload, dict):
        for key in ("items", "results", "reviews", "data", "value"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            list_vals = [v for v in payload.values() if isinstance(v, list)]
            if len(list_vals) == 1 and len(list_vals[0]) == len(batch):
                payload = list_vals[0]
    if not isinstance(payload, list) or len(payload) != len(batch):
        return None
    out = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            return None
        if item.get("index") != i or not isinstance(item.get("keep"), bool):
            return None
        rec = {
            "index": i,
            "keep": item["keep"],
            "canonical": str(item.get("canonical") or ""),
            "aliases": item.get("aliases") or [],
            "category": str(item.get("category") or ""),
            "reason": str(item.get("reason") or ""),
        }
        if not isinstance(rec["aliases"], list) or not all(isinstance(a, str) for a in rec["aliases"]):
            return None
        if rec["keep"] and not rec["canonical"]:
            return None
        rec["canonical"] = rec["canonical"].strip().lower()
        rec["aliases"] = [a.strip().lower() for a in rec["aliases"] if a.strip()]
        rec["category"] = rec["category"].strip().lower()
        if rec["category"] not in CATEGORIES:
            rec["category"] = "other" if rec["category"] else ("other" if not rec["keep"] else rec["category"] or "other")
        out.append(rec)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 审核技能词表候选")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--sleep-sec", type=float, default=3.0)
    args = parser.parse_args()

    api_key = os.environ["JOBNAV_LLM_API_KEY"]
    base_url = os.environ.get("JOBNAV_LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("JOBNAV_LLM_MODEL", "deepseek-chat")
    timeout = float(os.environ.get("JOBNAV_LLM_TIMEOUT_SEC", "120"))

    candidates = json.load(open(CANDIDATES_PATH, encoding="utf-8"))["candidates"]
    batches = [candidates[i:i + args.batch_size] for i in range(0, len(candidates), args.batch_size)]

    done: dict[int, list[dict]] = {}
    if PROGRESS_PATH.exists():
        done = {int(k): v for k, v in json.load(open(PROGRESS_PATH, encoding="utf-8")).items()}
        print(f"续跑：已有 {len(done)} 批结果")

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=timeout) as client:
        for b, batch in enumerate(batches):
            if b in done:
                continue
            prompt = build_user_prompt(batch)
            ok = None
            for attempt in range(args.max_retries):
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                }
                try:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"].strip()
                    ok = validate_batch(content, batch)
                except Exception as e:
                    print(f"  batch {b} attempt {attempt + 1} error: {type(e).__name__}: {e}")
                    ok = None
                if ok is not None:
                    break
                time.sleep(5 * (attempt + 1))
            if ok is None:
                raise RuntimeError(f"batch {b} failed after {args.max_retries} retries")
            done[b] = ok
            with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                json.dump(done, f, ensure_ascii=False)
            print(f"batch {b + 1}/{len(batches)} done (keep={sum(1 for r in ok if r['keep'])}/{len(batch)})")
            time.sleep(args.sleep_sec)

    reviews = []
    for b, batch in enumerate(batches):
        for cand, rec in zip(batch, done[b]):
            reviews.append({
                "name": cand["name"],
                "source": cand["source"],
                "keep": rec["keep"],
                "canonical": rec["canonical"],
                "aliases": rec["aliases"],
                "category": rec["category"],
                "reason": rec["reason"],
            })

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model,
        "n_candidates": len(candidates),
        "n_keep": sum(1 for r in reviews if r["keep"]),
        "reviews": reviews,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    PROGRESS_PATH.unlink(missing_ok=True)
    print(f"完成：keep={result['n_keep']}/{result['n_candidates']} -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
