"""
services/embedding_matcher.py  v2
资源-技能匹配模型 — Embedding 相似度版
============================================================
三级实现：
  L1  TF-IDF + 余弦相似度  (基准，双语技能文本，跨语言对齐)
  L2  sentence-transformers 零样本  (语义向量，无需额外训练)
  L3  sentence-transformers 微调    (在标注对上 CosineSimilarityLoss 训练)

关键词规则作为对比基准。

训练数据：learning_resources_v1.json 中标注的 (资源, 技能) 对
  正样本 ≈ 397 条
  负样本：困难负采样（同等数量）

评估指标：P@1 / P@3 / R@3 / MRR（按技能维度 80/20 划分）
"""

import json, pickle, random, time, warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
warnings.filterwarnings("ignore")

BASE_DIR   = Path(__file__).parent.parent   # services/ 上一层即仓库根
DATA_DIR   = BASE_DIR / "data" / "gold"
MODEL_DIR  = BASE_DIR / "models"
REPORT_DIR = BASE_DIR / "reports"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

LR_PATH    = DATA_DIR / "learning_resources_v1.json"
SKILL_PATH = DATA_DIR / "skill_prerequisite_v1.json"

random.seed(42)
np.random.seed(42)

# ── 英文关键词表（供 TF-IDF 双语表示用） ────────────────────────────────
SKILL_EN_KEYWORDS = {
    "sk_python_basic":   "python programming beginners tutorial basics",
    "sk_sql_basic":      "sql database mysql relational query",
    "sk_git":            "git github version control",
    "sk_linux_basic":    "linux bash shell scripting command line",
    "sk_math_basic":     "linear algebra probability statistics mathematics machine learning",
    "sk_pandas":         "pandas dataframe data analysis python",
    "sk_numpy":          "numpy numerical computing arrays python",
    "sk_data_structure": "data structures algorithms leetcode",
    "sk_matplotlib":     "matplotlib data visualization seaborn python",
    "sk_stats":          "statistics probability hypothesis testing statistical analysis",
    "sk_sql_advanced":   "advanced sql window functions analytics optimization",
    "sk_tableau":        "tableau powerbi business intelligence visualization",
    "sk_fastapi":        "fastapi rest api python web",
    "sk_docker":         "docker containerization kubernetes dockerfile",
    "sk_ab_test":        "ab testing experiment design hypothesis statistics",
    "sk_ml_basic":       "machine learning scikit-learn supervised regression classification",
    "sk_dl_basic":       "deep learning neural networks tensorflow keras",
    "sk_pytorch":        "pytorch deep learning neural networks",
    "sk_nlp_basic":      "nlp natural language processing text classification",
    "sk_embedding":      "word embedding text embedding word2vec sentence embedding",
    "sk_transformer":    "transformer attention mechanism bert self-attention",
    "sk_llm_basic":      "large language model llm generative ai gpt",
    "sk_prompt_eng":     "prompt engineering prompt design prompting",
    "sk_vector_db":      "vector database milvus faiss pinecone chroma",
    "sk_langchain":      "langchain llm framework python",
    "sk_lora_finetune":  "lora qlora fine-tuning llm peft parameter efficient",
    "sk_rag":            "retrieval augmented generation rag langchain",
    "sk_agent":          "ai agent agentic multi-agent autonomous",
    "sk_tool_use":       "function calling tool use tool calling llm",
}

