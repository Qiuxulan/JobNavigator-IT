import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, Input, ScrollView, Image } from '@tarojs/components'
import {
  getRolesCatalog,
  postRecommend,
  RoleCatalogItem,
  RecommendationItem
} from '../../services/api'
import { getUserId } from '../../utils/user'
import { getStoredSkills, getStoredTargetRole, saveProfile, PREFILL_MESSAGE_KEY } from '../../utils/store'
import { fetchFavoriteIds, recordHistory, setJobFavorite } from '../../services/me'
import './index.scss'

/** 把后端 explanation 特征串（covered=4 missing=11 hours=235 ...）转成可读文案 */
function formatExplanation(raw?: string): string {
  if (!raw) return ''
  const get = (k: string) => {
    const m = raw.match(new RegExp(`${k}=([\\d.]+)`))
    return m ? Number(m[1]) : null
  }
  const parts: string[] = []
  const covered = get('covered')
  const missing = get('missing')
  const hours = get('hours')
  if (covered !== null) parts.push(`已具备 ${covered} 项核心技能`)
  if (missing !== null && missing > 0) parts.push(`待补齐 ${missing} 项`)
  if (hours !== null && hours > 0) parts.push(`预计 ${hours} 学时`)
  return parts.join(' · ') || raw
}

export default function MatchPage() {
  const [roles, setRoles] = useState<RoleCatalogItem[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [targetRole, setTargetRole] = useState<RoleCatalogItem | null>(null)
  const [skills, setSkills] = useState<string[]>([])
  const [skillInput, setSkillInput] = useState('')
  const [recommendItems, setRecommendItems] = useState<RecommendationItem[]>([])
  const [recommending, setRecommending] = useState(false)
  const [recommended, setRecommended] = useState(false)
  const [favIds, setFavIds] = useState<Record<string, boolean>>({})

  useEffect(() => {
    // 从本地档案恢复已选技能与目标岗位
    const storedSkills = getStoredSkills()
    if (storedSkills.length) setSkills(storedSkills)
    const storedRole = getStoredTargetRole()
    getRolesCatalog()
      .then((res) => {
        const list = res.roles || []
        setRoles(list)
        const cats: string[] = []
        list.forEach((r) => {
          const c = r.coarse_role || '其他'
          if (!cats.includes(c)) cats.push(c)
        })
        setCategories(cats)
        if (cats.length) setExpanded({ [cats[0]]: true })
        if (storedRole && storedRole.role_id) {
          const found = list.find((r) => r.role_id === storedRole.role_id)
          if (found) setTargetRole(found)
        }
      })
      .catch(() => {})
  }, [])

  const rolesByCategory = useMemo(() => {
    const map: Record<string, RoleCatalogItem[]> = {}
    roles.forEach((r) => {
      const c = r.coarse_role || '其他'
      if (!map[c]) map[c] = []
      map[c].push(r)
    })
    return map
  }, [roles])

  const toggleCategory = (cat: string) => setExpanded((prev) => ({ ...prev, [cat]: !prev[cat] }))

  const selectRole = (role: RoleCatalogItem) => {
    setTargetRole(role)
    // 选中岗位后，将其技能展示为可点选 chips（不自动覆盖用户已选技能）
  }

  const candidateSkills = useMemo(() => {
    if (!targetRole) return []
    const list = targetRole.required_skills || []
    return list.filter((s) => !skills.includes(s)).slice(0, 24)
  }, [targetRole, skills])

  const addSkill = (s: string) => {
    const v = s.trim()
    if (!v || skills.includes(v)) return
    setSkills([...skills, v])
  }

  const removeSkill = (s: string) => setSkills(skills.filter((x) => x !== s))

  const doRecommend = async () => {
    if (!skills.length) {
      Taro.showToast({ title: '请先选择至少一项技能', icon: 'none' })
      return
    }
    setRecommending(true)
    try {
      const res = await postRecommend(
        {
          user_id: getUserId(),
          skills,
          target_role: targetRole?.role_name || null
        },
        5
      )
      setRecommendItems(res.items || [])
      setRecommended(true)
      // 批量拉取收藏状态标星（失败静默回退本地缓存）
      fetchFavoriteIds('job').then((ids) => setFavIds(ids)).catch(() => {})
      // 记录一次匹配历史（云端 + 本地兜底）
      const matchTitle = targetRole?.role_name_zh || targetRole?.role_name || res.items?.[0]?.job?.title || '岗位匹配'
      const matchId = targetRole?.role_id || res.items?.[0]?.job?.job_id || ''
      recordHistory('match', matchId, matchTitle, { skills, role: targetRole?.role_name || null })
      saveProfile(skills, targetRole
        ? { role_id: targetRole.role_id, role_name: targetRole.role_name, role_name_zh: targetRole.role_name_zh }
        : null)
    } catch (e) {
      // 统一错误提示已在 request 内处理
    } finally {
      setRecommending(false)
    }
  }

  const goPath = (item: RecommendationItem) => {
    Taro.navigateTo({
      url: `/pages/path/index?job_id=${encodeURIComponent(item.job.job_id)}&title=${encodeURIComponent(item.job.title)}`
    })
  }

  // 「问问助手」：预填消息写入 storage，跳助手 tab 由助手页 onShow 填入输入框（不自动发送）
  const askAssistant = (e: any, item: RecommendationItem) => {
    e.stopPropagation()
    const missing = (item.skill_gap.missing_skills || []).slice(0, 5)
    const msg =
      `我刚做了岗位匹配，结果是「${item.job.title}」（匹配度 ${(item.final_score * 100).toFixed(0)}%），` +
      `缺口技能：${missing.join('、') || '无'}。我想了解：`
    Taro.setStorageSync(PREFILL_MESSAGE_KEY, msg)
    Taro.switchTab({ url: '/pages/assistant/index' })
  }

  const toggleFav = async (e: any, item: RecommendationItem) => {
    e.stopPropagation()
    const next = !favIds[item.job.job_id]
    // 乐观更新
    setFavIds((prev) => ({ ...prev, [item.job.job_id]: next }))
    Taro.showToast({ title: next ? '已收藏' : '已取消收藏', icon: 'none' })
    await setJobFavorite(item, next)
  }

  return (
    <View className='container'>
      <View className='page-hero'>
        <Text className='page-hero-title'>岗位匹配</Text>
        <Text className='page-hero-sub'>选择你的技能，找到最适合的岗位与学习路径</Text>
      </View>
      <View className='card'>
        <Text className='match-section-title'>1. 选择目标岗位（可选）</Text>
        <ScrollView scrollY className='match-roles-scroll'>
          {categories.map((cat) => (
            <View key={cat} className='match-cat'>
              <View className='match-cat-header' onClick={() => toggleCategory(cat)}>
                <Text className='match-cat-name'>{cat}</Text>
                <Text className='match-cat-arrow'>{expanded[cat] ? '▾' : '▸'}</Text>
              </View>
              {expanded[cat] && (
                <View className='match-cat-body'>
                  {(rolesByCategory[cat] || []).map((r) => (
                    <Text
                      key={r.role_id}
                      className={`match-role-chip ${targetRole?.role_id === r.role_id ? 'match-role-chip--active' : ''}`}
                      onClick={() => selectRole(r)}
                    >
                      {r.role_name_zh || r.role_name}
                    </Text>
                  ))}
                </View>
              )}
            </View>
          ))}
          {targetRole && (
            <Text className='match-target text-primary-color'>
              已选目标：{targetRole.role_name_zh || targetRole.role_name}
            </Text>
          )}
        </ScrollView>
      </View>

      <View className='card'>
        <Text className='match-section-title'>2. 选择你的技能</Text>
        {targetRole && candidateSkills.length > 0 && (
          <View className='match-chip-group'>
            <Text className='match-chip-group-label'>该岗位常见技能（点选添加）：</Text>
            {candidateSkills.map((s) => (
              <Text key={s} className='match-skill-chip' onClick={() => addSkill(s)}>
                + {s}
              </Text>
            ))}
          </View>
        )}
        <View className='match-skill-input-row'>
          <Input
            className='match-skill-input'
            value={skillInput}
            placeholder='手动输入技能，如 python'
            onInput={(e) => setSkillInput(e.detail.value)}
            onConfirm={() => {
              addSkill(skillInput)
              setSkillInput('')
            }}
          />
          <Text
            className='match-skill-add'
            onClick={() => {
              addSkill(skillInput)
              setSkillInput('')
            }}
          >
            添加
          </Text>
        </View>
        {skills.length > 0 && (
          <View className='match-chip-group'>
            <Text className='match-chip-group-label'>已选技能（点击移除）：</Text>
            {skills.map((s) => (
              <Text key={s} className='match-skill-chip match-skill-chip--selected' onClick={() => removeSkill(s)}>
                {s} ✕
              </Text>
            ))}
          </View>
        )}
      </View>

      <View
        className={`btn-primary ${recommending ? 'btn-primary--disabled' : ''}`}
        onClick={doRecommend}
      >
        {recommending ? '匹配中…' : '开始匹配'}
      </View>

      {recommended && (
        <View className='match-results'>
          <Text className='match-results-title'>推荐结果</Text>
          {recommendItems.length === 0 && <View className='empty'>暂无匹配岗位</View>}
          {recommendItems.map((item, i) => (
            <View key={item.job.job_id} className='card match-result-card' onClick={() => goPath(item)}>
              <View className='match-result-top'>
                <View className='match-result-main'>
                  <View className='match-result-title-row'>
                    <Text className='match-result-rank'>{i + 1}</Text>
                    <Text className='match-result-title'>{item.job.title}</Text>
                    <Image
                      className='match-result-fav-img'
                      src={
                        favIds[item.job.job_id]
                          ? require('../../assets/icons/ic-star-fill.png')
                          : require('../../assets/icons/ic-star-outline.png')
                      }
                      mode='aspectFit'
                      onClick={(e) => toggleFav(e, item)}
                    />
                  </View>
                  <Text className='match-result-meta text-secondary'>
                    {item.job.coarse_role || ''}
                    {item.job.salary_min_k ? ` · ¥${item.job.salary_min_k}k-${item.job.salary_max_k}k` : ''}
                  </Text>
                </View>
                <View className='match-score'>
                  <Text className='match-score-value'>{(item.final_score * 100).toFixed(0)}%</Text>
                  <Text className='match-score-label'>匹配度</Text>
                  {item.confidence === 'high' || item.confidence === 'medium' || item.confidence === 'low' ? (
                    <Text className={`match-confidence match-confidence--${item.confidence}`}>
                      置信度 {item.confidence === 'high' ? '高' : item.confidence === 'medium' ? '中' : '低'}
                    </Text>
                  ) : null}
                </View>
              </View>
              <View className='match-score-bar'>
                <View
                  className='match-score-fill'
                  style={{ width: `${Math.min(100, Math.max(4, item.final_score * 100))}%` }}
                />
              </View>
              <Text className='match-result-explain'>{formatExplanation(item.explanation)}</Text>
              <View className='match-gap-row'>
                <Text className='tag tag-green'>已具备：{(item.skill_gap.overlap_skills || []).length}</Text>
                <Text className='tag tag-red'>需补齐：{(item.skill_gap.missing_skills || []).slice(0, 5).join('、') || '无'}</Text>
              </View>
              <View className='match-result-actions'>
                <View className='match-ask-btn' onClick={(e) => askAssistant(e, item)}>
                  <Text className='match-ask-btn-text'>问问助手</Text>
                  <Text className='match-ask-btn-arrow'>›</Text>
                </View>
                <View className='match-result-more' onClick={() => goPath(item)}>
                  <Text className='match-result-more-text'>查看学习路径</Text>
                  <Text className='match-result-more-arrow'>›</Text>
                </View>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  )
}
