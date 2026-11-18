import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Image } from '@tarojs/components'
import { clearAllHistory, HistoryType, listHistory, MeItem } from '../../../services/me'
import './index.scss'

const SEGMENTS: { key: HistoryType; label: string }[] = [
  { key: 'news', label: '新闻' },
  { key: 'trend', label: '趋势' },
  { key: 'match', label: '匹配' }
]

function formatTime(iso?: string): string {
  if (!iso) return ''
  const m = iso.match(/(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (m) return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`
  return iso.slice(0, 16)
}

export default function HistoryPage() {
  const [type, setType] = useState<HistoryType>('news')
  const [items, setItems] = useState<MeItem[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = async (t: HistoryType) => {
    setLoading(true)
    const list = await listHistory(t, 20)
    setItems(list)
    setLoading(false)
  }

  useDidShow(() => {
    refresh(type)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  })

  const switchType = (t: HistoryType) => {
    setType(t)
    refresh(t)
  }

  const onItemClick = (item: MeItem) => {
    if (type === 'trend') {
      Taro.navigateTo({ url: `/pages/trend-detail/index?skill=${encodeURIComponent(item.item_id)}` })
    } else if (type === 'news') {
      Taro.switchTab({ url: '/pages/news/index' })
    } else {
      Taro.switchTab({ url: '/pages/match/index' })
    }
  }

  const onClear = () => {
    Taro.showModal({
      title: '清空浏览历史',
      content: '将清空全部（新闻 / 趋势 / 匹配）浏览历史，且不可恢复。',
      confirmText: '清空',
      confirmColor: '#f04438'
    })
      .then(async (res) => {
        if (!res.confirm) return
        await clearAllHistory()
        setItems([])
        Taro.showToast({ title: '已清空', icon: 'success' })
      })
      .catch(() => {})
  }

  const iconFor = (t: HistoryType) =>
    t === 'news' ? 'ic-bookmark' : t === 'trend' ? 'ic-history' : 'ic-briefcase'

  return (
    <View className='container me-page'>
      <View className='me-history-header'>
        <View className='me-tabs me-tabs--compact'>
          {SEGMENTS.map((s) => (
            <Text
              key={s.key}
              className={`me-tab ${type === s.key ? 'me-tab--active' : ''}`}
              onClick={() => switchType(s.key)}
            >
              {s.label}
            </Text>
          ))}
        </View>
        <View className='me-clear-btn' onClick={onClear}>
          <Image className='me-clear-btn-icon' src={require('../../../assets/icons/ic-trash.png')} mode='aspectFit' />
          <Text className='me-clear-btn-text'>清空</Text>
        </View>
      </View>

      {loading && <View className='empty'>加载中…</View>}
      {!loading && items.length === 0 && <View className='empty'>暂无浏览记录</View>}

      {items.map((item) => (
        <View key={item.item_id} className='card me-card' onClick={() => onItemClick(item)}>
          <View className='me-card-main'>
            <Image className='me-card-icon' src={require(`../../../assets/icons/${iconFor(type)}.png`)} mode='aspectFit' />
            <View className='me-card-info'>
              <Text className='me-card-title'>{item.title}</Text>
              <Text className='me-card-meta text-secondary'>{formatTime(item.created_at)}</Text>
            </View>
            <Image className='me-card-chevron' src={require('../../../assets/icons/ic-chevron.png')} mode='aspectFit' />
          </View>
        </View>
      ))}
    </View>
  )
}
