# C 妯″潡 README锛歊AG 璇佹嵁妫€绱€丆oT 瑙ｉ噴涓婁笅鏂囦笌浜嬩欢鍥捐氨

> 璐熻矗浜猴細缁勫憳 2锛堣涓氳秼鍔胯В閲?/ RAG 璇佹嵁閾撅級銆?
> 鏈枃妗ｉ潰鍚戠瓟杈┿€佷氦浠樺拰闃熷弸鎺ュ叆锛岃缁嗚鏄庢湰妯″潡鍋氫簡浠€涔堛€佺敤浜嗗摢浜涙暟鎹€佸啓浜嗗摢浜涙枃浠躲€佸疄鐜伴€昏緫鏄粈涔堛€佹湁鍝簺绾︽潫銆佸浣曡皟鐢ㄦ帴鍙ｃ€佸浣曚娇鐢?CoT 鍜屽浘璋便€?

---

## 1. 妯″潡鐩爣

鏈ā鍧楄В鍐崇殑闂鏄細**瓒嬪娍棰勬祴缁欏嚭鈥滄煇宀椾綅鏈潵涓婂崌/涓嬮檷/鎸佸钩鈥濆悗锛岀郴缁熷浣曠粰鍑哄彲杩芥函銆佸彲瑙ｉ噴銆佸彲灞曠ず鐨勮瘉鎹摼**銆?

涓婃父 B 妯″潡锛圥atchTST锛夎礋璐ｉ娴嬫柟鍚戝拰闇€姹傛寚鏁般€傛湰妯″潡涓嶉噸鏂拌缁冮娴嬫ā鍨嬶紝鑰屾槸鍦ㄩ娴嬬粨鏋滀笂澧炲姞涓夌被鑳藉姏锛?

1. **RAG 璇佹嵁妫€绱?*
   - 浠?GDELT 鏂伴椈浜嬩欢绱㈠紩鍜?JD 宀椾綅鏁版嵁涓紝涓烘煇涓矖浣嶃€佹煇涓椂闂寸獥鍙ｆ绱㈣瘉鎹€?
   - 杈撳嚭鑱氬悎淇″彿銆佷唬琛ㄦ€т簨浠躲€丣D 瀛樺湪鎬ц瘉鎹€?

2. **CoT 瑙ｉ噴涓婁笅鏂?*
   - 灏嗛娴嬬粨鏋溿€佽仛鍚堜俊鍙枫€乀opK 浜嬩欢銆侀噸澶ц涓氫簨浠躲€丣D 璇佹嵁缁勮涓哄甫寮曠敤缂栧彿鐨勬帹鐞嗕笂涓嬫枃銆?
   - 鏈ā鍧楀彧鐢熸垚 grounded prompt/context锛屼笉鐩存帴璋冪敤 LLM銆?
   - 缁勫憳 3 鐨?Agent 鎴栧墠绔彲鎶婅 prompt 浜ょ粰 LLM 鍋氣€滃垎姝ラ瑙ｉ噴鈥濄€?

3. **浜嬩欢鍏ュ浘涓庡彲瑙嗗寲**
   - 灏嗕唬琛ㄦ€т簨浠朵綔涓?`event` 鑺傜偣鎺ュ叆鑱屼笟鍥捐氨銆?
   - 鐢?`AFFECTS(event -> job)` 杈硅〃绀轰簨浠朵笌宀椾綅瓒嬪娍涔嬮棿鐨勫叧绯汇€?
   - 杈撳嚭鍙弻鍑绘墦寮€鐨?HTML 鍥捐氨銆?

---

## 2. 鎬讳綋鏁版嵁娴?

```text
鍘熷鏁版嵁
  鈹溾攢 data/raw/gdelt_gkg_role_documents/gdelt_gkg_role_documents.jsonl
  鈹?   GDELT 宀椾綅绾т簨浠跺€欓€夛紝绾?2.6GB
  鈹溾攢 data/raw/processed_jd_jobs.json
  鈹?   鏍囧噯鍖?JD锛岀害 170MB
  鈹溾攢 data/gold/patchtst_prediction_milestones.json
  鈹?   PatchTST 閲岀▼纰戦娴嬶紝69 瑙掕壊 脳 5 涓閲?= 345 鏉?
  鈹溾攢 data/gold/patchtst_predictions_36m.json
  鈹?   PatchTST 閫愭湀棰勬祴锛?9 瑙掕壊 脳 36 鏈?= 2484 鏉?
  鈹溾攢 data/gold/role_taxonomy.json
  鈹?   role_id / canonical_role / category / aliases / top_skills
  鈹斺攢 data/gold/major_industry_events_v1.json
       浜哄伐鏁寸悊鐨勯噸澶ц涓氫簨浠剁洰褰曪紝101 鏉?

        鈹?
        鈻?

鈶?绂荤嚎绱㈠紩
  pipelines/trend/build_evidence_index.py
  -> data/processed/evidence_index/events/<role>/<month>.jsonl
  -> data/processed/evidence_index/jobs/<role>.jsonl
  -> data/processed/evidence_index/manifest.json

        鈹?
        鈻?

鈶?鍦ㄧ嚎/鎵归噺 RAG 妫€绱㈡牳蹇?
  app/services/evidence.py
  EvidenceService.retrieve_evidence(role, months, top_k, direction)
  -> aggregate + events + jobs + note

        鈹?
        鈹溾攢 GET /v1/evidence/{job_role}
        鈹溾攢 GET /v1/trends/{job_role}  鑷姩甯?evidence
        鈹溾攢 pipelines/trend/build_trend_evidence.py
        鈹?   -> data/gold/trend_evidence_v1.jsonl
        鈹?   -> data/gold/trend_evidence_monthly_v1.jsonl
        鈹?   -> reports/eval/industry_trend_explanation_eval_v1.md
        鈹溾攢 app/services/trend_explanation.py
        鈹?   -> CoT 涓婁笅鏂?/ grounded prompt
        鈹斺攢 pipelines/graph/build_event_graph.py
             -> data/processed/event_graph_v1.json
             -> reports/full_unified_graph.html
```

---

## 3. 杈撳叆鏁版嵁

### 3.1 GDELT 浜嬩欢鍊欓€?

鏂囦欢锛?

```text
data/raw/gdelt_gkg_role_documents/gdelt_gkg_role_documents.jsonl
```

鐗圭偣锛?

- 浣撻噺绾?2.6GB銆?
- 鍏ㄩ噺绱㈠紩鍚庡叡鏈?**1,726,284 鏉′簨浠跺€欓€?*銆?
- 瑕嗙洊 **67 涓湁浜嬩欢鍊欓€夌殑瑙掕壊**銆?
- 褰撳墠鐪熷疄鏂伴椈绐楀彛涓?**2026-01 鍒?2026-06**銆?
- 鍘熷 GDELT 鏁版嵁娌℃湁瀹屾暣姝ｆ枃锛屽洜姝ゆ绱㈠繀椤讳緷璧?URL slug銆乻ource_domain銆乼hemes銆乼one銆乵atched_terms 绛夊瓧娈点€?

绱㈠紩淇濈暀瀛楁锛?

```text
canonical_role
month
url
source_domain
themes
bucket_name
match_weight
matched_terms
matched_term_count
avg_tone
event_date
```

鍏朵腑 `tone` 鏄?GDELT 鐨勯€楀彿鍒嗛殧瀛楁锛屼唬鐮佷腑鍙栫涓€涓€间綔涓虹患鍚堟儏缁細

```python
parse_first_tone(tone)
```

### 3.2 JD 宀椾綅鏁版嵁

鏂囦欢锛?

```text
data/raw/processed_jd_jobs.json
```

绱㈠紩鍚庡叡鏈?**70,826 鏉?JD**锛岃鐩?**62 涓鑹?*銆?

绱㈠紩淇濈暀瀛楁锛?

```text
canonical_role
role_id
month
post_date
company_name
raw_job_title
salary_mid
job_url
role_match_score
```

娉ㄦ剰锛?

- `job_url` 鍦ㄥ綋鍓嶆簮鏁版嵁涓ぇ澶氫负绌恒€?
- 鍥犳 JD 璇佹嵁涓嶄綔涓哄彲鐐瑰嚮鏂伴椈璇佹嵁锛岃€屾槸浣滀负鈥滃矖浣嶅瓨鍦ㄦ€ц瘉鎹€濄€?
- 杈撳嚭涓細淇濈暀鍏徃鍚嶃€佸矖浣嶆爣棰樸€佸彂甯冩椂闂淬€佽柂璧勪腑浣嶆暟銆?

### 3.3 PatchTST 棰勬祴缁撴灉

榛樿浼樺厛璇诲彇锛?

```text
data/gold/patchtst_prediction_milestones.json
```

瑙勬ā锛?

- 69 涓鑹层€?
- 姣忎釜瑙掕壊 5 涓噷绋嬬瑙嗛噹銆?
- 鍏?**345 鏉¤秼鍔跨粨璁?*銆?

閫愭湀鐗堟湰锛?

```text
data/gold/patchtst_predictions_36m.json
```

瑙勬ā锛?

- 69 涓鑹层€?
- 姣忎釜瑙掕壊鏈潵 36 涓湀銆?
- 鍏?**2484 鏉￠€愭湀棰勬祴**銆?

閫傞厤鍣細

```text
pipelines/trend/_trend_source.py
```

鍏抽敭閫昏緫锛?

- 浼樺厛璇?PatchTST銆?
- 缂哄け鏃跺洖閫€鍒?`data/gold/role_trend_scores.json`銆?
- 鐢变簬 PatchTST 棰勬祴鏈潵鏈堜唤锛岃€屾湭鏉ユ病鏈夋柊闂伙紝鎵€浠ヨ瘉鎹粺涓€浠庢渶杩戠湡瀹炰簨浠剁獥鍙ｅ彇锛?

