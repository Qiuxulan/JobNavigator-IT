"""build_prereq_graph_v3: 用 roadmap.sh 真实路线图重建技能先修图.

以 roadmap.sh 社区维护的 IT 学习路线图（react-flow JSON，nodes + edges）为主数据源,
与手工维护的 ``skill_prerequisite_v2``（275 节点 / 331 边，置信度视为高）合并,
重建技能先修图 v3. 同时顺手抽取内容 MD 中的 @course@/@video@/@official@ 资源链接,
产出中间产物 ``roadmap_skill_resources.json`` 供后续资源库任务使用.

构建逻辑:
1. 从本地浅克隆仓库枚举 slug, 选定 45 张 IT 相关路线图（排除 computer-science 等
   纯理论图及 product-manager 等非 IT 岗位图）, 逐张 curl ``roadmap.sh/<slug>.json``
   （3 次重试 + 0.3s 限速, 失败时回退本地缓存）;
2. 解析 react-flow JSON: 仅保留 topic/subtopic 类型节点, 过滤装饰/分组节点;
   边方向为「先学 → 后学」（source 是 target 的先修, 已抽查 frontend/devops/python
   图人工确认, 如 Internet → HTML、HTML/CSS → JavaScript 的学习顺序）;
3. label → skill_id: 归一化（小写 / 去标点 / 压缩空白）后查词表 alias_to_id,
   映射不上的 label 做频次统计进 QC, 不建新技能;
4. 合并 roadmap 边 ∪ v2 边; 同对 (prereq, skill) 方向相反记 conflict, 按 v2 优先;
5. DAG 校验: 拓扑排序检测环, 解环按「roadmap 边优先于 v2 边被移除」的最小破坏原则,
   全部解环操作记录进 QC;
6. 节点元数据: 275 旧节点继承 v2; 词表 v2 中新增且被 roadmap 命中的技能新增节点,
   level 由 roadmap 子图深度推断（root=1, 每深一层 +0.5, 封顶 4）,
   difficulty 默认 intermediate, hours 按 level 启发式 40/80/120/160.

产出:
- ``data/gold/skill_prerequisite_v3.json`` —— 结构同 v2（version/total/hot_count/skills,
  每节点 skill_id/skill_name/category/level/difficulty/hours_estimate/hot/prerequisites/
  aliases, 另附 edge_count 汇总）, 不覆盖 v2;
- ``data/gold/skill_prerequisite_v3_qc.json`` —— 拉取/解析/映射/合并/环处理全链路 QC;
- ``/data/shichaojian/JNIT/processed/roadmap_skill_resources.json`` —— 技能 → 资源链接列表.

入口: ``python -m pipelines.foundation.build_prereq_graph_v3`` （幂等, 重复运行覆盖输出）.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
V2_JSON = ROOT / "data/gold/skill_prerequisite_v2.json"
VOCAB_JSON = ROOT / "data/gold/skill_vocab_v2.json"
V3_JSON = ROOT / "data/gold/skill_prerequisite_v3.json"
QC_JSON = ROOT / "data/gold/skill_prerequisite_v3_qc.json"

ROADMAP_REPO = Path("/data/shichaojian/JNIT/raw/roadmaps/developer-roadmap")
ROADMAP_CONTENT_DIR = ROADMAP_REPO / "roadmaps"
CACHE_DIR = Path("/data/shichaojian/JNIT/processed/roadmaps_json_cache")
RESOURCES_JSON = Path("/data/shichaojian/JNIT/processed/roadmap_skill_resources.json")

# 选定的 IT 相关路线图（45 张：语言/前端/后端/DevOps/云/数据/AI/安全/移动/QA）
SLUGS = [
    # 语言
    "python", "java", "javascript", "typescript", "golang", "rust",
    "c", "cpp", "php", "ruby",
    # 前端
    "frontend", "react", "vue", "angular", "nextjs", "html", "css",
    # 后端
    "backend", "full-stack", "nodejs", "django", "spring-boot",
    "ruby-on-rails",
    # DevOps / 云 / 基础设施
    "devops", "kubernetes", "docker", "aws", "terraform", "linux",
    "git-github", "shell-bash",
    # 数据 / AI
    "machine-learning", "ai-engineer", "ai-data-scientist", "mlops",
    "data-engineer", "data-analyst", "sql", "prompt-engineering",
    # 安全 / QA / 移动
    "cyber-security", "devsecops", "qa", "android", "ios", "flutter",
]

SKILL_NODE_TYPES = {"topic", "subtopic"}   # 其余为装饰/分组/连线节点
MAX_FETCH_RETRY = 3
FETCH_SLEEP = 0.3                          # 限速（秒）
LEVEL_MAX = 4.0
LEVEL_STEP = 0.5

RESOURCE_TAG_RE = re.compile(
    r"^-\s*\[@(course|video|official|article)\@\s*(.+?)\]\((https?://[^)]+)\)"
)


def norm_label(s: str) -> str:
    """label/alias 归一化: 小写、保留字母数字 +#%、去其余标点、压缩空白."""
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9+#%\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# 1. 拉取 roadmap JSON
# ---------------------------------------------------------------------------

