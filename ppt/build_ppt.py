"""基于 JobNavigator-IT_final.pptx 模板生成大创版 PPT。

做法：复制模板中的封面/目录/章节页/内容页底版/结束页，替换文字；内容页的图示用与模板一致的
字体、字号、配色（标题 微软雅黑 44pt #334251；小标题 思源黑体 3 Bold；正文 思源黑体 2；强调色 #EC3B3A）重绘。
"""
import copy
import json
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

SRC, OUT, MARKET, SHOTS = (Path(a) for a in sys.argv[1:5])
mk = json.loads(MARKET.read_text(encoding="utf-8"))

TITLE_FONT, H_FONT, B_FONT, NUM_FONT = "微软雅黑", "思源黑体 3 Bold", "思源黑体 2", "29LT Bukra Ultra-Bold"
DARK, TITLE_C, RED, GRAY, LIGHT, PINK = "3E3F43", "334251", "EC3B3A", "E7E8E7", "F7F6F9", "FFA2A5"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

prs = Presentation(SRC)
orig = list(prs.slides)


# ---------------------------------------------------------------- 幻灯片复制/删除
def dup(src):
    new = prs.slides.add_slide(src.slide_layout)
    rid_map = {}
    for rid, rel in src.part.rels.items():
        if rel.reltype.endswith("/notesSlide") or rel.reltype.endswith("/slideLayout"):
            continue
        rid_map[rid] = (new.part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref) if rel.is_external
                        else new.part.rels.get_or_add(rel.reltype, rel.target_part))
    # Slide.shapes 是惰性缓存的，必须原地替换 spTree 的子元素，不能整体替换 cSld
    new_csld, src_csld = new._element.cSld, src._element.cSld
    for child in list(new_csld):
        if child.tag != qn("p:spTree"):
            new_csld.remove(child)
    tree = new_csld.spTree
    for child in list(tree):
        tree.remove(child)
    for child in src_csld.spTree:
        tree.append(copy.deepcopy(child))
    for i, child in enumerate(c for c in src_csld if c.tag != qn("p:spTree")):
        new_csld.insert(i, copy.deepcopy(child))
    for child in list(new._element):
        if child.tag != qn("p:cSld"):
            new._element.remove(child)
    for child in src._element:
        if child.tag != qn("p:cSld"):
            new._element.append(copy.deepcopy(child))
    for el in new._element.iter():
        for k, v in list(el.attrib.items()):
            if k.startswith("{%s}" % R_NS) and v in rid_map:
                el.set(k, rid_map[v])
    return new


def drop(slide):
    lst = prs.slides._sldIdLst
    for sid in list(lst):
        if prs.part.related_part(sid.rId) is slide.part:
            prs.part.drop_rel(sid.rId)
            lst.remove(sid)


def _walk(shapes):
    for s in shapes:
        yield s
        if s.shape_type == 6:
            yield from _walk(s.shapes)


def shapes_by_text(slide, pred):
    return [s for s in _walk(slide.shapes) if s.has_text_frame and pred(s.text_frame.text.strip())]


def set_text(shape, lines):
    """保留第一个段落/第一个 run 的格式，替换为新文字（每个元素一个段落）。"""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]._p
    r0 = p0.find(qn("a:r"))
    rpr = copy.deepcopy(r0.find(qn("a:rPr"))) if r0 is not None and r0.find(qn("a:rPr")) is not None else None
    ppr = copy.deepcopy(p0.find(qn("a:pPr")))
    txBody = tf._txBody
    for p in txBody.findall(qn("a:p")):
        txBody.remove(p)
    for line in lines:
        p = etree.SubElement(txBody, qn("a:p"))
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        r = etree.SubElement(p, qn("a:r"))
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        etree.SubElement(r, qn("a:t")).text = line


def keep_only(slide, keep):
    for s in list(slide.shapes):
        if not keep(s):
            s._element.getparent().remove(s._element)


# ---------------------------------------------------------------- 绘制工具
def _font(run, font, size, bold=False, color=DARK):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
        el = rpr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rpr, qn(tag))
        el.set("typeface", font)


def text(slide, x, y, w, h, paras, font=B_FONT, size=22, bold=False, color=DARK, align=PP_ALIGN.LEFT,
         spacing=1.3, anchor=MSO_ANCHOR.TOP, bullet=False):
    """paras：字符串或 [(文字, {font,size,bold,color})...] 组成的列表，每项一个段落。"""
    if size <= 24 and font != NUM_FONT and size > 14:
        size = round(size * 1.18)
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        segs = para if isinstance(para, list) else [(para, {})]
        segs = [(sg, {**st, "size": round(st["size"] * 1.18)} if "size" in st and 14 < st["size"] <= 24 else st) for sg, st in segs]
        if bullet:
            segs = [("● ", {"color": RED, "size": size - 6})] + segs
        for seg, st in segs:
            r = p.add_run()
            r.text = seg
            _font(r, st.get("font", font), st.get("size", size), st.get("bold", bold), st.get("color", color))
    return tb


def box(slide, x, y, w, h, fill=LIGHT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line:
        s.line.color.rgb = RGBColor.from_string(line)
        s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def label(slide, x, y, w, h, s, fill=RED, color="FFFFFF", size=20, font=H_FONT):
    b = box(slide, x, y, w, h, fill=fill)
    tf = b.text_frame
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = s
    _font(r, font, size, True, color)
    return b


def arrow(slide, x, y, w=0.5, h=0.38, color=RED):
    a = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    a.fill.solid()
    a.fill.fore_color.rgb = RGBColor.from_string(color)
    a.line.fill.background()
    a.shadow.inherit = False
    return a


def num(slide, x, y, s, size=32, color=RED):
    return text(slide, x, y, 1.2, 0.8, [s], font=NUM_FONT, size=size, bold=True, color=color)


def picture(slide, path, x, y, w=None, h=None):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)
    pic.line.color.rgb = RGBColor.from_string(GRAY)
    pic.line.width = Pt(1)
    return pic


def footnote(slide, s):
    text(slide, 0.7, 10.55, 18.6, 0.45, [s], size=13, color="8A8F98")


# ---------------------------------------------------------------- 底版
COVER, TOC, SEC_A, SEC_B, CONTENT, END = orig[0], orig[1], orig[2], orig[11], orig[29], orig[31]


def content_slide(title):
    s = dup(CONTENT)
    keep_only(s, lambda sh: (sh.shape_type == 13 and sh.left > Inches(15)) or
              (sh.has_text_frame and sh.text_frame.text.strip() == "项目结论"))
    t = shapes_by_text(s, lambda x: x == "项目结论")[0]
    t.width = Inches(15)
    set_text(t, [title])
    return s


