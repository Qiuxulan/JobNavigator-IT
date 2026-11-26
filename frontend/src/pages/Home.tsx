import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getGraph, getNewsCategories, getRoleCatalog } from "../api";
import { getMarketOverview } from "../market";
import { Ic } from "../components/Icons";
import Dashboard from "./Dashboard";

const QUICK_LINKS = [
  { icon: Ic.target, label: "岗位匹配", desc: "按技能推荐岗位与置信度", path: "/match", hue: "linear-gradient(135deg,#4f6ef7,#7a5cff)" },
  { icon: Ic.compare, label: "岗位洞察", desc: "国内在招、技能要求与岗位对比", path: "/role", hue: "linear-gradient(135deg,#33cfd5,#1fc8a9)" },
  { icon: Ic.route, label: "学习路径", desc: "从现有技能到目标岗位", path: "/path", hue: "linear-gradient(135deg,#ffb13d,#ff9466)" },
  { icon: Ic.graph, label: "职业图谱", desc: "岗位 · 技能 · 事件关系", path: "/graph", hue: "linear-gradient(135deg,#9b72f0,#7a5cff)" },
  { icon: Ic.news, label: "行业新闻", desc: "招聘、融资与技术动态", path: "/news", hue: "linear-gradient(135deg,#5b8def,#33cfd5)" },
  { icon: Ic.chat, label: "AI 助手", desc: "一句话查询全部数据", path: "/chat", hue: "linear-gradient(135deg,#1c1e23,#4c5159)" },
];

interface HomeStats {
  roles: number | null;
  trends: number | null;
  skills: number | null;
  news: number | null;
}

export default function Home() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<HomeStats>({ roles: null, trends: null, skills: null, news: null });

  useEffect(() => {
    let alive = true;
    Promise.all([
      getRoleCatalog().then((items) => items.length).catch(() => null),
      getMarketOverview().then((m) => m.summary.open_roles).catch(() => null),
      getGraph().then((graph) => graph.nodes.filter((n) => n.kind === "skill").length).catch(() => null),
      getNewsCategories()
        .then((s) => Object.values(s.categories ?? {}).reduce((sum, n) => sum + n, 0))
        .catch(() => null),
    ]).then(([roles, trends, skills, news]) => {
      if (alive) setStats({ roles, trends, skills, news });
    });
    return () => { alive = false; };
  }, []);

  const statItems: { value: number | null; label: string }[] = [
    { value: stats.trends, label: "国内在招岗位" },
    { value: stats.roles, label: "细分岗位" },
    { value: stats.skills, label: "图谱技能" },
    { value: stats.news, label: "近 7 天新闻" },
  ];

  return (
    <div className="page" style={{ maxWidth: 1320 }}>
      <section className="home-hero fade">
        <div className="hh-l">
          <div className="hh-pill"><span className="hh-pill-dot" />国内实时岗位 · 技能图谱 · 学习路径 · AI 助手</div>
          <h1 className="hh-title">
            IT 职业导航<span className="lite">从岗位到学习路径</span>
          </h1>
          <p className="hh-sub">
            每天采集国内大厂官网在招岗位，告诉你哪些岗位在招、要什么技能、差在哪里、该怎么学；
            下方是国内市场总览，也可以从右侧直接进入岗位匹配、学习路径等功能。
          </p>
          <div className="hh-stats">
            {statItems.map((s) => (
              <div className="hh-stat" key={s.label}>
                {s.value === null ? <span className="hh-stat-skel" /> : <b>{s.value}</b>}
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="hh-quick">
          {QUICK_LINKS.map((q) => {
            const Icon = q.icon;
            return (
              <button key={q.path} className="hh-quick-item" onClick={() => navigate(q.path)}>
                <span className="hh-quick-ic" style={{ background: q.hue }}><Icon /></span>
                <span className="hh-quick-tx">
                  <b>{q.label}</b>
                  <small>{q.desc}</small>
                </span>
                <Ic.back className="hh-quick-arrow" style={{ transform: "rotate(180deg)" }} />
              </button>
            );
          })}
        </div>
      </section>

      <Dashboard embedded />
    </div>
  );
}
