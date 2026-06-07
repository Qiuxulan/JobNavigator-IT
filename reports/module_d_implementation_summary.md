# 模块 D 实现总结

## 1. 本轮工作的范围

本轮工作的核心是把职业推荐部分重构成一条完整的 D 模块链路：**简历输入 -> 技能抽取与标准化 -> Top10 岗位向量粗召回 -> 图谱精排 -> GraphSAGE 辅助路径搜索 -> 大模型报告生成**。  
其中，`job_roles.embedding` 只负责语义粗召回，图谱负责岗位技能缺口、技能先修关系、资源挂载、路径生成和最终精排，`GraphSAGE` 负责学习图结构 embedding，并把它用于 A* 搜索启发式和结构可达性奖励。

前面 A/B/C 模块没有被重做，只做了与 D 对接所必需的接入和复用：A 模块继续提供技能抽取入口，B 模块继续提供岗位库和岗位向量，C 模块继续提供技能先修图和学习资源库。也就是说，本轮的重点不是重建 A/B/C，而是把这些既有产物组织成 D 的可运行主链路。

---

## 2. 代码改动总览

### 2.1 抽取、推荐、路径与接口层

- `app/services/extractor.py`：把在线抽取链路统一成“微调模型优先 + 规则词表兜底 + 统一标准化”的行为，不再停留在 mock 级别；同时保证模型空输出时仍然能产出可用技能集合。
- `app/services/recommender.py`：把推荐链路从旧的启发式路径代价，改成复用 D 模块的粗召回与图谱精排结果，不再让旧的 `path_cost_score / trend_reward_score` 主导最终排序。
- `app/services/path_planner.py`：把它从“旧路径生成主逻辑”改成编排层，优先调用 D 模块的 `GraphPathPlannerV2`，只保留兼容性角色。
- `app/services/career_pathway_service.py`：新增 D 模块统一服务层，负责预检粗召回环境、执行 Top10 岗位向量召回、调用图谱精排与路径规划，是 `/v1/careers/report` 与后续职业接口的主入口。
- `app/services/career_catalog.py`：新增统一数据访问层，负责读取岗位库、技能图、资源库，并把岗位技能按 `skill_vocab.json` 映射到统一 `skill_id`，同时提供“每个岗位只取 Top30 技能”的核心逻辑。
- `app/services/graph_path_planner_v2.py`：新增 D 模块真正的图谱路径规划器，实现缺失技能集合的 A* 搜索、共享先修合并、学习路径生成、岗位分数计算以及 GraphSAGE 结构奖励。
- `app/services/report_generator.py`：新增大模型报告服务，把用户画像、粗召回、图谱精排和学习路径打包成结构化上下文，再调用 LLM 输出中文职业分析报告；后续还专门调整了 prompt，让报告不只是罗列字段，而是增加“为什么推荐、匹配强弱、技能重合度、路径风险与噪声技能”的分析。
- `app/api/routes.py`：新增 `/v1/careers/report`，把 D 模块整条链路暴露成一个端到端接口；同时保留原有 `/profile/extract`、`/jobs/recommend`、`/paths/generate` 的兼容结构。
- `app/schemas/api.py`：新增职业报告请求/响应 schema，补上 D 模块端到端接口的输入输出定义。
- `app/schemas/domain.py`：补齐了 D 链路中需要的领域对象结构，让岗位、技能缺口、学习路径、报告返回体能完整表达。
- `app/core/config.py`：新增 LLM 相关配置项，包括 `JOBNAV_LLM_BASE_URL`、`JOBNAV_LLM_API_KEY`、`JOBNAV_LLM_MODEL`、`JOBNAV_LLM_TIMEOUT_SEC`，用于驱动报告生成。

### 2.2 图谱、GraphSAGE 与样例脚本

