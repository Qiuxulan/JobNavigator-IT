# 妯″潡 B 鎬荤粨鏂囨。锛氱粏绮掑害宀椾綅搴?+ 鎺ㄨ崘妯″瀷

> 瀵瑰簲鍒嗗伐锛歚docs/01-product-roadmap/03-overall-team-assignment-3-weeks.md` 涓殑 **B锛氱粏绮掑害宀椾綅搴?+ 鎺ㄨ崘妯″瀷璐熻矗浜?*銆?
> 鏈枃妗ｈ鏄庢湰杞洿鏂颁簡鍝簺鏂囦欢銆佹瘡涓枃浠剁殑澶勭悊閫昏緫銆佷骇鍑虹墿銆佽繍琛屾柟寮忥紝浠ュ強鍏朵粬妯″潡锛圓/C/D锛夐渶瑕佹敞鎰忕殑浜嬮」銆?

## 1. 妯″潡鐩爣

鏋勫缓缁嗙矑搴﹀矖浣嶄綋绯诲苟瀹炵幇鍙岄樁娈垫帹鑽愶紙涓嶅仛瀛︿範璺緞鏈韩锛夛細

1. JD 鏍囬绮楃矑搴︽爣鍑嗗寲锛堟暟鎹?鍚庣/AI 搴旂敤绛夊ぇ绫伙級銆?
2. 缁嗙矑搴﹀矖浣嶆瀯寤猴紙JD 鍚戦噺鍖?鈫?鑱氱被 鈫?绨囧懡鍚嶏級銆?
3. 宀椾綅鎶€鑳界敾鍍忥紙姣忎釜宀椾綅楂橀鎶€鑳?TopN锛屽舰鎴?`job -> required_skills`锛夈€?
4. 鍙岄樁娈垫帹鑽愶細闃舵涓€鍚戦噺鍙洖 TopN锛岄樁娈典簩澶氱淮绮炬帓銆?
5. 鍙В閲婃帹鑽愮粨鏋滐細鍖归厤鍒嗘暟銆侀噸鍚堟妧鑳姐€佺己鍙ｆ妧鑳斤紙缁?C 鐢級銆佹帹鑽愮悊鐢便€?

## 2. 鏈疆鏇存柊/鏂板鐨勬枃浠?

### 淇敼
| 鏂囦欢 | 鏀瑰姩 |
|------|------|
| `app/schemas/domain.py` | `SkillGap` 鏂板瀛楁 `optional_skills`锛堝姞鍒嗘妧鑳斤細鍛戒腑鍙姞鍒嗐€佷笉璁＄己鍙ｏ紝浠呭睍绀?瑙ｉ噴锛夈€俽ecommender 宸插湪浜у嚭锛屾鍓?schema 缂哄瓧娈点€?|
| `app/services/recommender.py` | 閲嶅啓涓哄弻闃舵锛坧gvector ANN 鍙洖 + 澶氱淮绮炬帓锛夛紱閲嶄緷璧栨敼鍑芥暟鍐?import锛涗骇鍑?`overlap/missing/optional` 鎶€鑳戒笌鍙В閲婄悊鐢便€?|
| `infra/db/migrations/001_init.sql` | `job_roles.embedding` 缁村害 `VECTOR(384) 鈫?VECTOR(1024)`锛堝榻?JobBERT-v3 杈撳嚭锛涙棫 384 鏄?SBERT 缁村害锛屾槸 bug锛夈€?|
| `requirements.txt` / `environment.yml` | 琛?`pgvector`銆乣sentence-transformers`銆乣transformers`銆乣scikit-learn` 绛夋帹鑽愰摼渚濊禆銆?|
| `.github/workflows/ci.yml` | 澧炲姞 `pgvector/pgvector:pg16` 鐨?postgres service锛孋I 涓墽琛?`001_init.sql` 寤哄簱寤烘墿灞曪紝骞惰 `JOBNAV_POSTGRES_DSN`锛屼娇渚濊禆 pgvector 鐨勪唬鐮佽矾寰勫彲鍦?CI 杩炲簱銆?|

