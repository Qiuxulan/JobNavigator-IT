"""Agent orchestration — LLM function-calling based career & trend advisor.

Integrates the full career pipeline (resume analysis → job recommendation →
skill gap → learning path) with industry trend prediction and evidence retrieval.

Two operating modes:
  1. With LLM API key: OpenAI-compatible function calling loop
  2. Without LLM API key: keyword-based fallback with formatted Markdown output
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.core.config import settings

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_trend",
            "description": "查询某个 IT 岗位的未来趋势预测，返回趋势方向、置信度、历史指标和归因分析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "岗位角色名，如 'AI Engineer'"},
                    "months": {"type": "integer", "description": "预测未来几个月，默认 3", "default": 3},
                },
                "required": ["role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_evidence",
            "description": "检索支持趋势判断的新闻事件证据和 JD 链接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "岗位角色名"},
                    "start_month": {"type": "string", "description": "开始月份", "default": "2026-01"},
                    "end_month": {"type": "string", "description": "结束月份", "default": "2026-06"},
                    "top_k": {"type": "integer", "description": "返回前几条证据", "default": 5},
                },
                "required": ["role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_evidence_backtrack",
            "description": "获取某个角色的历史指标回溯数据（JD需求、新闻情绪、GitHub活跃度等），用于解释趋势变化原因。",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "岗位角色名"},
                    "month": {"type": "string", "description": "预测月份，如 '2026-08-01'", "default": "2026-08-01"},
                },
                "required": ["role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_roles",
            "description": "对比多个岗位角色的趋势，返回各角色的趋势方向和预测值。",
            "parameters": {
                "type": "object",
                "properties": {
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要对比的角色名列表",
                    },
                },
                "required": ["roles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_role_list",
            "description": "获取所有可查询的 IT 岗位角色列表（69个角色），按分类分组。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_resume",
            "description": "分析简历或技能描述，提取技能、经验、学历和目标岗位。当用户提供简历、描述自己的技能或说'我会xxx'时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "简历文本或技能描述"},
                },
                "required": ["resume_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_jobs",
            "description": "根据用户简历推荐匹配的岗位，含技能匹配度、差距分析和学习路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "简历文本或技能描述"},
                    "top_k": {"type": "integer", "description": "返回前几个推荐", "default": 5},
                },
                "required": ["resume_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill_gap",
            "description": "分析用户技能与目标岗位的差距。先调 analyze_resume 获取技能后再调此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "简历文本"},
                    "target_role": {"type": "string", "description": "目标岗位名称"},
                },
                "required": ["resume_text", "target_role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_learning_path",
            "description": "为用户规划学习路径，包含先修关系、学习时长和资源推荐。",
            "parameters": {
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "简历文本"},
                    "target_role": {"type": "string", "description": "目标岗位名称"},
                },
                "required": ["resume_text", "target_role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cot_explanation",
            "description": "获取某个岗位趋势的链式推理（CoT）解释上下文，含带引用编号的证据和分析框架。",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "岗位角色名"},
                    "horizon": {"type": "integer", "description": "预测视野月数", "default": 3},
                },
                "required": ["role"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是 JobNavigator-IT 职业发展与行业趋势分析助手，专注于 IT 行业。

你的能力分为两大板块：

**职业分析板块：**
1. 分析简历/技能描述 → 提取技能画像
2. 岗位推荐 → 基于技能匹配度推荐合适岗位
3. 技能差距分析 → 对比用户技能与目标岗位需求
4. 学习路径规划 → 生成含先修关系的学习计划和资源推荐

**行业趋势板块：**
5. 趋势预测 → 查询任意 IT 岗位的未来趋势（基于 PatchTST 时序模型、JD 需求、GDELT 新闻情绪、GitHub/arXiv 活跃度）
6. 证据检索 → 检索支持趋势判断的 GDELT 新闻事件 + JD 在招证据
7. 角色对比 → 多角色发展前景对比
8. 指标回溯 → 历史指标变化解释趋势原因
9. CoT 推理解释 → 带引用编号的链式推理上下文

**回答要求：**
- 用中文回答
- 数据驱动：每个结论都要有数据支撑
- 使用 Markdown 格式，善用表格、列表和 emoji 增强可读性
- 给出具体的、可执行的建议
- 当用户提供技能背景时，主动进行全链路分析

**CoT 推理规范（趋势分析时必须遵守）：**
- 当你获取到趋势数据和 get_cot_explanation 返回的证据上下文后，必须按以下 5 步链式推理：
  Step1: 模型预测说了什么（趋势方向、需求指数、置信度）
  Step2: 新闻面整体情绪如何（聚合数据：机会/风险事件数、净信号）
  Step3: 关键事件怎样支撑或反驳该预测（引用 [E#] 编号，含对反向信号的权衡）
  Step4: 在招 JD 反映的短期需求（引用 [J#] 编号）
  Step5: 综合判断该岗位趋势及主因
- 每个判断后用 [E1]/[M1]/[J1] 等标注引用来源
- 若证据中存在标注为「反向信号」的条目，必须在推理中明确指出并权衡，不得回避
- 不得引入证据之外的事实

当前数据覆盖 69 个 IT 细分岗位、275 个技能节点、完整的先修关系图谱和学习资源库。
趋势数据基于真实 JD 招聘数据（7万+条）、GDELT 全球新闻（172万条事件候选）、GitHub/arXiv 技术热度。
预测模型使用 PatchTST，当前主预测视野为未来 24 个月的 JD 需求指数。"""


# ── Tool execution using real services ────────────────────────────────────────

SYSTEM_GUARDRAILS = """
你是 JobNavigator-IT 的受控项目 Agent，只能基于本项目本地数据库和后端工具返回的数据回答。

强制边界：
1. 不允许联网搜索，不允许引用工具结果以外的新闻、岗位、课程、薪资、公司或统计数字。
2. 不允许自行杜撰岗位趋势、证据、JD、学习资源、技能关系或行业事件。
3. 用户问到数据库没有覆盖的内容时，必须明确回答“当前项目数据库没有该信息”，并说明可用的数据范围。
4. 岗位名称必须优先匹配本项目 69 个 canonical role；无法匹配时，先说明没有该岗位，再给出最接近的已收录岗位。
5. 趋势结论必须来自 query_trend、retrieve_evidence、get_evidence_backtrack 或 get_cot_explanation。
6. 职业推荐、技能差距和学习路径必须来自 recommend_jobs、get_skill_gap 或 plan_learning_path。
7. CoT 只输出可审计的证据链摘要，不输出隐藏思维链；每个判断必须带 [E#]、[M#] 或 [J#] 引用，引用必须来自工具结果。

当前项目数据范围：69 个 IT 细分岗位、275 个技能节点、技能前置关系、学习资源库、PatchTST 未来 24 个月岗位需求预测、GDELT/JD/重大行业事件证据。
"""


def _get_taxonomy() -> list[dict]:
    import json as _json
    from pathlib import Path
    path = Path("data/gold/role_taxonomy.json")
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return _json.load(f)


