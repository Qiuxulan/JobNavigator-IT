# A 模块英文技能抽取评测报告

## 目标

A 模块负责把英文简历、GitHub 风格文本和 JD 文本抽取为统一结构化数据。当前版本以规则抽取作为稳定兜底，并使用本地 JobBERT 模型增强英文技能 span 抽取。

## 数据来源

| 数据文件 | 来源 | 数量 | 用途 |
| --- | --- | ---: | --- |
| `skillspan_skill_eval.jsonl` | `jjzha/skillspan` | 170 条含技能 span 样本 | 英文技能评测 |
| `jd_skill_list_eval.jsonl` | `keerthanshetty/resume-skill-extractor-dataset` | 3050 条 | JD 技能列表评测与弱标注训练 |
| `resume_it_english.jsonl` | `yashpwr/resume-ner-training-data` 过滤结果 | 2867 条 | IT 简历抽取演示与后续标注 |
| `profile_labeled_v1.jsonl` | `batuhanmtl/job_resume_fit` 的 `INFORMATION-TECHNOLOGY` 类别 | 50 条 | 脱敏英文 IT 简历技能弱标注集 |

未过滤英文简历原始副本和中文模拟样本已从交付目录移除。

`profile_labeled_v1.jsonl` 使用数据集自带 `resume_skill_list` 作为弱标签，尚未经过人工逐条复核。Hugging Face 数据集页面更新时间为 2025 年 11 月 14 日，但这不代表其中每份简历文本都写于 2025 年。

## extractor_v1 训练结果

最终仅保留一个本地模型：

```text
models/extractor_v1/
```

训练环境：

- Python：`D:\anaconda3\envs\my_env\python.exe`
- 设备：CPU
- 原始基础模型：`jjzha/jobbert_skill_extraction`
- SkillSpan 人工 BIO 标注：1000 条
- 新增 JD 弱标注：989 条
- 总训练样本：1989 条
- SkillSpan validation：200 条
- epoch：1
- batch size：4

评估结果：

| 指标 | 结果 |
| --- | ---: |
| eval loss | 0.3697 |
| token accuracy | 0.9060 |
| skill-token accuracy | 0.5892 |

## 加载顺序

模型增强启用后，加载顺序如下：

1. `models/extractor_v1/`
2. Hugging Face `jjzha/jobbert_skill_extraction`
3. 模型不可用时继续使用规则抽取，不让在线 API 失败

## 规则版历史回归

| 数据集 | 样本数 | 技能 Precision | 技能 Recall | 技能 F1 |
| --- | ---: | ---: | ---: | ---: |
| JD seed gold | 8 | 0.9701 | 1.0000 | 0.9848 |
| Resume seed gold | 6 | 0.9464 | 1.0000 | 0.9725 |

## 新增 IT 简历弱标注集基线

规则抽取器在 `profile_labeled_v1.jsonl` 上的首次基线：

| 数据集 | 样本数 | 技能 Precision | 技能 Recall | 技能 F1 |
| --- | ---: | ---: | ---: | ---: |
| IT profile weak labels | 50 | 0.5629 | 0.0755 | 0.1331 |

该结果表明，当前规则词表对传统 IT 运维、网络和企业软件技能覆盖不足。后续可人工审核弱标签，并按高频遗漏项扩充技能词表。

## 已知限制

- JD 弱标注由 `required_skills` 与 JD 文本匹配生成，不等价于完整人工 BIO 标注。
- `resume_it_english.jsonl` 暂时不参加监督训练，因为它没有人工 gold skill 标签。
- 学历、工作年限、城市等字段仍主要依赖规则抽取。
