"""国内为主的市场数据 API。

数据：
- data/gold/cn_market_v1.json         国内科技公司官网在招岗位（每日采集，pipelines/cn_jobs）
- data/gold/role_profiles_v3.json     全球 JD 样本（12.9 万条，海外为主），只作“全球参考”
- data/gold/skill_trend_panel_v3.json 全球技能月度面板，用于“全球趋势参考”

接口：
- GET /v1/market/overview                 国内概览：在招数、公司、城市、岗位大类、技能 Top、每日序列
- GET /v1/market/roles                    99 个岗位的国内在招数 + 全球样本量（列表/对比用）
- GET /v1/market/roles/{role}             单岗位：国内画像 + 全球参考（技能、海外薪资、需求占比走势）
- GET /v1/market/compare?roles=a,b,c      多岗位对比（最多 4 个）
- GET /v1/market/companies?region=cn|global
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.role_i18n import role_zh

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
CN_PATH = GOLD / "cn_market_v1.json"
ROLES_PATH = GOLD / "role_profiles_v3.json"
PANEL_PATH = GOLD / "skill_trend_panel_v3.json"
GLOBAL_COMPANY_PATH = GOLD / "company_hiring_momentum.json"
MIN_MONTH_TOTAL = 1000   # 全球面板中样本量低于此值的月份不参与占比走势，避免采样量波动被误读为需求变化

router = APIRouter(prefix="/v1/market", tags=["market"])


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


@lru_cache(maxsize=4)
def _load(path_str: str, mtime: float) -> dict[str, Any]:
    del mtime  # 仅用于让缓存随文件更新失效
    with open(path_str, encoding="utf-8") as f:
        return json.load(f)


def _json(path: Path, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise HTTPException(status_code=503, detail=f"数据文件缺失：{path.name}，请先运行对应流水线")
        return {}
    return _load(str(path), _mtime(path))


def _cn() -> dict[str, Any]:
    return _json(CN_PATH)


def _global_roles() -> dict[str, dict[str, Any]]:
    doc = _json(ROLES_PATH)
    roles = doc["roles"] if isinstance(doc["roles"], list) else list(doc["roles"].values())
    return {r["role_id"]: r for r in roles}


def _resolve_role(key: str) -> str:
    roles = _global_roles()
    if key in roles:
        return key
    low = key.strip().lower()
    for rid, r in roles.items():
        if low in {str(r.get("role_name", "")).lower(), str(r.get("fine_role", "")).lower(), role_zh(r.get("role_name")).lower()}:
            return rid
    raise HTTPException(status_code=404, detail=f"未知岗位：{key}")


def _global_share_series(role: dict[str, Any]) -> list[dict[str, Any]]:
    """全球样本中该岗位 JD 占当月总量的比例；只保留样本充足的月份。"""
    panel = _json(PANEL_PATH, required=False)
    totals = panel.get("total_jd_by_month") or {}
    out = []
    for row in role.get("monthly_jd_counts") or []:
        total = totals.get(row["month"], 0)
        if total >= MIN_MONTH_TOTAL:
            out.append({"month": row["month"], "count": row["count"], "total": total,
                        "share": round(row["count"] / total, 5)})
    return out


def _skill_names() -> dict[str, str]:
    cn = _cn()
    return {s["skill_id"]: s["name"] for s in cn.get("skills", [])}


def _global_brief(role: dict[str, Any]) -> dict[str, Any]:
    names = _skill_names()
    freq = role.get("skill_freq") or {}
    series = _global_share_series(role)
    trend = None
    if len(series) >= 6:
        recent = sum(x["share"] for x in series[-3:]) / 3
        prev = sum(x["share"] for x in series[-6:-3]) / 3
        trend = round(recent / prev - 1, 4) if prev else None
    return {
        "jd_count": role.get("jd_count", 0),
        "salary_usd": role.get("salary"),
        "remote_ratio": role.get("remote_ratio"),
        "top_skills": [{"skill_id": k, "name": names.get(k, k.replace("-", " ").title()), "share": v}
                       for k, v in sorted(freq.items(), key=lambda kv: -kv[1])[:15]],
        "share_series": series,
        "share_change_3m": trend,
        "note": "全球样本以海外岗位为主（国内占比不足 1%），薪资为海外美元口径，仅供参考。",
    }


def _cn_role(rid: str) -> dict[str, Any] | None:
    return next((r for r in _cn().get("roles", []) if r["role_id"] == rid), None)


@router.get("/overview")
def market_overview() -> dict[str, Any]:
    cn = _cn()
    roles = _global_roles()
    hot = sorted(cn.get("roles", []), key=lambda r: -r["open_roles"])[:12]
    skills = cn.get("skills", [])
    # 国内明显比海外更看重的技能：国内占比 ≥2%、海外占比 ≥1%（分母太小的比值没有意义），且比值 ≥2
    hotter = [s for s in skills if s["share_cn"] >= 0.02 and (s.get("share_global") or 0) >= 0.01
              and s["share_cn"] / s["share_global"] >= 2]
    return {
        "as_of": cn.get("as_of"), "first_day": cn.get("first_day"), "days_observed": cn.get("days_observed"),
        "generated_at": cn.get("generated_at"), "source": cn.get("source"),
        "summary": cn.get("summary"), "daily": cn.get("daily"),
        "hot_roles": [{"role_id": r["role_id"], "role_zh": r["role_zh"], "role_name": r["role_name"],
                       "coarse_role": r["coarse_role"], "open_roles": r["open_roles"], "share": r["share"],
                       "top_companies": [c["name"] for c in r["companies"][:3]]} for r in hot],
        "top_skills": skills[:20],
        "cn_hotter_skills": sorted(hotter, key=lambda s: -s["share_cn"])[:10],
        "companies": [{k: c[k] for k in ("source", "company", "open_roles", "momentum_7d", "new_7d",
                                         "days_observed", "top_roles", "top_cities")} for c in cn.get("companies", [])],
        "n_roles_total": len(roles),
        "notes": cn.get("notes", []),
    }


@router.get("/roles")
def market_roles() -> dict[str, Any]:
    cn_by_id = {r["role_id"]: r for r in _cn().get("roles", [])}
    rows = []
    for rid, r in _global_roles().items():
        c = cn_by_id.get(rid)
        rows.append({"role_id": rid, "role_name": r.get("role_name"), "role_zh": role_zh(r.get("role_name")),
                     "coarse_role": r.get("coarse_role"), "cn_open_roles": c["open_roles"] if c else 0,
                     "cn_top_company": c["companies"][0]["name"] if c and c["companies"] else None,
                     "global_jd_count": r.get("jd_count", 0)})
    rows.sort(key=lambda x: (-x["cn_open_roles"], -x["global_jd_count"]))
    return {"as_of": _cn().get("as_of"), "roles": rows}


@router.get("/roles/{role}")
def market_role(role: str) -> dict[str, Any]:
    rid = _resolve_role(role)
    g = _global_roles()[rid]
    return {"role_id": rid, "role_name": g.get("role_name"), "role_zh": role_zh(g.get("role_name")),
            "coarse_role": g.get("coarse_role"), "as_of": _cn().get("as_of"),
            "cn": _cn_role(rid), "global": _global_brief(g)}


@router.get("/compare")
def market_compare(roles: str = Query(..., description="逗号分隔的岗位 id 或名称，最多 4 个")) -> dict[str, Any]:
    keys = [k for k in (x.strip() for x in roles.split(",")) if k][:4]
    out = []
    for k in keys:
        rid = _resolve_role(k)
        g = _global_roles()[rid]
        c = _cn_role(rid) or {}
        gb = _global_brief(g)
        out.append({
            "role_id": rid, "role_zh": role_zh(g.get("role_name")), "role_name": g.get("role_name"),
            "cn_open_roles": c.get("open_roles", 0),
            "cn_top_companies": [x["name"] for x in c.get("companies", [])[:3]],
            "cn_top_cities": [x["name"] for x in c.get("cities", [])[:3]],
            "cn_top_skills": [x["name"] for x in c.get("top_skills", [])[:6]],
            "cn_experience": c.get("experience", []),
            "global_jd_count": gb["jd_count"], "global_share_change_3m": gb["share_change_3m"],
            "global_salary_usd_median": (gb["salary_usd"] or {}).get("median"),
            "global_top_skills": [x["name"] for x in gb["top_skills"][:6]],
        })
    return {"as_of": _cn().get("as_of"), "roles": out}


@router.get("/companies")
def market_companies(region: str = Query("cn", pattern="^(cn|global)$")) -> dict[str, Any]:
    if region == "cn":
        cn = _cn()
        return {"region": "cn", "as_of": cn.get("as_of"), "days_observed": cn.get("days_observed"),
                "companies": cn.get("companies", []),
                "note": "国内科技公司官网每日在招 IT 岗位；动能需连续采集 7 天后才有值。"}
    doc = _json(GLOBAL_COMPANY_PATH, required=False)
    comps = list((doc.get("companies") or {}).values())
    comps.sort(key=lambda c: -((c.get("latest") or {}).get("open_roles") or 0))
    return {"region": "global", "as_of": (doc.get("window") or [None, None])[-1],
            "companies": [{"company": c.get("company"), "domain": c.get("domain"), "sector": c.get("sector"),
                           "open_roles": (c.get("latest") or {}).get("open_roles"),
                           "momentum_7d": (c.get("momentum_7d") or {}).get("delta"),
                           "momentum_30d": (c.get("momentum_30d") or {}).get("delta")} for c in comps],
            "note": "海外科技公司招聘页（ATS）在招数，仅作国际参考。"}
