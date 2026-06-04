"""
pipelines/graph/eval_path_quality.py  —  C部分路径质量评估流水线
=================================================================
功能：对四个标准测试案例（4岗位 × 3策略）运行路径生成，
      输出 path_eval_v1.md 和 path_plans_sample.json。

运行方式：
  cd JobNavigator-IT
  python pipelines/graph/eval_path_quality.py

输出：
  reports/path_eval_v1.md        — 完整 Markdown 路径报告
  reports/path_plans_sample.json — 结构化 JSON 路径数据
  reports/dag_validation.json    — DAG 无环验证报告
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "services"))

if __name__ == "__main__":
    # 直接调用 path_planner_v1 的主程序逻辑
    import runpy
    runpy.run_module("path_planner_v1", run_name="__main__", alter_sys=True)
