import Taro from '@tarojs/taro'
import { request } from './api'
import type { LearningPath, NewsItem, RecommendationItem } from './api'
import * as store from '../utils/store'

/**
 * 「我的数据」服务：收藏 / 浏览历史 / 个人资料。
 *
 * 策略：乐观更新本地 storage 作为缓存层，随后尽力同步云端 /v1/me/*；
 * 云端不可达时静默使用本地数据，绝不阻塞主流程、不弹错误。
 * 所有请求携带 header `X-Client-Id: <uuid>`（首次启动生成，storage key jobnav_client_id）。
 */

const CLIENT_ID_KEY = 'jobnav_client_id'

export type FavoriteType = 'job' | 'news' | 'path'
export type HistoryType = 'news' | 'trend' | 'match'

/** 统一的我的数据条目（收藏与历史同构） */
export interface MeItem {
  item_type: FavoriteType | HistoryType
  item_id: string
  title: string
  payload: any
  created_at?: string
}

export interface MeOverview {
  nickname: string
  joined_at: string
  favorite_counts: { job: number; news: number; path: number }
  history_counts: { news: number; trend: number; match: number }
}

function uuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/** 获取（必要时生成并持久化）设备级 client id。 */
export function getClientId(): string {
  try {
    let id = Taro.getStorageSync(CLIENT_ID_KEY)
    if (!id || typeof id !== 'string') {
      id = uuid()
      Taro.setStorageSync(CLIENT_ID_KEY, id)
    }
    return id
  } catch (e) {
    return uuid()
  }
}

function meRequest<T = any>(path: string, options: { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; data?: Record<string, any> } = {}) {
  return request<T>(path, { ...options, silent: true, header: { 'X-Client-Id': getClientId() } })
}

// ---------- 个人资料 ----------

export async function fetchOverview(): Promise<MeOverview | null> {
  try {
    return await meRequest<MeOverview>('/v1/me/overview')
  } catch (e) {
    return null
  }
}

/** 更新昵称：本地立即生效，云端尽力同步。返回是否同步成功。 */
export async function updateNickname(nickname: string): Promise<boolean> {
  const name = (nickname || '').trim()
  if (!name) return false
  store.setNickname(name)
  try {
    await meRequest('/v1/me/profile', { method: 'PUT', data: { nickname: name } })
    return true
  } catch (e) {
    return false
  }
}

/** 展示用昵称：云端 overview → 本地兜底 → 默认。 */
export function resolveNickname(overview: MeOverview | null): string {
  return overview?.nickname || store.getNickname() || 'IT 探索者'
}

// ---------- 收藏：本地缓存层读写 ----------

function jobFavoriteToItem(f: store.FavoriteJob): MeItem {
  return {
    item_type: 'job',
    item_id: f.job.job_id,
    title: f.job.title,
    payload: { job: f.job, final_score: f.final_score, explanation: f.explanation },
    created_at: f.saved_at
  }
}

function newsFavoriteToItem(f: store.FavoriteNews): MeItem {
  return {
    item_type: 'news',
    item_id: f.news_id,
    title: f.title,
    payload: { summary: f.summary, source: f.source, published_at: f.published_at, url: f.url },
    created_at: f.saved_at
  }
}

function pathFavoriteToItem(p: store.SavedPath): MeItem {
  return {
    item_type: 'path',
    item_id: p.job_id,
    title: p.job_title,
    payload: {
      job_title: p.job_title,
      total_steps: p.total_steps,
      total_hours: p.total_hours,
      score: p.score,
      path: p.path
    },
    created_at: p.saved_at
  }
}

export function localFavorites(type: FavoriteType): MeItem[] {
  if (type === 'job') return store.getFavoriteJobs().map(jobFavoriteToItem)
  if (type === 'news') return store.getFavoriteNews().map(newsFavoriteToItem)
  return store.getSavedPaths().map(pathFavoriteToItem)
}