def section(no, title, en, base):
    s = dup(base)
    nums = shapes_by_text(s, lambda x: x in ("01", "02", "03", "04", "05"))
    set_text(nums[0], [no])
    big = [sh for sh in _walk(s.shapes) if sh.has_text_frame and sh.text_frame.text.strip()
           and sh.text_frame.paragraphs[0].runs and (sh.text_frame.paragraphs[0].runs[0].font.size or 0) >= Pt(60)
           and sh.text_frame.text.strip() not in ("01", "02", "03", "04", "05")][0]
    set_text(big, [title])
    eng = [sh for sh in _walk(s.shapes) if sh.has_text_frame and sh.text_frame.paragraphs[0].runs
           and sh.text_frame.paragraphs[0].runs[0].font.size == Pt(28)][0]
    set_text(eng, [en])
    eng.width = Inches(9)
    return s


S = mk["summary"]
SK = {x["skill_id"]: x for x in mk["skills"]}
pct = lambda v, d=0: f"{v * 100:.{d}f}%"
N = f"{S['open_roles']:,}"
N_CN = N                        # 国内在招 IT 岗位（官网直采，真实口径）
N_COMP = str(S["n_companies"])  # 官网直采公司数
AS_OF = mk["as_of"].replace("-", ".")
AI_SHARE = next(c["share"] for c in S["coarse_roles"] if c["name"] == "Emerging AI")

# ================================================================ 1 封面
s = dup(COVER)
set_text(shapes_by_text(s, lambda x: x.startswith("面向IT"))[0], ["面向国内IT求职者的", "\t\t实时职业导航与学习规划平台"])
t = shapes_by_text(s, lambda x: x.startswith("时间"))[0]
set_text(t, ["2026.11　　指导老师：王春阳"])
t.width = Inches(9.4)
set_text(shapes_by_text(s, lambda x: x.startswith("小组成员"))[0], ["团队成员：邱徐岚 朱翎融 陈云舒 邵子翀"])

# ================================================================ 2 目录
s = dup(TOC)
CH = [("项目背景与痛点", "Background"), ("产品功能与整体架构", "Product & Architecture"),
      ("数据与核心技术", "Data & Technology"), ("创新点与应用成效", "Innovation & Results"),
      ("项目规划与预期成果", "Plan & Outcomes")]
old_cn = ["项目功能与整体框架", "数据处理", "技术路线与算法设计", "项目成果", "效果验证"]
old_en = ["Functions and overall framework", "Data processing", "Technical route and algorithm design", "Project results", "Effect verification"]
# 目录原顺序：01 功能框架 / 02 数据处理 / 03 技术路线 / 04 项目成果(第4位) / 05 效果验证 —— 按位置重新赋值
cn_shapes = sorted([shapes_by_text(s, lambda x, o=o: x == o)[0] for o in old_cn], key=lambda sh: sh.left)
en_shapes = sorted([shapes_by_text(s, lambda x, o=o: x == o)[0] for o in old_en], key=lambda sh: sh.left)
for (cn, en), a, b in zip(CH, cn_shapes, en_shapes):
    set_text(a, [cn])
    set_text(b, [en])
    b.left, b.width = a.left, a.width
    b.top = a.top + Inches(1.45)

# ================================================================ 01 背景与痛点
section("01", "项目背景与痛点", "Background and pain points", SEC_A)

s = content_slide("选题背景：IT 岗位正在快速重组")
text(s, 1.0, 1.75, 8.6, 0.7, ["行业层面"], font=H_FONT, size=30, bold=True)
text(s, 1.0, 2.55, 8.6, 6.2, [
    [("2025 年我国数字经济核心产业增加值占 GDP ", {}), ("10.5%", {"color": RED, "bold": True})],
    [("2025 年 1–10 月 AI 新发布岗位同比增长 ", {}), ("543%", {"color": RED, "bold": True}), ("，高性能计算工程师供需比仅 0.31", {})],
    [("预计到 2030 年约 ", {}), ("39%", {"color": RED, "bold": True}), (" 的关键岗位技能将发生变革", {})],
    [("城镇青年（16–24 岁）失业率部分月份超过 ", {}), ("16%", {"color": RED, "bold": True}), ("，结构性矛盾突出", {})],
], size=22, bullet=True, spacing=1.45)
box(s, 10.3, 1.75, 8.9, 7.3, fill=LIGHT)
text(s, 10.7, 1.95, 8.2, 0.7, [f"我们的实时数据（截至 {AS_OF}）"], font=H_FONT, size=28, bold=True)
text(s, 10.7, 2.75, 8.2, 6.2, [
    [(f"{N_COMP} 家官网直采 + 国聘平台，在招 IT 岗位 ", {}), (N_CN, {"color": RED, "bold": True}), (" 个", {})],
    [("AI / 大模型方向占 ", {}), (pct(AI_SHARE), {"color": RED, "bold": True}), ("，为第一大方向", {})],
    [("要求大模型（LLM）技能的岗位占 ", {}), (pct(SK["llm"]["share_cn"]), {"color": RED, "bold": True}),
     ("，要求 AI Agent 的占 ", {}), (pct(SK["agent"]["share_cn"]), {"color": RED, "bold": True})],
    [("同一技能国内外差异明显：Go 国内 ", {}), (pct(SK["go"]["share_cn"], 1), {"color": RED, "bold": True}),
     (f"，海外样本仅 {pct(SK['go']['share_global'], 1)}", {})],
    [("岗位高度集中：北京占 ", {}), (pct(S["cities"][0]["share"]), {"color": RED, "bold": True}),
     ("，北上深杭合计超过 9 成", {})],
], size=22, bullet=True, spacing=1.45)
label(s, 1.0, 9.35, 18.2, 0.8, "岗位变化快、国内外差异大 —— 求职者需要“实时、本土化”的职业导航", size=22)
footnote(s, "资料来源：《2025年度人才迁徙报告》；世界经济论坛《Future of Jobs Report 2025》；《2024年中国网络招聘行业研究报告》；国家统计局；本项目官网采集数据。")

s = content_slide("用户痛点与现有产品不足")
PAINS = [("职业方向难抉择", "热门赛道变化快，不清楚哪些岗位真的在招、在哪些城市、门槛如何，容易盲目跟风"),
         ("能力差距不清晰", "岗位技能描述不统一，说不清自己缺的是基础、工具还是项目经验，也不知道先补哪个"),
         ("求职流程碎片化", "招聘平台、简历工具、测评刷题、课程网站各管一段，“选岗—诊断—学习”需要自己拼接"),
         ("信息不本土、不实时", "现有分析多基于海外或过时数据集，对国内大厂当下的需求和技能偏好反映不足")]