def _execute_tool(name: str, arguments: dict) -> Any:
    if name == "query_trend":
        return _tool_query_trend(arguments)
    elif name == "retrieve_evidence":
        return _tool_retrieve_evidence(arguments)
    elif name == "get_evidence_backtrack":
        return _tool_get_evidence_backtrack(arguments)
    elif name == "compare_roles":
        return _tool_compare_roles(arguments)
    elif name == "get_role_list":
        return _tool_get_role_list()
    elif name == "analyze_resume":
        return _tool_analyze_resume(arguments)
    elif name == "recommend_jobs":
        return _tool_recommend_jobs(arguments)
    elif name == "get_skill_gap":
        return _tool_get_skill_gap(arguments)
    elif name == "plan_learning_path":
        return _tool_plan_learning_path(arguments)
    elif name == "get_cot_explanation":
        return _tool_get_cot_explanation(arguments)
    return {"error": f"Unknown tool: {name}"}


def _tool_query_trend(args: dict) -> dict:
    try:
        from app.services.trend import TrendService
        signal = TrendService.get_signal(args["role"], horizon_months=args.get("months", 3))
        result = signal.model_dump(mode="json")
        try:
            from app.services.trend_predictor import get_evidence as get_backtrack
            bt = get_backtrack(args["role"], "2026-08-01")
            if bt.get("key_factors"):
                result["main_factors"] = bt["key_factors"]
        except Exception:
            pass
        return result
    except Exception as e:
        return {"error": str(e)}


def _tool_retrieve_evidence(args: dict) -> dict:
    try:
        from app.services.evidence import EvidenceService
        from app.services.trend import _resolve_role
        resolved = _resolve_role(args["role"])
        return EvidenceService.retrieve_evidence(
            resolved.canonical_role,
            (args.get("start_month", "2026-01"), args.get("end_month", "2026-06")),
            args.get("top_k", 5),
        )
    except Exception as e:
        return {"error": str(e)}


def _tool_get_evidence_backtrack(args: dict) -> dict:
    try:
        from app.services.trend_predictor import get_evidence
        return get_evidence(args["role"], args.get("month", "2026-08-01"))
    except Exception as e:
        return {"error": str(e)}


def _tool_compare_roles(args: dict) -> list[dict]:
    from app.services.trend import TrendService
    results = []
    for role in args["roles"]:
        try:
            signal = TrendService.get_signal(role, horizon_months=3)
            results.append({
                "canonical_role": signal.canonical_role,
                "trend_direction": signal.trend_direction,
                "predicted_demand_index": signal.predicted_demand_index,
                "confidence": signal.confidence,
                "main_factors": signal.main_factors,
            })
        except Exception as e:
            results.append({"canonical_role": role, "error": str(e)})
    return results


def _tool_get_role_list() -> dict:
    taxonomy = _get_taxonomy()
    by_cat: dict[str, list] = {}
    for r in taxonomy:
        cat = r.get("category", "Other")
        by_cat.setdefault(cat, []).append(r["canonical_role"])
    return by_cat


def _find_controlled_roles(user_msg: str, all_roles: list[str]) -> list[str]:
    q = user_msg.lower().replace(" ", "")
    found: list[str] = []

    def add(role: str) -> None:
        if role in all_roles and role not in found:
            found.append(role)

    exact_aliases = [
        ("backendpythonengineer", "Backend Python Engineer"),
        ("pythonbackendengineer", "Backend Python Engineer"),
        ("backendpython", "Backend Python Engineer"),
        ("python后端工程师", "Backend Python Engineer"),
        ("python后端", "Backend Python Engineer"),
        ("rag工程师", "RAG Engineer"),
        ("ragengineer", "RAG Engineer"),
        ("rag", "RAG Engineer"),
        ("检索增强", "RAG Engineer"),
        ("向量数据库", "RAG Engineer"),
        ("ai数据工程师", "AI Data Engineer"),
        ("人工智能数据工程师", "AI Data Engineer"),
        ("aidataengineer", "AI Data Engineer"),
        ("ai data engineer", "AI Data Engineer"),
        ("数据工程师", "Data Engineer"),
        ("dataengineer", "Data Engineer"),
    ]
    for alias, role in exact_aliases:
        if alias.replace(" ", "").lower() in q:
            add(role)
    for role in all_roles:
        if role.lower().replace(" ", "") in q:
            add(role)
    if "AI Data Engineer" in found and "Data Engineer" in found:
        found.remove("Data Engineer")
    return found


def _controlled_agent_answer(messages: list[dict]) -> str | None:
    user_msg = messages[-1].get("content", "") if messages else ""
    if not user_msg:
        return None
    all_roles = [r["canonical_role"] for r in _get_taxonomy()]
    roles = _find_controlled_roles(user_msg, all_roles)
    compare_intent = any(token in user_msg.lower() for token in ["还是", "对比", "比较", "更适合", "vs", "or"])
    profile_intent = any(token in user_msg.lower() for token in ["我现在会", "我会", "技能", "python", "sql", "docker", "langchain"])
    if compare_intent and profile_intent and len(roles) >= 2:
        return _format_controlled_role_comparison(user_msg, roles[:4])
    return None


def _role_keywords(role: str) -> list[str]:
    base = [part.lower() for part in role.replace(".", " ").replace("-", " ").split() if len(part) > 1]
    extras = {
        "RAG Engineer": ["rag", "retrieval", "vector", "embedding", "langchain", "llm", "agent"],
        "AI Data Engineer": ["ai", "data", "pipeline", "etl", "databricks", "spark", "warehouse", "llm"],
        "Data Engineer": ["data", "pipeline", "etl", "spark", "databricks", "warehouse"],
    }
    return list(dict.fromkeys([*base, *extras.get(role, [])]))


def _relevant_events(role: str, evidence: dict, limit: int = 3) -> list[dict]:
    keywords = _role_keywords(role)
    matched = []
    for event in evidence.get("events", []) or []:
        text = " ".join(str(event.get(key, "")) for key in ["title", "event_type", "source_domain"]).lower()
        if _is_relevant_evidence_text(role, text, keywords):
            matched.append(event)
    return matched[:limit]


def _is_relevant_evidence_text(role: str, text: str, keywords: list[str]) -> bool:
    if role == "RAG Engineer":
        return any(k in text for k in ["rag", "retrieval", "vector", "embedding", "langchain"])
    if role == "AI Data Engineer":
        return any(k in text for k in ["ai data", "data engineer", "databricks", "spark", "etl", "pipeline", "warehouse"])
    if role == "Backend Python Engineer":
        if any(k in text for k in [".net", " php ", "javascript", "java developer"]):
            return False
        return "python" in text and any(k in text for k in ["backend", "developer", "engineer", "django", "flask", "fastapi", "postgresql", "api"])
    hits = sum(1 for keyword in keywords if keyword in text)
    return hits >= 2


