const API_BASE = "/api/v1";

const api = {
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
  tone?: number;
  event_type?: string;
}

export interface TrendSignal {
  canonical_role: string;
  role_name_zh?: string;
  horizon_months?: number;
  trend_direction: "up" | "down" | "flat" | string;
  predicted_demand_index: number;
  confidence: number;
  main_factors: string[];
  evidence: TrendEvidence[];
  monthly_forecast?: Array<Record<string, number | string | null>>;
}

export interface EvidenceResponse {
  role: string;
  aggregate?: {
    article_count?: number;
    mean_tone?: number;
    net_signal?: string;
  };
  events?: TrendEvidence[];
  jobs?: Array<Record<string, string | number | null>>;
  major_industry_events?: Array<{
    title?: string;
    event_type?: string;
    event_date?: string;
    impact_direction?: string;
  }>;
  note?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  label_zh?: string;
  kind: "role" | "skill" | "event";
  category?: string;
  hot?: boolean;
  level?: number;
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
  title: string;
  url?: string;
  provider?: string;
  level?: string;
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
  const trend = signal.trend_direction ?? signal.short_term ?? "flat";
  const predicted =
    signal.predicted_demand_index ??
    ({ up: 0.65, flat: 0.5, down: 0.35 } as Record<string, number>)[trend] ??
    0.5;
  return {
    ...signal,
    canonical_role: signal.canonical_role ?? signal.job_role ?? fallbackRole,
    trend_direction: trend,
    predicted_demand_index: predicted,
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

export default api;
