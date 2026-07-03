# 技能抽取流水线

`pipelines/extract` 负责把简历、GitHub 风格文本和 JD 文本转换为结构化技能信息，并为 `app.services.extractor.ExtractorService` 提供训练、评估和诊断能力。

## 当前运行策略

- API 主入口是 `ExtractorService`。
- 服务默认尝试加载本地微调权重 `models/extractor_v1`。
- 模型加载失败、推理报错或输出为空时，规则抽取结果继续生效。
- 输出结构保持 `UserProfile`，下游推荐、图谱精排和学习路径均使用同一结构。

## 主要脚本

| 脚本 | 作用 |
|---|---|
| `rule_extractor.py` | 规则版简历/JD 技能抽取，可用于快速调试 |
| `model_extractor.py` | JobBERT 技能抽取封装 |
| `train_extractor_v1.py` | 使用弱监督 JD 与 SkillSpan 数据继续训练抽取模型 |
| `eval_extractor.py` | 在 JD、简历或银标数据上评估抽取效果 |
| `diagnose_extractor_v1.py` | 区分模型加载失败、模型空输出、规则兜底等情况 |
| `prepare_skillspan.py` | 从 SkillSpan BIO 标注恢复技能短语并生成评估样本 |
| `prepare_profile_labeled_v1.py` | 构建简历侧弱标注样本 |
| `prepare_english_supplement.py` | 构建英文补充样本 |
| `filter_it_resumes.py` | 从简历数据中过滤 IT 相关样本 |

## 常用命令

诊断当前模型与规则兜底：

```powershell
python -m pipelines.extract.diagnose_extractor_v1
```

评估抽取效果：

```powershell
python pipelines/extract/eval_extractor.py --gold data/silver/profile_labeled_v1.jsonl --mode resume
python pipelines/extract/eval_extractor.py --gold data/silver/jd_skill_list_eval.jsonl --mode jd
python pipelines/extract/eval_extractor.py --gold data/silver/skillspan_skill_eval.jsonl --mode jd
```

命令行抽取单个文本：

```powershell
python pipelines/extract/rule_extractor.py resume path/to/resume.txt --out data/processed/user_profile_demo.json
python pipelines/extract/rule_extractor.py jd path/to/jd.txt --out data/processed/structured_job_demo.json
```

`data/processed/` 主要用于本地临时调试输出，当前主链路不依赖其中的历史文件。

## 当前保留数据

- `data/silver/profile_labeled_v1.jsonl`：简历弱标注数据。
- `data/silver/jd_skill_list_eval.jsonl`：JD 技能评估数据。
- `data/silver/skillspan_skill_eval.jsonl`：SkillSpan BIO 恢复后的评估样本。
- `data/silver/resume_it_english.jsonl`：英文 IT 简历补充样本。
- `models/extractor_v1/`：当前 API 默认尝试加载的本地微调权重。
- `reports/eval/job_extractor_eval_v1.md`：抽取评估报告。