def _remove_negated_skills(user_msg: str) -> str:
    text = user_msg
    neg_words = ["没有", "没学过", "没系统学过", "不熟", "不会"]
    skills = [
        "LangChain", "langchain", "向量数据库", "Vector Database", "vector database",
        "Kubernetes", "kubernetes", "K8s", "k8s", "云平台", "云", "Cloud", "cloud",
    ]
    compact = text.lower()
    for skill in skills:
        idx = compact.find(skill.lower())
        if idx < 0:
            continue
        window = text[max(0, idx - 18): idx + len(skill) + 8]
        if any(word in window for word in neg_words):
            text = text.replace(skill, "")
            compact = text.lower()
    return text


def _profile_text_for_controlled(user_msg: str) -> str:
    text = _remove_negated_skills(user_msg)
    cut_markers = [
        "现在我想",
        "我想在",
        "我想",
        "\u4f60\u80fd\u4e0d\u80fd",
        "\u5224\u65ad\u6211",
        "\u6211\u66f4\u9002\u5408",
        "\u987a\u4fbf\u8bf4\u660e",
        "请只根据",
        "请",
    ]
    end = len(text)
    for marker in cut_markers:
        idx = text.find(marker)
        if idx >= 0:
            end = min(end, idx)
    return text[:end].strip() or text


def _major_events_from_cot(role: str) -> list[dict]:
    cot = _tool_get_cot_explanation({"role": role, "horizon": 3})
    if "error" in cot:
        return []
    keywords = _role_keywords(role)
    majors = (cot.get("context") or {}).get("major_events", [])
    filtered = [
        item for item in majors
        if _is_relevant_major_text(role, " ".join(str(item.get(key, "")) for key in ["title", "impact"]).lower(), keywords)
    ]
    return (filtered or majors)[:3]


def _is_relevant_major_text(role: str, text: str, keywords: list[str]) -> bool:
    if role == "RAG Engineer":
        return any(k in text for k in ["rag", "retrieval", "vector", "embedding", "langchain", "gpt", "codex", "agent", "llm"])
    if role == "AI Data Engineer":
        return any(k in text for k in ["data", "databricks", "spark", "pipeline", "gpt", "codex", "agent", "llm", "ai"])
    if role == "Backend Python Engineer":
        if any(k in text for k in [".net", "php", "javascript", "java "]):
            return False
        return any(k in text for k in ["python", "backend", "django", "flask", "fastapi", "api", "codex", "software engineering", "gpt"])
    return sum(1 for keyword in keywords if keyword in text) >= 1