/** 云端 → 本地缓存同步 */
function cacheFavoritesFromCloud(type: FavoriteType, items: MeItem[]) {
  try {
    if (type === 'job') {
      store.setFavoriteJobs(
        items.map((it) => ({
          job: (it.payload?.job || {}) as any,
          final_score: Number(it.payload?.final_score || 0),
          explanation: it.payload?.explanation,
          saved_at: it.created_at || new Date().toISOString()
        }))
      )
    } else if (type === 'news') {
      store.setFavoriteNews(
        items.map((it) => ({
          news_id: it.item_id,
          title: it.title,
          summary: it.payload?.summary,
          source: it.payload?.source,
          published_at: it.payload?.published_at,
          url: it.payload?.url,
          saved_at: it.created_at || new Date().toISOString()
        }))
      )
    } else {
      store.setSavedPaths(
        items.map((it) => ({
          job_id: it.item_id,
          job_title: it.payload?.job_title || it.title,
          total_steps: Number(it.payload?.total_steps || (it.payload?.path?.total_steps ?? 0)),
          total_hours: Number(it.payload?.total_hours || (it.payload?.path?.total_estimated_hours ?? 0)),
          score: Number(it.payload?.score || (it.payload?.path?.score ?? 0)),
          saved_at: it.created_at || new Date().toISOString(),
          path: it.payload?.path
        }))
      )
    }
  } catch (e) {}
}

/** 读取某类收藏：优先云端，失败回退本地缓存。 */
export async function listFavorites(type: FavoriteType): Promise<MeItem[]> {
  try {
    const res = await meRequest<{ items: MeItem[] }>(`/v1/me/favorites?item_type=${type}`)
    const items = res?.items || []
    cacheFavoritesFromCloud(type, items)
    return items
  } catch (e) {
    return localFavorites(type)
  }
}

/** 批量获取收藏 id 集合（用于标星）。 */
export async function fetchFavoriteIds(type: FavoriteType): Promise<Record<string, true>> {
  const items = await listFavorites(type)
  const map: Record<string, true> = {}
  items.forEach((it) => {
    if (it.item_id) map[it.item_id] = true
  })
  return map
}

/** 删除收藏：本地立即移除 + DELETE 尽力同步。 */
export async function removeFavorite(type: FavoriteType, itemId: string): Promise<void> {
  try {
    if (type === 'job') {
      store.setFavoriteJobs(store.getFavoriteJobs().filter((f) => f.job.job_id !== itemId))
    } else if (type === 'news') {
      store.setFavoriteNews(store.getFavoriteNews().filter((f) => f.news_id !== itemId))
    } else {
      store.setSavedPaths(store.getSavedPaths().filter((p) => p.job_id !== itemId))
    }
  } catch (e) {}
  try {
    await meRequest(`/v1/me/favorites/${type}/${encodeURIComponent(itemId)}`, { method: 'DELETE' })
  } catch (e) {}
}

/** 收藏/取消岗位：本地乐观更新，返回收藏状态。 */
export async function setJobFavorite(item: RecommendationItem, favorited: boolean): Promise<void> {
  const id = item.job.job_id
  if (favorited) {
    const ok = store.toggleFavoriteJob(item)
    void ok
    try {
      await meRequest('/v1/me/favorites', {
        method: 'PUT',
        data: {
          item_type: 'job',
          item_id: id,
          title: item.job.title,
          payload: { job: item.job, final_score: item.final_score, explanation: item.explanation }
        }
      })
    } catch (e) {}
  } else {
    await removeFavorite('job', id)
  }
}

/** 收藏/取消新闻：本地乐观更新。 */
export async function setNewsFavorite(item: NewsItem, favorited: boolean): Promise<void> {
  const id = item.news_id
  if (favorited) {
    store.toggleFavoriteNews(item)
    try {
      await meRequest('/v1/me/favorites', {
        method: 'PUT',
        data: {
          item_type: 'news',
          item_id: id,
          title: item.title,
          payload: {
            summary: item.summary,
            source: item.source,
            published_at: item.published_at,
            url: item.url
          }
        }
      })
    } catch (e) {}
  } else {
    await removeFavorite('news', id)
  }
}

