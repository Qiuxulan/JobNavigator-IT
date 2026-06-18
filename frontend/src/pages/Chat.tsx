import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { agentChat } from "../api";
import type { ChatMessage } from "../api";
import { Ic } from "../components/Icons";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
}

const QUICK = [
  { icon: Ic.up, title: "行业趋势总览", desc: "整体走向、分类排名与热门岗位", q: "给我一份 IT 行业趋势总览" },
  { icon: Ic.brain, title: "分析我的技能", desc: "粘贴简历或列出技能，匹配岗位", q: "我会 Python、SQL、Docker 和 LangChain，适合什么岗位？" },
  { icon: Ic.target, title: "RAG Engineer 前景", desc: "单岗位趋势、证据和学习建议", q: "RAG Engineer 这个岗位前景如何？" },
  { icon: Ic.route, title: "职业规划", desc: "面向目标岗位的分阶段路径", q: "我想转 Machine Learning Engineer，帮我规划学习路径" },
  { icon: Ic.compare, title: "角色对比", desc: "横向比较多个岗位", q: "对比 AI Engineer 和 DevOps Engineer" },
  { icon: Ic.layers, title: "查看全部角色", desc: "浏览当前收录的细分岗位", q: "平台收录了哪些岗位？" },
];

const CAPS = ["简历分析", "岗位推荐", "技能差距", "学习路径", "趋势预测", "证据检索"];

function InlineText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
        if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </>
  );
}

function MarkdownBlock({ text }: { text: string }) {
  const lines = text.split(/\r?\n/);
  const blocks: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i += 1;
      blocks.push(<pre key={i}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    if (line.startsWith("|") && lines[i + 1]?.includes("---")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        if (!lines[i].includes("---")) rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i += 1;
      }
      const [head, ...body] = rows;
      blocks.push(
        <table key={i}>
          <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{body.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci}><InlineText text={c} /></td>)}</tr>)}</tbody>
        </table>
      );
      continue;
    }
    if (/^#{1,4}\s/.test(line)) {
      const level = line.match(/^#+/)?.[0].length || 3;
      const content = line.replace(/^#{1,4}\s/, "");
      const Tag = `h${Math.min(level, 4)}` as "h1" | "h2" | "h3" | "h4";
      blocks.push(<Tag key={i}><InlineText text={content} /></Tag>);
      i += 1;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      blocks.push(<ul key={i}>{items.map((item) => <li key={item}><InlineText text={item} /></li>)}</ul>);
      continue;
    }
    blocks.push(<p key={i}><InlineText text={line} /></p>);
    i += 1;
  }
  return <div className="md">{blocks}</div>;
}

export default function Chat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    return h < 6 ? "夜深了" : h < 12 ? "早上好" : h < 18 ? "下午好" : "晚上好";
  }, []);

  const send = async (text?: string) => {
    const value = (text ?? input).trim();
    if (!value || loading) return;
    const nextMessages = [...messages, { role: "user" as const, content: value }];
    setMessages(nextMessages);
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
    setLoading(true);
    try {
      const history: ChatMessage[] = nextMessages.map((m) => ({ role: m.role, content: m.content }));
      const reply = await agentChat(history);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (err: unknown) {
      let detail = "未知错误";
      if (err && typeof err === "object") {
        const axErr = err as { response?: { status?: number; data?: unknown }; code?: string; message?: string };
        if (axErr.response) {
          detail = `HTTP ${axErr.response.status}: ${JSON.stringify(axErr.response.data)}`;
        } else if (axErr.code === "ECONNABORTED") {
          detail = "请求超时（60 秒），Agent 处理时间过长";
        } else if (axErr.message) {
          detail = axErr.message;
        }
      }
      console.error("agentChat error:", err);
      setMessages((prev) => [...prev, { role: "assistant", content: `请求失败：${detail}\n\n如果后端未启动，请在终端运行：\n\`python -m uvicorn app.main:app --port 8000\`` }]);
    } finally {
      setLoading(false);
    }
  };

  const onInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(170, e.target.scrollHeight)}px`;
  };

  return (
    <div className="chat-wrap">
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-inner">
          {messages.length === 0 && (
            <div className="chat-hero fade">
              <div className="hero-mark"><Ic.spark /></div>
              <div className="hero-greet">{greeting}，<span className="lite">我是你的职业发展助手。</span></div>
              <div className="hero-sub">我已接入真实 Agent，可以综合趋势预测、证据检索、职业推荐、技能差距和学习路径回答问题。</div>
              <div className="hero-caps">
                {CAPS.map((c) => <span className="cap" key={c}><span className="dot-cat" style={{ background: "#8fb094" }} />{c}</span>)}
              </div>
              <div className="quick-label">从这里开始</div>
              <div className="quick-grid">
                {QUICK.map((q) => {
                  const Icon = q.icon;
                  return (
                    <button className="quick" key={q.title} onClick={() => send(q.q)}>
                      <div className="quick-ic"><Icon /></div>
                      <div><div className="quick-t">{q.title}</div><div className="quick-d">{q.desc}</div></div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div className={"msg " + (m.role === "assistant" ? "ai" : "user") + " fade"} key={i}>
              <div className="msg-av">{m.role === "assistant" ? <Ic.spark /> : <Ic.user />}</div>
              <div className="msg-col"><div className="bubble">{m.role === "assistant" ? <MarkdownBlock text={m.content} /> : m.content}</div></div>
            </div>
          ))}
          {loading && (
            <div className="msg ai fade">
              <div className="msg-av"><Ic.spark /></div>
              <div className="msg-col"><div className="bubble typing"><span /><span /><span /></div></div>
            </div>
          )}
        </div>
      </div>

      <div className="chat-foot">
        <div className="composer">
          <textarea
            ref={taRef}
            value={input}
            onChange={onInput}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            rows={1}
            placeholder="询问岗位趋势、粘贴简历分析技能，或描述你的职业目标..."
          />
          <button className="send-btn" disabled={!input.trim() || loading} onClick={() => send()}><Ic.send /></button>
        </div>
        <div className="composer-hint">
          <span>Enter 发送</span>
          <span>Shift + Enter 换行</span>
          <span>真实 Agent API</span>
        </div>
      </div>
    </div>
  );
}