for i, (h, b) in enumerate(PAINS):
    x = 0.9 + i * 4.65
    box(s, x, 1.75, 4.35, 4.6, fill=LIGHT)
    num(s, x + 0.25, 1.9, f"0{i + 1}", size=30)
    text(s, x + 0.25, 2.75, 3.9, 0.7, [h], font=H_FONT, size=26, bold=True)
    text(s, x + 0.25, 3.55, 3.9, 2.7, [b], size=19, spacing=1.35)
text(s, 0.9, 6.55, 8, 0.6, [[("现有产品", {"bold": True}), ("——为什么还不够", {"color": "8A8F98", "size": 20})]], font=H_FONT, size=26)
EXIST = [("综合招聘平台（BOSS直聘、智联招聘）", "解决“投递”，缺少能力缺口与学习路径"),
         ("AI 简历/面试工具（Jobscan 等）", "聚焦简历与面试，不做跨阶段规划"),
         ("测评与刷题平台", "偏短期应试，不回答“该往哪个方向走”"),
         ("学术职业路径系统（CareerBERT 等）", "依赖私有轨迹数据，难以落地到国内用户")]
for i, (a, b) in enumerate(EXIST):
    y = 7.25 + i * 0.82
    box(s, 0.9, y, 18.3, 0.7, fill=LIGHT if i % 2 == 0 else "FFFFFF", line=GRAY)
    label(s, 1.05, y + 0.11, 0.48, 0.48, f"{i+1}", size=17)
    text(s, 1.75, y + 0.06, 7.6, 0.6, [[(a, {"bold": True})]], size=19, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 9.5, y + 0.06, 9.5, 0.6, [b], size=19, color="5C626C", anchor=MSO_ANCHOR.MIDDLE)

# ================================================================ 02 产品与架构
section("02", "产品功能与整体架构", "Product and architecture", SEC_B)

s = content_slide("产品功能总览：网页 + 微信小程序双端")
FUNCS = [("国内市场看板", f"{N_COMP} 家官网直采 + 国聘央企国企聚合，每日在招 {N_CN} 个 IT 岗位；公司、城市、方向分布与技能需求 Top"),
         ("岗位洞察与对比", "单岗位国内在招、主要公司/城市、技能与经验要求、官网真实岗位直达；最多 4 岗并排对比"),
         ("岗位匹配", "输入技能或简历，推荐最合适的岗位，给出匹配度、置信度与技能缺口"),
         ("学习路径", "按技能先修关系生成分阶段路径，挂载 2006 条课程/视频/项目资源"),
         ("知识图谱与行业新闻", "岗位—技能—事件关系图可拖动探索；13 个来源新闻每 3 小时更新"),
         ("AI 职业助手", "自然语言提问，14 个工具调用本地实时数据，回答注明数据口径与日期")]
for i, (h, b) in enumerate(FUNCS):
    col, row = i % 3, i // 3
    x, y = 0.9 + col * 6.15, 1.8 + row * 3.85
    box(s, x, y, 5.85, 3.55, fill=LIGHT)
    label(s, x + 0.3, y + 0.3, 3.2, 0.65, h, size=20)
    text(s, x + 0.3, y + 1.15, 5.3, 2.3, [b], size=20, spacing=1.4)
label(s, 0.9, 9.6, 18.25, 0.75, "个人中心同步收藏、学习路径存档与浏览历史；网页端与小程序共用同一套后端接口", fill=GRAY, color=DARK, size=20)

s = content_slide("整体技术架构")
ARCH_IMG = Path(__file__).parent / "assets" / "architecture.png"
p = s.shapes.add_picture(str(ARCH_IMG), Inches(0.9), Inches(1.62), height=Inches(7.9))
p.left = Inches(0.9 + (18.3 - p.width / 914400) / 2)
p.line.fill.background()
label(s, 0.9, 9.7, 18.3, 0.75, "五层流水线：数据逐层加工上行，线上只读本地产物——快、省、可解释", fill=GRAY, color=DARK, size=20)

s = content_slide("用户使用闭环")
STEPS = [("看市场", "首页看国内在招岗位、热门方向和技能需求"),
         ("选方向", "岗位洞察：在招数、公司城市、技能要求，多岗位对比"),
         ("测匹配", "输入技能/简历，得到匹配度、置信度与技能缺口"),
         ("补技能", "按先修关系生成学习路径与资源，存档跟踪"),
         ("问助手", "随时追问“为什么”“先学什么”，助手基于实时数据回答")]
for i, (h, b) in enumerate(STEPS):
    x = 0.8 + i * 3.8
    box(s, x, 2.0, 3.25, 3.9, fill=LIGHT)
    num(s, x + 0.25, 2.15, f"0{i + 1}", size=28)
    text(s, x + 0.25, 2.95, 2.9, 0.7, [h], font=H_FONT, size=28, bold=True)
    text(s, x + 0.25, 3.75, 2.85, 2.1, [b], size=19, spacing=1.4)
    if i < 4:
        arrow(s, x + 3.3, 3.75)
ex = mk_role = next(r for r in mk["roles"] if r["role_id"] == "role_001")
box(s, 0.9, 6.3, 18.3, 4.05, fill=LIGHT)
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.9), Inches(6.3), Inches(0.09), Inches(4.05))
bar.fill.solid(); bar.fill.fore_color.rgb = RGBColor.from_string(RED); bar.line.fill.background(); bar.shadow.inherit = False
text(s, 1.25, 6.5, 17.5, 0.7, ["示例：会 Python、SQL 的计算机专业大三学生，想做 AI 应用"], font=H_FONT, size=26, bold=True)
text(s, 1.25, 7.35, 17.6, 2.9, [
    [("看市场：", {"bold": True, "color": RED}), (f"AI / 大模型方向占国内在招的 {pct(AI_SHARE)}，其中 AI 智能体工程师在招 {ex['open_roles']} 个，主要在{ex['companies'][0]['name']}、{ex['companies'][1]['name']}", {})],
    [("测匹配：", {"bold": True, "color": RED}), ("该岗位国内要求 " + "、".join(f"{x['name']} {pct(x['share'])}" for x in ex["top_skills"][:4]) + "，缺口集中在 Agent 与工具调用", {})],
    [("补技能：", {"bold": True, "color": RED}), ("系统按先修关系给出 Python → 大模型应用 → Tool Calling → RAG 的学习顺序与资源", {})],
], size=20, bullet=True, spacing=1.5)