```python
EVENT_WINDOW = ("2026-01", "2026-06")
```

### 3.4 閲嶅ぇ琛屼笟浜嬩欢鐩綍

鏂囦欢锛?

```text
data/gold/major_industry_events_v1.json
```

瑙勬ā锛?

- `event_catalog` 鍏?**101 鏉￠噸澶ц涓氫簨浠?*銆?

鐢ㄩ€旓細

- 寮ヨˉ GDELT 鏃犳鏂囥€佷綆璐ㄩ噺鏂伴椈杈冨鐨勯棶棰樸€?
- 鎻愪緵鍏紑鏉ユ簮銆侀珮鍙俊鐨勮涓氳儗鏅簨浠躲€?
- 鍦ㄦ壒閲忚瘉鎹€丆oT 涓婁笅鏂囧拰浜嬩欢鍥捐氨涓兘鍙互浣跨敤銆?

---

## 4. 杈撳嚭鏁版嵁

### 4.0 妯″潡绾ф暟鎹暀瀛樻€昏

| 闃舵 | 杈撳叆瑙勬ā | 澶勭悊閫昏緫 | 杈撳嚭瑙勬ā |
|---|---:|---|---:|
| 鍘熷 GDELT 浜嬩欢 | 绾?2.6GB | 閫愯娴佸紡璇诲彇锛屾寜宀椾綅/鏈堝垎鐗?| 1,726,284 鏉′簨浠跺€欓€?|
| 鍘熷 JD | 绾?170MB | 瀛楁鐦﹁韩锛屾寜宀椾綅鍒嗙墖 | 70,826 鏉?JD |
| Evidence Index | 1,726,284 浜嬩欢 + 70,826 JD | 鍙繚鐣欐绱㈠繀瑕佸瓧娈?| events 瑕嗙洊 67 瑙掕壊锛宩obs 瑕嗙洊 62 瑙掕壊 |
| PatchTST 閲岀▼纰?| 69 瑙掕壊 脳 5 瑙嗛噹 | 缁熶竴瓒嬪娍缁撹鏍煎紡 | 345 鏉¤秼鍔跨粨璁?|
| 鎵归噺 RAG 璇佹嵁 | 345 鏉¤秼鍔跨粨璁?| 姣忔潯璋冪敤 EvidenceService锛孴opK=5 | 345 琛?trend_evidence锛屽叾涓?335 琛屾湁浜嬩欢 |
| 閫愭湀 RAG 璇佹嵁 | 69 瑙掕壊 脳 36 鏈?| 澶嶇敤鍚屼竴妫€绱㈡牳蹇冿紝鎸夋湀杈撳嚭 | 2484 琛?trend_evidence_monthly |
| 浜嬩欢鍏ュ浘鍊欓€?| 69 鏉℃渶杩戣閲庤秼鍔?| 姣忓矖浣?RAG Top3 + 閲嶅ぇ浜嬩欢 Top5 | 380 鏉″€欓€夎竟 |
| 鏈€缁堜簨浠跺浘璋?| 380 鏉″€欓€夎竟 | RAG 杈规寜 P60 + 0.35 鍦版澘杩囨护锛岄噸澶т簨浠朵繚鐣?| 321 鏉¤竟锛?08 涓簨浠惰妭鐐?|
| HTML 鍙鍖?| event_graph_v1.json + career graph | Canvas / vis-network 娓叉煋 | 绾簨浠跺浘 + 鍏ㄩ噺铻嶅悎鍥?+ 鍗曞矖浣嶅浘 |

### 4.1 璇佹嵁绱㈠紩

鐢熸垚鑴氭湰锛?

```bash
python pipelines/trend/build_evidence_index.py
```

杈撳嚭锛?

```text
data/processed/evidence_index/
  events/<role>/<month>.jsonl
  jobs/<role>.jsonl
  manifest.json
```

褰撳墠绱㈠紩缁熻锛?

```text
events: 1,726,284 鏉?
jobs:   70,826 鏉?
浜嬩欢绐楀彛: 2026-01~2026-06
```

### 4.2 瓒嬪娍璇佹嵁鏂囦欢

鐢熸垚鑴氭湰锛?

```bash
python -m pipelines.trend.build_trend_evidence
```

杈撳嚭锛?

```text
data/gold/trend_evidence_v1.jsonl
reports/eval/industry_trend_explanation_eval_v1.md
```

褰撳墠 `trend_evidence_v1.jsonl` 鏈?**345 琛?*锛屾瘡琛屽搴斾竴涓秼鍔跨粨璁恒€?

褰撳墠 345 鏉¤秼鍔胯瘉鎹殑瑕嗙洊鎯呭喌锛?

```text
鏈?aggregate 鑱氬悎淇″彿: 335 / 345
鏈変簨浠惰瘉鎹?TopK:      335 / 345
鏈?JD 璇佹嵁:           310 / 345
鏃犱簨浠惰瘉鎹?            10 / 345
鏃?JD 璇佹嵁:             35 / 345
```

姣忔潯瓒嬪娍缁撹鐨勪簨浠惰瘉鎹暟閲忓垎甯冿細

```text
0 鏉′簨浠惰瘉鎹?  10 鏉¤秼鍔跨粨璁?
1 鏉′簨浠惰瘉鎹?  30 鏉¤秼鍔跨粨璁?
2 鏉′簨浠惰瘉鎹?  30 鏉¤秼鍔跨粨璁?
3 鏉′簨浠惰瘉鎹?  20 鏉¤秼鍔跨粨璁?
4 鏉′簨浠惰瘉鎹?  30 鏉¤秼鍔跨粨璁?
5 鏉′簨浠惰瘉鎹? 225 鏉¤秼鍔跨粨璁?
```

涔熷氨鏄锛岀粷澶у鏁拌秼鍔跨粨璁哄彲浠ユ嬁鍒版弧棰?TopK=5 鐨勪簨浠惰瘉鎹紱灏戞暟瑙掕壊鍥犱负鍊欓€夎緝灏戞垨绾︽潫杩囨护杈冧弗锛屽彧淇濈暀 1~4 鏉°€?

姣忔潯瓒嬪娍缁撹鐨?JD 璇佹嵁鏁伴噺鍒嗗竷锛?

```text
0 鏉?JD 璇佹嵁:  35 鏉¤秼鍔跨粨璁?
1 鏉?JD 璇佹嵁:   5 鏉¤秼鍔跨粨璁?
2 鏉?JD 璇佹嵁:   5 鏉¤秼鍔跨粨璁?
3 鏉?JD 璇佹嵁:   5 鏉¤秼鍔跨粨璁?
5 鏉?JD 璇佹嵁: 295 鏉¤秼鍔跨粨璁?
```

浜嬩欢璇佹嵁寮哄急鍒嗗竷锛?

```text
strong: 915 鏉?
weak:   480 鏉?
```

璇存槑锛?

- `strong` 琛ㄧず閫氳繃宀椾綅鐩稿叧鎬х瓑鏇翠弗鏍肩害鏉熺殑浜嬩欢鏍锋湰銆?
- `weak` 琛ㄧず寮虹浉鍏虫牱鏈笉瓒虫椂锛岀敤鏍囬璐ㄩ噺杈冨ソ鐨勮ˉ鍏呬簨浠跺厹搴曘€?
- weak 涓嶇瓑浜庝笉鑳界敤锛屼絾鍦ㄨВ閲婃椂瑕侀厤鍚?`risk_notes`锛屼笉瑕佹妸瀹冨綋浣滃己鍥犳灉璇佹嵁銆?

鎵归噺璇佹嵁涓殑浜嬩欢绫诲瀷鍒嗗竷锛?

```text
market_report:          604
security_incident:      357
research_breakthrough:  228
policy:                 102
funding:                 85
layoff:                  19
```

瓒嬪娍鏂瑰悜鍒嗗竷锛?

```text
stable: 143
down:   125
up:      77
```

閫愭湀鐗堟湰锛?

```bash
python -m pipelines.trend.build_trend_evidence --monthly
```

杈撳嚭锛?

```text
data/gold/trend_evidence_monthly_v1.jsonl
```

褰撳墠閫愭湀鏂囦欢鏈?**2484 琛?*銆?

### 4.3 浜嬩欢鍥捐氨鏂囦欢

鐢熸垚鑴氭湰锛?

```bash
python -m pipelines.graph.build_event_graph
```

杈撳嚭锛?

```text
data/processed/event_graph_v1.json
```

褰撳墠鍥捐氨缁熻锛?

```text
candidate_edges: 380
threshold: 0.7065
pctl: 60
weight_floor: 0.35
kept_edges: 321
kept_rag_edges: 41
kept_major_edges: 280
kept_event_nodes: 108
distinct_jobs_affected: 69
```

瑙ｉ噴锛?

- 鍊欓€夎竟 380 鏉°€?
- 浣跨敤 P60 鍒嗕綅鏁板拰缁濆鍦版澘杩囨护鍚庯紝淇濈暀 321 鏉¤竟銆?
- 鍏朵腑 RAG 妫€绱簨浠惰竟 41 鏉°€?
- 閲嶅ぇ琛屼笟浜嬩欢杈?280 鏉°€?
- 鍏?108 涓簨浠惰妭鐐广€?
- 瑕嗙洊 69 涓矖浣嶃€?

### 4.3.1 涓轰粈涔堝浘璋遍噷鍙湁杩欎箞澶氫簨浠?

鍥捐氨涓嶆槸鎶婃墍鏈?RAG 璇佹嵁閮界敾鍑烘潵銆傚師鍥犳湁涓変釜锛?

