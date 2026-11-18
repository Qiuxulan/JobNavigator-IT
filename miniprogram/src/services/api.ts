import Taro from '@tarojs/taro'
import { BASE_URL, API_TIMEOUT } from '../config'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: Record<string, any>
  loading?: boolean
  loadingText?: string
  /** 静默模式：出错时不弹 toast（调用方自行兜底） */
  silent?: boolean
  /** 额外请求头 */
  header?: Record<string, string>
}

/** 统一请求封装：拼 baseURL、错误提示、可选 loading。 */
export async function request<T = any>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', data, loading = false, loadingText = '加载中…', silent = false, header } = options
  if (loading) {
    Taro.showLoading({ title: loadingText, mask: true })
  }
  try {
    const res = await Taro.request<T>({
      url: `${BASE_URL}${path}`,
      method,
      data,
      timeout: API_TIMEOUT,
      header: { 'Content-Type': 'application/json', ...header }
    })
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return res.data
    }
    const detail = (res.data as any)?.detail
    const msg = typeof detail === 'string' ? detail : `请求失败（${res.statusCode}）`
    throw new Error(msg)
  } catch (err: any) {
    const msg = err?.errMsg || err?.message || '网络异常，请稍后重试'
    if (loading) Taro.hideLoading()
    if (!silent && !/cancel/i.test(msg)) {
      Taro.showToast({ title: msg.slice(0, 40), icon: 'none', duration: 2500 })
    }
    throw err
  } finally {
    if (loading) Taro.hideLoading()
  }
}

// ---------- 类型定义（与 FastAPI 响应对齐） ----------

export interface UserProfilePayload {
  user_id: string
  skills: string[]
  target_role?: string | null
  years_experience?: number
  education?: string | null
  city?: string | null
}

export interface JobRole {
  job_id: string
  title: string
  fine_role?: string
  coarse_role?: string
  city?: string | null
  salary_min_k?: number | null
  salary_max_k?: number | null
  required_skills?: string[]
}

export interface SkillGap {
  missing_skills: string[]
  overlap_skills: string[]
  optional_skills?: string[]
  transferable?: { known_skill: string; target_skill: string; category?: string | null }[]
}

export interface RecommendationItem {
  job: JobRole
  final_score: number
  semantic_score: number
  constraint_score: number
  path_cost_score: number
  trend_reward_score: number
  explanation: string
  skill_gap: SkillGap
  // matching v5：校准后置信度分档（high/medium/low），可能缺失或为 null，前端需容错
  confidence?: 'high' | 'medium' | 'low' | null
}

export interface RecommendResponse {
  items: RecommendationItem[]
}

export interface LearningResource {
  resource_id: string
  title: string
  url: string
  provider: string
  level?: string
  hours_estimate?: number | null
  language?: string | null
  quality_score?: number | null
  source?: string | null
}

export interface LearningPathStep {
  step_no: number
  skill: string
  reason: string
  resources: LearningResource[]
}

export interface LearningPath {
  target_job_id: string
  total_steps: number
  total_estimated_hours: number
  score: number
  steps: LearningPathStep[]
}

export interface PathGenerateResponse {
  path: LearningPath
}

export interface RoleCatalogItem {
  role_id: string
  role_name: string
  role_name_zh?: string
  coarse_role?: string
  size?: number
  required_skills?: string[]
  core_skill_ids?: string[]
  [k: string]: any
}

export interface RolesCatalogResponse {
  roles: RoleCatalogItem[]
}

export interface ChatMessagePayload {
  role: 'user' | 'assistant' | 'system'
  content: string
}

// ---------- 业务 API ----------

export function postRecommend(profile: UserProfilePayload, topK = 5) {
  return request<RecommendResponse>('/v1/jobs/recommend', {
    method: 'POST',
    data: { profile, preference: {}, top_k: topK },
    loading: true,
    loadingText: '正在匹配岗位…'
  })
}

export function postPathGenerate(profile: UserProfilePayload, targetJobId: string) {
  return request<PathGenerateResponse>('/v1/paths/generate', {
    method: 'POST',
    data: { profile, target_job_id: targetJobId },
    loading: true,
    loadingText: '正在生成学习路径…'
  })
}

export function postAgentChat(messages: ChatMessagePayload[]) {
  return request<{ reply: string }>('/v1/agent/chat', {
    method: 'POST',
    data: { messages }
  })
}

export function getRolesCatalog() {
  return request<RolesCatalogResponse>('/v1/roles/catalog')
}

export function getSkillTrendsOverview() {
  return request<{
    emerging: TrendSkillItem[]
    rising: TrendSkillItem[]
    declining: TrendSkillItem[]
    total_skills: number
    analysis_end?: string
  }>('/v1/trends/skills')
}