### 鏂板
| 鏂囦欢 | 浣滅敤 |
|------|------|
| `app/services/skill_norm.py` | 鍏ㄩ槦鍏叡鎶€鑳藉綊涓€鍖栧伐鍏凤紙璇嶈〃涓庝唬鐮佸垎绂伙級銆?|
| `pipelines/extract/extract_all_skills.py` | 涓夋簮缁熶竴鎶藉彇灞?鈫?缁熶竴 JSONL銆?|
| `pipelines/extract/match_djinni_skills.py` | Djinni 鍏ㄩ噺璇嶅吀鍖归厤鎶藉彇銆?|
| `pipelines/extract/extract_djinni_skills.py` | Djinni 妯″瀷鎶藉彇鎺㈣矾鐗堛€?|
| `pipelines/taxonomy/build_skill_vocab.py` | 瀹屾暣 IT 鏍囧噯鎶€鑳借瘝琛紙鍏ㄩ槦鍏辩敤锛宍skill_norm` 瀹為檯浣跨敤锛夈€?|
| `pipelines/taxonomy/build_skill_vocab_onet.py` | O*NET 杈呭姪/鍙傝€冭瘝琛紙褰撳墠涓嶈浠ｇ爜娑堣垂锛夈€?|
| `pipelines/taxonomy/cluster_roles.py` | 缁嗙矑搴﹀矖浣嶅垎灞傝仛绫汇€?|
| `pipelines/taxonomy/postprocess_roles.py` | 浜哄伐瀹″畾鍚堝苟/鏀瑰悕 鈫?鏈€缁堝矖浣嶅簱銆?|
| `pipelines/taxonomy/build_job_vectors.py` | 宀椾綅鍚戦噺鍖栧苟鍐欏叆 pgvector銆?|
| `pipelines/taxonomy/recall.py` | pgvector ANN 鍙洖銆?|
| `pipelines/taxonomy/rank.py` | 绮炬帓鍘熷瀷銆?|
| `pipelines/taxonomy/evaluate.py` | 璇勪及锛圚it@1/Hit@K/MRR/NDCG@K锛夈€?|
| `pipelines/taxonomy/diagnose_skills.py` | 鎶€鑳界粺涓€鎬ц瘖鏂€?|
| `pipelines/taxonomy/role_decisions.json` | 浜哄伐瀹″畾鍐崇瓥琛紙91鈫?0锛夈€?|
| `reports/summary/job_module_b_taxonomy_recommendation_summary.md` | 鏈枃妗ｃ€?|

鍚勬枃浠跺す鍙︽湁 README锛歚pipelines/taxonomy/README.md`銆乣pipelines/extract/README.md`銆乣app/services/README.md`銆?

## 3. 姣忎釜鏂囦欢鐨勮缁嗗鐞嗛€昏緫

### 鎶藉彇灞?`pipelines/extract`
- **extract_all_skills.py**锛氳 asaniczka / Djinni / emerging 涓夋簮 JD锛岀粺涓€杩?`skill_norm` 璇嶈〃鎶芥妧鑳斤紝杈撳嚭缁熶竴 JSONL锛涘悓鏃剁粺璁℃暟鎹簮瑙勬ā銆佹妧鑳借鐩栫巼銆佹柟鍚戞爣绛惧垎甯冦€侀珮棰戞湭鍖归厤鍊欓€夎瘝锛堢敤浜庢墿璇嶈〃锛夈€?
- **match_djinni_skills.py**锛氱敤 asaniczka 宸叉湁鎶€鑳藉悕鏋勫缓璇嶈〃锛屽湪 Djinni JD 姝ｆ枃鍋氳瘝鍏告壂鎻忓尮閰嶃€傝浜嗘渶灏忚瘝棰?鏈€灏忛暱搴?鍗曟潯涓婇檺涓変釜闃堝€煎幓闀垮熬鍣０銆?
- **extract_djinni_skills.py**锛氭帰璺増锛岀敤 jjzha 鐨?knowledge + skill 涓や釜妯″瀷鍦ㄦ牱鏈笂鎶藉彇銆佸彞瀛愮骇杈撳叆锛屽厛楠岃瘉鏁堟灉銆?