1. 鍏ㄩ噺 GDELT 鍊欓€夋湁 172 涓囨潯锛屽櫔闊冲緢楂橈紝濡傛灉鍏ㄦ寕鍒板浘涓婏紝鍥捐氨浼氫笉鍙銆?
2. `trend_evidence_v1.jsonl` 鏄粰鎶ュ憡/鎺ュ彛鐢ㄧ殑锛屾瘡鏉¤秼鍔挎渶澶?TopK=5锛涘浘璋辨槸缁欒倝鐪肩湅鐨勶紝鎵€浠ユ洿涓ユ牸銆?
3. 鍥捐氨鍙彇姣忎釜宀椾綅鏈€杩戣閲庣殑涓€鏉¤秼鍔跨粨璁猴紝鑰屼笉鏄妸 3/6/12/24/36 涓湀鍏ㄩ儴鐢昏繘鍥撅紝鍚﹀垯鍚屼竴宀椾綅浼氶噸澶嶆寕寰堝杈广€?

浜嬩欢鍏ュ浘鐨勬暟鎹紡鏂楁槸锛?

```text
鍘熷 GDELT 浜嬩欢鍊欓€?
  1,726,284 鏉?
        鈹?
        鈻?
鎸夎鑹?+ 鏈堜唤寤虹珛 evidence_index
  events: 1,726,284 鏉?/ 67 涓湁浜嬩欢鍊欓€夌殑瑙掕壊
  jobs:      70,826 鏉?/ 62 涓湁 JD 鐨勮鑹?
        鈹?
        鈻?
PatchTST 閲岀▼纰戣秼鍔跨粨璁?
  345 鏉?= 69 涓鑹?脳 5 涓娴嬭閲?
        鈹?
        鈻?
鎵归噺 RAG 璇佹嵁鏂囦欢
  trend_evidence_v1.jsonl: 345 琛?
  鍏朵腑 335 琛屾湁 aggregate锛?35 琛屾湁浜嬩欢璇佹嵁
        鈹?
        鈻?
浜嬩欢鍏ュ浘鍙彇姣忎釜宀椾綅鏈€杩戦娴嬭閲?
  69 鏉″矖浣嶈秼鍔跨粨璁?
        鈹?
        鈻?
姣忎釜宀椾綅鏈€澶氬彇 TOPK_GRAPH=3 鏉?RAG 浜嬩欢
  鍚屾椂鎸傞噸澶ц涓氫簨浠讹紝鏈€澶?5 鏉?宀椾綅鏂瑰悜
        鈹?
        鈻?
鍥捐氨鍊欓€夎竟 raw_edges
  380 鏉?
  鈹溾攢 RAG 鍊欓€夎竟绾?100 鏉?
  鈹斺攢 閲嶅ぇ琛屼笟浜嬩欢鍊欓€夎竟 280 鏉?
        鈹?
        鈻?
闃堝€艰繃婊?
  RAG 杈规寜 retrieval_score 鍙?P60 闃堝€硷紝涓旇姹?>= 0.35
  褰撳墠闃堝€?= 0.7065
        鈹?
        鈻?
鏈€缁?event_graph_v1.json
  321 鏉?AFFECTS 杈?
  鈹溾攢 RAG 杈?41 鏉?
  鈹斺攢 閲嶅ぇ琛屼笟浜嬩欢杈?280 鏉?
  108 涓?event 鑺傜偣
  瑕嗙洊 69 涓矖浣?
```

鎵€浠ュ浘璋遍噷鍙湁 108 涓簨浠惰妭鐐广€?21 鏉¤竟锛屾槸鍒绘剰绛涢€夊悗鐨勭粨鏋滐紝涓嶆槸鏁版嵁涓嶈冻銆?

### 4.3.2 鈥?7 鏉′笅闄嶈竟鈥濅笉鏄瓫閫夎捣鐐?

鍥捐氨缁熻閲屾湁涓€涓鏄撹瑙ｇ殑鏁板瓧锛?

```text
graph_edges_by_trend:
  neutral: 301
  negative: 17
  positive: 3
```

杩欓噷鐨?**17 鏉?negative** 鎸囩殑鏄渶缁堝浘璋辫竟閲岋紝`trend_impact_direction=negative` 鐨勮竟锛屼篃灏辨槸鈥滈娴嬫柟鍚戞槑纭笅闄嶁€濈殑杈规暟銆?

瀹冧笉鏄師濮嬫暟鎹噺锛屼篃涓嶆槸鈥滀粠 17 鏉￠噷绛涘嚭鍥捐氨浜嬩欢鈥濄€傜湡瀹炵瓫閫夎捣鐐规槸锛?

```text
1,726,284 鏉?GDELT 鍊欓€変簨浠?
-> 345 鏉¤秼鍔跨粨璁虹殑 RAG 璇佹嵁
-> 380 鏉″浘璋卞€欓€夎竟
-> 321 鏉℃渶缁堝浘璋辫竟
```

17 鏉″彧鏄湪鏈€缁堝浘璋遍噷鎸夐娴嬫柟鍚戠粺璁″嚭鏉ョ殑涓嬮檷杈广€?

### 4.3.3 姣忎釜宀椾綅鍥捐氨閲屼細鏈夊灏戣瘉鎹竟

鏈€缁堝浘璋辫鐩?69 涓矖浣嶏紝姣忎釜宀椾綅淇濈暀鐨?`AFFECTS` 杈规暟閲忓垎甯冨涓嬶細

```text
姣忓矖浣?3 鏉¤竟:  9 涓矖浣?
姣忓矖浣?4 鏉¤竟: 31 涓矖浣?
姣忓矖浣?5 鏉¤竟: 13 涓矖浣?
姣忓矖浣?6 鏉¤竟:  9 涓矖浣?
姣忓矖浣?7 鏉¤竟:  5 涓矖浣?
姣忓矖浣?8 鏉¤竟:  2 涓矖浣?
```

涓轰粈涔堜笉鏄瘡涓矖浣嶉兘涓€鏍凤紵

- RAG 閮ㄥ垎姣忎釜宀椾綅鏈€澶氬彇 3 鏉″€欓€変簨浠躲€?
- 浣嗕弗鏍艰繃婊ゅ悗锛屾湁鐨勫矖浣?RAG 浜嬩欢灏戜簬 3 鏉°€?
- 閲嶅ぇ琛屼笟浜嬩欢鏈€澶氭寕 5 鏉★紝浣嗗彇鍐充簬璇ュ矖浣嶅拰瓒嬪娍鏂瑰悜鏄惁鍦?`major_industry_events_v1.json` 涓湁鏄犲皠銆?
- 鍚屼竴涓噸澶т簨浠跺彲杩炴帴澶氫釜宀椾綅锛屽洜姝?event 鑺傜偣鏁板皯浜庤竟鏁般€?

鍥犳锛屽崟宀椾綅鍥捐氨閲岄€氬父浼氱湅鍒?**3 鍒?8 鏉′簨浠惰瘉鎹竟**銆?

### 4.3.4 鍥捐氨杈规寜鏉ユ簮鍒嗙被

鏈€缁?321 鏉¤竟鎸夋潵婧愬垎锛?

```text
public_major_event: 280
rag_event:           41
```

瑙ｉ噴锛?

- `rag_event` 鏄粠 GDELT 浜嬩欢妫€绱㈤噷绛涘嚭鐨勫矖浣嶇浉鍏充簨浠躲€?
- `public_major_event` 鏄汉宸ユ暣鐞嗙殑鍏紑鏉ユ簮閲嶅ぇ琛屼笟浜嬩欢锛屾洿閫傚悎鍥捐氨灞曠ず鍜岀瓟杈╄В閲娿€?
- 鍥捐氨閲岄噸澶ц涓氫簨浠惰竟澶氾紝鏄洜涓哄畠浠彲瑙ｉ噴鎬ф洿寮恒€佹潵婧愭洿绋筹紝涓斾細琚鐢ㄥ埌澶氫釜宀椾綅銆?

### 4.3.5 鍥捐氨杈规寜浜嬩欢绫诲瀷鍒嗙被

鏈€缁堝浘璋辫竟鐨勪富瑕佷簨浠剁被鍨嬶細

```text
ai_coding_agent:              61
model_release:                48
market_report:                15
ai_infrastructure:            14
language_release:             13
research_breakthrough:        13
enterprise_ai_platform:       11
game_engine_release:          10
security_incident:            10
regulation:                    8
security_standard:             7
frontend_framework_release:    7
testing_tool_release:          6
mobile_platform_release:       5
outage:                        5
ml_framework_release:          5
runtime_release:               5
market_research:               5
quality_risk:                  4
funding:                       4
```

杩欒鏄庡浘璋遍噷鐨勪簨浠朵富瑕佸垎涓哄洓绫伙細

1. AI/妯″瀷/Agent 骞冲彴绫讳簨浠躲€?
2. 缂栫▼璇█銆佹鏋躲€佽繍琛屾椂銆佸伐鍏峰彂甯冪被浜嬩欢銆?
3. 瀹夊叏銆佺洃绠°€侀闄╃被浜嬩欢銆?
4. 甯傚満鐮旂┒鍜岃涓氭姤鍛婄被浜嬩欢銆?

### 4.4 鍥捐氨 HTML

绾簨浠跺浘锛?

```bash
python -m pipelines.graph.build_event_graph_view
```

杈撳嚭锛?

```text
reports/event_graph_view.html
```

铻嶅悎鍥撅細

```bash
python -m pipelines.graph.build_unified_graph_view --full --top-n 12
```

杈撳嚭锛?

```text
reports/full_unified_graph.html
```

鍗曞矖浣嶅浘锛?

