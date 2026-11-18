import { useEffect, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View, Text, ScrollView, Textarea, Button } from '@tarojs/components'
import { postAgentChat, ChatMessagePayload } from '../../services/api'
import { PREFILL_MESSAGE_KEY } from '../../utils/store'
import { MarkdownView } from '../../utils/markdown'
import './index.scss'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const HISTORY_KEY = 'jobnav_chat_history'
const MAX_HISTORY = 40

function windowHeight(): number {
  try {
    const info: any = (Taro as any).getWindowInfo ? (Taro as any).getWindowInfo() : Taro.getSystemInfoSync()
    return info.windowHeight || 600
  } catch (e) {
    return 600
  }
}

/** 实测滚动修复：scroll-view 必须拿到确定高度，flex:1 在真机上不生效。
 *  两趟测量：先按估算值渲染完成布局，再实测头部/快捷区/输入条位置，
 *  用输入条 top 反推消息区高度（天然排除 tabBar 与安全区差异）。 */
function measureScrollHeight(): Promise<number> {
  return new Promise((resolve) => {
    setTimeout(() => {
      const query = Taro.createSelectorQuery()
      query.select('.assistant-header').boundingClientRect()
      query.select('.assistant-quick').boundingClientRect()
      query.select('.assistant-input-bar').boundingClientRect()
      query.exec((rects: any[]) => {
        const [header, quick, inputBar] = rects || []
        if (!header || !inputBar) {
          resolve(Math.max(200, windowHeight() - 300))
          return
        }
        const top = header.top + (header.height || 0) + (quick?.height || 0)
        resolve(Math.max(200, Math.floor(inputBar.top - top)))
      })
    }, 50)
  })
}

const QUICK_QUESTIONS = [
  '我想转行做 AI 工程师，应该从哪里开始？',
  'Python 后端开发未来 1 年的前景怎么样？',
  '帮我对比一下数据分析和机器学习岗位',
  '我只会 Java，转大数据方向要补什么技能？'
]

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = Taro.getStorageSync(HISTORY_KEY)
      return Array.isArray(saved) ? saved : []
    } catch (e) {
      return []
    }
  })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [scrollHeight, setScrollHeight] = useState(400)

  useEffect(() => {
    let alive = true
    measureScrollHeight().then((h) => {
      if (alive) setScrollHeight(h)
    })
    return () => {
      alive = false
    }
  }, [])

  // 匹配页「问助手」跳转过来时，读取预填消息（只填不自动发）
  useDidShow(() => {
    try {
      const pre = Taro.getStorageSync(PREFILL_MESSAGE_KEY)
      if (pre) {
        Taro.removeStorageSync(PREFILL_MESSAGE_KEY)
        setInput(String(pre).slice(0, 500))
      }
    } catch (e) {}
  })

  const persist = (list: ChatMessage[]) => {
    const tail = list.slice(-MAX_HISTORY)
    setMessages(tail)
    try {
      Taro.setStorageSync(HISTORY_KEY, tail)
    } catch (e) {}
  }

  const send = async (text: string) => {
    const content = (text || input).trim()
    if (!content || sending) return

    const next: ChatMessage[] = [...messages, { role: 'user', content }]
    persist(next)
    setInput('')
    setSending(true)
    try {
      // 只把最近若干条作为上下文，避免 payload 过大
      const payload: ChatMessagePayload[] = next.slice(-10).map((m) => ({
        role: m.role,
        content: m.content
      }))
      const res = await postAgentChat(payload)
      persist([...next, { role: 'assistant', content: res.reply }])
    } catch (e) {
      persist([...next, { role: 'assistant', content: '（请求失败，请检查网络后重试）' }])
    } finally {
      setSending(false)
    }
  }

  const clearHistory = () => {
    Taro.showModal({
      title: '清空对话',
      content: '确定要清空全部聊天记录吗？',
      success: (res) => {
        if (res.confirm) {
          persist([])
        }
      }
    })
  }

  const copyText = (content: string) => {
    Taro.setClipboardData({ data: content })
  }

  return (
    <View className='assistant-page'>
      <View className='assistant-header'>
        <Text className='assistant-title'>职业助手</Text>
        <Text className='assistant-clear' onClick={clearHistory}>
          清空记录
        </Text>
      </View>

      <ScrollView
        className='assistant-scroll'
        scrollY
        scrollWithAnimation
        enhanced
        showScrollbar={false}
        style={{ height: `${scrollHeight}px` }}
        scrollIntoView={
          sending ? 'msg-typing' : messages.length ? `msg-${messages.length - 1}` : undefined
        }
      >
        {messages.length === 0 && (
          <View className='assistant-welcome'>
            <View className='assistant-welcome-avatar'>
              <Text>🧭</Text>
            </View>
            <Text className='assistant-welcome-title'>你好，我是 JobNavigator 职业助手</Text>
            <Text className='assistant-welcome-desc'>
              我可以基于 IT 岗位库与行业趋势数据，回答职业规划、技能学习、岗位对比等问题。点击下方快捷问题开始吧。
            </Text>
          </View>
        )}
        {messages.map((m, i) => (
          <View
            key={i}
            id={`msg-${i}`}
            className={`msg-row ${m.role === 'user' ? 'msg-row--user' : ''}`}
          >
            <View
              className={`msg-bubble ${m.role === 'user' ? 'msg-bubble--user' : ''}`}
              onLongPress={() => copyText(m.content)}
            >
              {m.role === 'assistant' ? (
                <MarkdownView content={m.content} />
              ) : (
                <Text className='msg-text'>{m.content}</Text>
              )}
            </View>
          </View>
        ))}
        {sending && (
          <View className='msg-row' id='msg-typing'>
            <View className='msg-bubble msg-bubble--typing'>
              <View className='typing-dots'>
                <View className='typing-dot' />
                <View className='typing-dot' />
                <View className='typing-dot' />
              </View>
            </View>
          </View>
        )}
      </ScrollView>

      <View className='assistant-quick'>
        {QUICK_QUESTIONS.map((q) => (
          <Text key={q} className='assistant-chip' onClick={() => send(q)}>
            {q}
          </Text>
        ))}
      </View>

      <View className='assistant-input-bar'>
        <Textarea
          className='assistant-input'
          value={input}
          placeholder='输入你的问题…'
          maxlength={500}
          cursorSpacing={20}
          onInput={(e) => setInput(e.detail.value)}
          confirmType='send'
          onConfirm={() => send('')}
        />
        <Button
          className={`assistant-send ${sending ? 'assistant-send--disabled' : ''}`}
          onClick={() => send('')}
        >
          发送
        </Button>
      </View>
    </View>
  )
}