def fetch_roadmap(slug: str) -> dict | None:
    """curl roadmap.sh/<slug>.json, 带重试与限速; 失败回退本地缓存."""
    url = f"https://roadmap.sh/{slug}.json"
    cache = CACHE_DIR / f"{slug}.json"
    for attempt in range(1, MAX_FETCH_RETRY + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JNIT-prereq-graph/3.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            time.sleep(FETCH_SLEEP)
            return data
        except Exception as exc:  # noqa: BLE001 - 网络异常统一重试
            print(f"    [warn] {slug} 第 {attempt} 次拉取失败: {exc}")
            time.sleep(FETCH_SLEEP * attempt)
    if cache.exists():
        print(f"    [warn] {slug} 在线拉取失败, 回退缓存 {cache}")
        return json.loads(cache.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# 2. 解析 react-flow JSON
# ---------------------------------------------------------------------------

def parse_roadmap(slug: str, data: dict) -> tuple[list[str], list[tuple[str, str]], int]:
    """返回 (node labels, edges[(source_label, target_label)], 类型过滤后边数).

    仅保留 topic/subtopic 类型节点, 过滤装饰/分组节点; 边方向为「先学 → 后学」.
    """
    nodes = {n["id"]: n for n in data.get("nodes", [])}
    labels: dict[str, str] = {}
    for nid, n in nodes.items():
        if n.get("type") not in SKILL_NODE_TYPES:
            continue
        label = ((n.get("data") or {}).get("label") or "").strip()
        if not label:
            continue
        labels[nid] = label
    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    n_type_filtered = 0
    for e in data.get("edges", []):
        s, t = labels.get(e.get("source")), labels.get(e.get("target"))
        if not s or not t or s == t:
            continue
        n_type_filtered += 1
        if (s, t) in seen:
            continue
        seen.add((s, t))
        edges.append((s, t))
    return list(labels.values()), edges, n_type_filtered


# ---------------------------------------------------------------------------
# 3. label → skill_id 映射
# ---------------------------------------------------------------------------

def build_alias_lookup(vocab: dict) -> tuple[dict[str, str], int]:
    """归一化 alias（含 id/name 本身）→ skill_id; 返回 (lookup, 冲突数)."""
    lookup: dict[str, str] = {}
    conflicts = 0
    entries = [(s["id"], s["id"]) for s in vocab["skills"]]
    entries += [(s["name"], s["id"]) for s in vocab["skills"]]
    entries += [(a, s["id"]) for s in vocab["skills"] for a in s.get("aliases", [])]
    entries += [(k, v) for k, v in vocab.get("alias_to_id", {}).items()]
    for alias, sid in entries:
        key = norm_label(alias)
        if not key:
            continue
        if key in lookup and lookup[key] != sid:
            conflicts += 1
            continue
        lookup.setdefault(key, sid)
    return lookup, conflicts


def map_label(label: str, lookup: dict[str, str]) -> str | None:
    key = norm_label(label)
    if key in lookup:
        return lookup[key]
    # 尾部长问答式 label 的轻量兜底: 去掉前导 "learn/what is/how to"
    m = re.match(r"^(?:learn|what is|how to|getting started with)\s+(.+)$", key)
    if m and m.group(1) in lookup:
        return lookup[m.group(1)]
    return None


# ---------------------------------------------------------------------------
# 4-6. 合并 / DAG 校验 / 元数据
# ---------------------------------------------------------------------------

def break_cycles(edges: dict[tuple[str, str], int], record: list[dict]) -> None:
    """拓扑排序检测环并按最小破坏原则解环（置信度低者优先移除）, 原地修改 edges."""
    while True:
        children: dict[str, list[str]] = defaultdict(list)
        indeg: Counter[str] = Counter()
        nodeset: set[str] = set()
        for (a, b) in edges:
            children[a].append(b)
            indeg[b] += 1
            nodeset.update((a, b))
        queue = [n for n in nodeset if indeg[n] == 0]
        visited = 0
        while queue:
            u = queue.pop()
            visited += 1
            for v in children[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)
        if visited == len(nodeset):
            return
        # 仍有环: 在当前剩余子图上找一条环, 移除其上置信度最低的边
        remaining = set(edges)
        # 用 DFS 找一个环
        color: dict[str, int] = {}
        stack: list[str] = []
        cycle_edges: list[tuple[str, str]] | None = None

        def dfs(u: str) -> bool:
            nonlocal cycle_edges
            color[u] = 1
            stack.append(u)
            for v in children[u]:
                if (u, v) not in remaining:
                    continue
                if color.get(v, 0) == 0:
                    if dfs(v):
                        return True
                elif color.get(v) == 1:
                    i = stack.index(v)
                    cycle_edges = list(zip(stack[i:], stack[i + 1:] + [v]))
                    return True
            stack.pop()
            color[u] = 2
            return False

        import sys
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, 100000))
        try:
            for n in nodeset:
                if color.get(n, 0) == 0 and dfs(n):
                    break
        finally:
            sys.setrecursionlimit(old_limit)
        if not cycle_edges:
            # 理论上不可达; 兜底: 移除任意一条剩余边
            victim = min(remaining, key=lambda e: edges[e])
            record.append({"removed_edge": list(victim),
                           "confidence": edges[victim], "reason": "fallback"})
            del edges[victim]
            continue
        victim = min(cycle_edges, key=lambda e: edges.get(e, 0))
        record.append({
            "cycle": [list(e) for e in cycle_edges],
            "removed_edge": list(victim),
            "confidence": edges[victim],
            "reason": "lowest_confidence_on_cycle",
        })
        del edges[victim]