- `pipelines/graph/build_career_graph_v2.py`：新增并确定为最终构图脚本。它只使用 `fine_grained_roles_v1.json`、`skill_prerequisite_v2.json`、`learning_resources_v1.json`、`skill_vocab.json` 四份核心产物构建三类节点（job/skill/resource）和三类边（`JOB_REQUIRES`、`SKILL_PREREQ`、`SKILL_HAS_RESOURCE`），并把每个岗位按 `skill_freq` 截成 Top30 技能入图。
- `pipelines/graph/train_graphsage_v2.py`：新增并确定为最终 GraphSAGE 训练脚本，从数据库直接读取 `graph_nodes.feature_vector` 与 `graph_edges` 训练轻量两层 GraphSAGE，导出本地模型文件，并把 embedding 写回数据库。
- `pipelines/graph/export_graph_interactive_v2.py`：新增并不断迭代为最终图谱可视化脚本，最后形成现在保留的 `reports/full_career_graph_v2.html`。这个脚本经历了多次 UI 调整：只显示全职业 + 全技能主图、每个岗位只显示 Top15 技能、节点缩小、默认极弱缓动、点击节点高亮邻居、整体配色改成橘红/灰/粉低饱和主题、边透明度显著降低。
- `pipelines/graph/run_sample_rankings_v2.py`：新增样例验证脚本，用于跑“抽取 -> 粗召回 -> 精排 -> 路径”链路，并且增加了 recall preflight，避免缺模型缓存或缺向量库时长时间卡住。
- `pipelines/extract/diagnose_extractor_v1.py`：新增抽取诊断脚本，用于区分“模型加载失败”“模型能跑但为空”“规则有命中但模型无命中”等情况，帮助排查微调模型行为。
- `pipelines/report/run_resource_rich_career_reports.py`：新增最终保留的 3 条高资源覆盖样例脚本，专门选择更靠近 `RAG / LLM Inference / Backend Python` 等资源覆盖相对较好的方向，便于得到更完整的路径资源和职业报告。

### 2.3 数据库、依赖与测试

- `infra/db/migrations/002_graph_d.sql`：补充 D 模块图谱表与相关结构，为图节点和图边入库提供数据库支持。
- `infra/db/migrations/003_graph_d_v2.sql`：补充 v2 图谱与 GraphSAGE 需要的字段和表结构，确保最终版本的构图与 embedding 回写可落库。
- `requirements.txt`、`environment.yml`：补充 D 模块新依赖，确保图谱构建、GraphSAGE、报告生成和测试脚本在本地/容器内可运行。
- `tests/unit/test_graph_pipeline.py`：新增 D 模块图谱构建层面的测试，验证构图 payload 与关键约束。
- `tests/unit/test_sample_rankings_v2.py`：新增 D 模块样例链路测试，验证 `run_sample_rankings_v2` 的预检和输出。
- `tests/unit/test_services.py`：补充报告生成和 D 服务的单测覆盖。
- `tests/integration/test_api_contract.py`：补充 `/v1/careers/report` 等接口契约测试。

---

## 3. 图谱是怎么构建的

最终图谱只依赖四份核心数据：岗位主数据 `data/gold/fine_grained_roles_v1.json`、技能先修图 `data/gold/skill_prerequisite_v2.json`、学习资源库 `data/gold/learning_resources_v1.json`、技能别名字典 `data/gold/skill_vocab.json`。  
构图脚本 `pipelines/graph/build_career_graph_v2.py` 会先把所有岗位技能、用户技能、先修技能、资源技能统一映射到同一套 `skill_id` 空间，再构建三类节点：岗位节点、技能节点、资源节点。

岗位节点的核心来源是 `fine_grained_roles_v1.json`。这里没有单独的技能打分字段，所以最终采用 `skill_freq` 作为岗位-技能重要度，并且每个岗位只保留 Top30 技能入图。构图时把 `importance_score`、`rank`、`is_core` 写到 `JOB_REQUIRES` 边上，这样后续路径搜索不只是知道“缺了什么技能”，还能知道“缺的技能对岗位有多重要”。

技能节点来自 `skill_prerequisite_v2.json`。这里保留了 `level`、`difficulty`、`hours_estimate` 等信息，并把 prerequisites 构造成 `SKILL_PREREQ` 边，因此图谱不只是一个岗位-技能二部图，而是把技能之间的学习顺序也编码了进去。

