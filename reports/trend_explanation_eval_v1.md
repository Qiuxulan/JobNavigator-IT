# 趋势证据评估报告 (trend_explanation_eval_v1)

- 生成：2026-06-12T10:58:45
- 模块：C（证据检索 RAG，完整版四重约束 + 聚合信号）
- 输出：`data/gold/trend_evidence_v1.jsonl`

## 1. 核心指标

| 指标 | 数值 |
|---|---|
| 趋势结论总数 | 340 |
| **含聚合信号(aggregate)覆盖率** | **97.9%**（333/340） |
| 含干净事件样本覆盖率 | 97.9%（333/340） |
| 平均干净事件数/条 | 4.55（TopK=5） |
| 聚合方向与结论一致 | 313/340 |
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
  "trend_id": "net_backend_engineer_2026-01-01_h3",
  "role_family": "Backend Development",
  "canonical_role": ".NET Backend Engineer",
  "skill_name": null,
  "month": "2026-01-01",
  "horizon_months": 3,
  "conclusion": ".NET Backend Engineer 预计未来 3 个月需求持平（需求指数 0.53，置信度 65%）。 本月相关新闻 16343 篇，净信号 positive。",
  "trend_direction": "stable",
  "trend_direction_raw": "flat",
  "predicted_demand_index": 0.5262,
  "confidence": 0.65,
  "main_factors": [
    "行业机会类新闻增强",
    "行业风险类新闻增强"
  ],
  "aggregate": {
    "article_count": 16343,
    "mean_tone": -0.714,
    "positive_ratio": 0.444,
    "opportunity_events": 5672,
    "risk_events": 5347,
    "net_signal": "positive",
    "top_themes": [
      "EPU_POLICY",
      "WB_133_INFORMATION_AND_COMMUNICATION_TECHNOLOGIES",
      "WB_678_DIGITAL_GOVERNMENT",
      "USPEC_POLICY1",
      "EPU_ECONOMY_HISTORIC",
      "WB_696_PUBLIC_SECTOR_MANAGEMENT"
    ],
    "top_domains": [
      "www.manilatimes.net",
      "www.calcuttanews.net",
      "www.abc.net.au",
      "www.thedailystar.net",
      "www.bssnews.net"
    ]
  },
  "evidence_topk": [
    {
      "source_name": "GDELT",
      "source_url": "https://www.openpr.com/news/4336503/azure-mattress-review-shows-how-trust-drives-brand-loyalty",
      "title": "azure mattress review shows how trust drives brand loyalty",
      "published_at": "2026-01-05",
      "evidence_text": "www.openpr.com · market_report · tone 2.247",
      "retrieval_score": 0.6225,
      "evidence_type": "market_report",
      "impact_direction": "positive"
    },
    {
      "source_name": "GDELT",
      "source_url": "https://it-online.co.za/2026/01/16/mid-tier-security-engineer-azure-sentinel-microsoft-defender-dbn-hybrid/",
      "title": "mid tier security engineer azure sentinel microsoft defender dbn hybrid",
      "published_at": "2026-01-17",
      "evidence_text": "it-online.co.za · security_incident · tone 4.008",
      "retrieval_score": 0.4946,
      "evidence_type": "security_incident",
      "impact_direction": "positive"
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