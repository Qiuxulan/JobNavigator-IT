"""C 模块 ① 离线索引层：把全量证据数据分片成"角色+月"小文件，零依赖。

设计：方案C（文件分区）。纯标准库，不依赖 duckdb/pyarrow/pandas，
团队无需额外安装；检索时只读命中角色+月的小分片，不碰 2.6GB 整体。

输入（全量，来自网盘，不在 git）：
  - data/raw/gdelt_gkg_role_documents/gdelt_gkg_role_documents.jsonl  2.6GB 事件
  - data/raw/processed_jd_jobs.json                                  170MB JD

输出：
  - data/processed/evidence_index/events/<role>/<month>.jsonl   事件分片
  - data/processed/evidence_index/jobs/<role>.jsonl             JD 存在性证据
  - data/processed/evidence_index/manifest.json                角色→分片清单+计数

兼容输入格式：.jsonl（逐行一对象，全量用）或 JSON 数组（样本/JD 用），自动识别。

用法：
  python pipelines/trend/build_evidence_index.py            # 全量
  python pipelines/trend/build_evidence_index.py --sample   # 20k 样本快速验证
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

GDELT_FULL = "data/raw/gdelt_gkg_role_documents/gdelt_gkg_role_documents.jsonl"
GDELT_SAMPLE = "data/gold/gdelt_gkg_role_documents_sample.json"
JD_PATH = "data/raw/processed_jd_jobs.json"
OUT_DIR = Path("data/processed/evidence_index")
EVENTS_DIR = OUT_DIR / "events"
JOBS_DIR = OUT_DIR / "jobs"

# 事件分片保留字段（丢弃无关字段，文件更小）
EVENT_FIELDS = ("canonical_role", "month", "url", "source_domain", "themes",
                "bucket_name", "match_weight", "matched_terms", "matched_term_count")
# JD 分片保留字段（丢弃 raw_jd_text 等大字段）
JOB_FIELDS = ("canonical_role", "role_id", "month", "post_date", "company_name",
              "raw_job_title", "salary_mid", "job_url", "role_match_score")

_SAFE = re.compile(r"[^A-Za-z0-9]+")


def safe_name(s: str) -> str:
    """角色名 → 安全目录名（记录里仍保留原始 canonical_role，不丢信息）。"""
    return _SAFE.sub("_", str(s or "unknown")).strip("_") or "unknown"


def parse_first_tone(tone) -> float:
    if tone is None:
        return 0.0
    if isinstance(tone, (int, float)):
        return float(tone)
    try:
        return float(str(tone).split(",")[0])
    except (ValueError, IndexError):
        return 0.0


def iter_records(path: str):
    """逐条产出记录，自动识别 jsonl（逐行）或 JSON 数组。"""
    with open(path, "r", encoding="utf-8") as f:
        first = f.read(1)
        while first and first.isspace():
            first = f.read(1)
        f.seek(0)
        if first == "[":
            # JSON 数组：样本/JD 体量可整体载入
            for rec in json.load(f):
                yield rec
        else:
            # JSONL：逐行流式，内存 O(1)，适合 2.6GB
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


class ShardWriter:
    """按 key 维护一批输出句柄；句柄数有限（角色×月≈几百），全程打开，结束统一关闭。"""

    def __init__(self):
        self.handles: dict[Path, object] = {}

    def write(self, path: Path, obj: dict) -> None:
        h = self.handles.get(path)
        if h is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            h = open(path, "w", encoding="utf-8")
            self.handles[path] = h
        h.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def close(self) -> None:
        for h in self.handles.values():
            h.close()


def build_events(gdelt_path: str, manifest: dict) -> None:
    print(f"[events] 分片 {gdelt_path} ...")
    w = ShardWriter()
    counts: Counter = Counter()          # (role) -> n
    months_by_role: dict = defaultdict(set)
    n = 0
    for rec in iter_records(gdelt_path):
        role = rec.get("canonical_role")
        if not role:
            continue
        month = rec.get("month") or "unknown"
        slim = {k: rec.get(k) for k in EVENT_FIELDS}
        slim["avg_tone"] = parse_first_tone(rec.get("tone"))
        slim["event_date"] = str(rec.get("DATE") or "")
        path = EVENTS_DIR / safe_name(role) / f"{month}.jsonl"
        w.write(path, slim)
        counts[role] += 1
        months_by_role[role].add(month)
        n += 1
        if n % 200000 == 0:
            print(f"  ... {n} 条")
    w.close()
    manifest["events"] = {
        "total": n,
        "roles": {r: {"count": c, "months": sorted(months_by_role[r])}
                  for r, c in counts.items()},
    }
    print(f"[events] 完成 {n} 条 / {len(counts)} 角色")


def build_jobs(jd_path: str, manifest: dict) -> None:
    if not Path(jd_path).exists():
        print(f"[jobs] 跳过：{jd_path} 不存在")
        return
    print(f"[jobs] 分片 {jd_path} ...")
    w = ShardWriter()
    counts: Counter = Counter()
    n = 0
    for rec in iter_records(jd_path):
        role = rec.get("canonical_role")
        if not role:
            continue
        slim = {k: rec.get(k) for k in JOB_FIELDS}
        path = JOBS_DIR / f"{safe_name(role)}.jsonl"
        w.write(path, slim)
        counts[role] += 1
        n += 1
    w.close()
    manifest["jobs"] = {"total": n, "roles": dict(counts)}
    print(f"[jobs] 完成 {n} 条 / {len(counts)} 角色")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="用 20k 样本而非全量")
    ap.add_argument("--gdelt", default=None)
    ap.add_argument("--jd", default=JD_PATH)
    ap.add_argument("--skip-jobs", action="store_true")
    args = ap.parse_args()

    gdelt_path = args.gdelt or (GDELT_SAMPLE if args.sample else GDELT_FULL)
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "source_gdelt": gdelt_path}
    build_events(gdelt_path, manifest)
    if not args.skip_jobs:
        build_jobs(args.jd, manifest)
    with open(OUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    ev = manifest.get("events", {})
    print(f"\n=== 索引概览 ===")
    print(f"events: {ev.get('total', 0)} 条 / {len(ev.get('roles', {}))} 角色")
    if "jobs" in manifest:
        print(f"jobs:   {manifest['jobs']['total']} 条 / {len(manifest['jobs']['roles'])} 角色")
    print(f"manifest -> {OUT_DIR / 'manifest.json'}")
    print(f"[done] 用时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