资源节点来自 `learning_resources_v1.json`。资源以 `skill -> resource` 的形式挂到 `SKILL_HAS_RESOURCE` 边上，所以图里每个技能理论上都可以附带若干课程、教程或 GitHub 资源。

本轮实际落库结果是：`69` 个岗位节点、`275` 个技能节点、`385` 个资源节点，总计 `729` 个节点；边方面有 `1967` 条 `JOB_REQUIRES`、`331` 条 `SKILL_PREREQ` 和 `461` 条 `SKILL_HAS_RESOURCE`，总计 `2759` 条边。构图摘要输出在 `reports/graph_build_summary_v2.json`。

---

## 4. GraphSAGE 是怎么训练和使用的

训练脚本是 `pipelines/graph/train_graphsage_v2.py`。它直接从数据库读取 `graph_nodes.feature_vector` 和 `graph_edges`，不再依赖早期那种单独物化特征的中间脚本。训练使用的关系只有三类：`SKILL_PREREQ`、`JOB_REQUIRES`、`SKILL_HAS_RESOURCE`，目标是让图中的真实邻接关系在 embedding 空间里被重建出来，同时通过 `job-skill` 的结构拉近约束，让岗位与其关键技能在向量空间中更接近。

最终训练的是一个轻量两层 GraphSAGE。训练完成后会输出：

- `models/graphsage_v2/model.pt`
- `models/graphsage_v2/embeddings.npy`
- `models/graphsage_v2/node_index.json`
- `reports/graphsage_metrics_v2.json`

同时 embedding 会写回数据库 `graphsage_embeddings` 与 `graph_nodes.embedding_vector`。本轮写回条数与节点数一致，共 `729` 条。

在在线推理阶段，GraphSAGE 不参与岗位粗召回，它只服务于 D 模块图搜索：一方面用于 A* 的启发式距离估计，另一方面用于岗位精排中的 `graph_reward`，即“当前用户到目标岗位关键技能集合在图结构上的可达性奖励”。

---

## 5. 学习路径是怎么生成的

学习路径的实现位于 `app/services/graph_path_planner_v2.py`。流程不是直接对岗位做搜索，而是先针对某个候选岗位取出它的 Top30 关键技能，再把这些技能和用户当前技能集合做差，得到缺失技能集合。之后对每个缺失技能在 `SKILL_PREREQ` 图上执行 A* 搜索，找出满足先修约束的最短可行补齐路径。

为了避免重复学习，多个缺失技能的路径会被合并，共享先修技能只保留一份；随后再对合并后的技能集合做拓扑排序，得到最终学习顺序。每个步骤都会尽量从 `learning_resources_v1.json` 里挂上最多 3 个资源，形成可执行的学习路径。

岗位最终分数由以下因素共同组成：语义粗召回分、已覆盖关键技能的重要度比例、资源奖励、GraphSAGE 结构奖励、缺失技能惩罚、先修难度惩罚、总学时惩罚。也就是说，D 模块不只回答“像哪个岗位”，还回答“转过去要补什么、难不难、路径是否有资源可学”。

---

## 6. 报告生成链路

`app/services/report_generator.py` 把职业推荐结果进一步包装成适合最终展示的报告。它会把用户画像、Top10 粗召回、图谱精排后的候选岗位、Top1 的技能重合与缺失分析、学习路径及其资源情况整理成上下文，再通过 `/v1/careers/report` 调用大模型输出中文职业策略报告。

这一部分后续做了专门修改：报告不再只是字段堆砌，而是明确要求模型解释“为什么粗召回像这些岗位”“为什么 Top1 比其他岗位更合适”“重合技能说明了什么”“缺失技能的难度和转岗成本如何”“路径里哪些步骤是基础、哪些是角色关键、哪些可能是噪声”。这一步是为了让输出更像分析报告，而不是纯表格转述。

---

## 7. 本轮样例验证结果

本轮最终保留的不是早期那 10 条样例，而是 3 条更贴近当前资源库覆盖方向的样例，运行脚本为 `pipelines/report/run_resource_rich_career_reports.py`，结果文件保存在：

- `reports/resource_rich_career_reports_api_output.json`
- `reports/resource_rich_career_reports_summary.md`

