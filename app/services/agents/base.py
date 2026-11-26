"""多 agent 基础设施：子 agent 规格与 function-calling 执行循环。

每个专才 agent = 独立 system prompt + 工具子集（从 agent.py 的 TOOL_DEFINITIONS 过滤），
工具实现仍复用 app.services.agent._execute_tool，保证行为与单 agent 版一致。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from app.core.config import settings


@dataclass
class AgentSpec:
    key: str                     # 路由用的英文键，如 "career"
    name: str                    # 展示名，如 "职业匹配 Agent"
    description: str             # 给编排器看的职责描述
    system_prompt: str           # 专才 system prompt（编排器会再叠加全局 guardrails）
    tool_names: list[str] = field(default_factory=list)


def _tool_defs(tool_names: list[str]) -> list[dict]:
    from app.services.agent import TOOL_DEFINITIONS

    return [t for t in TOOL_DEFINITIONS if t["function"]["name"] in set(tool_names)]


def llm_call(messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.3, json_mode: bool = False) -> dict:
    """单次 chat/completions 调用，返回 message dict；失败抛异常由上层兜底。"""
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
    payload: dict = {"model": settings.llm_model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=settings.llm_timeout_sec) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def run_agent(spec: AgentSpec, task: str, context: str = "", max_rounds: int = 6) -> str:
    """执行一个专才 agent：task 为编排器派发的子任务，context 为对话历史摘要。"""
    from app.services.agent import SYSTEM_GUARDRAILS, _execute_tool

    tools = _tool_defs(spec.tool_names)
    user_content = task if not context else f"{task}\n\n【对话上下文】\n{context}"
    conversation = [
        {"role": "system", "content": f"{SYSTEM_GUARDRAILS}\n\n{spec.system_prompt}"},
        {"role": "user", "content": user_content},
    ]
    for _ in range(max_rounds):
        msg = llm_call(conversation, tools=tools or None)
        conversation.append(msg)
        if not msg.get("tool_calls"):
            return msg.get("content", "")

        cot_prompt_pending = ""
        for tc in msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}
            result = _execute_tool(fn_name, fn_args)
            conversation.append({
                "role": "tool", "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
            if fn_name == "get_cot_explanation" and isinstance(result, dict) and "error" not in result:
                cot_prompt_pending = result.get("cot_prompt", "") or cot_prompt_pending
        if cot_prompt_pending:
            from app.services.trend_explanation import COT_SYSTEM_PROMPT

            conversation.append({"role": "system", "content": COT_SYSTEM_PROMPT})
            conversation.append({"role": "user", "content": f"请基于以上证据进行链式推理分析：\n\n{cot_prompt_pending}"})
    return conversation[-1].get("content", "（处理轮次过多，请简化问题）")
