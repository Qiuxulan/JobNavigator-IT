// 国内市场（/v1/market，国内科技公司官网每日在招岗位）
import { request } from './api'

export interface NameShare { name: string; count: number; share: number }
export interface CnSkill { skill_id: string; name: string; share_cn: number; share_global: number | null }
export interface CnCompany {
  source: string
  company: string
  open_roles: number
  momentum_7d: number | null
  days_observed: number
  top_roles: { role_id: string; role_zh: string; count: number }[]
  top_cities: NameShare[]
}
export interface MarketOverview {
  as_of: string
  days_observed: number
  summary: { open_roles: number; n_companies: number; cities: NameShare[]; coarse_roles: NameShare[] }
  hot_roles: { role_id: string; role_zh: string; open_roles: number; top_companies: string[] }[]
  top_skills: CnSkill[]
  cn_hotter_skills: CnSkill[]
  companies: CnCompany[]
}
export interface MarketRoleDetail {
  role_id: string
  role_name: string
  role_zh: string
  coarse_role: string
  as_of: string
  cn: {
    open_roles: number
    share: number
    companies: NameShare[]
    cities: NameShare[]
    experience: NameShare[]
    top_skills: { skill_id: string; name: string; share: number }[]
    samples: { title: string; company: string; city: string; posted_at: string; url: string }[]
  } | null
  global: { jd_count: number; salary_usd: { median: number } | null; note: string }
}

export function getMarketOverview() {
  return request<MarketOverview>('/v1/market/overview', { silent: true })
}

export function getMarketRole(roleId: string) {
  return request<MarketRoleDetail>(`/v1/market/roles/${encodeURIComponent(roleId)}`, { silent: true })
}

export const pct = (v?: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`)
