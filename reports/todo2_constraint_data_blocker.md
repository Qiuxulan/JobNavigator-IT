# TODO-2 constraint_score 数据阻塞 — 待组内对齐

**背景**:推荐精排公式 `Final = α·语义 + β·constraint − γ·缺口 + δ·趋势` 里的 `constraint_score`，设计意图是拿用户偏好（`preferred_city / expected_salary_k / degree_floor`）去匹配岗位的城市/薪资/学历。目前代码里是固定值 `0.8`（`app/services/recommender.py` TODO-2）。要改成真值时，发现现有数据支撑不了。

## 数据现状（岗位库三源各自能提供什么）

| 源 | 记录数 | 占比 | 城市 | 薪资 | 学历 |
|---|---|---|---|---|---|
| **djinni** | 30,843 | 74% | ❌ 无 | ❌ 无 | ❌ 无 |
| **emerging** | 9,259 | 22% | ✅ 美国城市（"Houston, Harris County"） | ✅ USD 年薪（131393） | ❌ 无 |
| **asaniczka** | 1,724 | 4% | ✅ 美国 job_location | ❌ 无 | ❌ 无 |

字段来源：`data/raw/djinni/djinni_jd.csv`、`data/raw/emerging_it_jd.jsonl`、`data/raw/asaniczka/job_postings.csv`。

## 三个阻塞点

1. **占 74% 的 Djinni 主源三样全无**——岗位库主体没有城市/薪资来源。
2. **唯一有薪资的 emerging 是美国 USD 年薪**，而用户场景是中文简历、`preferred_city=上海`、`expected_salary_k`（单位 k）。"上海" vs "Houston"、"期望薪资 k" vs "131393 USD/年"，口径完全对不上，算出来的 constraint 是噪声，会污染推荐。
3. **没有任何源带学历字段**，`degree_floor` 从现有数据永远无法实现。

## 额外工程成本

岗位库 JSON（`fine_grained_roles_v1.json`）只保留了 `source_mix`（各源计数），**没保留每个簇的成员 JD**。要按簇聚合城市/薪资，得先重跑聚类拿回"每条 JD → 哪个 role"的映射，再 join 原始记录——而且只覆盖那 22% 的美国 emerging 数据。

## 需要组里决定的事

`constraint_score` 这个维度，在当前数据下要不要做、怎么做：

- **A. 维持固定值 0.8，标为数据阻塞**：最诚实，不造假数据污染推荐；答辩时讲清为什么没做。
- **B. 部分实现（有则用、无则回退 0.8）**：从 emerging/asaniczka 聚合，但数据是美国 USD，只能算 demo 级近似，语义与中文场景不一致。
- **C. 重定义 constraint**：放弃 city/salary，改用 asaniczka/emerging 都有的 `job_level/job_type`（资历/全职）；或把 constraint 退出公式、权重并入 semantic。

**连带问题**：如果决定保留 city/salary 约束，需要有人补一份带"中国城市 + CNY 薪资"的岗位数据源，否则这个维度对中国用户没有意义。

---
*由 B 模块（推荐）整理，2026-06-01。`recommender.py` 中 TODO-2 / TODO-4 标记暂保留。*