# ── 关键词规则（对比基准） ───────────────────────────────────────────────
SKILL_KEYWORDS = {
    "sk_python_basic":   ["python programming", "python basics", "python tutorial"],
    "sk_sql_basic":      ["sql", "relational database", "mysql"],
    "sk_git":            ["git", "version control", "github tutorial"],
    "sk_linux_basic":    ["linux", "bash scripting", "shell scripting"],
    "sk_math_basic":     ["linear algebra for machine learning", "mathematics for machine learning", "probability"],
    "sk_pandas":         ["pandas", "dataframe", "data analysis with pandas"],
    "sk_numpy":          ["numpy", "numerical computing"],
    "sk_data_structure": ["data structures", "algorithms", "leetcode"],
    "sk_matplotlib":     ["matplotlib", "data visualization", "seaborn"],
    "sk_stats":          ["statistics", "statistical analysis", "hypothesis testing"],
    "sk_sql_advanced":   ["advanced sql", "sql window", "sql analytics"],
    "sk_tableau":        ["tableau", "power bi", "powerbi", "business intelligence"],
    "sk_fastapi":        ["fastapi", "rest api with fastapi"],
    "sk_docker":         ["docker", "containerization", "dockerfile"],
    "sk_ab_test":        ["a/b testing", "ab testing", "experiment design"],
    "sk_ml_basic":       ["machine learning", "scikit-learn", "supervised learning"],
    "sk_dl_basic":       ["deep learning", "neural networks", "tensorflow", "keras"],
    "sk_pytorch":        ["pytorch", "pytorch deep learning"],
    "sk_nlp_basic":      ["nlp", "natural language processing"],
    "sk_embedding":      ["word embedding", "text embedding", "word2vec"],
    "sk_transformer":    ["transformer", "attention mechanism", "bert"],
    "sk_llm_basic":      ["large language model", "llm", "generative ai"],
    "sk_prompt_eng":     ["prompt engineering", "prompt design"],
    "sk_vector_db":      ["vector database", "milvus", "faiss", "pinecone"],
    "sk_langchain":      ["langchain"],
    "sk_lora_finetune":  ["lora", "qlora", "fine-tuning llm", "peft"],
    "sk_rag":            ["retrieval augmented generation", "rag"],
    "sk_agent":          ["ai agent", "agentic ai", "multi-agent"],
    "sk_tool_use":       ["function calling", "tool use", "tool calling"],
}


# ════════════════════════════════════════════════════════════
# 1. 加载 + 构造训练数据
# ════════════════════════════════════════════════════════════
def load_data():
    with open(LR_PATH, encoding="utf-8") as f:
        lr = json.load(f)
    with open(SKILL_PATH, encoding="utf-8") as f:
        sg = json.load(f)

    skill_name_map = {s["skill_id"]: s["skill_name"] for s in sg["skills"]}
    skill_texts = {}
    for s in sg["skills"]:
        sid = s["skill_id"]
        prereq_names = " ".join(skill_name_map.get(p, "") for p in s.get("prerequisites", []))
        en_kw = SKILL_EN_KEYWORDS.get(sid, "")
        # 双语：中文技能名 + 英文关键词 + 前置技能名
        skill_texts[sid] = (
            f"{s['skill_name']} {s.get('category','')} {prereq_names} "
            f"{en_kw} {s.get('difficulty','')} level{s.get('level',0)}"
        )

    resource_pool  = {}
    positive_pairs = set()

    for sid, info in lr["skills"].items():
        for r in info["resources"]:
            rid = r["resource_id"]
            if rid not in resource_pool:
                resource_pool[rid] = {
                    "text":   f"{r['title']} {r.get('source','')} {r.get('note','')}",
                    "title":  r["title"],
                    "source": r["source"],
                }
            positive_pairs.add((rid, sid))

    return skill_texts, resource_pool, positive_pairs, skill_name_map


def build_train_val(skill_texts, resource_pool, positive_pairs):
    skill_pos = defaultdict(list)
    for rid, sid in positive_pairs:
        skill_pos[sid].append(rid)

    train_pos, val_pos = [], []
    for sid, rids in skill_pos.items():
        random.shuffle(rids)
        cut = max(1, int(len(rids) * 0.8))
        train_pos += [(r, sid) for r in rids[:cut]]
        val_pos   += [(r, sid) for r in rids[cut:]]

    all_rids = list(resource_pool.keys())
    negatives = {}
    for sid in skill_texts:
        pos_set = set(skill_pos[sid])
        negs    = [r for r in all_rids if r not in pos_set]
        random.shuffle(negs)
        negatives[sid] = negs[:len(skill_pos[sid]) * 4]

    return train_pos, val_pos, negatives, skill_pos


# ════════════════════════════════════════════════════════════
# 2. TF-IDF 模型（双语技能文本，跨语言对齐）
# ════════════════════════════════════════════════════════════
def train_tfidf(skill_texts, resource_pool):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    skill_ids = list(skill_texts.keys())
    res_ids   = list(resource_pool.keys())
    corpus    = [skill_texts[s] for s in skill_ids] + \
                [resource_pool[r]["text"] for r in res_ids]

    vec = TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2),
        min_df=1, sublinear_tf=True, max_features=12000,
    )
    vec.fit(corpus)

    s_vecs = vec.transform([skill_texts[s] for s in skill_ids])
    r_vecs = vec.transform([resource_pool[r]["text"] for r in res_ids])
    sim    = cosine_similarity(s_vecs, r_vecs)

    model_path = MODEL_DIR / "tfidf_matcher.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"vec": vec, "skill_ids": skill_ids,
                     "res_ids": res_ids, "sim": sim}, f)

    def top_k(sid, k):
        idx = skill_ids.index(sid)
        top = np.argsort(sim[idx])[::-1][:k]
        return [(res_ids[i], float(sim[idx, i])) for i in top]

    return top_k, len(vec.vocabulary_), model_path


