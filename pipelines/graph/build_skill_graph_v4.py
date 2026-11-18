"""构建 skill_prerequisite_v4.json —— 三路信号融合的技能先修图(设计方案 learning_path_method_v2.md)。

相比 v3(人工种子图 276 节点 347 边)的改进:

1. **LLM 先修补全(主路)**:DeepSeek JSON mode 批量预测技能对先修关系。
   - 候选对 = v3 种子边(重校验) + JD 高共现对 + 同类目采样对;
   - 每批 12 对/次 prompt,每批 temperature=0 跑 3 次自洽投票,agreement=多数票比例;
   - 反向验证:正向通过的边再问 B→A,正反向冲突的边降级/丢弃(先修关系必须非对称);
   - 限速 sleep 0.3s、失败重试 3 次、中间结果落盘缓存目录支持断点续跑。
2. **资源共现(辅助路)**:同资源 skill_ids 共现,资源带 level 时低 level → 高 level 记方向先验。
3. **JD 共现不对称(辅助路)**:12.7 万 JD 技能共现,P(A|B)>>P(A) 且不对称时 A 更基础。

融合:confidence = 0.5·LLM_agreement + 0.3·v3_seed + 0.2·cooccur_score(+反向印证 bonus 0.15,
正反向冲突 −0.2),阈值 0.5 收边;v3 人工边永不删除只降权。输出保证 DAG(破环时删最低
confidence 边,出度 ≤5 剪枝)。

hours_estimate = 该技能资源 duration_hours 中位数 × 0.6(无资源回退 v3 值 → 类目中位数 → 10);
difficulty_score = 资源 level(quality 加权)均值归一,保留离散 difficulty 标签向后兼容。

QC:边数/覆盖率/环处理数/LLM 调用数与成本/与 v3 重合率/LLM 与 v3 一致率(precision 代理)
/20 条新边抽样,写 data/gold/skill_prerequisite_v4_qc.json。

用法:
    /var/lib/jobnav-env/bin/python -m pipelines.graph.build_skill_graph_v4            # 全流程
    /var/lib/jobnav-env/bin/python -m pipelines.graph.build_skill_graph_v4 --skip-llm # 纯数据降级
    /var/lib/jobnav-env/bin/python -m pipelines.graph.build_skill_graph_v4 --max-pairs 800
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[2]
GOLD_DIR = ROOT / "data" / "gold"
VOCAB_PATH = GOLD_DIR / "skill_vocab_v2.json"
V3_GRAPH_PATH = GOLD_DIR / "skill_prerequisite_v3.json"
RESOURCES_PATH = GOLD_DIR / "learning_resources_v4.json"
OUT_PATH = GOLD_DIR / "skill_prerequisite_v4.json"
QC_PATH = GOLD_DIR / "skill_prerequisite_v4_qc.json"
JD_ENRICHED_DIR = Path(
    os.environ.get("JOBNAV_JD_ENRICHED_DIR",
                   "/data/shichaojian/JNIT/processed/jd_unified_v3_enriched")
)
CACHE_DIR = Path(
    os.environ.get("JOBNAV_SKILL_GRAPH_V4_CACHE",
                   "/data/shichaojian/JNIT/processed/skill_graph_v4_cache")
)

# ---------------------------------------------------------------------------
# 常量(对应设计方案 §1.5 / §2.1)
# ---------------------------------------------------------------------------
FUSION_W_LLM = 0.5
FUSION_W_V3_SEED = 0.3
FUSION_W_COOCCUR = 0.2
REVERSE_BONUS = 0.15        # 正向确认且反向拒绝 → +0.15
REVERSE_CONFLICT_PENALTY = 0.2  # 正反向都确认 → −0.2(先修必须非对称)
EDGE_CONF_THRESHOLD = 0.5
MAX_OUT_DEGREE = 5
SELF_CONSISTENCY_VOTES = 3
REVERSE_VOTES = 2
PAIRS_PER_BATCH = 12
LLM_SLEEP_SEC = 0.3
LLM_MAX_RETRY = 3
LLM_TIMEOUT_SEC = 60
RESOURCE_COOCUR_MIN_SUPPORT = 3   # 资源共现 ≥3 次才给满分方向先验
HOURS_DISCOUNT = 0.6              # 学习该技能不需要看完所有资源
LEVEL_VALUE = {"beginner": 1.0, "intermediate": 2.0, "advanced": 3.0}
DIFFICULTY_LABELS = ((0.4, "beginner"), (0.7, "intermediate"), (1.01, "advanced"))
# deepseek-chat 官网价(¥/1M tokens,缓存未命中输入 / 输出),仅用于 QC 成本估计
PRICE_INPUT_PER_M = 2.0
PRICE_OUTPUT_PER_M = 8.0
RANDOM_SEED = 42

sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_vocab() -> list[dict]:
    payload = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    return payload["skills"]


def load_v3_graph() -> dict[str, dict]:
    payload = json.loads(V3_GRAPH_PATH.read_text(encoding="utf-8"))
    return {s["skill_id"]: s for s in payload.get("skills", [])}


def load_resources() -> list[dict]:
    payload = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
    return payload.get("resources") or []


def build_skill_resource_index(
    resources: list[dict], vocab_ids: set[str]
) -> dict[str, dict]:
    """技能 → 资源标题/时长/level 分布(资源共现与 hours/difficulty 估计共用)。"""
    index: dict[str, dict] = {sid: {"titles": [], "durations": [],
                                    "levels": [], "quality": []} for sid in vocab_ids}
    for res in resources:
        skill_ids = [s for s in (res.get("skill_ids") or []) if s in vocab_ids]
        duration = res.get("duration_hours")
        level = res.get("level") if res.get("level") in LEVEL_VALUE else None
        quality = float(res.get("quality_score") or 0.5)
        title = str(res.get("title") or "")
        for sid in skill_ids:
            entry = index[sid]
            if title and len(entry["titles"]) < 6:
                entry["titles"].append(title)
            if duration and float(duration) > 0:
                entry["durations"].append(float(duration))
            if level:
                entry["levels"].append((LEVEL_VALUE[level], quality))
            entry["quality"].append(quality)
    return index


def build_resource_direction(
    res_index: dict[str, dict],
) -> dict[str, float]:
    """各技能自身资源 level 的 quality 加权均值(1-3),作为资源侧层级估计。"""
    mean_level: dict[str, float] = {}
    for sid, entry in res_index.items():
        if entry["levels"]:
            total_w = sum(q for _, q in entry["levels"]) or 1e-8
            mean_level[sid] = sum(lv * q for lv, q in entry["levels"]) / total_w
    return mean_level


def compute_jd_cooccurrence(
    vocab_ids: set[str],
) -> tuple[dict[str, int], dict[tuple[str, str], int], int]:
    """JD 技能共现:返回 (skill计数, 无序对计数, JD总数)。只读 skills 列,内存友好。"""
    import pyarrow.dataset as ds

    dataset = ds.dataset(str(JD_ENRICHED_DIR), format="parquet")
    skill_count: dict[str, int] = defaultdict(int)
    pair_count: dict[tuple[str, str], int] = defaultdict(int)
    total_jd = 0
    for batch in dataset.to_batches(columns=["skills"], batch_size=4096):
        for skills in batch.column("skills").to_pylist():
            ids = sorted({s for s in (skills or []) if s in vocab_ids})
            if not ids:
                continue
            total_jd += 1
            for sid in ids:
                skill_count[sid] += 1
            for a, b in itertools.combinations(ids, 2):
                pair_count[(a, b)] += 1
    return dict(skill_count), dict(pair_count), total_jd


def jd_directional_score(
    a: str, b: str, skill_count: dict[str, int],
    pair_count: dict[tuple[str, str], int], total_jd: int,
) -> float:
    """边 A→B(A 是 B 的先修)的 JD 不对称支持 [0,1]。

    A 更基础 ⇒ 需要 B 的 JD 大多也要 A ⇒ P(A|B) >> P(A) 且 P(A|B) > P(B|A)。
    """
    pair = pair_count.get((a, b)) or pair_count.get((b, a)) or 0
    if pair < 20 or total_jd == 0:
        return 0.0
    ca, cb = skill_count.get(a, 0), skill_count.get(b, 0)
    if ca < 30 or cb < 30:
        return 0.0
    cond_ab = pair / cb          # P(A|B)
    cond_ba = pair / ca          # P(B|A)
    lift_ab = cond_ab / (ca / total_jd)
    if lift_ab < 1.2:
        return 0.0
    asym = (cond_ab - cond_ba) / (cond_ab + cond_ba + 1e-9)
    return max(0.0, min(1.0, asym))


# ---------------------------------------------------------------------------
# 候选对采样
# ---------------------------------------------------------------------------

def sample_candidate_pairs(
    vocab: list[dict],
    v3_nodes: dict[str, dict],
    skill_count: dict[str, int],
    pair_count: dict[tuple[str, str], int],
    max_pairs: int,
) -> list[tuple[str, str, str]]:
    """返回 [(a, b, source)],A→B 表示"Ask: A 是否是 B 的先修"。source ∈ seed/jd_cooccur/category。"""
    rng = random.Random(RANDOM_SEED)
    pairs: dict[tuple[str, str], str] = {}

    # 1) v3 种子边(重校验,源方向即 v3 方向)
    for sid, node in v3_nodes.items():
        for pre in node.get("prerequisites") or []:
            if pre in v3_nodes or any(s["id"] == pre for s in vocab):
                pairs.setdefault((pre, sid), "v3_seed")

    vocab_ids = {s["id"] for s in vocab}
    by_category: dict[str, list[str]] = defaultdict(list)
    for s in vocab:
        by_category[s["category"]].append(s["id"])

    # 2) JD 高共现对:每个技能取不对称性最强的 3 个搭档
    asym_ranked: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
    for (a, b), cnt in pair_count.items():
        if cnt < 30:
            continue
        ca, cb = skill_count.get(a, 0), skill_count.get(b, 0)
        if ca < 30 or cb < 30:
            continue
        cond_ab, cond_ba = cnt / cb, cnt / ca
        asym = abs(cond_ab - cond_ba) / (cond_ab + cond_ba + 1e-9)
        direction = (a, b) if cond_ab > cond_ba else (b, a)
        asym_ranked[direction[0]].append((asym * min(cond_ab, cond_ba), direction[1], "jd_cooccur"))
    for a, cands in asym_ranked.items():
        cands.sort(reverse=True)
        for _, b, src in cands[:3]:
            if a != b and b in vocab_ids:
                pairs.setdefault((a, b), src)

    # 3) 同类目采样:每个技能随机 2 个同类搭档(覆盖冷启动/低频技能)
    for s in vocab:
        same = [x for x in by_category[s["category"]] if x != s["id"]]
        rng.shuffle(same)
        for b in same[:2]:
            key = tuple(sorted((s["id"], b)))
            pairs.setdefault((key[0], key[1]), "category")

    # 配额:保证 seed 全保留,jd/category 按配额截断
    ordered = sorted(pairs.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    rng.shuffle(ordered)
    seeds = [(k, v) for k, v in ordered if v == "v3_seed"]
    others = [(k, v) for k, v in ordered if v != "v3_seed"]
    budget_others = max(0, max_pairs - len(seeds))
    selected = seeds + others[:budget_others]
    return [(a, b, src) for (a, b), src in selected]


# ---------------------------------------------------------------------------
# LLM 批量预测(DeepSeek JSON mode)
# ---------------------------------------------------------------------------

def _llm_settings() -> tuple[str, str, str]:
    from app.core.config import settings
    return settings.llm_base_url, settings.llm_api_key, settings.llm_model


def _cache_key(payload_text: str, tag: str) -> Path:
    digest = hashlib.sha256(f"{tag}\n{payload_text}".encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{tag}_{digest}.json"


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _call_deepseek(system: str, prompt: str, usage: dict) -> dict | None:
    import httpx

    base_url, api_key, model = _llm_settings()
    if not api_key:
        return None
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    for attempt in range(LLM_MAX_RETRY):
        try:
            with httpx.Client(timeout=LLM_TIMEOUT_SEC) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
            data = resp.json()
            u = data.get("usage") or {}
            usage["calls"] = usage.get("calls", 0) + 1
            usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + int(u.get("prompt_tokens", 0))
            usage["completion_tokens"] = usage.get("completion_tokens", 0) + int(u.get("completion_tokens", 0))
            content = (data["choices"][0]["message"]["content"] or "").strip()
            parsed = _extract_json(content)
            if parsed is not None:
                return parsed
        except Exception:
            if attempt == LLM_MAX_RETRY - 1:
                return None
            time.sleep(2.0 * (attempt + 1))
        time.sleep(LLM_SLEEP_SEC)
    return None


def _skill_card(sid: str, vocab_map: dict[str, dict], res_index: dict[str, dict]) -> str:
    s = vocab_map[sid]
    titles = res_index.get(sid, {}).get("titles") or []
    titles_txt = "; ".join(titles[:3]) if titles else "无"
    return (f"- {sid} | {s['name']} | category={s['category']} | "
            f"别名: {', '.join((s.get('aliases') or [])[:3]) or '-'} | 代表资源: {titles_txt}")


def _build_batch_prompt(
    batch: list[tuple[str, str]], vocab_map: dict[str, dict],
    res_index: dict[str, dict],
) -> str:
    involved = sorted({sid for a, b in batch for sid in (a, b)})
    cards = "\n".join(_skill_card(sid, vocab_map, res_index) for sid in involved)
    pair_lines = "\n".join(f'{i + 1}. {a} -> {b}' for i, (a, b) in enumerate(batch))
    return (
        "你是 IT 技能教育体系设计专家。下面给出一批候选技能对「A -> B」,请判断 A 是否是 B 的"
        "合理先修(prerequisite):即学习 B 之前是否应当先掌握 A。\n"
        "判断标准:概念依赖(如 微积分->机器学习)、工具依赖(如 docker->kubernetes)、"
        "难度递进(明显更基础的排前面)。方向必须非对称:若两者互为先修或只是并列相关,判 false。\n"
        "只依据给出的技能信息判断,不要引入白名单外技能。\n\n"
        f"技能信息:\n{cards}\n\n"
        f"候选对(共 {len(batch)} 对):\n{pair_lines}\n\n"
        '对每一对输出判定,JSON 格式:{"results":[{"from_id":"...","to_id":"...","is_prereq":true,'
        '"confidence":0.0-1.0}]}。必须覆盖全部候选对,无关/并列/方向反了都判 false。'
    )


def _parse_batch_result(
    parsed: dict | None, batch: list[tuple[str, str]]
) -> dict[tuple[str, str], tuple[bool, float]]:
    """返回 {(a,b): (is_prereq, confidence)};缺失的对按 false 处理。"""
    verdicts: dict[tuple[str, str], tuple[bool, float]] = {}
    results = (parsed or {}).get("results") or []
    seen: set[tuple[str, str]] = set()
    for row in results:
        a, b = str(row.get("from_id") or ""), str(row.get("to_id") or "")
        if (a, b) in batch:
            try:
                conf = max(0.0, min(1.0, float(row.get("confidence"))))
            except (TypeError, ValueError):
                conf = 0.5 if row.get("is_prereq") else 0.0
            verdicts[(a, b)] = (bool(row.get("is_prereq")), conf)
            seen.add((a, b))
    for pair in batch:
        if pair not in seen:
            verdicts[pair] = (False, 0.0)
    return verdicts


def run_llm_voting(
    candidate_pairs: list[tuple[str, str]],
    vocab_map: dict[str, dict],
    res_index: dict[str, dict],
    usage: dict,
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    """自洽投票:每批 SELF_CONSISTENCY_VOTES 次,返回 (agreement, mean_true_confidence)。"""
    votes_true: dict[tuple[str, str], int] = defaultdict(int)
    conf_sum: dict[tuple[str, str], float] = defaultdict(float)
    batches = [candidate_pairs[i:i + PAIRS_PER_BATCH]
               for i in range(0, len(candidate_pairs), PAIRS_PER_BATCH)]
    system = "你是 IT 技能教育路径设计专家,以严格 JSON 输出。"
    for bi, batch in enumerate(batches):
        prompt = _build_batch_prompt(batch, vocab_map, res_index)
        tag = "vote"
        for vote in range(SELF_CONSISTENCY_VOTES):
            key = _cache_key(prompt + f"\n# vote {vote}", tag)
            if key.exists():
                parsed = json.loads(key.read_text(encoding="utf-8"))
            else:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                parsed = _call_deepseek(system, prompt, usage)
                if parsed is None:
                    print(f"[llm] batch {bi + 1}/{len(batches)} vote {vote + 1} FAILED, skip")
                    continue
                key.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
                time.sleep(LLM_SLEEP_SEC)
            for pair, (is_pre, conf) in _parse_batch_result(parsed, batch).items():
                if is_pre:
                    votes_true[pair] += 1
                    conf_sum[pair] += conf
        print(f"[llm] forward batch {bi + 1}/{len(batches)} done "
              f"({usage.get('calls', 0)} calls so far)")
    agreement = {p: votes_true[p] / SELF_CONSISTENCY_VOTES for p in candidate_pairs}
    mean_conf = {p: (conf_sum[p] / votes_true[p] if votes_true[p] else 0.0)
                 for p in candidate_pairs}
    return agreement, mean_conf


def run_reverse_validation(
    forward_pairs: list[tuple[str, str]],
    vocab_map: dict[str, dict],
    res_index: dict[str, dict],
    usage: dict,
) -> dict[tuple[str, str], float]:
    """反向验证:问 B→A 是否为先修。返回 {(a,b): reverse_agreement}(>0 表示反向也被确认)。"""
    reverse_input = [(b, a) for a, b in forward_pairs]
    batches = [reverse_input[i:i + PAIRS_PER_BATCH]
               for i in range(0, len(reverse_input), PAIRS_PER_BATCH)]
    system = "你是 IT 技能教育路径设计专家,以严格 JSON 输出。"
    reverse_votes: dict[tuple[str, str], int] = defaultdict(int)
    for bi, batch in enumerate(batches):
        prompt = _build_batch_prompt(batch, vocab_map, res_index)
        for vote in range(REVERSE_VOTES):
            key = _cache_key(prompt + f"\n# vote {vote}", "reverse")
            if key.exists():
                parsed = json.loads(key.read_text(encoding="utf-8"))
            else:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                parsed = _call_deepseek(system, prompt, usage)
                if parsed is None:
                    print(f"[llm] reverse batch {bi + 1}/{len(batches)} vote {vote + 1} FAILED")
                    continue
                key.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
                time.sleep(LLM_SLEEP_SEC)
            for (b, a), (is_pre, _conf) in _parse_batch_result(parsed, batch).items():
                if is_pre:
                    reverse_votes[(a, b)] += 1
    return {p: reverse_votes[p] / REVERSE_VOTES for p in forward_pairs}


# ---------------------------------------------------------------------------
# 融合 / DAG / 输出
# ---------------------------------------------------------------------------

def _find_cycle_edges(
    edges: dict[tuple[str, str], float]
) -> list[tuple[str, str]]:
    """当前边集中仍处在环上的边(迭代剥离入度 0 节点后剩下的部分)。"""
    nodes = {n for e in edges for n in e}
    indeg = {n: 0 for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        indeg[b] += 1
        children[a].append(b)
    queue = [n for n in nodes if indeg[n] == 0]
    removed = set(nodes)
    while queue:
        n = queue.pop()
        removed.discard(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)
    return [(a, b) for (a, b) in edges if a in removed and b in removed]


def enforce_dag_and_outdegree(
    edge_conf: dict[tuple[str, str], float],
    edge_is_seed: dict[tuple[str, str], bool],
) -> tuple[dict[tuple[str, str], float], int, int]:
    """保证 DAG 并控制每个技能的先修列表长度 ≤ MAX_OUT_DEGREE。

    环:反复删除环上 confidence 最低的非种子边(全是种子则删最低 confidence)。
    先修数:某技能的入边(先修列表)超过 5 时,按 confidence 升序删非种子边;
    v3 种子边永不删除(只降权)。"""
    edges = dict(edge_conf)
    n_cycle = 0
    while True:
        cycle_edges = _find_cycle_edges(edges)
        if not cycle_edges:
            break
        non_seed = [e for e in cycle_edges if not edge_is_seed.get(e)]
        victim = min(non_seed or cycle_edges,
                     key=lambda e: (edges[e], edge_is_seed.get(e, False), e))
        del edges[victim]
        n_cycle += 1
    # 先修列表长度剪枝(边 A→B 中 B 的先修数 = B 的入边数)
    incoming: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in edges:
        incoming[e[1]].append(e)
    pruned = 0
    for b, es in incoming.items():
        if len(es) > MAX_OUT_DEGREE:
            es.sort(key=lambda e: (edges[e], edge_is_seed.get(e, False), e))
            count = len(es)
            for e in es:  # 从最低 confidence 的非种子边开始删,直到 ≤5 或只剩种子
                if count <= MAX_OUT_DEGREE:
                    break
                if not edge_is_seed.get(e):
                    del edges[e]
                    pruned += 1
                    count -= 1
    return edges, n_cycle, pruned


def estimate_hours(
    sid: str,
    res_index: dict[str, dict],
    v3_nodes: dict[str, dict],
    category_hours: dict[str, float],
    vocab_map: dict[str, dict],
) -> tuple[float, str]:
    durations = sorted(res_index.get(sid, {}).get("durations") or [])
    if durations:
        return max(2.0, round(_median(durations) * HOURS_DISCOUNT)), "resource_median"
    v3 = v3_nodes.get(sid)
    if v3 and v3.get("hours_estimate"):
        return float(v3["hours_estimate"]), "v3_fallback"
    cat = vocab_map[sid]["category"]
    if cat in category_hours:
        return category_hours[cat], "category_median"
    return 10.0, "default"


def estimate_difficulty(
    sid: str, res_index: dict[str, dict], v3_nodes: dict[str, dict]
) -> tuple[float, str]:
    levels = res_index.get(sid, {}).get("levels") or []
    if levels:
        total_w = sum(q for _, q in levels) or 1e-8
        wmean = sum(lv * q for lv, q in levels) / total_w
        score = max(0.0, min(1.0, (wmean - 1.0) / 2.0))
        return score, "resource_level"
    v3 = v3_nodes.get(sid)
    if v3 and v3.get("level"):
        return max(0.0, min(1.0, (float(v3["level"]) - 1.0) / 3.0)), "v3_level"
    return 0.35, "default"


def _median(values: list[float]) -> float:
    n = len(values)
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def _difficulty_label(score: float) -> str:
    for threshold, label in DIFFICULTY_LABELS:
        if score < threshold:
            return label
    return "advanced"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pairs", type=int, default=1300, help="候选对总量上限")
    parser.add_argument("--skip-llm", action="store_true", help="纯数据降级(不调 DeepSeek)")
    parser.add_argument("--out", type=str, default=str(OUT_PATH))
    args = parser.parse_args()

    t0 = time.time()
    print("[1/6] 加载词表 / v3 种子图 / 资源库 ...")
    vocab = load_vocab()
    vocab_map = {s["id"]: s for s in vocab}
    vocab_ids = set(vocab_map)
    v3_nodes = load_v3_graph()
    resources = load_resources()
    res_index = build_skill_resource_index(resources, vocab_ids)
    mean_res_level = build_resource_direction(res_index)

    print(f"      词表 {len(vocab)} 技能;v3 图 {len(v3_nodes)} 节点;"
          f"资源 {len(resources)} 条")
    # 资源共现方向支持
    res_cooccur_support: dict[tuple[str, str], int] = defaultdict(int)
    for res in resources:
        ids = sorted({s for s in (res.get("skill_ids") or []) if s in vocab_ids})
        for a, b in itertools.combinations(ids, 2):
            la, lb = mean_res_level.get(a, 2.0), mean_res_level.get(b, 2.0)
            if abs(la - lb) >= 0.5:
                lo, hi = (a, b) if la < lb else (b, a)
                res_cooccur_support[(lo, hi)] += 1

    print("[2/6] JD 共现统计 ...")
    skill_count, pair_count, total_jd = compute_jd_cooccurrence(vocab_ids)
    print(f"      {total_jd} 条 JD 含白名单技能;{len(pair_count)} 个共现对")

    print("[3/6] 采样候选对 ...")
    candidates = sample_candidate_pairs(vocab, v3_nodes, skill_count, pair_count, args.max_pairs)
    by_source: dict[str, int] = defaultdict(int)
    for _, _, src in candidates:
        by_source[src] += 1
    print(f"      候选对 {len(candidates)} 对({dict(by_source)})")

    usage: dict = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
    agreement: dict[tuple[str, str], float] = {}
    mean_conf: dict[tuple[str, str], float] = {}
    if not args.skip_llm:
        print(f"[4/6] LLM 批量预测(每对 {SELF_CONSISTENCY_VOTES} 票,批大小 {PAIRS_PER_BATCH})...")
        candidate_only = [(a, b) for a, b, _ in candidates]
        agreement, mean_conf = run_llm_voting(candidate_only, vocab_map, res_index, usage)
        # 反向验证:正向 agreement ≥ 2/3 的边
        to_reverse = [p for p in candidate_only if agreement.get(p, 0) >= 2 / 3]
        print(f"      反向验证 {len(to_reverse)} 条正向边 ...")
        reverse_agr = run_reverse_validation(to_reverse, vocab_map, res_index, usage)
    else:
        print("[4/6] --skip-llm:跳过 LLM 预测")
        reverse_agr = {}

    print("[5/6] 融合 + DAG 约束 ...")
    seed_set = {(a, b) for a, b, src in candidates if src == "v3_seed"}
    edge_conf: dict[tuple[str, str], float] = {}
    edge_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    edge_detail: dict[tuple[str, str], dict] = {}
    for a, b, src in candidates:
        llm_agr = agreement.get((a, b), 0.0)
        jd_score = jd_directional_score(a, b, skill_count, pair_count, total_jd)
        res_score = min(1.0, res_cooccur_support.get((a, b), 0) / RESOURCE_COOCUR_MIN_SUPPORT)
        cooccur_score = max(0.6 * jd_score + 0.4 * res_score, res_score * 0.8)
        is_seed = (a, b) in seed_set or (
            b in v3_nodes and a in (v3_nodes[b].get("prerequisites") or []))
        conf = (FUSION_W_LLM * llm_agr + FUSION_W_V3_SEED * (1.0 if is_seed else 0.0)
                + FUSION_W_COOCCUR * cooccur_score)
        rev = reverse_agr.get((a, b), 0.0)
        if llm_agr >= 2 / 3:
            if rev <= 0.0:
                conf += REVERSE_BONUS
            elif rev >= 0.5:
                conf -= REVERSE_CONFLICT_PENALTY
        conf = max(0.0, min(1.0, round(conf, 4)))
        keep = is_seed or conf >= EDGE_CONF_THRESHOLD
        if not keep:
            continue
        if is_seed:
            edge_sources[(a, b)].add("v3_seed")
        if llm_agr > 0:
            edge_sources[(a, b)].add("llm_deepseek")
        if jd_score > 0:
            edge_sources[(a, b)].add("jd_cooccur")
        if res_score > 0:
            edge_sources[(a, b)].add("resource_cooccur")
        edge_conf[(a, b)] = conf
        edge_detail[(a, b)] = {
            "llm_agreement": round(llm_agr, 4),
            "llm_mean_confidence": round(mean_conf.get((a, b), 0.0), 4),
            "jd_directional": round(jd_score, 4),
            "resource_directional": round(res_score, 4),
            "reverse_agreement": round(rev, 4),
            "v3_seed": bool(is_seed),
        }

    edge_is_seed = {e: "v3_seed" in edge_sources[e] for e in edge_conf}
    edges, n_cycle, n_pruned = enforce_dag_and_outdegree(edge_conf, edge_is_seed)
    print(f"      收边 {len(edges)} 条(破环删 {n_cycle},出度剪枝 {n_pruned})")

    # 难度 / 时长估计
    raw_hours: dict[str, tuple[float, str]] = {}
    for sid in vocab_ids:
        hours, src = estimate_hours(sid, res_index, v3_nodes, {}, vocab_map)
        raw_hours[sid] = (hours, src)
    cat_vals: dict[str, list[float]] = defaultdict(list)
    for sid, (hours, src) in raw_hours.items():
        if src == "resource_median":
            cat_vals[vocab_map[sid]["category"]].append(hours)
    category_hours = {c: round(_median(sorted(v)), 1) for c, v in cat_vals.items()}
    for sid in vocab_ids:
        hours, src = raw_hours[sid]
        if src != "resource_median":
            hours, src = estimate_hours(sid, res_index, v3_nodes, category_hours, vocab_map)
            raw_hours[sid] = (hours, src)

    dependents: dict[str, list[str]] = defaultdict(list)
    for (a, b) in edges:
        dependents[b].append(a)

    print("[6/6] 写出 v4 图 + QC ...")
    out_skills = []
    for s in vocab:
        sid = s["id"]
        diff_score, diff_src = estimate_difficulty(sid, res_index, v3_nodes)
        hours, hours_src = raw_hours[sid]
        prereqs = sorted((a for (a, b) in edges if b == sid),
                         key=lambda a: (-edges[(a, sid)], a))
        prereq_detail = [
            {"skill_id": a, "confidence": edges[(a, sid)],
             "sources": sorted(edge_sources[(a, sid)])}
            for a in prereqs
        ]
        node = {
            "skill_id": sid,
            "skill_name": s["name"],
            "category": s["category"],
            "level": max(1, min(4, round(diff_score * 3) + 1)),
            "difficulty": _difficulty_label(diff_score),
            "difficulty_score": round(diff_score, 4),
            "hours_estimate": int(round(hours)),
            "hot": bool(s.get("hot", False)),
            "aliases": s.get("aliases") or [],
            "prerequisites": prereqs,
            "prereq_detail": prereq_detail,
            "evidence": {
                "hours_source": hours_src,
                "difficulty_source": diff_src,
                "resource_hours_median": (round(_median(sorted(res_index[sid]["durations"])), 1)
                                          if res_index[sid]["durations"] else None),
                "resource_level_mean": (round(sum(lv * q for lv, q in res_index[sid]["levels"])
                                              / (sum(q for _, q in res_index[sid]["levels"]) or 1e-8), 3)
                                        if res_index[sid]["levels"] else None),
                "jd_count": skill_count.get(sid, 0),
                "dependents": len(dependents.get(sid, [])),
            },
        }
        v3_node = v3_nodes.get(sid)
        if v3_node:
            node["aliases"] = sorted(set(node["aliases"]) | set(v3_node.get("aliases") or []))
        out_skills.append(node)

    v4_edge_set = set(edges)
    v3_edge_set = {(a, b) for b, n in v3_nodes.items() for a in (n.get("prerequisites") or [])}
    # LLM 与 v3 一致率(precision 代理):v3 种子边中被 LLM agreement ≥ 2/3 确认的比例
    seed_confirmed = sum(
        1 for a, b in seed_set if agreement.get((a, b), 0.0) >= 2 / 3
    )
    covered = {n for e in v4_edge_set for n in e}
    new_edges = sorted((e for e in v4_edge_set if e not in v3_edge_set),
                       key=lambda e: (-edges[e], e))
    llm_new = [e for e in new_edges if "llm_deepseek" in edge_sources[e]]

    cost_yuan = (usage["prompt_tokens"] / 1e6 * PRICE_INPUT_PER_M
                 + usage["completion_tokens"] / 1e6 * PRICE_OUTPUT_PER_M)
    qc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_skills": len(vocab),
        "edge_count": len(v4_edge_set),
        "node_count": len(covered),
        "coverage": round(len(covered) / len(vocab), 4),
        "v3_comparison": {
            "v3_nodes": len(v3_nodes), "v3_edges": len(v3_edge_set),
            "overlap_edges": len(v4_edge_set & v3_edge_set),
            "overlap_rate_vs_v3": round(len(v4_edge_set & v3_edge_set) / max(1, len(v3_edge_set)), 4),
            "new_edges": len(new_edges),
            "new_edges_from_llm": len(llm_new),
        },
        "dag": {"cycles_broken": n_cycle, "prereq_count_pruned": n_pruned,
                "is_dag": not _find_cycle_edges(edges),
                "max_prereq_count": max((len([1 for e in v4_edge_set if e[1] == b]) for b in covered),
                                        default=0)},
        "llm": {
            "enabled": not args.skip_llm,
            "candidate_pairs": len(candidates),
            "candidate_pairs_by_source": dict(by_source),
            "api_calls": usage["calls"],
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "estimated_cost_yuan": round(cost_yuan, 4),
            "seed_edges_llm_confirmed": seed_confirmed,
            "seed_edges_total": len(seed_set),
            "llm_v3_agreement_rate": round(seed_confirmed / max(1, len(seed_set)), 4),
        },
        "hours": {
            "median": _median(sorted(h for h, _ in raw_hours.values())),
            "mean": round(sum(h for h, _ in raw_hours.values()) / len(raw_hours), 1),
            "min": min(h for h, _ in raw_hours.values()),
            "max": max(h for h, _ in raw_hours.values()),
            "source_dist": _count_by_src(raw_hours),
        },
        "difficulty": _count_difficulty(out_skills),
        "sample_new_edges": [
            {"from": a, "to": b,
             "from_name": vocab_map[a]["name"], "to_name": vocab_map[b]["name"],
             "confidence": edges[(a, b)],
             "sources": sorted(edge_sources[(a, b)]),
             "llm_agreement": edge_detail[(a, b)]["llm_agreement"]}
            for a, b in new_edges[:20]
        ],
        "elapsed_sec": round(time.time() - t0, 1),
    }

    payload = {
        "version": "v4",
        "description": "三路融合(LLM 先修预测 + v3 种子 + JD/资源共现)技能先修 DAG,"
                       "详见 learning_path_method_v2.md",
        "generated_at": qc["generated_at"],
        "total": len(out_skills),
        "edge_count": len(v4_edge_set),
        "sources": ["v3_seed", "llm_deepseek", "jd_cooccur", "resource_cooccur"],
        "fusion_weights": {"llm_agreement": FUSION_W_LLM, "v3_seed": FUSION_W_V3_SEED,
                           "cooccur": FUSION_W_COOCCUR},
        "skills": out_skills,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    QC_PATH.write_text(json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"      写出 {out_path}({len(v4_edge_set)} 边,覆盖 {len(covered)}/295)")
    print(f"      QC:覆盖率 {qc['coverage']:.1%},与 v3 重合 {qc['v3_comparison']['overlap_rate_vs_v3']:.1%},"
          f"LLM 一致率 {qc['llm']['llm_v3_agreement_rate']:.1%},"
          f"API 调用 {usage['calls']} 次 ≈ ¥{cost_yuan:.2f}")
    print(f"      QC 写入 {QC_PATH}")


def _count_by_src(raw_hours: dict[str, tuple[float, str]]) -> dict[str, int]:
    dist: dict[str, int] = defaultdict(int)
    for _, src in raw_hours.values():
        dist[src] += 1
    return dict(dist)


def _count_difficulty(skills: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = defaultdict(int)
    for s in skills:
        dist[s["difficulty"]] += 1
    return dict(dist)


if __name__ == "__main__":
    main()
