import Taro from '@tarojs/taro'
import type { JobRole, LearningPath, NewsItem, RecommendationItem } from '../services/api'

// ---------- storage key 约定 ----------
// jobnav_selected_skills    string[]          已选技能
// jobnav_target_role        StoredTargetRole  目标岗位
// jobnav_joined_at          string            首次进入时间（ISO）
// jobnav_nickname           string            用户昵称（云端不可达时的本地兜底）
// jobnav_favorite_jobs      FavoriteJob[]     收藏的推荐岗位（云端收藏 job 的本地缓存）
// jobnav_favorite_news      FavoriteNews[]    收藏的新闻（云端收藏 news 的本地缓存）
// jobnav_saved_paths        SavedPath[]       已保存的学习路径（云端收藏 path 的本地缓存）
// jobnav_history_trends     HistoryItem[]     趋势浏览历史（≤20）
// jobnav_history_news       HistoryItem[]     新闻浏览历史（≤20）
// jobnav_history_match      HistoryItem[]     匹配浏览历史（≤20）
// jobnav_prefill_message    string            匹配页「问助手」预填消息（助手页 onShow 消费）

export const SKILLS_STORAGE_KEY = 'jobnav_selected_skills'
export const TARGET_ROLE_STORAGE_KEY = 'jobnav_target_role'
export const JOINED_AT_KEY = 'jobnav_joined_at'
export const NICKNAME_KEY = 'jobnav_nickname'
export const FAVORITE_JOBS_KEY = 'jobnav_favorite_jobs'
export const FAVORITE_NEWS_KEY = 'jobnav_favorite_news'
export const SAVED_PATHS_KEY = 'jobnav_saved_paths'
export const HISTORY_TRENDS_KEY = 'jobnav_history_trends'
export const HISTORY_NEWS_KEY = 'jobnav_history_news'
export const HISTORY_MATCH_KEY = 'jobnav_history_match'
export const PREFILL_MESSAGE_KEY = 'jobnav_prefill_message'

export const HISTORY_LIMIT = 20

export interface StoredTargetRole {
  role_id: string
  role_name: string
  role_name_zh?: string
}

export interface FavoriteJob {
  job: JobRole
  final_score: number
  explanation?: string
  saved_at: string
}

export interface SavedPath {
  job_id: string
  job_title: string
  total_steps: number
  total_hours: number
  score: number
  saved_at: string
  path: LearningPath
}

export interface HistoryItem {
  id: string
  title: string
  viewed_at: string
}

/** 本地历史分类：'trends' 与云端 item_type 'trend' 对应 */
export type LocalHistoryType = 'trends' | 'news' | 'match'

export interface FavoriteNews {
  news_id: string
  title: string
  summary?: string
  source?: string
  published_at?: string
  url?: string
  saved_at: string
}

function read<T>(key: string, fallback: T): T {
  try {
    const v = Taro.getStorageSync(key)
    return v === undefined || v === '' || v === null ? fallback : (v as T)
  } catch (e) {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    Taro.setStorageSync(key, value)
  } catch (e) {}
}

// ---------- 技能档案 ----------

export function getStoredSkills(): string[] {
  return read<string[]>(SKILLS_STORAGE_KEY, [])
}

export function getStoredTargetRole(): StoredTargetRole | null {
  return read<StoredTargetRole | null>(TARGET_ROLE_STORAGE_KEY, null)
}

export function saveProfile(skills: string[], targetRole: StoredTargetRole | null) {
  write(SKILLS_STORAGE_KEY, skills)
  write(TARGET_ROLE_STORAGE_KEY, targetRole)
}

// ---------- 加入时间 ----------

export function getJoinedAt(): string {
  const existing = read<string>(JOINED_AT_KEY, '')
  if (existing) return existing
  const now = new Date().toISOString()
  write(JOINED_AT_KEY, now)
  return now
}

// ---------- 昵称（云端 profile 的本地兜底） ----------

export function getNickname(): string {
  return read<string>(NICKNAME_KEY, '')
}

export function setNickname(nickname: string) {
  write(NICKNAME_KEY, nickname)
}

// ---------- 推荐收藏（job 类收藏本地缓存） ----------

export function getFavoriteJobs(): FavoriteJob[] {
  return read<FavoriteJob[]>(FAVORITE_JOBS_KEY, [])
}

export function setFavoriteJobs(list: FavoriteJob[]) {
  write(FAVORITE_JOBS_KEY, list)
}

export function isFavoriteJob(jobId: string): boolean {
  return getFavoriteJobs().some((f) => f.job.job_id === jobId)
}

