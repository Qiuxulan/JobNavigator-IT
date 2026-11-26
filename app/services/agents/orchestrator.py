"""编排器：意图路由 → 并行派单给专才 agent → 汇总润色。

流程：
  1. router LLM 调用（JSON mode）：把用户问题拆成 1-3 个子任务，每个指定一个专才 agent；
     路由失败时退回关键词启发式。
  2. 子任务在 ThreadPoolExecutor 中并行执行（各自独立 function-calling 循环）。
  3. 单任务直接返回该 agent 的回答；多任务再做一次聚合 LLM 调用，把多个专才结果
     整合成一篇连贯回答（保留各专才的引用标记 [E#]/[来源, 日期]）。
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from app.services.agents.base import llm_call, run_agent
from app.services.agents.registry import AGENTS

ROUTER_PROMPT = """你是多智能体编排器。把用户的职业/行业问题拆成子任务，派给下列专才 agent：

{agent_docs}

规则：
1. 输出严格 JSON：{{"tasks": [{{"agent": "<key>", "task": "<该 agent 要完成的具体子任务，中文，自包含>"}}], "reason": "<一句话路由理由>"}}
2. tasks 1-3 个：单一意图只派 1 个；复合问题（如“推荐岗位并给学习路径”）按领域拆成多个，agent 可重复。
3. task 必须自包含：把用户问题中该 agent 需要的背景（技能、目标岗位、时间范围）完整写进去。
4. 拿不准归属时派给 career。"""

_KEYWORD_ROUTES = [
    ("news", ["新闻", "动态", "最近发生", "裁员", "倒闭", "融资", "发布", "热搜", "公司在招", "招聘情况", "市场大盘"]),
    ("industry", ["趋势", "前景", "预测", "会不会被取代", "饱和", "需求", "对比", "哪个更有前途", "行情"]),
    ("planner", ["学习", "路径", "课程", "资料", "怎么学", "先学", "补哪", " roadmap", "教程"]),
    ("career", ["推荐", "适合", "匹配", "简历", "技能", "转行", "gap", "缺口", "方向"]),
]


def _heuristic_route(user_msg: str) -> list[dict]:
    q = user_msg.lower()
    hits = []
    for key, words in _KEYWORD_ROUTES:
        if any(w in q for w in words):
            hits.append(key)
    if not hits:
        hits = ["career"]
    return [{"agent": hits[0], "task": user_msg}]


def _llm_route(user_msg: str, history_hint: str) -> list[dict]:
    agent_docs = "\n".join(f"- {s.key}（{s.name}）：{s.description}" for s in AGENTS.values())
    prompt = ROUTER_PROMPT.format(agent_docs=agent_docs)
    content = user_msg if not history_hint else f"{user_msg}\n\n【对话上下文】\n{history_hint}"
    msg = llm_call(
        [{"role": "system", "content": prompt}, {"role": "user", "content": content}],
        temperature=0.1, json_mode=True,
    )
    data = json.loads(msg.get("content") or "{}")
    tasks = data.get("tasks") or []
    valid = []
    for t in tasks[:3]:
        key, task = t.get("agent"), (t.get("task") or "").strip()
        if key in AGENTS and task:
            valid.append({"agent": key, "task": task})
    if not valid:
        raise ValueError("router 未给出有效任务")
    return valid


def _aggregate(user_msg: str, results: list[dict]) -> str:
    sections = "\n\n".join(
        f"### {AGENTS[r['agent']].name} 的回答\n{r['answer']}" for r in results if r.get("answer")
    )
    prompt = """你是多智能体系统的汇总器。下面是多个专才 agent 对同一用户问题的分析结果。
请整合成一篇连贯的中文回答：
1. 结论先行，保留各 agent 的关键数据、匹配分、趋势结论与引用标记（[E#]/[M#]/[来源, 日期]）；
2. 去除重复内容，统一术语与口吻；
3. 不得新增任何数字、岗位、新闻或资源；
4. 如果某个 agent 明确说“数据库没有该信息”，汇总时如实保留这一限制。"""
    msg = llm_call(
        [{"role": "system", "content": prompt},
         {"role": "user", "content": f"用户问题：{user_msg}\n\n{sections}"}],
        temperature=0.3,
    )
    return msg.get("content") or sections


def run_multi_agent(messages: list[dict], max_rounds: int = 6) -> str:
    user_msg = messages[-1].get("content", "") if messages else ""
    history = [m for m in messages[:-1] if m.get("role") in ("user", "assistant")]
    history_hint = "\n".join(f"{m['role']}: {m.get('content', '')[:300]}" for m in history[-4:])

    try:
        tasks = _llm_route(user_msg, history_hint)
    except Exception as e:
        print(f"[multi-agent] 路由失败，退回启发式: {type(e).__name__}: {e}", flush=True)
        tasks = _heuristic_route(user_msg)

    results: list[dict] = []

    def _run(t: dict) -> dict:
        spec = AGENTS[t["agent"]]
        try:
            return {"agent": t["agent"], "answer": run_agent(spec, t["task"], history_hint, max_rounds=max_rounds)}
        except Exception as e:  # 单个专才失败不拖垮整体
            print(f"[multi-agent] {t['agent']} 执行失败: {type(e).__name__}: {e}", flush=True)
            return {"agent": t["agent"], "answer": "", "error": str(e)[:200]}

    if len(tasks) == 1:
        results = [_run(tasks[0])]
    else:
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            results = list(pool.map(_run, tasks))

    ok = [r for r in results if r.get("answer")]
    if not ok:
        raise RuntimeError("所有专才 agent 均失败: " + "; ".join(r.get("error", "?") for r in results))
    if len(ok) == 1:
        return ok[0]["answer"]
    try:
        return _aggregate(user_msg, ok)
    except Exception as e:
        print(f"[multi-agent] 聚合失败，拼接返回: {type(e).__name__}: {e}", flush=True)
        return "\n\n".join(f"**{AGENTS[r['agent']].name}**\n\n{r['answer']}" for r in ok)
