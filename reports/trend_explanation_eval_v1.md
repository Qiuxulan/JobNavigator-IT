# 趋势证据评估报告 (trend_explanation_eval_v1)

- 生成：2026-06-13T01:01:52
- 模块：C（证据检索 RAG，完整版四重约束 + 聚合信号）
- 输出：`data/gold/trend_evidence_v1.jsonl`

## 1. 核心指标

| 指标 | 数值 |
|---|---|
| 趋势结论总数 | 345 |
| **含聚合信号(aggregate)覆盖率** | **97.1%**（335/345） |
| 含干净事件样本覆盖率 | 97.1%（335/345） |
| 平均干净事件数/条 | 4.16（TopK=5） |
| 聚合方向与结论一致 | 243/345 |
| 覆盖角色 | 69 |

## 2. 两层证据说明

**主力 = 聚合信号**：每条结论几乎都有 aggregate（篇数/情绪/机会·风险/净信号），由多篇文档统计而来，对单篇噪音稳健，是趋势佐证主力，覆盖率远高于干净事件。

**佐证 = 干净事件样本**：过四重约束（技能白名单+主题共现+域名黑名单+方向一致）才入选，少而精，标注“相关性近似”。

## 3. 数据质量与口径

1. GDELT 无标题/正文，匹配多为关键词/URL 伪词；本模块用约束换精度，召回不足由聚合兜底。
2. 方向归一：B 的 `flat` → 契约 `stable`，原值存 `trend_direction_raw`。
3. 粒度：按 `canonical_role` 出行，`role_family`=taxonomy.category，D 可聚合。
4. JD 证据 `job_url` 源数据为空，降级为存在性证据（公司/标题/薪资）。

## 4. 抽检样例

```json
{
  "trend_id": "net_backend_engineer_3_month",
  "role_family": "Backend Development",
  "canonical_role": ".NET Backend Engineer",
  "skill_name": null,
  "month": "2026-08-01",
  "horizon_months": 3,
  "evidence_window": [
    "2026-01",
    "2026-06"
  ],
  "conclusion": ".NET Backend Engineer 预计未来 3 个月需求持平（预测月 2026-08-01，需求指数 0.38，置信度 79%）。 近 6 个月相关新闻 94136 篇，净信号 negative。",
  "trend_direction": "stable",
  "trend_direction_raw": "flat",
  "predicted_demand_index": 0.3802,
  "confidence": 0.7946,
  "main_factors": [
    "gdelt",
    "github",
    "arxiv"
  ],
  "aggregate": {
    "article_count": 94136,
    "mean_tone": -0.72,
    "positive_ratio": 0.433,
    "opportunity_events": 31924,
    "risk_events": 34469,
    "net_signal": "negative",
    "top_themes": [
      "EPU_POLICY",
      "WB_133_INFORMATION_AND_COMMUNICATION_TECHNOLOGIES",
      "WB_678_DIGITAL_GOVERNMENT",
      "USPEC_POLICY1",
      "EPU_ECONOMY_HISTORIC",
      "WB_135_TRANSPORT"
    ],
    "top_domains": [
      "www.manilatimes.net",
      "www.calcuttanews.net",
      "www.abc.net.au",
      "www.bssnews.net",
      "www.thedailystar.net"
    ]
  },
  "evidence_topk": [
    {
      "source_name": "GDELT",
      "source_url": "https://www.tomshardware.com/tech-industry/big-tech/microsoft-facing-usd2-8-billion-uk-lawsuit-for-overcharging-60-000-businesses-using-microsoft-server-on-other-clouds-azure-users-allegedly-recieved-lower-wholesale-pricing",
      "title": "microsoft facing usd2 8 billion uk lawsuit for overcharging 60 000 businesses using microsoft server on other clouds azu",
      "published_at": "2026-04-22",
      "evidence_text": "www.tomshardware.com · policy · tone -3.103",
      "retrieval_score": 0.4644,
      "evidence_type": "policy",
      "impact_direction": "negative",
      "evidence_strength": "strong"
    },
    {
      "source_name": "GDELT",
      "source_url": "http://www.newjerseytelegraph.com/news/279049142/amdocs-entitlement-server-sets-new-industry-performance-benchmark-on-microsoft-azure",
      "title": "amdocs entitlement server sets new industry performance benchmark on microsoft azure",
      "published_at": "2026-05-14",
      "evidence_text": "www.newjerseytelegraph.com · security_incident · tone 1.577",
      "retrieval_score": 0.4545,
      "evidence_type": "security_incident",
      "impact_direction": "positive",
      "evidence_strength": "strong"
    }
  ],
  "major_industry_events": [
    {
      "event_id": "evt_openai_gpt41_api_2025_04",
      "title": "OpenAI released GPT-4.1 API models with stronger coding, long-context and agent capabilities",
      "event_date": "2025-04-14",
      "source_name": "OpenAI",
      "source_url": "https://openai.com/index/gpt-4-1/",
      "event_type": "model_release",
      "impact_direction": "positive",
      "event_importance": 0.95,
      "summary_zh": "GPT-4.1 强调代码能力、指令遵循和 100 万 token 长上下文，提升 AI Agent、RAG、代码生成、前端生成和自动化测试的可用性。"
    },
    {
      "event_id": "evt_openai_codex_2025_05",
      "title": "OpenAI introduced Codex as a cloud software engineering agent",
      "event_date": "2025-05-16",
      "source_name": "OpenAI",
      "source_url": "https://openai.com/index/introducing-codex/",
      "event_type": "ai_coding_agent",
      "impact_direction": "mixed",
      "event_importance": 0.95,
      "summary_zh": "云端代码智能体可以读代码、改代码、跑测试并提交变更，利好 AI/DevOps/自动化岗位，同时压缩部分初级开发与重复性测试任务。"
    },
    {
      "event_id": "evt_aidev_coding_agents_github_2026_02",
      "title": "AIDev dataset documented large-scale AI coding-agent pull requests across GitHub",
      "event_date": "2026-02-09",
      "source_name": "arXiv",
      "source_url": "https://arxiv.org/abs/2602.09185",
      "event_type": "market_research",
      "impact_direction": "mixed",
      "event_importance": 0.86,
      "summary_zh": "研究收集了大规模 AI Agent PR 数据，说明 Agentic Coding 已从实验进入真实开发流程；对通用编码岗位形成效率提升和岗位结构重塑压力。"
    },
    {
      "event_id": "evt_kubernetes_133_2025_04",
      "title": "Kubernetes v1.33 released with platform, workload and cluster-operation improvements",
      "event_date": "2025-04-23",
      "source_name": "Kubernetes",
      "source_url": "https://kubernetes.io/blog/2025/04/23/kubernetes-v1-33-release/",
      "event_type": "platform_release",
      "impact_direction": "positive",
      "event_importance": 0.86,
      "summary_zh": "Kubernetes 持续演进强化云原生平台工程、DevOps、SRE、后端部署和测试环境治理需求。"
    }
  ],
  "jd_evidence": [
    {
      "evidence_type": "job_posting",
      "company_name": "Binariks",
      "title": "Senior C# (.Net) Engineer",
      "post_date": "2023-09-01",
      "salary_mid": null,
      "job_url": null,
      "out_of_range": true
    }
  ],
  "risk_notes": [
    "证据相关性为近似（GDELT 无正文，基于技能白名单+主题共现约束）。",
    "证据多为英文新闻源，中文本土市场需补充。"
  ],
  "model_version": "trend-evidence-v2-constrained"
}
```