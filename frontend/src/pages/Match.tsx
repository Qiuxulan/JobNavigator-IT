import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getRoleCatalog, getSkillTrends, recommendJobs } from "../api";
import type { RecommendationItem, RoleCatalogItem, SkillTrendItem } from "../api";
import { Ic } from "../components/Icons";
import PageHead from "../components/PageHead";
import { MatchConfidenceBadge, CatBadge } from "../components/Badge";

const DEFAULT_SKILLS = ["Python", "SQL", "Docker", "LangChain"];
const EDUCATIONS = ["大专", "本科", "硕士", "博士"];
const MAX_MISSING_CHIPS = 8;

function pickSkillNames(items: SkillTrendItem[], limit: number): string[] {
  return items.slice(0, limit).map((item) => item.name || item.skill).filter(Boolean);
}

export default function Match() {
  const navigate = useNavigate();
  const [roles, setRoles] = useState<RoleCatalogItem[]>([]);
  const [rolesFailed, setRolesFailed] = useState(false);
  const [trendSkills, setTrendSkills] = useState<string[]>([]);
  const [targetId, setTargetId] = useState("");
  const [skills, setSkills] = useState<string[]>(DEFAULT_SKILLS);
  const [skillInput, setSkillInput] = useState("");
  const [years, setYears] = useState("");
  const [education, setEducation] = useState("");
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getRoleCatalog()
      .then((list) => { if (alive) setRoles(list); })
      .catch(() => { if (alive) setRolesFailed(true); });
    getSkillTrends()
      .then((overview) => {
        if (!alive) return;
        const names = [
          ...pickSkillNames(overview.emerging || [], 12),
          ...pickSkillNames(overview.rising || [], 12),
        ];
        setTrendSkills(Array.from(new Set(names)));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const targetRole = useMemo(
    () => roles.find((role) => role.role_id === targetId) || null,
    [roles, targetId],
  );

  const candidateSkills = useMemo(() => {
    const list: string[] = [];
    if (targetRole) list.push(...targetRole.required_skills, ...targetRole.core_skills);
    list.push(...trendSkills);
    const picked = list.filter((skill) => skill && !skills.includes(skill));
    return Array.from(new Set(picked)).slice(0, 30);
  }, [targetRole, trendSkills, skills]);

  const addSkill = (skill: string) => {
    const value = skill.trim();
    if (!value || skills.includes(value)) return;
    setSkills([...skills, value]);
  };

  const removeSkill = (skill: string) => setSkills(skills.filter((s) => s !== skill));

  const submit = async () => {
    if (!skills.length) {
      setError("请先选择至少一项技能");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const results = await recommendJobs(
        {
          user_id: "frontend_user",
          skills,
          target_role: targetRole?.role_name || null,
          years_experience: years ? Number(years) || 0 : 0,
          education: education || null,
        },
        5,
      );
      setItems(results);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "推荐请求失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const goPath = (item: RecommendationItem) => {
    const params = new URLSearchParams({ role: item.job.job_id, skills: skills.join(",") });
    navigate(`/path?${params.toString()}`);
  };

  return (
    <div className="page" style={{ maxWidth: 1200 }}>
      <PageHead
        eyebrow="Career Match / Job Recommendation"
        title={<>岗位<span className="lite">匹配</span></>}
        sub="选择你的技能与背景，推荐模块会综合语义相似、技能覆盖、学习成本与行业趋势，给出校准后的匹配度和置信度分档。"
      />

      {rolesFailed && (
        <div className="error-box">岗位目录加载失败，仍可输入技能直接匹配。</div>
      )}

      <div className="path-layout">
        <section className="card path-form">
          <div className="card-hd">
            <div>
              <div className="card-title">匹配条件</div>
              <div className="card-desc">技能用逗号或换行分隔，也可点选下方候选</div>
            </div>
          </div>
          <div className="card-bd">
            <label className="form-label" htmlFor="match-role">目标岗位（可选）</label>
            <select id="match-role" className="select" value={targetId} onChange={(e) => setTargetId(e.target.value)}>
              <option value="">不限岗位</option>
              {roles.map((role) => (
                <option key={role.role_id} value={role.role_id}>
                  {role.role_name_zh || role.role_name} / {role.coarse_role}
                </option>
              ))}
            </select>

            <label className="form-label" htmlFor="match-skills">当前技能</label>
            <textarea
              id="match-skills"
              className="textarea"
              value={skills.join(", ")}
              onChange={(e) =>
                setSkills(
                  e.target.value
                    .split(/[,，\n]/)
                    .map((s) => s.trim())
                    .filter(Boolean),
                )
              }
              rows={4}
            />

            {candidateSkills.length > 0 && (
              <>
                <div className="chip-cat-label">
                  <span className="dot-cat" style={{ background: "#8fb094" }} />
                  候选技能（点选添加）
                </div>
                <div className="chips" style={{ marginBottom: 16 }}>
                  {candidateSkills.map((skill) => (
                    <span key={skill} className="chip" onClick={() => addSkill(skill)}>+ {skill}</span>
                  ))}
                </div>
              </>
            )}

            <div className="match-input-row">
              <input
                className="input"
                value={skillInput}
                placeholder="手动输入技能，如 kubernetes"
                onChange={(e) => setSkillInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addSkill(skillInput);
                    setSkillInput("");
                  }
                }}
              />
              <button
                className="btn sm"
                onClick={() => { addSkill(skillInput); setSkillInput(""); }}
              >
                添加
              </button>
            </div>

            {skills.length > 0 && (
              <>
                <div className="chip-cat-label">
                  <span className="dot-cat" style={{ background: "#5B8DEF" }} />
                  已选技能（点击移除）
                </div>
                <div className="chips" style={{ marginBottom: 4 }}>
                  {skills.map((skill) => (
                    <span key={skill} className="chip sel" onClick={() => removeSkill(skill)}>
                      {skill} ✕
                    </span>
                  ))}
                </div>
              </>
            )}

            <label className="form-label" htmlFor="match-years">工作年限</label>
            <input
              id="match-years"
              className="input"
              type="number"
              min={0}
              max={50}
              step={0.5}
              value={years}
              placeholder="如 3"
              onChange={(e) => setYears(e.target.value)}
            />

            <label className="form-label" htmlFor="match-edu">学历</label>
            <select id="match-edu" className="select" value={education} onChange={(e) => setEducation(e.target.value)}>
              <option value="">不限</option>
              {EDUCATIONS.map((edu) => (
                <option key={edu} value={edu}>{edu}</option>
              ))}
            </select>

            <button className="btn primary lg" style={{ marginTop: 18, width: "100%", justifyContent: "center" }} onClick={submit} disabled={loading}>
              <Ic.target />
              {loading ? "匹配中..." : "开始匹配"}
            </button>
          </div>
        </section>

        <section className="card path-main">
          <div className="card-hd">
            <div>
              <div className="card-title">推荐结果</div>
              <div className="card-desc">按校准后的匹配度排序</div>
            </div>
          </div>
          <div className="card-bd">
            {error && <div className="error-box">{error}</div>}
            {!searched && !error && (
              <div className="cmp-empty">
                <Ic.target />
                <div>填写左侧技能后点击「开始匹配」。</div>
              </div>
            )}
            {loading && (
              <div className="match-skel-list" aria-label="加载中">
                {[0, 1, 2].map((n) => (
                  <div className="match-skel" key={n}>
                    <div className="match-skel-row">
                      <div className="skel" style={{ width: 26, height: 26 }} />
                      <div className="skel" style={{ width: `${46 - n * 8}%`, height: 18 }} />
                      <div style={{ flex: 1 }} />
                      <div className="skel" style={{ width: 72, height: 52 }} />
                    </div>
                    <div className="skel" style={{ width: "100%", height: 6, borderRadius: 99 }} />
                    <div className="skel" style={{ width: "82%", height: 12 }} />
                    <div className="skel" style={{ width: "58%", height: 12 }} />
                  </div>
                ))}
              </div>
            )}
            {searched && !loading && items.length === 0 && !error && (
              <div className="cmp-empty">
                <Ic.gap />
                <div>暂无匹配岗位，试试减少技能或更换目标岗位。</div>
              </div>
            )}
            {searched && !loading && items.map((item, i) => (
              <article key={item.job.job_id} className="match-card">
                <div className="match-card-top">
                  <div className="match-card-main">
                    <div className="match-card-title-row">
                      <span className={"match-rank" + (i < 3 ? " top" : "")}>{i + 1}</span>
                      <span className="match-card-title">{item.job.title}</span>
                      {item.job.coarse_role && <CatBadge category={item.job.coarse_role} />}
                    </div>
                    <div className="match-card-meta">
                      {item.job.fine_role && item.job.fine_role !== item.job.title && <span>{item.job.fine_role}</span>}
                      {item.job.city && <span>{item.job.city}</span>}
                      {item.job.salary_min_k != null && item.job.salary_max_k != null && (
                        <span>¥{item.job.salary_min_k}k-{item.job.salary_max_k}k</span>
                      )}
                    </div>
                  </div>
                  <div className={"match-scorebox" + (item.confidence ? ` conf-${item.confidence === "medium" ? "mid" : item.confidence}` : "")}>
                    <div className="match-scorebox-value">{(item.final_score * 100).toFixed(0)}<small>%</small></div>
                    <div className="match-scorebox-label">匹配度</div>
                    <MatchConfidenceBadge confidence={item.confidence} />
                  </div>
                </div>

                <div className="match-bar">
                  <div
                    className="match-bar-fill"
                    style={{ width: `${Math.min(100, Math.max(4, item.final_score * 100))}%` }}
                  />
                </div>

                <div className="match-explain">{item.explanation}</div>

                <div className="match-gap">
                  <span className="match-gap-label">已具备 {item.skill_gap.overlap_skills.length}</span>
                  {item.skill_gap.overlap_skills.slice(0, 6).map((skill) => (
                    <span key={skill} className="match-chip have">{skill}</span>
                  ))}
                </div>
                <div className="match-gap">
                  <span className="match-gap-label">需补齐 {item.skill_gap.missing_skills.length}</span>
                  {item.skill_gap.missing_skills.slice(0, MAX_MISSING_CHIPS).map((skill) => (
                    <span key={skill} className="match-chip miss">{skill}</span>
                  ))}
                  {item.skill_gap.missing_skills.length > MAX_MISSING_CHIPS && (
                    <span className="match-chip more">+{item.skill_gap.missing_skills.length - MAX_MISSING_CHIPS}</span>
                  )}
                </div>

                <div className="match-card-foot">
                  <button className="btn ghost sm" onClick={() => goPath(item)}>
                    查看学习路径 <Ic.back style={{ width: 13, height: 13, transform: "rotate(180deg)" }} />
                  </button>
                </div>
              </article>
            ))}
            {searched && !loading && items.length > 0 && (
              <div className="match-note">
                数据说明：匹配度为校准分数（语义相似 + 技能覆盖 + 行业趋势加权）；置信度由技能覆盖率、校准语义分与命中技能数综合分档。
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