```bash
python -m pipelines.graph.build_unified_graph_view --role "RAG Engineer" --top-n 12
```

杈撳嚭绀轰緥锛?

```text
reports/role_011_unified_graph.html
```

---

## 5. 鏂囦欢娓呭崟涓庤亴璐?

### 5.1 RAG 妫€绱㈡牳蹇?

鏂囦欢锛?

```text
app/services/evidence.py
```

鑱岃矗锛?

- 瀹炵幇 `EvidenceService.retrieve_evidence()`銆?
- 浠?evidence_index 涓鍙栧矖浣?+ 鏈堜唤鍛戒腑鐨勫皬鍒嗙墖銆?
- 鍋氱浉鍏虫€ц繃婊ゃ€丅M25 鎺掑簭銆佹柟鍚戝綊鍥犳帓搴忋€佽仛鍚堢粺璁°€丣D 娣峰叆銆?
- 鏄繍琛屾椂鎺ュ彛銆佹壒閲忚瘉鎹€丆oT銆佸浘璋卞叆鍥惧叡鐢ㄧ殑鍞竴妫€绱㈡牳蹇冦€?

瀵瑰涓诲嚱鏁帮細

```python
EvidenceService.retrieve_evidence(
    role: str,
    months: tuple[str, str],
    top_k: int = 5,
    direction: str | None = None,
) -> dict
```

杩斿洖缁撴瀯锛?

```json
{
  "role": "RAG Engineer",
  "months": ["2026-01", "2026-06"],
  "direction": "flat",
  "aggregate": {},
  "events": [],
  "jobs": [],
  "candidates_total": 259,
  "candidates_kept": 5,
  "note": "..."
}
```

### 5.2 绂荤嚎绱㈠紩

鏂囦欢锛?

```text
pipelines/trend/build_evidence_index.py
```

鑱岃矗锛?

- 鎶?2.6GB GDELT jsonl 鍜?170MB JD 鏁版嵁杞垚杞婚噺鍒嗙墖銆?
- 绾爣鍑嗗簱瀹炵幇锛屼笉渚濊禆 DuckDB/ES/鍚戦噺鏁版嵁搴撱€?
- 鏌ヨ鏃跺彧璇诲懡涓矖浣嶅拰鏈堜唤鐨勫皬鏂囦欢锛岄伩鍏嶆瘡娆℃壂鎻忓叏閲忋€?

璁捐閫夋嫨锛?

- 娌℃湁浣跨敤 Elasticsearch锛屽洜涓烘煡璇㈡槸缁撴瀯鍖栬繃婊?+ 鎺掑簭锛屼笉鏄紑鏀惧叏鏂囨悳绱€?
- 娌℃湁浣跨敤鍚戦噺搴擄紝鍥犱负 GDELT 缂烘鏂囷紝涓?172 涓囨潯鍏ㄩ噺 embedding 鎴愭湰杩囬珮銆?
- 閲囩敤鏂囦欢鍒嗗尯鏂规锛氱畝鍗曘€佺ǔ瀹氥€佷究浜庢瘮璧涚幆澧冨鐜般€?

### 5.3 瓒嬪娍缁撹閫傞厤鍣?

鏂囦欢锛?

```text
pipelines/trend/_trend_source.py
```

鑱岃矗锛?

- 缁熶竴璇诲彇 PatchTST 鎴栧熀绾胯秼鍔跨粨璁恒€?
- 灞忚斀涓婃父鏂囦欢宸紓銆?
- 璁?`build_trend_evidence.py` 鍜?`build_event_graph.py` 涓嶄緷璧栧叿浣撴ā鍨嬭緭鍑烘牸寮忋€?

### 5.4 鎵归噺璇佹嵁鐢熸垚

鏂囦欢锛?

```text
pipelines/trend/build_trend_evidence.py
```

鑱岃矗锛?

- 瀵?345 鏉?PatchTST 閲岀▼纰戣秼鍔跨粨璁烘壒閲忚皟鐢?`EvidenceService`銆?
- 杈撳嚭 `trend_evidence_v1.jsonl`銆?
- 杈撳嚭璇勪及鎶ュ憡 `reports/eval/industry_trend_explanation_eval_v1.md`銆?
- 鏀寔 `--monthly` 鐢熸垚 2484 琛岄€愭湀鐗堟湰銆?

### 5.5 CoT 涓婁笅鏂?

鏂囦欢锛?

```text
app/services/trend_explanation.py
```

鑱岃矗锛?

- 缁勮 CoT 浣跨敤鐨?grounded context銆?
- 涓嶇洿鎺ヨ皟鐢?LLM銆?
- 鍙礋璐ｆ妸浜嬪疄缁勭粐鎴愬彲寮曠敤銆佸彲绾︽潫鐨?prompt銆?

鏍稿績鍑芥暟锛?

```python
assemble_cot_context(role: str, horizon: int = 3) -> dict
build_cot_prompt(ctx: dict) -> str
```

### 5.6 TrendService 鎺ュ叆

鏂囦欢锛?

```text
app/services/trend.py
```

鑱岃矗锛?

- `TrendService.get_signal()` 浼樺厛璋冪敤 PatchTST銆?
- 鑻?PatchTST 涓嶅彲鐢紝鍥為€€鍒板熀绾?`role_trend_scores.json`銆?
- 鑷姩璋冪敤 EvidenceService锛屽皢 evidence 濉叆瓒嬪娍鎺ュ彛杩斿洖銆?

### 5.7 API 璺敱

鏂囦欢锛?

```text
app/api/routes.py
```

鏂板/鐩稿叧鎺ュ彛锛?

```text
GET /v1/trends/{job_role}
GET /v1/evidence/{job_role}
```

### 5.8 浜嬩欢鍏ュ浘

鏂囦欢锛?

```text
pipelines/graph/build_event_graph.py
```

鑱岃矗锛?

- 澶嶇敤 EvidenceService 鐨勯€夋嫨缁撴灉銆?
- 灏嗕簨浠跺啓鎴?`event` 鑺傜偣銆?
- 灏嗕簨浠跺拰宀椾綅涔嬮棿鍐欐垚 `AFFECTS` 杈广€?
- 杈撳嚭 `data/processed/event_graph_v1.json`銆?
- 鍙€?`--write-db` 鍐欏叆 Postgres 鍥捐氨琛ㄣ€?

### 5.9 鍥捐氨鍙鍖?

鏂囦欢锛?

```text
pipelines/graph/build_event_graph_view.py
pipelines/graph/build_unified_graph_view.py
pipelines/graph/export_graph_interactive_v2.py
app/services/evidence_color.py
```

鑱岃矗锛?

- `build_event_graph_view.py`锛氱敓鎴愮函浜嬩欢 鈫?宀椾綅鍥俱€?
- `build_unified_graph_view.py`锛氳瀺鍚堝矖浣?鎶€鑳藉浘璋卞拰浜嬩欢璇佹嵁鍥俱€?
- `export_graph_interactive_v2.py`锛欳anvas 浜や簰寮忔覆鏌撳櫒銆?
- `evidence_color.py`锛氱粺涓€浜嬩欢杈归鑹查€昏緫锛岄伩鍏嶄笉鍚屽浘閲岄鑹茶鍒欎笉涓€鑷淬€?

---

## 6. RAG 妫€绱㈤€昏緫

### 6.1 涓嶆槸鏅€氭枃鏈?RAG

鏈ā鍧椾笉鏄€滄妸鏂囨。濉炶繘鍚戦噺搴撶劧鍚庣浉浼煎害妫€绱⑩€濈殑 RAG銆?

鍘熷洜锛?

- GDELT 鏁版嵁娌℃湁鍙潬姝ｆ枃銆?
- 澶ч噺鍊欓€夋潵鑷?URL slug銆佷富棰樸€佸叧閿瘝銆?
- 鐩存帴 embedding 浼氭妸鍣煶涓€璧峰悜閲忓寲锛屼笖 172 涓囨潯鎴愭湰杈冮珮銆?

鍥犳鏈ā鍧楅噰鐢細

```text
缁撴瀯鍖栧垎鐗囪繃婊?+ 瑙勫垯绾︽潫 + BM25 涓婚鐩稿叧 + 瓒嬪娍鏂瑰悜褰掑洜鎺掑簭 + 鑱氬悎缁熻鍏滃簳
```

### 6.2 妫€绱㈡祦绋?

缁欏畾锛?

```text
role = "RAG Engineer"
months = ("2026-01", "2026-06")
top_k = 5
direction = "flat"
```

娴佺▼锛?

1. 瀹氫綅鍒嗙墖鐩綍锛?

```text
data/processed/evidence_index/events/RAG_Engineer/*.jsonl
```

2. 鎸夋湀浠借鍙栧€欓€変簨浠躲€?

3. 璁＄畻 aggregate 鑱氬悎淇″彿銆?

4. 閫氳繃鐩稿叧鎬ч椄闂ㄨ繃婊ゅ櫔闊炽€?

5. 鏋勯€?BM25 query锛?
   - 瑙掕壊鍚?
   - role aliases
   - top_skills

6. 瀵瑰€欓€変簨浠惰绠楀鍚堝垎銆?

7. 鍘婚噸銆?

8. 鎸夋柟鍚戝亸濂介€夋嫨 TopK銆?

9. 娣峰叆 JD 瀛樺湪鎬ц瘉鎹€?

10. 杩斿洖璇佹嵁閾俱€?

### 6.2.1 鍗曞矖浣嶈瘉鎹摼渚嬪瓙锛歊AG Engineer

浠?`RAG Engineer`銆佺獥鍙?`2026-01~2026-06`銆佹柟鍚?`flat` 涓轰緥锛?

