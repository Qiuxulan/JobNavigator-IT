// 国内为主的市场数据接口（后端 app/api/market.py）
import { api } from "./api";

export interface NameShare { name: string; count: number; share: number }

export interface CnSkill {
  skill_id: string;
  name: string;
  count: number;
  share_cn: number;
  share_global: number | null;
  share_new_7d?: number | null;
  companies: Record<string, number>;
}

export interface CnCompany {
  source: string;
  company: string;
  open_roles: number;
  momentum_7d: number | null;
  new_7d: number;
  days_observed: number;
  top_roles: { role_id: string; role_zh: string; count: number }[];
  top_cities: NameShare[];
  daily?: { date: string; open_roles: number; new_roles: number; closed_roles: number }[];
}

export interface MarketOverview {
  as_of: string;
  first_day: string;
  days_observed: number;
  source: string;
  summary: {
    open_roles: number;
    n_companies: number;
    companies: NameShare[];
    cities: NameShare[];
    coarse_roles: NameShare[];
    experience: NameShare[];
    skill_coverage: number;
  };
  daily: { date: string; open_roles: number; new_roles: number }[];
  hot_roles: { role_id: string; role_zh: string; role_name: string; coarse_role: string; open_roles: number; share: number; top_companies: string[] }[];
  top_skills: CnSkill[];
  cn_hotter_skills: CnSkill[];
  companies: CnCompany[];
  n_roles_total: number;
  notes: string[];
}

export interface MarketRoleRow {
  role_id: string;
  role_name: string;
  role_zh: string;
  coarse_role: string;
  cn_open_roles: number;
  cn_top_company: string | null;
  global_jd_count: number;
}

export interface CnRoleDetail {
  open_roles: number;
  share: number;
  companies: NameShare[];
  cities: NameShare[];
  experience: NameShare[];
  top_skills: { skill_id: string; name: string; share: number }[];
  new_7d: number;
  samples: { title: string; company: string; city: string; posted_at: string; url: string }[];
}

export interface GlobalRoleBrief {
  jd_count: number;
  salary_usd: { currency: string; median: number; p25: number; p75: number; sample_size: number } | null;
  remote_ratio: number | null;
  top_skills: { skill_id: string; name: string; share: number }[];
  share_series: { month: string; count: number; total: number; share: number }[];
  share_change_3m: number | null;
  note: string;
}

export interface MarketRoleDetail {
  role_id: string;
  role_name: string;
  role_zh: string;
  coarse_role: string;
  as_of: string;
  cn: CnRoleDetail | null;
  global: GlobalRoleBrief;
}

export interface CompareRow {
  role_id: string;
  role_zh: string;
  role_name: string;
  cn_open_roles: number;
  cn_top_companies: string[];
  cn_top_cities: string[];
  cn_top_skills: string[];
  cn_experience: NameShare[];
  global_jd_count: number;
  global_share_change_3m: number | null;
  global_salary_usd_median: number | null;
  global_top_skills: string[];
}

export const getMarketOverview = () => api.get<MarketOverview>("/market/overview").then((r) => r.data);
export const getMarketRoles = () => api.get<{ as_of: string; roles: MarketRoleRow[] }>("/market/roles").then((r) => r.data);
export const getMarketRole = (role: string) =>
  api.get<MarketRoleDetail>(`/market/roles/${encodeURIComponent(role)}`).then((r) => r.data);
export const compareRoles = (ids: string[]) =>
  api.get<{ as_of: string; roles: CompareRow[] }>("/market/compare", { params: { roles: ids.join(",") } }).then((r) => r.data);

export const COARSE_ZH: Record<string, string> = {
  "Emerging AI": "AI 与大模型",
  "AI & Data": "数据",
  "Backend Development": "后端开发",
  "Frontend Development": "前端开发",
  "Mobile Development": "移动端",
  "Cloud Native & DevOps": "云原生与运维",
  "QA & Testing": "测试",
  Security: "安全",
  "Game Development": "游戏",
  "Product & Business Analysis": "产品与项目",
  "General Engineering": "通用研发",
  "Other IT": "其他 IT",
};

export const coarseZh = (c?: string | null) => (c ? COARSE_ZH[c] || c : "—");
export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;