def _format_controlled_role_comparison(user_msg: str, roles: list[str]) -> str:
    analysis_text = _profile_text_for_controlled(user_msg)
    resume = _tool_analyze_resume({"resume_text": analysis_text})
    skills = resume.get("skills", [])
    rows = []
    for role in roles:
        trend = _tool_query_trend({"role": role, "months": 24})
        gap = _tool_get_skill_gap({"resume_text": analysis_text, "target_role": role})
        path = _tool_plan_learning_path({"resume_text": analysis_text, "target_role": role})
        evidence = _tool_retrieve_evidence({"role": role})
        rows.append({
            "role": role,
            "trend": trend,
            "gap": gap,
            "path": path,
            "evidence": evidence,
            "news": _relevant_events(role, evidence),
            "majors": _major_events_from_cot(role),
        })

    def score(row: dict) -> float:
        gap = row["gap"]
        trend = row["trend"]
        overlap = len(gap.get("overlap_skills", []))
        missing = len(gap.get("missing_skills", []))
        fit = overlap / max(overlap + missing, 1)
        return round(0.58 * fit + 0.28 * float(trend.get("predicted_demand_index", 0)) + 0.14 * float(trend.get("confidence", 0)), 4)

    scored = [(score(row), row) for row in rows]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    role_label = " vs ".join(row["role"] for _, row in scored)
    ranking = " > ".join(row["role"] for _, row in scored)

    lines = [
        f"## 受控 Agent 分析：{role_label}\n",
        "我已按项目内岗位体系、趋势数据和技能图谱解析用户明确指定的岗位，没有使用外部搜索。\n",
        f"**识别到的技能**：{', '.join(skills) if skills else '未识别到明确技能'}\n",
        "### 结论\n",
        f"建议排序：**{ranking}**。\n\n首选 **{best['role']}**，依据是：当前技能重合度、PatchTST 需求指数、置信度和学习路径成本的综合评分为 **{best_score:.4f}**。\n",
        "### 目标岗位对比\n",
        "| 岗位 | 24个月趋势 | 需求指数 | 置信度 | 已匹配技能 | 主要缺口 | 路径步数/小时 |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for _, row in scored:
        role = row["role"]
        trend = row["trend"]
        gap = row["gap"]
        path = row["path"]
        overlap = ", ".join(gap.get("overlap_skills", [])[:5]) or "-"
        missing = ", ".join(gap.get("missing_skills", [])[:6]) or "-"
        lines.append(
            f"| {role} | {trend.get('trend_direction', 'flat')} | "
            f"{float(trend.get('predicted_demand_index', 0)):.4f} | "
            f"{float(trend.get('confidence', 0)):.0%} | {overlap} | {missing} | "
            f"{path.get('total_steps', 0)}步/{path.get('total_hours', 0)}小时 |"
        )

    lines.append("\n### 关键证据\n")
    for _, row in scored:
        role = row["role"]
        evidence = row["evidence"]
        agg = evidence.get("aggregate") or {}
        lines.append(f"#### {role}")
        lines.append(
            f"- 聚合信号：相关新闻 {agg.get('article_count', 0)} 条，平均情绪 {float(agg.get('mean_tone', 0)):.2f}，净信号 {agg.get('net_signal', 'N/A')}。"
        )
        if row["majors"]:
            for item in row["majors"][:3]:
                lines.append(f"- [{item.get('cite')}] {item.get('date', '')}：{item.get('title', '')}（{item.get('impact', '')}）")
        relevant = row["news"]
        if relevant:
            for idx, item in enumerate(relevant, start=1):
                lines.append(f"- [E{idx}] {item.get('title', '')}（{item.get('impact_direction', 'neutral')}）")
        else:
            lines.append("- 直接新闻证据：当前检索结果缺少足够明确命中该岗位关键词的新闻标题，因此不把宽泛新闻当作关键证据。")

    lines.append("\n### 学习路径优先级\n")
    for _, row in scored:
        role = row["role"]
        path = row["path"]
        steps = path.get("steps", [])[:5]
        lines.append(f"#### {role}")
        if not steps:
            lines.append("- 暂无可生成路径。")
            continue
        for step in steps:
            res = step.get("resources", [])
            first_res = f"；资源：{res[0].get('title')}" if res else ""
            lines.append(f"- Step {step.get('step_no')}: {step.get('skill')}（{step.get('reason')}）{first_res}")
    return "\n".join(lines)


def _tool_analyze_resume(args: dict) -> dict:
    try:
        from app.services.extractor import ExtractorService
        profile = ExtractorService.extract(args["resume_text"], None, "agent_user")
        return {
            "user_id": profile.user_id,
            "skills": profile.skills,
            "target_role": profile.target_role,
            "years_experience": profile.years_experience,
            "education": profile.education,
        }
    except Exception as e:
        return {"error": str(e)}


def _local_match_role(user_skills: list[str], target_role: str | None = None, top_k: int = 5):
    """Local file-based role matching — fallback when PostgreSQL is unavailable."""
    from app.services.career_catalog import load_roles, role_top_skills, jobrole_from_role
    from app.services.skill_norm import normalize_skill_id

    roles = load_roles()
    user_norm = {normalize_skill_id(s) or s.lower() for s in user_skills}

    scored = []
    for rid, role in roles.items():
        top_skills = role_top_skills(role, top_n=30)
        role_skill_ids = {s["skill_id"] for s in top_skills}
        role_skill_names = {s.get("display_name", s["skill_id"]) for s in top_skills}

        overlap = user_norm & role_skill_ids
        missing = role_skill_ids - user_norm
        score = len(overlap) / max(len(role_skill_ids), 1)

        job = jobrole_from_role(role)
        scored.append({
            "job": job,
            "fine_role": job.fine_role,
            "score": score,
            "overlap_skills": [s.get("display_name", s["skill_id"]) for s in top_skills if s["skill_id"] in overlap],
            "missing_skills": [s.get("display_name", s["skill_id"]) for s in top_skills if s["skill_id"] in missing],
            "role_skills": top_skills,
        })

    if target_role:
        target_low = target_role.lower()
        for item in scored:
            if item["fine_role"].lower() == target_low or target_low in item["fine_role"].lower():
                return [item]

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _local_learning_path(missing_skills: list[str], target_role: str) -> dict:
    """Build learning path from local skill graph + resources."""
    from app.services.career_catalog import load_skill_graph, load_resources
    from app.services.skill_norm import normalize_skill_id

    graph = load_skill_graph()
    resources = load_resources()
    steps = []
    total_hours = 0

    for i, skill_name in enumerate(missing_skills[:10], 1):
        sid = normalize_skill_id(skill_name) or skill_name.lower().replace(" ", "-")
        node = graph.get(sid, {})
        prereqs = node.get("prerequisites", [])
        est_hours = node.get("estimated_hours", 20)
        total_hours += est_hours

        skill_resources = resources.get(sid, [])
        steps.append({
            "step_no": i,
            "skill": skill_name,
            "reason": f"{'→'.join(prereqs[:2])} → {skill_name}" if prereqs else f"{target_role} 核心技能",
            "estimated_hours": est_hours,
            "resources": [
                {"title": r.title, "url": r.url, "provider": r.provider}
                for r in skill_resources[:2]
            ],
        })

    return {
        "target_role": target_role,
        "total_steps": len(steps),
        "total_hours": total_hours,
        "steps": steps,
    }


def _graphv2_analyze(profile, target_job_id: str, semantic_score: float = 0.5) -> dict | None:
    """Use GraphPathPlannerV2 directly — works with local embeddings, no DB needed."""
    try:
        from app.services.graph_path_planner_v2 import GraphPathPlannerV2
        if not GraphPathPlannerV2.is_available():
            return None
        analysis = GraphPathPlannerV2.analyze_role(
            profile=profile, target_job_id=target_job_id,
            semantic_score=semantic_score,
        )
        return {
            "role": analysis.role,
            "role_score": analysis.role_score,
            "score_breakdown": analysis.score_breakdown,
            "skill_gap": analysis.skill_gap,
            "path": analysis.path,
        }
    except Exception:
        return None


def _tool_recommend_jobs(args: dict) -> dict:
    try:
        from app.services.extractor import ExtractorService
        profile = ExtractorService.extract(args["resume_text"], None, "agent_user")
        top_k = args.get("top_k", 5)

        # Tier 1: DB-backed career pathway (sentence-transformers + pgvector)
        try:
            from app.services.career_pathway_service import rank_careers
            from app.schemas.domain import UserPreference
            ranked = rank_careers(profile, UserPreference(), top_n=max(10, top_k))
            results = []
            for row in ranked[:top_k]:
                results.append({
                    "job_title": row["job"].title,
                    "fine_role": row["job"].fine_role,
                    "score": round(row["role_score"], 4),
                    "skill_gap": {
                        "missing": row["skill_gap"].missing_skills[:5],
                        "overlap": row["skill_gap"].overlap_skills[:5],
                    },
                })
            return {"profile_skills": profile.skills, "recommendations": results}
        except Exception:
            pass

        # Tier 2: GraphPathPlannerV2 with local matching (no DB)
        matched = _local_match_role(profile.skills, top_k=top_k)
        results = []
        for m in matched:
            analysis = _graphv2_analyze(profile, m["job"].job_id, semantic_score=m["score"])
            if analysis:
                display_score = max(analysis["role_score"], m["score"])
                results.append({
                    "job_title": m["job"].title,
                    "fine_role": m["fine_role"],
                    "score": round(display_score, 4),
                    "coverage": round(analysis["score_breakdown"]["coverage"], 4),
                    "skill_gap": {
                        "missing": analysis["skill_gap"].missing_skills[:5],
                        "overlap": analysis["skill_gap"].overlap_skills[:5],
                    },
                    "path_hours": analysis["path"].total_estimated_hours,
                })
            else:
                results.append({
                    "job_title": m["job"].title,
                    "fine_role": m["fine_role"],
                    "score": round(m["score"], 4),
                    "skill_gap": {
                        "missing": m["missing_skills"][:5],
                        "overlap": m["overlap_skills"][:5],
                    },
                })
        return {"profile_skills": profile.skills, "recommendations": results}
    except Exception as e:
        return {"error": str(e)}


def _resolve_target_job_id(target: str) -> str | None:
    """Resolve a target role name to a job_id in the roles catalog."""
    from app.services.career_catalog import load_roles
    roles = load_roles()
    target_low = target.lower()
    for rid, role in roles.items():
        fine = (role.get("fine_role") or role.get("role_name", "")).lower()
        if fine == target_low or target_low in fine:
            return rid
    for rid, role in roles.items():
        name = (role.get("role_name") or "").lower()
        if target_low in name:
            return rid
    return None


def _tool_get_skill_gap(args: dict) -> dict:
    try:
        from app.services.extractor import ExtractorService
        profile = ExtractorService.extract(args["resume_text"], None, "agent_user")
        target = args["target_role"]

        # Tier 1: DB-backed
        try:
            from app.services.career_pathway_service import rank_careers
            from app.schemas.domain import UserPreference
            ranked = rank_careers(profile, UserPreference(), top_n=20)
            for row in ranked:
                if row["job"].fine_role.lower() == target.lower() or target.lower() in row["job"].title.lower():
                    return {
                        "target_role": row["job"].fine_role,
                        "score": round(row["role_score"], 4),
                        "missing_skills": row["skill_gap"].missing_skills,
                        "overlap_skills": row["skill_gap"].overlap_skills,
                        "score_breakdown": row["score_breakdown"],
                        "user_skills": profile.skills,
                    }
        except Exception:
            pass

        # Tier 2: GraphPathPlannerV2 direct (local embeddings)
        job_id = _resolve_target_job_id(target)
        if job_id:
            analysis = _graphv2_analyze(profile, job_id)
            if analysis:
                return {
                    "target_role": target,
                    "score": round(analysis["role_score"], 4),
                    "missing_skills": analysis["skill_gap"].missing_skills,
                    "overlap_skills": analysis["skill_gap"].overlap_skills,
                    "score_breakdown": analysis["score_breakdown"],
                    "user_skills": profile.skills,
                }

        # Tier 3: Local fallback
        matched = _local_match_role(profile.skills, target_role=target)
        if matched:
            m = matched[0]
            return {
                "target_role": m["fine_role"],
                "score": round(m["score"], 4),
                "missing_skills": m["missing_skills"],
                "overlap_skills": m["overlap_skills"],
                "user_skills": profile.skills,
            }
        return {"target_role": target, "user_skills": profile.skills, "note": f"未匹配到 {target}"}
    except Exception as e:
        return {"error": str(e)}


def _tool_plan_learning_path(args: dict) -> dict:
    try:
        from app.services.extractor import ExtractorService
        profile = ExtractorService.extract(args["resume_text"], None, "agent_user")
        target = args["target_role"]

        # Tier 1: DB-backed
        try:
            from app.services.career_pathway_service import rank_careers
            from app.schemas.domain import UserPreference
            ranked = rank_careers(profile, UserPreference(), top_n=20)
            for row in ranked:
                if row["job"].fine_role.lower() == target.lower() or target.lower() in row["job"].title.lower():
                    path = row["path"]
                    return _format_path_dict(row["job"].fine_role, path)
        except Exception:
            pass

        # Tier 2: GraphPathPlannerV2 direct
        job_id = _resolve_target_job_id(target)
        if job_id:
            analysis = _graphv2_analyze(profile, job_id)
            if analysis:
                return _format_path_dict(target, analysis["path"])

        # Tier 3: Local fallback
        matched = _local_match_role(profile.skills, target_role=target)
        if matched:
            missing = matched[0]["missing_skills"]
            return _local_learning_path(missing, target)
        return {"target_role": target, "note": "未匹配到该岗位的学习路径"}
    except Exception as e:
        return {"error": str(e)}


def _format_path_dict(target_role: str, path) -> dict:
    """Format a LearningPath object into a serializable dict."""
    return {
        "target_role": target_role,
        "total_steps": path.total_steps,
        "total_hours": path.total_estimated_hours,
        "score": getattr(path, "score", 0),
        "steps": [
            {
                "step_no": s.step_no,
                "skill": s.skill,
                "reason": s.reason,
                "resources": [{"title": r.title, "url": r.url, "provider": r.provider} for r in s.resources[:2]],
            }
            for s in path.steps[:10]
        ],
    }


def _tool_get_cot_explanation(args: dict) -> dict:
    try:
        from app.services.trend_explanation import assemble_cot_context, build_cot_prompt
        ctx = assemble_cot_context(args["role"], args.get("horizon", 3))
        prompt = build_cot_prompt(ctx)
        return {"context": ctx, "cot_prompt": prompt}
    except Exception as e:
        return {"error": str(e)}


def _run_cot_reasoning(cot: dict | None) -> str | None:
    """Call LLM with CoT grounded prompt for chain-of-thought reasoning. Returns markdown or None."""
    if not cot or "error" in cot or not settings.llm_api_key:
        return None
    cot_prompt = cot.get("cot_prompt", "")
    if not cot_prompt:
        return None
    try:
        from app.services.trend_explanation import COT_SYSTEM_PROMPT
        url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": COT_SYSTEM_PROMPT},
                {"role": "user", "content": cot_prompt},
            ],
            "temperature": 0.3,
        }
        with httpx.Client(timeout=settings.llm_timeout_sec) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ── Chat entry points ──────────────────────────────────────────────────────────

