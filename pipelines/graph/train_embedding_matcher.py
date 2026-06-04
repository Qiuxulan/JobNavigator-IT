"""
pipelines/graph/train_embedding_matcher.py  —  C部分 Embedding 模型训练入口
============================================================================
功能：训练资源-技能匹配 Embedding 模型，输出评估报告和向量文件。

三级模型：
  L1  TF-IDF + 余弦相似度（双语技能文本，跨语言对齐）
  L2  sentence-transformers 零样本
  L3  sentence-transformers 微调（MultipleNegativesRankingLoss）

运行方式：
  cd JobNavigator-IT
  python pipelines/graph/train_embedding_matcher.py

输出：
  models/tfidf_matcher.pkl          — TF-IDF 模型
  models/st_finetuned/              — 微调后模型（config + 权重）
  models/resource_embeddings.npy    — 资源向量矩阵（线上推理直接加载）
  models/skill_embeddings.npy       — 技能向量矩阵
  reports/embedding_eval.json       — 评估指标 JSON
  reports/embedding_eval_summary.md — 可读评估报告

预计运行时间：约 5 分钟（CPU），含模型下载约 10 分钟（首次）
"""
import sys
from pathlib import Path

# 将 services/ 加入路径
sys.path.insert(0, str(Path(__file__).parents[2] / "services"))

if __name__ == "__main__":
    from embedding_matcher import main
    main()