export interface TrendSparkPoint {
  month: string
  share: number
}

export interface TrendSkillItem {
  skill: string
  name: string
  status?: string
  momentum_3m?: number | null
  yoy?: number | null
  spark?: TrendSparkPoint[]
}

export interface SkillTrendDetail {
  skill: string
  name: string
  status?: string
  momentum_3m?: number | null
  yoy?: number | null
  trend_slope?: number | null
  volatility?: number | null
  forecast?: { method?: string; m3?: number; m6?: number; mape?: number } | null
  monthly: { month: string; count?: number; share?: number | null; salary_median?: number | null; remote_share?: number | null; low_coverage?: boolean }[]
  analysis_end?: string
}

export function getSkillTrendDetail(skill: string) {
  return request<SkillTrendDetail>(`/v1/trends/skills/${encodeURIComponent(skill)}`)
}

export interface NewsItem {
  news_id: string
  title: string
  url: string
  url_resolved?: boolean
  source?: string
  lang?: string
  published_at?: string
  summary?: string
  content_text?: string
  category?: string
  skills?: string[]
  role_ids?: string[]
}

export interface NewsListResponse {
  items: NewsItem[]
  total: number
  page: number
  page_size: number
}

export function getNews(params: { page: number; page_size: number; category?: string; q?: string }) {
  const qs = new URLSearchParams()
  qs.set('page', String(params.page))
  qs.set('page_size', String(params.page_size))
  if (params.category) qs.set('category', params.category)
  if (params.q) qs.set('q', params.q)
  return request<NewsListResponse>(`/v1/news?${qs.toString()}`)
}

export function getNewsCategories() {
  return request<{ days: number; categories: Record<string, number> }>('/v1/news/categories')
}

// ---------- 招聘风向标（GET /v1/hiring/overview，任一节可能为 null） ----------

export interface HiringMomentum {
  delta?: number | null
  pct?: number | null
}

export interface HiringCompany {
  domain?: string
  company?: string
  sector?: string | null
  latest_open_roles?: number | null
  momentum_7d?: HiringMomentum | null
  momentum_30d?: HiringMomentum | null
}

export interface LayoffMonth {
  month?: string
  notices?: number
  employees_affected?: number
  n_companies?: number
}

export interface LayoffEmployer {
  month?: string
  employer?: string
  employees_affected?: number
  n_notices?: number
}

export interface HnHiringMonth {
  month?: string
  n_job_posts?: number
  remote_ratio?: number | null
  salary_disclosed_ratio?: number | null
}

export interface HiringOverview {
  generated_at?: string | null
  company_momentum?: {
    window?: string[]
    n_companies?: number
    top?: HiringCompany[]
    by_sector?: Record<string, HiringCompany[]>
  } | null
  layoffs?: {
    window?: string[]
    n_notices?: number
    recent_months?: LayoffMonth[]
    top_recent_employers?: LayoffEmployer[]
  } | null
  hn_hiring?: {
    months?: HnHiringMonth[]
    skill_mentions_top30?: Array<Record<string, number | string>>
  } | null
}

export function getHiringOverview() {
  return request<HiringOverview>('/v1/hiring/overview', { silent: true })
}

// ---------- 公司雷达（GET /v1/companies） ----------

export interface CompanyListItem {
  domain: string
  name: string
  sector?: string | null
  latest_open_roles?: number | null
  momentum_7d?: HiringMomentum | null
  momentum_30d?: HiringMomentum | null
  layoff_events_12m?: { notices?: number; employees?: number }
  status_tag?: string
}

export interface CompanyListResponse {
  generated_at?: string | null
  window?: string[] | null
  n_companies?: number
  companies?: CompanyListItem[]
}

export interface CompanyLayoffEvent {
  month?: string
  employer?: string
  employees_affected?: number
  n_notices?: number
  states?: string[]
  event_types?: string[]
  latest_effective_date?: string
}

export interface CompanyNewsItem {
  title?: string
  url?: string
  source?: string
  published_at?: string | null
}

export interface CompanyDetail {
  domain: string
  name: string
  sector?: string | null
  status_tag?: string
  latest_open_roles?: number | null
  open_roles_avg_30d?: number | null
  momentum_7d?: HiringMomentum | null
  momentum_30d?: HiringMomentum | null
  window?: string[] | null
  generated_at?: string | null
  layoff_source?: string | null
  open_roles_daily?: { date?: string; count?: number | null }[]
  layoff_events?: CompanyLayoffEvent[]
  related_news?: CompanyNewsItem[]
}

export function getCompanies() {
  return request<CompanyListResponse>('/v1/companies', { silent: true })
}

export function getCompanyDetail(domain: string) {
  return request<CompanyDetail>(
    `/v1/companies/${encodeURIComponent(domain)}`,
    { silent: true }
  )
}
