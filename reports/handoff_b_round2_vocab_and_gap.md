# B 模块第二轮改动交接说明 —— 词表中文化 + 缺口口径修正

> 作者:B(细粒度岗位库 + 推荐)  日期:2026-06-02
> 背景:A→B→C 联调(`run_a_b_c_smoke`)跑通后,针对推荐质量做的一批改进。
> 一句话:**接口没变,推荐展示更真实、缺口更干净、中文链路打通**。下游 C 无需任何适配。

---

## 1. 本轮改了什么(4 项)

### ① overlap 展示放宽,missing 仍按 core(不改排序)
`app/services/recommender.py` 精排中:
- `missing`(缺口,喂学习路径 + 进 `gap_penalty`)仍按 **core_skills(top5)** 算 —— 排序口径不变。
- `overlap`(展示"已掌握")放宽到 **required_skills(完整15项画像)** —— 不参与打分,故**不改变推荐顺序**,只让"已掌握技能"显示得更全。

效果:RAG 用户 overlap 从只有 `LLM` → `LLM, Python, LangChain, RAG`。

### ② A 模块 102 个中文别名并入词表
`pipelines/taxonomy/build_skill_vocab.py` 新增两个补充结构(不改动原手工条目,便于回滚):
- `ZH_ALIASES`:45 个中文别名挂到 B 已有条目(如 `机器学习→Machine Learning`、`检索增强生成→RAG`)。
- `A_MODULE_SKILLS`:53 个 B 原本没有的新条目(含 AI 产品 Coze/Qwen/AIGC、腾讯云、GIS/IoT、CNN/RNN、命名实体识别等;**已剔除"产品管理/项目管理"两个非技术管理类**)。

词表规模 223 → **275**,重建**零冲突**。中文实测:机器学习→Machine Learning、智能体→AI Agent、扣子→Coze、通义千问→Qwen 均正确归一化。

> 说明:中文别名只影响"用户简历端"归一化,岗位库是英文,**无需重新向量化**。

### ③ 清理噪声技能 "API"
孤立的 `API` 太泛、无区分度(任何后端岗都涉及),会造成假缺口。已:
- 从词表删除 `API` 条目(`REST API` / `API Design` / `OpenAI API` 等具体项保留)。
- 从 18 个岗位的 `core_skills` 中移除 `API`(`data/gold/fine_grained_roles_v1.json`)。

### ④ 新增技能覆盖关系(Spring Boot ⇒ Spring)
`recommender.py` 的 `_skill_gap` 加入 `SKILL_COVERAGE` 单向蕴含表:掌握更具体技能即视为覆盖更宽泛技能。当前只放确定项 `{"spring boot": ["spring"]}`,消除"有 Spring Boot 却被判缺 Spring"的假缺口。

效果:Java 后端用户 missing 从 `[Spring, API]` → **空**。

---

## 2. 对下游 C 的影响:无

`RecommendationItem` / `SkillGap`(`missing_skills` / `overlap_skills` / `optional_skills`)结构**完全未变**,只是 `missing_skills` 更干净。C 继续按原契约消费 `missing_skills` 生成学习路径即可。无缺口时(如 Java 后端),C 已能优雅返回兜底路径("项目实战"),正常。

---

## 3. 验证结果

**评估(18 用户评测集,GAMMA=0.02)—— 无倒退:**
Hit@1 = 0.889,Hit@5 = 1.000,MRR = 0.944,NDCG@5 = 0.836(与改动前基本持平,说明清理是"纯净化"而非以准确率换取)。

**smoke(A→B→C)关键改善:**
- RAG 用户:overlap `LLM` → `LLM/Python/LangChain/RAG`
- Java 后端:missing `[Spring, API]` → `[]`
- Data Analyst:overlap `Python` → `Python/SQL`(推荐仍偏 AI Data Engineer,见第 5 节 problem-1,本轮未动)

---

## 4. 运行方式

```bash
conda activate jobnavigator-it
docker compose -f infra/docker/docker-compose.yml up -d postgres   # 仅需 pgvector,勿构建 api/worker
python -m pipelines.taxonomy.build_skill_vocab                      # 重新生成词表
python -m pipelines.taxonomy.evaluate                              # 重跑评估
python -m pipelines.integration.run_a_b_c_smoke --limit 3 --top-k 3
```

---

## 5. 本轮**未**处理(仍挂起,不影响 C)

- **problem-1(排序偏置)**:Data Analyst 被推成 AI Data Engineer。主因是 `_trend_bonus` 对 AI 岗无脑加分 + 精排未用 `target_role` 对齐。待与组里一起改(动核心公式,需重跑评估)。
- **TODO-2 constraint_score**:仍固定 0.8。岗位库主源(Djinni 74%)无城市/薪资、唯一有薪资的 emerging 是美国 USD,数据撑不起 city/salary 约束。方向已调研(见 `reports/todo2_constraint_data_blocker.md`):城市/学历退出、薪资改用"CN 薪资参考表 + sigmoid 软约束",待组里定。

---

## 6. 改动文件清单

- `app/services/recommender.py` —— overlap 放宽 + `SKILL_COVERAGE` 覆盖关系
- `pipelines/taxonomy/build_skill_vocab.py` —— `ZH_ALIASES` + `A_MODULE_SKILLS`,删 `API`
- `data/gold/skill_vocab.json` —— 重新生成产物(275 技能)
- `data/gold/fine_grained_roles_v1.json` —— 18 个岗位 core_skills 移除 `API`
