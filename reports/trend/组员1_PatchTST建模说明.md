# 组员1：PatchTST 时序趋势预测建模说明

本文档说明行业趋势模块当前使用的 PatchTST 预测方案。模型基于修正后的行业月度数据，为 69 个 IT 岗位生成未来 36 个月的需求趋势，并提供逐月预测、关键节点和指标级证据回溯。

## 1. 数据来源

模型数据准备以以下本地文件为唯一权威输入：

```text
data/gold/role_month_features.json
```

数据准备脚本不会优先读取 PostgreSQL，避免数据库未同步时使用旧数据。脚本将稀疏的岗位月度记录补齐为固定长度面板，并输出：

```text
data/gold/patchtst_role_month_features.json
data/gold/patchtst_role_month_features.parquet
```

当前面板规模：

| 项目 | 数值 |
|:--|--:|
| 岗位数 | 69 |
| 月份数 | 77 |
| 时间范围 | 2020-01-01 至 2026-05-01 |
| 面板行数 | 5313 |
| GDELT impact 非零岗位数 | 67 |
| arXiv 正向论文信号岗位数 | 27 |

主要数据字段包括：

| 数据源 | 字段 | 用途 |
|:--|:--|:--|
| JD | `jd_demand_index` | PatchTST 输入和预测目标 |
| JD | `jd_demand_observed` | 标记真实 JD 标签月份 |
| GDELT | `gdelt_sentiment_index`、`gdelt_article_count` | 新闻趋势校准与证据回溯 |
| GDELT | `gdelt_opportunity_index`、`gdelt_risk_index` | 机会和风险趋势校准 |
| GDELT | `gdelt_event_impact_score` | 事件冲击趋势校准 |
| GitHub | `github_repo_count`、`github_repo_stars` | 技术活跃度校准 |
| arXiv | `arxiv_paper_count` | 学术热度校准 |

数据面板不会把 JD 数据断档月份当成真实的零需求。每个岗位在最后一个真实 JD 月份之后沿用最近需求值作为预测上下文，同时将 `jd_demand_observed` 设为 `false`。训练窗口只有在完整预测区间均为真实 JD 标签时才会进入训练或验证。

GDELT、GitHub 和 arXiv 分别使用 `gdelt_observed`、`github_observed`、`arxiv_observed` 标记真实来源记录。缺失数据不会被当作真实零信号参与校准。

## 2. 模型方案

主模型使用轻量级 PatchTST 风格网络，只对 `jd_demand_index` 建模：

```text
最近 24 个月 JD 需求序列
  -> 长度 6、步长 3 的时间块
  -> 线性 Patch Embedding
  -> Transformer Encoder
  -> Prediction Head
  -> 未来 36 个月 JD 需求指数
```

模型预测的是相对输入末月基线的需求变化，训练时对输入和目标变化分别标准化，损失函数为 Smooth L1 Loss。所有岗位共享同一个模型，但滑动窗口不会跨岗位拼接。

默认参数：

| 参数 | 值 |
|:--|--:|
| `context_length` | 24 |
| `horizon` | 36 |
| `patch_len` | 6 |
| `stride` | 3 |
| `d_model` | 64 |
| `n_heads` | 4 |
| `num_layers` | 2 |
| `dropout` | 0.10 |
| `batch_size` | 64 |
| `epochs` | 80 |
| `learning_rate` | 0.001 |
| `weight_decay` | 0.0001 |
| `seed` | 42 |

## 3. 外部信号校准

GDELT、GitHub 和 arXiv 不直接进入 PatchTST 训练通道，而是在主模型预测后用于短期校准。这样可以保留 JD 需求序列的可解释边界，同时使用更新到 2026 年的行业信号修正近期预测。

校准规则：