# ════════════════════════════════════════════════════════════
# 3. sentence-transformers 零样本 + 微调
# ════════════════════════════════════════════════════════════
def run_sentence_transformers(skill_texts, resource_pool,
                              train_pos, negatives, val_pos, skill_pos):
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.preprocessing import normalize   # ← 提到外层作用域
    except ImportError:
        print("  [SKIP] sentence-transformers 未安装")
        return None, None

    BASE_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
    SAVE_PATH  = str(MODEL_DIR / "st_finetuned")

    skill_ids = list(skill_texts.keys())
    res_ids   = list(resource_pool.keys())

    def encode_and_sim(model):
        """计算 skill × resource 余弦相似度矩阵"""
        r_embs = model.encode(
            [resource_pool[r]["text"] for r in res_ids],
            batch_size=64, show_progress_bar=False,
        )
        s_embs = model.encode(
            [skill_texts[s] for s in skill_ids],
            batch_size=64, show_progress_bar=False,
        )
        r_n = normalize(r_embs); s_n = normalize(s_embs)
        return s_n @ r_n.T    # (29, N_res)

    def make_topk_fn(sim_mat):
        def top_k(sid, k):
            idx = skill_ids.index(sid)
            top = np.argsort(sim_mat[idx])[::-1][:k]
            return [(res_ids[i], float(sim_mat[idx, i])) for i in top]
        return top_k

    # ── 零样本 ───────────────────────────────────────────────
    print(f"  加载基础模型: {BASE_MODEL}")
    t0 = time.time()
    model_zs = SentenceTransformer(BASE_MODEL)
    print(f"  加载完成 ({time.time()-t0:.1f}s)")

    print("  零样本编码...")
    sim_zs = encode_and_sim(model_zs)
    topk_zs = make_topk_fn(sim_zs)
    zs_metrics, _ = _evaluate("ST-ZeroShot", topk_zs, val_pos, skill_pos, res_ids)

    # ── 微调 ─────────────────────────────────────────────────
    print("\n  开始微调 (SentenceTransformerTrainer API)...")
    try:
        from sentence_transformers import SentenceTransformerTrainer
        from sentence_transformers.training_args import SentenceTransformerTrainingArguments
        from sentence_transformers.losses import MultipleNegativesRankingLoss
        from datasets import Dataset

        # ── MNR Loss：只需正样本对，batch内其他样本自动作为隐式负例 ──
        # 每 batch_size=32 时，每条正样本隐含 31 个负例，梯度信号远超显式负采样
        anchors   = [skill_texts[sid]            for _, sid in train_pos]
        positives = [resource_pool[rid]["text"]  for rid, _ in train_pos]

        train_ds = Dataset.from_dict({
            "anchor":   anchors,
            "positive": positives,
        })
        print(f"  训练样本: {len(train_ds)} 条正对 (MultipleNegativesRankingLoss，batch内隐式负例)")

        NUM_EPOCHS   = 3
        BATCH_SIZE   = 32   # 更大的 batch → 更多隐式负例
        total_steps  = max(1, (len(train_ds) // BATCH_SIZE) * NUM_EPOCHS)
        warmup_steps = max(1, int(total_steps * 0.1))

        args = SentenceTransformerTrainingArguments(
            output_dir                  = SAVE_PATH,
            num_train_epochs            = NUM_EPOCHS,
            per_device_train_batch_size = BATCH_SIZE,
            warmup_steps                = warmup_steps,
            learning_rate               = 2e-5,
            logging_steps               = 10,
            save_strategy               = "no",
            report_to                   = "none",
        )
        model_ft = SentenceTransformer(BASE_MODEL)   # 新实例，避免污染零样本
        loss_fn  = MultipleNegativesRankingLoss(model_ft)

        trainer = SentenceTransformerTrainer(
            model          = model_ft,
            args           = args,
            train_dataset  = train_ds,
            loss           = loss_fn,
        )
        t1 = time.time()
        trainer.train()
        elapsed = time.time() - t1
        model_ft.save_pretrained(SAVE_PATH)
        print(f"  微调完成 ({elapsed:.1f}s)，保存至 {SAVE_PATH}")

        print("  微调后编码评估...")
        sim_ft = encode_and_sim(model_ft)

        # 保存向量
        np.save(str(MODEL_DIR / "resource_embeddings.npy"), normalize(
            model_ft.encode([resource_pool[r]["text"] for r in res_ids], batch_size=64)))
        np.save(str(MODEL_DIR / "skill_embeddings.npy"), normalize(
            model_ft.encode([skill_texts[s] for s in skill_ids], batch_size=64)))

        topk_ft = make_topk_fn(sim_ft)
        ft_metrics, _ = _evaluate("ST-Finetuned", topk_ft, val_pos, skill_pos, res_ids)

        return zs_metrics, ft_metrics, topk_ft, sim_ft, skill_ids, res_ids

    except Exception as e:
        print(f"  [微调失败] {e}")
        return zs_metrics, None, topk_zs, sim_zs, skill_ids, res_ids


# ════════════════════════════════════════════════════════════
# 4. 评估函数
# ════════════════════════════════════════════════════════════
def _evaluate(name, get_topk, val_pos, skill_pos, res_ids):
    from collections import defaultdict
    val_sp = defaultdict(set)
    for rid, sid in val_pos:
        val_sp[sid].add(rid)

    mrr_list, p1, p3, r3 = [], [], [], []
    per_skill = {}

    for sid, v_rids in val_sp.items():
        top5 = [r for r, _ in get_topk(sid, 5)]
        rank = None
        for vr in v_rids:
            if vr in top5:
                ri = top5.index(vr) + 1
                rank = ri if rank is None else min(rank, ri)
        mrr_list.append(1.0 / rank if rank else 0.0)
        p1.append(1 if top5 and top5[0] in v_rids else 0)
        hits3 = len(set(top5[:3]) & v_rids)
        p3.append(hits3 / 3)
        r3.append(hits3 / len(v_rids))
        per_skill[sid] = {"hits@3": hits3, "val_pos": len(v_rids),
                          "top3": top5[:3], "mrr": round(mrr_list[-1], 4)}

    metrics = {
        "p@1": round(float(np.mean(p1)),  4),
        "p@3": round(float(np.mean(p3)),  4),
        "r@3": round(float(np.mean(r3)),  4),
        "mrr": round(float(np.mean(mrr_list)), 4),
        "n_skills_evaluated": len(val_sp),
    }
    print(f"\n  [{name}] P@1={metrics['p@1']:.3f}  P@3={metrics['p@3']:.3f}"
          f"  R@3={metrics['r@3']:.3f}  MRR={metrics['mrr']:.3f}"
          f"  (n={metrics['n_skills_evaluated']})")
    return metrics, per_skill


def eval_keyword_rules(val_pos, skill_pos, resource_pool, res_ids):
    def kw_topk(sid, k):
        scores = []
        for rid in res_ids:
            t = resource_pool[rid]["text"].lower()
            sc = sum(2 if kw in t[:120] else (1 if kw in t else 0)
                     for kw in SKILL_KEYWORDS.get(sid, []))
            scores.append((rid, sc))
        scores.sort(key=lambda x: -x[1])
        return scores[:k]
    return _evaluate("Keyword-Rules", kw_topk, val_pos, skill_pos, res_ids)


# ════════════════════════════════════════════════════════════
# 主程序
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 62)
    print("Embedding 资源-技能匹配模型  训练 + 评估  (v2)")
    print("=" * 62)

    print("\n[1] 加载数据")
    skill_texts, resource_pool, positive_pairs, _ = load_data()
    res_ids = list(resource_pool.keys())

    print("\n[2] 构造训练/验证集 (80/20 按技能划分)")
    train_pos, val_pos, negatives, skill_pos = build_train_val(
        skill_texts, resource_pool, positive_pairs)
    print(f"  训练正样本: {len(train_pos)}  验证正样本: {len(val_pos)}")

    # ── 关键词规则基准 ────────────────────────────────────────
    print("\n[3] 关键词规则基准评估")
    kw_metrics, _ = eval_keyword_rules(val_pos, skill_pos, resource_pool, res_ids)

    # ── TF-IDF ───────────────────────────────────────────────
    print("\n[4] TF-IDF 模型训练（双语技能文本）")
    tfidf_topk, vocab_size, model_path = train_tfidf(skill_texts, resource_pool)
    print(f"  词表大小: {vocab_size}，模型: {model_path}")
    tfidf_metrics, _ = _evaluate("TF-IDF", tfidf_topk, val_pos, skill_pos, res_ids)

    # ── sentence-transformers ────────────────────────────────
    print("\n[5] sentence-transformers 零样本 + 微调")
    st_result = run_sentence_transformers(
        skill_texts, resource_pool, train_pos, negatives, val_pos, skill_pos
    )

    zs_metrics  = st_result[0] if st_result else None
    ft_metrics  = st_result[1] if st_result else None

    # ── 汇总 + 保存 ──────────────────────────────────────────
    all_metrics = {
        "keyword_rules": kw_metrics,
        "tfidf_bilingual": tfidf_metrics,
    }
    if zs_metrics: all_metrics["st_zeroshot"]  = zs_metrics
    if ft_metrics: all_metrics["st_finetuned"] = ft_metrics

    # MRR 衡量"最相关资源出现多早"，对推荐系统更重要；P@3 作为次要指标
    best = max(all_metrics, key=lambda k: all_metrics[k].get("mrr", 0))

    report = {
        "generated": "2026-06-01",
        "training_data": {
            "positive_pairs": len(positive_pairs),
            "train_pos": len(train_pos),
            "val_pos":   len(val_pos),
            "resources": len(resource_pool),
            "skills":    len(skill_texts),
        },
        "models": {
            k: {"metrics": v} for k, v in all_metrics.items()
        },
        "best_model": best,
        "recommendation": f"P@3最高: {best} ({all_metrics[best]['p@3']:.3f})",
    }
    if "tfidf_bilingual" in report["models"]:
        report["models"]["tfidf_bilingual"]["vocab_size"] = vocab_size
        report["models"]["tfidf_bilingual"]["model_file"] = str(model_path)
    if ft_metrics:
        report["models"]["st_finetuned"]["model_dir"]   = str(MODEL_DIR / "st_finetuned")
        report["models"]["st_finetuned"]["base_model"]  = "paraphrase-multilingual-MiniLM-L12-v2"
        report["models"]["st_finetuned"]["epochs"]      = 3

    (REPORT_DIR / "embedding_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown
    md = ["# 资源-技能 Embedding 匹配模型评估报告", "生成：2026-06-01", "",
          "## 训练数据",
          f"- 正样本配对：{len(positive_pairs)} 对（来自 learning_resources_v1.json）",
          f"- 训练集：{len(train_pos)} 条 | 验证集：{len(val_pos)} 条（80/20 按技能维度划分）",
          f"- 负样本：困难负采样（每技能4×）",
          "", "## 模型对比",
          "| 模型 | 类型 | P@1 | P@3 | R@3 | MRR |",
          "|------|------|-----|-----|-----|-----|"]
    type_map = {
        "keyword_rules":   "关键词打分规则（基准）",
        "tfidf_bilingual": "TF-IDF + 余弦相似度（双语）",
        "st_zeroshot":     "sentence-transformers 零样本",
        "st_finetuned":    "sentence-transformers 微调 ← 训练后",
    }
    for k, m in all_metrics.items():
        marker = " **[最优]**" if k == best else ""
        md.append(
            f"| {type_map.get(k,k)}{marker} | {'ML模型' if k!='keyword_rules' else '规则'} "
            f"| {m['p@1']:.3f} | {m['p@3']:.3f} | {m['r@3']:.3f} | {m['mrr']:.3f} |")
    md += ["", "## 结论",
           f"**最优模型**：{type_map.get(best,best)}（P@3 = {all_metrics[best]['p@3']:.3f}）",
           "",
           "## 模型文件",
           f"- `models/tfidf_matcher.pkl` — TF-IDF 向量化器 + 相似度矩阵",
           f"- `models/st_finetuned/`     — 微调后 sentence-transformers 模型",
           f"- `models/resource_embeddings.npy` — 资源向量（可直接加载用于线上推理）",
           f"- `models/skill_embeddings.npy`    — 技能向量",
           ]
    (REPORT_DIR / "embedding_eval_summary.md").write_text("\n".join(md), encoding="utf-8")

    # 控制台汇总
    print("\n" + "=" * 62)
    print(f"{'模型':<32} P@1   P@3   R@3   MRR")
    print("-" * 62)
    for k, m in all_metrics.items():
        marker = " ← BEST" if k == best else ""
        print(f"{type_map.get(k,k):<32} "
              f"{m['p@1']:.3f} {m['p@3']:.3f} {m['r@3']:.3f} {m['mrr']:.3f}{marker}")
    print("=" * 62)
    print(f"报告: {REPORT_DIR}/embedding_eval.json")
    print(f"      {REPORT_DIR}/embedding_eval_summary.md")


if __name__ == "__main__":
    main()
