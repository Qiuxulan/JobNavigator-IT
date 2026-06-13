# 行业模块数据字段规范

本文档定义行业分析模块的核心数据表字段，作为 A/B/C/D 四个任务之间的统一数据契约。

适用范围：

1. 行业数据采集与事件结构化
2. 趋势预测模型训练与评估
3. 证据检索与趋势解释
4. 行业融合评分与接口输出

## 1. 命名与分层约定

数据分层沿用项目数据设计：

1. `raw`
: 原始下载、爬取或 API 返回结果，保留原始字段。
2. `silver`
: 清洗后的统一字段，完成时间、岗位族、技能名、来源等标准化。
3. `gold`
: 模型训练、评估和服务接口直接使用的数据。

行业模块主要交付文件：

| 文件 | 负责人 | 用途 |
|---|---|---|
| `data/gold/industry_timeseries_v1.parquet` | A | 行业趋势预测主时序 |
| `data/gold/industry_events_v1.parquet` | A | 行业事件与冲击特征 |
| `data/gold/trend_forecast_v1.parquet` | B | 趋势预测输出 |
| `data/gold/trend_evidence_v1.jsonl` | C | 趋势解释证据 |
| `data/gold/industry_report_v1.json` | D | 接口返回用行业报告 |

统一命名规则：

1. 时间字段使用 ISO 格式，例如 `2026-06-01`。
2. 月粒度字段统一命名为 `month`，格式为 `YYYY-MM`。
3. 岗位族统一使用 `role_family`，例如 `ai_application`, `data_engineering`, `backend`, `security`。
4. 技能名统一使用 `skill_name`，原始技能名保留在 `raw_skill_name`。
5. 外部来源必须保留 `source_name`、`source_url`、`collected_at`。

## 2. 行业时序主表

文件：`data/gold/industry_timeseries_v1.parquet`

负责人：A 产出，B/D 消费。

粒度建议：`month + role_family + skill_name + city`。如果某来源没有城市字段，`city` 设为 `unknown`。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `month` | string | 是 | 月份，格式 `YYYY-MM` |
| `role_family` | string | 是 | 岗位族标准名 |
| `skill_name` | string | 否 | 标准技能名；岗位整体趋势可为空 |
| `raw_skill_name` | string | 否 | 来源中的原始技能名 |
| `city` | string | 否 | 城市或地区 |
| `country` | string | 否 | 国家或地区 |
| `job_count` | int | 是 | 当前粒度下岗位数量 |
| `salary_median` | float | 否 | 薪资中位数，建议统一为月薪或年薪并记录币种 |
| `salary_currency` | string | 否 | 薪资币种，如 `CNY`, `USD`, `EUR` |
| `experience_median_years` | float | 否 | 经验门槛中位数 |
| `skill_frequency` | float | 否 | 技能在该岗位族 JD 中出现的频率 |
| `github_activity` | float | 否 | GitHub 技术热度，如 star/push/release 加权值 |
| `paper_count` | int | 否 | OpenAlex 论文数量 |
| `patent_count` | int | 否 | PatentsView 专利数量 |
| `trend_keyword` | string | 否 | 用于检索技术热度的关键词 |
| `source_name` | string | 是 | 数据来源名称 |
| `source_url` | string | 否 | 数据来源链接 |
| `collected_at` | datetime | 是 | 采集或处理时间 |
| `quality_flag` | string | 否 | 质量标签，如 `ok`, `missing_salary`, `low_sample` |

## 3. 行业事件表

文件：`data/gold/industry_events_v1.parquet`

负责人：A 产出，B/C/D 消费。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `event_id` | string | 是 | 事件唯一 ID |
| `event_date` | date | 是 | 事件发生或报道日期 |
| `month` | string | 是 | 月份，格式 `YYYY-MM` |
| `source_name` | string | 是 | 来源名称，如 GDELT、工信部、Layoffs.fyi |
| `source_url` | string | 否 | 原文或数据链接 |
| `title` | string | 是 | 事件标题 |
| `event_text` | string | 否 | 事件正文或摘要 |
| `event_type` | string | 是 | 事件类型 |
| `impact_direction` | string | 是 | 影响方向：`positive`, `neutral`, `negative` |
| `impact_strength` | float | 否 | 影响强度，建议范围 0 到 1 |
| `role_family` | string | 否 | 关联岗位族 |
| `skill_name` | string | 否 | 关联技能 |
| `company_name` | string | 否 | 关联公司 |
| `region` | string | 否 | 关联地区 |
| `confidence` | float | 否 | 事件分类或关联置信度 |
| `model_name` | string | 否 | 事件分类模型名称 |
| `collected_at` | datetime | 是 | 采集或处理时间 |

`event_type` 建议枚举：

