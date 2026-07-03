# Module C Summary: 瀛︿範璺緞瑙勫垝妯″瀷

## 鏍稿績鐩爣

灏?B 妯″潡杈撳嚭鐨?*鎶€鑳界己鍙ｅ垪琛?*杞寲涓哄彲鎵ц鐨?*鏈夊簭瀛︿範璺緞 + 璧勬簮鎺ㄨ崘**锛?
浣滀负"宀椾綅鎺ㄨ崘 鈫?鑳藉姏琛ュ叏"鐨勮惤鍦颁腑闂村眰銆?

---

## 鍏抽敭浜や粯鐗?

| 浜や粯鐗?| 璺緞 | 璇存槑 |
|--------|------|------|
| 鎶€鑳藉厛淇浘璋?| `data/gold/skill_prerequisite_v1.json` | 29涓妧鑳借妭鐐癸紝38鏉℃湁鍚戣竟锛孌AG鏃犵幆楠岃瘉閫氳繃 |
| 瀛︿範璧勬簮搴?| `data/gold/learning_resources_v1.json` | 326鏉¤祫婧愶紙B绔?Coursera/GitHub涓夋簮锛夛紝29/29鎶€鑳藉叏瑕嗙洊 |
| 鎶€鑳借瘝琛?| `data/gold/skill_vocab.json` | 138鏉″埆鍚嶆槧灏勶紝渚?`skill_norm.py` 璋冪敤 |
| 璺緞瑙勫垝鏈嶅姟 | `services/path_planner_v1.py` | 涓夌瓥鐣ヨ矾寰勭敓鎴?+ DAG楠岃瘉 + Embedding璧勬簮鍖归厤 |
| Embedding璁粌 | `services/embedding_matcher.py` | TF-IDF + ST寰皟锛孧RR=0.457锛?58.7% vs 闆舵牱鏈級|
| 瀵规帴灞?| `app/services/path_planner.py` | 瀹炵幇鍥㈤槦缁熶竴鎺ュ彛锛岃皟鐢?`skill_norm.py` |
| 鍥捐氨娴佹按绾?| `pipelines/graph/build_skill_graph.py` | DAG楠岃瘉 + 璇嶈〃鏍￠獙 |
| 璺緞璇勪及鎶ュ憡 | `reports/eval/job_path_eval_v1.md` | 4妗堜緥 脳 3绛栫暐 = 12鏉″畬鏁磋矾寰勮鍒?|
| Embedding璇勪及 | `reports/eval/job_embedding_eval_summary.md` | P@1/P@3/R@3/MRR 鍥涙寚鏍囧姣?|
| 棰勮缁冨悜閲?| `models/resource_embeddings.npy` | 326鏉¤祫婧愬悜閲忥紙绾夸笂鎺ㄧ悊鐩存帴鍔犺浇锛墊
| TF-IDF妯″瀷 | `models/tfidf_matcher.pkl` | 鍙岃鎶€鑳芥枃鏈?+ 璇嶈〃2060鏉?|

---

## 璺緞鐢熸垚绠楁硶

### 涓夋潯鍊欓€夎矾寰勭瓥鐣?

| 绛栫暐 | 鍘熺悊 | 閫傜敤鍦烘櫙 |
|------|------|---------|
| `shortest` | 蹇€熼€氶亾锛岃烦杩囩悊璁哄熀纭€锛團AST_TRACK_SKIP锛夛紝鎸夊眰绾ф帓搴?| 鏈変竴瀹氳儗鏅€佽拷姹傞€熸垚 |
| `easy_first` | 璐績鏈€灏忓爢锛屽缁堜粠"鍙鎶€鑳?閲岄€夋渶绠€鍗曠殑 | 闆跺熀纭€锛屽惊搴忔笎杩?|
| `full_cover` | 瀹屾暣璺緞 + 鎵╁睍鎶€鑳斤紙ROLE_ENRICHMENT锛?| 杩芥眰绯荤粺鎬ф帉鎻?|

### 璺緞璇勫垎鍏紡

```
Score = Coverage 脳 (1 - 0.04 脳 max(0, steps - 5))
```

- Coverage锛氱洰鏍囨妧鑳借鐩栫巼锛堝惈鐢ㄦ埛宸叉湁鎶€鑳斤級
- 姝ラ鏁版儵缃氾細瓒呰繃5姝ユ瘡姝ユ墸4%锛屼笂闄?.5

### DAG 楠岃瘉

閲囩敤 DFS 涓夎壊鏍囪娉曪紙WHITE/GRAY/BLACK锛夛紝楠岃瘉缁撴灉锛?
- 29鑺傜偣锛?8杈癸紝**PASS锛堟棤鐜矾锛?*
- 鏍硅妭鐐癸細sk_python_basic / sk_sql_basic / sk_git / sk_linux_basic / sk_math_basic

---

## Embedding 璧勬簮鍖归厤妯″瀷

### 璁粌鏁版嵁

