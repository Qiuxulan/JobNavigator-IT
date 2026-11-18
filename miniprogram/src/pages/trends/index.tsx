import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import {
  getCompanies,
  getHiringOverview,
  getSkillTrendsOverview,
  CompanyListItem,
  HiringOverview,
  TrendSkillItem
} from '../../services/api'
import { getMarketOverview, MarketOverview, pct } from '../../services/market'
import './index.scss'

type RadarKey = 'expanding' | 'layoff' | 'hc'

const RADAR_TABS: { key: RadarKey; label: string }[] = [
  { key: 'expanding', label: '🔥 扩张榜' },
  { key: 'layoff', label: '📉 裁员名单' },
  { key: 'hc', label: '🏢 HC 大户' }
]

const STATUS_LABEL: Record<string, string> = {
  expanding: '扩张中',
  shrinking: '裁员中',
  cooling: '收缩中',
  stable: '平稳'
}

const fmtSigned = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(0)}`
const fmtPct = (p?: number | null) =>
  p == null ? '' : ` (${p >= 0 ? '+' : ''}${(p * 100).toFixed(1)}%)`

export default function TrendsPage() {
  const [region, setRegion] = useState<'cn' | 'global'>('cn')
  const [market, setMarket] = useState<MarketOverview | null | undefined>(undefined)
  const [radar, setRadar] = useState<RadarKey>('expanding')
  const [companies, setCompanies] = useState<CompanyListItem[]>([])
  const [hiring, setHiring] = useState<HiringOverview | null | undefined>(undefined)
  const [skills, setSkills] = useState<{
    emerging: TrendSkillItem[]
    rising: TrendSkillItem[]
  }>({ emerging: [], rising: [] })

  useEffect(() => {
    getMarketOverview().then(setMarket).catch(() => setMarket(null))
    getCompanies()
      .then((res) => setCompanies(res.companies || []))
      .catch(() => setCompanies([]))
    getHiringOverview()
      .then((res) => setHiring(res || null))
      .catch(() => setHiring(null))
    getSkillTrendsOverview()
      .then((res) =>
        setSkills({ emerging: res.emerging || [], rising: res.rising || [] })
      )
      .catch(() => {})
  }, [])

  const expandingTop = useMemo(
    () =>
      [...companies]
        .sort(
          (a, b) => (b.momentum_30d?.delta ?? -1e9) - (a.momentum_30d?.delta ?? -1e9)
        )
        .filter((c) => (c.momentum_30d?.delta ?? 0) > 0)
        .slice(0, 5),
    [companies]
  )
  const hcTop = useMemo(
    () =>
      [...companies]
        .sort((a, b) => (b.latest_open_roles ?? 0) - (a.latest_open_roles ?? 0))
        .slice(0, 5),
    [companies]
  )
  const layoffTop = useMemo(
    () => (hiring?.layoffs?.top_recent_employers || []).slice(0, 5),
    [hiring]
  )
  const hnMonths = useMemo(() => (hiring?.hn_hiring?.months || []).slice(-6), [hiring])
  const hnMax = useMemo(() => Math.max(...hnMonths.map((m) => m.n_job_posts || 0), 1), [hnMonths])
  const hnLatest = hnMonths[hnMonths.length - 1]

  const goCompany = (domain?: string) => {
    if (!domain) return
    Taro.navigateTo({ url: `/pages/company/index?domain=${encodeURIComponent(domain)}` })
  }

  const goRole = (id: string) => {
    Taro.navigateTo({ url: `/pages/role/index?id=${encodeURIComponent(id)}` })
  }

  const goSkills = () => {
    Taro.navigateTo({ url: '/pages/skill-trends/index' })
  }

  return (
    <View className='container'>
      <View className='page-hero'>
        <Text className='page-hero-title'>行业雷达</Text>
        <Text className='page-hero-sub'>国内大厂官网每日在招岗位 · 技能需求 · 热门方向</Text>
      </View>

      <View className='region-tabs'>
        <Text className={`region-tab ${region === 'cn' ? 'region-tab--active' : ''}`} onClick={() => setRegion('cn')}>国内</Text>
        <Text className={`region-tab ${region === 'global' ? 'region-tab--active' : ''}`} onClick={() => setRegion('global')}>海外参考</Text>
      </View>

      {region === 'cn' && market === undefined && <View className='empty'>加载中…</View>}
      {region === 'cn' && market === null && <View className='empty'>国内数据暂不可用，请稍后再试</View>}
      {region === 'cn' && market && (
        <>
          <View className='cn-kpis'>
            <View className='cn-kpi'><Text className='cn-kpi-v'>{market.summary.open_roles}</Text><Text className='cn-kpi-l'>在招 IT 岗位</Text></View>
            <View className='cn-kpi'><Text className='cn-kpi-v'>{market.summary.n_companies}</Text><Text className='cn-kpi-l'>家大厂官网</Text></View>
            <View className='cn-kpi'><Text className='cn-kpi-v'>{market.summary.cities[0]?.name || '—'}</Text><Text className='cn-kpi-l'>最集中城市</Text></View>
          </View>

          <View className='card'>
            <Text className='card-title'>公司在招</Text>
            {market.companies.map((c, i) => (
              <View className='radar-row radar-row--static' key={c.source}>
                <Text className={`radar-rank radar-rank--${Math.min(i + 1, 5)}`}>{i + 1}</Text>
                <View className='radar-info'>
                  <Text className='radar-name radar-name--single'>{c.company}</Text>
                  <Text className='text-secondary radar-sub'>{c.top_roles.slice(0, 2).map((r) => r.role_zh).join(' · ')}</Text>
                </View>
                <Text className='radar-delta radar-delta--hc'>{c.open_roles}<Text className='radar-delta-unit'> 在招</Text></Text>
              </View>
            ))}
            <Text className='radar-footnote'>数据截至 {market.as_of} · 已连续采集 {market.days_observed} 天</Text>
          </View>

          <View className='card'>
            <Text className='card-title'>热门岗位方向</Text>
            {market.hot_roles.slice(0, 8).map((r, i) => (
              <View className='radar-row' key={r.role_id} onClick={() => goRole(r.role_id)}>
                <Text className={`radar-rank radar-rank--${Math.min(i + 1, 5)}`}>{i + 1}</Text>
                <View className='radar-info'>
                  <Text className='radar-name radar-name--single'>{r.role_zh}</Text>
                  <Text className='text-secondary radar-sub'>{r.top_companies.join(' · ')}</Text>
                </View>
                <Text className='radar-delta radar-delta--up'>{r.open_roles} ›</Text>
              </View>
            ))}
          </View>

          <View className='card'>
            <Text className='card-title'>国内技能需求 Top</Text>
            {market.top_skills.slice(0, 10).map((s) => (
              <View className='cn-skill' key={s.skill_id}>
                <Text className='cn-skill-name'>{s.name}</Text>
                <View className='cn-skill-track'><View className='cn-skill-fill' style={{ width: `${(s.share_cn / (market.top_skills[0]?.share_cn || 1)) * 100}%` }} /></View>
                <Text className='cn-skill-val'>{pct(s.share_cn)}</Text>
              </View>
            ))}
            <Text className='radar-footnote' onClick={goSkills}>占比 = 要求该技能的岗位 / 全部在招岗位 · 海外技能趋势 ›</Text>
          </View>
        </>
      )}

      {region === 'global' && (<>
      {/* ===== 公司雷达主板块 ===== */}
      <View className='card radar-card'>
        <View className='radar-tabs'>
          {RADAR_TABS.map((t) => (
            <Text
              key={t.key}
              className={`radar-tab ${radar === t.key ? 'radar-tab--active' : ''}`}
              onClick={() => setRadar(t.key)}
            >
              {t.label}
            </Text>
          ))}
        </View>

        {companies.length === 0 && radar !== 'layoff' && (
          <View className='empty'>公司数据更新中…</View>
        )}

        {/* 🔥 扩张榜：30d 净增 Top5 */}
        {radar === 'expanding' &&
          companies.length > 0 &&
          (expandingTop.length === 0 ? (
            <View className='empty'>近 30 天暂无净扩招公司</View>
          ) : (
            expandingTop.map((c, i) => (
              <View
                className='radar-row'
                key={c.domain}
                onClick={() => goCompany(c.domain)}
              >
                <Text className={`radar-rank radar-rank--${i + 1}`}>{i + 1}</Text>
                <View className='radar-info'>
                  <View className='radar-name-row'>
                    <Text className='radar-name'>{c.name}</Text>
                    {c.sector && <Text className='radar-sector'>{c.sector}</Text>}
                  </View>
                  <Text className='text-secondary radar-sub'>
                    {c.latest_open_roles ?? '—'} 在招 · 7日 {fmtSigned(c.momentum_7d?.delta ?? 0)}
                  </Text>
                </View>
                <Text className='radar-delta radar-delta--up'>
                  ▲ {fmtSigned(c.momentum_30d?.delta ?? 0)}
                  {fmtPct(c.momentum_30d?.pct)}
                </Text>
              </View>
            ))
          ))}

        {/* 📉 裁员名单：WARN 近月 Top5 */}
        {radar === 'layoff' &&
          (hiring === undefined ? (
            <View className='empty'>加载中…</View>
          ) : layoffTop.length === 0 ? (
            <View className='empty'>窗口内暂无 WARN 裁员备案</View>
          ) : (
            layoffTop.map((e, i) => (
              <View className='radar-row radar-row--static' key={`${e.employer}-${i}`}>
                <Text className={`radar-rank radar-rank--warn-${i + 1}`}>{i + 1}</Text>
                <View className='radar-info'>
                  <Text className='radar-name radar-name--single'>{e.employer}</Text>
                  <Text className='text-secondary radar-sub'>{e.month} · WARN 备案</Text>
                </View>
                <Text className='radar-delta radar-delta--down'>
                  {e.employees_affected ?? '—'} 人
                </Text>
              </View>
            ))
          ))}

        {/* 🏢 HC 大户：在招数 Top5 */}
        {radar === 'hc' &&
          companies.length > 0 &&
          hcTop.map((c, i) => (
            <View className='radar-row' key={c.domain} onClick={() => goCompany(c.domain)}>
              <Text className={`radar-rank radar-rank--${i + 1}`}>{i + 1}</Text>
              <View className='radar-info'>
                <View className='radar-name-row'>
                  <Text className='radar-name'>{c.name}</Text>
                  {c.sector && <Text className='radar-sector'>{c.sector}</Text>}
                </View>
                <Text className='text-secondary radar-sub'>
                  {STATUS_LABEL[c.status_tag || ''] || c.status_tag || ''} · 30日{' '}
                  {fmtSigned(c.momentum_30d?.delta ?? 0)}
                </Text>
              </View>
              <Text className='radar-delta radar-delta--hc'>
                {c.latest_open_roles ?? '—'}
                <Text className='radar-delta-unit'> HC</Text>
              </Text>
            </View>
          ))}

        <Text className='radar-footnote' onClick={goSkills}>
          技能风向已移至下方小卡 ›
        </Text>
      </View>

      {/* ===== 技能风向小板块 ===== */}
      <View className='card skill-mini' onClick={goSkills}>
        <View className='skill-mini-hd'>
          <Text className='skill-mini-title'>技能风向</Text>
          <Text className='skill-mini-more'>查看全部 ›</Text>
        </View>
        <View className='skill-mini-cols'>
          <View className='skill-mini-col'>
            <Text className='skill-mini-col-title skill-mini-col-title--emerging'>新兴</Text>
            {skills.emerging.slice(0, 3).map((s) => (
              <View className='skill-mini-row' key={`e-${s.skill}`}>
                <Text className='skill-mini-name'>{s.name}</Text>
                <Text className='skill-mini-val'>
                  {(s.momentum_3m || 0) >= 0 ? '+' : ''}
                  {Math.round((s.momentum_3m || 0) * 100)}%
                </Text>
              </View>
            ))}
            {skills.emerging.length === 0 && <Text className='text-secondary skill-mini-none'>—</Text>}
          </View>
          <View className='skill-mini-divider' />
          <View className='skill-mini-col'>
            <Text className='skill-mini-col-title skill-mini-col-title--rising'>上升</Text>
            {skills.rising.slice(0, 3).map((s) => (
              <View className='skill-mini-row' key={`r-${s.skill}`}>
                <Text className='skill-mini-name'>{s.name}</Text>
                <Text className='skill-mini-val'>
                  {(s.momentum_3m || 0) >= 0 ? '+' : ''}
                  {Math.round((s.momentum_3m || 0) * 100)}%
                </Text>
              </View>
            ))}
            {skills.rising.length === 0 && <Text className='text-secondary skill-mini-none'>—</Text>}
          </View>
        </View>
      </View>

      {/* ===== HN 月度招聘小卡 ===== */}
      <View className='card'>
        <Text className='card-title'>HN「Who is Hiring」近 6 月</Text>
        {hnMonths.length === 0 && <View className='empty'>数据更新中</View>}
        {hnMonths.length > 0 && (
          <>
            <View className='hn-bars'>
              {hnMonths.map((m) => (
                <View className='hn-bar-col' key={m.month}>
                  <Text className='hn-bar-val'>{m.n_job_posts ?? 0}</Text>
                  <View className='hn-bar-track'>
                    <View
                      className='hn-bar'
                      style={{
                        height: `${Math.max(10, Math.round(((m.n_job_posts || 0) / hnMax) * 100))}%`
                      }}
                    />
                  </View>
                  <Text className='hn-bar-month'>{(m.month || '').slice(5)}月</Text>
                </View>
              ))}
            </View>
            {hnLatest && (
              <Text className='hn-note'>
                最新月远程 {(hnLatest.remote_ratio != null ? hnLatest.remote_ratio * 100 : 0).toFixed(0)}
                % · 薪资披露{' '}
                {(hnLatest.salary_disclosed_ratio != null ? hnLatest.salary_disclosed_ratio * 100 : 0).toFixed(0)}%
              </Text>
            )}
          </>
        )}
      </View>
      </>)}
    </View>
  )
}
