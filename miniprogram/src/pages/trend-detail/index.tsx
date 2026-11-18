import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { getSkillTrendDetail, SkillTrendDetail } from '../../services/api'
import { recordHistory } from '../../services/me'
import './index.scss'

const STATUS_LABEL: Record<string, string> = {
  emerging: '新兴',
  growing: '增长',
  stable: '平稳',
  declining: '衰退'
}

const METHOD_LABEL: Record<string, string> = {
  'chronos-bolt': 'Chronos-Bolt 时序基础模型',
  holt: 'Holt 指数平滑',
  naive: '朴素法',
  seasonal_naive: '季节朴素法'
}

export default function TrendDetailPage() {
  const [detail, setDetail] = useState<SkillTrendDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const params = Taro.getCurrentInstance().router?.params || {}
    const skill = decodeURIComponent(params.skill || '')
    if (!skill) {
      setLoading(false)
      return
    }
    Taro.setNavigationBarTitle({ title: '技能详情' })
    getSkillTrendDetail(skill)
      .then((res) => {
        setDetail(res)
        Taro.setNavigationBarTitle({ title: res.name })
        recordHistory('trend', res.skill || skill, res.name)      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // 月度柱状图：最近 24 个月，按最大 share 归一化
  const chart = useMemo(() => {
    if (!detail) return { rows: [] as { month: string; height: number; share: number | null }[], max: 0 }
    const monthly = (detail.monthly || []).filter((m) => m.share != null).slice(-24)
    const max = Math.max(...monthly.map((m) => m.share as number), 1e-6)
    return {
      max,
      rows: monthly.map((m) => ({
        month: m.month,
        share: m.share as number,
        height: Math.max(4, Math.round(((m.share as number) / max) * 100))
      }))
    }
  }, [detail])

  if (loading) {
    return <View className='empty'>加载中…</View>
  }
  if (!detail) {
    return <View className='empty'>未找到该技能的数据</View>
  }

  const monthlyWithSalary = (detail.monthly || []).filter((m) => m.salary_median != null)
  const latestSalary = monthlyWithSalary[monthlyWithSalary.length - 1]?.salary_median

  return (
    <View className='container'>
      <View className='card'>
        <View className='detail-title-row'>
          <Text className='detail-name'>{detail.name}</Text>
          <Text className={`tag ${detail.status === 'declining' ? 'tag-red' : detail.status === 'emerging' ? 'tag-green' : ''}`}>
            {STATUS_LABEL[detail.status || ''] || detail.status || '未知'}
          </Text>
        </View>
        <View className='detail-metrics'>
          <View className='detail-metric'>
            <Text className='detail-metric-value'>
              {(detail.momentum_3m ?? 0) >= 0 ? '+' : ''}
              {((detail.momentum_3m ?? 0) * 100).toFixed(0)}%
            </Text>
            <Text className='detail-metric-label'>3 月动能</Text>
          </View>
          <View className='detail-metric'>
            <Text className='detail-metric-value'>
              {detail.yoy != null ? `${(detail.yoy >= 0 ? '+' : '') + (detail.yoy * 100).toFixed(0)}%` : '--'}
            </Text>
            <Text className='detail-metric-label'>同比</Text>
          </View>
          <View className='detail-metric'>
            <Text className='detail-metric-value'>
              {latestSalary != null ? `¥${Math.round(latestSalary)}k` : '--'}
            </Text>
            <Text className='detail-metric-label'>最新中位月薪</Text>
          </View>
        </View>
      </View>

      <View className='card'>
        <Text className='detail-section-title'>月度需求占比（近 24 月）</Text>
        <View className='bar-chart'>
          {chart.rows.map((r) => (
            <View key={r.month} className='bar-col'>
              <View className='bar-track'>
                <View className='bar-fill' style={{ height: `${r.height}%` }} />
              </View>
            </View>
          ))}
        </View>
        {chart.rows.length > 0 && (
          <View className='bar-labels'>
            <Text className='bar-label'>{chart.rows[0].month}</Text>
            <Text className='bar-label'>{chart.rows[chart.rows.length - 1].month}</Text>
          </View>
        )}
      </View>

      {detail.forecast && (
        <View className='card'>
          <Text className='detail-section-title'>趋势预测（{METHOD_LABEL[detail.forecast.method || ''] || detail.forecast.method || 'holt'}）</Text>
          <View className='detail-metrics'>
            <View className='detail-metric'>
              <Text className='detail-metric-value'>{((detail.forecast.m3 ?? 0) * 100).toFixed(2)}%</Text>
              <Text className='detail-metric-label'>3 月后预测占比</Text>
            </View>
            <View className='detail-metric'>
              <Text className='detail-metric-value'>{((detail.forecast.m6 ?? 0) * 100).toFixed(2)}%</Text>
              <Text className='detail-metric-label'>6 月后预测占比</Text>
            </View>
            <View className='detail-metric'>
              <Text className='detail-metric-value'>
                {detail.forecast.mape != null ? `${(detail.forecast.mape * 100).toFixed(0)}%` : '--'}
              </Text>
              <Text className='detail-metric-label'>
                回测误差 MAPE{detail.forecast.mape != null ? `（可信度${detail.forecast.mape < 0.2 ? '高' : detail.forecast.mape < 0.4 ? '中' : '低'}）` : ''}
              </Text>
            </View>
          </View>
        </View>
      )}

      <View className='card'>
        <Text className='detail-section-title'>说明</Text>
        <Text className='detail-desc text-secondary'>
          占比 = 该技能在当月全部岗位 JD 中出现的频率。动能与同比基于月度序列计算，预测由 Holt
          双指数平滑生成。数据截止 {detail.analysis_end || '--'}。
        </Text>
      </View>
    </View>
  )
}