### 璇嶈〃 / 褰掍竴鍖?
- **build_skill_vocab.py**锛氭瀯寤哄叏闃熺粺涓€鏍囧噯璇嶈〃锛坕d/name/aliases/category/hot锛夆啋 `skill_vocab.json`锛屽惈 `alias_to_id`銆乣id_to_name`銆乣all_aliases`銆乣by_category`銆傝繖鏄?`skill_norm` 瀹為檯鍔犺浇鐨勮瘝琛ㄣ€?
- **build_skill_vocab_onet.py**锛歄*NET Technology Skills 鍏ㄩ儴鎶€鏈悕鍘婚噸 + 鏍?Hot 鈫?`skill_vocab_onet.json`銆傝緟鍔?鍙傝€冪敤锛屽綋鍓嶄笉琚换浣曚唬鐮佹秷璐广€?
- **app/services/skill_norm.py**锛氬熀浜?`skill_vocab.json` 鍋氬綊涓€鍖栵紙浠绘剰鍐欐硶鈫掓爣鍑嗗悕/id锛変笌鏂囨湰璇嶅吀鍖归厤锛堥暱鍒悕浼樺厛銆佽瘝杈圭晫姝ｅ垯銆佸垎鍧楃紪璇戯級銆?

### 宀椾綅搴?
- **cluster_roles.py**锛氳缁熶竴 JSONL锛屽仛鍚戦噺鍖?+ 鍒嗗眰 KMeans锛沞merging 鍗曠嫭鑱氱被閬垮厤琚?14 涓?Djinni 澶х被娣规病锛涜仛绫绘枃鏈敤 title + search_keyword + skills + JD 鎽樿锛涘懡鍚嶄紭鍏堢湅 search_keyword 涓庢妧鑳界敾鍍忋€備骇鍑哄師濮嬬皣宀椾綅搴?+ 鎶€鑳界敾鍍忋€?
- **postprocess_roles.py**锛氭寜 `role_decisions.json` 鎶?91 涓師濮嬬皣鍚堝苟/鏀瑰悕涓烘渶缁?70 涓嫭绔嬪矖浣嶏紱鑷姩澶囦唤鍘熸枃浠讹紱浜у嚭鏈€缁堝矖浣嶅簱銆侀厤濂楁妧鑳界敾鍍忋€?1鈫?0 鏄犲皠琛紙绛旇京鍙拷婧級銆?
- **diagnose_skills.py**锛氱粺璁℃妧鑳芥€绘暟/鍘婚噸鏁般€佺枒浼奸噸澶嶇粍銆乣(鏂瑰悜)` 娈嬬暀锛岃瘎浼板綊涓€鍖栨敹鐩娿€?

