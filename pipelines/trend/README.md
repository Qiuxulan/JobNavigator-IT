# 趋势流水线

## 执行顺序

```bash
# 0. 角色分类（仅首次运行）
python -m pipelines.trend.build_role_taxonomy

# 1. 数据采集
python -m pipelines.trend.collect_hf_recruitment_jobs       # HF 招聘数据 (141K)
python -m pipelines.trend.collect_ai_job_dataset_jobs        # AI 岗位补充 (15K)

# 2. 岗位标准化 + 角色匹配
python -m pipelines.trend.standardize_jd_roles               # 匹配到69角色
python -m pipelines.trend.build_jd_role_month_features       # JD 月特征聚合

# 3. GDELT 新闻数据处理
python -m pipelines.trend.process_gdelt_gkg_local            # 本地 GKG zip 处理

# 4. 技术热度采集
python -m pipelines.trend.collect_tech_heat                  # GitHub + arXiv

# 5. 特征合并 + 模型数据
python -m pipelines.trend.build_role_month_features          # 三源合并
python -m pipelines.trend.score_role_trends                  # 趋势评分
python -m pipelines.trend.prepare_trend_model_dataset        # PatchTST 数据集
```

## 说明

- **数据源**：JD（HF+AIRecruitment） + GDELT GKG（本地158 zip） + Tech Heat（GitHub+arXiv）
- **时间范围**：2020-01 ~ 2026-05（77个月），69个角色
- **全量数据**：所有采集脚本默认无样本限制（sample_limit=0）
- **GDELT 本地处理**：处理 `data/GDELT/` 下的 GKG zip，产出：
  - `gdelt_gkg_role_documents.jsonl` — **岗位级事件证据**（RAG 证据链用，已保留）
  - `gdelt_gkg_role_month_features.json` / `gdelt_impact_role_month_features.json` — 月特征
- **JD 原始缓存**：`collect_*_jobs` 脚本从 Arrow/CSV 源读取，处理后缓存到 JSON。`standardize_jd_roles` 回退读取这些缓存。
- **LinkedIn/Kaggle**：已禁用并移除相关代码
- **Google Trends**：已禁用（`trend_enable_google_trends=False`）
- **DOC API**：`collect_gdelt_role_articles` / `build_gdelt_role_month_features` 已移除，全部由 GKG 本地处理替代
- **PatchTST**：`prepare_trend_model_dataset` 产出 `patchtst_role_month_features.json`（69角色×77月面板数据），`trend_patchtst_lookback_months` 控制上下文窗口
