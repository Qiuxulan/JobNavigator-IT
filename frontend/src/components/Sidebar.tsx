import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Ic, Logo } from "./Icons";

export default function Sidebar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const items = [
    { path: "/dashboard", label: "趋势仪表盘", icon: Ic.dash },
    { path: "/compare", label: "角色对比", icon: Ic.compare },
    { path: "/graph", label: "知识图谱", icon: Ic.graph },
    { path: "/path", label: "学习路径", icon: Ic.route },
    { path: "/chat", label: "AI 助手", icon: Ic.chat },
  ];

  const isActive = (p: string) =>
    p === "/dashboard"
      ? pathname.startsWith("/dashboard") || pathname.startsWith("/role")
      : pathname.startsWith(p);

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
        <div className="nav-label">Menu</div>
        {items.map((it) => {
          const I = it.icon;
          return (
            <NavLink key={it.path} to={it.path} className={"nav-item" + (isActive(it.path) ? " active" : "")}>
              <I /> {it.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="nav-spacer" />
      <div className="nav-foot">
        <div className="nav-foot-av"><Ic.user /></div>
        <div>
          <div className="nav-foot-name">趋势数据集</div>
          <div className="nav-foot-sub"><span className="nav-dot" />PatchTST 预测模型</div>
        </div>
      </div>
    </aside>
  );
}