### 鍙洖 / 绮炬帓 / 璇勪及
- **build_job_vectors.py**锛氳鏈€缁堝矖浣嶅簱锛岀敤 JobBERT-v3 缂栫爜锛堟枃鏈嫾娉曡鈥滃叧閿害鏉熲€濓級锛孶PSERT 杩?postgres `job_roles`锛堝惈 1024 缁?embedding锛夈€?
- **recall.py**锛氱嚎涓婃妸 query 鍚戦噺涓?`job_roles.embedding` 鐢?`<=>` 浣欏鸡 ANN 鍙洖 TopN銆?
- **app/services/recommender.py**锛氬彫鍥?TopN 鈫?绮炬帓 `Final = ALPHA路璇箟 + BETA路绾︽潫 鈭?GAMMA路缂哄彛 + DELTA路瓒嬪娍`锛涚己鍙ｅ彧閽堝鏍稿績鎶€鑳斤紙`core_skills`锛屾棤鍒欓€€鍥?`required_skills`锛夛紝`optional_skills` 浠呭睍绀猴紱杈撳嚭鍙В閲婄悊鐢变笌 `SkillGap`銆?
- **rank.py**锛氱簿鎺掗€昏緫鐨勭嫭绔嬪師鍨?瀵圭収瀹炵幇銆?
- **evaluate.py**锛氱敤 `eval_set_v1.json`锛堟寜宀椾綅鍚嶆爣 ground truth锛岃繍琛屾椂瑙ｆ瀽鎴?role_id锛岄噸缂栧彿涓嶅け鏁堬級绠?Hit@1/Hit@K/MRR/NDCG@K銆?

## 4. 浜у嚭鐗?

