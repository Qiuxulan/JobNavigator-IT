# A 模块：简历 / JD 文本抽取

这个目录是 A 模块的核心抽取流水线，用来把简历、GitHub 风格文本和招聘 JD 文本转换成结构化数据，供后续的岗位推荐、学习路径规划和职业图谱融合模块使用。

## 运行评测

```bash
python pipelines/extract/eval_extractor.py --gold pipelines/extract/eval/jd_gold.jsonl --mode jd
python pipelines/extract/eval_extractor.py --gold pipelines/extract/eval/resume_gold.jsonl --mode resume
python pipelines/extract/eval_extractor.py --gold data/silver/profile_labeled_v1.jsonl --mode resume
```

## 命令行抽取

```bash
python pipelines/extract/rule_extractor.py resume path/to/resume.txt --out data/processed/user_profile_demo.json
python pipelines/extract/rule_extractor.py jd path/to/jd.txt --out data/processed/structured_job_demo.json
python pipelines/extract/rule_extractor.py resume path/to/resume.txt --use-model
```

说明：

- `resume` 表示输入是简历或 GitHub 风格个人文本。
- `jd` 表示输入是招聘 JD 文本。
- `--out` 指定输出 JSON 文件路径。
- `--use-model` 会启用可选的 JobBERT 技能抽取模型 `jjzha/jobbert_skill_extraction`。
- 如果本地没有安装模型依赖，或模型暂时无法下载，程序会自动回退到规则版抽取，不会中断。

## 处理 SkillSpan 数据集

```bash
python pipelines/extract/prepare_skillspan.py --out data/processed/skillspan_skills.json --eval-out data/silver/skillspan_skill_eval.jsonl
```

这个脚本会读取 Hugging Face 数据集 `jjzha/skillspan`，根据 `tokens` 和 `tags_skill` 的 BIO 标签还原技能短语，并输出：

- `data/processed/skillspan_skills.json`：SkillSpan 高频技能候选。
- `data/silver/skillspan_skill_eval.jsonl`：可用于后续评测的 JSONL 样本。

注意：这一步需要安装 `datasets`，并且需要能访问 Hugging Face 或已有本地缓存。

## 在 API 中启用 JobBERT

```bash
set JNIT_ENABLE_JOBBERT=1
```

默认情况下，在线 API 仍然只使用规则版抽取，保证演示稳定。设置 `JNIT_ENABLE_JOBBERT=1` 后，`ExtractorService` 会尝试启用 JobBERT 技能抽取增强。

API 输出结构不变，仍然返回统一的 `UserProfile`：

- `user_id`
- `skills`
- `target_role`
- `years_experience`
- `education`
- `city`
- `github_url`

## 下游交付文件

- `data/processed/user_profiles.jsonl`
- `data/processed/structured_jobs.jsonl`
- `data/processed/skill_vocab.json`
- `data/processed/skill_alias_map.json`
- `data/processed/skillspan_skills.json`
- `data/silver/skillspan_skill_eval.jsonl`
- `reports/extractor_eval_v1.md`

## 当前版本说明

V1 版本以规则抽取为主，优先保证输出字段稳定、可评测、能被 B/C/D 模块直接使用。JobBERT 和 SkillSpan 是可选增强：JobBERT 用于补充英文技能 span，SkillSpan 用于扩充英文技能候选和后续评测数据。