# ================================================================ 03 数据与技术
section("03", "数据与核心技术", "Data and core technology", SEC_A)

s = content_slide("技术路线总览：四层模型链")
CHAIN = [("数据层", f"国内 {N_COMP} 家官网直采 + 国聘平台（每日）｜全球 JD 12.99 万条（每月）｜14 源新闻（每 3 小时）｜WARN 裁员 · 公司在招 · HN 招聘", "B"),
         ("处理层", "IT 岗过滤 → 技能抽取（v2+v4 词表，910 条候选经 LLM 审核保留 174 条）→ 岗位归类（99 岗）→ 岗位画像（近期加权）", "B"),
         ("模型层", "Qwen3-Embedding-4B 语义召回 → LightGBM LambdaRank 学习排序 → p5/p95 分数校准 ｜ 技能先修 DAG + 多信号路径规划 ｜ Chronos-Bolt / Holt 回测选模预测", "R"),
         ("服务层", "FastAPI 30+ 接口：市场看板 · 岗位洞察 · 匹配 · 路径 · 趋势 · 公司雷达 · 新闻 · 助手 · 个人中心", "B")]
for i, (h, b, c) in enumerate(CHAIN):
    y = 1.75 + i * 1.75
    label(s, 0.9, y, 2.6, 1.45, h, size=24, fill=RED if c == "R" else DARK)
    box(s, 3.75, y, 15.4, 1.45, fill=LIGHT)
    text(s, 4.05, y + 0.1, 14.9, 1.3, [b], size=20, anchor=MSO_ANCHOR.MIDDLE, spacing=1.3)
    if i < 3:
        a = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(2.0), Inches(y + 1.44), Inches(0.4), Inches(0.32))
        a.fill.solid(); a.fill.fore_color.rgb = RGBColor.from_string(RED); a.line.fill.background(); a.shadow.inherit = False
text(s, 0.9, 8.85, 18.3, 1.4, [
    [("设计原则：", {"bold": True}), ("线上服务只读取本地产物，主链路零 API 黑盒；每个模型都有离线评估报告（reports/eval/），指标可复现；月度 14 步自动化链路保证时效", {})],
], size=20, spacing=1.4)
footnote(s, "模型链完整方法说明见仓库 reports/model_chain.md。")

s = content_slide("数据体系：国内实时为主，全球样本为参考")
ROWS = [("数据", "来源", "规模", "更新", "用途"),
        ("国内在招岗位", f"{N_COMP} 家官网直采（腾讯/字节/阿里系/小米/蔚来…）+ 国聘央企国企", f"{N_CN} 个 IT 岗位", "每日", "市场看板、岗位洞察、助手"),
        ("全球 JD 样本", "8 个公开招聘数据集融合（海外为主）", "12.99 万条 · 37 个月", "每月", "岗位画像、技能趋势参考"),
        ("行业新闻", "IT之家、InfoQ、36氪、HackerNews 等 14 源", "1.4 万+ 条", "每 3 小时", "新闻页、助手、证据"),
        ("学习资源", "Coursera、B 站、GitHub、官方文档", "2006 条（162 门含章节）", "按需", "学习路径"),
        ("技能与岗位体系", "自建词表 + 岗位聚类与人工校对", "630 技能 · 99 细分岗位", "每月", "抽取、归类、图谱")]
tbl = s.shapes.add_table(len(ROWS), 5, Inches(0.9), Inches(1.85), Inches(18.3), Inches(6.7)).table
widths = [2.9, 5.6, 3.8, 1.8, 4.2]
for j, w in enumerate(widths):
    tbl.columns[j].width = Inches(w)
for i, row in enumerate(ROWS):
    for j, val in enumerate(row):
        c = tbl.cell(i, j)
        c.fill.solid()
        c.fill.fore_color.rgb = RGBColor.from_string(RED if i == 0 else (LIGHT if i % 2 else "FFFFFF"))
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = c.text_frame
        tf.paragraphs[0].text = ""
        r = tf.paragraphs[0].add_run()
        r.text = val
        _font(r, H_FONT if i == 0 or j == 0 else B_FONT, 24 if i == 0 else 21, i == 0 or j == 0, "FFFFFF" if i == 0 else DARK)
label(s, 0.9, 8.85, 18.3, 0.8, "官网不公开薪资：系统不展示、也不编造人民币薪资，海外美元薪资一律标注“海外参考”", fill=GRAY, color=DARK, size=20)

s = content_slide("国内实时岗位数据管线")
PIPE = [("官网采集", f"{N_COMP} 家直采 + 国聘\n公开接口每日采集"), ("IT 岗过滤", "研发/算法/测试/运维/\n数据/安全/产品"),
        ("技能抽取", "中英文词典 +\n中文同义词"), ("岗位归类", "60+ 条中文岗位名\n规则 → 99 岗位"),
        ("进出记录", "首次/最后出现日期\n→ 新增与下架"), ("市场聚合", "公司/城市/方向/\n技能/经验")]
for i, (h, b) in enumerate(PIPE):
    x = 0.8 + i * 3.15
    label(s, x, 1.95, 2.6, 0.75, h, size=21)
    box(s, x, 2.8, 2.6, 1.7, fill=LIGHT)
    text(s, x + 0.1, 2.9, 2.4, 1.5, b.split("\n"), size=17, align=PP_ALIGN.CENTER, spacing=1.3, anchor=MSO_ANCHOR.MIDDLE)
    if i < 5:
        arrow(s, x + 2.63, 2.1, w=0.48, h=0.42)
KPI = [(N_CN, "当天在招 IT 岗位"), (pct(S["skill_coverage"], 1), "岗位成功抽取到技能"), ("75.2%", "岗位归入具体细分岗位"), (f"{S['n_companies']} / {S['n_companies']}", "官网直采公司成功")]
for i, (v, l) in enumerate(KPI):
    x = 0.9 + i * 4.6
    text(s, x, 5.0, 4.3, 1.0, [v], font=NUM_FONT, size=40, bold=True, color=RED, align=PP_ALIGN.CENTER)
    text(s, x, 6.0, 4.3, 0.6, [l], size=20, align=PP_ALIGN.CENTER, color="5C626C")