| 浜у嚭 | 鐢熸垚鑰?|
|------|--------|
| `data/silver/all_jd_skills_v1.jsonl`锛? stats锛?| extract_all_skills.py |
| `data/gold/djinni_skill_match_v1.json` | match_djinni_skills.py |
| `data/gold/skill_vocab_onet.json` | build_skill_vocab.py |
| `data/gold/skill_vocab.json` | Build skill vocab.py |
| `data/gold/fine_grained_roles_v1.json`锛堜氦浠樼墿鈶狅級 | cluster_roles.py 鈫?postprocess_roles.py |
| `data/gold/job_skill_profile_v1.json`锛堜氦浠樼墿鈶★級 | postprocess_roles.py |
| `data/gold/role_name_mapping_v1.json` | postprocess_roles.py |
| postgres `job_roles` 琛紙鍚?embedding锛?| build_job_vectors.py |
| 鎺ㄨ崘缁撴灉锛坄RecommendationItem` 鍒楄〃锛屽惈 `SkillGap`锛?| recommender.py锛堜氦浠樼墿鈶㈠搴?`app/services`锛?|
| `reports/eval/job_recommend_eval_v1.md`锛堜氦浠樼墿鈶ｏ級 | evaluate.py + 浜哄伐鏁寸悊 |

## 5. 鎬庝箞杩愯

### 渚濊禆涓庢暟鎹簱
```bash
pip install -r requirements.txt          # 鎴?conda env create -f environment.yml
# 璧峰甫 pgvector 鐨?postgres锛堟湰鍦扮敤 docker compose 鎴?pgvector/pgvector 闀滃儚锛?
psql "$JOBNAV_POSTGRES_DSN" -f infra/db/migrations/001_init.sql
export JOBNAV_POSTGRES_DSN=postgresql://jobnav:jobnav@localhost:5432/jobnavigator
```

### 绂荤嚎鍏ㄩ摼璺紙鎸夐『搴忥級
```bash
python -m pipelines.taxonomy.build_skill_vocab        # 鍏ㄩ槦鏍囧噯璇嶈〃(skill_norm 浣跨敤)
python -m pipelines.taxonomy.build_skill_vocab_onet    # O*NET 杈呭姪璇嶈〃(鍙€?涓嶈浠ｇ爜娑堣垂)
python -m pipelines.extract.extract_all_skills         # 缁熶竴鎶藉彇
python -m pipelines.taxonomy.cluster_roles             # 鑱氱被 鈫?鍘熷绨?
python -m pipelines.taxonomy.postprocess_roles         # 鍚堝苟 鈫?鏈€缁堝矖浣嶅簱
python -m pipelines.taxonomy.build_job_vectors         # 鍐?pgvector
python -m pipelines.taxonomy.recall                    # 鍙洖鍐掔儫
python -m pipelines.taxonomy.evaluate                  # 璇勪及
```

### 绾夸笂璋冪敤
閫氳繃 `app/api/routes.py` 鈫?`RecommenderService.recommend(profile, preference, top_k)`锛屽墠鎻愭槸宸茶窇杩?`build_job_vectors.py` 涓?postgres 鍦ㄧ嚎銆?

## 6. 鍏朵粬妯″潡闇€瑕佹敞鎰?

- **A锛堟娊鍙?鐢诲儚锛?*锛氭帹鑽愯緭鍏ユ槸 `UserProfile`锛坄skills` 鐢ㄦ爣鍑嗘妧鑳藉悕锛夈€傛妧鑳藉綊涓€鍖栬缁熶竴鐢?`app/services/skill_norm.py`锛岃瘝琛ㄦ洿鏂板彧鏀?`data/gold/skill_vocab.json`锛屽嬁鍚勮嚜閫犺瘝琛ㄣ€?
- **C锛堝涔犺矾寰勶級**锛氱己鍙ｆ妧鑳戒粠鎺ㄨ崘缁撴灉 `RecommendationItem.skill_gap.missing_skills` 鍙栵紱鏂板鐨?`optional_skills` 鏄姞鍒嗘妧鑳斤紝涓嶅睘浜庡繀瀛︾己鍙ｃ€俙path_cost_score` 鐩墠鏄己鍙ｆ儵缃氱殑鍗犱綅锛屽緟 C 鐨?`path_planner` 鎺ュ叆鍚庢浛鎹紙recommender 閲?TODO-1锛夈€?
- **D锛堣秼鍔匡級**锛歚trend_reward_score` 鐜扮敤鍏抽敭璇嶅崰浣嶈〃锛圱ODO-3锛夛紝鎺ュ叆鐪熷疄鐑害鍚庢浛鎹紱宀椾綅搴?`city/salary/degree` 瀛楁琛ラ綈鍚庯紝recommender 鐨?`constraint_score`锛堢幇鍥哄畾 0.8锛孴ODO-2锛夋墠鑳界湡绠椼€?
- **鍏ㄥ憳锛圖B / 鍚戦噺涓€鑷存€э級**锛歚job_roles.embedding` 蹇呴』鏄?1024 缁达紙JobBERT-v3锛夈€俼uery 涓庡矖浣嶅悜閲忕殑妯″瀷銆佹枃鏈嫾娉曘€乣normalize_embeddings=True` 蹇呴』瀹屽叏涓€鑷达紝鍚﹀垯 ANN 鍙洖閿欎綅銆傛敼浠讳竴澶勯渶鍚屾 `build_job_vectors.py` / `recall.py` / `recommender._load_engine`銆?
- **鏁版嵁瑙勬ā**锛氬矖浣嶅簱鍩轰簬鍏ㄩ噺绾?17 涓囨潯 JD锛坅saniczka 1.2 涓?+ Djinni 14.2 涓?+ emerging 1.7 涓囷紝Djinni 鎶€鑳藉凡鍏ㄩ噺鎶藉彇锛岃 `data/silver/all_jd_skills_stats_v1.json`锛夈€傝仛绫婚樁娈典负鎺у埗 KMeans 瑙勬ā鎸夌矖绮掑害妗跺垎灞傛娊鏍凤紙浼犵粺绫绘瘡妗?5000銆乪merging 20000锛夛紝鎶€鑳界敾鍍忓熀浜庡叏閲忕粺璁°€?
- **CI**锛歚ci.yml` 宸叉寕 pgvector postgres service 骞舵墽琛岃縼绉伙紱渚濊禆 DB 鐨勬祴璇曢渶璇?`JOBNAV_POSTGRES_DSN`銆傛秹鍙婃ā鍨嬩笅杞?鍏ㄩ噺鍚戦噺鐨勭鍒扮鐢ㄤ緥涓嶅湪 CI 鍐掔儫瑕嗙洊鑼冨洿鍐呫€?