1. `policy`
2. `regulation`
3. `funding`
4. `layoff`
5. `product_release`
6. `company_announcement`
7. `research_breakthrough`
8. `market_report`
9. `security_incident`
10. `other`

## 4. 趋势预测结果表

文件：`data/gold/trend_forecast_v1.parquet`

负责人：B 产出，D 消费。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `forecast_id` | string | 是 | 预测结果唯一 ID |
| `generated_at` | datetime | 是 | 预测生成时间 |
| `target_month` | string | 是 | 被预测月份 |
| `horizon` | int | 是 | 预测步长，如 1、3、6 |
| `role_family` | string | 是 | 岗位族 |
| `skill_name` | string | 否 | 技能名 |
| `target_metric` | string | 是 | 预测目标 |
| `y_true` | float | 否 | 真实值；未来月份可为空 |
| `y_pred` | float | 是 | 预测值 |
| `y_pred_lower` | float | 否 | 置信区间下界 |
| `y_pred_upper` | float | 否 | 置信区间上界 |
| `trend_direction` | string | 是 | `up`, `stable`, `down` |
| `model_name` | string | 是 | 模型名称，如 `sarimax`, `patchtst` |
| `model_version` | string | 否 | 模型版本 |
| `features_used` | string | 否 | 使用的特征列表，可存 JSON 字符串 |

`target_metric` 建议枚举：

1. `job_count`
2. `skill_frequency`
3. `salary_median`
4. `demand_index`
5. `competition_proxy`
6. `risk_score`

## 5. 趋势证据表

文件：`data/gold/trend_evidence_v1.jsonl`

负责人：C 产出，D 消费。

每行对应一个趋势结论及其证据 TopK。

```json
{
  "trend_id": "ai_application_rag_2026_06_h3",
  "role_family": "ai_application",
  "skill_name": "RAG",
  "conclusion": "RAG 应用类岗位需求预计短期上升。",
  "trend_direction": "up",
  "evidence_topk": [
    {
      "source_name": "GDELT",
      "source_url": "https://example.com/news",
      "title": "Enterprise knowledge base adoption expands",
      "published_at": "2026-05-12",
      "evidence_text": "企业知识库问答和文档智能需求增加。",
      "retrieval_score": 0.82,
      "evidence_type": "market_report"
    }
  ],
  "risk_notes": ["证据主要来自英文新闻，中文市场需补充本土数据。"]
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `trend_id` | string | 是 | 趋势结论 ID |
| `role_family` | string | 是 | 岗位族 |
| `skill_name` | string | 否 | 技能名 |
| `conclusion` | string | 是 | 趋势结论 |
| `trend_direction` | string | 是 | `up`, `stable`, `down` |
| `evidence_topk` | array | 是 | 证据列表 |
| `risk_notes` | array | 否 | 风险提示 |

## 6. 行业报告输出结构

文件：`data/gold/industry_report_v1.json`

负责人：D 产出，接口消费。

建议结构：

```json
{
  "role_family": "ai_application",
  "role_label": "AI 应用方向",
  "trend_direction": "up",
  "opportunity_score": 0.78,
  "risk_level": "medium",
  "competition_level": "medium",
  "time_horizon": "3_months",
  "summary": "AI 应用方向短期需求上升，但对工程化落地能力要求提高。",
  "key_drivers": [
    "RAG 和 Agent 应用持续进入企业知识管理场景",
    "开源项目活跃度保持增长"
  ],
  "key_risks": [
    "初级岗位竞争增强",
    "部分企业对岗位名称使用不统一"
  ],
  "evidence": [
    {
      "title": "Enterprise knowledge base adoption expands",
      "source_name": "GDELT",
      "source_url": "https://example.com/news",
      "published_at": "2026-05-12"
    }
  ],
  "recommended_action": "优先补齐 RAG 工程化、向量数据库、评测与部署能力。"
}
```

## 7. 与接口的关系

行业报告最终应接入现有决策接口输出。建议接口内部统一使用以下字段：

| 接口字段 | 来源 | 说明 |
|---|---|---|
| `industry.role_family` | D | 岗位族 |
| `industry.trend_direction` | B/D | 趋势方向 |
| `industry.opportunity_score` | D | 综合机会分 |
| `industry.risk_level` | D | 风险等级 |
| `industry.competition_level` | D | 竞争强度 |
| `industry.summary` | C/D | 行业解释 |
| `industry.evidence` | C | 可追溯证据 |
| `industry.recommended_action` | D | 行动建议 |

## 8. 质量检查标准

进入 `gold` 层前至少满足：

1. 每条记录必须有 `source_name`。
2. 可追溯来源必须尽量保留 `source_url`。
3. 月份字段必须可解析为 `YYYY-MM`。
4. 岗位族必须映射到项目统一 `role_family`。
5. 趋势结论必须至少挂载 1 条证据。
6. 风险等级必须能解释其来源规则或模型分数。