```text
杈撳叆瑙掕壊: RAG Engineer
杈撳叆绐楀彛: 2026-01 ~ 2026-06
杈撳叆鏂瑰悜: flat

鍘熷鍊欓€変簨浠?candidates_total: 259
閫氳繃鐩稿叧鎬ч椄闂?candidates_kept: 40
鏈€缁堣繑鍥炰簨浠?TopK: 5
鏈€缁堣繑鍥?JD: 0
```

璇ュ矖浣嶇殑 TopK 浜嬩欢鏍蜂緥缁熻锛?

```text
security_incident / negative / weak / score=0.3695 / title_quality=0.6 / role_affinity=0.0
market_report      / positive / weak / score=0.5886 / title_quality=1.0 / role_affinity=0.0
market_report      / positive / weak / score=0.5543 / title_quality=1.0 / role_affinity=0.0
market_report      / neutral  / weak / score=0.3473 / title_quality=0.6 / role_affinity=0.0
research_breakthrough / positive / weak / score=0.3043 / title_quality=0.7 / role_affinity=0.0
```

瑙ｉ噴锛?

- `259 -> 40` 鏄?RAG 鐩稿叧鎬ч椄闂ㄧ瓫閫夌粨鏋溿€?
- `40 -> 5` 鏄帓搴忓悗鍙?TopK銆?
- 杩?5 鏉¤櫧鐒跺彲浣滀负琛ュ厖鏍锋湰锛屼絾 `role_affinity=0.0`锛屾墍浠ユ爣娉ㄤ负 `weak`銆?
- 鍥犳绯荤粺 note 浼氭彁绀猴細`寮虹浉鍏充簨浠朵笉瓒筹紝琛ュ厖 5 鏉″急鐩稿叧浜嬩欢锛涜秼鍔夸綈璇佷互 aggregate/JD 涓哄噯`銆?
- 杩欎篃鏄垜浠负浠€涔堣璁♀€滀袱灞傝瘉鎹€濈殑鍘熷洜锛氬崟鏉′簨浠朵笉寮烘椂锛岀敤 aggregate 鑱氬悎淇″彿浣滀负涓诲姏銆?

### 6.3 鑱氬悎淇″彿 aggregate

鑱氬悎淇″彿鏄湰妯″潡鐨勪富鍔涜瘉鎹紝鍥犱负鍗曟潯 GDELT 浜嬩欢鍣煶杈冨銆?

杈撳嚭瀛楁锛?

```json
{
  "article_count": 259,
  "mean_tone": -0.43,
  "positive_ratio": 0.421,
  "opportunity_events": 38,
  "risk_events": 102,
  "net_signal": "negative",
  "top_themes": [],
  "top_domains": []
}
```

鍚箟锛?

- `article_count`锛氬€欓€夌浉鍏虫柊闂绘暟銆?
- `mean_tone`锛氬钩鍧囨儏缁€?
- `positive_ratio`锛歵one > 0 鐨勬瘮渚嬨€?
- `opportunity_events`锛氱粡娴?灏变笟璇涓?tone > 0 鐨勪簨浠舵暟銆?
- `risk_events`锛氱粡娴?灏变笟璇涓?tone < 0 鐨勪簨浠舵暟銆?
- `net_signal`锛氭満浼氬浜庨闄╀负 positive锛岄闄╁浜庢満浼氫负 negative锛屽惁鍒?mixed銆?

### 6.4 鍗曟潯浜嬩欢璇佹嵁

杈撳嚭瀛楁锛?

```json
{
  "evidence_type": "news_event",
  "url": "...",
  "source_domain": "...",
  "title": "...",
  "published_at": "2026-03-20",
  "tone": -4.479,
  "themes": [],
  "match_weight": 0.2,
  "event_type": "security_incident",
  "impact_direction": "negative",
  "is_counter_signal": false,
  "direction_align": 0.83,
  "title_quality": 0.7,
  "role_affinity": 0.6,
  "evidence_strength": "weak",
  "retrieval_score": 0.46
}
```

### 6.5 JD 璇佹嵁

杈撳嚭瀛楁锛?

```json
{
  "evidence_type": "job_posting",
  "company_name": "...",
  "title": "...",
  "post_date": "2025-04-30",
  "salary_mid": 130809,
  "job_url": null,
  "role_match_score": 0.91,
  "out_of_range": true
}
```

`out_of_range=true` 琛ㄧず褰撳墠鏂伴椈绐楀彛鍐呮病鏈?JD锛屽洖閫€鍒拌瑙掕壊鍏ㄩ儴 JD 浣滀负瀛樺湪鎬ц瘉鎹€?

---

## 7. RAG 绾︽潫璁捐

鐢变簬 GDELT 娌℃湁姝ｆ枃锛屼笖 URL/涓婚/鍏抽敭璇嶅櫔闊冲緢寮猴紝鏈ā鍧楀姞鍏ヤ簡澶氬眰绾︽潫銆?

### 7.1 绾︽潫鎬昏

褰撳墠鑷冲皯鍖呭惈浠ヤ笅绾︽潫锛?

1. 鎶€鑳借瘝鐧藉悕鍗曠害鏉熴€?
2. URL/鍚庣紑浼瘝杩囨护銆?
3. 姝т箟鎶€鑳借瘝绾︽潫銆?
4. 绉戞妧涓婚绾︽潫銆?
5. 缁忔祹/鍔冲姩鍔涗富棰樺叡鐜扮害鏉熴€?
6. 鍨冨溇鍩熷悕榛戝悕鍗曘€?
7. 寮卞彲淇″煙鍚嶉檷鏉冦€?
8. 鍧忔爣棰樼煭璇繃婊ゃ€?
9. 鍧忔爣棰樿瘝杩囨护銆?
10. 宀椾綅涓婁笅鏂囪瘝绾︽潫銆?
11. 寮虹鎶€涓婚绾︽潫銆?
12. 瑙掕壊閿氳瘝鎵╁睍銆?
13. 瑙掕壊蹇呴渶璇嶇害鏉熴€?
14. 鏍囬璐ㄩ噺鍒嗐€?
15. 宀椾綅鐩稿叧鎬у垎銆?
16. URL 鍘婚噸銆?
17. 鏍囬杩戦噸澶嶅幓閲嶃€?
18. 瓒嬪娍鏂瑰悜瀵归綈銆?
19. 鍙嶅悜淇″彿淇濈暀銆?
20. 鍥捐氨鍏ュ浘闃堝€肩害鏉熴€?
21. 鍥捐氨棰滆壊灞傛嫑鑱樺櫔闊崇害鏉熴€?

### 7.2 鎶€鑳借瘝鐧藉悕鍗?

鏂囦欢锛?

```text
data/gold/skill_vocab.json
```

浠ｇ爜锛?

```python
_load_skill_vocab()
_SKILL_VOCAB
```

浣滅敤锛?

- 鍙湁鍛戒腑鎶€鑳借瘝琛ㄧ殑鏈鎵嶆洿鍙兘琚涓烘槸鎶€鏈浉鍏炽€?
- 閬垮厤鎶婃櫘閫氳嫳鏂囪瘝璇垽涓烘妧鑳姐€?

### 7.3 URL/鍚庣紑浼瘝杩囨护

浠ｇ爜甯搁噺锛?

```python
ARTIFACT_TERMS = {
    "html", "htm", "php", "aspx", ".net", "www", "amp", "com", "org", "co", "io"
}
```

浣滅敤锛?

- URL 閲屽父瑙佸悗缂€鍜屽煙鍚嶇墖娈典笉鑳藉綋浣滄妧鏈瘉鎹€?
- 渚嬪 `.net` 鍙兘鍙槸鍩熷悕鍚庣紑锛屼笉涓€瀹氭槸 .NET 鎶€鏈€?

### 7.4 姝т箟鎶€鑳借瘝绾︽潫

浠ｇ爜甯搁噺锛?

```python
AMBIGUOUS_TERMS = {
    "react", "go", "swift", "rust", "java", "python",
    "ruby", "scala", "spring", "node", "next", "dart",
    "shell", "pandas", "spark", "agent"
}
```

浣滅敤锛?

- `react` 鍙兘鏄€滀綔鍑哄弽搴斺€濄€?
- `go` 鏄櫘閫氬姩璇嶃€?
- `swift` 鍙寚蹇€熴€?
- `python` 涔熷彲鑳芥槸鍔ㄧ墿鎴栭潪鎶€鏈澧冦€?

杩欎簺璇嶄笉鑳藉崟鐙綔涓哄己璇佹嵁锛屽繀椤婚厤鍚堟爣棰樹笂涓嬫枃銆佸己鎶€鑳借瘝鎴栫鎶€缁忔祹涓婚鍏辩幇銆?

### 7.5 绉戞妧涓婚涓庣粡娴庝富棰樺叡鐜?

绉戞妧涓婚锛?

```python
TECH_THEMES = (
    "SOFTWARE", "COMPUTER", "CYBER", "ARTIFICIAL_INTELLIGENCE",
    "MACHINE_LEARNING", "WB_652_ICT_APPLICATIONS", "TECHNOLOGY",
)
```

缁忔祹/鍔冲姩鍔涗富棰橈細

```python
ECON_THEMES = (
    "ECON_", "LAYOFF", "UNEMPLOY", "WB_855_LABOR", "ENTREPRENEUR",
    "EPU_ECONOMY", "HIRING", "RECRUIT", "WB_2024",
)
```

浣滅敤锛?

- 瀵规涔夋妧鑳借瘝锛岃姹傛妧鏈富棰樺拰缁忔祹/鍔冲姩鍔涗富棰樺叡鐜般€?
- 渚嬪鍙湁 `python` 涓嶅锛涘鏋滃悓鏃跺嚭鐜扮鎶€涓婚鍜屾嫑鑱?缁忔祹涓婚锛屾墠鏇村彲淇°€?

