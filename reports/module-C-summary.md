# Module C Summary: 学习路径规划模型

## 核心目标

将 B 模块输出的**技能缺口列表**转化为可执行的**有序学习路径 + 资源推荐**，
作为"岗位推荐 → 能力补全"的落地中间层。

---

## 关键交付物

| 交付物 | 路径 | 说明 |
|--------|------|------|
| 技能先修图谱 | `data/gold/skill_prerequisite_v1.json` | 29个技能节点，38条有向边，DAG无环验证通过 |
| 学习资源库 | `data/gold/learning_resources_v1.json` | 326条资源（B站/Coursera/GitHub三源），29/29技能全覆盖 |
| 技能词表 | `data/gold/skill_vocab.json` | 138条别名映射，供 `skill_norm.py` 调用 |
| 路径规划服务 | `services/path_planner_v1.py` | 三策略路径生成 + DAG验证 + Embedding资源匹配 |
| Embedding训练 | `services/embedding_matcher.py` | TF-IDF + ST微调，MRR=0.457（+58.7% vs 零样本）|
| 对接层 | `app/services/path_planner.py` | 实现团队统一接口，调用 `skill_norm.py` |
| 图谱流水线 | `pipelines/graph/build_skill_graph.py` | DAG验证 + 词表校验 |
| 路径评估报告 | `reports/path_eval_v1.md` | 4案例 × 3策略 = 12条完整路径计划 |
| Embedding评估 | `reports/embedding_eval_summary.md` | P@1/P@3/R@3/MRR 四指标对比 |
| 预训练向量 | `models/resource_embeddings.npy` | 326条资源向量（线上推理直接加载）|
| TF-IDF模型 | `models/tfidf_matcher.pkl` | 双语技能文本 + 词表2060条 |

---

## 路径生成算法

### 三条候选路径策略

| 策略 | 原理 | 适用场景 |
|------|------|---------|
| `shortest` | 快速通道，跳过理论基础（FAST_TRACK_SKIP），按层级排序 | 有一定背景、追求速成 |
| `easy_first` | 贪心最小堆，始终从"可学技能"里选最简单的 | 零基础，循序渐进 |
| `full_cover` | 完整路径 + 扩展技能（ROLE_ENRICHMENT） | 追求系统性掌握 |

### 路径评分公式

```
Score = Coverage × (1 - 0.04 × max(0, steps - 5))
```

- Coverage：目标技能覆盖率（含用户已有技能）
- 步骤数惩罚：超过5步每步扣4%，上限0.5

### DAG 验证

采用 DFS 三色标记法（WHITE/GRAY/BLACK），验证结果：
- 29节点，38边，**PASS（无环路）**
- 根节点：sk_python_basic / sk_sql_basic / sk_git / sk_linux_basic / sk_math_basic

---

## Embedding 资源匹配模型

### 训练数据

| 项目 | 数值 |
|------|------|
| 正样本对 | 397 对（来自 learning_resources_v1.json 手工标注）|
| 训练集 | 304 条（80%，按技能维度划分）|
| 验证集 | 93 条（20%）|
| 基础模型 | `paraphrase-multilingual-MiniLM-L12-v2`（中英文多语言）|
| 损失函数 | `MultipleNegativesRankingLoss`（batch=32，隐含31个负例/样本）|
| 训练轮次 | 3 epochs |

### 评估指标对比

| 模型 | P@1 | P@3 | R@3 | MRR |
|------|-----|-----|-----|-----|
| 关键词规则（基准） | 0.138 | 0.241 | 0.432 | 0.382 |
| TF-IDF 双语 | 0.276 | 0.195 | 0.323 | 0.401 |
| ST 零样本 | 0.103 | 0.172 | 0.289 | 0.288 |
| **ST 微调（最优）** | **0.241** | **0.230** | **0.401** | **0.457** |

MRR 相比零样本提升 **+58.7%**，相比关键词规则提升 **+19.6%**。

> 模型权重（model.safetensors，449MB）体积过大未提交 Git。
> 复现方式：`cd JobNavigator-IT && python services/embedding_matcher.py`（约5分钟）

---

## 关键集成点

### 上游（B 模块）

```python
# B 输出的 SkillGap.missing_skills 直接作为 candidate_skills 传入 C
path = PathPlannerService.generate(
    profile          = profile,           # A模块输出
    target_job_id    = job.job_id,        # B模块推荐岗位
    candidate_skills = skill_gap.missing_skills,  # B模块技能缺口
)
```

- **技能格式**：纯字符串（如 `"LangChain"`, `"RAG"`），由 `skill_norm.normalize_skill_id()` 归一化
- **词表统一**：`data/gold/skill_vocab.json` 是唯一数据源，`skill_norm.py` 加载该文件

### 下游（D 模块）

C 返回的 `LearningPath` 包含：
- `steps[].skill`：技能名称
- `steps[].resources`：带 URL 的学习资源列表
- `score`：路径综合评分（可作为 D 模块趋势融合的输入）
- `total_estimated_hours`：总学时（可用于学习成本惩罚项）

---

## 已知限制

1. **技能词表覆盖**：目前覆盖 29 类 IT 技能，138 条别名；新兴技能需手动更新 `skill_vocab.json`
2. **目标岗位映射**：仅支持 4 类粗粒度岗位，依赖 `target_job_id` 关键词匹配；待 B 模块提供精确映射接口后升级
3. **模型权重**：`st_finetuned/model.safetensors` 未提交（449MB），运行前需执行 `python services/embedding_matcher.py` 训练生成
4. **资源时效性**：学习资源链接基于 2026年初采集，部分 Coursera URL 为搜索链接，需定期更新

---

## 运行方式

```bash
# 1. 训练 Embedding 模型（首次运行必须）
python services/embedding_matcher.py

# 2. 生成图谱验证报告
python pipelines/graph/build_skill_graph.py

# 3. 生成四案例学习路径评估报告
python services/path_planner_v1.py

# 4. 运行单元测试
pytest tests/unit/test_services.py::test_path_generation -v

# 5. 端到端联通测试
python test_e2e.py
```
