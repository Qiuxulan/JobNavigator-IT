import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { getCompanyDetail, CompanyDetail } from '../../services/api'
import './index.scss'

const STATUS_LABEL: Record<string, string> = {
  expanding: '扩张中',
  shrinking: '裁员中',
  cooling: '收缩中',
  stable: '平稳'
}

const STATUS_CLASS: Record<string, string> = {
  expanding: 'cmp-status--expanding',
  shrinking: 'cmp-status--shrinking',
  cooling: 'cmp-status--cooling',
  stable: 'cmp-status--stable'
}

const fmtDelta = (d?: number | null) => (d == null ? '—' : `${d >= 0 ? '+' : ''}${d.toFixed(0)}`)

/** 在招岗位日度走势：纯 View 柱状条，以窗口内最大值为 100%。 */
function DailyChart({ daily }: { daily: { date?: string; count?: number | null }[] }) {
  const data = (daily || []).filter((p) => p.count != null)
  if (data.length < 2) return <View className='cmp-chart-empty'>日度数据更新中</View>
  const max = Math.max(...data.map((p) => p.count as number), 1)
  const min = Math.min(...data.map((p) => p.count as number))
  const last = data[data.length - 1]
  return (
    <View>
      <View className='cmp-chart-legend'>
        <Text className='text-secondary'>峰值 {max}</Text>
        <Text className='text-secondary'>
          {(last.date || '').slice(5)} 最新 {last.count}
        </Text>
      </View>
      <View className='cmp-chart'>
        {data.map((p, i) => (
          <View
            key={i}
            className={`cmp-chart-bar ${i === data.length - 1 ? 'cmp-chart-bar--last' : ''}`}
            style={{ height: `${Math.max(8, Math.round(((p.count as number) / max) * 100))}%` }}
          />
        ))}
      </View>
      <View className='cmp-chart-axis'>
        <Text className='text-secondary'>{data[0].date}</Text>
        <Text className='text-secondary'>窗口最低 {min}</Text>
        <Text className='text-secondary'>{last.date}</Text>
      </View>
    </View>
  )
}