### 7.6 鍩熷悕榛戝悕鍗?

浠ｇ爜甯搁噺锛?

```python
JUNK_DOMAIN_SUBSTR = (
    "ticker", "marketsdaily", "dailypolitical", "defenseworld",
    "prokerala", "starmagazine", "newsbusters", "ghanamma",
    "wyomingnewsnow", "dailymail", "insidermonkey", "finanznachrichten",
)
```

浣滅敤锛?

- 杩囨护鑲＄エ鑷姩鑱氬悎绔欍€佸皬鎶ャ€佷綆璐ㄩ噺绔欑偣銆?
- 杩欎簺绔欑偣浼氬埗閫犲ぇ閲忓叧閿瘝鍣煶銆?

### 7.7 寮卞彲淇″煙鍚嶉檷鏉?

浠ｇ爜甯搁噺锛?

```python
WEAK_DOMAIN_SUBSTR = (
    "manilatimes", "webindia", "calcuttanews", "moneycontrol",
    "tickerreport", "livemint"
)
```

浣滅敤锛?

- 涓嶇洿鎺ュ垹闄ゃ€?
- 鍦ㄦ爣棰樿川閲忓垎閲岄檷鏉冦€?

### 7.8 鍧忔爣棰樿繃婊?

鍧忔爣棰樼煭璇細

```python
BAD_TITLE_PHRASES = (
    "reacts to", "readers react", "doctor reacts",
    "python eggs", "bridge cracks", "amid crisis", ...
)
```

鍧忔爣棰樿瘝锛?

```python
BAD_TITLE_WORDS = {
    "war", "iran", "trump", "shooting", "murder",
    "gaza", "ukraine", "flood", "earthquake", ...
}
```

浣滅敤锛?

- 杩囨护鏀挎不銆佺伨瀹炽€佺ぞ浼氭柊闂荤瓑闈?IT 瓒嬪娍鍐呭銆?
- 閬垮厤 `react`銆乣python` 绛夎瘝閫犳垚璇懡涓€?

### 7.9 宀椾綅涓婁笅鏂囪瘝

浠ｇ爜甯搁噺锛?

```python
ROLE_CONTEXT_WORDS = {
    "frontend", "backend", "fullstack", "developer",
    "engineer", "architect", "software", "qa", "sre",
    "cloud", "data", "mobile", "web", "api", "hiring", "job"
}
```

浣滅敤锛?

- 鏍囬鎴?URL slug 涓嚭鐜板矖浣嶄笂涓嬫枃璇嶏紝璇存槑鏇村彲鑳芥槸 IT 宀椾綅鐩稿叧銆?

### 7.10 瑙掕壊閿氳瘝涓庡繀闇€璇?

瑙掕壊閿氳瘝鎵╁睍锛?

```python
ROLE_ANCHOR_EXPANSIONS = {
    "ai": {"ai", "artificial", "intelligence", "machine", "learning", "llm", "openai", "agent"},
    "frontend": {"frontend", "react", "vue", "angular", "javascript", "typescript"},
    "backend": {"backend", "server", "api", "java", "python", "node", "microservices"},
    ...
}
```

瑙掕壊蹇呴渶璇嶏細

```python
ROLE_REQUIRED_TERMS = {
    "backend go engineer": {"go", "golang"},
    "backend java engineer": {"java", "spring"},
    "frontend react engineer": {"react", "reactjs", "javascript", "typescript", "frontend"},
    ...
}
```

浣滅敤锛?

- 闄愬埗鈥滆繖涓簨浠跺埌搴曟槸涓嶆槸杩欎釜宀椾綅鐨勮瘉鎹€濄€?
- 渚嬪 Backend Go Engineer 鑷冲皯瑕佸懡涓?`go/golang`銆?
- Frontend React Engineer 涓嶈兘鍙洜涓烘櫘閫氳嫳鏂?react 灏卞叆閫夈€?

### 7.11 鏍囬璐ㄩ噺鍒?

鍑芥暟锛?

```python
_title_quality(title, domain) -> float
```

閫昏緫锛?

- 鍧忔爣棰樼洿鎺?0銆?
- 鏍囬澶煭鎴栫函鏁板瓧浣庡垎銆?
- 鏈夊矖浣嶄笂涓嬫枃璇嶅姞鍒嗐€?
- 鏈夋槑纭妧鑳借瘝鍔犲垎銆?
- 寮卞彲淇″煙鍚嶉檷鏉冦€?

鐢ㄩ€旓細

- RAG 鎺掑簭鏃跺弬涓庡鍚堝垎銆?
- 鍥捐氨鍏ュ浘鏃惰姹傛渶浣庢爣棰樿川閲忋€?

### 7.12 宀椾綅鐩稿叧鎬у垎

鍑芥暟锛?

```python
_role_title_affinity(role, info, title) -> float
```

閫昏緫锛?

- 鏍囬蹇呴』鍛戒腑璇ュ矖浣嶇殑 role anchor銆?
- 鐗瑰畾宀椾綅蹇呴』婊¤冻 required terms銆?
- 濡傛灉鍙懡涓涔夎瘝锛岃€屼笖娌℃湁寮烘妧鏈笂涓嬫枃锛屽垯鍒?0銆?
- 鍛戒腑澶氫釜閿氳瘝銆佸矖浣嶈瘝銆佸己鎶€鑳借瘝浼氬姞鍒嗐€?

鐢ㄩ€旓細

- RAG 鎺掑簭銆?
- 鍥捐氨鍏ュ浘銆?
- 灞曠ず寮哄急鐩稿叧銆?

### 7.13 鍘婚噸

涓ゅ眰鍘婚噸锛?

1. URL 鍘婚噸銆?
2. 鏍囬杩戦噸澶嶅幓閲嶃€?

鏍囬杩戦噸澶嶇鍚嶏細

```python
_title_sig(title)
```

鍋氭硶锛?

- 鍙栨爣棰樺墠 7 涓疄璇嶄綔涓虹鍚嶃€?
- 閬垮厤鍚屼竴鏂伴椈涓嶅悓 URL 鎴栬浆杞界増鏈噸澶嶅叆閫夈€?

### 7.14 鏂瑰悜瀵归綈

鍑芥暟锛?

```python
_direction_align(tone, etype, direction)
```

閫昏緫锛?

- 濡傛灉棰勬祴鏂瑰悜鏄?`flat/stable`锛屾柟鍚戝榻愰粯璁?0.5銆?
- 濡傛灉棰勬祴 `up`锛屽亸濂芥 tone 鍜屾満浼氱被浜嬩欢銆?
- 濡傛灉棰勬祴 `down`锛屽亸濂借礋 tone 鍜岄闄╃被浜嬩欢銆?
- 鏈轰細绫伙細

```python
OPPORTUNITY_TYPES = {"funding", "product_release", "research_breakthrough"}
```

- 椋庨櫓绫伙細

```python
RISK_TYPES = {"layoff", "policy", "security_incident"}
```

### 7.15 鍙嶅悜淇″彿淇濈暀

RAG 涓嶅彧閫夋嫨鏀寔棰勬祴鐨勮瘉鎹€?

褰撴柟鍚戞槑纭椂锛屽鏋?TopK 鍏ㄩ儴鏄悓鍚戣瘉鎹紝浠ｇ爜浼氬皾璇曚繚鐣欎竴鏉″弽鍚戜俊鍙凤細

```text
涓婃定缁撹閲屼繚鐣欎竴鏉¤礋鍚戦闄?
涓嬮檷缁撹閲屼繚鐣欎竴鏉℃鍚戞満浼?
```

鐩殑锛?

- 閬垮厤閫夋嫨鎬т妇璇併€?
- 缁?CoT 鎻愪緵鈥滄潈琛″弽鍚戣瘉鎹€濈殑鏉愭枡銆?

### 7.16 鍥捐氨鍏ュ浘绾︽潫

鏂囦欢锛?

```text
pipelines/graph/build_event_graph.py
```

鏍稿績闃堝€硷細

```python
TOPK_GRAPH = 3
WEIGHT_FLOOR = 0.35
PCTL = 60
TITLE_QUALITY_MIN = 0.5
ROLE_AFFINITY_MIN = 0.5
```

鍚箟锛?

- 鍥捐氨姣旀櫘閫?RAG 鏇翠弗鏍笺€?
- 姣忎釜宀椾綅鍙寕灏戦噺浜嬩欢銆?
- 鍏ュ浘浜嬩欢瑕佹眰鏍囬璐ㄩ噺 >= 0.5銆?
- 鍏ュ浘浜嬩欢瑕佹眰宀椾綅鐩稿叧鎬?>= 0.5銆?
- 妫€绱㈠垎鏁扮敤 P60 鍔ㄦ€侀槇鍊?+ 缁濆鍦版澘杩囨护銆?

---

## 8. 澶嶅悎鎺掑簭鍏紡

浠ｇ爜娉ㄩ噴涓渶鍒濊璁′负锛?

```text
composite = 0.4路涓婚鐩稿叧(BM25)
          + 0.3路鏂瑰悜瀵归綈
          + 0.2路浜嬩欢閲嶈鎬?
          + 0.1路鏃堕棿杩戝害
```

瀹為檯浠ｇ爜鍦ㄥ姞鍏ヨ川閲忕害鏉熷悗浣跨敤鏇寸ǔ鐨勭増鏈細

```text
composite =
  0.25 * BM25涓婚鐩稿叧
