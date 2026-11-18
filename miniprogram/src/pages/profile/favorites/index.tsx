import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Image } from '@tarojs/components'
import { listFavorites, MeItem, removeFavorite } from '../../../services/me'
import './index.scss'

type FavType = 'job' | 'news'

const SEGMENTS: { key: FavType; label: string }[] = [
  { key: 'job', label: '岗位' },
  { key: 'news', label: '新闻' }
]

function formatTime(iso?: string): string {
  if (!iso) return ''
  const m = iso.match(/(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (m) return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`
  return iso.slice(0, 16)
}

export default function FavoritesPage() {
  const [type, setType] = useState<FavType>('job')
  const [items, setItems] = useState<MeItem[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = async (t: FavType) => {
    setLoading(true)
    const list = await listFavorites(t)
    setItems(list)
    setLoading(false)
  }

  useDidShow(() => {
    refresh(type)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  })

  const switchType = (t: FavType) => {
    setType(t)
    refresh(t)
  }

  const onItemClick = (item: MeItem) => {
    if (type === 'job') {
      Taro.navigateTo({
        url: `/pages/path/index?job_id=${encodeURIComponent(item.item_id)}&title=${encodeURIComponent(item.title)}`
      })
    } else {
      // 新闻详情在 tab 页内，跳回新闻页
      Taro.switchTab({ url: '/pages/news/index' })
    }
  }

  const onRemove = (e: any, item: MeItem) => {
    e.stopPropagation()
    Taro.showModal({
      title: '取消收藏',
      content: `确定不再收藏「${item.title}」吗？`,
      confirmText: '取消收藏',
      confirmColor: '#f04438'
    })
      .then(async (res) => {
        if (!res.confirm) return
        setItems((prev) => prev.filter((it) => it.item_id !== item.item_id))
        await removeFavorite(type, item.item_id)
      })
      .catch(() => {})
  }

  return (
    <View className='container me-page'>
      <View className='me-tabs'>
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

      {loading && <View className='empty'>加载中…</View>}
      {!loading && items.length === 0 && (
        <View className='empty'>{type === 'job' ? '在匹配页点星标收藏岗位' : '在新闻页点星标收藏新闻'}</View>
      )}

      {items.map((item) => (
        <View key={item.item_id} className='card me-card' onClick={() => onItemClick(item)}>
          <View className='me-card-main'>
            <Image
              className='me-card-icon'
              src={require(`../../../assets/icons/${type === 'job' ? 'ic-briefcase' : 'ic-bookmark'}.png`)}
              mode='aspectFit'
            />
            <View className='me-card-info'>
              <Text className='me-card-title'>{item.title}</Text>
              <Text className='me-card-meta text-secondary'>
                {type === 'job'
                  ? `匹配度 ${(Number(item.payload?.final_score || 0) * 100).toFixed(0)}% · 收藏于 ${formatTime(item.created_at)}`
                  : `${item.payload?.source || '资讯'} · ${formatTime(item.payload?.published_at || item.created_at)}`}
              </Text>
            </View>
            <View className='me-card-del' onClick={(e) => onRemove(e, item)}>
              <Text className='me-card-del-x'>✕</Text>
            </View>
          </View>
        </View>
      ))}
    </View>
  )
}