| 椤圭洰 | 鏁板€?|
|------|------|
| 姝ｆ牱鏈 | 397 瀵癸紙鏉ヨ嚜 learning_resources_v1.json 鎵嬪伐鏍囨敞锛墊
| 璁粌闆?| 304 鏉★紙80%锛屾寜鎶€鑳界淮搴﹀垝鍒嗭級|
| 楠岃瘉闆?| 93 鏉★紙20%锛墊
| 鍩虹妯″瀷 | `paraphrase-multilingual-MiniLM-L12-v2`锛堜腑鑻辨枃澶氳瑷€锛墊
| 鎹熷け鍑芥暟 | `MultipleNegativesRankingLoss`锛坆atch=32锛岄殣鍚?1涓礋渚?鏍锋湰锛墊
| 璁粌杞 | 3 epochs |

### 璇勪及鎸囨爣瀵规瘮

| 妯″瀷 | P@1 | P@3 | R@3 | MRR |
|------|-----|-----|-----|-----|
| 鍏抽敭璇嶈鍒欙紙鍩哄噯锛?| 0.138 | 0.241 | 0.432 | 0.382 |
| TF-IDF 鍙岃 | 0.276 | 0.195 | 0.323 | 0.401 |
| ST 闆舵牱鏈?| 0.103 | 0.172 | 0.289 | 0.288 |
| **ST 寰皟锛堟渶浼橈級** | **0.241** | **0.230** | **0.401** | **0.457** |

MRR 鐩告瘮闆舵牱鏈彁鍗?**+58.7%**锛岀浉姣斿叧閿瘝瑙勫垯鎻愬崌 **+19.6%**銆?

> 妯″瀷鏉冮噸锛坢odel.safetensors锛?49MB锛変綋绉繃澶ф湭鎻愪氦 Git銆?
> 澶嶇幇鏂瑰紡锛歚cd JobNavigator-IT && python services/embedding_matcher.py`锛堢害5鍒嗛挓锛?

---

## 鍏抽敭闆嗘垚鐐?

### 涓婃父锛圔 妯″潡锛?

```python
# B 杈撳嚭鐨?SkillGap.missing_skills 鐩存帴浣滀负 candidate_skills 浼犲叆 C
path = PathPlannerService.generate(
    profile          = profile,           # A妯″潡杈撳嚭
    target_job_id    = job.job_id,        # B妯″潡鎺ㄨ崘宀椾綅
    candidate_skills = skill_gap.missing_skills,  # B妯″潡鎶€鑳界己鍙?
)
```

- **鎶€鑳芥牸寮?*锛氱函瀛楃涓诧紙濡?`"LangChain"`, `"RAG"`锛夛紝鐢?`skill_norm.normalize_skill_id()` 褰掍竴鍖?
- **璇嶈〃缁熶竴**锛歚data/gold/skill_vocab.json` 鏄敮涓€鏁版嵁婧愶紝`skill_norm.py` 鍔犺浇璇ユ枃浠?

### 涓嬫父锛圖 妯″潡锛?

C 杩斿洖鐨?`LearningPath` 鍖呭惈锛?
- `steps[].skill`锛氭妧鑳藉悕绉?
- `steps[].resources`锛氬甫 URL 鐨勫涔犺祫婧愬垪琛?
- `score`锛氳矾寰勭患鍚堣瘎鍒嗭紙鍙綔涓?D 妯″潡瓒嬪娍铻嶅悎鐨勮緭鍏ワ級
- `total_estimated_hours`锛氭€诲鏃讹紙鍙敤浜庡涔犳垚鏈儵缃氶」锛?

---

## 宸茬煡闄愬埗

1. **鎶€鑳借瘝琛ㄨ鐩?*锛氱洰鍓嶈鐩?29 绫?IT 鎶€鑳斤紝138 鏉″埆鍚嶏紱鏂板叴鎶€鑳介渶鎵嬪姩鏇存柊 `skill_vocab.json`
2. **鐩爣宀椾綅鏄犲皠**锛氫粎鏀寔 4 绫荤矖绮掑害宀椾綅锛屼緷璧?`target_job_id` 鍏抽敭璇嶅尮閰嶏紱寰?B 妯″潡鎻愪緵绮剧‘鏄犲皠鎺ュ彛鍚庡崌绾?
3. **妯″瀷鏉冮噸**锛歚st_finetuned/model.safetensors` 鏈彁浜わ紙449MB锛夛紝杩愯鍓嶉渶鎵ц `python services/embedding_matcher.py` 璁粌鐢熸垚
4. **璧勬簮鏃舵晥鎬?*锛氬涔犺祫婧愰摼鎺ュ熀浜?2026骞村垵閲囬泦锛岄儴鍒?Coursera URL 涓烘悳绱㈤摼鎺ワ紝闇€瀹氭湡鏇存柊

---

## 杩愯鏂瑰紡

```bash
# 1. 璁粌 Embedding 妯″瀷锛堥娆¤繍琛屽繀椤伙級
python services/embedding_matcher.py

# 2. 鐢熸垚鍥捐氨楠岃瘉鎶ュ憡
python pipelines/graph/build_skill_graph.py

# 3. 鐢熸垚鍥涙渚嬪涔犺矾寰勮瘎浼版姤鍛?
python services/path_planner_v1.py

# 4. 杩愯鍗曞厓娴嬭瘯
pytest tests/unit/test_services.py::test_path_generation -v

# 5. 绔埌绔仈閫氭祴璇?
python test_e2e.py
```

