import { useEffect, useMemo, useRef, useState } from "react";
import { getNews, getNewsCategories, getNewsSources } from "../api";
import type { NewsItem, NewsResponse, NewsSourceInfo } from "../api";
import { Ic } from "../components/Icons";
import PageHead from "../components/PageHead";

const CATEGORY_ZH: Record<string, string> = {
  hiring: "招聘信息",
  layoff: "裁员动态",
  funding: "融资",
  product_release: "产品发布",
  research: "研究进展",
  policy: "政策监管",
  security: "安全事件",
  tech_general: "技术综合",
};

const CATEGORY_ORDER = Object.keys(CATEGORY_ZH);

const CATEGORY_COLOR: Record<string, string> = {
  hiring: "#10b981",
  layoff: "#fb5566",
  funding: "#d9a13b",
  product_release: "#5B8DEF",
  research: "#a897bb",
  policy: "#c26a1b",
  security: "#e05299",
  tech_general: "#8a919c",
};

function skillLabel(id: string): string {
  return id
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function relativeTime(iso: string | null | undefined, now: number): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = Math.max(0, now - t);
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return new Date(t).toLocaleDateString("zh-CN");
}

function excerpt(item: NewsItem): string {
  const raw = item.content_text;
  const text = raw && !raw.startsWith("点击查看原文") ? raw : (item.summary ?? "");
  const clean = (text || "").replace(/\s+/g, " ").trim();
  return clean.length > 200 ? clean.slice(0, 200) + "…" : clean;
}

function hexA(hex: string, alpha: string): string {
  return hex.length === 7 ? `${hex}${alpha}` : hex;
}

function pageNumbers(page: number, pages: number): number[] {
  const set = new Set<number>([0, pages - 1, page - 1, page, page + 1]);
  return Array.from(set).filter((i) => i >= 0 && i < pages).sort((a, b) => a - b);
}

