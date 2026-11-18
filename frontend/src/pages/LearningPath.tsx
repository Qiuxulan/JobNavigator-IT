import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { generateLearningPath, getRoleCatalog } from "../api";
import type { LearningPath, RoleCatalogItem } from "../api";
import { Ic } from "../components/Icons";
import PageHead from "../components/PageHead";
import { catColor } from "../components/Badge";

const DEFAULT_SKILLS = "Python, SQL, Docker, LangChain";

function splitSkills(value: string): string[] {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function cleanSkillIds(values: string[]): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value && value.trim()))));
}

function levelLabel(level?: string): string {
  if (level === "beginner") return "入门";
  if (level === "intermediate") return "进阶";
  if (level === "advanced") return "高级";
  return level || "资源";
}

function difficultyBadgeClass(difficulty?: string | null): string {
  if (difficulty === "advanced") return "conf-low";
  if (difficulty === "intermediate") return "conf-mid";
  return "conf-high";
}

function stars(score: number | null | undefined): string {
  if (score === null || score === undefined) return "";
  const n = Math.max(0, Math.min(5, Math.round(score * 5)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

export default function LearningPathPage() {
  const [searchParams] = useSearchParams();
  const presetRoleId = searchParams.get("role");
  const presetSkills = searchParams.get("skills");
  const [roles, setRoles] = useState<RoleCatalogItem[]>([]);
  const [targetId, setTargetId] = useState("");
  const [skillsText, setSkillsText] = useState(presetSkills || DEFAULT_SKILLS);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    getRoleCatalog().then((items) => {
      if (!alive) return;
      const sorted = [...items].sort((a, b) => (a.role_name_zh || a.role_name).localeCompare(b.role_name_zh || b.role_name, "zh-CN"));
      setRoles(sorted);
      const presetRole = presetRoleId ? sorted.find((role) => role.role_id === presetRoleId) : undefined;
      const defaultRole = presetRole || sorted.find((role) => /RAG|LLM|Agent/i.test(role.role_name)) || sorted[0];
      if (defaultRole) setTargetId(defaultRole.role_id);
    });
    return () => {
      alive = false;
    };
    // 仅首次加载应用 URL 预填参数
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const targetRole = useMemo(
    () => roles.find((role) => role.role_id === targetId) || null,
    [roles, targetId],
  );

  const categories = useMemo(() => {
    const map = new Map<string, number>();
    for (const role of roles) map.set(role.coarse_role, (map.get(role.coarse_role) || 0) + 1);
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  }, [roles]);

  async function submit() {
    if (!targetRole) return;
    setLoading(true);
    setError("");
    try {
      const candidateSkills = cleanSkillIds([...targetRole.required_skill_ids, ...targetRole.core_skill_ids]);
      const result = await generateLearningPath({
        skills: splitSkills(skillsText),
        targetJobId: targetRole.role_id,
        targetRole: targetRole.role_name,
        candidateSkills,
      });
      setPath(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "学习路径生成失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page path-page" style={{ maxWidth: 1200 }}>
      <PageHead
        eyebrow="Career Path Planner"
        title={<>根据技能缺口生成<span className="lite"> 学习路径</span></>}
        sub="使用职业推荐模块里的 GraphPathPlannerV2：输入当前技能，选择目标岗位，输出按前置依赖排序的学习步骤和资源。"
      />

      <div className="path-layout">
        <section className="card path-form">
          <div className="card-hd">
            <div>
              <div className="card-title">路径输入</div>
              <div className="card-desc">技能用逗号或换行分隔</div>
            </div>
          </div>
          <div className="card-bd">
            <label className="form-label" htmlFor="target-role">目标岗位</label>
            <select id="target-role" className="select" value={targetId} onChange={(event) => setTargetId(event.target.value)}>
              {roles.map((role) => (
                <option key={role.role_id} value={role.role_id}>
                  {role.role_name_zh || role.role_name} / {role.coarse_role}
                </option>
              ))}
            </select>

            <label className="form-label" htmlFor="skills">当前技能</label>
            <textarea
              id="skills"
              className="textarea"
              value={skillsText}
              onChange={(event) => setSkillsText(event.target.value)}
              rows={6}
            />

            <button className="btn primary lg" onClick={submit} disabled={loading || !targetRole}>
              <Ic.route />
              {loading ? "生成中..." : "生成学习路径"}
            </button>

            {targetRole && (
              <div className="path-target">
                <div className="path-target-title">{targetRole.role_name_zh || targetRole.role_name}</div>
                <div className="path-target-meta">
                  <span className="dot-cat" style={{ background: catColor(targetRole.coarse_role) }} />
                  {targetRole.role_name} · {targetRole.coarse_role} · 岗位样本 {targetRole.size || 0}
                </div>
                <div className="path-skill-cloud">
                  {targetRole.core_skills.slice(0, 10).map((skill) => (
                    <span key={skill}>{skill}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="card path-main">
          <div className="card-hd">
            <div>
              <div className="card-title">学习路径</div>
              <div className="card-desc">按技能前置关系和目标岗位重要性排序</div>
            </div>
            {path && (
              <div className="path-score">
                <span>{Math.round((path.score || 0) * 100)}</span>
                <small>score</small>
              </div>
            )}
          </div>
          <div className="card-bd">
            {error && <div className="error-box">{error}</div>}
            {!path && !error && (
              <div className="cmp-empty">
                <Ic.route />
                <div>选择岗位并输入技能后生成路径</div>
              </div>
            )}
            {path && path.total_steps === 0 && (
              <div className="cmp-empty path-congrats">
                <Ic.up />
                <div className="path-congrats-title">恭喜，技能已全覆盖！</div>
                <div className="path-congrats-sub">你已具备目标岗位的全部核心技能，无需额外学习步骤。可以直接查看岗位趋势或尝试对比其他岗位。</div>
              </div>
            )}
            {path && path.total_steps > 0 && (
              <>
                <div className="path-summary">
                  <div><b>{path.total_steps}</b><span>学习步骤</span></div>
                  <div><b>{path.total_estimated_hours || 0}</b><span>预计总学时</span></div>
                  <div><b>{splitSkills(skillsText).length}</b><span>已填技能</span></div>
                </div>
                <div className="path-rail">
                  {path.steps.map((step) => {
                    const stepHours = step.resources.reduce((sum, r) => sum + (r.hours_estimate || 0), 0);
                    return (
                      <article key={`${step.step_no}-${step.skill}`} className="path-step">
                        <div className="path-no">{step.step_no}</div>
                        <div className="path-step-body">
                          <div className="path-step-top">
                            <div className="path-step-title">{step.skill}</div>
                            {(() => {
                              const firstDifficulty = step.resources.find((r) => r.difficulty)?.difficulty;
                              return firstDifficulty ? (
                                <span className={"badge " + difficultyBadgeClass(firstDifficulty)}>
                                  {levelLabel(firstDifficulty)}
                                </span>
                              ) : null;
                            })()}
                            {stepHours > 0 && <span className="badge neutral">约 {Math.round(stepHours)} 学时</span>}
                          </div>
                          <div className="path-step-reason">{step.reason}</div>
                          <div className="resource-list">
                            {step.resources.slice(0, 3).map((resource) => (
                              <a
                                key={resource.url || resource.title}
                                className="resource-card"
                                href={resource.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <span>{resource.title}</span>
                                <small>
                                  {resource.provider && <em className="res-provider">{resource.provider}</em>}
                                  {resource.level && <i>{levelLabel(resource.level)}</i>}
                                  {resource.hours_estimate != null && <i>{Math.round(resource.hours_estimate)}h</i>}
                                </small>
                                {resource.quality_score != null && <small className="res-stars">{stars(resource.quality_score)}<u>{resource.quality_score.toFixed(2)}</u></small>}
                              </a>
                            ))}
                            {!step.resources.length && <span className="resource-empty">暂无资源链接</span>}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      <section className="card path-cats">
        <div className="card-bd">
          {categories.map(([name, count]) => (
            <div key={name} className="path-cat">
              <span className="dot-cat" style={{ background: catColor(name) }} />
              <span>{name}</span>
              <b>{count}</b>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