export function toggleFavoriteJob(item: RecommendationItem): boolean {
  const list = getFavoriteJobs()
  const idx = list.findIndex((f) => f.job.job_id === item.job.job_id)
  if (idx >= 0) {
    list.splice(idx, 1)
    write(FAVORITE_JOBS_KEY, list)
    return false
  }
  list.unshift({
    job: item.job,
    final_score: item.final_score,
    explanation: item.explanation,
    saved_at: new Date().toISOString()
  })
  write(FAVORITE_JOBS_KEY, list)
  return true
}

// ---------- 新闻收藏（news 类收藏本地缓存） ----------

export function getFavoriteNews(): FavoriteNews[] {
  return read<FavoriteNews[]>(FAVORITE_NEWS_KEY, [])
}

export function setFavoriteNews(list: FavoriteNews[]) {
  write(FAVORITE_NEWS_KEY, list)
}

export function isFavoriteNews(newsId: string): boolean {
  return getFavoriteNews().some((f) => f.news_id === newsId)
}

export function toggleFavoriteNews(item: NewsItem): boolean {
  const list = getFavoriteNews()
  const idx = list.findIndex((f) => f.news_id === item.news_id)
  if (idx >= 0) {
    list.splice(idx, 1)
    write(FAVORITE_NEWS_KEY, list)
    return false
  }
  list.unshift({
    news_id: item.news_id,
    title: item.title,
    summary: item.summary,
    source: item.source,
    published_at: item.published_at,
    url: item.url,
    saved_at: new Date().toISOString()
  })
  write(FAVORITE_NEWS_KEY, list)
  return true
}

// ---------- 路径存档（path 类收藏本地缓存） ----------

export function getSavedPaths(): SavedPath[] {
  return read<SavedPath[]>(SAVED_PATHS_KEY, [])
}

export function setSavedPaths(list: SavedPath[]) {
  write(SAVED_PATHS_KEY, list)
}

export function savePath(jobId: string, jobTitle: string, path: LearningPath): boolean {
  const list = getSavedPaths()
  if (list.some((p) => p.job_id === jobId)) return false
  list.unshift({
    job_id: jobId,
    job_title: jobTitle,
    total_steps: path.total_steps,
    total_hours: path.total_estimated_hours,
    score: path.score,
    saved_at: new Date().toISOString(),
    path
  })
  write(SAVED_PATHS_KEY, list)
  return true
}

// ---------- 浏览历史（本地缓存，云端历史不可达时兜底） ----------

const HISTORY_KEY_MAP: Record<LocalHistoryType, string> = {
  trends: HISTORY_TRENDS_KEY,
  news: HISTORY_NEWS_KEY,
  match: HISTORY_MATCH_KEY
}

export function addHistory(type: LocalHistoryType, id: string, title: string) {
  if (!id) return
  const key = HISTORY_KEY_MAP[type]
  const list = read<HistoryItem[]>(key, [])
  const next = [
    { id, title, viewed_at: new Date().toISOString() },
    ...list.filter((h) => h.id !== id)
  ].slice(0, HISTORY_LIMIT)
  write(key, next)
}

export function getHistory(type: LocalHistoryType): HistoryItem[] {
  return read<HistoryItem[]>(HISTORY_KEY_MAP[type], [])
}

export function setHistory(type: LocalHistoryType, items: HistoryItem[]) {
  write(HISTORY_KEY_MAP[type], items.slice(0, HISTORY_LIMIT))
}

// ---------- 清除缓存 ----------

export type CacheCategory = 'favorites' | 'paths' | 'history' | 'profile'

export function clearCache(category: CacheCategory | 'all') {
  if (category === 'all' || category === 'favorites') {
    Taro.removeStorageSync(FAVORITE_JOBS_KEY)
    Taro.removeStorageSync(FAVORITE_NEWS_KEY)
  }
  if (category === 'all' || category === 'paths') Taro.removeStorageSync(SAVED_PATHS_KEY)
  if (category === 'all' || category === 'history') {
    Taro.removeStorageSync(HISTORY_TRENDS_KEY)
    Taro.removeStorageSync(HISTORY_NEWS_KEY)
    Taro.removeStorageSync(HISTORY_MATCH_KEY)
  }
  if (category === 'all' || category === 'profile') {
    Taro.removeStorageSync(SKILLS_STORAGE_KEY)
    Taro.removeStorageSync(TARGET_ROLE_STORAGE_KEY)
    Taro.removeStorageSync(NICKNAME_KEY)
  }
}
