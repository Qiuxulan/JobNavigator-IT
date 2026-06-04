# extractor_v1

本目录是 A 模块最终交付的英文技能抽取模型。

## 训练信息

- 原始基础模型：`jjzha/jobbert_skill_extraction`
- 人工标注数据：`jjzha/skillspan`
- SkillSpan 训练样本：1000 条
- JD 弱标注训练样本：989 条
- 总训练样本：1989 条
- 评估样本：200 条
- epoch：1
- batch size：4

## 评估结果

```json
{
  "eval_loss": 0.3697350323200226,
  "eval_token_accuracy": 0.9059959349593496,
  "eval_skill_token_accuracy": 0.589242053789731,
  "epoch": 1.0
}
```

新增 JD 标签由 `required_skills` 与 JD 正文匹配后自动生成，属于弱标注。
