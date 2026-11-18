import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Image } from '@tarojs/components'
import { listFavorites, MeItem } from '../../../services/me'
import './index.scss'

function formatTime(iso?: string): string {
  if (!iso) return ''
  const m = iso.match(/(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (m) return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`
  return iso.slice(0, 16)
}

export default function PathsPage() {
  const [items, setItems] = useState<MeItem[]>([])
  const [loading, setLoading] = useState(true)

  useDidShow(() => {
    setLoading(true)
    listFavorites('path').then((list) => {
      setItems(list)
      setLoading(false)
    })
  })

  const goPath = (item: MeItem) => {
    if (!item.item_id) return
    Taro.navigateTo({
      url: `/pages/path/index?job_id=${encodeURIComponent(item.item_id)}&title=${encodeURIComponent(item.title)}`
    })
  }

  return (
    <View className='container'>
      {loading && <View className='empty'>加载中…</View>}
      {!loading && items.length === 0 && <View className='empty'>在路径页点「保存此路径」留存学习路径</View>}

      {items.map((item) => (
        <View key={item.item_id} className='card me-card' onClick={() => goPath(item)}>
          <View className='me-card-main'>
            <Image className='me-card-icon' src={require('../../../assets/icons/ic-route.png')} mode='aspectFit' />
            <View className='me-card-info'>
              <Text className='me-card-title'>{item.title}</Text>
              <Text className='me-card-meta text-secondary'>保存于 {formatTime(item.created_at)}</Text>
            </View>
            <Image className='me-card-chevron' src={require('../../../assets/icons/ic-chevron.png')} mode='aspectFit' />
          </View>
          <View className='me-path-metrics'>
            <View className='me-path-metric'>
              <Image className='me-path-metric-icon' src={require('../../../assets/icons/ic-route.png')} mode='aspectFit' />
              <Text className='me-path-metric-text'>{Number(item.payload?.total_steps || 0)} 步</Text>
            </View>
            <View className='me-path-metric'>
              <Image className='me-path-metric-icon' src={require('../../../assets/icons/ic-clock.png')} mode='aspectFit' />
              <Text className='me-path-metric-text'>约 {Number(item.payload?.total_hours || 0)}h</Text>
            </View>
            {Number(item.payload?.score) > 0 && (
              <View className='me-path-metric'>
                <Image className='me-path-metric-icon' src={require('../../../assets/icons/ic-star-fill.png')} mode='aspectFit' />
                <Text className='me-path-metric-text'>{(Number(item.payload?.score) * 100).toFixed(0)}%</Text>
              </View>
            )}
          </View>
        </View>
      ))}
    </View>
  )
}
