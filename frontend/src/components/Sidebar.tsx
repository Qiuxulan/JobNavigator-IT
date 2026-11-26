import type { ComponentType, SVGProps } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Ic, Logo } from "./Icons";

interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** 额外视为激活的路径前缀（如岗位详情归属「岗位对比」） */
  also?: string[];
}

interface NavGroup {
  label: string;
  en: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    label: "总览",
    en: "Overview",
    items: [{ path: "/", label: "首页", icon: Ic.dash }],
  },
  {
    label: "职业匹配",
    en: "Career Match",
    items: [
      { path: "/match", label: "岗位匹配", icon: Ic.target },
      { path: "/role", label: "岗位洞察", icon: Ic.compare },
      { path: "/path", label: "学习路径", icon: Ic.route },
    ],
  },
  {
    label: "行业洞察",
    en: "Insights",
    items: [
      { path: "/graph", label: "职业图谱", icon: Ic.graph },
      { path: "/news", label: "行业新闻", icon: Ic.news },
    ],
  },
  {
    label: "助手",
    en: "Assistant",
    items: [{ path: "/chat", label: "AI 助手", icon: Ic.chat }],
  },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const isActive = (it: NavItem) => {
    if (it.path === "/") return pathname === "/";
    return pathname.startsWith(it.path) || (it.also ?? []).some((p) => pathname.startsWith(p));
  };

  return (
    <aside className="sidebar">
      <div className="brand" onClick={() => navigate("/")}>
        <div className="brand-mark"><Logo accent="#FFB13D" /></div>
        <div>
          <div className="brand-name">JobNavigator</div>
          <div className="brand-sub">IT Trend Intelligence</div>
        </div>
      </div>

      <button className="side-cta" onClick={() => navigate("/chat")}>
        <Ic.spark />
        <span className="cta-label">向 AI 助手提问</span>
      </button>

      <nav className="nav">
        {GROUPS.map((g) => (
          <div className="nav-group" key={g.label}>
            <div className="nav-label">
              <span>{g.label}</span>
              <span className="nav-label-en">{g.en}</span>
            </div>
            {g.items.map((it) => {
              const I = it.icon;
              return (
                <NavLink key={it.path} to={it.path} className={"nav-item" + (isActive(it) ? " active" : "")}>
                  <I /> {it.label}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="nav-spacer" />
      <div className="nav-foot">
        <div className="nav-foot-av"><Ic.user /></div>
        <div>
          <div className="nav-foot-name">国内实时数据</div>
          <div className="nav-foot-sub"><span className="nav-dot" />官网岗位每日更新</div>
        </div>
      </div>
    </aside>
  );
}