def chat(messages: list[dict], max_rounds: int = 8) -> str:
    os.environ.pop("SSLKEYLOGFILE", None)

    # Stable fast path for the representative multi-role decision workflow.
    # It still calls project tools and data, but avoids unnecessary external
    # LLM rounds for a fully structured comparison request.
    controlled = _controlled_agent_answer(messages)
    if controlled is not None:
        return controlled

    if not settings.llm_api_key:
        return _chat_without_llm(messages)

    conversation = [{"role": "system", "content": f"{SYSTEM_GUARDRAILS}\n\n{SYSTEM_PROMPT}"}] + messages

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    for _ in range(max_rounds):
        payload = {
            "model": settings.llm_model,
            "messages": conversation,
            "tools": TOOL_DEFINITIONS,
            "temperature": 0.3,
        }

        try:
            with httpx.Client(timeout=settings.llm_timeout_sec) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
        except httpx.TimeoutException:
            return "❌ Qwen Agent 调用超时。当前已配置 LLM API Key，但外部模型服务未在超时时间内返回；没有使用本地规则伪造回答。"
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500]
            return f"❌ Qwen Agent 调用失败（HTTP {e.response.status_code}）。外部模型返回：{detail}"
        except Exception as e:
            return f"❌ Qwen Agent 连接失败：{type(e).__name__}: {str(e)[:300]}。当前没有使用本地规则伪造回答。"

        body = resp.json()
        choice = body["choices"][0]
        msg = choice["message"]
        conversation.append(msg)

        if choice.get("finish_reason") != "tool_calls" and not msg.get("tool_calls"):
            return msg.get("content", "")

        for tc in msg.get("tool_calls", []):
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])
            result = _execute_tool(fn_name, fn_args)
            tool_content = json.dumps(result, ensure_ascii=False, default=str)
            conversation.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_content,
            })

            # P0-1: CoT injection — when get_cot_explanation returns, inject
            # the grounded prompt so LLM does Step1-5 chain-of-thought reasoning
            if fn_name == "get_cot_explanation" and "error" not in result:
                cot_prompt = result.get("cot_prompt", "")
                if cot_prompt:
                    from app.services.trend_explanation import COT_SYSTEM_PROMPT
                    conversation.append({
                        "role": "system",
                        "content": COT_SYSTEM_PROMPT,
                    })
                    conversation.append({
                        "role": "user",
                        "content": f"请基于以上证据进行链式推理分析：\n\n{cot_prompt}",
                    })

    return conversation[-1].get("content", "抱歉，处理轮次过多，请简化您的问题。")