text(s, 0.9, 7.0, 18.3, 3.2, [
    "每日记录每个岗位首次出现与最后出现的日期，自动得到每天在招数、新增数、下架数——国内趋势来自真实的逐日观测，而不是二手数据集",
    "岗位名与职能类别双重过滤，剔除销售、运营、门店等非技术岗与海外城市岗位；过滤规则迭代时自动对历史记录重算，口径前后一致",
    "新增一家公司只需写一个采集函数，过滤、归类、聚合逻辑全部复用",
], size=20, bullet=True, spacing=1.45)

s = content_slide("核心技术一：岗位画像与语义召回")
box(s, 0.9, 1.7, 8.8, 4.7, fill=LIGHT)
text(s, 1.25, 1.85, 8.1, 0.7, ["岗位画像：99 岗 × 12.99 万真实 JD"], font=H_FONT, size=28, bold=True)
text(s, 1.25, 2.7, 8.1, 3.6, [
    "近期加权技能频率：越近的 JD 权重越高，技能要求跟着市场走",
    "真实薪资分布、远程比例、趋势动量逐岗统计，不人工填写",
    "技能词表 v2+v4：910 条官方候选经 LLM 审核保留 174 条硬技能，覆盖率 86.8%",
], size=20, bullet=True, spacing=1.45)
box(s, 10.3, 1.7, 8.8, 4.7, fill=LIGHT)
text(s, 10.65, 1.85, 8.1, 0.7, ["语义召回：Qwen3-Embedding-4B"], font=H_FONT, size=28, bold=True)
text(s, 10.65, 2.7, 8.1, 3.6, [
    "用户画像文本与岗位文本在同一 JD 语义空间编码（2560 维向量）",
    "pgvector 余弦检索 TopK，中英文简历通吃，明显优于 JobBERT",
    "本地推理，召回不依赖任何外部 API",
], size=20, bullet=True, spacing=1.45)
for i, (v, l) in enumerate([("99", "细分岗位画像"), ("12.99 万", "建模 JD 条数"), ("86.8%", "技能抽取覆盖率"), ("2560 维", "本地语义向量")]):
    x = 0.9 + i * 4.6
    text(s, x, 6.5, 4.3, 1.0, [v], font=NUM_FONT, size=40, bold=True, color=RED, align=PP_ALIGN.CENTER)
    text(s, x, 7.5, 4.3, 0.6, [l], size=20, align=PP_ALIGN.CENTER, color="5C626C")
label(s, 0.9, 8.9, 18.3, 0.8, "画像每月随新 JD 自动重建——岗位门槛反映的是“最近的市场”，不是几年前的教材", fill=GRAY, color=DARK, size=20)

s = content_slide("核心技术二：学习排序（LTR）与分数校准")
STG = [("三级排序", ["公式分：0.15×覆盖 + 0.70×语义 + 0.15×趋势（58 例网格调参）", "LTR 主排序：LightGBM LambdaRank，21 维本地特征", "可选 LLM 精排：DeepSeek 全局重排（非必需）"]),
       ("蒸馏训练", ["250 个分层合成画像 × Top10 候选 = 2500 条教师标签", "教师标签有区分度：0/1/2/3 分 = 345/1423/543/189", "5-fold 分组交叉验证 NDCG@5 = 0.937"]),
       ("校准与置信", ["p5/p95 锚点分段线性校准，展示分区分度 ×2.9", "排序键保持原始分：分数拉开但顺序不变（单调性证明）", "高/中/低置信度 = 覆盖率+语义分+命中技能数，规则公开"])]
for i, (h, items) in enumerate(STG):
    x = 0.9 + i * 6.2
    label(s, x, 1.9, 5.6, 0.8, h, size=24)
    box(s, x, 2.85, 5.6, 3.55, fill=LIGHT)
    text(s, x + 0.3, 3.0, 5.15, 3.35, items, size=18, bullet=True, spacing=1.35)
EV2 = [("排序方案", "Hit@1", "NDCG@5", "说明"),
       ("纯公式基线", "0.793", "0.695", "手工权重，可解释"),
       ("LTR 本地模型（线上）", "1.000", "0.774", "零 API 调用，< 1 秒"),
       ("LLM 教师（DeepSeek）", "0.983", "0.782", "15-30 秒，需联网 API")]
tbl = s.shapes.add_table(len(EV2), 4, Inches(0.9), Inches(6.75), Inches(18.3), Inches(2.6)).table
for j, w in enumerate([5.2, 3.0, 3.0, 7.1]):
    tbl.columns[j].width = Inches(w)
for i, row in enumerate(EV2):
    for j, val in enumerate(row):
        c = tbl.cell(i, j)
        c.fill.solid()
        c.fill.fore_color.rgb = RGBColor.from_string(RED if i == 0 else (LIGHT if i % 2 else "FFFFFF"))
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        r = c.text_frame.paragraphs[0].add_run()
        r.text = val
        _font(r, H_FONT if i == 0 or j == 0 else B_FONT, 22 if i == 0 else 20, i == 0 or j == 0 or i == 2,
              "FFFFFF" if i == 0 else (RED if i == 2 else DARK))
label(s, 0.9, 9.55, 18.3, 0.75, "蒸馏的本地小模型反超教师：Hit@1 = 1.000（58 例评估集），特征重要性完全可解释", fill=GRAY, color=DARK, size=20)

s = content_slide("核心技术三：先修约束的学习路径")
text(s, 0.9, 1.8, 8.8, 0.7, ["技能先修关系图（DAG）"], font=H_FONT, size=28, bold=True)
text(s, 0.9, 2.6, 8.8, 3.4, ["443 条先修边，覆盖岗位核心技能", "LLM 三路独立构建 → 交集/投票融合 → 环检测去环", "避免“先学框架再学语言”这类顺序错误"], size=21, bullet=True, spacing=1.5)
text(s, 10.3, 1.8, 8.8, 0.7, ["多信号路径规划"], font=H_FONT, size=28, bold=True)
text(s, 10.3, 2.6, 8.8, 3.4, ["拓扑约束：先修未满足的技能不会被提前安排", "难度匹配（最近发展区）+ 资源覆盖 + 学时惩罚", "已会技能可迁移折算，缩短路径"], size=21, bullet=True, spacing=1.5)
for i, (v, l) in enumerate([("443", "先修边"), ("2006", "学习资源"), ("0.343", "个性化一致性 τ（旧版 0.001）"), ("92.5%", "资源链接直连率")]):
    x = 0.9 + i * 4.6
    text(s, x, 6.2, 4.3, 1.0, [v], font=NUM_FONT, size=40, bold=True, color=RED, align=PP_ALIGN.CENTER)
    text(s, x, 7.2, 4.3, 0.6, [l], size=20, align=PP_ALIGN.CENTER, color="5C626C")