const PATH_PAYLOAD_LIMIT = 30000

/**
 * 路径 payload 裁剪：资源只留关键字段，控制在 ~30KB 内（微信收藏 payload ≤32KB）。
 */
export function trimPathPayload(path: LearningPath): Record<string, any> {
  const clone: any = {
    target_job_id: path.target_job_id,
    total_steps: path.total_steps,
    total_estimated_hours: path.total_estimated_hours,
    score: path.score,
    steps: (path.steps || []).map((s) => ({
      step_no: s.step_no,
      skill: s.skill,
      reason: s.reason,
      resources: (s.resources || []).slice(0, 24).map((r) => ({
        resource_id: r.resource_id,
        title: r.title,
        url: r.url,
        provider: r.provider,
        level: r.level,
        hours_estimate: r.hours_estimate
      }))
    }))
  }
  // 仍超限时，逐步裁掉每步最后一个资源
  while (JSON.stringify(clone).length > PATH_PAYLOAD_LIMIT && clone.steps.some((s: any) => s.resources.length > 1)) {
    for (const s of clone.steps) {
      if (s.resources.length > 1) s.resources.pop()
    }
  }
  return clone
}

/** 保存学习路径（item_type=path）。本地存档 + 云端尽力同步。 */
export async function savePathFavorite(jobId: string, jobTitle: string, path: LearningPath): Promise<void> {
  store.savePath(jobId, jobTitle, path)
  try {
    await meRequest('/v1/me/favorites', {
      method: 'PUT',
      data: {
        item_type: 'path',
        item_id: jobId,
        title: jobTitle,
        payload: trimPathPayload(path)
      }
    })
  } catch (e) {}
}

// ---------- 浏览历史 ----------

const LOCAL_HISTORY_TYPE: Record<HistoryType, store.LocalHistoryType> = {
  news: 'news',
  trend: 'trends',
  match: 'match'
}

export function localHistory(type: HistoryType): MeItem[] {
  return store.getHistory(LOCAL_HISTORY_TYPE[type]).map((h) => ({
    item_type: type,
    item_id: h.id,
    title: h.title,
    payload: null,
    created_at: h.viewed_at
  }))
}

/** 读取历史：优先云端，失败回退本地。 */
export async function listHistory(type: HistoryType, limit = 20): Promise<MeItem[]> {
  try {
    const res = await meRequest<{ items: MeItem[] }>(`/v1/me/history?item_type=${type}&limit=${limit}`)
    const items = res?.items || []
    store.setHistory(
      LOCAL_HISTORY_TYPE[type],
      items.map((it) => ({ id: it.item_id, title: it.title, viewed_at: it.created_at || new Date().toISOString() }))
    )
    return items
  } catch (e) {
    return localHistory(type).slice(0, limit)
  }
}

/** 记录一条浏览历史：本地立即写 + POST 尽力同步（重复浏览自动置顶由后端处理）。 */
export async function recordHistory(type: HistoryType, itemId: string, title: string, payload: any = null): Promise<void> {
  if (!itemId) return
  store.addHistory(LOCAL_HISTORY_TYPE[type], itemId, title)
  try {
    await meRequest('/v1/me/history', {
      method: 'POST',
      data: { item_type: type, item_id: itemId, title, payload }
    })
  } catch (e) {}
}

/** 清空全部云端历史 + 本地历史缓存。 */
export async function clearAllHistory(): Promise<void> {
  store.setHistory('trends', [])
  store.setHistory('news', [])
  store.setHistory('match', [])
  try {
    await meRequest('/v1/me/history', { method: 'DELETE' })
  } catch (e) {}
}