这三条样例分别偏向 `RAG / Agent`、`LLM Inference`、`Backend Python` 三种方向，目的是让路径中有更多技能能挂到已有学习资源。最终结果是：

- `resource_rich_rag`：Top1 为 `AI Agent Engineer`，路径 24 步，其中 10 步带资源；
- `resource_rich_llm_inference`：Top1 为 `LLM Inference Engineer`，路径 21 步，其中 6 步带资源；
- `resource_rich_backend_python`：Top1 为 `Backend Python Engineer`，路径 18 步，其中 5 步带资源。

这说明图谱、GraphSAGE、路径生成、报告接口都已经跑通，但同时也暴露出资源覆盖并不完整。

---

## 8. 本轮发现的问题

当前最明显的问题有两个。第一个是**资源覆盖不足**：很多岗位虽然能成功生成学习路径，但路径中的很多技能在 `learning_resources_v1.json` 里并没有对应资源，所以会出现部分步骤 `resources=[]`。这不是路径失败，而是资源库本身覆盖还不够。

第二个是**岗位技能画像噪声**。最典型的例子是 `RAG Engineer` 路径里出现了 `C`、`Java`。这个问题已经定位到数据和排序层：它们直接来自 `fine_grained_roles_v1.json` 的 `skill_freq`，又被 `role_top_skills()` 机械地选进岗位 Top30，且本身没有 prerequisites、`level` 又低，所以在最终路径排序中被排到前面。换句话说，这个问题的根因是岗位技能画像质量，而不是 GraphSAGE 或 A* 算法本身。

此外，当前图谱虽然已经有效，但复杂度还没有高到“没有图谱就完全做不出来”的程度。它本质上仍然更接近“岗位技能缺口 + 技能先修图 + GraphSAGE 辅助”的系统，而不是高度复杂的职业知识图谱推理系统。这一点在后续如果要继续提升 D 模块时，需要继续补岗位迁移关系、技能替代关系和用户行为边。

---

## 9. 当前保留的核心产物

当前 D 模块最终保留的核心代码和产物如下：

- `app/services/extractor.py`
- `app/services/career_catalog.py`
- `app/services/career_pathway_service.py`
- `app/services/graph_path_planner_v2.py`
- `app/services/report_generator.py`
- `pipelines/graph/build_career_graph_v2.py`
- `pipelines/graph/train_graphsage_v2.py`
- `pipelines/graph/export_graph_interactive_v2.py`
- `pipelines/graph/run_sample_rankings_v2.py`
- `pipelines/extract/diagnose_extractor_v1.py`
- `pipelines/report/run_resource_rich_career_reports.py`
- `models/graphsage_v2/model.pt`
- `models/graphsage_v2/embeddings.npy`
- `models/graphsage_v2/node_index.json`
- `reports/graph_build_summary_v2.json`
- `reports/graphsage_metrics_v2.json`
- `reports/full_career_graph_v2.html`
- `reports/resource_rich_career_reports_api_output.json`
- `reports/resource_rich_career_reports_summary.md`

与之对应，已经删掉的旧版 D 文件主要包括早期 `graph_path_planner`、早期构图脚本、早期 GraphSAGE 脚本、Mermaid 静态图导出脚本以及旧的 10 条样例报告脚本，目的是把目录收敛到当前唯一有效的 `v2` 主链路。

---

## 10. 结论

本轮已经把模块 D 从“一个设想”推进成了一套完整可运行的系统：简历可以被抽取为技能，技能可以进入统一 `skill_id` 空间，岗位可以通过 `JobBERT-v3 + pgvector` 做粗召回，图谱可以基于岗位技能重要度、技能先修关系和学习资源进行精排与路径生成，GraphSAGE 可以为图搜索提供结构表示，而最终结果还可以进一步通过大模型生成职业分析报告。

现阶段这套系统已经具备可运行、可解释、可视化、可演示的职业推荐与学习路径能力。后续如果继续迭代，优先级最高的方向会是：清洗岗位技能画像、补资源覆盖、提高路径排序的岗位相关性，以及让报告更进一步减少模板感、增强分析性。