- GDELT 综合新闻情绪、机会、风险和事件冲击趋势，最大调整幅度为 0.03。
- GitHub 综合仓库数和 star 趋势，最大调整幅度为 0.015。
- arXiv 使用论文数量趋势，最大调整幅度为 0.01。
- 三类信号总调整幅度限制在 `[-0.05, 0.05]`。
- 第 1 至 3 个月使用完整调整，第 4 至 6 个月逐步衰减，第 7 个月起不再调整。
- 数据不足两个月或最新信号超过 6 个月时，该来源不参与校准。

每条预测同时保留 `base_predicted_demand_index`、`supplemental_adjustment` 和各来源信号详情，便于追踪最终预测的形成过程。

## 4. 训练与评估

当前数据可构建 40 个完整监督窗口，其中训练样本 32 个、验证样本 8 个。验证预测起点为 2022-01-01 至 2022-05-01。

最新验证指标：

| 指标 | 数值 |
|:--|--:|
| MAE | 0.100506 |
| RMSE | 0.134899 |
| sMAPE | 0.293748 |
| 3 个月 MAE | 0.109211 |
| 3 个月方向准确率 | 0.75 |
| 6 个月 MAE | 0.050266 |
| 6 个月方向准确率 | 0.75 |
| 12 个月 MAE | 0.057597 |
| 12 个月方向准确率 | 0.75 |

验证指标衡量 PatchTST 主预测，不包含未来未知外部信号。36 个月预测更适合作为趋势规划参考，不应解释为因果结论。

## 5. 预测产物

模型覆盖 2026-06-01 至 2029-05-01，共生成 69 个岗位、2484 条逐月预测。

| 交付物 | 路径 |
|:--|:--|
| 稠密训练面板 | `data/gold/patchtst_role_month_features.json` |
| 训练面板 Parquet | `data/gold/patchtst_role_month_features.parquet` |
| 模型权重 | `models/patchtst_trend/patchtst_trend_model.pt` |
| 训练指标 | `models/patchtst_trend/patchtst_metrics.json` |
| 36 个月逐月预测 | `data/gold/patchtst_predictions_36m.json` |
| 关键节点预测 | `data/gold/patchtst_prediction_milestones.json` |

关键节点文件为每个岗位保留第 3、6、12、24、36 个月的预测。

逐月记录的核心结构：

```json
{
  "canonical_role": "AI Engineer",
  "month": "2026-06-01",
  "step": 1,
  "base_predicted_demand_index": 0.4,
  "predicted_demand_index": 0.41,
  "trend_direction": "up",
  "confidence": 0.8,
  "change_from_latest": 0.04,
  "supplemental_adjustment": 0.01,
  "supplemental_signals": {}
}
```

## 6. 使用方式

从修正后的本地数据重建面板：

```powershell
python -m pipelines.trend.prepare_trend_model_dataset
```

使用默认参数训练模型：

```powershell
python -m pipelines.trend.train_patchtst_predictor
```

生成逐月预测和关键节点：

```powershell
python -m pipelines.trend.generate_patchtst_predictions
```

服务接口保持不变：

```python
from app.services.trend_predictor import get_evidence, get_milestones, predict

forecast = predict("AI Engineer", months=36)
milestones = get_milestones("AI Engineer")
evidence = get_evidence("AI Engineer", "2029-05-01")
```

- `predict(role, months)` 返回逐月预测。
- `get_milestones(role)` 返回 3/6/12/24/36 月节点。
- `get_evidence(role, month)` 返回历史指标、JD 观测范围、关键因素、转折点和预测校准证据。

## 7. 使用边界

- 模型输出是基于历史序列和近期行业信号的预测，不代表因果关系。
- JD 真实标签覆盖不足的岗位不会产生监督训练窗口，但仍可使用共享模型预测。
- arXiv 采集结果只记录命中论文的月份，因此未命中月份按“未观测”处理，而不是确认的零论文月份。
- 第 7 至 36 个月不使用当前外部信号校准，长期结果主要由 PatchTST 主模型决定。
- 指标级证据不包含新闻正文、新闻 URL 或 JD 原始链接。
