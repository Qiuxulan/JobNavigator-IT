/**
 * 轻量 Markdown 渲染器（View/Text 逐块渲染，不用 rich-text）。
 * 支持助手实际输出格式：#~### 标题、**加粗**、*斜体*、`代码`、-/* 无序列表、
 * 1. 有序列表、``` 代码块、| 表格 |、> 引用、--- 分隔线。
 * 表格在列数较多时通过横向 ScrollView 滚动。
 */
import { View, Text, ScrollView } from '@tarojs/components'
import type { ReactNode } from 'react'

type Block =
  | { type: 'h'; level: 1 | 2 | 3; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'code'; text: string }
  | { type: 'table'; header: string[]; rows: string[][] }
  | { type: 'quote'; lines: string[] }
  | { type: 'hr' }

/** 按行解析为块级节点 */
export function parseMarkdown(src: string): Block[] {
  const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    // 代码块
    if (/^\s*```/.test(line)) {
      const buf: string[] = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        buf.push(lines[i])
        i++
      }
      i++ // 跳过收尾 ```
      blocks.push({ type: 'code', text: buf.join('\n') })
      continue
    }

    if (!line.trim()) {
      i++
      continue
    }

    // 标题
    const hm = line.match(/^(#{1,3})\s+(.+)$/)
    if (hm) {
      blocks.push({ type: 'h', level: hm[1].length as 1 | 2 | 3, text: hm[2].trim() })
      i++
      continue
    }

    // 分隔线
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ type: 'hr' })
      i++
      continue
    }

    // 无序列表
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, '').trim())
        i++
      }
      blocks.push({ type: 'ul', items })
      continue
    }

    // 有序列表
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, '').trim())
        i++
      }
      blocks.push({ type: 'ol', items })
      continue
    }

    // 引用
    if (/^\s*>\s?/.test(line)) {
      const qlines: string[] = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        qlines.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      blocks.push({ type: 'quote', lines: qlines })
      continue
    }

    // 表格：连续以 | 开头的行，第二行为分隔行
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const raw: string[][] = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        raw.push(splitRow(lines[i]))
        i++
      }
      const isSep = (cells: string[]) => cells.every((c) => /^:?-{2,}:?$/.test(c.trim()))
      let header: string[]
      let rows: string[][]
      if (raw.length >= 2 && isSep(raw[1])) {
        header = raw[0]
        rows = raw.slice(2)
      } else {
        header = raw[0]
        rows = raw.slice(1)
      }
      const cols = Math.max(header.length, ...rows.map((r) => r.length), 1)
      const pad = (cells: string[]) => Array.from({ length: cols }, (_, k) => cells[k] || '')
      blocks.push({ type: 'table', header: pad(header), rows: rows.map(pad) })
      continue
    }

    // 段落：连续普通行合并（保留换行）
    const buf: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,3}\s|\s*[-*]\s|\s*\d+[.)]\s|\s*>\s?|\s*\||\s*```|\s*(-{3,}|\*{3,}|_{3,})\s*$)/.test(lines[i])
    ) {
      buf.push(lines[i].trim())
      i++
    }
    blocks.push({ type: 'p', text: buf.join('\n') })
  }
  return blocks
}

function splitRow(line: string): string[] {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'))
}

const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/

/** 行内解析：**加粗**、`代码`、*斜体* */
export function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let rest = text
  let k = 0
  while (rest) {
    const m = rest.match(INLINE_RE)
    if (!m || m.index === undefined) {
      out.push(rest)
      break
    }
    if (m.index > 0) out.push(rest.slice(0, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) {
      out.push(
        <Text key={k++} className='md-strong'>
          {tok.slice(2, -2)}
        </Text>
      )
    } else if (tok.startsWith('`')) {
      out.push(
        <Text key={k++} className='md-code'>
          {tok.slice(1, -1)}
        </Text>
      )
    } else {
      out.push(
        <Text key={k++} className='md-em'>
          {tok.slice(1, -1)}
        </Text>
      )
    }
    rest = rest.slice(m.index + tok.length)
  }
  return out
}

function TableBlock({ header, rows }: { header: string[]; rows: string[][] }) {
  const cols = header.length
  return (
    <ScrollView scrollX className='md-table-scroll' enhanced showScrollbar={false}>
      <View className='md-table' style={{ minWidth: `${Math.max(100, cols * 20)}%` }}>
        <View className='md-tr md-tr--head'>
          {header.map((c, j) => (
            <Text key={j} className='md-td md-th'>
              {renderInline(c)}
            </Text>
          ))}
        </View>
        {rows.map((r, i) => (
          <View key={i} className='md-tr'>
            {r.map((c, j) => (
              <Text key={j} className='md-td'>
                {renderInline(c)}
              </Text>
            ))}
          </View>
        ))}
      </View>
    </ScrollView>
  )
}

/** 块级渲染入口 */
export function MarkdownView({ content }: { content: string }) {
  const blocks = parseMarkdown(content)
  return (
    <View className='md-root'>
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'h':
            return (
              <Text key={i} className={`md-h md-h${b.level}`}>
                {renderInline(b.text)}
              </Text>
            )
          case 'p':
            return (
              <Text key={i} className='md-p'>
                {b.text.split('\n').map((ln, j) => (
                  <Text key={j} className='md-p-line'>
                    {renderInline(ln)}
                    {'\n'}
                  </Text>
                ))}
              </Text>
            )
          case 'ul':
            return (
              <View key={i} className='md-list'>
                {b.items.map((it, j) => (
                  <View key={j} className='md-li'>
                    <Text className='md-li-bullet'>•</Text>
                    <Text className='md-li-text'>{renderInline(it)}</Text>
                  </View>
                ))}
              </View>
            )
          case 'ol':
            return (
              <View key={i} className='md-list'>
                {b.items.map((it, j) => (
                  <View key={j} className='md-li'>
                    <Text className='md-li-bullet md-li-num'>{j + 1}.</Text>
                    <Text className='md-li-text'>{renderInline(it)}</Text>
                  </View>
                ))}
              </View>
            )
          case 'code':
            return (
              <ScrollView key={i} scrollX className='md-codeblock-scroll' enhanced showScrollbar={false}>
                <Text className='md-codeblock'>{b.text}</Text>
              </ScrollView>
            )
          case 'table':
            return <TableBlock key={i} header={b.header} rows={b.rows} />
          case 'quote':
            return (
              <View key={i} className='md-quote'>
                {b.lines.map((ln, j) => (
                  <Text key={j} className='md-quote-line'>
                    {renderInline(ln)}
                  </Text>
                ))}
              </View>
            )
          case 'hr':
            return <View key={i} className='md-hr' />
          default:
            return null
        }
      })}
    </View>
  )
}

export default MarkdownView