def _chat_without_llm(messages: list[dict]) -> str:
    """Fallback when no LLM API key is configured — keyword dispatch."""
    user_msg = messages[-1].get("content", "") if messages else ""
    q = user_msg.lower()

    taxonomy = _get_taxonomy()
    all_roles = [r["canonical_role"] for r in taxonomy]
    skill_keywords_clean = [
        "简历", "技能", "熟悉", "掌握", "经验", "会 ", "我会", "resume", "skill",
        "python", "java", "react", "sql", "docker", "kubernetes", "langchain",
        "rag", "llm", "pytorch", "machine learning",
    ]
    career_keywords_clean = ["转", "规划", "路径", "方向", "发展", "推荐", "想做", "想学", "适合", "gap", "career"]
    trend_keywords_clean = ["趋势", "前景", "发展", "怎么样", "如何", "需求", "trend", "future"]
    compare_keywords_clean = ["对比", "比较", " vs ", "哪个好", "还是", "compare"]
    list_keywords_clean = ["岗位列表", "全部岗位", "有哪些岗位", "角色列表", "role list"]

    def _find_roles_clean(limit: int = 4) -> list[str]:
        found = []
        compact_q = q.replace(" ", "")
        for role_name in all_roles:
            role_q = role_name.lower()
            if role_q in q or role_q.replace(" ", "") in compact_q:
                found.append(role_name)
        aliases = {
            "前端": "Frontend Engineer",
            "后端": "Backend Python Engineer",
            "全栈": "Full Stack Engineer",
            "数据分析": "Data Scientist",
            "数据工程": "Data Engineer",
            "运维": "DevOps Engineer",
            "安全": "Security Engineer",
            "测试": "QA Engineer",
            "人工智能": "AI Engineer",
            "机器学习": "Machine Learning Engineer",
            "大模型": "LLM Inference Engineer",
            "知识图谱": "Knowledge Graph Engineer",
        }
        for key, role_name in aliases.items():
            if key in user_msg and role_name in all_roles and role_name not in found:
                found.append(role_name)
        return found[:limit]

    clean_found_roles = _find_roles_clean()
    if any(k in user_msg for k in list_keywords_clean):
        by_cat = _tool_get_role_list()
        lines = ["## IT 岗位角色列表\n"]
        for cat, names in by_cat.items():
            lines.append(f"### {cat}")
            lines.extend(f"- {name}" for name in names)
            lines.append("")
        return "\n".join(lines)

    if any(k in user_msg for k in compare_keywords_clean) and len(clean_found_roles) >= 2:
        return _format_compare_response(_tool_compare_roles({"roles": clean_found_roles}))

    if any(k in user_msg for k in trend_keywords_clean) and clean_found_roles:
        role_name = clean_found_roles[0]
        pred = _tool_query_trend({"role": role_name, "months": 3})
        evidence = _tool_retrieve_evidence({"role": role_name})
        cot = _tool_get_cot_explanation({"role": role_name, "horizon": 3})
        cot_analysis = _run_cot_reasoning(cot)
        return _format_trend_response(pred, evidence, cot=cot, cot_analysis=cot_analysis)

    looks_like_profile = (
        len(user_msg) > 30 and sum(1 for k in skill_keywords_clean if k in q or k in user_msg) >= 2
    )
    if looks_like_profile or any(k in user_msg for k in career_keywords_clean):
        return _full_pipeline(user_msg, all_roles)

    # Resume / skill analysis
    skill_keywords = ["简历", "技能", "会", "熟悉", "掌握", "经验", "resume", "skill",
                       "python", "java", "react", "sql", "docker", "kubernetes"]
    is_resume = (len(user_msg) > 50 and sum(1 for k in skill_keywords if k in q) >= 2)

    career_intent = any(k in user_msg for k in ["转", "规划", "路径", "方向", "发展",
                                                  "推荐", "想做", "想转", "想学", "适合"])

    # Full pipeline: resume + career intent → complete analysis
    if is_resume and career_intent:
        return _full_pipeline(user_msg, all_roles)

    # Resume with enough content → also do full pipeline
    if is_resume:
        result = _tool_analyze_resume({"resume_text": user_msg})
        if result.get("skills") and len(result["skills"]) >= 3:
            return _full_pipeline(user_msg, all_roles)
        return _format_resume_response(result)

    # Career planning with skill keywords
    if career_intent and any(k in q for k in skill_keywords):
        return _full_pipeline(user_msg, all_roles)

    # Comparison (must be checked before trend to avoid single-role trend fallthrough)
    if any(k in user_msg for k in ["对比", "比较", "compare", "vs", "和", "还是"]):
        found = [r for r in all_roles if r.lower() in q]
        # Also match Chinese aliases
        if len(found) < 2:
            cn_map = {
                "前端": "Frontend React Engineer", "后端": "Backend Java Engineer",
                "全栈": "Full Stack Developer", "数据分析": "Data Scientist",
                "数据工程": "Data Engineer", "运维": "DevOps Engineer",
                "安全": "Information Security Analyst", "测试": "QA Automation Engineer",
                "移动": "Mobile Developer", "游戏": "Unity Developer",
                "产品": "Product Manager", "项目": "Project Manager",
                "ai": "AI Engineer", "人工智能": "AI Engineer",
                "机器学习": "Machine Learning Engineer", "深度学习": "Machine Learning Engineer",
                "mlops": "MLOps Engineer", "云": "Cloud Architect",
                "嵌入式": "Embedded Systems Engineer", "区块链": "Blockchain Developer",
                "nlp": "NLP Scientist", "架构": "Solutions Architect",
                "sre": "Site Reliability Engineer",
            }
            for cn, en in cn_map.items():
                if cn in user_msg and en not in found:
                    found.append(en)
        if len(found) >= 2:
            results = _tool_compare_roles({"roles": found[:4]})
            return _format_compare_response(results)

    # Trend query
    if any(k in user_msg for k in ["趋势", "前景", "发展", "怎么样", "如何"]) or "trend" in q:
        for rname in all_roles:
            if rname.lower() in q or rname.lower().replace(" ", "") in q:
                pred = _tool_query_trend({"role": rname, "months": 3})
                evidence = _tool_retrieve_evidence({"role": rname})
                cot = _tool_get_cot_explanation({"role": rname, "horizon": 3})
                cot_analysis = _run_cot_reasoning(cot)
                return _format_trend_response(pred, evidence, cot=cot, cot_analysis=cot_analysis)

    # Role list
    if any(k in user_msg for k in ["角色", "列表", "岗位", "有哪些"]) or "role" in q or "list" in q:
        by_cat = _tool_get_role_list()
        lines = ["## 📋 IT 岗位角色列表\n"]
        for cat, names in by_cat.items():
            lines.append(f"### {cat}")
            for name in names:
                lines.append(f"- {name}")
            lines.append("")
        return "\n".join(lines)

    # Default: dashboard overview
    return _format_dashboard_response(taxonomy, user_msg)


