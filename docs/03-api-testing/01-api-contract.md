# 接口契约（V1）

## 1. `POST /v1/profile/extract`

输入：

- `resume_text` 或 `resume_file`
- `github_url`
- `user_id`

输出：

- 标准化 `UserProfile`
- 核心字段：技能、目标岗位、经验、学历、城市

## 2. `POST /v1/jobs/recommend`

输入：

- `profile`
- `preference`
- `top_k`

输出：

- `items[]`（TopK 推荐）
- 每条包含：岗位信息、总分、分数分解、技能重合/缺口、解释文案

## 3. `POST /v1/paths/generate`

输入：

- `profile`
- `target_job_id`
- `candidate_skills`

输出：

- 路径步骤
- 每步技能、理由、资源、估算时长

## 4. `GET /v1/trends/{job_role}`

输出：

- 短期方向
- 长期方向
- 证据事件列表

## 5. `POST /v1/chat/decision`

当前状态：

- 预留接口
- 固定返回 `501`

后续接入 Agent 时，不改路径，只扩展行为。

