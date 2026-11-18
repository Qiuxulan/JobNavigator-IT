import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { getSkillTrendsOverview, TrendSkillItem } from '../../services/api'
import './index.scss'

type SegmentKey = 'emerging' | 'rising' | 'declining'

const SEGMENTS: { key: SegmentKey; label: string }[] = [
  { key: 'emerging', label: '新兴' },
  { key: 'rising', label: '上升' },
  { key: 'declining', label: '衰退' }
]

const STATUS_LABEL: Record<string, string> = {
  emerging: '新兴',
  growing: '增长',
  stable: '平稳',
  declining: '衰退'
}

/** 纯 View/CSS 迷你趋势条：按 share 最大值归一化高度。 */
function Sparkline({ spark }: { spark?: { month: string; share: number }[] }) {
  const data = (spark || []).filter((p) => p.share != null)
  if (data.length < 2) return <View className='spark spark--empty' />
  const max = Math.max(...data.map((p) => p.share), 1e-6)
  return (
    <View className='spark'>
      {data.map((p, i) => (
        <View
          key={i}
          className='spark-bar'
          style={{ height: `${Math.max(8, Math.round((p.share / max) * 100))}%` }}
        />
      ))}
    </View>
  )
}

export default function SkillTrendsPage() {
  const [segment, setSegment] = useState<SegmentKey>('emerging')
  const [data, setData] = useState<Record<SegmentKey, TrendSkillItem[]>>({
    emerging: [],
    rising: [],
    declining: []
  })
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    getSkillTrendsOverview()
      .then((res) => {
        setData({
          emerging: res.emerging || [],
          rising: res.rising || [],
          declining: res.declining || []
        })
        setLoaded(true)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const list = useMemo(() => data[segment], [data, segment])

  const goDetail = (item: TrendSkillItem) => {
    Taro.navigateTo({ url: `/pages/trend-detail/index?skill=${encodeURIComponent(item.skill)}` })
  }

  return (
    <View className='container'>
      <View className='page-hero'>
        <Text className='page-hero-title'>技能风向</Text>
        <Text className='page-hero-sub'>基于全网岗位数据，洞察 IT 技能兴衰趋势</Text>
      </View>
      <View className='trends-segments'>
        {SEGMENTS.map((s) => (
          <Text
            key={s.key}
            className={`trends-segment ${segment === s.key ? 'trends-segment--active' : ''}`}
            onClick={() => setSegment(s.key)}
          >
            {s.label}
          </Text>
        ))}
      </View>

      {loading && <View className='empty'>加载中…</View>}
      {!loading && loaded && list.length === 0 && <View className='empty'>暂无数据</View>}

      {list.map((item, i) => (
        <View key={item.skill} className='card trends-item' onClick={() => goDetail(item)}>
          <View className={`trends-rank ${i < 3 ? `trends-rank--${i + 1}` : ''}`}>
            <Text className='trends-rank-no'>{i + 1}</Text>
          </View>
          <View className='trends-info'>
            <View className='trends-name-row'>
              <Text className='trends-name'>{item.name}</Text>
              <Text className={`trends-status trends-status--${item.status || ''}`}>
                {STATUS_LABEL[item.status || ''] || item.status}
              </Text>
            </View>
            <View className='trends-momentum-row'>
              <Text className='text-secondary'>3 月动能</Text>
              <Text
                className={`trends-momentum-tag ${
                  (item.momentum_3m || 0) >= 0 ? 'trends-momentum-tag--up' : 'trends-momentum-tag--down'
                }`}
              >
                {(item.momentum_3m || 0) >= 0 ? '▲ ' : '▼ '}
                {(item.momentum_3m || 0) >= 0 ? '+' : ''}
                {((item.momentum_3m || 0) * 100).toFixed(0)}%
              </Text>
              {item.yoy != null && (
                <Text className='text-secondary'>同比 {(item.yoy >= 0 ? '+' : '') + (item.yoy * 100).toFixed(0)}%</Text>
              )}
            </View>
          </View>
          <Sparkline spark={item.spark} />
        </View>
      ))}
    </View>
  )
}
