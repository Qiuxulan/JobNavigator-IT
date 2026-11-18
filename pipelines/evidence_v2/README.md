# evidence_v2：岗位级月度证据采集

替代旧 GDELT GKG 证据层（GKG 元数据无有效事件时间、岗位相关性差）。
调研后数据源组合（2026-10-17 实测）：Google News RSS + layoffs.fyi + SEC EDGAR。
**不使用 GDELT**（本机 DOC API 被限流 429）。

## 用法

```bash
/var/lib/jobnav-env/bin/python -m pipelines.evidence_v2.collect [--months 6] [--roles all]
# --roles 支持 role_id 逗号列表，只限制本轮采集；summary/QC 始终覆盖全部岗位
```

幂等：按月分片（`{role_id}/{YYYY-MM}.jsonl`）、按 evidence_id（google news url
sha1[:12]）去重合并，可重复跑；重跑会重试未解码的 URL。

## 数据源与逻辑

1. **Google News RSS（主力）**：每岗位 canonical_role + aliases 前 2 个，每月一查询。
   当前月 `when:30d`；历史月 `after:YYYY-MM-01 before:下月01`（实测可用）。
   查询三级降级（0 结果才降级，共用同一相关性过滤）：整短语引号 → 无引号 AND
   → 无引号核心词（去 Frontend/Backend/Cloud 等方向修饰词，长岗位名 AND 过严）。
   限速 1s/请求，失败重试 2 次。
2. **跳转链接解码**：`news.google.com/rss/articles/CBMi...` 走 batchexecute RPC
   （先取页面 data-n-a-sg/ts，再三层嵌套 f.req POST garturlreq）。
   **必须 HTTP/2**（httpx[http2]，h2 包；HTTP/1.1 一律 400）。失败保留原始链接
   `url_resolved=False`，不编造。每 (role, month) 最多解码 top 12 条。
3. **layoffs.fyi**：年度总量用本地
   `/data/shichaojian/JNIT/raw/events/layoffs_fyi_annual_stats.json`；
   明细用 GitHub 镜像 `codeload github frankwang0909/tech-layoff-tracker`
   （官网 Airtable 不直接抓；raw.githubusercontent 本机被墙），按月聚合
   （公司/日期/人数/AI 行业标记），缓存 24h。
4. **SEC EDGAR**：`efts.sec.gov/LATEST/search-index` 按月查 8-K
   "workforce reduction" 披露（UA 必须带邮箱），公司级市场信号。

## 相关性过滤（旧版失败点）

- 通过（两道闸门，其一）：
  1. 标题命中岗位锚词（canonical/alias 整短语词边界、复数兼容、`.NET`/`C++`
     等非单词字符边界已处理）**且**（IT 上下文词 或 岗位技能词 或 科技媒体来源）；
  2. （IT 上下文词 且 岗位技能词）共现。
  单有锚词不够——"food & drink product manager" 这类非 IT 岗位提及要剔除。
- 剔除：体育/娱乐/政治噪声域名与标题。
- 事件分类（关键词规则，优先级从高到低）：
  layoff > security_incident > policy > funding > hiring > ai_adoption >
  product_release > general。

## 输出

- `/data/shichaojian/JNIT/processed/evidence_v2/{role_id}/{YYYY-MM}.jsonl`
  每条：{evidence_id, role_id, title, url, url_resolved, google_news_url,
  source_name, published_at, month, event_type, relevance_score, query_used,
  anchor_hits, skill_hits}
- `/data/shichaojian/JNIT/processed/evidence_v2/_market/`：layoffs_fyi_detail.json、
  sec_edgar/{YYYY-MM}.json（市场级，不计入岗位条目）
- `data/gold/evidence_v2_summary.json`：API 层直读（months_covered / total_items /
  by_type / 每月 top3 by relevance）
- `data/gold/evidence_v2_qc.json`：总量、解码成功率、过滤前后、按类型分布、备注

## 测试

```bash
/var/lib/jobnav-env/bin/python -m pytest tests/unit/test_evidence_v2_collect.py -q
```
