"""HN "Ask HN: Who is hiring?" 月帖采集器（需求侧实时招聘信号）。

每月 1 日（太平洋时间）HN 会发当月招聘帖，评论为结构化文本：
``公司 | 岗位 | REMOTE(地区) | 薪资 | <链接>``。本脚本用 Algolia HN API
（免认证）定位当月帖、拉全量评论树、正则解析 公司|岗位|远程|薪资 结构，
落盘原始快照并做聚合统计（月度岗位帖数、高频技能词 top30——
用 data/gold/skill_vocab_v2.json 的别名匹配）。

幂等：raw 快照按 YYYY-MM.json 落盘，已存在的月份默认跳过（--force 覆盖）。
支持一次性回填 2025-01 至今（--backfill）。

用法::

    python -m pipelines.trend.collect_hn_hiring                # 当月
    python -m pipelines.trend.collect_hn_hiring --backfill     # 回填 2025-01 至今
    python -m pipelines.trend.collect_hn_hiring --month 2026-10

输出：
  /data/shichaojian/JNIT/raw/events/hn_hiring/YYYY-MM.json   原始快照（含解析结果）
  /data/shichaojian/JNIT/processed/hn_hiring_monthly.json    聚合统计（全量重算）
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path("/data/shichaojian/JNIT/raw/events/hn_hiring")
PROCESSED_DIR = Path("/data/shichaojian/JNIT/processed")
SKILL_VOCAB_PATH = ROOT / "data/gold/skill_vocab_v2.json"

ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search"
ALGOLIA_ITEM = "https://hn.algolia.com/api/v1/items/{item_id}"

BACKFILL_START = "2025-01"
REQUEST_SLEEP_SEC = 1.2  # Algolia 免 key，礼貌限速

# 调研实证过的帖子 id（Algolia 实测 2026-11-05），search 失败时兜底
KNOWN_STORY_IDS = {
    "2026-11": 50338728,
    "2026-10": 49922569,
    "2026-09": 49522897,
}

MONTH_TITLE_RE = re.compile(r"ask hn:\s*who is hiring\b", re.I)

# 远程标记（多种写法）
REMOTE_RE = re.compile(r"\bremote\b", re.I)
ONSITE_RE = re.compile(r"\bonsite\b|\bon-site\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)

# 薪资：$100k-$200k / €5,000/month / 100-150k / £80k+ 等
SALARY_RE = re.compile(
    r"[$€£]\s?[\d][\d,\.]*\s*(?:[kKmM])?\s*(?:[-–]\s*[$€£]?\s?[\d][\d,\.]*\s*[kKmM]?)?"
    r"(?:\s*/?\s*(?:year|yr|month|mo|week|hour|hr|annum))?"
    r"|\b\d{2,3}\s*[-–]\s*\d{2,3}\s*[kK]\b(?:\s*(?:usd|eur|gbp))?"
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def month_range(start_ym: str, end_ym: str) -> list[str]:
    start = datetime.strptime(start_ym, "%Y-%m")
    end = datetime.strptime(end_ym, "%Y-%m")
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ---------------------------------------------------------------- 帖子定位

def find_monthly_story(client: httpx.Client, ym: str) -> dict | None:
    """Algolia search 当月 "Who is hiring?" 帖，返回 {id,title,points,created_at}。"""
    hits: list[dict] = []
    page = 0
    while page < 4:
        resp = client.get(ALGOLIA_SEARCH, params={
            "tags": "story",
            "query": "Ask HN: Who is hiring",
            "hitsPerPage": 100,
            "page": page,
        })
        resp.raise_for_status()
        data = resp.json()
        hits.extend(data.get("hits", []))
        if page + 1 >= data.get("nbPages", 1):
            break
        page += 1
        time.sleep(REQUEST_SLEEP_SEC)

    prefix = ym + "-"  # 帖子创建时间前缀（UTC 近似即可，月帖在 1-3 日）
    best: dict | None = None
    for h in hits:
        title = (h.get("title") or "")
        created = (h.get("created_at") or "")[:10]
        if not MONTH_TITLE_RE.search(title):
            continue
        if created[:7] != ym:
            continue
        if best is None or (h.get("points") or 0) > (best.get("points") or 0):
            best = h
    if best:
        return {
            "id": int(best["objectID"]),
            "title": best.get("title"),
            "points": best.get("points"),
            "created_at": best.get("created_at"),
        }
    # 兜底：调研实证 id
    sid = KNOWN_STORY_IDS.get(ym)
    if sid:
        resp = client.get(ALGOLIA_ITEM.format(item_id=sid))
        resp.raise_for_status()
        d = resp.json()
        return {"id": sid, "title": d.get("title"), "points": d.get("points"),
                "created_at": d.get("created_at")}
    return None


# ---------------------------------------------------------------- 评论树

def fetch_comment_tree(client: httpx.Client, story_id: int) -> dict:
    resp = client.get(ALGOLIA_ITEM.format(item_id=story_id))
    resp.raise_for_status()
    return resp.json()


def _flatten(node: dict, out: list[dict]) -> None:
    """递归展开评论树，只取顶层直接评论（招聘贴岗位信息都在顶层）。"""
    for child in node.get("children") or []:
        text = html.unescape(re.sub(r"<[^>]+>", "", child.get("text") or ""))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append({
                "comment_id": child.get("id"),
                "author": child.get("author"),
                "created_at": child.get("created_at"),
                "text": text,
            })


# ---------------------------------------------------------------- 评论解析

def parse_comment(text: str) -> dict:
    """解析 ``公司 | 岗位 | REMOTE(地区) | 薪资 | 链接`` 结构。

    分隔符以 | 为主，容忍 ; 与 ·；链接单独抽离；非结构化评论
    （如讨论串）company/role 为空。
    """
    url = ""
    m = re.search(r"https?://\S+", text)
    if m:
        url = m.group(0).rstrip(").,;]")
        text = (text[:m.start()] + " " + text[m.end():]).strip()

    parts = [p.strip() for p in re.split(r"\s*[|·;]\s*", text) if p.strip()]
    parts = [p for p in parts if not re.fullmatch(r"https?://\S+", p)]

    company, role, remote_raw = "", "", ""
    for p in parts:
        if not company and not ROLEISH_RE.search(p):
            company = p
            continue
        if not role:
            role = p
            continue
        break
    # 远程/混合/现场标记通常在第 2-4 段
    for p in parts:
        if REMOTE_RE.search(p) or HYBRID_RE.search(p) or ONSITE_RE.search(p):
            remote_raw = p
            break

    salary = ""
    for p in parts:
        s = SALARY_RE.search(p)
        if s and len(p) < 80:
            salary = s.group(0).strip()
            break

    remote: str | None = None
    if remote_raw:
        rl = remote_raw.lower()
        remote = "hybrid" if HYBRID_RE.search(rl) else (
            "onsite" if (ONSITE_RE.search(rl) and not REMOTE_RE.search(rl)) else "remote")

    return {
        "company": company[:200],
        "role": role[:200],
        "remote": remote,
        "remote_raw": remote_raw[:200] or None,
        "salary_raw": salary or None,
        "url": url or None,
    }


ROLEISH_RE = re.compile(
    r"\b(engineer|developer|scientist|designer|manager|architect|lead|dev\b|"
    r"programmer|analyst|admin|specialist|intern|founder|cto|vp\b|head\b|"
    r"researcher|writer|marketer|sales|recruit|support|ops\b|sre\b|qa\b)\b", re.I)


def is_job_post(parsed: dict) -> bool:
    return bool(parsed.get("company") and parsed.get("role"))


# ---------------------------------------------------------------- 技能匹配

def build_skill_patterns() -> list[tuple[str, str]]:
    """返回 [(skill_id, 小写别名)]，长别名优先。"""
    vocab = json.loads(SKILL_VOCAB_PATH.read_text(encoding="utf-8"))
    alias_to_id: dict[str, str] = {}
    for skill in vocab.get("skills", []):
        sid = skill["id"]
        alias_to_id.setdefault(skill["name"].lower(), sid)
        for a in skill.get("aliases") or []:
            alias_to_id.setdefault(a.lower(), sid)
    # alias_to_id 表兜底（含 skills 数组没列全的别名）
    for a, sid in (vocab.get("alias_to_id") or {}).items():
        alias_to_id.setdefault(a.lower(), sid)
    return sorted(alias_to_id.items(), key=lambda kv: -len(kv[0]))


def match_skills(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    lowered = text.lower()
    out, seen = [], set()
    for alias, sid in patterns:
        if len(alias) < 2 or alias not in lowered:
            continue
        if re.fullmatch(r"[a-z0-9+#.\- ]+", alias):
            pat = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", re.I)
        else:
            pat = re.compile(re.escape(alias), re.I)
        if pat.search(text) and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


# ---------------------------------------------------------------- 主流程

def collect_month(client: httpx.Client, ym: str, force: bool = False) -> dict:
    out_file = RAW_DIR / f"{ym}.json"
    if out_file.exists() and not force:
        return {"month": ym, "status": "exists", "file": str(out_file)}

    story = find_monthly_story(client, ym)
    if story is None:
        return {"month": ym, "status": "no_story"}
    time.sleep(REQUEST_SLEEP_SEC)
    tree = fetch_comment_tree(client, story["id"])

    raw_comments: list[dict] = []
    _flatten(tree, raw_comments)

    skill_patterns = build_skill_patterns()
    posts = []
    for c in raw_comments:
        parsed = parse_comment(c["text"])
        entry = {**c, "parsed": parsed,
                 "skills": match_skills(c["text"], skill_patterns)}
        entry["is_job_post"] = is_job_post(parsed)
        posts.append(entry)

    payload = {
        "month": ym,
        "story_id": story["id"],
        "story_title": story.get("title"),
        "story_url": f"https://news.ycombinator.com/item?id={story['id']}",
        "story_points": story.get("points"),
        "fetched_at": _utcnow(),
        "source": "hn_algolia",
        "n_comments": len(posts),
        "n_job_posts": sum(1 for p in posts if p["is_job_post"]),
        "comments": posts,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out_file)
    return {"month": ym, "status": "ok", "story_id": story["id"],
            "n_comments": len(posts),
            "n_job_posts": payload["n_job_posts"], "file": str(out_file)}


def rebuild_aggregate() -> dict:
    """重算全量聚合统计：月度岗位帖数 + 高频技能词 top30 + 远程占比。"""
    monthly: dict[str, dict] = {}
    skill_counter: dict[str, int] = {}
    for fp in sorted(RAW_DIR.glob("*.json")):
        payload = json.loads(fp.read_text(encoding="utf-8"))
        ym = payload["month"]
        posts = [c for c in payload["comments"] if c.get("is_job_post")]
        n_remote = sum(1 for c in posts if (c["parsed"].get("remote") == "remote"))
        n_salary = sum(1 for c in posts if c["parsed"].get("salary_raw"))
        for c in payload["comments"]:
            for sid in c.get("skills") or []:
                skill_counter[sid] = skill_counter.get(sid, 0) + 1
        monthly[ym] = {
            "story_id": payload.get("story_id"),
            "n_comments": payload.get("n_comments"),
            "n_job_posts": len(posts),
            "remote_ratio": round(n_remote / len(posts), 4) if posts else None,
            "salary_disclosed_ratio": round(n_salary / len(posts), 4) if posts else None,
        }

    top30 = sorted(skill_counter.items(), key=lambda kv: -kv[1])[:30]
    aggregate = {
        "generated_at": _utcnow(),
        "backfill_start": BACKFILL_START,
        "months": monthly,
        "skill_mentions_top30": [{"skill_id": s, "mentions": n} for s, n in top30],
        "notes": [
            "技能词频用 data/gold/skill_vocab_v2.json 全部别名做词边界匹配，"
            "统计口径为「当月帖评论中提及该技能的评论数」（非去重岗位数）。",
            "帖子 id 由 Algolia search 定位（title 匹配 + 当月创建 + points 最高），"
            "失败时回落到调研实证 id 表。",
        ],
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "hn_hiring_monthly.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description="HN Who is hiring 月帖采集")
    parser.add_argument("--month", help="采集指定月 YYYY-MM（默认当月）")
    parser.add_argument("--backfill", action="store_true",
                        help="回填 2025-01 至当月全部历史月帖")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的月份快照")
    args = parser.parse_args()

    now_ym = datetime.now(timezone.utc).strftime("%Y-%m")
    if args.backfill:
        months = month_range(BACKFILL_START, now_ym)
    elif args.month:
        months = [args.month]
    else:
        months = [now_ym]

    results = []
    with httpx.Client(timeout=60.0, headers={"User-Agent": "jobnav-hn-hiring"}) as client:
        for ym in months:
            try:
                r = collect_month(client, ym, force=args.force)
            except Exception as exc:  # 单月失败不阻塞
                r = {"month": ym, "status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
            results.append(r)
            print(json.dumps(r, ensure_ascii=False))
            if ym != months[-1]:
                time.sleep(REQUEST_SLEEP_SEC)

    agg = rebuild_aggregate()
    print(f"aggregate -> {PROCESSED_DIR / 'hn_hiring_monthly.json'} "
          f"({len(agg['months'])} months)")


if __name__ == "__main__":
    main()
