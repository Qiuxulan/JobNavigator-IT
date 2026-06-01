from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from pipelines.extract.model_extractor import safe_extract_model_skills
except ImportError:  # pragma: no cover - supports direct CLI execution from this folder.
    from model_extractor import safe_extract_model_skills


ROOT = Path(__file__).resolve().parent
DEFAULT_VOCAB_PATH = ROOT / "skill_vocab.json"


EDUCATION_ORDER = ["中专", "大专", "本科", "硕士", "博士"]

ROLE_PATTERNS = {
    "Data Analyst": ["数据分析师", "data analyst", "business analyst", "bi analyst"],
    "Data Engineer": ["数据工程师", "data engineer"],
    "Machine Learning Engineer": ["机器学习工程师", "machine learning engineer", "ml engineer"],
    "AI Engineer": [
        "ai engineer", "人工智能工程师", "大模型工程师", "大模型应用工程师",
        "rag应用工程师", "agent应用工程师", "llm engineer",
    ],
    "Backend Engineer": ["后端工程师", "backend engineer", "java engineer", "python backend"],
    "Frontend Engineer": ["前端工程师", "frontend engineer"],
    "Full Stack Engineer": ["全栈工程师", "full stack engineer", "full-stack engineer"],
    "MLOps Engineer": ["mlops engineer", "机器学习平台工程师"],
    "DevOps Engineer": ["devops engineer", "运维开发工程师"],
    "Security Engineer": ["安全工程师", "security engineer"],
}


@dataclass
class ProjectInfo:
    project_name: str
    keywords: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class UserProfile:
    user_id: str
    name: str | None
    education: str | None
    major: str | None
    experience_years: float
    years_experience: float
    skills: list[str]
    projects: list[ProjectInfo]
    target_role: str | None
    city: str | None
    github_url: str | None
    raw_text: str


@dataclass
class StructuredJob:
    job_id: str
    title_raw: str | None
    title_normalized: str | None
    company: str | None
    location: str | None
    description: str
    required_skills: list[str]
    nice_to_have_skills: list[str]
    education_required: str | None
    min_experience_years: float
    salary_min: int | None
    salary_max: int | None
    source: str | None


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".json"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        return read_docx_text(path)
    raise ValueError(f"暂不支持 {suffix}，第一版建议先转成 .txt/.md/.docx")


def read_docx_text(path: Path) -> str:
    import html
    import zipfile

    with zipfile.ZipFile(path) as zf:
        data = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", data)
    text = html.unescape(text)
    return normalize_space(text)


