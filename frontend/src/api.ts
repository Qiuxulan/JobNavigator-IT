// Works behind path-based port proxies (e.g. code-server /proxy/<port>/):
// prepend the detected proxy prefix so API calls stay under the same path.
const PROXY_PREFIX = window.location.pathname.match(/^(.+\/proxy\/\d+)/)?.[1] ?? "";
const API_BASE = `${PROXY_PREFIX}/api/v1`;

export const api = {
  async get<T>(path: string, options: { params?: Record<string, string | number | boolean | undefined> } = {}) {
    return request<T>(path, { method: "GET", params: options.params });
  },
  async post<T>(path: string, body?: unknown, options: { timeout?: number } = {}) {
    return request<T>(path, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
      timeout: options.timeout,
    });
  },
};

async function request<T>(
  path: string,
  options: RequestInit & { params?: Record<string, string | number | boolean | undefined>; timeout?: number } = {},
): Promise<{ data: T }> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(options.params || {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeout ?? 60_000);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Request failed: ${response.status}`);
    }
    return { data: (await response.json()) as T };
  } finally {
    window.clearTimeout(timeout);
  }
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function agentChat(messages: ChatMessage[]): Promise<string> {
  const { data } = await api.post<{ reply: string }>("/agent/chat", { messages }, { timeout: 180_000 });
  return data.reply;
}

export interface TrendEvidence {
  title?: string;
  source?: string;
  source_domain?: string;
  url?: string;
  event_date?: string;
  published_at?: string;
  impact_direction?: string;
  tone?: number | null;
  event_type?: string;
  retrieval_score?: number | null;
  match_weight?: number | null;
}

export interface MonthlyForecastRow {
  month?: string | null;
  is_history?: boolean;
  demand_index?: number | null;
  jd_share?: number | null;
  salary_mid?: number | null;
  low_confidence?: boolean;
  predicted_demand_index?: number | null;
  jd_share_pred?: number | null;
  salary_mid_pred?: number | null;
  lower80?: number | null;
  upper80?: number | null;
}

export interface TrendSignal {
  canonical_role: string;
  role_name_zh?: string;
  horizon_months?: number;
  trend_direction: "up" | "down" | "flat" | string;
  predicted_demand_index?: number;
  confidence: number;
  main_factors: string[];
  evidence: TrendEvidence[];
  monthly_forecast?: MonthlyForecastRow[];
  // v2 资产溯源字段（稀疏岗可能为 null，前端如实展示）
  model_used?: string | null;
  backtest_smape?: number | null;
  direction_accuracy?: number | null;
  sparse?: boolean | null;
}

export interface EvidenceResponse {
  role: string;
  months?: string[];
  note?: string;
  candidates_total?: number;
  aggregate?: {
    article_count?: number;
    mean_tone?: number;
    net_signal?: string;
    by_type?: Record<string, number>;
    months_covered?: string[];
    latest_month?: string | null;
    avg_items_per_month?: number;
    mean_relevance?: number;
    opportunity_events?: number;
    risk_events?: number;
  };
  events?: TrendEvidence[];
  jobs?: Array<Record<string, string | number | null>>;
  major_industry_events?: Array<{
    title?: string;
    event_type?: string;
    event_date?: string;
    impact_direction?: string;
  }>;
}

export interface GraphNode {
  id: string;
  label: string;
  label_zh?: string;
  kind: "role" | "skill" | "event";
  category?: string;
  hot?: boolean;
  level?: number;
  size?: number;
  importance?: number;
  role_id?: string;
  event_date?: string;
  impact_direction?: string;
  source_name?: string;
  source_url?: string;
  summary_zh?: string;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: "REQUIRES" | "CORE_SKILL" | "PREREQ" | "AFFECTS" | string;
}

export interface RoleCatalogItem {
  role_id: string;
  role_name: string;
  role_name_zh?: string;
  coarse_role: string;
  size?: number;
  required_skill_ids: string[];
  core_skill_ids: string[];
  required_skills: string[];
  core_skills: string[];
}

export interface LearningResource {
  resource_id?: string;
  title: string;
  url?: string;
  provider?: string;
  level?: string;
  difficulty?: string | null;
  hours_estimate?: number | null;
  language?: string | null;
  quality_score?: number | null;
  source?: string | null;
}

export interface LearningPathStep {
  step_no: number;
  skill: string;
  reason: string;
  resources: LearningResource[];
}

export interface LearningPath {
  target_job_id: string;
  total_steps: number;
  total_estimated_hours?: number;
  score?: number;
  steps: LearningPathStep[];
}

export interface CotContext {
  canonical_role: string;
  horizon_months: number;
  prediction?: {
    trend_direction?: string;
    predicted_demand_index?: number;
    confidence?: number;
  };
  aggregate?: {
    article_count?: number;
    opportunity_events?: number;
    risk_events?: number;
    net_signal?: string;
  };
  events?: Array<{
    cite: string;
    title?: string;
    impact?: string;
    event_type?: string;
    tone?: number;
    is_counter_signal?: boolean;
    url?: string;
  }>;
  major_events?: Array<{
    cite: string;
    title?: string;
    date?: string;
    impact?: string;
    source_url?: string;
  }>;
  jobs?: Array<{
    cite: string;
    company?: string;
    title?: string;
    salary_mid?: number | string | null;
  }>;
  note?: string;
}

export async function getTrend(role: string, months = 3): Promise<TrendSignal> {
  const { data } = await api.get<{ signal: TrendSignal & { job_role?: string; short_term?: string } }>(`/trends/${encodeURIComponent(role)}`, {
    params: { horizon_months: months },
  });
  return normalizeTrendSignal(data.signal, role);
}

export async function getEvidence(role: string, topK = 5): Promise<EvidenceResponse> {
  const { data } = await api.get<EvidenceResponse>(`/evidence/${encodeURIComponent(role)}`, {
    params: { top_k: topK },
  });
  return data;
}

export async function getCotContext(role: string, horizon = 3): Promise<CotContext> {
  const { data } = await api.get<{ context: CotContext; cot_prompt: string }>(`/cot/${encodeURIComponent(role)}`, {
    params: { horizon },
  });
  return data.context;
}

export interface TrendBatchItem {
  canonical_role: string;
  role_name_zh?: string;
  trend_direction: string;
  predicted_demand_index: number;
  confidence: number;
}

export async function getTrendBatch(months = 3): Promise<TrendBatchItem[]> {
  const { data } = await api.get<{ signals: TrendBatchItem[] }>("/trends/batch", {
    params: { horizon_months: months },
  });
  return data.signals;
}

function normalizeTrendSignal(signal: TrendSignal & { job_role?: string; short_term?: string }, fallbackRole: string): TrendSignal {
  return {
    ...signal,
    canonical_role: signal.canonical_role ?? signal.job_role ?? fallbackRole,
    trend_direction: signal.trend_direction ?? signal.short_term ?? "flat",
    confidence: signal.confidence ?? 0,
    main_factors: signal.main_factors ?? [],
    evidence: signal.evidence ?? [],
  };
}

export async function getRoleList(): Promise<Record<string, string[]>> {
  const { data } = await api.get<{ roles: Record<string, string[]> }>("/roles");
  return data.roles;
}

export async function getRoleCatalog(): Promise<RoleCatalogItem[]> {
  const { data } = await api.get<{ roles: RoleCatalogItem[] }>("/roles/catalog");
  return data.roles;
}

export async function getGraph(): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
  const { data } = await api.get<{ nodes: GraphNode[]; links: GraphLink[] }>("/graph");
  return data;
}

export async function generateLearningPath(params: {
  skills: string[];
  targetJobId: string;
  targetRole?: string;
  candidateSkills?: string[];
}): Promise<LearningPath> {
  const { data } = await api.post<{ path: LearningPath }>("/paths/generate", {
    profile: {
      user_id: "frontend_user",
      skills: params.skills,
      target_role: params.targetRole,
    },
    target_job_id: params.targetJobId,
    candidate_skills: params.candidateSkills || [],
  });
  return data.path;
}

export async function extractProfile(resumeText: string) {
  const { data } = await api.post("/profile/extract", { resume_text: resumeText });
  return data;
}

export async function rankCareers(resumeText: string, topK = 10) {
  const { data } = await api.post("/careers/rank", { resume_text: resumeText, top_k: topK });
  return data;
}

// ---------------------------------------------------------------------------
// 岗位推荐（app/api/routes.py，POST /v1/jobs/recommend）
// final_score 为校准后分数；confidence 为 v5 校准规则分档，可能缺失或为 null。
// ---------------------------------------------------------------------------

export type MatchConfidence = "high" | "medium" | "low";

export interface RecommendJobRole {
  job_id: string;
  title: string;
  fine_role?: string;
  coarse_role?: string;
  city?: string | null;
  salary_min_k?: number | null;
  salary_max_k?: number | null;
  required_skills?: string[];
}

export interface RecommendationItem {
  job: RecommendJobRole;
  final_score: number;
  semantic_score: number;
  constraint_score: number;
  path_cost_score: number;
  trend_reward_score: number;
  explanation: string;
  skill_gap: {
    missing_skills: string[];
    overlap_skills: string[];
    optional_skills?: string[];
    transferable?: { known_skill: string; target_skill: string; category?: string | null }[];
  };
  confidence?: MatchConfidence | null;
}

export interface RecommendResponse {
  items: RecommendationItem[];
}

export async function recommendJobs(
  profile: {
    user_id: string;
    skills: string[];
    target_role?: string | null;
    years_experience?: number;
    education?: string | null;
    city?: string | null;
  },
  topK = 5,
): Promise<RecommendationItem[]> {
  const { data } = await api.post<RecommendResponse>("/jobs/recommend", { profile, top_k: topK });
  return data.items ?? [];
}

// ---------------------------------------------------------------------------
// 岗位画像 insights（app/api/role_insights.py）
// ---------------------------------------------------------------------------

export interface SalaryStats {
  currency?: string | null;
  median?: number | null;
  p25?: number | null;
  p75?: number | null;
  sample_size?: number | null;
}

export interface TrendModelInfo {
  model_used?: string | null;
  backtest_smape?: number | null;
  direction_accuracy?: number | null;
  n_reliable_train_months?: number | null;
  confidence?: number | null;
  trend_direction?: string | null;
  sparse?: boolean | null;
}

export interface SkillFreqItem {
  skill_id: string;
  freq: number;
}

export interface MonthlyJdPoint {
  month?: string | null;
  count?: number | null;
}

export interface RoleInsights {
  role_id: string;
  role_name?: string;
  role_name_zh?: string;
  coarse_role?: string;
  jd_count?: number | null;
  remote_ratio?: number | null;
  salary: SalaryStats;
  seniority_distribution: Record<string, number>;
  top_skills: SkillFreqItem[];
  monthly_jd_counts: MonthlyJdPoint[];
  model: TrendModelInfo;
}

/** roleKey 支持 role_id（role_000）或 role_name（大小写不敏感），404 时抛错。 */
export async function getRoleInsights(roleKey: string): Promise<RoleInsights> {
  const { data } = await api.get<RoleInsights>(`/roles/${encodeURIComponent(roleKey)}/insights`);
  return data;
}

export interface RoleOverviewRow {
  role_id: string;
  role_name?: string;
  role_name_zh?: string;
  coarse_role?: string;
  jd_count?: number | null;
  remote_ratio?: number | null;
  salary: SalaryStats;
  trend: TrendModelInfo;
  jd_share_3m: number[];
  jd_share_trend: string;
  monthly_jd_tail: MonthlyJdPoint[];
}

export interface RoleOverview {
  dataset: {
    version?: string;
    total_jd?: number | null;
    assigned_jd?: number | null;
    assignment_rate?: number | null;
    months?: string[];
    data_through?: string | null;
    role_count: number;
  };
  roles: RoleOverviewRow[];
}

export async function getRoleOverview(): Promise<RoleOverview> {
  const { data } = await api.get<RoleOverview>("/roles/overview");
  return data;
}

// ---------------------------------------------------------------------------
// 行业新闻（app/api/news.py）
// ---------------------------------------------------------------------------

export interface NewsItem {
  news_id: string;
  title: string;
  url: string;
  url_resolved?: boolean;
  source: string;
  lang: string;
  published_at: string;
  summary?: string | null;
  content_text?: string | null;
  category?: string | null;
  skills?: string[];
  role_ids?: string[];
}

export interface NewsFreshness {
  latest_published_at?: string | null;
  sources_active?: number;
}

export interface NewsResponse {
  items: NewsItem[];
  total: number;
  page: number;
  page_size: number;
  freshness?: NewsFreshness;
}

export interface NewsCategoryStats {
  days: number;
  categories: Record<string, number>;
}

export interface NewsSourceInfo {
  source: string;
  count: number;
  latest_published_at?: string | null;
}

export async function getNews(params: {
  page?: number;
  pageSize?: number;
  page_size?: number;
  category?: string;
  source?: string;
  lang?: string;
  hours?: number;
  q?: string;
} = {}): Promise<NewsResponse> {
  const { data } = await api.get<NewsResponse>("/news", {
    params: {
      page: params.page,
      page_size: params.pageSize ?? params.page_size,
      category: params.category || undefined,
      source: params.source || undefined,
      lang: params.lang || undefined,
      hours: params.hours,
      q: params.q || undefined,
    },
  });
  return data;
}

export async function getNewsCategories(): Promise<NewsCategoryStats> {
  const { data } = await api.get<NewsCategoryStats>("/news/categories");
  return data;
}

export async function getNewsSources(): Promise<NewsSourceInfo[]> {
  const { data } = await api.get<{ sources: NewsSourceInfo[] }>("/news/sources");
  return data.sources;
}

// ---------------------------------------------------------------------------
// 技能趋势 v3（app/api/trends_v3.py，data/gold/skill_trend_panel_v3.json）
// ---------------------------------------------------------------------------

export interface SkillTrendSparkPoint {
  month?: string | null;
  share?: number | null;
}

export interface SkillTrendItem {
  skill: string;
  name: string;
  status: string;
  momentum_3m: number | null;
  yoy: number | null;
  spark: SkillTrendSparkPoint[];
}

export interface SkillTrendsOverview {
  generated_at?: string | null;
  analysis_end?: string | null;
  window?: { month_start?: string | null; month_end?: string | null };
  months?: string[];
  total_skills: number;
  status_distribution: Record<string, number>;
  emerging: SkillTrendItem[];
  rising: SkillTrendItem[];
  declining: SkillTrendItem[];
}

export async function getSkillTrends(): Promise<SkillTrendsOverview> {
  const { data } = await api.get<SkillTrendsOverview>("/trends/skills");
  return data;
}

export interface SkillTrendMonthlyRow {
  month?: string | null;
  count?: number | null;
  share?: number | null;
  salary_median?: number | null;
  remote_share?: number | null;
  low_coverage?: boolean;
}

export interface SkillTrendForecast {
  method?: string | null;
  m3?: number | null;
  m6?: number | null;
  mape?: number | null;
}

export interface SkillTrendDetail {
  skill: string;
  name: string;
  status: string;
  momentum_3m: number | null;
  yoy: number | null;
  trend_slope: number | null;
  volatility: number | null;
  forecast: SkillTrendForecast | null;
  monthly: SkillTrendMonthlyRow[];
  generated_at?: string | null;
  analysis_end?: string | null;
}

export async function getSkillTrendDetail(skill: string): Promise<SkillTrendDetail> {
  const { data } = await api.get<SkillTrendDetail>(`/trends/skills/${encodeURIComponent(skill)}`);
  return data;
}

// ---------------------------------------------------------------------------
// 招聘风向标（app/api/hiring.py，GET /v1/hiring/overview）
// ---------------------------------------------------------------------------

export interface HiringMomentum {
  delta?: number | null;
  pct?: number | null;
  window_days?: number | null;
}

export interface HiringCompany {
  domain?: string;
  company?: string;
  sector?: string | null;
  latest_open_roles?: number | null;
  momentum_7d?: HiringMomentum | null;
  momentum_30d?: HiringMomentum | null;
}

export interface HiringCompanyMomentum {
  window?: string[];
  n_companies?: number;
  top?: HiringCompany[];
  by_sector?: Record<string, HiringCompany[]>;
}

export interface LayoffMonth {
  month?: string;
  notices?: number;
  employees_affected?: number;
  n_companies?: number;
}

export interface LayoffEmployer {
  month?: string;
  employer?: string;
  employees_affected?: number;
  n_notices?: number;
  states?: string[];
}

export interface HiringLayoffs {
  window?: string[];
  n_notices?: number;
  recent_months?: LayoffMonth[];
  top_recent_employers?: LayoffEmployer[];
}

export interface HnHiringMonth {
  month?: string;
  n_job_posts?: number;
  remote_ratio?: number | null;
  salary_disclosed_ratio?: number | null;
}

export interface HnHiring {
  months?: HnHiringMonth[];
  skill_mentions_top30?: Array<Record<string, number | string>>;
}

export interface HiringOverview {
  generated_at?: string | null;
  company_momentum?: HiringCompanyMomentum | null;
  layoffs?: HiringLayoffs | null;
  hn_hiring?: HnHiring | null;
}

export async function getHiringOverview(): Promise<HiringOverview> {
  const { data } = await api.get<HiringOverview>("/hiring/overview");
  return data;
}

// ---------------------------------------------------------------------------
// 公司雷达（app/api/companies.py，GET /v1/companies[/domain]）
// ---------------------------------------------------------------------------

export type CompanyStatusTag = "expanding" | "cooling" | "stable" | "shrinking" | string;

export interface CompanyMomentum {
  delta?: number | null;
  pct?: number | null;
  window_days?: number | null;
}

export interface CompanyLayoff12m {
  notices?: number | null;
  employees?: number | null;
}

export interface CompanyListItem {
  domain: string;
  name?: string;
  sector?: string | null;
  latest_open_roles?: number | null;
  momentum_7d?: CompanyMomentum | null;
  momentum_30d?: CompanyMomentum | null;
  layoff_events_12m?: CompanyLayoff12m | null;
  status_tag?: CompanyStatusTag | null;
}

export interface CompanyListResponse {
  generated_at?: string | null;
  window?: string[];
  n_companies?: number;
  companies: CompanyListItem[];
}

export interface CompanyOpenRolesDailyPoint {
  date?: string | null;
  count?: number | null;
}

export interface CompanyLayoffEvent {
  month?: string | null;
  employer?: string | null;
  employees_affected?: number | null;
  states?: string[];
}

export interface CompanyRelatedNews {
  title?: string | null;
  url?: string | null;
  source?: string | null;
  published_at?: string | null;
}

export interface CompanyDetail {
  domain: string;
  name?: string;
  sector?: string | null;
  status_tag?: CompanyStatusTag | null;
  latest_open_roles?: number | null;
  open_roles_avg_30d?: number | null;
  momentum_7d?: CompanyMomentum | null;
  momentum_30d?: CompanyMomentum | null;
  open_roles_daily?: CompanyOpenRolesDailyPoint[];
  layoff_events?: CompanyLayoffEvent[];
  related_news?: CompanyRelatedNews[];
  window?: string[] | null;
  generated_at?: string | null;
}

export async function getCompanies(): Promise<CompanyListItem[]> {
  const { data } = await api.get<CompanyListResponse>("/companies");
  return data.companies ?? [];
}

export async function getCompanyDetail(domain: string): Promise<CompanyDetail> {
  const { data } = await api.get<CompanyDetail>(`/companies/${encodeURIComponent(domain)}`);
  return data;
}

export default api;