+ 0.20 * 鏂瑰悜瀵归綈
+ 0.10 * salience
+ 0.05 * 鏃堕棿杩戝害
+ 0.20 * 鏍囬璐ㄩ噺
+ 0.20 * 宀椾綅鐩稿叧鎬?
```

鍏朵腑锛?

- BM25锛氳鑹插悕銆佸埆鍚嶃€乼op_skills 涓庝簨浠朵富棰?鍖归厤璇?鏍囬鐨勭浉鍏冲害銆?
- 鏂瑰悜瀵归綈锛氫簨浠舵儏缁笌棰勬祴鏂瑰悜鏄惁涓€鑷淬€?
- salience锛歵one 寮哄害鍜?match_weight銆?
- 鏃堕棿杩戝害锛氬悓绐楀彛鍐呰秺鏂扮殑浜嬩欢鐣ヤ紭鍏堛€?
- 鏍囬璐ㄩ噺锛氭爣棰樻槸鍚﹀儚鐪熷疄 IT/琛屼笟浜嬩欢銆?
- 宀椾綅鐩稿叧鎬э細鏍囬鏄惁鍜岃宀椾綅纭疄鐩稿叧銆?

---

## 9. CoT 閮ㄥ垎鎬庝箞鐢?

### 9.1 CoT 鐨勮竟鐣?

鏈ā鍧楀姞鍏ョ殑鏄?**grounded CoT context**锛屼笉鏄湪鍚庣鐩存帴璋冪敤 LLM 鐢熸垚鏈€缁堝洖绛斻€?

杈圭晫锛?

- 鏈ā鍧楄礋璐ｆ妸浜嬪疄銆佽瘉鎹拰寮曠敤缂栧彿鏁寸悊濂姐€?
- Agent 鎴?LLM 灞傝礋璐ｇ敓鎴愯嚜鐒惰瑷€閾惧紡瑙ｉ噴銆?
- LLM 蹇呴』琚害鏉熶负鍙兘渚濇嵁缁欏畾璇佹嵁鎺ㄧ悊銆?

### 9.2 浠ｇ爜浣嶇疆

```text
app/services/trend_explanation.py
```

### 9.3 涓婁笅鏂囩粨鏋?

璋冪敤锛?

```python
from app.services.trend_explanation import assemble_cot_context

ctx = assemble_cot_context("RAG Engineer", horizon=3)
```

杩斿洖锛?

```json
{
  "canonical_role": "RAG Engineer",
  "horizon_months": 3,
  "prediction": {
    "trend_direction": "flat",
    "predicted_demand_index": 0.016,
    "confidence": 0.72
  },
  "aggregate": {},
  "events": [
    {
      "cite": "E1",
      "title": "...",
      "impact": "negative",
      "event_type": "security_incident",
      "tone": -4.479,
      "is_counter_signal": false,
      "evidence_strength": "weak",
      "url": "..."
    }
  ],
  "major_events": [
    {
      "cite": "M1",
      "title": "...",
      "date": "2025-04-14",
      "impact": "positive",
      "source_url": "..."
    }
  ],
  "jobs": [
    {
      "cite": "J1",
      "company": "...",
      "title": "...",
      "salary_mid": 130000
    }
  ],
  "note": "..."
}
```

寮曠敤缂栧彿绾﹀畾锛?

```text
E# = GDELT / 鏂伴椈浜嬩欢璇佹嵁
M# = 閲嶅ぇ琛屼笟浜嬩欢
J# = JD 鍦ㄦ嫑璇佹嵁
```

### 9.4 鏋勯€?CoT Prompt

璋冪敤锛?

```python
from app.services.trend_explanation import assemble_cot_context, build_cot_prompt