def normalize_space(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_skill_vocab(path: Path = DEFAULT_VOCAB_PATH) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_skills(text: str, vocab: dict[str, list[str]]) -> list[str]:
    found: list[str] = []
    lower_text = text.lower()
    for canonical, aliases in vocab.items():
        candidates = [canonical, *aliases]
        if any(alias_match(lower_text, alias.lower()) for alias in candidates):
            found.append(canonical)
    return sorted(set(found), key=lambda x: x.lower())


def canonicalize_skill(skill: str, vocab: dict[str, list[str]]) -> str:
    lower_skill = skill.lower().strip()
    for canonical, aliases in vocab.items():
        candidates = [canonical, *aliases]
        if any(lower_skill == alias.lower().strip() for alias in candidates):
            return canonical
    return skill.strip()


def extract_skills_hybrid(text: str, vocab: dict[str, list[str]], use_model: bool = False) -> list[str]:
    rule_skills = extract_skills(text, vocab)
    if not use_model:
        return rule_skills
    model_skills = [canonicalize_skill(skill, vocab) for skill in safe_extract_model_skills(text)]
    return sorted(set([*rule_skills, *model_skills]), key=lambda x: x.lower())


def alias_match(lower_text: str, alias: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", alias):
        return alias in lower_text
    escaped = re.escape(alias)
    return re.search(rf"(?<![a-z0-9+#]){escaped}(?![a-z0-9+#])", lower_text) is not None


def extract_name(text: str) -> str | None:
    patterns = [
        r"(?:姓名|Name)[:：]\s*([A-Za-z\u4e00-\u9fff]{2,20})",
        r"^([A-Za-z\u4e00-\u9fff]{2,20})\s*(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.M)
        if match:
            name = match.group(1).strip()
            if name not in {"简历", "个人简历", "Resume"}:
                return name
    return None


def extract_education(text: str) -> str | None:
    hits = [edu for edu in EDUCATION_ORDER if edu in text]
    english_map = {
        "bachelor": "本科",
        "master": "硕士",
        "phd": "博士",
        "doctor": "博士",
        "associate": "大专",
    }
    lower_text = text.lower()
    for key, value in english_map.items():
        if key in lower_text:
            hits.append(value)
    if not hits:
        return None
    return max(hits, key=lambda edu: EDUCATION_ORDER.index(edu))


def extract_major(text: str) -> str | None:
    patterns = [
        r"(?:专业|Major)[:：]\s*([A-Za-z\u4e00-\u9fff /&+-]{2,40})",
        r"([计算机|软件工程|数据科学|人工智能|统计学|数学][A-Za-z\u4e00-\u9fff /&+-]{0,20})(?:专业|方向)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip(" ：:，,。.")
    return None


def extract_experience_years(text: str) -> float:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:年|years?|yrs?)\s*(?:以上)?\s*(?:工作|开发|相关)?\s*(?:经验|experience)?",
        r"(?:工作年限|经验|experience)[:：]?\s*(\d+(?:\.\d+)?)\s*(?:年|years?|yrs?)",
    ]
    values: list[float] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            try:
                values.append(float(match.group(1)))
            except ValueError:
                pass
    return max(values) if values else 0.0


def extract_target_role(text: str) -> str | None:
    patterns = [
        r"(?:求职意向|目标岗位|期望岗位|意向岗位|Target Role)[:：]\s*([^\n；;。]+)",
        r"(?:应聘|申请)\s*([A-Za-z\u4e00-\u9fff /+-]{2,40})(?:岗位|职位)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            raw = match.group(1).strip(" ：:，,。.")
            normalized = normalize_role(raw)
            return normalized or raw
    return normalize_role(text)


def extract_city(text: str) -> str | None:
    labeled = extract_labeled_value(text, ["城市", "地点", "所在地", "Location", "City"])
    if labeled:
        return labeled.split()[0].strip(" ，,。.")
    cities = [
        "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "武汉", "西安",
        "重庆", "天津", "长沙", "合肥", "厦门", "青岛", "大连", "郑州", "Remote", "远程",
    ]
    lower_text = text.lower()
    for city in cities:
        if city.lower() in lower_text:
            return city
    return None


def normalize_role(text: str | None) -> str | None:
    if not text:
        return None
    lower = text.lower()
    for normalized, aliases in ROLE_PATTERNS.items():
        if any(alias.lower() in lower for alias in aliases):
            return normalized
    return None


def extract_projects(text: str, skills: list[str]) -> list[ProjectInfo]:
    blocks = split_project_blocks(text)
    projects: list[ProjectInfo] = []
    for idx, block in enumerate(blocks, start=1):
        line = next((x.strip() for x in block.splitlines() if x.strip()), "")
        name = re.sub(r"^\d+[.、]\s*", "", line)
        name = name.split("：", 1)[0].split(":", 1)[0].strip()
        if not name or len(name) > 50:
            name = f"project_{idx}"
        tools = [skill for skill in skills if skill.lower() in block.lower() or skill in block]
        keywords = extract_keywords(block)
        projects.append(ProjectInfo(project_name=name, keywords=keywords, tools=tools, description=block.strip()))
    return projects[:8]


def split_project_blocks(text: str) -> list[str]:
    project_anchor = re.search(r"(项目经历|项目经验|Projects?|Project Experience)", text, flags=re.I)
    if not project_anchor:
        return []
    section = text[project_anchor.end() :]
    stop = re.search(r"\n\s*(教育经历|工作经历|实习经历|获奖|证书|技能|Skills?)[:：]?", section, flags=re.I)
    if stop:
        section = section[: stop.start()]
    blocks = re.split(r"\n\s*(?=\d+[.、])", section)
    return [b.strip() for b in blocks if len(b.strip()) >= 8]


def extract_keywords(text: str) -> list[str]:
    keywords = [
        "用户画像", "聚类", "分类", "回归", "推荐系统", "可视化", "特征工程", "模型评估",
        "数据清洗", "数据分析", "报表", "仪表盘", "RAG", "Agent", "知识图谱", "A/B测试",
    ]
    return [kw for kw in keywords if kw.lower() in text.lower()]


def extract_labeled_value(text: str, labels: list[str]) -> str | None:
    joined = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{joined})[:：]\s*([^\n]+)", text, flags=re.I)
    if not match:
        return None
    return match.group(1).strip(" ：:，,。.")


def extract_salary(text: str) -> tuple[int | None, int | None]:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*[kK]\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK]",
        r"(\d+(?:\.\d+)?)\s*万\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            if "万" in match.group(0):
                return int(low * 10000 / 12), int(high * 10000 / 12)
            return int(low * 1000), int(high * 1000)
    return None, None


def split_required_and_nice_skills(text: str, skills: list[str]) -> tuple[list[str], list[str]]:
    nice_markers = ["优先", "加分", "nice to have", "preferred", "plus"]
    nice: list[str] = []
    required: list[str] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for skill in skills:
        lower_skill = skill.lower()
        skill_lines = [line for line in lines if lower_skill in line.lower() or skill in line]
        if any(any(marker in line.lower() for marker in nice_markers) for line in skill_lines):
            nice.append(skill)
        else:
            required.append(skill)
    return sorted(set(required)), sorted(set(nice))


def parse_resume(
    text: str,
    user_id: str = "user_001",
    vocab_path: Path = DEFAULT_VOCAB_PATH,
    github_url: str | None = None,
    use_model: bool = False,
) -> UserProfile:
    text = normalize_space(text)
    vocab = load_skill_vocab(vocab_path)
    skills = extract_skills_hybrid(text, vocab, use_model=use_model)
    experience_years = extract_experience_years(text)
    return UserProfile(
        user_id=user_id,
        name=extract_name(text),
        education=extract_education(text),
        major=extract_major(text),
        experience_years=experience_years,
        years_experience=experience_years,
        skills=skills,
        projects=extract_projects(text, skills),
        target_role=extract_target_role(text),
        city=extract_city(text),
        github_url=github_url,
        raw_text=text,
    )


def parse_jd(
    text: str,
    job_id: str = "job_001",
    vocab_path: Path = DEFAULT_VOCAB_PATH,
    use_model: bool = False,
) -> StructuredJob:
    text = normalize_space(text)
    vocab = load_skill_vocab(vocab_path)
    skills = extract_skills_hybrid(text, vocab, use_model=use_model)
    required, nice = split_required_and_nice_skills(text, skills)
    title = extract_labeled_value(text, ["岗位名称", "职位名称", "岗位", "职位", "Job Title", "Title"])
    salary_min, salary_max = extract_salary(text)
    return StructuredJob(
        job_id=job_id,
        title_raw=title,
        title_normalized=normalize_role(title or text),
        company=extract_labeled_value(text, ["公司", "Company"]),
        location=extract_labeled_value(text, ["地点", "城市", "Location", "City"]),
        description=text,
        required_skills=required,
        nice_to_have_skills=nice,
        education_required=extract_education(text),
        min_experience_years=extract_experience_years(text),
        salary_min=salary_min,
        salary_max=salary_max,
        source=extract_labeled_value(text, ["来源", "Source"]),
    )


def to_jsonable(obj: Any) -> dict[str, Any]:
    return asdict(obj)


def to_app_user_profile(profile: UserProfile) -> dict[str, Any]:
    return {
        "user_id": profile.user_id,
        "skills": profile.skills,
        "target_role": profile.target_role,
        "years_experience": profile.years_experience,
        "education": profile.education,
        "city": profile.city,
        "github_url": profile.github_url,
    }


def to_processed_job(job: StructuredJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "title": job.title_raw or job.title_normalized or "",
        "title_raw": job.title_raw,
        "title_normalized": job.title_normalized,
        "location": job.location,
        "required_skills": job.required_skills,
        "nice_to_have_skills": job.nice_to_have_skills,
        "education_required": job.education_required,
        "min_experience_years": job.min_experience_years,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "source": job.source,
    }


def write_json(data: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A 模块第一版：简历 / JD 文本规则抽取")
    parser.add_argument("mode", choices=["resume", "jd"], help="抽取类型")
    parser.add_argument("input", type=Path, help="输入文本路径，支持 .txt/.md/.docx")
    parser.add_argument("--out", type=Path, default=None, help="输出 JSON 路径")
    parser.add_argument("--id", default=None, help="user_id 或 job_id")
    parser.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB_PATH, help="技能词表 JSON 路径")
    parser.add_argument("--use-model", action="store_true", help="启用 JobBERT 技能抽取增强，失败时自动回退规则版")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    text = read_text(args.input)
    if args.mode == "resume":
        obj = parse_resume(text, user_id=args.id or "user_001", vocab_path=args.vocab, use_model=args.use_model)
        default_out = ROOT / "outputs" / "user_profile.json"
    else:
        obj = parse_jd(text, job_id=args.id or "job_001", vocab_path=args.vocab, use_model=args.use_model)
        default_out = ROOT / "outputs" / "structured_job.json"

    out_path = args.out or default_out
    data = to_jsonable(obj)
    write_json(data, out_path)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