def roadmap_depth_levels(node_skills: set[str],
                         edges: list[tuple[str, str]]) -> dict[str, float]:
    """roadmap 子图上按深度推断 level: root=1, 每深一层 +0.5, 封顶 LEVEL_MAX."""
    children: dict[str, list[str]] = defaultdict(list)
    indeg: Counter[str] = Counter()
    for a, b in edges:
        if a in node_skills and b in node_skills:
            children[a].append(b)
            indeg[b] += 1
    depth: dict[str, int] = {}
    queue = [n for n in node_skills if indeg[n] == 0]
    for n in queue:
        depth[n] = 0
    while queue:
        u = queue.pop()
        for v in children[u]:
            nd = depth[u] + 1
            if nd > depth.get(v, -1):
                depth[v] = nd
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return {n: min(LEVEL_MAX, 1.0 + LEVEL_STEP * d) for n, d in depth.items()}


def hours_by_level(level: float) -> int:
    return min(160, int(round(40 * level)))


def extract_resources() -> dict[str, dict]:
    """扫描内容 MD, 抽取 @course@/@video@/@official@ 资源链接."""
    resources: dict[str, dict] = {"_meta": {"slugs_scanned": len(SLUGS)}}
    for slug in SLUGS:
        cdir = ROADMAP_CONTENT_DIR / slug / "content"
        if not cdir.is_dir():
            continue
        for md in sorted(cdir.glob("*.md")):
            token = md.name.split("@", 1)[0].replace("-", " ").strip()
            key = norm_label(token)
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            links = []
            for line in text.splitlines():
                m = RESOURCE_TAG_RE.match(line.strip())
                if m:
                    links.append({"type": m.group(1), "title": m.group(2),
                                  "url": m.group(3), "roadmap": slug})
            if links:
                ent = resources.setdefault(
                    key, {"skill_key": token, "links": []})
                ent["links"].extend(links)
    resources["_meta"]["skill_keys"] = sum(
        1 for k in resources if not k.startswith("_"))
    resources["_meta"]["total_links"] = sum(
        len(v["links"]) for v in resources.values()
        if isinstance(v, dict) and "links" in v)
    return resources


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    v2 = json.loads(V2_JSON.read_text(encoding="utf-8"))
    vocab = json.loads(VOCAB_JSON.read_text(encoding="utf-8"))
    lookup, alias_conflicts = build_alias_lookup(vocab)

    # ---- 1-2. 拉取并解析 ----------------------------------------------------
    slug_stats: dict[str, dict] = {}
    all_edges: list[tuple[str, str]] = []        # roadmap 映射后边 (prereq, skill)
    unmapped_counter: Counter[str] = Counter()
    node_total = node_mapped = 0
    edge_type_filtered = 0
    fetched = failed = 0
    for slug in SLUGS:
        data = fetch_roadmap(slug)
        if data is None:
            failed += 1
            slug_stats[slug] = {"status": "failed"}
            continue
        fetched += 1
        labels, raw_edges, n_filtered = parse_roadmap(slug, data)
        edge_type_filtered += n_filtered
        mapped_edges = 0
        node_id = {}
        for lab in labels:
            sid = map_label(lab, lookup)
            node_id[lab] = sid
            node_total += 1
            if sid is None:
                unmapped_counter[lab] += 1
            else:
                node_mapped += 1
        for s_lab, t_lab in raw_edges:
            s_sid, t_sid = node_id.get(s_lab), node_id.get(t_lab)
            if s_sid and t_sid and s_sid != t_sid:
                all_edges.append((s_sid, t_sid))
                mapped_edges += 1
        n_nodes_mapped = sum(1 for v in node_id.values() if v)
        slug_stats[slug] = {
            "status": "ok", "nodes": len(labels),
            "nodes_mapped": n_nodes_mapped,
            "edges_raw": len(raw_edges), "edges_mapped": mapped_edges,
        }
        print(f">>> {slug:<20} nodes={len(labels):>3}/{n_nodes_mapped:>3} "
              f"edges_raw={len(raw_edges):>3} edges_mapped={mapped_edges:>3}")

    # ---- 3-4. 合并 ----------------------------------------------------------
    v2_skills = {s["skill_id"]: s for s in v2["skills"]}
    vocab_ids = {s["id"] for s in vocab["skills"]}

    edge_conf: dict[tuple[str, str], int] = {}   # (prereq, skill) -> confidence
    edge_source: dict[tuple[str, str], str] = {}
    for s in v2["skills"]:
        for p in s["prerequisites"]:
            edge_conf[(p, s["skill_id"])] = 2    # v2 高置信
            edge_source[(p, s["skill_id"])] = "v2"

    roadmap_edge_cnt = 0
    conflicts: dict[tuple[str, str], dict] = {}
    dup_roadmap = 0
    for a, b in all_edges:
        if (a, b) in edge_conf:                  # 已有（v2 或去重前 roadmap 边）
            dup_roadmap += 1
            continue
        if (b, a) in edge_conf:                  # 方向冲突, v2 优先
            conflicts.setdefault((a, b), {
                "roadmap_edge": [a, b], "v2_edge": [b, a],
                "resolution": "v2_wins",
            })
            continue
        edge_conf[(a, b)] = 1                    # roadmap 低置信
        edge_source[(a, b)] = "roadmap"
        roadmap_edge_cnt += 1

    # ---- 5. DAG 校验与解环 ---------------------------------------------------
    cycle_record: list[dict] = []
    n_edges_before = len(edge_conf)
    break_cycles(edge_conf, cycle_record)

    # ---- 6. 节点元数据 -------------------------------------------------------
    node_ids: set[str] = set()
    for a, b in edge_conf:
        node_ids.update((a, b))
    for sid in v2_skills:
        node_ids.add(sid)

    # roadmap 边（解环后）用于深度推断
    rm_edges = [(a, b) for (a, b), c in edge_conf.items()
                if edge_source[(a, b)] == "roadmap"]
    depth_levels = roadmap_depth_levels(node_ids, rm_edges)

    skills_out = []
    for sid in sorted(node_ids):
        if sid in v2_skills:
            old = v2_skills[sid]
            skills_out.append({
                "skill_id": sid,
                "skill_name": old["skill_name"],
                "category": old["category"],
                "level": old["level"],
                "difficulty": old["difficulty"],
                "hours_estimate": old["hours_estimate"],
                "hot": old["hot"],
                "prerequisites": sorted(p for (p, s) in edge_conf if s == sid),
                "aliases": old["aliases"],
            })
            continue
        # 新增节点: 词表 v2 中命中 roadmap 的技能
        vskill = next((s for s in vocab["skills"] if s["id"] == sid), None)
        name = vskill["name"] if vskill else sid
        category = vskill["category"] if vskill else "methods"
        hot = vskill["hot"] if vskill else False
        aliases = vskill["aliases"] if vskill else [sid]
        level = depth_levels.get(sid, 2.0)
        skills_out.append({
            "skill_id": sid,
            "skill_name": name,
            "category": category,
            "level": level,
            "difficulty": "intermediate",
            "hours_estimate": hours_by_level(level),
            "hot": hot,
            "prerequisites": sorted(p for (p, s) in edge_conf if s == sid),
            "aliases": aliases,
        })

    total_edges = sum(len(s["prerequisites"]) for s in skills_out)
    children: dict[str, list[str]] = defaultdict(list)
    for s in skills_out:
        for p in s["prerequisites"]:
            children[p].append(s["skill_id"])
    roots = [s["skill_id"] for s in skills_out if not s["prerequisites"]]
    leaves = [s["skill_id"] for s in skills_out if not children[s["skill_id"]]]

    out = {
        "version": "v3",
        "description": "技能先修图 v3：roadmap.sh 真实路线图 ∪ skill_prerequisite_v2 "
                       "（v2 边高置信优先）",
        "total": len(skills_out),
        "hot_count": sum(1 for s in skills_out if s["hot"]),
        "edge_count": total_edges,
        "skills": skills_out,
    }
    V3_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> 写出 {V3_JSON}  nodes={len(skills_out)} edges={total_edges}")

    # ---- 资源抽取 ------------------------------------------------------------
    resources = extract_resources()
    RESOURCES_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESOURCES_JSON.write_text(
        json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> 写出 {RESOURCES_JSON}  skill_keys="
          f"{resources['_meta']['skill_keys']} links={resources['_meta']['total_links']}")

    # ---- 抽查技能先修链 -------------------------------------------------------
    def prereq_chain(sid: str) -> dict:
        chain: dict[str, list[str]] = {}
        seen: set[str] = set()
        frontier = [sid]
        depth_of = {sid: 0}
        while frontier:
            u = frontier.pop()
            node = next((s for s in skills_out if s["skill_id"] == u), None)
            if node is None:
                continue
            direct = node["prerequisites"]
            if direct:
                chain[u] = direct
            for p in direct:
                if p not in seen:
                    seen.add(p)
                    depth_of[p] = depth_of[u] + 1
                    if depth_of[p] < 6:
                        frontier.append(p)
        return {"skill": sid, "category": next(
                    (s["category"] for s in skills_out if s["skill_id"] == sid), None),
                "levels": len(chain),
                "closure_size": len(seen), "chain": chain}

    spot = {sid: prereq_chain(sid) for sid in ("rag", "kubernetes", "react")}

    # ---- QC ------------------------------------------------------------------
    mapped_edge_total = sum(s["edges_mapped"] for s in slug_stats.values())
    raw_edge_total = sum(s["edges_raw"] for s in slug_stats.values())
    qc = {
        "version": "v3",
        "roadmaps": {
            "requested": len(SLUGS),
            "fetched": fetched,
            "failed": failed,
            "per_slug": slug_stats,
        },
        "parsing": {
            "skill_node_types": sorted(SKILL_NODE_TYPES),
            "node_total": node_total,
            "node_mapped_to_vocab": node_mapped,
            "node_mapping_rate": round(node_mapped / node_total, 4)
            if node_total else 0,
            "raw_edges_total": raw_edge_total,
            "edges_after_skill_type_filter": edge_type_filtered,
            "edges_mapped_to_vocab": mapped_edge_total,
            "edge_mapping_rate": round(mapped_edge_total / max(edge_type_filtered, 1), 4),
        },
        "alias_lookup": {"entries": len(lookup), "conflicts_skipped": alias_conflicts},
        "merge": {
            "v2_edges": sum(1 for src in edge_source.values() if src == "v2"),
            "roadmap_edges_added": roadmap_edge_cnt,
            "roadmap_duplicates_of_existing": dup_roadmap,
            "direction_conflicts": list(conflicts.values()),
            "conflict_count": len(conflicts),
            "edges_before_cycle_break": n_edges_before,
        },
        "dag": {
            "acyclic_after_break": True,
            "cycles_found": len(cycle_record) > 0,
            "cycles_broken": len(cycle_record),
            "cycle_break_records": cycle_record,
        },
        "final_graph": {
            "total_nodes": len(skills_out),
            "total_edges": total_edges,
            "root_count": len(roots),
            "leaf_count": len(leaves),
            "inherited_v2_nodes": len(v2_skills),
            "new_nodes_from_vocab": len(skills_out) - len(v2_skills),
            "roots": sorted(roots),
        },
        "spot_check_prereq_chains": spot,
        "top30_unmapped_labels": [
            {"label": lab, "count": c}
            for lab, c in unmapped_counter.most_common(30)
        ],
    }
    QC_JSON.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> 写出 {QC_JSON}")
    print(f"    合并后: nodes={len(skills_out)} edges={total_edges} "
          f"roots={len(roots)} leaves={len(leaves)}")
    print(f"    环处理: 解环 {len(cycle_record)} 次; 方向冲突 {len(conflicts)} 条（v2 优先）")
    for sid, ch in spot.items():
        print(f"    抽查 {sid}: 先修闭包 {ch['closure_size']} 个, 涉及 {ch['levels']} 层")


if __name__ == "__main__":
    main()
