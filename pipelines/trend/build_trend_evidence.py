"""C 妯″潡 鈶?鈶わ細鎵归噺浜у嚭瓒嬪娍璇佹嵁鏂囦欢 + 璇勪及鎶ュ憡锛堝畬鏁寸増锛屽鐢?EvidenceService锛夈€?

瀵?B 鐨勬瘡鏉¤秼鍔跨粨璁猴紝璋冪敤缁熶竴妫€绱㈡牳蹇冨彇銆岃仛鍚堜俊鍙?+ 骞插噣鏍锋湰浜嬩欢 + JD 璇佹嵁銆嶏紝
鎸夊绾?搂5 鍐?data/gold/trend_evidence_v1.jsonl锛屽苟鐢熸垚璇勪及鎶ュ憡銆?

涓庤繍琛屾椂鎺ュ彛 retrieve_evidence 鍏辩敤鍚屼竴涓绱㈡牳蹇冿紝涓嶉噸澶嶅疄鐜版绱㈤€昏緫銆?

鐢ㄦ硶锛?
  python -m pipelines.trend.build_trend_evidence
  python pipelines/trend/build_trend_evidence.py
鍓嶇疆锛氬厛璺?build_evidence_index.py 鐢熸垚绱㈠紩銆?
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.evidence import EvidenceService
from pipelines.trend._trend_source import EVENT_WINDOW, load_conclusions

TAXONOMY_PATH = Path("data/gold/role_taxonomy.json")
OUT_JSONL = Path("data/gold/trend_evidence_v1.jsonl")
OUT_JSONL_MONTHLY = Path("data/gold/trend_evidence_monthly_v1.jsonl")
OUT_REPORT = Path("reports/eval/industry_trend_explanation_eval_v1.md")
MAJOR_EVENTS_PATH = Path("data/gold/major_industry_events_v1.json")

DIRECTION_NORMALIZE = {"up": "up", "flat": "stable", "stable": "stable", "down": "down"}
DIRECTION_CN = {"up": "涓婂崌", "stable": "鎸佸钩", "down": "涓嬮檷"}
TOPK = 5


def _load_major_events() -> tuple[dict[str, dict], dict[tuple[str, str], list[str]]]:
    if not MAJOR_EVENTS_PATH.exists():
        return {}, {}
    data = json.loads(MAJOR_EVENTS_PATH.read_text(encoding="utf-8"))
    catalog = {e["event_id"]: e for e in data.get("event_catalog", [])}
    mapping = {
        (r["canonical_role"], r["trend_direction"]): r.get("major_event_ids", [])
        for r in data.get("role_trend_evidence", [])
    }
    return catalog, mapping


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _make_evidence_topk(events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        out.append({
            "source_name": "GDELT",
            "source_url": ev.get("url"),
            "title": ev.get("title"),
            "published_at": ev.get("published_at"),
            "evidence_text": f"{ev.get('source_domain', '')} 路 {ev.get('event_type', '')} 路 tone {ev.get('tone')}",
            "retrieval_score": ev.get("retrieval_score"),
            "evidence_type": ev.get("event_type"),
            "impact_direction": ev.get("impact_direction"),
            "evidence_strength": ev.get("evidence_strength", "strong"),
        })
    return out


def _make_jd_evidence(jobs: list[dict]) -> list[dict]:
    out = []
    for j in jobs:
        out.append({
            "evidence_type": "job_posting",
            "company_name": j.get("company_name"),
            "title": j.get("title"),
            "post_date": j.get("post_date"),
            "salary_mid": j.get("salary_mid"),
            "job_url": j.get("job_url"),
            "out_of_range": j.get("out_of_range"),
        })
    return out


def _make_major_events(role: str, raw_direction: str, role_family: str | None,
                       catalog: dict[str, dict],
                       mapping: dict[tuple[str, str], list[str]]) -> list[dict]:
    lookup_direction = "flat" if raw_direction == "stable" else raw_direction
    ids = mapping.get((role, lookup_direction), [])
    if not ids and role_family:
        ids = [
            event_id
            for event_id, ev in sorted(
                catalog.items(),
                key=lambda item: float(item[1].get("event_importance") or 0.0),
                reverse=True,
            )
            if role_family in (ev.get("categories") or [])
            and lookup_direction in (ev.get("trend_fit") or [])
        ][:5]
    out = []
    for event_id in ids:
        ev = catalog.get(event_id)
        if not ev:
            continue
        out.append({
            "event_id": event_id,
            "title": ev.get("title"),
            "event_date": ev.get("event_date"),
            "source_name": ev.get("source_name"),
            "source_url": ev.get("source_url"),
            "event_type": ev.get("event_type"),
            "impact_direction": ev.get("impact_direction"),
            "event_importance": ev.get("event_importance"),
            "summary_zh": ev.get("summary_zh"),
        })
    return out


def _risk_notes(direction: str, agg: dict | None, events: list[dict]) -> list[str]:
    notes = ["璇佹嵁鐩稿叧鎬т负杩戜技锛圙DELT 鏃犳鏂囷紝鍩轰簬鎶€鑳界櫧鍚嶅崟+涓婚鍏辩幇绾︽潫锛夈€?]
    if agg:
        net = agg.get("net_signal")
        if direction == "up" and net == "negative":
            notes.append("鑱氬悎鍑€淇″彿鍋忚礋锛屼笌涓婂崌缁撹涓嶄竴鑷达紝闇€璋ㄦ厧銆?)
        elif direction == "down" and net == "positive":
            notes.append("鑱氬悎鍑€淇″彿鍋忔锛屼笌涓嬮檷缁撹涓嶄竴鑷达紝闇€璋ㄦ厧銆?)
        if agg.get("article_count", 0) < 20:
            notes.append(f"鏈湀鐩稿叧鏂伴椈浠?{agg.get('article_count')} 绡囷紝鏍锋湰鍋忓皬銆?)
    weak_count = sum(1 for ev in events if ev.get("evidence_strength") == "weak")
    if weak_count:
        notes.append(f"鍚?{weak_count} 鏉″急鐩稿叧琛ュ厖浜嬩欢锛涘己缁撹浠?aggregate/JD 涓哄噯銆?)
    if not events:
        notes.append("鏃犻€氳繃鍥涢噸绾︽潫鐨勫共鍑€浜嬩欢鏍锋湰锛岃秼鍔夸綈璇佷互 aggregate 涓哄噯銆?)
    notes.append("璇佹嵁澶氫负鑻辨枃鏂伴椈婧愶紝涓枃鏈湡甯傚満闇€琛ュ厖銆?)
    return notes


def main(granularity: str = "milestone") -> None:
    conclusions = load_conclusions(granularity=granularity)   # 閲岀▼纰?鎴?閫愭湀鍏ㄩ噺
    tax = {t["canonical_role"]: t for t in json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))}
    out_path = OUT_JSONL_MONTHLY if granularity == "monthly" else OUT_JSONL

    t0 = time.time()
    rows_out = []
    ev_cache: dict = {}                         # (role,鏂瑰悜)->妫€绱㈢粨鏋? 閫愭湀妯″紡閬垮厤閲嶅妫€绱?
    major_catalog, major_mapping = _load_major_events()
    stats = {"total": 0, "with_events": 0, "with_aggregate": 0,
             "aligned": 0, "event_counts": [], "roles": set(), "roles_with_events": set()}

    n = len(conclusions)
    src = conclusions[0]["source"] if conclusions else "?"
    print(f"[trend_evidence] {n} 鏉＄粨璁?鏉ユ簮={src})锛岃瘉鎹獥鍙?{EVENT_WINDOW}锛岄€愪釜妫€绱?...", flush=True)
    for i, row in enumerate(conclusions, 1):
        role = row["canonical_role"]
        month = row["month"]                   # 棰勬祴鏈堜唤(鍙兘鍦ㄦ湭鏉?
        horizon = int(row.get("horizon_months", 3))
        horizon_label = row.get("horizon_label", f"{horizon}_month")
        raw_dir = row.get("trend_direction", "flat")
        direction = DIRECTION_NORMALIZE.get(raw_dir, "stable")
        idx = float(row.get("predicted_demand_index", 0.0))
        conf = float(row.get("confidence", 0.0))
        factors = row.get("factors", [])
        info = tax.get(role, {})

        if i % 50 == 0 or i == n:
            print(f"  ... {i}/{n}", flush=True)

        # 棰勬祴鍦ㄦ湭鏉ユ棤鏂伴椈 -> 璇佹嵁浠庢渶杩戠湡瀹炰簨浠剁獥鍙ｅ彇锛涘悓(瑙掕壊,鏂瑰悜)缂撳瓨澶嶇敤
        ck = (role, raw_dir)
        res = ev_cache.get(ck)
        if res is None:
            res = EvidenceService.retrieve_evidence(role, EVENT_WINDOW, TOPK, raw_dir)
            ev_cache[ck] = res
        events = res.get("events", [])
        agg = res.get("aggregate")
        major_events = _make_major_events(role, raw_dir, info.get("category"), major_catalog, major_mapping)

        conclusion = (f"{role} 棰勮鏈潵 {horizon} 涓湀闇€姹倇DIRECTION_CN[direction]}"
                      f"锛堥娴嬫湀 {month}锛岄渶姹傛寚鏁?{idx:.2f}锛岀疆淇″害 {conf:.0%}锛夈€?)
        if agg:
            conclusion += f" 杩?6 涓湀鐩稿叧鏂伴椈 {agg['article_count']} 绡囷紝鍑€淇″彿 {agg['net_signal']}銆?

        rows_out.append({
            "trend_id": f"{_slug(role)}_{horizon_label}",
            "role_family": info.get("category"),
            "canonical_role": role,
            "skill_name": None,
            "month": month,
            "horizon_months": horizon,
            "evidence_window": list(EVENT_WINDOW),
            "conclusion": conclusion,
            "trend_direction": direction,
            "trend_direction_raw": raw_dir,
            "predicted_demand_index": round(idx, 4),
            "confidence": round(conf, 4),
            "main_factors": factors,
            "aggregate": agg,
            "evidence_topk": _make_evidence_topk(events),
            "major_industry_events": major_events,
            "jd_evidence": _make_jd_evidence(res.get("jobs", [])),
            "risk_notes": _risk_notes(direction, agg, events),
            "model_version": "trend-evidence-v2-constrained",
        })

        # 缁熻
        stats["total"] += 1
        stats["roles"].add(role)
        if agg:
            stats["with_aggregate"] += 1
        if events:
            stats["with_events"] += 1
            stats["roles_with_events"].add(role)
            stats["event_counts"].append(len(events))
            # 鏂瑰悜瀵归綈锛氳仛鍚堝噣淇″彿鏂瑰悜涓庣粨璁轰竴鑷?
            if agg and ((direction == "up" and agg["net_signal"] == "positive")
                        or (direction == "down" and agg["net_signal"] == "negative")
                        or (direction == "stable")):
                stats["aligned"] += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if granularity != "monthly":
        _write_report(stats, rows_out)         # 璇勪及鎶ュ憡鍙负閲岀▼纰戠増鐢熸垚
    cov = stats["with_events"] / stats["total"] if stats["total"] else 0
    print(f"[ok] {len(rows_out)} 琛?-> {out_path}")
    print(f"[ok] 鎶ュ憡 -> {OUT_REPORT}")
    print(f"[stat] 鍚共鍑€浜嬩欢: {stats['with_events']}/{stats['total']} = {cov:.1%} | "
          f"鍚仛鍚? {stats['with_aggregate']}/{stats['total']} | 鐢ㄦ椂 {time.time()-t0:.1f}s")


def _write_report(stats: dict, rows_out: list[dict]) -> None:
    total = stats["total"]
    we = stats["with_events"]
    wa = stats["with_aggregate"]
    cov = we / total if total else 0
    agg_cov = wa / total if total else 0
    counts = stats["event_counts"]
    avg_ev = sum(counts) / len(counts) if counts else 0

    L = []
    L.append("# 瓒嬪娍璇佹嵁璇勪及鎶ュ憡 (trend_explanation_eval_v1)\n")
    L.append(f"- 鐢熸垚锛歿datetime.now().isoformat(timespec='seconds')}")
    L.append("- 妯″潡锛欳锛堣瘉鎹绱?RAG锛屽畬鏁寸増鍥涢噸绾︽潫 + 鑱氬悎淇″彿锛?)
    L.append("- 杈撳嚭锛歚data/gold/trend_evidence_v1.jsonl`\n")
    L.append("## 1. 鏍稿績鎸囨爣\n")
    L.append("| 鎸囨爣 | 鏁板€?|")
    L.append("|---|---|")
    L.append(f"| 瓒嬪娍缁撹鎬绘暟 | {total} |")
    L.append(f"| **鍚仛鍚堜俊鍙?aggregate)瑕嗙洊鐜?* | **{agg_cov:.1%}**锛坽wa}/{total}锛?|")
    L.append(f"| 鍚共鍑€浜嬩欢鏍锋湰瑕嗙洊鐜?| {cov:.1%}锛坽we}/{total}锛?|")
    L.append(f"| 骞冲潎骞插噣浜嬩欢鏁?鏉?| {avg_ev:.2f}锛圱opK={TOPK}锛?|")
    L.append(f"| 鑱氬悎鏂瑰悜涓庣粨璁轰竴鑷?| {stats['aligned']}/{total} |")
    L.append(f"| 瑕嗙洊瑙掕壊 | {len(stats['roles'])} |\n")
    L.append("## 2. 涓ゅ眰璇佹嵁璇存槑\n")
    L.append("**涓诲姏 = 鑱氬悎淇″彿**锛氭瘡鏉＄粨璁哄嚑涔庨兘鏈?aggregate锛堢瘒鏁?鎯呯华/鏈轰細路椋庨櫓/鍑€淇″彿锛夛紝"
             "鐢卞绡囨枃妗ｇ粺璁¤€屾潵锛屽鍗曠瘒鍣煶绋冲仴锛屾槸瓒嬪娍浣愯瘉涓诲姏锛岃鐩栫巼杩滈珮浜庡共鍑€浜嬩欢銆俓n")
    L.append("**浣愯瘉 = 骞插噣浜嬩欢鏍锋湰**锛氳繃鍥涢噸绾︽潫锛堟妧鑳界櫧鍚嶅崟+涓婚鍏辩幇+鍩熷悕榛戝悕鍗?鏂瑰悜涓€鑷达級鎵嶅叆閫夛紝"
             "灏戣€岀簿锛屾爣娉ㄢ€滅浉鍏虫€ц繎浼尖€濄€俓n")
    L.append("## 3. 鏁版嵁璐ㄩ噺涓庡彛寰刓n")
    L.append("1. GDELT 鏃犳爣棰?姝ｆ枃锛屽尮閰嶅涓哄叧閿瘝/URL 浼瘝锛涙湰妯″潡鐢ㄧ害鏉熸崲绮惧害锛屽彫鍥炰笉瓒崇敱鑱氬悎鍏滃簳銆?)
    L.append("2. 鏂瑰悜褰掍竴锛欱 鐨?`flat` 鈫?濂戠害 `stable`锛屽師鍊煎瓨 `trend_direction_raw`銆?)
    L.append("3. 绮掑害锛氭寜 `canonical_role` 鍑鸿锛宍role_family`=taxonomy.category锛孌 鍙仛鍚堛€?)
    L.append("4. JD 璇佹嵁 `job_url` 婧愭暟鎹负绌猴紝闄嶇骇涓哄瓨鍦ㄦ€ц瘉鎹紙鍏徃/鏍囬/钖祫锛夈€俓n")
    sample = next((r for r in rows_out if r["evidence_topk"]), rows_out[0] if rows_out else None)
    if sample:
        L.append("## 4. 鎶芥鏍蜂緥\n")
        slim = dict(sample)
        slim["evidence_topk"] = slim["evidence_topk"][:2]
        slim["jd_evidence"] = slim["jd_evidence"][:1]
        L.append("```json")
        L.append(json.dumps(slim, ensure_ascii=False, indent=2))
        L.append("```")
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--monthly", action="store_true",
                    help="閫愭湀鍏ㄩ噺(69脳36=2484琛?甯︾紦瀛?鍑?trend_evidence_monthly_v1.jsonl)锛涢粯璁ら噷绋嬬(345琛?")
    args = ap.parse_args()
    main(granularity="monthly" if args.monthly else "milestone")

