import { useNavigate } from "react-router-dom";
import { Ic, Logo } from "../components/Icons";

export default function Landing() {
  const navigate = useNavigate();
  const tools = [
    { icon: Ic.dash, title: "趋势仪表盘", desc: "查看 69 个细分岗位的预测方向、需求指数和分类分布。", path: "/dashboard" },
    { icon: Ic.compare, title: "角色对比", desc: "横向比较多个岗位的需求指数、置信度和趋势判断。", path: "/compare" },
    { icon: Ic.graph, title: "知识图谱", desc: "查看岗位、技能、前置关系和行业事件影响链路。", path: "/graph" },
    { icon: Ic.route, title: "学习路径", desc: "输入已有技能和目标岗位，生成按前置关系排序的学习步骤。", path: "/path" },
    { icon: Ic.chat, title: "Agent 助手", desc: "在一个入口里查询趋势、证据、职业推荐和学习路径。", path: "/chat" },
  ];

  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-nav-in">
          <div className="lp-brand">
            <div className="lp-brand-mark"><Logo accent="#FFB13D" /></div>
            <div>
              <div className="lp-brand-name">JobNavigator</div>
              <div className="lp-brand-sub">IT Trend Intelligence</div>
            </div>
          </div>
          <div className="lp-nav-cta">
            <button className="btn ghost" onClick={() => navigate("/chat")}>Agent 助手</button>
            <button className="btn primary" onClick={() => navigate("/dashboard")}>
              进入仪表盘 <Ic.back style={{ transform: "rotate(180deg)" }} />
            </button>
          </div>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-l">
          <div className="lp-pill"><span className="lp-pill-dot" />PatchTST 预测 · RAG 证据 · 职业路径</div>
          <h1 className="lp-h1">JobNavigator<br /><span className="lp-h1-mark">IT 岗位趋势与职业推荐系统</span></h1>
          <p className="lp-lead">
            系统整合岗位月度预测、行业事件证据、技能图谱和职业推荐模块，用于查看岗位趋势、分析技能缺口，并生成可执行的学习路径。
          </p>
          <div className="lp-hero-cta">
            <button className="btn primary lg" onClick={() => navigate("/dashboard")}><Ic.dash /> 趋势仪表盘</button>
            <button className="btn lg" onClick={() => navigate("/path")}><Ic.route /> 生成学习路径</button>
          </div>
          <div className="lp-hero-meta">
            <span><b className="num">69</b> 岗位</span>
            <span className="lp-sep" />
            <span><b className="num">275</b> 技能</span>
            <span className="lp-sep" />
            <span><b className="num">36</b> 个月预测</span>
          </div>
        </div>
        <div className="lp-hero-r" />
      </section>

      <section className="lp-section" id="lp-tools">
        <div className="lp-sec-head">
          <div className="page-eyebrow">Modules</div>
          <h2 className="lp-h2">已接入的功能模块</h2>
        </div>
        <div className="lp-tools">
          {tools.map((tool) => {
            const Icon = tool.icon;
            return (
              <button className="lp-tool" key={tool.path} onClick={() => navigate(tool.path)}>
                <div className="lp-tool-top"><div className="lp-tool-ic"><Icon /></div></div>
                <div className="lp-tool-t">{tool.title}</div>
                <div className="lp-tool-d">{tool.desc}</div>
                <div className="lp-tool-go">打开 →</div>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
