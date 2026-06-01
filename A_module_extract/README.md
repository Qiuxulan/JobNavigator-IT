# A 模块：英文简历 / JD 技能抽取

本目录是 A 模块的完整交付包。它负责将英文简历、GitHub 风格文本和 JD 文本抽取为结构化数据，供推荐、学习路径和图谱模块使用。

## 当前交付物

- `data/silver/skillspan_skill_eval.jsonl`
- `data/silver/jd_skill_list_eval.jsonl`
- `data/silver/resume_it_english.jsonl`
- `data/silver/profile_labeled_v1.jsonl`
- `models/extractor_v1/`
- `reports/extractor_eval_v1.md`

下游模块可以继续读取：

- `data/processed/user_profiles.jsonl`
- `data/processed/structured_jobs.jsonl`

## 数据说明

- `skillspan_skill_eval.jsonl`：由公开数据集 `jjzha/skillspan` 生成的英文技能 span 评测数据。
- `jd_skill_list_eval.jsonl`：由公开英文 JD 数据生成，带 `required_skills`，用于弱标注训练。
- `resume_it_english.jsonl`：从公开英文简历中过滤得到的 IT 相关简历，用于真实文本演示和后续标注。
- `profile_labeled_v1.jsonl`：从 `batuhanmtl/job_resume_fit` 中筛选的 50 条 `INFORMATION-TECHNOLOGY` 英文简历，已脱敏，并使用数据集自带 `resume_skill_list` 作为技能弱标签。
- 中文模拟数据和未过滤英文简历原始副本已移除。

`profile_labeled_v1.jsonl` 不是人工逐条复核的 gold 集。上传前如需作为正式评测集，建议人工审核并修订其中的 `gold_skills`。

## 模型说明

最终模型为 `models/extractor_v1/`。它基于 `jjzha/jobbert_skill_extraction`，融合：

- SkillSpan 人工 BIO 标注：1000 条
- 新增 JD 弱标注：989 条
- 总训练样本：1989 条

本地模型不可用时，代码会尝试加载 Hugging Face 上的 `jjzha/jobbert_skill_extraction`；如果仍不可用，则继续使用规则抽取。

## 常用命令

启用本地模型增强：

```powershell
python A_module_extract\pipelines\extract\rule_extractor.py resume path\to\resume.txt --use-model
```

重新训练：

```powershell
$env:SSLKEYLOGFILE=$null
$env:HF_HUB_OFFLINE='1'
D:\anaconda3\envs\my_env\python.exe A_module_extract\pipelines\extract\train_extractor_v1.py `
  --base-model jjzha/jobbert_skill_extraction `
  --output-dir A_module_extract\models\extractor_v1 `
  --num-train-epochs 1 `
  --max-skillspan-train-samples 1000 `
  --max-jd-train-samples 1000 `
  --max-eval-samples 200 `
  --per-device-train-batch-size 4
```

## 限制

- 本地模型主要增强英文技能 span 抽取。
- 学历、工作年限、城市和目标岗位仍由规则抽取器负责。
- IT 简历当前没有人工 gold skill 标签，因此暂不直接参加监督训练。