export default function CompanyPage() {
  const [detail, setDetail] = useState<CompanyDetail | null | undefined>(undefined)

  useEffect(() => {
    const params = Taro.getCurrentInstance().router?.params || {}
    const domain = decodeURIComponent(params.domain || '')
    if (!domain) {
      setDetail(null)
      return
    }
    getCompanyDetail(domain)
      .then((res) => {
        setDetail(res)
        if (res.name) {
          Taro.setNavigationBarTitle({ title: res.name })
        }
      })
      .catch(() => setDetail(null))
  }, [])

  const tag = detail?.status_tag || 'stable'
  const layoffs = useMemo(() => detail?.layoff_events || [], [detail])
  const news = useMemo(() => detail?.related_news || [], [detail])

  // 微信小程序无法直接打开外部链接，复制到剪贴板兜底（与新闻页一致）
  const copyLink = (url?: string) => {
    if (!url) {
      Taro.showToast({ title: '该新闻暂无原文链接', icon: 'none' })
      return
    }
    Taro.setClipboardData({
      data: url,
      success: () => {
        Taro.showToast({ title: '链接已复制，粘贴到浏览器打开', icon: 'none', duration: 2500 })
      }
    })
  }

  if (detail === undefined) {
    return (
      <View className='container'>
        <View className='empty'>加载中…</View>
      </View>
    )
  }
  if (detail === null) {
    return (
      <View className='container'>
        <View className='empty'>未找到该公司，数据可能更新中</View>
      </View>
    )
  }

  return (
    <View className='container'>
      {/* 头部：公司名 + sector + 状态 */}
      <View className='card cmp-head'>
        <View className='cmp-title-row'>
          <Text className='cmp-name'>{detail.name}</Text>
          <Text className={`cmp-status ${STATUS_CLASS[tag] || ''}`}>
            {STATUS_LABEL[tag] || tag}
          </Text>
        </View>
        <View className='cmp-tags'>
          {detail.sector && <Text className='tag'>{detail.sector}</Text>}
          <Text className='tag tag-gray'>{detail.domain}</Text>
        </View>
      </View>

      {/* 核心指标 */}
      <View className='card'>
        <View className='cmp-metrics'>
          <View className='cmp-metric'>
            <Text className='cmp-metric-num'>{detail.latest_open_roles ?? '—'}</Text>
            <Text className='text-secondary'>官网在招岗位</Text>
          </View>
          <View className='cmp-metric'>
            <Text
              className={`cmp-metric-num ${
                (detail.momentum_7d?.delta ?? 0) >= 0 ? 'cmp-metric-num--up' : 'cmp-metric-num--down'
              }`}
            >
              {fmtDelta(detail.momentum_7d?.delta)}
            </Text>
            <Text className='text-secondary'>
              7 日净增
              {detail.momentum_7d?.pct != null &&
                ` · ${((detail.momentum_7d?.pct ?? 0) >= 0 ? '+' : '')}${(
                  (detail.momentum_7d?.pct ?? 0) * 100
                ).toFixed(1)}%`}
            </Text>
          </View>
          <View className='cmp-metric'>
            <Text
              className={`cmp-metric-num ${
                (detail.momentum_30d?.delta ?? 0) >= 0 ? 'cmp-metric-num--up' : 'cmp-metric-num--down'
              }`}
            >
              {fmtDelta(detail.momentum_30d?.delta)}
            </Text>
            <Text className='text-secondary'>
              30 日净增
              {detail.momentum_30d?.pct != null &&
                ` · ${((detail.momentum_30d?.pct ?? 0) >= 0 ? '+' : '')}${(
                  (detail.momentum_30d?.pct ?? 0) * 100
                ).toFixed(1)}%`}
            </Text>
          </View>
        </View>
        {detail.open_roles_avg_30d != null && (
          <Text className='cmp-avg'>30 日平均在招 {detail.open_roles_avg_30d.toFixed(0)} 个</Text>
        )}
      </View>

      {/* 在招岗位日度走势 */}
      <View className='card'>
        <Text className='card-title'>在招岗位走势（日度）</Text>
        <DailyChart daily={detail.open_roles_daily || []} />
      </View>

      {/* 裁员记录 */}
      {layoffs.length > 0 && (
        <View className='card'>
          <Text className='card-title'>WARN 裁员备案</Text>
          {layoffs.map((e, i) => (
            <View className='cmp-layoff-row' key={`${e.month}-${i}`}>
              <View className='cmp-layoff-info'>
                <Text className='cmp-layoff-month'>{e.month}</Text>
                <Text className='text-secondary cmp-layoff-sub'>
                  {(e.states || []).join(' / ') || '—'}
                  {(e.event_types || []).includes('closure') ? ' · 含关闭' : ''}
                  {e.latest_effective_date && e.latest_effective_date !== 'nan'
                    ? ` · 生效 ${e.latest_effective_date}`
                    : ''}
                </Text>
              </View>
              <View className='cmp-layoff-num-wrap'>
                <Text className='cmp-layoff-num'>{e.employees_affected ?? '—'}</Text>
                <Text className='text-secondary'>人 · {e.n_notices ?? 0} 份备案</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* 相关新闻 */}
      <View className='card'>
        <Text className='card-title'>相关动态</Text>
        {news.length === 0 && <Text className='text-secondary cmp-news-none'>近期暂无相关新闻</Text>}
        {news.map((n, i) => (
          <View className='cmp-news-row' key={i} onClick={() => copyLink(n.url)}>
            <View className='cmp-news-info'>
              <Text className='cmp-news-title'>{n.title}</Text>
              <Text className='text-secondary cmp-news-meta'>
                {n.source || '未知来源'}
                {n.published_at ? ` · ${(n.published_at || '').slice(0, 10)}` : ''} · 点击复制链接
              </Text>
            </View>
          </View>
        ))}
      </View>

      {/* 数据说明 */}
      <Text className='cmp-note'>
        数据窗口 {detail.window?.[0] || '—'} ~ {detail.window?.[1] || '—'} · 来源：
        公司官网在招岗位日度采样（roletrends 数据集）；裁员为美国 WARN Act 备案口径（
        {detail.layoff_source ? 'APProjects 数据集' : '未匹配到记录'}）；新闻来自站内情报库。更新于{' '}
        {(detail.generated_at || '').slice(0, 10) || '—'}。
      </Text>
    </View>
  )
}