label(s, 0.9, 8.6, 18.3, 0.8, "输出：分阶段学习步骤 + 预计学时 + 每一步的课程/视频/项目资源，可存档到个人中心持续跟踪", fill=GRAY, color=DARK, size=20)

s = content_slide("核心技术四：行业趋势预测（时序基础模型）")
box(s, 0.9, 1.7, 8.8, 4.7, fill=LIGHT)
text(s, 1.25, 1.85, 8.1, 0.7, ["技能趋势面板（份额制，抗采集偏差）"], font=H_FONT, size=26, bold=True)
text(s, 1.25, 2.7, 8.1, 3.6, [
    "630 个技能 × 37 个月 JD 份额序列——用“占比”而非“条数”，采集量波动不会误读为需求变化",
    "状态机输出新兴/上升/平稳/衰退榜；新兴判定优先于数据量门槛，新词不被误杀",
    "岗位级预测：五模型回测选模，置信度如实标注",
], size=20, bullet=True, spacing=1.4)
box(s, 10.3, 1.7, 8.8, 4.7, fill=LIGHT)
text(s, 10.65, 1.85, 8.1, 0.7, ["Chronos-Bolt：逐技能回测选模上岗"], font=H_FONT, size=26, bold=True)
text(s, 10.65, 2.7, 8.1, 3.6, [
    "亚马逊时序基础模型（GPU 本地推理，峰值显存仅 106MB）",
    "与 damped Holt、naive 在同一滚动交叉验证协议下对擂（6 原点 × 24 月）",
    "保守替换：仅 CV 误差严格更优才换——207 个技能中 111 个用 Chronos",
], size=20, bullet=True, spacing=1.4)
for i, (v, l) in enumerate([("0.307", "Chronos 中位 MAPE"), ("-17.7%", "较 Holt 误差下降"), ("66.7%", "对最优基线胜率"), ("37 月", "月度序列长度")]):
    x = 0.9 + i * 4.6
    text(s, x, 6.5, 4.3, 1.0, [v], font=NUM_FONT, size=40, bold=True, color=RED, align=PP_ALIGN.CENTER)
    text(s, x, 7.5, 4.3, 0.6, [l], size=20, align=PP_ALIGN.CENTER, color="5C626C")
label(s, 0.9, 8.9, 18.3, 0.8, "不迷信大模型：回测赢不了经典方法的技能就保留 Holt/naive——每个技能的预测方法都可在页面查看", fill=GRAY, color=DARK, size=20)

s = content_slide("核心技术五：市场信号与公司雷达")
SIG = [("公司招聘动能", ["国内 42 家官网直采 + 海外 25 家头部公司日度在招快照", "7 日 / 30 日净增与涨跌幅，识别真实扩张", "状态标签：扩张中 / 降温 / 平稳 / 有裁员备案"]),
       ("收缩信号（国内直测 + 海外先行）", ["国内：42 家公司逐日追踪岗位集中下架与在招净减（国内无法定裁员申报，下架即直测信号）", "海外：美国 WARN Act 法定裁员备案 1748 条，作先行指标", "公司名归一化防误匹配（Meta Platforms → meta）"]),
       ("开发者市场热度", ["HN “Who is Hiring” 月度招聘帖 23 个月回填", "在招帖量、远程岗位比例、薪资披露比例", "与技能面板交叉验证趋势方向"])]
for i, (h, items) in enumerate(SIG):
    x = 0.9 + i * 6.2
    label(s, x, 1.9, 5.6, 0.8, h, size=23)
    box(s, x, 2.85, 5.6, 3.75, fill=LIGHT)
    text(s, x + 0.3, 3.0, 5.15, 3.55, items, size=19, bullet=True, spacing=1.4)
for i, (h, b) in enumerate([
    ("前端呈现", "雷达页三榜（扩张 / 裁员 / HC 大户）→ 点击公司进入详情：28 天在招走势、动量指标、裁员记录、相关新闻"),
    ("数据诚实", "裁员名单来自 WARN 备案、海外动能榜来自 25 家追踪池、国内榜来自 42 家公司逐日在招记录，三者口径在页面明确标注，不混用"),
]):
    x = 0.9 + i * 9.35
    box(s, x, 7.1, 8.95, 2.4, fill=LIGHT)
    label(s, x + 0.3, 7.35, 2.3, 0.6, h, size=19)
    text(s, x + 0.3, 8.15, 8.4, 1.3, [b], size=19, spacing=1.35)

s = content_slide("核心技术六：基于实时数据的职业助手")
text(s, 0.9, 1.8, 8.4, 0.7, ["工具调用，而不是凭记忆回答"], font=H_FONT, size=28, bold=True)
text(s, 0.9, 2.6, 8.4, 6.0, [
    "DeepSeek 驱动，14 个工具全部落在本地数据：国内市场、岗位匹配、技能缺口、学习路径、新闻检索、证据回溯等",
    "国内问题优先调用国内实时数据，回答写明“截至某日、N 个在招岗位”",
    "数据分层：国内实时 / 新闻 / 海外参考，口径不混用；官网无薪资时明确说明，不编造",
], size=21, bullet=True, spacing=1.5)
box(s, 9.9, 1.8, 9.3, 7.9, fill=LIGHT)
text(s, 10.2, 1.95, 8.8, 0.6, ["用户：国内哪些公司在招 AI 智能体工程师？要什么技能？"], font=H_FONT, size=20, bold=True)
top = ex["companies"][:4]
text(s, 10.2, 2.75, 8.8, 6.8, [
    f"助手：截至 {mk['as_of']}，国内大厂官网共有 {ex['open_roles']} 个在招岗位。",
    "公司：" + "、".join(f"{c['name']} {c['count']}" for c in top),
    "城市：" + "、".join(f"{c['name']} {c['count']}" for c in ex["cities"][:4]),
    "技能：" + "、".join(f"{x['name']} {pct(x['share'])}" for x in ex["top_skills"][:6]),
    "建议：AI Agent 与 LLM 是硬门槛；Go 的要求比例高于 Java，偏工程架构方向；按 Python → 大模型应用 → Tool Calling → RAG 补齐。",
], size=19, spacing=1.45, color="3E3F43")

