import { useEffect, useState } from 'react'
import Taro from '@tarojs/taro'
import { View, Text, ScrollView, Image } from '@tarojs/components'
import { postPathGenerate, LearningPath } from '../../services/api'
import { getUserId } from '../../utils/user'
import { getStoredSkills, getSavedPaths, savePath } from '../../utils/store'
import { savePathFavorite } from '../../services/me'
import { renderInline } from '../../utils/markdown'
import './index.scss'

export default function PathPage() {
  const [path, setPath] = useState<LearningPath | null>(null)
  const [loading, setLoading] = useState(true)
  const [jobTitle, setJobTitle] = useState('学习路径')
  const [jobId, setJobId] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const params = Taro.getCurrentInstance().router?.params || {}
    const jobId = decodeURIComponent(params.job_id || '')
    const title = decodeURIComponent(params.title || '学习路径')
    setJobId(jobId)
    setJobTitle(title)
    Taro.setNavigationBarTitle({ title })
    if (!jobId) {
      setLoading(false)
      return
    }
    setSaved(getSavedPaths().some((p) => p.job_id === jobId))
    const skills = getStoredSkills()
    postPathGenerate({ user_id: getUserId(), skills, target_role: title }, jobId)
      .then((res) => setPath(res.path))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const copyUrl = (url: string) => {
    if (!url) {
      Taro.showToast({ title: '该资源暂无链接', icon: 'none' })
      return
    }
    Taro.setClipboardData({
      data: url,
      success: () => {
        Taro.showToast({ title: '链接已复制，去浏览器打开', icon: 'none', duration: 2500 })
      }
    })
  }

  const saveCurrentPath = () => {
    if (!path || !jobId) return
    if (saved) {
      Taro.showToast({ title: '该路径已保存过', icon: 'none' })
      return
    }
    // 本地存档 + 云端收藏（item_type=path，payload 自动裁剪到 32KB 内）
    savePath(jobId, jobTitle, path)
    savePathFavorite(jobId, jobTitle, path)
    setSaved(true)
    Taro.showToast({ title: '路径已保存', icon: 'success' })
  }

  if (loading) {
    return <View className='empty'>加载中…</View>
  }
  if (!path) {
    return <View className='empty'>未能生成学习路径，请返回重试</View>
  }

  return (
    <ScrollView scrollY className='path-page'>
      <View className='container'>
        <View className='path-hero'>
          <Text className='path-hero-label'>学习路径</Text>
          <Text className='path-hero-title'>{jobTitle}</Text>
          <Text className='path-hero-sub'>按步骤补齐技能缺口，点击资源卡片即可复制链接</Text>
        </View>

        <View className='card'>
          <View className='path-metrics'>
            <View className='path-metric'>
              <Text className='path-metric-value'>{path.total_steps}</Text>
              <Text className='path-metric-label'>学习步骤</Text>
            </View>
            <View className='path-metric'>
              <Text className='path-metric-value'>{path.total_estimated_hours}h</Text>
              <Text className='path-metric-label'>预计总时长</Text>
            </View>
            <View className='path-metric'>
              <Text className='path-metric-value'>{(path.score * 100).toFixed(0)}%</Text>
              <Text className='path-metric-label'>路径得分</Text>
            </View>
          </View>
          <View
            className={`btn-primary path-save-btn ${saved ? 'btn-primary--disabled' : ''}`}
            onClick={saveCurrentPath}
          >
            {saved ? '已保存 ✓' : '保存此路径'}
          </View>
        </View>

        {path.steps.map((step, idx) => (
          <View key={step.step_no} className='path-step'>
            <View className='path-step-rail'>
              <View className='path-step-dot'>
                <Text className='path-step-no'>{step.step_no}</Text>
              </View>
              {idx < path.steps.length - 1 && <View className='path-step-line' />}
            </View>
            <View className='path-step-body card'>
              <Text className='path-step-skill'>{step.skill}</Text>
              <Text className='path-step-reason text-secondary'>{step.reason}</Text>
              {(step.resources || []).map((r) => (
                <View
                  key={r.resource_id || r.url}
                  className='path-resource'
                  onClick={() => copyUrl(r.url)}
                >
                  <View className='path-resource-main'>
                    <View className='path-resource-title-row'>
                      <Text className='path-resource-title'>{renderInline(r.title)}</Text>
                      <Image
                        className='path-resource-link-icon'
                        src={require('../../assets/icons/ic-external-link.png')}
                        mode='aspectFit'
                      />
                    </View>
                    <Text className='path-resource-meta text-secondary'>
                      {r.provider}
                      {r.level ? ` · ${r.level}` : ''}
                      {r.hours_estimate ? ` · 约${r.hours_estimate}h` : ''}
                    </Text>
                    <View className='path-resource-tags'>
                      {r.source ? <Text className='tag tag-gray'>{r.source}</Text> : null}
                      {typeof r.quality_score === 'number' ? (
                        <Text className='tag'>质量 {r.quality_score.toFixed(1)}</Text>
                      ) : null}
                      <Text className='path-resource-hint'>点击复制链接</Text>
                    </View>
                  </View>
                </View>
              ))}
            </View>
          </View>
        ))}
      </View>
    </ScrollView>
  )
}
