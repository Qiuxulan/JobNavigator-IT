"""monthly_update: 一键月度更新编排器。

把「跟上行业变化」所需的月度链路串成一个命令，每步独立 try/except，
失败只记日志不中断，最后汇总状态写 jsonl 日志。全链路幂等，同月重复运行无副作用。

步骤（v3 链路，2026-10-19 重接线；2026-11-05 增补 HN 月帖 + JOA 快照；
2026-11-06 接入 trend_v2 岗位级趋势面板 + 预测，岗位详情页趋势随月度更新）：
1. download_snapshots  探测 minmaxxxer 与 JOA（JobOpportunitiesAPI/
   joa-employer-direct-job-postings-YYYY-MM，CC-BY-4.0）在 HF 上的当月/上月
   快照，有新仓库就 hf download 到 /data/shichaojian/JNIT/raw/jd/<src>_<YYYY_MM>/
2. fetch_live_api      拉 remotive / jobicy 实时远程岗，写
   /data/shichaojian/JNIT/raw/jd/live_api/<YYYY-MM>.json（失败不阻塞）；
   collect_hn_hiring    拉 HN "Who is hiring?" 当月帖（Algolia API），写
   /data/shichaojian/JNIT/raw/events/hn_hiring/<YYYY-MM>.json（已存在的月份跳过）
3. unify_jd_v3 + enrich_skills_v3   有新数据（或 --skip-download 强制）时重跑
   多源融合（含 JOA 源）与技能抽取补全，产出 jd_unified_v3_enriched
4. expand_roles_v3 / build_role_profiles_v3 / build_skill_trend_v3 /
   collect_learning_resources_v4   依次重跑（岗位扩充、画像、趋势面板、学习资源）；
   trend_v2.build_panel → trend_v2.forecast   岗位级趋势面板 + 回测选模预测
   （依赖 expand_roles_v3 的映射，panel 先于 forecast；产出 trend_panel_v2.json /
   trend_forecasts_v2.json，供 API /v1/trends 读）
5. evidence_collect    pipelines.evidence_v2.collect --months 1 增量
6. job_vectors         仅当 data/gold/role_profiles_v3.json 的 mtime 新于
   state 记录时才重跑 build_job_vectors（写 pgvector）
7. 汇总                每步耗时/状态/行数变化写 monthly_update_log.jsonl（追加）

用法：
    /var/lib/jobnav-env/bin/python -m pipelines.monthly_update [--dry-run] [--skip-download]

crontab 配置（每月 3 号 04:17 运行，crontab -e 添加一行）：
    17 4 3 * * cd /mnt/afs/JobNavigator-IT && HF_HOME=/var/lib/hf JOBNAV_POSTGRES_DSN=postgresql://jobnav:jobnav@localhost:5432/jobnavigator /var/lib/jobnav-env/bin/python -m pipelines.monthly_update >> /data/shichaojian/JNIT/processed/monthly_update_cron.log 2>&1
（环境变量也可放进 ~/.profile 或 /etc/environment；脚本内已内置同样的默认值，
 crontab 里不显式导出也能跑。）

状态文件：/data/shichaojian/JNIT/processed/.monthly_update_state.json
日志文件：/data/shichaojian/JNIT/processed/monthly_update_log.jsonl（每行一次运行）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

JNIT = Path("/data/shichaojian/JNIT")
RAW_JD = JNIT / "raw" / "jd"
PROCESSED = JNIT / "processed"
LIVE_API_DIR = RAW_JD / "live_api"
UNIFIED_DIR = PROCESSED / "jd_unified_v3_enriched"
STATE_PATH = PROCESSED / ".monthly_update_state.json"
LOG_PATH = PROCESSED / "monthly_update_log.jsonl"

ROLE_PROFILES_JSON = REPO_ROOT / "data" / "gold" / "role_profiles_v3.json"

DEFAULT_DSN = "postgresql://jobnav:jobnav@localhost:5432/jobnavigator"
DEFAULT_HF_HOME = "/var/lib/hf"
HF_DATASET_PATTERNS = {
    "minmaxxxer": "minmaxxxer/job-postings-with-salaries-{ym}",  # ym = YYYY-MM
    # JOA 雇主直采月度快照（CC-BY-4.0），first_seen 作 posted_at
    "joa": "JobOpportunitiesAPI/joa-employer-direct-job-postings-{ym}",
}

REMOTIVE_URL = "https://remotive.com/api/remote-jobs?limit=500"
JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs?count=50"

# hf CLI 路径：优先取当前解释器同目录（/var/lib/jobnav-env/bin/hf），其次 PATH
_HF_BIN = shutil.which("hf", path=str(Path(sys.executable).parent))
if _HF_BIN is None:
    _HF_BIN = shutil.which("hf") or "hf"


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _child_env() -> dict:
    """子进程环境：透传当前环境，补齐 HF_HOME / JOBNAV_POSTGRES_DSN 默认值。"""
    env = os.environ.copy()
    env.setdefault("HF_HOME", DEFAULT_HF_HOME)
    env.setdefault("JOBNAV_POSTGRES_DSN", DEFAULT_DSN)
    return env


def run_module(module: str, extra_args: list[str] | None = None,
               dry_run: bool = False) -> dict:
    """subprocess 跑一个 ``python -m`` 模块，返回步骤结果 dict。"""
    cmd = [sys.executable, "-m", module] + (extra_args or [])
    print(f"[monthly_update] $ {' '.join(cmd)}", flush=True)
    if dry_run:
        return {"status": "dry-run"}
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=_child_env(),
                          capture_output=True, text=True)
    seconds = round(time.monotonic() - t0, 1)
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
    result = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "seconds": seconds,
        "returncode": proc.returncode,
    }
    if proc.returncode != 0:
        result["error_tail"] = tail[-800:]
    else:
        result["output_tail"] = tail[-400:]
    return result


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# ---------------------------------------------------------------------------
# 步骤 1: HF 月快照下载
# ---------------------------------------------------------------------------

def _candidate_months() -> list[str]:
    """当前月与上月，格式 YYYY-MM。"""
    now = datetime.now(UTC)
    months = [now.strftime("%Y-%m")]
    prev = (now.month - 2) % 12 + 1
    year = now.year - (1 if now.month == 1 else 0)
    months.append(f"{year:04d}-{prev:02d}")
    return months


def download_snapshots(dry_run: bool = False) -> dict:
    """探测当月/上月的 minmaxxxer 与 JOA 快照，本地缺的 hf download。幂等。"""
    from huggingface_hub import repo_exists  # 延迟导入，--help 更快

    downloaded, skipped = [], []
    for prefix, pattern in HF_DATASET_PATTERNS.items():
        for ym in _candidate_months():
            repo = pattern.format(ym=ym)
            try:
                exists = repo_exists(repo, repo_type="dataset")
            except Exception as e:  # 网络问题不阻塞
                return {"status": "failed", "error": f"repo_exists({repo}): {e}"}
            if not exists:
                skipped.append(f"{repo} (HF 上不存在)")
                continue
            local_dir = RAW_JD / f"{prefix}_{ym.replace('-', '_')}"
            marker = local_dir / ".complete"
            if marker.exists() or list(local_dir.glob("*.parquet")) or \
                    list(local_dir.glob("*.jsonl")):
                skipped.append(f"{repo} (本地已有 {local_dir.name})")
                continue
            cmd = [_HF_BIN, "download", repo, "--repo-type", "dataset",
                   "--local-dir", str(local_dir)]
            print(f"[monthly_update] $ {' '.join(cmd)}", flush=True)
            if dry_run:
                downloaded.append(f"{repo} -> {local_dir} (dry-run)")
                continue
            proc = subprocess.run(cmd, env=_child_env(), capture_output=True, text=True)
            if proc.returncode != 0:
                return {"status": "failed",
                        "error": f"hf download {repo} 失败: "
                                 + proc.stderr.strip().splitlines()[-1][:300]}
            marker.write_text(_now() + "\n", encoding="utf-8")
            downloaded.append(f"{repo} -> {local_dir}")

    detail = {"downloaded": downloaded, "skipped": skipped}
    if downloaded:
        detail["new_data"] = True
    return {"status": "ok", "detail": detail}


# ---------------------------------------------------------------------------
# 步骤 2: live API 增量
# ---------------------------------------------------------------------------

def fetch_live_api(dry_run: bool = False) -> dict:
    """拉 remotive / jobicy 最新远程岗写 live_api/<YYYY-MM>.json。失败不阻塞。"""
    import urllib.request

    ym = datetime.now(UTC).strftime("%Y-%m")
    out_file = LIVE_API_DIR / f"{ym}.json"
    payload: dict = {"fetched_at": _now()}

    def _get(url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "jobnav-monthly-update"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    errors = {}
    for name, url in (("remotive", REMOTIVE_URL), ("jobicy", JOBICY_URL)):
        try:
            data = _get(url)
            n = len(data.get("jobs") or [])
            payload[name] = data
            print(f"[monthly_update] live_api {name}: {n} jobs", flush=True)
        except Exception as e:
            errors[name] = str(e)[:200]

    if dry_run:
        return {"status": "dry-run",
                "detail": {"would_write": str(out_file)}}

    if set(errors) == {"remotive", "jobicy"}:
        return {"status": "failed", "error": f"两个 API 均失败: {errors}"}

    LIVE_API_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out_file)  # 原子覆盖，同月重跑幂等
    n_rem = len(payload.get("remotive", {}).get("jobs") or [])
    n_jbc = len(payload.get("jobicy", {}).get("jobs") or [])
    detail = {"file": str(out_file), "remotive_jobs": n_rem, "jobicy_jobs": n_jbc}
    if errors:
        detail["partial_errors"] = errors
    return {"status": "ok", "detail": detail}


# ---------------------------------------------------------------------------
# 步骤 3-6 之间的辅助
# ---------------------------------------------------------------------------

def _unified_row_count() -> int | None:
    """读 jd_unified 分区目录估算总行数（读 parquet 元数据，不拉数据）。"""
    import pyarrow.parquet as pq

    total = 0
    try:
        for part in sorted(UNIFIED_DIR.glob("posted_month=*/part-0.parquet")):
            total += pq.ParquetFile(part).metadata.num_rows
    except OSError:
        return None
    return total


def should_run_job_vectors(state: dict) -> tuple[bool, str]:
    """role_profiles_v2.json mtime 新于上次记录才刷新岗位向量。"""
    try:
        mtime = ROLE_PROFILES_JSON.stat().st_mtime
    except OSError:
        return False, f"{ROLE_PROFILES_JSON} 不存在，跳过"
    last = state.get("role_profiles_v2_mtime")
    if last is None:
        return True, "无历史记录，视为已更新"
    if mtime > last:
        return True, f"mtime {mtime:.0f} > 记录 {last:.0f}"
    return False, f"mtime {mtime:.0f} <= 记录 {last:.0f}，无需刷新"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JobNavigator-IT 月度更新编排器")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将执行的步骤，不实际执行")
    parser.add_argument("--skip-download", action="store_true",
                        help="跳过步骤 1-2（HF 快照 + live API），直接重跑处理链路")
    args = parser.parse_args(argv)

    state = load_state()
    run_id = _now()
    steps: list[dict] = []

    def record(name: str, result: dict) -> None:
        result = {"step": name, **result}
        steps.append(result)
        status = result.get("status")
        extra = f" ({result['seconds']}s)" if "seconds" in result else ""
        print(f"[monthly_update] {name}: {status}{extra}", flush=True)
        if result.get("error"):
            print(f"[monthly_update]   error: {result['error']}", flush=True)

    print(f"[monthly_update] run_id={run_id} dry_run={args.dry_run} "
          f"skip_download={args.skip_download}", flush=True)

    # ---- 步骤 1-2: 数据获取 ----
    new_data = bool(args.skip_download)  # --skip-download 视为强制重跑链路
    if args.skip_download:
        print("[monthly_update] 步骤 1-2 跳过（--skip-download）", flush=True)
        steps.append({"step": "download", "status": "skipped",
                      "reason": "--skip-download"})
    else:
        try:
            r = download_snapshots(dry_run=args.dry_run)
            record("download_hf_snapshots", r)
            new_data = new_data or bool(r.get("detail", {}).get("new_data"))
        except Exception:
            record("download_hf_snapshots",
                   {"status": "failed", "error": traceback.format_exc()[-500:]})
        try:
            r = fetch_live_api(dry_run=args.dry_run)
            record("fetch_live_api", r)
            if r.get("status") in ("ok", "dry-run"):
                new_data = True  # live 快照每月覆盖刷新，拿到即视为有新数据
        except Exception:
            record("fetch_live_api",
                   {"status": "failed", "error": traceback.format_exc()[-500:]})
        try:
            # HN "Who is hiring?" 当月帖（Algolia API，免认证；已存在的月份自动跳过）
            r = run_module("pipelines.trend.collect_hn_hiring",
                           dry_run=args.dry_run)
            record("collect_hn_hiring", r)
        except Exception:
            record("collect_hn_hiring",
                   {"status": "failed", "error": traceback.format_exc()[-500:]})

    # ---- 步骤 3: JD 统一融合 + 技能补全（v3 链路）----
    if not new_data and UNIFIED_DIR.exists():
        record("unify_jd_v3", {"status": "skipped",
                               "reason": "无新数据且 jd_unified_v3_enriched 已存在"})
    else:
        rows_before = _unified_row_count() if not args.dry_run else None
        r = run_module("pipelines.extract.unify_jd_v3", dry_run=args.dry_run)
        record("unify_jd_v3", r)
        r = run_module("pipelines.extract.enrich_skills_v3",
                       extra_args=["--vocab-v4", "data/gold/skill_vocab_v4.json"],
                       dry_run=args.dry_run)
        if r.get("status") == "ok":
            rows_after = _unified_row_count()
            r["rows_before"] = rows_before
            r["rows_after"] = rows_after
            if rows_before is not None and rows_after is not None:
                r["rows_delta"] = rows_after - rows_before
        record("enrich_skills_v3", r)

    # ---- 步骤 4: 岗位扩充 + 画像 + 技能趋势（v3 链路）----
    r = run_module("pipelines.taxonomy.expand_roles_v3", dry_run=args.dry_run)
    record("expand_roles_v3", r)
    r = run_module("pipelines.taxonomy.build_role_profiles_v3",
                   extra_args=["--extra-vocab", "data/gold/skill_vocab_v4.json"],
                   dry_run=args.dry_run)
    record("build_role_profiles_v3", r)
    # 岗位级趋势面板 + 预测（trend_v2，依赖 expand_roles_v3 的 title→role 映射，
    # 必须在 build_role_profiles_v3 之后、panel 先于 forecast）
    r = run_module("pipelines.trend_v2.build_panel", dry_run=args.dry_run)
    record("trend_v2.build_panel", r)
    r = run_module("pipelines.trend_v2.forecast", dry_run=args.dry_run)
    record("trend_v2.forecast", r)
    r = run_module("pipelines.trend.build_skill_trend_v3", dry_run=args.dry_run)
    record("build_skill_trend_v3", r)
    # Chronos-Bolt 三方 CV 选模覆盖预测层（输入即上一步的 v3 面板+full parquet）
    r = run_module("pipelines.trend.build_skill_trend_v4_chronos", dry_run=args.dry_run)
    record("build_skill_trend_v4_chronos", r)
    r = run_module("pipelines.report.collect_learning_resources_v4",
                   dry_run=args.dry_run)
    record("collect_learning_resources_v4", r)

    # ---- 步骤 5: 证据增量 ----
    r = run_module("pipelines.evidence_v2.collect", ["--months", "1"],
                   dry_run=args.dry_run)
    record("evidence_v2.collect", r)

    # ---- 步骤 6: 岗位向量（mtime 变化才跑）----
    need_vectors, reason = should_run_job_vectors(state)
    if not need_vectors:
        record("taxonomy.build_job_vectors", {"status": "skipped", "reason": reason})
    else:
        print(f"[monthly_update] build_job_vectors: {reason}", flush=True)
        r = run_module("pipelines.taxonomy.build_job_vectors", dry_run=args.dry_run)
        record("taxonomy.build_job_vectors", r)
        if r.get("status") == "ok" and not args.dry_run:
            state["role_profiles_v2_mtime"] = ROLE_PROFILES_JSON.stat().st_mtime

    # ---- 步骤 7: 汇总写日志 / 更新状态 ----
    n_failed = sum(1 for s in steps if s.get("status") == "failed")
    summary = {
        "run_id": run_id,
        "dry_run": args.dry_run,
        "skip_download": args.skip_download,
        "status": "failed" if n_failed else "ok",
        "steps_failed": n_failed,
        "steps": steps,
    }
    print(f"[monthly_update] done: {len(steps)} 步，失败 {n_failed} 步", flush=True)

    if not args.dry_run:
        state["last_run"] = run_id
        state["last_status"] = summary["status"]
        save_state(state)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print(f"[monthly_update] log -> {LOG_PATH}", flush=True)

    return 1 if n_failed else 0


if __name__ == "__main__":
    sys.exit(main())
