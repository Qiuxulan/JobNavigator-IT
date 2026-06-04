# 资源-技能 Embedding 匹配模型评估报告
生成：2026-06-01

## 训练数据
- 正样本配对：395 对（来自 learning_resources_v1.json）
- 训练集：303 条 | 验证集：92 条（80/20 按技能维度划分）
- 负样本：困难负采样（每技能4×）

## 模型对比
| 模型 | 类型 | P@1 | P@3 | R@3 | MRR |
|------|------|-----|-----|-----|-----|
| 关键词打分规则（基准） **[最优]** | 规则 | 0.276 | 0.241 | 0.386 | 0.454 |
| TF-IDF + 余弦相似度（双语） | ML模型 | 0.241 | 0.172 | 0.310 | 0.399 |
| sentence-transformers 零样本 | ML模型 | 0.172 | 0.195 | 0.316 | 0.316 |
| sentence-transformers 微调 ← 训练后 | ML模型 | 0.207 | 0.253 | 0.430 | 0.437 |

## 结论
**最优模型**：关键词打分规则（基准）（P@3 = 0.241）

## 模型文件
- `models/tfidf_matcher.pkl` — TF-IDF 向量化器 + 相似度矩阵
- `models/st_finetuned/`     — 微调后 sentence-transformers 模型
- `models/resource_embeddings.npy` — 资源向量（可直接加载用于线上推理）
- `models/skill_embeddings.npy`    — 技能向量