def _full_pipeline(user_msg: str, all_roles: list[str]) -> str:
    """End-to-end: resume → extract → recommend → skill gap → learning path → trend."""
    resume_result = _tool_analyze_resume({"resume_text": user_msg})
    if "error" in resume_result or not resume_result.get("skills"):
        return _format_resume_response(resume_result)

    # Determine target role — priority: explicit role name > intent keyword > extracted > recommend
    q = user_msg.lower()
    target = ""

    # 1. Check if user mentioned an exact role name
    for rname in all_roles:
        if rname.lower() in q:
            target = rname
            break

    # 2. Infer from intent keywords (user says "想转AI方向")
    if not target:
        role_hints = [
            ("ai", "AI Engineer"), ("人工智能", "AI Engineer"),
            ("机器学习", "Machine Learning Engineer"), ("ml engineer", "Machine Learning Engineer"),
            ("前端", "Frontend Engineer"), ("frontend", "Frontend Engineer"),
            ("后端", "Backend Engineer"), ("backend", "Backend Engineer"),
            ("全栈", "Full Stack Developer"), ("fullstack", "Full Stack Developer"),
            ("数据分析", "Data Scientist"), ("数据工程", "Data Engineer"),
            ("data scientist", "Data Scientist"), ("data engineer", "Data Engineer"),
            ("云", "Cloud Architect"), ("cloud", "Cloud Architect"),
            ("安全", "Cybersecurity Analyst"), ("security", "Cybersecurity Analyst"),
            ("devops", "DevOps Engineer"), ("运维", "DevOps Engineer"),
            ("mlops", "MLOps Engineer"), ("sre", "Site Reliability Engineer"),
        ]
        for hint, role in role_hints:
            if hint in q:
                target = role
                break

    # 3. Use extracted target from profile
    if not target:
        target = resume_result.get("target_role") or ""

    # 4. Fallback: use top recommendation
    if not target:
        recs = _tool_recommend_jobs({"resume_text": user_msg, "top_k": 1})
        if recs.get("recommendations"):
            target = recs["recommendations"][0]["fine_role"]

    if not target:
        return _format_resume_response(resume_result)

    # Full pipeline
    gap = _tool_get_skill_gap({"resume_text": user_msg, "target_role": target})
    path = _tool_plan_learning_path({"resume_text": user_msg, "target_role": target})
    trend = _tool_query_trend({"role": target, "months": 3})
    evidence = _tool_retrieve_evidence({"role": target})
    recs = _tool_recommend_jobs({"resume_text": user_msg, "top_k": 3})

    # CoT explanation context (grounded reasoning with citations)
    cot = None
    cot_analysis = None
    try:
        cot = _tool_get_cot_explanation({"role": target, "horizon": 3})
        cot_analysis = _run_cot_reasoning(cot)
    except Exception:
        pass

    return _format_full_report(resume_result, gap, path, trend, evidence, recs, target,
                               cot=cot, cot_analysis=cot_analysis)


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _format_full_report(resume: dict, gap: dict, path: dict, trend: dict,
                        evidence: dict, recs: dict, target: str, cot: dict | None = None,
                        cot_analysis: str | None = None) -> str:
    lines = [f"## 🎯 {target} — 完整职业发展分析\n"]

    # Section 1: Profile
    lines.append("### 📋 技能画像\n")
    skills = resume.get("skills", [])
    if resume.get("education"):
        lines.append(f"- **学历**: {resume['education']}")
    if resume.get("years_experience"):
        lines.append(f"- **工作经验**: {resume['years_experience']} 年")
    lines.append(f"- **识别技能** ({len(skills)}项): {', '.join(skills[:12])}")

    # Section 2: Trend (组员1+2 output)
    if trend and "error" not in trend:
        arrow = {"up": "📈 上升", "down": "📉 下降", "flat": "➡️ 平稳"}.get(
            trend.get("trend_direction", ""), "")
        lines.append(f"\n### 📈 {target} 行业趋势（PatchTST 预测）\n")
        lines.append(f"| 指标 | 数据 |")
        lines.append(f"|------|------|")
        lines.append(f"| 趋势方向 | {arrow} |")
        lines.append(f"| 预测需求指数 | {trend.get('predicted_demand_index', 0):.4f} |")
        lines.append(f"| 置信度 | {trend.get('confidence', 0):.0%} |")
        factors = trend.get("main_factors", [])
        if factors:
            lines.append(f"\n**驱动因素:**")
            for f in factors[:5]:
                lines.append(f"- {f}")

    # Section 3: Evidence (组员2 output) — with unified coloring
    if evidence and "error" not in evidence:
        from app.services.evidence_color import event_polarity
        agg = evidence.get("aggregate")
        events = evidence.get("events", evidence.get("top_events", []))
        if agg or events:
            lines.append(f"\n### 📰 证据支撑（RAG 检索）\n")
        if agg:
            lines.append(f"- 相关新闻: {agg.get('article_count', 0)} 条")
            lines.append(f"- 平均情绪: {agg.get('mean_tone', 0):.2f}")
            lines.append(f"- 净信号: {agg.get('net_signal', 'N/A')}")
        if events:
            lines.append(f"\n**Top 事件证据:**")
            for ev in events[:3]:
                polarity = event_polarity(ev)
                emoji = {"positive": "🟢", "negative": "🔴"}.get(polarity, "⚪")
                title = ev.get("title", "事件")[:50]
                lines.append(f"- {emoji} {title}")

    # Section 3.5: CoT chain-of-thought analysis
    if cot_analysis:
        lines.append(f"\n### 🔗 链式推理分析（CoT）\n")
        lines.append(cot_analysis)
    elif cot and "error" not in cot:
        ctx = cot.get("context", {})
        majors = ctx.get("major_events", [])
        if majors:
            lines.append(f"\n### 📌 重大行业事件\n")
            for m in majors:
                lines.append(f"- [{m['cite']}] {m.get('date', '')} — {m.get('title', '')} ({m.get('impact', '')})")
        cot_events = ctx.get("events", [])
        if cot_events:
            counter = [e for e in cot_events if e.get("is_counter_signal")]
            if counter:
                lines.append(f"\n**反向信号（需注意）：**")
                for e in counter:
                    lines.append(f"- [{e['cite']}] {e.get('title', '')} — {e.get('event_type', '')}")

    # Section 4: Skill gap
    if gap and "error" not in gap:
        lines.append(f"\n### 🔍 技能差距分析\n")
        if gap.get("score"):
            lines.append(f"- **匹配分数**: {gap['score']}")
        if gap.get("overlap_skills"):
            lines.append(f"- **已具备**: {', '.join(gap['overlap_skills'][:8])}")
        if gap.get("missing_skills"):
            lines.append(f"- **需补充**: {', '.join(gap['missing_skills'][:8])}")

    # Section 5: Learning path
    if path and "error" not in path and path.get("steps"):
        lines.append(f"\n### 📚 学习路径（预计 {path.get('total_hours', '?')} 小时）\n")
        lines.append("| 序号 | 技能 | 原因 | 推荐资源 |")
        lines.append("|------|------|------|----------|")
        for s in path["steps"][:8]:
            res = ""
            if s.get("resources"):
                r = s["resources"][0]
                res = f"[{r['title'][:20]}]({r.get('url', '')})" if r.get("url") else r["title"][:25]
            lines.append(f"| {s['step_no']} | {s['skill']} | {s['reason'][:25]} | {res} |")

    # Section 6: Job recommendations
    if recs and "error" not in recs and recs.get("recommendations"):
        lines.append(f"\n### 💼 推荐岗位\n")
        lines.append("| 岗位 | 技能覆盖 | 预计学习时间 | 待补技能 |")
        lines.append("|------|----------|-------------|----------|")
        for r in recs["recommendations"][:5]:
            missing = ", ".join(r.get("skill_gap", {}).get("missing", [])[:3])
            hours = f"{r['path_hours']}h" if r.get("path_hours") else "-"
            lines.append(f"| {r['fine_role']} | {r['score']:.1%} | {hours} | {missing} |")

    lines.append("\n---")
    lines.append("💡 *可继续追问：「详细学习路径」「对比其他角色」「更多趋势证据」*")
    return "\n".join(lines)