ctx = assemble_cot_context("RAG Engineer", horizon=3)
prompt = build_cot_prompt(ctx)
```

Prompt 瑕佹眰 LLM 鎸変互涓嬫楠ゅ洖绛旓細

```text
Step1 妯″瀷棰勬祴璇翠簡浠€涔?
Step2 鏂伴椈闈㈡暣浣撴儏缁浣?
Step3 鍏抽敭浜嬩欢鎬庢牱鏀拺鎴栧弽椹宠棰勬祴
Step4 鍦ㄦ嫑 JD 鍙嶆槧鐨勭煭鏈熼渶姹?
Step5 缁煎悎鍒ゆ柇璇ュ矖浣嶈秼鍔垮強涓诲洜
```

### 9.5 绯荤粺鎻愮ず

浠ｇ爜涓彁渚涳細

```python
COT_SYSTEM_PROMPT
```

鏍稿績绾︽潫锛?

1. 鍙兘渚濇嵁缁欏畾璇佹嵁鎺ㄧ悊銆?
2. 姣忎釜鍒ゆ柇鍚庡繀椤绘爣娉ㄥ紩鐢ㄧ紪鍙凤紝濡?`[E1]`銆乣[M1]`銆乣[J1]`銆?
3. 濡傛灉瀛樺湪鍙嶅悜淇″彿锛屽繀椤绘槑纭寚鍑哄苟鏉冭　銆?

### 9.6 鍛戒护琛岃嚜妫€

```bash
python -m app.services.trend_explanation "RAG Engineer"
```

杈撳嚭锛?

- 瑙掕壊棰勬祴銆?
- 鑱氬悎鏂伴椈淇″彿銆?
- 缂栧彿浜嬩欢璇佹嵁銆?
- 閲嶅ぇ琛屼笟浜嬩欢銆?
- JD 璇佹嵁銆?
- 鍒嗘楠ゆ帹鐞嗕换鍔°€?

---

## 10. API 鎬庝箞鐢?

### 10.1 鑾峰彇瓒嬪娍鍜岃瘉鎹?

鎺ュ彛锛?

```http
GET /v1/trends/{job_role}?horizon_months=3
```

绀轰緥锛?

```bash
curl "http://localhost:8000/v1/trends/RAG%20Engineer?horizon_months=3"
```

杩斿洖锛?

- canonical_role
- horizon_months
- trend_direction
- predicted_demand_index
- confidence
- main_factors
- evidence

璇ユ帴鍙ｅ唴閮ㄨ皟鐢細

```python
TrendService.get_signal()
```

鐒跺悗鑷姩璧帮細

```python
EvidenceService.retrieve_evidence()
```

### 10.2 鍙幏鍙栬瘉鎹?

鎺ュ彛锛?

```http
GET /v1/evidence/{job_role}
```

鍙傛暟锛?

```text
start_month: 榛樿 2026-01
end_month:   榛樿 2026-06
top_k:       榛樿 5
direction:   鍙€?up / flat / down
```

绀轰緥锛?

```bash
curl "http://localhost:8000/v1/evidence/RAG%20Engineer?start_month=2026-01&end_month=2026-06&top_k=5&direction=flat"
```

杩斿洖锛?

```json
{
  "role": "RAG Engineer",
  "months": ["2026-01", "2026-06"],
  "direction": "flat",
  "aggregate": {},
  "events": [],
  "jobs": [],
  "candidates_total": 259,
  "candidates_kept": 5,
  "note": "..."
}
```

---

## 11. 鍥捐氨鎬庝箞鐢?

### 11.1 浜嬩欢鍥捐氨璇箟

鑺傜偣锛?

```text
event
job
skill
resource
```

鏂板鍏崇郴锛?

```text
AFFECTS(event -> job)
```

浜嬩欢鑺傜偣瀛楁锛?

```json
{
  "title": "...",
  "url": "...",
  "source_domain": "...",
  "published_at": "...",
  "tone": -3.1,
  "event_type": "security_incident",
  "role_affinity": 0.7,
  "title_quality": 0.8,
  "themes": [],
  "source_layer": "rag_event"
}
```

杈瑰瓧娈碉細

```json
{
  "src_type": "event",
  "src_id": "evt_xxx",
  "dst_type": "job",
  "dst_id": "role_011",
  "relation": "AFFECTS",
  "weight": 0.7167,
  "confidence": 0.85,
  "meta_json": {
    "impact_direction": "positive",
    "trend_impact_direction": "neutral",
    "event_type": "model_release",
    "month": "2026-08-01",
    "trend_direction": "flat",
    "role_family": "Emerging AI",
    "source_layer": "public_major_event"
  }
}
```

### 11.2 棰滆壊瑙勫垯

鏂囦欢锛?

```text
app/services/evidence_color.py
```

褰撳墠璁捐锛?

- 浜嬩欢鑺傜偣缁熶竴鐏拌壊銆?
- 杈归鑹茶〃杈捐秼鍔?璇佹嵁鏂瑰悜銆?

棰滆壊锛?

```text
缁胯壊杈?= 涓婂崌棰勬祴锛屾垨鎸佸钩棰勬祴涓嬬殑鏄庣‘姝ｅ悜鎶€鏈簨浠?
绾㈣壊杈?= 涓嬮檷棰勬祴锛屾垨鎸佸钩棰勬祴涓嬬殑鏄庣‘椋庨櫓浜嬩欢
钃濊壊杈?= 鎸佸钩/娣峰悎/涓嶆槑纭瘉鎹?
```

涓轰粈涔堣繖鏍疯璁★細

- 濡傛灉鐢ㄤ簨浠惰妭鐐圭孩缁匡紝浼氬嚭鐜扳€滅豢鑹蹭簨浠跺緢澶氾紝浣嗕笅闄嶅矖浣嶆洿澶氣€濈殑璇銆?
- 浜嬩欢鏈韩鏄瘉鎹紝涓嶇洿鎺ヤ唬琛ㄥ矖浣嶉娴嬫柟鍚戙€?
- AFFECTS 杈规墠琛ㄧず鈥滆繖涓簨浠跺浣曞奖鍝嶈繖涓矖浣嶈秼鍔库€濄€?

鎸佸钩棰勬祴涓嬬殑浜岀骇绾︽潫锛?

- 涓嶇洿鎺ョ浉淇℃墍鏈?`impact_direction=positive`銆?
- `market_report` 涓嶈嚜鍔ㄦ煋缁裤€?
- 鏍囬鍚?`engineer/developer/job/hiring/senior/junior/remote/on site` 绛夋嫑鑱樼棔杩癸紝涓嶆煋缁裤€?
- 鍙湁鏄庣‘鎶€鏈簨浠剁被鍨嬫墠鏌撶豢銆?
- 瀹夊叏浜嬫晠銆佺洃绠°€侀闄╀簨浠舵墠鏌撶孩銆?

褰撳墠棰滆壊缁熻锛?

```text
positive/缁? 138
negative/绾? 25
neutral/钃? 158
```

### 11.3 鐢熸垚鍥捐氨

鐢熸垚浜嬩欢鍥捐氨鏁版嵁锛?

```bash
python -m pipelines.graph.build_event_graph
```

鐢熸垚绾簨浠跺浘锛?

```bash
python -m pipelines.graph.build_event_graph_view
```

鐢熸垚鍏ㄩ噺铻嶅悎鍥撅細

```bash
python -m pipelines.graph.build_unified_graph_view --full --top-n 12
```

鐢熸垚鍗曡鑹茶瀺鍚堝浘锛?

```bash
python -m pipelines.graph.build_unified_graph_view --role "RAG Engineer" --top-n 12
```

鎵撳紑锛?

```text
reports/event_graph_view.html
reports/full_unified_graph.html
reports/role_011_unified_graph.html
```

鍏ㄩ噺铻嶅悎鍥鹃粯璁ら殣钘忔爣绛撅紝鍥犱负鑺傜偣澶銆傞渶瑕佺湅鍚嶇О鏃剁偣鍑烩€滄樉绀烘爣绛锯€濄€?

---

## 12. 婕旂ず鍛戒护

### 12.1 鏌ョ湅鏌愯鑹插畬鏁磋瘉鎹摼

```bash
python -m pipelines.trend.show_evidence_demo --role "RAG Engineer"
```

杈撳嚭鍖呮嫭锛?

- PatchTST 閲岀▼纰戦娴嬨€?
- 鑱氬悎鏂伴椈淇″彿銆?
- TopK 浜嬩欢璇佹嵁銆?
- JD 鍦ㄦ嫑璇佹嵁銆?
- 閲嶅ぇ琛屼笟浜嬩欢銆?
- note 椋庨櫓璇存槑銆?

### 12.2 閲嶅缓绱㈠紩

```bash
python -m pipelines.trend.build_evidence_index
```

鏍锋湰璋冭瘯锛?

```bash
python -m pipelines.trend.build_evidence_index --sample
```

### 12.3 閲嶅缓瓒嬪娍璇佹嵁

```bash
python -m pipelines.trend.build_trend_evidence
```

閫愭湀鐗堟湰锛?

```bash
python -m pipelines.trend.build_trend_evidence --monthly
```

### 12.4 閲嶅缓鍥捐氨鍜?HTML

```bash
python -m pipelines.graph.build_event_graph
python -m pipelines.graph.build_event_graph_view
python -m pipelines.graph.build_unified_graph_view --full --top-n 12
```

---

## 13. 褰撳墠璇勪及缁撴灉

璇勪及鏂囦欢锛?

```text
reports/eval/industry_trend_explanation_eval_v1.md
```

褰撳墠鏍稿績鎸囨爣锛?

```text
瓒嬪娍缁撹鎬绘暟: 345
鍚仛鍚堜俊鍙疯鐩栫巼: 97.1% (335/345)
鍚共鍑€浜嬩欢鏍锋湰瑕嗙洊鐜? 97.1% (335/345)
骞冲潎骞插噣浜嬩欢鏁?鏉? 4.16 (TopK=5)
瑕嗙洊瑙掕壊: 69
```

瑙ｉ噴锛?

- 鑱氬悎淇″彿瑕嗙洊鐜囬珮锛岃鏄庡ぇ閮ㄥ垎瓒嬪娍缁撹閮芥湁缁熻鏀拺銆?
- 骞插噣浜嬩欢瑕嗙洊鐜囬珮锛屼絾鍏朵腑浠嶆湁 weak 浜嬩欢锛岄渶瑕佺粨鍚?risk_notes 璇存槑銆?
- 鐢变簬 GDELT 鏃犳鏂囷紝涓嶈兘澹扮О鎵€鏈夊崟鏉℃柊闂婚兘瀹屽叏鍑嗙‘锛屽彧鑳借鈥滅浉鍏虫€ц繎浼尖€濄€?

---

## 14. 宸茬煡闄愬埗

1. **GDELT 鏃犳鏂?*
   - 鍗曟潯浜嬩欢鍙兘渚濊禆 URL slug銆乼hemes銆乼one銆乵atched_terms銆?
   - 鎵€浠ュ崟鏉′簨浠惰В閲婂姏鏈夐檺銆?

2. **鍏抽敭璇嶅櫔闊?*
   - `react/go/python/rust/swift` 绛夎瘝瀹规槗璇尮閰嶃€?
   - 宸查€氳繃姝т箟璇嶇害鏉熴€佸潖鏍囬杩囨护銆佽鑹查敋璇嶇瓑鏂瑰紡缂撹В銆?

3. **鑻辨枃鏉ユ簮鍋忓**
   - 褰撳墠璇佹嵁澶氭潵鑷嫳鏂囨柊闂绘簮銆?
   - 涓枃鏈湡甯傚満浠嶉渶琛ュ厖銆?

4. **JD URL 缂哄け**
   - JD 璇佹嵁鏃犳硶鎻愪緵鍙偣鍑诲矖浣嶉摼鎺ャ€?
   - 鐩墠鍙綔涓哄瓨鍦ㄦ€ц瘉鎹€?

5. **瓒嬪娍棰勬祴涓庢柊闂荤獥鍙ｄ笉涓€鑷?*
   - PatchTST 棰勬祴鏈潵 3/6/12/24/36 涓湀銆?
   - 鏂伴椈鍙鐩?2026-01~06銆?
   - 鍥犳璇佹嵁绐楀彛鍥哄畾涓烘渶杩戠湡瀹炰簨浠剁獥鍙ｏ紝鑰屼笉鏄娴嬫湀浠姐€?

6. **棰滆壊鍙槸鍙鍖栬緟鍔?*
   - 鍥捐氨杈归鑹蹭笉鏄ā鍨嬭缁冩爣绛俱€?
   - 棰滆壊瑙勫垯鐢ㄤ簬灞曠ず锛屼笉鑳芥浛浠?trend_direction銆乮mpact_direction 鍘熷瀛楁銆?

---

## 15. 鍚戦槦鍙?鑰佸笀瑙ｉ噴鏃跺彲浠ヨ繖鏍疯

鎴戜滑杩欎釜妯″潡涓嶆槸绠€鍗曞湴鎶婂嚑鏉℃柊闂昏创鍒拌秼鍔垮悗闈紝鑰屾槸鍋氫簡涓€鏉″畬鏁寸殑鈥滈娴嬭В閲婇摼鈥濓細

1. 涓婃父 PatchTST 缁欏嚭宀椾綅鏈潵瓒嬪娍銆?
2. 鎴戜滑浠?GDELT 鍜?JD 鏁版嵁涓寜宀椾綅銆佹湀浠芥瀯寤鸿瘉鎹储寮曘€?
3. 妫€绱㈡椂鍏堢敤缁撴瀯鍖栧垎鐗囧彫鍥炲€欓€夛紝鍐嶉€氳繃鎶€鑳借瘝鐧藉悕鍗曘€佷富棰樺叡鐜般€佸煙鍚嶉粦鍚嶅崟銆佸潖鏍囬杩囨护銆佽鑹查敋璇嶃€佸矖浣嶇浉鍏虫€х瓑澶氶噸绾︽潫杩囨护鍣煶銆?
4. 瀵瑰€欓€変簨浠跺仛 BM25 涓婚鐩稿叧銆佹柟鍚戝榻愩€佹爣棰樿川閲忋€佸矖浣嶇浉鍏虫€х瓑澶嶅悎鎺掑簭銆?
5. 杈撳嚭涓ゅ眰璇佹嵁锛氳仛鍚堜俊鍙蜂綔涓轰富鍔涳紝TopK 浜嬩欢浣滀负浠ｈ〃鎬т綈璇侊紝JD 浣滀负瀛樺湪鎬ц瘉鎹€?
6. 瀵?LLM/Agent锛屾垜浠笉璁╁畠鑷敱缂栭€狅紝鑰屾槸鎻愪緵甯﹀紩鐢ㄧ紪鍙风殑 grounded CoT prompt锛岃姹傛瘡涓€姝ユ帹鐞嗛兘寮曠敤璇佹嵁銆?
7. 瀵瑰彲瑙嗗寲锛屾垜浠妸浜嬩欢鎺ュ叆鑱屼笟鍥捐氨锛岀敤 AFFECTS 杈硅〃绀轰簨浠跺宀椾綅瓒嬪娍鐨勫奖鍝嶏紝骞堕€氳繃杈归鑹插睍绀轰笂鍗囥€佷笅闄嶃€佹寔骞虫垨娣峰悎褰卞搷銆?

涓€鍙ヨ瘽鎬荤粨锛?

```text
鏈ā鍧楀畬鎴愪簡琛屼笟瓒嬪娍棰勬祴涔嬪悗鐨?RAG 璇佹嵁妫€绱€佸彈绾︽潫 CoT 瑙ｉ噴涓婁笅鏂囥€佷簨浠跺叆鍥惧拰鍙鍖栧睍绀洪棴鐜€?
```