export default function News() {
  const [data, setData] = useState<NewsResponse | null>(null);
  const [catStats, setCatStats] = useState<Record<string, number>>({});
  const [sources, setSources] = useState<NewsSourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [category, setCategory] = useState("");
  const [lang, setLang] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [srcOpen, setSrcOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const pageSize = 15;

  // 搜索防抖 300ms
  useEffect(() => {
    const t = window.setTimeout(() => setQDebounced(q.trim()), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  // 相对时间每 30s 刷新
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    let alive = true;
    getNewsCategories().then((s) => { if (alive) setCatStats(s.categories ?? {}); }).catch(() => {});
    getNewsSources().then((list) => { if (alive) setSources(list); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    const doFetch = async () => {
      try {
        let res: NewsResponse;
        if (selectedSources.length <= 1) {
          res = await getNews({
            page,
            pageSize,
            category: category || undefined,
            lang: lang || undefined,
            source: selectedSources[0],
            q: qDebounced || undefined,
          });
        } else {
          // 后端 source 仅支持精确单值：多选时逐源取回累计条数，按发布时间合并后本地分页
          const fetched = await Promise.all(
            selectedSources.map((s) =>
              getNews({
                page: 1,
                pageSize: page * pageSize,
                category: category || undefined,
                lang: lang || undefined,
                source: s,
                q: qDebounced || undefined,
              }),
            ),
          );
          const merged = fetched
            .flatMap((r) => r.items)
            .sort((a, b) => new Date(b.published_at).getTime() - new Date(a.published_at).getTime());
          res = {
            items: merged.slice((page - 1) * pageSize, page * pageSize),
            total: fetched.reduce((sum, r) => sum + r.total, 0),
            page,
            page_size: pageSize,
            freshness: fetched[0]?.freshness,
          };
        }
        if (alive) setData(res);
      } catch {
        if (alive) { setError(true); setData(null); }
      } finally {
        if (alive) setLoading(false);
      }
    };
    void doFetch();
    return () => { alive = false; };
  }, [page, pageSize, category, lang, selectedSources, qDebounced]);

  // 任一过滤条件变化时回到第一页
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return; }
    setPage(1);
  }, [category, lang, selectedSources, qDebounced]);

  const totalCount = useMemo(
    () => Object.values(catStats).reduce((s, n) => s + n, 0),
    [catStats],
  );

  const freshness = data?.freshness;
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const items = data?.items ?? [];

  const toggleSource = (s: string) => {
    setSelectedSources((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const maxCat = Math.max(1, ...Object.values(catStats));

  return (
    <div className="page">
      <PageHead
        eyebrow="News / Industry Feed"
        title={<>行业<span className="lite">新闻</span></>}
        sub={`聚合招聘、裁员、融资、产品与技术社区动态，近 7 天 ${totalCount} 条更新，用于支撑趋势判断的事件证据。`}
        extra={
          <div className="news-fresh" title={freshness?.latest_published_at ?? ""}>
            <span className="news-pulse" />
            {freshness?.latest_published_at
              ? <>最新更新于 {relativeTime(freshness.latest_published_at, now)} · {freshness.sources_active ?? "—"} 个源活跃</>
              : "等待数据更新…"}
          </div>
        }
      />

      <div className="news-layout">
        <div className="news-main">
          <div className="news-filters">
            <div className="chips">
              <button className={"chip" + (category === "" ? " sel" : "")} onClick={() => setCategory("")}>
                全部<span className="chip-n num">{totalCount}</span>
              </button>
              {CATEGORY_ORDER.map((c) => {
                const color = CATEGORY_COLOR[c];
                const selected = category === c;
                return (
                  <button
                    key={c}
                    className={"chip news-chip-btn" + (selected ? " sel" : "")}
                    style={selected ? { background: hexA(color, "1f"), borderColor: hexA(color, "73"), color } : undefined}
                    onClick={() => setCategory(selected ? "" : c)}
                  >
                    <span className="dot-cat" style={{ background: color }} />
                    {CATEGORY_ZH[c]}
                    <span className="chip-n num">{catStats[c] ?? 0}</span>
                  </button>
                );
              })}
            </div>
            <div className="row wrap">
              <div className="seg">
                <button className={lang === "" ? "active" : ""} onClick={() => setLang("")}>全部</button>
                <button className={lang === "zh" ? "active" : ""} onClick={() => setLang("zh")}>中文</button>
                <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>英文</button>
              </div>
              <div className="news-src-dd">
                <button className={"btn sm" + (srcOpen ? " active-dd" : "")} onClick={() => setSrcOpen((v) => !v)}>
                  来源{selectedSources.length > 0 ? `（已选 ${selectedSources.length}）` : ""} <span className="dd-caret">▾</span>
                </button>
                {srcOpen && (
                  <>
                    <div className="dd-backdrop" onClick={() => setSrcOpen(false)} />
                    <div className="dd-panel">
                      {sources.map((s) => (
                        <label key={s.source} className="dd-item">
                          <input type="checkbox" checked={selectedSources.includes(s.source)} onChange={() => toggleSource(s.source)} />
                          <span className="dd-name">{s.source}</span>
                          <span className="dd-meta">{relativeTime(s.latest_published_at, now)}</span>
                        </label>
                      ))}
                      {selectedSources.length > 0 && (
                        <button className="dd-clear" onClick={() => setSelectedSources([])}>清除全部选择</button>
                      )}
                    </div>
                  </>
                )}
              </div>
              <div className="search" style={{ flex: 1, minWidth: 180 }}>
                <Ic.search />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索标题或内容..." />
              </div>
            </div>
          </div>

          {error && (
            <div className="error-box news-error">
              新闻加载失败，请确认后端服务已启动后
              <button className="btn sm" style={{ marginLeft: 10 }} onClick={() => window.location.reload()}>重新加载</button>
            </div>
          )}

          {!error && loading && (
            <div className="news-skel-list" aria-label="加载中">
              {[0, 1, 2, 3, 4].map((n) => (
                <div className="news-skel-card" key={n}>
                  <div className="skel" style={{ width: `${68 - (n % 3) * 12}%`, height: 17 }} />
                  <div className="skel" style={{ width: 190, height: 12 }} />
                  <div className="skel" style={{ width: "94%", height: 12 }} />
                  <div className="skel" style={{ width: `${72 - (n % 2) * 18}%`, height: 12 }} />
                </div>
              ))}
            </div>
          )}

          {!error && !loading && items.length === 0 && (
            <div className="cmp-empty">
              <Ic.news />
              <div>没有符合条件的新闻，试试放宽筛选条件。</div>
            </div>
          )}

          {!error && !loading && items.length > 0 && (
            <div className="news-list">
              {items.map((item) => {
                const cat = item.category ?? "";
                const text = excerpt(item);
                return (
                  <article className="news-card fade" key={item.news_id}>
                    <div className="news-card-top">
                      <a className="news-card-title" href={item.url} target="_blank" rel="noopener noreferrer">
                        {item.title}
                        <Ic.ext />
                      </a>
                    </div>
                    <div className="news-card-meta">
                      {cat && (
                        <span
                          className={"news-cat" + (cat === "layoff" ? " hot" : cat === "hiring" ? " pos" : "")}
                          style={cat === "hiring" || cat === "layoff" ? undefined : { color: CATEGORY_COLOR[cat] ?? "var(--ink-2)", background: "var(--card-3)", borderColor: "var(--line)" }}
                        >
                          {CATEGORY_ZH[cat] ?? cat}
                        </span>
                      )}
                      <span className="news-card-src">{item.source}</span>
                      <span className="news-card-time">{relativeTime(item.published_at, now)}</span>
                      {item.lang && <span className="news-lang">{item.lang === "zh" ? "中文" : item.lang === "en" ? "英文" : item.lang}</span>}
                    </div>
                    {text && <p className="news-card-text">{text}</p>}
                    {(item.skills?.length ?? 0) > 0 && (
                      <div className="news-skills">
                        {(item.skills ?? []).slice(0, 5).map((s) => (
                          <span key={s} className="news-skill">{skillLabel(s)}</span>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}

          {!error && data && (
            <div className="pager">
              <div className="pager-info">共 {data.total} 条 · 第 {page} / {pages} 页</div>
              <div className="pager-ctrl">
                <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
                {pageNumbers(page, pages).map((n, i, arr) => (
                  <span key={n} style={{ display: "contents" }}>
                    {i > 0 && arr[i - 1] < n - 1 && <span className="pager-btn" style={{ border: "none", background: "none", cursor: "default" }}>…</span>}
                    <button className={"pager-btn" + (n + 1 === page ? " active" : "")} onClick={() => setPage(n + 1)}>{n + 1}</button>
                  </span>
                ))}
                <button className="pager-btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>›</button>
              </div>
            </div>
          )}
        </div>

        <aside className="news-side">
          <div className="card">
            <div className="card-hd"><div className="card-title">近 7 天分类统计</div></div>
            <div className="card-bd">
              {CATEGORY_ORDER.filter((c) => (catStats[c] ?? 0) > 0).length === 0
                ? <div className="muted" style={{ fontSize: 13 }}>暂无统计数据</div>
                : (
                  <div className="catbar-list">
                    {CATEGORY_ORDER
                      .filter((c) => (catStats[c] ?? 0) > 0)
                      .sort((a, b) => (catStats[b] ?? 0) - (catStats[a] ?? 0))
                      .map((c) => (
                        <div className="catbar news-catbar" key={c} onClick={() => { setCategory(category === c ? "" : c); window.scrollTo({ top: 0 }); }}>
                          <div className="catbar-name"><span className="dot-cat" style={{ background: CATEGORY_COLOR[c] }} />{CATEGORY_ZH[c]}</div>
                          <div className="catbar-track"><div className="catbar-fill" style={{ width: `${Math.max(3, (catStats[c] / maxCat) * 100)}%`, background: CATEGORY_COLOR[c] }} /></div>
                          <div className="catbar-val">{catStats[c]}</div>
                        </div>
                      ))}
                  </div>
                )}
            </div>
          </div>

          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">源活跃列表</div>
                <div className="card-desc">近 7 天抓取来源与最新条目</div>
              </div>
            </div>
            <div className="card-bd news-src-list">
              {sources.length === 0
                ? <div className="muted" style={{ fontSize: 13 }}>暂无来源数据</div>
                : sources.map((s) => (
                  <div className="news-src-row" key={s.source}>
                    <span className="dot-cat" style={{ background: "#8fb094" }} />
                    <span className="news-src-name">{s.source}</span>
                    <span className="news-src-time">{relativeTime(s.latest_published_at, now)}</span>
                    <span className="news-src-count num">{s.count}</span>
                  </div>
                ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
