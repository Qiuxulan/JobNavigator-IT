"""evidence_v2：岗位级月度证据采集。

替代旧 GDELT GKG 证据层（GKG 元数据拿不到有效事件时间，且证据与岗位相关性差）。
数据源组合（已实测）：
- Google News RSS（主力，岗位级，按月分片）
- layoffs.fyi 年度统计（本地）+ GitHub 技术裁员明细镜像（codeload zip）
- SEC EDGAR 全文检索（8-K "workforce reduction" 披露，市场级）

入口：``python -m pipelines.evidence_v2.collect [--months 6] [--roles all]``
"""
