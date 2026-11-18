import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, Image } from '@tarojs/components'
import { getNewsCategories, getSkillTrendsOverview } from '../../services/api'
import { fetchOverview, MeOverview, resolveNickname, updateNickname } from '../../services/me'
import { clearCache, getJoinedAt, getNickname, setNickname } from '../../utils/store'
import './index.scss'

const APP_VERSION = '1.2.0'

const ic = (name: string) => require(`../../assets/icons/${name}.png`)

function formatTime(iso?: string): string {
  if (!iso) return ''
  const m = iso.match(/(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (m) return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`
  return iso.slice(0, 16)
}

function joinedDays(joinedAt: string): number {
  const t = new Date(joinedAt).getTime()
  if (!t) return 1
  return Math.max(1, Math.floor((Date.now() - t) / 86400000) + 1)
}

const GRID_ITEMS = [
  { key: 'favorites', label: '我的收藏', icon: 'ic-bookmark', url: '/pages/profile/favorites/index' },
  { key: 'paths', label: '学习路径', icon: 'ic-route', url: '/pages/profile/paths/index' },
  { key: 'history', label: '浏览历史', icon: 'ic-history', url: '/pages/profile/history/index' },
  { key: 'settings', label: '设置', icon: 'ic-settings', url: '' }
]

export default function ProfilePage() {
  const [overview, setOverview] = useState<MeOverview | null>(null)
  const [nickname, setNick] = useState('IT 探索者')
  const [joinedAt, setJoinedAt] = useState('')
  const [dataUpdatedAt, setDataUpdatedAt] = useState('')
  const [serviceStatus, setServiceStatus] = useState<{ ok: boolean; ms: number } | null>(null)

  const refresh = async () => {
    setNick(getNickname() || 'IT 探索者')
    setJoinedAt(getJoinedAt())
    const ov = await fetchOverview()
    setOverview(ov)
    setNick(resolveNickname(ov))
    if (ov?.joined_at) setJoinedAt(ov.joined_at)
  }

  useDidShow(() => {
    refresh()
    getSkillTrendsOverview()
      .then((res: any) => {
        const t = res?.generated_at || res?.analysis_end
        if (t) setDataUpdatedAt(String(t))
      })
      .catch(() => {})
  })

  const editNickname = () => {
    // Taro 类型未包含 editable（基础库 2.17.0+ 支持），此处显式放宽
    Taro.showModal({
      title: '修改昵称',
      editable: true,
      placeholderText: '输入你的昵称',
      content: nickname === 'IT 探索者' ? '' : nickname
    } as any)
      .then(async (res: any) => {
        if (!res.confirm) return
        const name = (res.content || '').trim()
        if (!name) return
        setNick(name)
        setNickname(name)
        const synced = await updateNickname(name)
        Taro.showToast({ title: synced ? '昵称已保存' : '已保存在本地', icon: 'success' })
      })
      .catch(() => {})
  }

  const goGrid = (item: (typeof GRID_ITEMS)[number]) => {
    if (item.key === 'settings') {
      Taro.pageScrollTo({ selector: '.profile-settings-anchor', duration: 200 }).catch(() => {})
      return
    }
    Taro.navigateTo({ url: item.url })
  }

  const favCount =
    (overview?.favorite_counts.job || 0) +
    (overview?.favorite_counts.news || 0) +
    (overview?.favorite_counts.path || 0)
  const browseCount =
    (overview?.history_counts.news || 0) +
    (overview?.history_counts.trend || 0) +
    (overview?.history_counts.match || 0)

  const doClearCache = () => {
    Taro.showActionSheet({
      itemList: ['清除推荐收藏', '清除新闻收藏', '清除路径存档', '清除浏览历史', '全部清除']
    })
      .then((res) => {
        const map = ['favorites', 'favorites', 'paths', 'history', 'all'] as const
        // 收藏类包含岗位与新闻两类，单独「清除新闻收藏」时用 favorites 一并清掉（本地键相邻）
        const cat = res.tapIndex === 1 ? 'favorites' : map[res.tapIndex]
        clearCache(cat)
        refresh()
        Taro.showToast({ title: '已清除', icon: 'success' })
      })
      .catch(() => {})
  }

  const doClearCloud = () => {
    Taro.showModal({
      title: '清空云端记录',
      content: '将清空服务器上保存的全部浏览历史（收藏不受影响）。',
      confirmText: '清空',
      confirmColor: '#f04438'
    })
      .then(async (res) => {
        if (!res.confirm) return
        const { clearAllHistory } = await import('../../services/me')
        await clearAllHistory()
        refresh()
        Taro.showToast({ title: '云端记录已清空', icon: 'success' })
      })
      .catch(() => {})
  }

  const checkService = async () => {
    setServiceStatus(null)
    const start = Date.now()
    try {
      await getNewsCategories()
      setServiceStatus({ ok: true, ms: Date.now() - start })
    } catch (e) {
      setServiceStatus({ ok: false, ms: Date.now() - start })
    }
  }

  const showAbout = () => {
    Taro.showModal({
      title: `JobNavigator v${APP_VERSION}`,
      content:
        'IT 岗位趋势洞察与学习路径助手。\n\n' +
        '数据来源：GDELT 全球新闻事件库与全网 IT 岗位样本，经 NLP 抽取与趋势建模。\n\n' +
        (dataUpdatedAt ? `数据更新：${formatTime(dataUpdatedAt)}` : ''),
      showCancel: false
    })
  }

  return (
    <View className='container profile-page'>
      {/* 顶部用户区 */}
      <View className='profile-hero'>
        <View className='profile-hero-avatar' onClick={editNickname}>
          <Text className='profile-hero-avatar-text'>{nickname.slice(0, 1) || '🧭'}</Text>
          <View className='profile-hero-edit'>
            <Image className='profile-hero-edit-icon' src={ic('ic-edit-white')} mode='aspectFit' />
          </View>
        </View>
        <View className='profile-hero-info' onClick={editNickname}>
          <View className='profile-hero-name-row'>
            <Text className='profile-hero-name'>{nickname}</Text>
            <Image className='profile-hero-name-edit' src={ic('ic-edit-white')} mode='aspectFit' />
          </View>
          <Text className='profile-hero-joined'>加入 JobNavigator {joinedAt ? joinedDays(joinedAt) : 1} 天</Text>
        </View>
      </View>

      {/* 数据统计条 */}
      <View className='profile-stats'>
        <View className='profile-stat' onClick={() => Taro.navigateTo({ url: '/pages/profile/favorites/index' })}>
          <Text className='profile-stat-value'>{overview ? favCount : '-'}</Text>
          <Text className='profile-stat-label'>收藏</Text>
        </View>
        <View className='profile-stat-divider' />
        <View className='profile-stat' onClick={() => Taro.navigateTo({ url: '/pages/profile/paths/index' })}>
          <Text className='profile-stat-value'>{overview ? overview.favorite_counts.path : '-'}</Text>
          <Text className='profile-stat-label'>学习路径</Text>
        </View>
        <View className='profile-stat-divider' />
        <View className='profile-stat' onClick={() => Taro.navigateTo({ url: '/pages/profile/history/index' })}>
          <Text className='profile-stat-value'>{overview ? browseCount : '-'}</Text>
          <Text className='profile-stat-label'>浏览</Text>
        </View>
      </View>

      {/* 功能宫格 */}
      <View className='profile-grid'>
        {GRID_ITEMS.map((item) => (
          <View key={item.key} className='profile-grid-item' onClick={() => goGrid(item)}>
            <View className='profile-grid-icon-wrap'>
              <Image className='profile-grid-icon' src={ic(item.icon)} mode='aspectFit' />
            </View>
            <Text className='profile-grid-label'>{item.label}</Text>
          </View>
        ))}
      </View>

      {/* 设置组 */}
      <View className='profile-settings-anchor' />
      <View className='card profile-settings'>
        <View className='profile-settings-row' onClick={doClearCache}>
          <View className='profile-settings-left'>
            <Image className='profile-settings-icon' src={ic('ic-trash')} mode='aspectFit' />
            <Text className='profile-settings-label'>清空缓存</Text>
          </View>
          <Image className='profile-settings-chevron' src={ic('ic-chevron')} mode='aspectFit' />
        </View>
        <View className='profile-settings-row' onClick={doClearCloud}>
          <View className='profile-settings-left'>
            <Image className='profile-settings-icon' src={ic('ic-database')} mode='aspectFit' />
            <Text className='profile-settings-label'>清空云端记录</Text>
          </View>
          <Image className='profile-settings-chevron' src={ic('ic-chevron')} mode='aspectFit' />
        </View>
        <View className='profile-settings-row' onClick={checkService}>
          <View className='profile-settings-left'>
            <Image className='profile-settings-icon' src={ic('ic-refresh')} mode='aspectFit' />
            <Text className='profile-settings-label'>后端服务状态</Text>
          </View>
          {serviceStatus === null ? (
            <Image className='profile-settings-chevron' src={ic('ic-chevron')} mode='aspectFit' />
          ) : (
            <Text className={`profile-status ${serviceStatus.ok ? 'profile-status--ok' : 'profile-status--fail'}`}>
              {serviceStatus.ok ? `正常 · ${serviceStatus.ms}ms` : '连接失败'}
            </Text>
          )}
        </View>
        <View className='profile-settings-row profile-settings-row--last' onClick={showAbout}>
          <View className='profile-settings-left'>
            <Image className='profile-settings-icon' src={ic('ic-info')} mode='aspectFit' />
            <Text className='profile-settings-label'>关于 JobNavigator</Text>
          </View>
          <View className='profile-settings-right'>
            <Text className='profile-settings-value'>v{APP_VERSION}</Text>
            <Image className='profile-settings-chevron' src={ic('ic-chevron')} mode='aspectFit' />
          </View>
        </View>
      </View>
    </View>
  )
}