s = content_slide("自动化工程与质量体系")
text(s, 0.9, 1.8, 18.3, 0.7, ["月度自动更新链路（14 步，cron 每月执行，全程无人值守）"], font=H_FONT, size=26, bold=True)
FLOW = ["多源采集", "融合去重", "技能增强", "岗位归类", "岗位画像", "技能面板", "时序选模", "岗位预测", "向量重建"]
for i, step in enumerate(FLOW):
    x = 0.9 + (i % 9) * 2.06
    box(s, x, 2.6, 1.86, 0.9, fill=LIGHT if i % 2 else "FFE9E9")
    text(s, x, 2.62, 1.86, 0.86, [step], size=16, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if i < 8:
        arrow(s, x + 1.86, 2.86, w=0.2, h=0.3)
text(s, 0.9, 3.9, 18.3, 1.2, [
    [("新闻每 3 小时、国内岗位每日、全球数据每月；", {}), ("证据检索窗口随分片自动滚动，永不过期", {"color": RED, "bold": True})],
], size=20, spacing=1.4)
text(s, 0.9, 5.0, 18.3, 0.7, ["质量门：每个模型都有离线评估，达标才上线"], font=H_FONT, size=26, bold=True)
QA = [("159 项", "pytest 单元+接口契约测试，全绿"), ("58 例", "匹配评估集，三轮调参回归"), ("9 份", "reports/eval/ 报告可复现"), ("0 假数据", "前端数字全部来自真实数据")]
for i, (v, l) in enumerate(QA):
    x = 0.9 + i * 4.6
    text(s, x, 5.85, 4.3, 1.0, [v], font=NUM_FONT, size=40, bold=True, color=RED, align=PP_ALIGN.CENTER)
    text(s, x, 6.95, 4.3, 1.2, [l], size=18, align=PP_ALIGN.CENTER, color="5C626C", spacing=1.3)
text(s, 0.9, 7.75, 18.3, 2.6, [
    "降级设计：LLM API 不可用时匹配自动回退本地 LTR；面板文件缺失自动回退上一版本；证据目录不可读回退兜底窗口",
    "所有评估脚本在 experiments/ 可复跑：匹配回归、路径评估、校准拟合、Chronos 对擂、LTR 训练",
], size=20, bullet=True, spacing=1.45)

# ================================================================ 04 创新与成效
section("04", "创新点与应用成效", "Innovation and results", SEC_B)

s = content_slide("项目创新点")
INNOV = [("国内一体化实时数据底座",
          f"{N_COMP} 家官网直采 + 国聘平台每日更新，逐日快照把“当天在招”累积成真实时间序列；国内 vs 海外同技能对照（大模型 {pct(SK['llm']['share_cn'])} vs {pct(SK['llm']['share_global'])}、Go {pct(SK['go']['share_cn'], 1)} vs {pct(SK['go']['share_global'], 1)}）；市场、匹配、路径、助手全部模块共用同一数据底座，取代滞后、以海外为主的二手数据集"),
         ("用户全流程闭环，而非功能拼凑",
          "“看市场 → 选方向 → 测匹配 → 补技能 → 问助手”五环相扣：看板发现方向后进岗位洞察对比；匹配结果一键转交职业助手追问；技能缺口直接生成受先修约束的学习路径；路径存档到“我的”持续跟踪——五个模块跑在同一条数据链上"),
         ("数据驱动的职业 Agent",
          "单智能体函数调用架构：DeepSeek 只负责理解意图与组织语言，14 个工具是读取本地实时数据的确定性函数；回答强制携带数据口径与日期（“截至某日、N 个在招岗位”）；官网未公开的薪资明确说不知道——从机制上杜绝编造，而非靠提示词约束"),
         ("可解释的匹配与学习路径",
          "匹配：LTR 排序 + 分位数校准 + 三档置信度 + 技能缺口清单，分数可不可信如实告知；路径：443 条先修边构成 DAG 约束学习顺序，LLM 三路构建投票去环——每条建议都能回答“为什么推荐、为什么先学这个”")]
for i, (h, b) in enumerate(INNOV):
    col, row = i % 2, i // 2
    x, y = 0.9 + col * 9.25, 1.8 + row * 4.25
    box(s, x, y, 8.95, 3.95, fill=LIGHT)
    num(s, x + 0.3, y + 0.2, f"0{i + 1}", size=34)
    text(s, x + 1.55, y + 0.3, 7.2, 0.7, [h], font=H_FONT, size=26, bold=True)
    text(s, x + 0.35, y + 1.2, 8.3, 2.7, [b], size=17, spacing=1.35)

s = content_slide("应用成效：国内市场看板")
picture(s, SHOTS / "p_home.png", 0.9, 1.7, w=12.6)
text(s, 13.9, 1.8, 5.4, 8.5, [
    [("实时：", {"bold": True}), ("每天采集 " + N_COMP + " 家官网与国聘平台，首页即当天在招情况", {})],
    [("本土：", {"bold": True}), ("默认国内口径，海外数据收进“海外参考”开关", {})],
    [("可比：", {"bold": True}), ("国内技能需求榜 + 国内比海外更看重的技能", {})],
    [("可追溯：", {"bold": True}), ("岗位榜单一键进入详情，岗位可直达官网投递页", {})],
], size=20, bullet=True, spacing=1.6)

s = content_slide("应用成效：岗位洞察与对比")
picture(s, SHOTS / "p_role.png", 0.9, 1.7, w=12.6)
text(s, 13.9, 1.8, 5.4, 8.5, [
    [("一页看懂一个岗位：", {"bold": True}), ("国内在招数、主要公司与城市、经验要求", {})],
    [("技能要求国内 vs 海外", {"bold": True}), ("并排对比", {})],
    [("真实岗位：", {"bold": True}), ("官网岗位列表，点击直达投递", {})],
    [("岗位对比：", {"bold": True}), ("原独立页面并入详情页，最多 4 岗并排比较", {})],
], size=20, bullet=True, spacing=1.6)

s = content_slide("应用成效：微信小程序端")
MP_SHOTS = [("mp_assistant.png", "AI 职业助手", "工具调用实时数据，回答带数据口径"),
            ("mp_radar.png", "行业雷达", "公司扩张 / 裁员 / HC 三榜，可进详情"),
            ("mp_match.png", "岗位匹配", "校准匹配度 + 置信度徽标 + 一键问助手"),
            ("mp_profile.png", "个人中心", "收藏 / 路径 / 历史云端同步")]
shown = 0
for fname, cap, desc in MP_SHOTS:
    f = SHOTS / fname
    if not f.exists():
        continue
    x = 1.1 + shown * 4.55
    pic = s.shapes.add_picture(str(f), Inches(x), Inches(1.75), height=Inches(6.4))
    pic.line.color.rgb = RGBColor.from_string(GRAY)
    pic.line.width = Pt(1.25)
    text(s, x - 0.3, 8.3, 4.0, 0.6, [cap], font=H_FONT, size=22, bold=True, align=PP_ALIGN.CENTER)
    text(s, x - 0.3, 8.95, 4.0, 1.1, [desc], size=17, align=PP_ALIGN.CENTER, color="5C626C", spacing=1.3)
    shown += 1
if shown == 0:
    text(s, 0.9, 4.0, 18.3, 1.0, ["（小程序截图待补充）"], size=22, color="8A8F98")

s = content_slide("应用成效：知识图谱与行业新闻")
picture(s, SHOTS / "p_graph.png", 0.9, 1.7, w=9.0)
picture(s, SHOTS / "p_news.png", 10.2, 1.7, w=9.0)
text(s, 0.9, 7.6, 9.0, 2.6, ["岗位—技能—事件关系图：节点可拖动、缩放，四种视角切换（岗位图谱 / 全量总览 / 学习路径 / 事件影响）"], size=20, spacing=1.45)
text(s, 10.2, 7.6, 9.0, 2.6, ["14 个中英文来源每 3 小时更新，按招聘、融资、裁员、政策、技术分类，可按岗位检索相关动态"], size=20, spacing=1.45)

s = content_slide("效果评估")
EV = [("模块", "评估方式", "结果"),
      ("国内数据采集", "官网公开接口每日直采", f"{N_COMP} 家官网直采 · {N_CN} 个 IT 岗位 · 技能覆盖 {pct(S['skill_coverage'], 1)} · 归类 75.2%"),
      ("岗位匹配", "58 例评估集，对比随机/热门/BM25/纯语义/LLM", "LTR：Hit@1 1.000，NDCG@5 0.774，零 API 调用"),
      ("分数校准", "1740 对分布拟合 + 单调性检验", "展示分区分度 ×2.9，排序结果不变"),
      ("学习路径", "个性化一致性、先修冲突、资源可用性", "τ 0.001 → 0.343；零先修冲突；链接直连 92.5%"),
      ("技能占比预测", "逐技能滚动交叉验证", "Chronos-Bolt 中位 MAPE 0.307，较 Holt 0.373 降低 17.7%"),
      ("工程质量", "单元 + 接口契约测试", "pytest 159 项通过")]
tbl = s.shapes.add_table(len(EV), 3, Inches(0.9), Inches(1.85), Inches(18.3), Inches(8.2)).table
for j, w in enumerate([3.4, 6.6, 8.3]):
    tbl.columns[j].width = Inches(w)
for i, row in enumerate(EV):
    for j, val in enumerate(row):
        c = tbl.cell(i, j)
        c.fill.solid()
        c.fill.fore_color.rgb = RGBColor.from_string(RED if i == 0 else (LIGHT if i % 2 else "FFFFFF"))
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = c.text_frame
        tf.paragraphs[0].text = ""
        r = tf.paragraphs[0].add_run()
        r.text = val
        _font(r, H_FONT if i == 0 or j == 0 else B_FONT, 24 if i == 0 else 21, i == 0 or j == 0,
              "FFFFFF" if i == 0 else (RED if j == 2 else DARK))
footnote(s, "评估脚本与结果见仓库 experiments/ 与 reports/eval/；海外技能趋势受数据源构成影响，页面仅作参考。")

# ================================================================ 05 规划
section("05", "项目规划与预期成果", "Plan and expected results", SEC_A)

s = content_slide("研究进度与计划")
PLAN = [("2026.04 – 2026.06", "总体设计与数据治理", "已完成", "确定模块与技术路线；多源 JD、课程资源、技能标准库采集与清洗"),
        ("2026.07 – 2026.10", "模型开发与系统集成", "已完成", "岗位画像、匹配排序、先修图与路径规划、新闻与 Agent；网页 + 小程序上线"),
        ("2026.11 – 2027.01", "国内数据接入与系统优化", "进行中", f"已接入 {N_COMP} 家官网直采 + 国聘平台（{N_CN} 个岗位，国聘含月薪字段）；继续扩展公司覆盖"),
        ("2027.02 – 2027.03", "试点运行与评估", "计划", "校内计算机相关专业同学试用，收集行为日志，验证推荐与路径的可执行性；申报软件著作权"),
        ("2027.04 – 2027.05", "结项答辩与总结", "计划", "完成系统报告、操作手册与实验数据归档，提炼创新点")]
for i, (t_, h, st, b) in enumerate(PLAN):
    y = 1.8 + i * 1.7
    label(s, 0.9, y, 3.6, 0.7, t_, size=19, fill=RED if st != "计划" else DARK)
    text(s, 4.8, y - 0.02, 5.6, 0.7, [[(h, {"bold": True}), (f"　{st}", {"color": RED if st == "进行中" else "8A8F98", "size": 18})]], font=H_FONT, size=24)
    text(s, 4.8, y + 0.72, 14.4, 0.8, [b], size=19, color="3E3F43")

s = content_slide("预期成果")
OUTS = [("可用的双端产品", "网页端 + 微信小程序，覆盖市场看板、岗位洞察、匹配、学习路径、助手全流程"),
        ("国内 IT 岗位实时数据集", "大厂官网每日在招岗位与进出记录，持续积累国内岗位与技能需求的时间序列"),
        ("知识产权与论文", "申报软件著作权 1 项；整理国内外技能需求对比与可解释匹配方法，撰写论文或技术报告"),
        ("校内试点与推广", "面向本校同学试点，形成使用反馈与评估报告，具备扩展到就业指导中心的潜力")]
for i, (h, b) in enumerate(OUTS):
    col, row = i % 2, i // 2
    x, y = 0.9 + col * 9.25, 1.8 + row * 4.25
    box(s, x, y, 8.95, 3.95, fill=LIGHT)
    num(s, x + 0.3, y + 0.2, f"0{i + 1}", size=34)
    text(s, x + 1.55, y + 0.3, 7.2, 0.7, [h], font=H_FONT, size=28, bold=True)
    text(s, x + 0.35, y + 1.25, 8.3, 2.6, [b], size=20, spacing=1.45)

# ================================================================ 结束页
s = dup(END)
set_text(shapes_by_text(s, lambda x: x.startswith("JobNavigator-IT"))[0],
         ["JobNavigator-IT", "——国内IT求职者的实时职业导航平台"])

for sl in orig:
    drop(sl)
prs.save(OUT)
print("saved", OUT, len(prs.slides), "slides")
