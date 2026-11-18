"""生成答辩 PPT 用的系统架构框架图（PNG，PPT 红灰主题）。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# 中文字体
font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(font_path)
plt.rcParams["font.family"] = "Noto Sans CJK JP"
plt.rcParams["axes.unicode_minus"] = False

RED, DARK, LIGHT, MID = "#EC3B3A", "#334251", "#F7F6F9", "#5C626C"
PINK = "#FDECEC"

fig, ax = plt.subplots(figsize=(19, 10.6), dpi=140)
ax.set_xlim(0, 19); ax.set_ylim(0, 10.6); ax.axis("off")
fig.patch.set_facecolor("white")

LAYERS = [
    ("应用层", RED, ["网页端（React + Vite）", "微信小程序（Taro）", "个人中心（云端存档）"]),
    ("服务层", DARK, ["FastAPI 30+ 接口", "市场看板 · 岗位洞察 · 匹配 · 路径", "趋势 · 公司雷达 · 新闻 · 助手"]),
    ("模型层", RED, ["Qwen3-Embedding 语义召回", "LightGBM 学习排序（LTR）", "分数校准 + 置信度", "先修 DAG + 路径规划", "Chronos-Bolt 时序预测"]),
    ("处理层", DARK, ["IT 岗过滤 → 技能抽取（LLM 审核词表）", "岗位归类 99 岗 → 岗位画像（近期加权）", "趋势面板（份额制）"]),
    ("数据层", RED, ["国内 6 家大厂官网（每日）", "全球 JD 12.99 万条（每月）", "13 源新闻（每 3 小时）", "WARN 裁员 · 公司在招 · HN 招聘"]),
]

y = 10.1
layer_h, gap = 1.72, 0.42
for i, (name, color, items) in enumerate(LAYERS):
    y0 = y - layer_h
    # 左侧层标签
    ax.add_patch(FancyBboxPatch((0.55, y0), 2.35, layer_h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=color, ec="none"))
    ax.text(1.72, y0 + layer_h / 2, name, ha="center", va="center", fontsize=23, color="white", weight="bold")
    # 右侧内容卡：每个 item 一个小框
    n = len(items)
    cw = (15.3 - (n - 1) * 0.28) / n
    for j, it in enumerate(items):
        x0 = 3.2 + j * (cw + 0.28)
        ax.add_patch(FancyBboxPatch((x0, y0 + 0.12), cw, layer_h - 0.24,
                                    boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc=PINK if color == RED else LIGHT, ec="#E2E3E6", lw=1))
        ax.text(x0 + cw / 2, y0 + layer_h / 2, items[j], ha="center", va="center",
                fontsize=15.5, color=DARK, linespacing=1.35, wrap=True)
    # 层间箭头
    if i < 4:
        ax.add_patch(FancyArrowPatch((1.72, y0 - 0.03), (1.72, y0 - gap + 0.03),
                                     arrowstyle="-|>", mutation_scale=26, color=RED, lw=2.5))
    y = y0 - gap

# 右侧双向标注
ax.text(18.35, 5.3, "", fontsize=1)
ax.annotate("", xy=(18.45, 9.9), xytext=(18.45, 0.7),
            arrowprops=dict(arrowstyle="-|>", mutation_scale=30, color=MID, lw=2))
ax.text(18.62, 5.3, "数据逐层加工上行", rotation=90, va="center", fontsize=15, color=MID)

plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
out = "/mnt/afs/JobNavigator-IT/ppt/assets/architecture.png"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
plt.savefig(out, dpi=140, facecolor="white")
print("saved", out)
