# 报告生成脚本

`pipelines/report` 只保留报告类脚本，不存放长期数据产物。当前唯一脚本用于调用后端职业报告接口，生成资源覆盖较完整的职业路径样例。

## 文件说明

| 文件 | 作用 |
|---|---|
| `run_resource_rich_career_reports.py` | 使用 3 组模拟简历调用 `/v1/careers/report`，检查 D 模块职业匹配、图谱精排、学习路径和 LLM 报告输出。 |

## 生成产物

脚本运行后会写入 `reports/summary/`：

| 产物 | 作用 |
|---|---|
| `job_resource_rich_career_reports_api_output.json` | 完整 API 原始响应，便于检查字段、TopK 岗位、学习路径步骤和资源挂载。 |
| `job_resource_rich_career_reports_summary.md` | 面向展示和报告整理的 Markdown 摘要。 |

这些产物属于职业部分 D 模块报告数据，不是行业趋势数据。
