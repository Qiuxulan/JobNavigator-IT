import { useCallback, useEffect, useState } from 'react'
import Taro, { usePullDownRefresh, useReachBottom } from '@tarojs/taro'
import { View, Text, Image } from '@tarojs/components'
import { getNews, getNewsCategories, NewsItem } from '../../services/api'
import { fetchFavoriteIds, recordHistory, setNewsFavorite } from '../../services/me'
import './index.scss'

const PAGE_SIZE = 20

const CATEGORY_LABEL: Record<string, string> = {
  tech_general: '技术综合',
  product_release: '产品发布',
  research: '研究',
  funding: '融资',
  security: '安全',
  policy: '政策',
  layoff: '裁员',
  hiring: '招聘'
}

function formatDate(iso?: string): string {
  if (!iso) return ''
  // 2026-11-04T22:00:23+00:00 → 11-04 22:00
  const m = iso.match(/(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (m) return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`
  return iso.slice(0, 16)
}

export default function NewsPage() {
  const [categories, setCategories] = useState<{ key: string; count: number }[]>([])
  const [activeCat, setActiveCat] = useState('')
  const [items, setItems] = useState<NewsItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [noMore, setNoMore] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [favIds, setFavIds] = useState<Record<string, boolean>>({})

  useEffect(() => {
    getNewsCategories()
      .then((res) => {
        const list = Object.entries(res.categories || {})
          .map(([key, count]) => ({ key, count }))
          .sort((a, b) => b.count - a.count)
        setCategories(list)
      })
      .catch(() => {})
    // 加载收藏标星状态（云端优先，失败回退本地缓存）
    fetchFavoriteIds('news').then((ids) => setFavIds(ids)).catch(() => {})
  }, [])

  const fetchPage = useCallback(
    async (targetPage: number, cat: string, append: boolean) => {
      if (loading) return
      setLoading(true)
      try {
        const res = await getNews({ page: targetPage, page_size: PAGE_SIZE, category: cat || undefined })
        setTotal(res.total)
        setPage(res.page)
        setNoMore(res.page * res.page_size >= res.total)
        setItems((prev) => (append ? [...prev, ...res.items] : res.items))
      } catch (e) {
        // request 内已统一提示
      } finally {
        setLoading(false)
      }
    },
    [loading]
  )

  useEffect(() => {
    fetchPage(1, activeCat, false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCat])

  usePullDownRefresh(() => {
    fetchPage(1, activeCat, false).finally(() => Taro.stopPullDownRefresh())
  })

  useReachBottom(() => {
    if (!loading && !noMore) {
      fetchPage(page + 1, activeCat, true)
    }
  })

  const toggleExpand = (id: string) => {
    if (expandedId !== id) {
      const item = items.find((n) => n.news_id === id)
      if (item) recordHistory('news', item.news_id, item.title, { source: item.source, url: item.url })
    }
    setExpandedId(expandedId === id ? null : id)
  }

  const toggleFav = async (e: any, item: NewsItem) => {
    e.stopPropagation()
    const next = !favIds[item.news_id]
    setFavIds((prev) => ({ ...prev, [item.news_id]: next }))
    Taro.showToast({ title: next ? '已收藏' : '已取消收藏', icon: 'none' })
    await setNewsFavorite(item, next)
  }

  const copy = (data: string, label: string) => {
    Taro.setClipboardData({ data }).then(() => {
      Taro.showToast({ title: `${label}已复制`, icon: 'none' })
    })
  }

  // 微信小程序无法直接打开外部链接（web-view 需企业主体+备案域名），复制到剪贴板兜底
  const readOriginal = (e: any, url: string) => {
    e.stopPropagation()
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

  return (
    <View className='news-page'>
      <View className='page-hero news-hero'>
        <Text className='page-hero-title'>IT 新闻</Text>
        <Text className='page-hero-sub'>追踪行业动态与技术热点</Text>
      </View>
      <View className='news-tabs'>
        <Text
          className={`news-tab ${activeCat === '' ? 'news-tab--active' : ''}`}
          onClick={() => setActiveCat('')}
        >
          全部
        </Text>
        {categories.map((c) => (
          <Text
            key={c.key}
            className={`news-tab ${activeCat === c.key ? 'news-tab--active' : ''}`}
            onClick={() => setActiveCat(c.key)}
          >
            {CATEGORY_LABEL[c.key] || c.key} {c.count}
          </Text>
        ))}
      </View>

      <View className='container'>
        {items.length === 0 && !loading && <View className='empty'>暂无新闻</View>}
        {items.map((n) => (
          <View key={n.news_id} className='card news-card' onClick={() => toggleExpand(n.news_id)}>
            <View className='news-title-row'>
              <Text className='news-title'>{n.title}</Text>
              {!!n.url && (
                <Image
                  className='news-title-link'
                  src={require('../../assets/icons/ic-external-link.png')}
                  mode='aspectFit'
                />
              )}
            </View>
            <View className='news-meta-row'>
              <Text className='news-meta text-secondary'>
                {n.source || ''} · {formatDate(n.published_at)}
              </Text>
              <View className='news-meta-right'>
                <Text className={`news-cat news-cat--${n.category || 'default'}`}>
                  {CATEGORY_LABEL[n.category || ''] || n.category || '资讯'}
                </Text>
                <Image
                  className='news-fav-img'
                  src={
                    favIds[n.news_id]
                      ? require('../../assets/icons/ic-star-fill.png')
                      : require('../../assets/icons/ic-star-outline.png')
                  }
                  mode='aspectFit'
                  onClick={(e) => toggleFav(e, n)}
                />
              </View>
            </View>
            {(n.skills || []).length > 0 && (
              <View className='news-skills'>
                {(n.skills || []).slice(0, 6).map((s) => (
                  <Text key={s} className='tag tag-gray'>{s}</Text>
                ))}
              </View>
            )}
            {expandedId === n.news_id && (
              <View className='news-detail'>
                <Text className='news-summary'>{n.summary || '（暂无摘要，可点击下方按钮复制原文链接阅读全文）'}</Text>
                <View className='news-actions'>
                  <View className='news-read-origin' onClick={(e) => readOriginal(e, n.url)}>
                    <Image
                      className='news-read-origin-icon'
                      src={require('../../assets/icons/ic-external-white.png')}
                      mode='aspectFit'
                    />
                    <Text className='news-read-origin-text'>阅读原文</Text>
                  </View>
                  {n.summary && (
                    <Text className='news-action' onClick={() => copy(`${n.title}\n\n${n.summary}`, '摘要')}>复制标题+摘要</Text>
                  )}
                </View>
              </View>
            )}
            <Text className='news-expand-hint text-secondary'>
              {expandedId === n.news_id ? '收起 ▴' : '展开详情 ▾'}
            </Text>
          </View>
        ))}
        {loading && <View className='empty'>加载中…</View>}
        {!loading && noMore && items.length > 0 && <View className='empty'>已经到底啦</View>}
        <View className='news-footer-total text-secondary'>共 {total} 条</View>
      </View>
    </View>
  )
}
