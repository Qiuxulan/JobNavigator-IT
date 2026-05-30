"""
Djinni 技能抽取 - 探路版(双模型结合:skill + knowledge)

用 jjzha 的两个配套模型抽取:
  - jobbert_knowledge_extraction: 抽硬技术/知识(Python/Docker 这类,与 asaniczka 对齐)
  - jobbert_skill_extraction:    抽能力短语(developing... 这类,作补充)
先在前 N 条真实 Djinni JD 上跑,看效果再谈全量。
运行:python -m pipelines.extract.extract_djinni_skills
"""

import re
import pandas as pd
from transformers import pipeline

DJINNI_CSV = "data/raw/djinni/djinni_jd.csv"
N_SAMPLE = 5          # 先看几条
SCORE_TH = 0.5        # 置信度阈值


def split_sentences(text):
    """简单分句:jjzha 对句子级输入效果最好,别整段喂"""
    text = re.sub(r"\s+", " ", str(text)).strip()
    # 按句号/换行/分号切
    sents = re.split(r"[.;\n!?]", text)
    return [s.strip() for s in sents if len(s.strip()) > 10]


def extract_spans(pipe, sentence, score_th=SCORE_TH):
    """对一句话抽 span,把连续的 B/I 拼成完整技能短语"""
    preds = pipe(sentence)
    spans, cur = [], []
    for tok in preds:
        label = tok["entity"]
        word = tok["word"]
        if label == "B":
            if cur:
                spans.append(_join(cur))
            cur = [(word, tok["score"])]
        elif label == "I" and cur:
            cur.append((word, tok["score"]))
        else:  # O
            if cur:
                spans.append(_join(cur))
                cur = []
    if cur:
        spans.append(_join(cur))
    # 过滤低置信度
    return [s for s, sc in spans if sc >= score_th]


def _join(tokens):
    """把 wordpiece(带##)拼回完整词,返回 (短语, 平均分)"""
    words = [w for w, _ in tokens]
    scores = [s for _, s in tokens]
    text = ""
    for w in words:
        if w.startswith("##"):
            text += w[2:]
        else:
            text += (" " + w) if text else w
    avg = sum(scores) / len(scores)
    return text.strip(), avg


def main():
    print(">>> 加载两个抽取模型 ...")
    skill_pipe = pipeline("token-classification", model="jjzha/jobbert_skill_extraction")
    know_pipe = pipeline("token-classification", model="jjzha/jobbert_knowledge_extraction")

    print(">>> 读取 Djinni 前几条 JD ...")
    df = pd.read_csv(DJINNI_CSV, nrows=50)  # 多读点,挑有正文的
    df = df.dropna(subset=["Long Description"])
    df = df[df["Long Description"].str.len() > 100].head(N_SAMPLE)

    for idx, row in df.iterrows():
        title = row["Position"]
        jd = row["Long Description"]
        sents = split_sentences(jd)

        knowledge, skills = set(), set()
        for s in sents:
            for k in extract_spans(know_pipe, s):
                knowledge.add(k)
            for sk in extract_spans(skill_pipe, s):
                skills.add(sk)

        print("\n" + "=" * 60)
        print(f"岗位: {title}")
        print(f"  [knowledge/技术] {sorted(knowledge)}")
        print(f"  [skill/能力]     {sorted(skills)}")


if __name__ == "__main__":
    main()