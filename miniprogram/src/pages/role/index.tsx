import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text } from '@tarojs/components'
import { getMarketRole, MarketRoleDetail, NameShare, pct } from '../../services/market'
import './index.scss'

function Bars({ rows, color }: { rows: NameShare[]; color: string }) {
  const max = rows[0]?.share || 1
  return (
    <View>
      {rows.map((r) => (
        <View className='rl-bar-row' key={r.name}>
          <Text className='rl-bar-name'>{r.name}</Text>
          <View className='rl-bar-track'>
            <View className='rl-bar-fill' style={{ width: `${(r.share / max) * 100}%`, background: color }} />
          </View>
          <Text className='rl-bar-val'>{pct(r.share)}</Text>
        </View>
      ))}
    </View>
  )
}

export default function RolePage() {
  const { params } = useRouter()
  const [d, setD] = useState<MarketRoleDetail | null | undefined>(undefined)

  useEffect(() => {
    if (!params.id) return
    getMarketRole(decodeURIComponent(params.id)).then(setD).catch(() => setD(null))
  }, [params.id])

  if (d === undefined) return <View className='container'><View className='empty'>加载中…</View></View>
  if (d === null) return <View className='container'><View className='empty'>未找到该岗位</View></View>
  const cn = d.cn
  const exp = (cn?.experience || []).filter((e) => e.name !== '未注明')

  const copy = (url: string) => {
    Taro.setClipboardData({ data: url }).then(() => Taro.showToast({ title: '投递链接已复制', icon: 'none' }))
  }

  return (
    <View className='container'>
      <View className='page-hero'>
        <Text className='page-hero-title'>{d.role_zh}</Text>
        <Text className='page-hero-sub'>{d.role_name} · 国内数据截至 {d.as_of}</Text>
      </View>

      <View className='rl-kpis'>
        <View className='rl-kpi'><Text className='rl-kpi-v'>{cn?.open_roles ?? 0}</Text><Text className='rl-kpi-l'>国内在招</Text></View>
        <View className='rl-kpi'><Text className='rl-kpi-v'>{cn?.companies[0]?.name || '—'}</Text><Text className='rl-kpi-l'>招聘最多</Text></View>
        <View className='rl-kpi'><Text className='rl-kpi-v'>{cn?.cities[0]?.name || '—'}</Text><Text className='rl-kpi-l'>主要城市</Text></View>
      </View>

      <View className='card'>
        <Text className='card-title'>技能要求（国内在招岗位中的比例）</Text>
        {cn?.top_skills.length ? (
          <View className='rl-chips'>
            {cn.top_skills.slice(0, 12).map((s) => (
              <Text className='rl-chip' key={s.skill_id}>{s.name} {pct(s.share)}</Text>
            ))}
          </View>
        ) : <View className='empty'>暂无</View>}
      </View>

      <View className='card'>
        <Text className='card-title'>公司分布</Text>
        <Bars rows={(cn?.companies || []).slice(0, 6)} color='#4f6ef7' />
        <Text className='card-title rl-gap'>城市分布</Text>
        <Bars rows={(cn?.cities || []).filter((c) => c.name !== '未注明').slice(0, 6)} color='#33cfd5' />
        {exp.length > 0 && (
          <Text className='text-secondary rl-note'>
            经验要求：{exp.slice(0, 3).map((e) => `${e.name} ${e.count} 个`).join(' · ')}
          </Text>
        )}
      </View>

      <View className='card'>
        <Text className='card-title'>正在招聘（点击复制投递链接）</Text>
        {(cn?.samples || []).map((s, i) => (
          <View className='rl-job' key={i} onClick={() => copy(s.url)}>
            <Text className='rl-job-title'>{s.title}</Text>
            <Text className='text-secondary rl-job-sub'>{s.company} · {s.city || '多地'}{s.posted_at ? ` · ${s.posted_at}` : ''}</Text>
          </View>
        ))}
        {!cn?.samples.length && <View className='empty'>暂无国内在招岗位</View>}
      </View>

      <View className='card'>
        <Text className='card-title'>海外参考</Text>
        <Text className='text-secondary rl-note'>
          海外样本 {d.global.jd_count} 条 JD{d.global.salary_usd ? ` · 薪资中位数 $${Math.round(d.global.salary_usd.median).toLocaleString()}/年` : ''}。{d.global.note}
        </Text>
      </View>
    </View>
  )
}