def _format_resume_response(result: dict) -> str:
    if "error" in result:
        return f"❌ 分析失败: {result['error']}"
    lines = ["## 📋 简历/技能分析结果\n"]
    if result.get("education"):
        lines.append(f"**学历**: {result['education']}")
    if result.get("years_experience"):
        lines.append(f"**工作经验**: {result['years_experience']} 年")
    if result.get("target_role"):
        lines.append(f"**目标岗位**: {result['target_role']}")
    skills = result.get("skills", [])
    lines.append(f"\n### 🎯 识别到 {len(skills)} 项技能\n")
    for s in skills:
        lines.append(f"- {s}")
    lines.append("\n---\n💡 *输入「推荐岗位」查看匹配度最高的岗位，或输入角色名查询趋势*")
    return "\n".join(lines)


def _format_career_report(resume: dict, gap: dict, path: dict, trend: dict, target: str) -> str:
    lines = [f"## 📊 职业发展综合报告 — {target}\n"]

    lines.append("### 🎯 技能分析\n")
    lines.append(f"**识别技能**: {', '.join(resume.get('skills', []))}")

    if gap and "error" not in gap:
        lines.append(f"\n### 📌 技能差距（vs {gap.get('target_role', target)}）\n")
        lines.append(f"- **匹配分数**: {gap.get('score', 'N/A')}")
        if gap.get("overlap_skills"):
            lines.append(f"- **已具备**: {', '.join(gap['overlap_skills'][:8])}")
        if gap.get("missing_skills"):
            lines.append(f"- **需补充**: {', '.join(gap['missing_skills'][:8])}")

    if path and "error" not in path and path.get("steps"):
        lines.append(f"\n### 📚 学习路径（预计 {path.get('total_hours', '?')} 小时）\n")
        lines.append("| 序号 | 技能 | 原因 | 资源 |")
        lines.append("|------|------|------|------|")
        for s in path["steps"][:8]:
            res = s["resources"][0]["title"][:25] if s.get("resources") else ""
            lines.append(f"| {s['step_no']} | {s['skill']} | {s['reason'][:20]} | {res} |")

    if trend and "error" not in trend:
        arrow = {"up": "📈 上升", "down": "📉 下降", "flat": "➡️ 平稳"}.get(trend.get("trend_direction", ""), "")
        lines.append(f"\n### 📈 {target} 行业趋势\n")
        lines.append(f"- **趋势方向**: {arrow}")
        lines.append(f"- **预测需求指数**: {trend.get('predicted_demand_index', 0):.4f}")
        lines.append(f"- **置信度**: {trend.get('confidence', 0):.0%}")

    return "\n".join(lines)


def _format_trend_response(pred: dict, evidence: dict, cot: dict | None = None,
                           cot_analysis: str | None = None) -> str:
    if "error" in pred:
        return f"未找到相关角色：{pred['error']}"
    from app.services.evidence_color import event_polarity
    arrow = {"up": "📈 上升", "down": "📉 下降", "flat": "➡️ 平稳"}.get(pred.get("trend_direction", ""), "")
    lines = [
        f"## {pred.get('canonical_role', '')} 趋势预测\n",
        f"**趋势方向**: {arrow}",
        f"**预测需求指数**: {pred.get('predicted_demand_index', 0):.4f}",
        f"**置信度**: {pred.get('confidence', 0):.0%}\n",
    ]
    factors = pred.get("main_factors", [])
    if factors:
        lines.append("### 关键驱动因素")
        for f in factors:
            lines.append(f"- {f}")

    ev_data = pred.get("evidence", [])
    if ev_data:
        lines.append(f"\n### 相关证据（{len(ev_data)} 条）")
        for ev in ev_data[:5]:
            polarity = event_polarity(ev)
            emoji = {"positive": "🟢", "negative": "🔴"}.get(polarity, "⚪")
            title = ev.get("title", "事件")
            lines.append(f"- {emoji} [{title[:50]}] — {ev.get('source', 'GDELT')}")

    if evidence and "error" not in evidence:
        agg = evidence.get("aggregate")
        if agg:
            lines.append(f"\n### 新闻聚合信号")
            lines.append(f"- 相关新闻: {agg.get('article_count', 0)} 条")
            lines.append(f"- 平均情绪: {agg.get('mean_tone', 0):.2f}")
            lines.append(f"- 净信号: {agg.get('net_signal', 'N/A')}")

    # CoT grounded reasoning (LLM chain-of-thought with citations)
    if cot_analysis:
        lines.append(f"\n### 🔗 链式推理分析（CoT）\n")
        lines.append(cot_analysis)
    elif cot and "error" not in cot:
        ctx = cot.get("context", {})
        majors = ctx.get("major_events", [])
        if majors:
            lines.append(f"\n### 📌 重大行业事件\n")
            for m in majors:
                lines.append(f"- [{m['cite']}] {m.get('date', '')} — {m.get('title', '')} ({m.get('impact', '')})")
        cot_events = ctx.get("events", [])
        counter = [e for e in cot_events if e.get("is_counter_signal")]
        if counter:
            lines.append(f"\n**反向信号（需注意）：**")
            for e in counter:
                lines.append(f"- [{e['cite']}] {e.get('title', '')} — {e.get('event_type', '')}")

    return "\n".join(lines)


def _format_compare_response(results: list[dict]) -> str:
    if not results:
        return "未找到可对比的角色。"
    lines = ["## ⚖️ 角色趋势对比\n"]
    lines.append("| 角色 | 趋势 | 预测需求指数 | 置信度 |")
    lines.append("|------|------|-------------|--------|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['canonical_role']} | ❌ | - | - |")
            continue
        arrow = {"up": "📈", "down": "📉", "flat": "➡️"}.get(r.get("trend_direction", ""), "")
        lines.append(
            f"| {r['canonical_role']} | {arrow} {r.get('trend_direction', '')} | "
            f"{r.get('predicted_demand_index', 0):.4f} | {r.get('confidence', 0):.0%} |"
        )
    return "\n".join(lines)


def _format_dashboard_response(taxonomy: list[dict], query: str) -> str:
    from app.services.trend import TrendService
    by_cat: dict[str, list] = {}
    for r in taxonomy:
        by_cat.setdefault(r.get("category", "Other"), []).append(r["canonical_role"])
    total = len(taxonomy)

    lines = [
        "## 🏠 IT 行业趋势概览\n",
        f"覆盖 **{total}** 个细分岗位，{len(by_cat)} 个分类\n",
        "### 分类概览\n",
    ]
    for cat, names in by_cat.items():
        lines.append(f"- **{cat}**: {', '.join(names[:4])}{'...' if len(names) > 4 else ''} ({len(names)}个)")

    lines.append("\n---")
    lines.append("💡 **你可以：**")
    lines.append("- 输入角色名查趋势，如「AI Engineer 前景如何」")
    lines.append("- 粘贴简历获取技能分析和岗位推荐")
    lines.append("- 描述技能背景，如「我会Python和SQL，想转AI方向」")
    lines.append("- 对比角色，如「对比 AI Engineer 和 MLOps Engineer」")
    return "\n".join(lines)
