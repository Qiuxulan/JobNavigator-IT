# 妯″潡 D 瀹炵幇鎬荤粨

## 1. 鏈疆宸ヤ綔鐨勮寖鍥?
鏈疆宸ヤ綔鐨勬牳蹇冩槸鎶婅亴涓氭帹鑽愰儴鍒嗛噸鏋勬垚涓€鏉″畬鏁寸殑 D 妯″潡閾捐矾锛?*绠€鍘嗚緭鍏?-> 鎶€鑳芥娊鍙栦笌鏍囧噯鍖?-> Top10 宀椾綅鍚戦噺绮楀彫鍥?-> 鍥捐氨绮炬帓 -> GraphSAGE 杈呭姪璺緞鎼滅储 -> 澶фā鍨嬫姤鍛婄敓鎴?*銆? 
鍏朵腑锛宍job_roles.embedding` 鍙礋璐ｈ涔夌矖鍙洖锛屽浘璋辫礋璐ｅ矖浣嶆妧鑳界己鍙ｃ€佹妧鑳藉厛淇叧绯汇€佽祫婧愭寕杞姐€佽矾寰勭敓鎴愬拰鏈€缁堢簿鎺掞紝`GraphSAGE` 璐熻矗瀛︿範鍥剧粨鏋?embedding锛屽苟鎶婂畠鐢ㄤ簬 A* 鎼滅储鍚彂寮忓拰缁撴瀯鍙揪鎬у鍔便€?
鍓嶉潰 A/B/C 妯″潡娌℃湁琚噸鍋氾紝鍙仛浜嗕笌 D 瀵规帴鎵€蹇呴渶鐨勬帴鍏ュ拰澶嶇敤锛欰 妯″潡缁х画鎻愪緵鎶€鑳芥娊鍙栧叆鍙ｏ紝B 妯″潡缁х画鎻愪緵宀椾綅搴撳拰宀椾綅鍚戦噺锛孋 妯″潡缁х画鎻愪緵鎶€鑳藉厛淇浘鍜屽涔犺祫婧愬簱銆備篃灏辨槸璇达紝鏈疆鐨勯噸鐐逛笉鏄噸寤?A/B/C锛岃€屾槸鎶婅繖浜涙棦鏈変骇鐗╃粍缁囨垚 D 鐨勫彲杩愯涓婚摼璺€?
---

## 2. 浠ｇ爜鏀瑰姩鎬昏

### 2.1 鎶藉彇銆佹帹鑽愩€佽矾寰勪笌鎺ュ彛灞?
- `app/services/extractor.py`锛氭妸鍦ㄧ嚎鎶藉彇閾捐矾缁熶竴鎴愨€滃井璋冩ā鍨嬩紭鍏?+ 瑙勫垯璇嶈〃鍏滃簳 + 缁熶竴鏍囧噯鍖栤€濈殑琛屼负锛屼笉鍐嶅仠鐣欏湪 mock 绾у埆锛涘悓鏃朵繚璇佹ā鍨嬬┖杈撳嚭鏃朵粛鐒惰兘浜у嚭鍙敤鎶€鑳介泦鍚堛€?- `app/services/recommender.py`锛氭妸鎺ㄨ崘閾捐矾浠庢棫鐨勫惎鍙戝紡璺緞浠ｄ环锛屾敼鎴愬鐢?D 妯″潡鐨勭矖鍙洖涓庡浘璋辩簿鎺掔粨鏋滐紝涓嶅啀璁╂棫鐨?`path_cost_score / trend_reward_score` 涓诲鏈€缁堟帓搴忋€?- `app/services/path_planner.py`锛氭妸瀹冧粠鈥滄棫璺緞鐢熸垚涓婚€昏緫鈥濇敼鎴愮紪鎺掑眰锛屼紭鍏堣皟鐢?D 妯″潡鐨?`GraphPathPlannerV2`锛屽彧淇濈暀鍏煎鎬ц鑹层€?- `app/services/career_pathway_service.py`锛氭柊澧?D 妯″潡缁熶竴鏈嶅姟灞傦紝璐熻矗棰勬绮楀彫鍥炵幆澧冦€佹墽琛?Top10 宀椾綅鍚戦噺鍙洖銆佽皟鐢ㄥ浘璋辩簿鎺掍笌璺緞瑙勫垝锛屾槸 `/v1/careers/report` 涓庡悗缁亴涓氭帴鍙ｇ殑涓诲叆鍙ｃ€?- `app/services/career_catalog.py`锛氭柊澧炵粺涓€鏁版嵁璁块棶灞傦紝璐熻矗璇诲彇宀椾綅搴撱€佹妧鑳藉浘銆佽祫婧愬簱锛屽苟鎶婂矖浣嶆妧鑳芥寜 `skill_vocab.json` 鏄犲皠鍒扮粺涓€ `skill_id`锛屽悓鏃舵彁渚涒€滄瘡涓矖浣嶅彧鍙?Top30 鎶€鑳解€濈殑鏍稿績閫昏緫銆?- `app/services/graph_path_planner_v2.py`锛氭柊澧?D 妯″潡鐪熸鐨勫浘璋辫矾寰勮鍒掑櫒锛屽疄鐜扮己澶辨妧鑳介泦鍚堢殑 A* 鎼滅储銆佸叡浜厛淇悎骞躲€佸涔犺矾寰勭敓鎴愩€佸矖浣嶅垎鏁拌绠椾互鍙?GraphSAGE 缁撴瀯濂栧姳銆?- `app/services/report_generator.py`锛氭柊澧炲ぇ妯″瀷鎶ュ憡鏈嶅姟锛屾妸鐢ㄦ埛鐢诲儚銆佺矖鍙洖銆佸浘璋辩簿鎺掑拰瀛︿範璺緞鎵撳寘鎴愮粨鏋勫寲涓婁笅鏂囷紝鍐嶈皟鐢?LLM 杈撳嚭涓枃鑱屼笟鍒嗘瀽鎶ュ憡锛涘悗缁繕涓撻棬璋冩暣浜?prompt锛岃鎶ュ憡涓嶅彧鏄綏鍒楀瓧娈碉紝鑰屾槸澧炲姞鈥滀负浠€涔堟帹鑽愩€佸尮閰嶅己寮便€佹妧鑳介噸鍚堝害銆佽矾寰勯闄╀笌鍣０鎶€鑳解€濈殑鍒嗘瀽銆?- `app/api/routes.py`锛氭柊澧?`/v1/careers/report`锛屾妸 D 妯″潡鏁存潯閾捐矾鏆撮湶鎴愪竴涓鍒扮鎺ュ彛锛涘悓鏃朵繚鐣欏師鏈?`/profile/extract`銆乣/jobs/recommend`銆乣/paths/generate` 鐨勫吋瀹圭粨鏋勩€?- `app/schemas/api.py`锛氭柊澧炶亴涓氭姤鍛婅姹?鍝嶅簲 schema锛岃ˉ涓?D 妯″潡绔埌绔帴鍙ｇ殑杈撳叆杈撳嚭瀹氫箟銆?- `app/schemas/domain.py`锛氳ˉ榻愪簡 D 閾捐矾涓渶瑕佺殑棰嗗煙瀵硅薄缁撴瀯锛岃宀椾綅銆佹妧鑳界己鍙ｃ€佸涔犺矾寰勩€佹姤鍛婅繑鍥炰綋鑳藉畬鏁磋〃杈俱€?- `app/core/config.py`锛氭柊澧?LLM 鐩稿叧閰嶇疆椤癸紝鍖呮嫭 `JOBNAV_LLM_BASE_URL`銆乣JOBNAV_LLM_API_KEY`銆乣JOBNAV_LLM_MODEL`銆乣JOBNAV_LLM_TIMEOUT_SEC`锛岀敤浜庨┍鍔ㄦ姤鍛婄敓鎴愩€?
### 2.2 鍥捐氨銆丟raphSAGE 涓庢牱渚嬭剼鏈?
- `pipelines/graph/build_career_graph_v2.py`锛氭柊澧炲苟纭畾涓烘渶缁堟瀯鍥捐剼鏈€傚畠鍙娇鐢?`fine_grained_roles_v1.json`銆乣skill_prerequisite_v2.json`銆乣learning_resources_v1.json`銆乣skill_vocab.json` 鍥涗唤鏍稿績浜х墿鏋勫缓涓夌被鑺傜偣锛坖ob/skill/resource锛夊拰涓夌被杈癸紙`JOB_REQUIRES`銆乣SKILL_PREREQ`銆乣SKILL_HAS_RESOURCE`锛夛紝骞舵妸姣忎釜宀椾綅鎸?`skill_freq` 鎴垚 Top30 鎶€鑳藉叆鍥俱€?- `pipelines/graph/train_graphsage_v2.py`锛氭柊澧炲苟纭畾涓烘渶缁?GraphSAGE 璁粌鑴氭湰锛屼粠鏁版嵁搴撶洿鎺ヨ鍙?`graph_nodes.feature_vector` 涓?`graph_edges` 璁粌杞婚噺涓ゅ眰 GraphSAGE锛屽鍑烘湰鍦版ā鍨嬫枃浠讹紝骞舵妸 embedding 鍐欏洖鏁版嵁搴撱€?- `pipelines/graph/export_graph_interactive_v2.py`锛氭柊澧炲苟涓嶆柇杩唬涓烘渶缁堝浘璋卞彲瑙嗗寲鑴氭湰锛屾渶鍚庡舰鎴愮幇鍦ㄤ繚鐣欑殑 `reports/full_career_graph_v2.html`銆傝繖涓剼鏈粡鍘嗕簡澶氭 UI 璋冩暣锛氬彧鏄剧ず鍏ㄨ亴涓?+ 鍏ㄦ妧鑳戒富鍥俱€佹瘡涓矖浣嶅彧鏄剧ず Top15 鎶€鑳姐€佽妭鐐圭缉灏忋€侀粯璁ゆ瀬寮辩紦鍔ㄣ€佺偣鍑昏妭鐐归珮浜偦灞呫€佹暣浣撻厤鑹叉敼鎴愭绾?鐏?绮変綆楗卞拰涓婚銆佽竟閫忔槑搴︽樉钁楅檷浣庛€?- `pipelines/graph/run_sample_rankings_v2.py`锛氭柊澧炴牱渚嬮獙璇佽剼鏈紝鐢ㄤ簬璺戔€滄娊鍙?-> 绮楀彫鍥?-> 绮炬帓 -> 璺緞鈥濋摼璺紝骞朵笖澧炲姞浜?recall preflight锛岄伩鍏嶇己妯″瀷缂撳瓨鎴栫己鍚戦噺搴撴椂闀挎椂闂村崱浣忋€?- `pipelines/extract/diagnose_extractor_v1.py`锛氭柊澧炴娊鍙栬瘖鏂剼鏈紝鐢ㄤ簬鍖哄垎鈥滄ā鍨嬪姞杞藉け璐モ€濃€滄ā鍨嬭兘璺戜絾涓虹┖鈥濃€滆鍒欐湁鍛戒腑浣嗘ā鍨嬫棤鍛戒腑鈥濈瓑鎯呭喌锛屽府鍔╂帓鏌ュ井璋冩ā鍨嬭涓恒€?- `pipelines/report/run_resource_rich_career_reports.py`锛氭柊澧炴渶缁堜繚鐣欑殑 3 鏉￠珮璧勬簮瑕嗙洊鏍蜂緥鑴氭湰锛屼笓闂ㄩ€夋嫨鏇撮潬杩?`RAG / LLM Inference / Backend Python` 绛夎祫婧愯鐩栫浉瀵硅緝濂界殑鏂瑰悜锛屼究浜庡緱鍒版洿瀹屾暣鐨勮矾寰勮祫婧愬拰鑱屼笟鎶ュ憡銆?
### 2.3 鏁版嵁搴撱€佷緷璧栦笌娴嬭瘯

- `infra/db/migrations/002_graph_d.sql`锛氳ˉ鍏?D 妯″潡鍥捐氨琛ㄤ笌鐩稿叧缁撴瀯锛屼负鍥捐妭鐐瑰拰鍥捐竟鍏ュ簱鎻愪緵鏁版嵁搴撴敮鎸併€?- `infra/db/migrations/003_graph_d_v2.sql`锛氳ˉ鍏?v2 鍥捐氨涓?GraphSAGE 闇€瑕佺殑瀛楁鍜岃〃缁撴瀯锛岀‘淇濇渶缁堢増鏈殑鏋勫浘涓?embedding 鍥炲啓鍙惤搴撱€?- `requirements.txt`銆乣environment.yml`锛氳ˉ鍏?D 妯″潡鏂颁緷璧栵紝纭繚鍥捐氨鏋勫缓銆丟raphSAGE銆佹姤鍛婄敓鎴愬拰娴嬭瘯鑴氭湰鍦ㄦ湰鍦?瀹瑰櫒鍐呭彲杩愯銆?- `tests/unit/test_graph_pipeline.py`锛氭柊澧?D 妯″潡鍥捐氨鏋勫缓灞傞潰鐨勬祴璇曪紝楠岃瘉鏋勫浘 payload 涓庡叧閿害鏉熴€?- `tests/unit/test_sample_rankings_v2.py`锛氭柊澧?D 妯″潡鏍蜂緥閾捐矾娴嬭瘯锛岄獙璇?`run_sample_rankings_v2` 鐨勯妫€鍜岃緭鍑恒€?- `tests/unit/test_services.py`锛氳ˉ鍏呮姤鍛婄敓鎴愬拰 D 鏈嶅姟鐨勫崟娴嬭鐩栥€?- `tests/integration/test_api_contract.py`锛氳ˉ鍏?`/v1/careers/report` 绛夋帴鍙ｅ绾︽祴璇曘€?
---

## 3. 鍥捐氨鏄€庝箞鏋勫缓鐨?
鏈€缁堝浘璋卞彧渚濊禆鍥涗唤鏍稿績鏁版嵁锛氬矖浣嶄富鏁版嵁 `data/gold/fine_grained_roles_v1.json`銆佹妧鑳藉厛淇浘 `data/gold/skill_prerequisite_v2.json`銆佸涔犺祫婧愬簱 `data/gold/learning_resources_v1.json`銆佹妧鑳藉埆鍚嶅瓧鍏?`data/gold/skill_vocab.json`銆? 
鏋勫浘鑴氭湰 `pipelines/graph/build_career_graph_v2.py` 浼氬厛鎶婃墍鏈夊矖浣嶆妧鑳姐€佺敤鎴锋妧鑳姐€佸厛淇妧鑳姐€佽祫婧愭妧鑳界粺涓€鏄犲皠鍒板悓涓€濂?`skill_id` 绌洪棿锛屽啀鏋勫缓涓夌被鑺傜偣锛氬矖浣嶈妭鐐广€佹妧鑳借妭鐐广€佽祫婧愯妭鐐广€?
宀椾綅鑺傜偣鐨勬牳蹇冩潵婧愭槸 `fine_grained_roles_v1.json`銆傝繖閲屾病鏈夊崟鐙殑鎶€鑳芥墦鍒嗗瓧娈碉紝鎵€浠ユ渶缁堥噰鐢?`skill_freq` 浣滀负宀椾綅-鎶€鑳介噸瑕佸害锛屽苟涓旀瘡涓矖浣嶅彧淇濈暀 Top30 鎶€鑳藉叆鍥俱€傛瀯鍥炬椂鎶?`importance_score`銆乣rank`銆乣is_core` 鍐欏埌 `JOB_REQUIRES` 杈逛笂锛岃繖鏍峰悗缁矾寰勬悳绱笉鍙槸鐭ラ亾鈥滅己浜嗕粈涔堟妧鑳解€濓紝杩樿兘鐭ラ亾鈥滅己鐨勬妧鑳藉宀椾綅鏈夊閲嶈鈥濄€?
鎶€鑳借妭鐐规潵鑷?`skill_prerequisite_v2.json`銆傝繖閲屼繚鐣欎簡 `level`銆乣difficulty`銆乣hours_estimate` 绛変俊鎭紝骞舵妸 prerequisites 鏋勯€犳垚 `SKILL_PREREQ` 杈癸紝鍥犳鍥捐氨涓嶅彧鏄竴涓矖浣?鎶€鑳戒簩閮ㄥ浘锛岃€屾槸鎶婃妧鑳戒箣闂寸殑瀛︿範椤哄簭涔熺紪鐮佷簡杩涘幓銆?
璧勬簮鑺傜偣鏉ヨ嚜 `learning_resources_v1.json`銆傝祫婧愪互 `skill -> resource` 鐨勫舰寮忔寕鍒?`SKILL_HAS_RESOURCE` 杈逛笂锛屾墍浠ュ浘閲屾瘡涓妧鑳界悊璁轰笂閮藉彲浠ラ檮甯﹁嫢骞茶绋嬨€佹暀绋嬫垨 GitHub 璧勬簮銆?
鏈疆瀹為檯钀藉簱缁撴灉鏄細`69` 涓矖浣嶈妭鐐广€乣275` 涓妧鑳借妭鐐广€乣385` 涓祫婧愯妭鐐癸紝鎬昏 `729` 涓妭鐐癸紱杈规柟闈㈡湁 `1967` 鏉?`JOB_REQUIRES`銆乣331` 鏉?`SKILL_PREREQ` 鍜?`461` 鏉?`SKILL_HAS_RESOURCE`锛屾€昏 `2759` 鏉¤竟銆傛瀯鍥炬憳瑕佽緭鍑哄湪 `reports/graph_build_summary_v2.json`銆?
---

## 4. GraphSAGE 鏄€庝箞璁粌鍜屼娇鐢ㄧ殑

璁粌鑴氭湰鏄?`pipelines/graph/train_graphsage_v2.py`銆傚畠鐩存帴浠庢暟鎹簱璇诲彇 `graph_nodes.feature_vector` 鍜?`graph_edges`锛屼笉鍐嶄緷璧栨棭鏈熼偅绉嶅崟鐙墿鍖栫壒寰佺殑涓棿鑴氭湰銆傝缁冧娇鐢ㄧ殑鍏崇郴鍙湁涓夌被锛歚SKILL_PREREQ`銆乣JOB_REQUIRES`銆乣SKILL_HAS_RESOURCE`锛岀洰鏍囨槸璁╁浘涓殑鐪熷疄閭绘帴鍏崇郴鍦?embedding 绌洪棿閲岃閲嶅缓鍑烘潵锛屽悓鏃堕€氳繃 `job-skill` 鐨勭粨鏋勬媺杩戠害鏉燂紝璁╁矖浣嶄笌鍏跺叧閿妧鑳藉湪鍚戦噺绌洪棿涓洿鎺ヨ繎銆?
鏈€缁堣缁冪殑鏄竴涓交閲忎袱灞?GraphSAGE銆傝缁冨畬鎴愬悗浼氳緭鍑猴細

- `models/graphsage_v2/model.pt`
- `models/graphsage_v2/embeddings.npy`
- `models/graphsage_v2/node_index.json`
- `reports/graphsage_metrics_v2.json`

鍚屾椂 embedding 浼氬啓鍥炴暟鎹簱 `graphsage_embeddings` 涓?`graph_nodes.embedding_vector`銆傛湰杞啓鍥炴潯鏁颁笌鑺傜偣鏁颁竴鑷达紝鍏?`729` 鏉°€?
鍦ㄥ湪绾挎帹鐞嗛樁娈碉紝GraphSAGE 涓嶅弬涓庡矖浣嶇矖鍙洖锛屽畠鍙湇鍔′簬 D 妯″潡鍥炬悳绱細涓€鏂归潰鐢ㄤ簬 A* 鐨勫惎鍙戝紡璺濈浼拌锛屽彟涓€鏂归潰鐢ㄤ簬宀椾綅绮炬帓涓殑 `graph_reward`锛屽嵆鈥滃綋鍓嶇敤鎴峰埌鐩爣宀椾綅鍏抽敭鎶€鑳介泦鍚堝湪鍥剧粨鏋勪笂鐨勫彲杈炬€у鍔扁€濄€?
---

## 5. 瀛︿範璺緞鏄€庝箞鐢熸垚鐨?
瀛︿範璺緞鐨勫疄鐜颁綅浜?`app/services/graph_path_planner_v2.py`銆傛祦绋嬩笉鏄洿鎺ュ宀椾綅鍋氭悳绱紝鑰屾槸鍏堥拡瀵规煇涓€欓€夊矖浣嶅彇鍑哄畠鐨?Top30 鍏抽敭鎶€鑳斤紝鍐嶆妸杩欎簺鎶€鑳藉拰鐢ㄦ埛褰撳墠鎶€鑳介泦鍚堝仛宸紝寰楀埌缂哄け鎶€鑳介泦鍚堛€備箣鍚庡姣忎釜缂哄け鎶€鑳藉湪 `SKILL_PREREQ` 鍥句笂鎵ц A* 鎼滅储锛屾壘鍑烘弧瓒冲厛淇害鏉熺殑鏈€鐭彲琛岃ˉ榻愯矾寰勩€?
涓轰簡閬垮厤閲嶅瀛︿範锛屽涓己澶辨妧鑳界殑璺緞浼氳鍚堝苟锛屽叡浜厛淇妧鑳藉彧淇濈暀涓€浠斤紱闅忓悗鍐嶅鍚堝苟鍚庣殑鎶€鑳介泦鍚堝仛鎷撴墤鎺掑簭锛屽緱鍒版渶缁堝涔犻『搴忋€傛瘡涓楠ら兘浼氬敖閲忎粠 `learning_resources_v1.json` 閲屾寕涓婃渶澶?3 涓祫婧愶紝褰㈡垚鍙墽琛岀殑瀛︿範璺緞銆?
宀椾綅鏈€缁堝垎鏁扮敱浠ヤ笅鍥犵礌鍏卞悓缁勬垚锛氳涔夌矖鍙洖鍒嗐€佸凡瑕嗙洊鍏抽敭鎶€鑳界殑閲嶈搴︽瘮渚嬨€佽祫婧愬鍔便€丟raphSAGE 缁撴瀯濂栧姳銆佺己澶辨妧鑳芥儵缃氥€佸厛淇毦搴︽儵缃氥€佹€诲鏃舵儵缃氥€備篃灏辨槸璇达紝D 妯″潡涓嶅彧鍥炵瓟鈥滃儚鍝釜宀椾綅鈥濓紝杩樺洖绛斺€滆浆杩囧幓瑕佽ˉ浠€涔堛€侀毦涓嶉毦銆佽矾寰勬槸鍚︽湁璧勬簮鍙鈥濄€?
---

## 6. 鎶ュ憡鐢熸垚閾捐矾

`app/services/report_generator.py` 鎶婅亴涓氭帹鑽愮粨鏋滆繘涓€姝ュ寘瑁呮垚閫傚悎鏈€缁堝睍绀虹殑鎶ュ憡銆傚畠浼氭妸鐢ㄦ埛鐢诲儚銆乀op10 绮楀彫鍥炪€佸浘璋辩簿鎺掑悗鐨勫€欓€夊矖浣嶃€乀op1 鐨勬妧鑳介噸鍚堜笌缂哄け鍒嗘瀽銆佸涔犺矾寰勫強鍏惰祫婧愭儏鍐垫暣鐞嗘垚涓婁笅鏂囷紝鍐嶉€氳繃 `/v1/careers/report` 璋冪敤澶фā鍨嬭緭鍑轰腑鏂囪亴涓氱瓥鐣ユ姤鍛娿€?
杩欎竴閮ㄥ垎鍚庣画鍋氫簡涓撻棬淇敼锛氭姤鍛婁笉鍐嶅彧鏄瓧娈靛爢鐮岋紝鑰屾槸鏄庣‘瑕佹眰妯″瀷瑙ｉ噴鈥滀负浠€涔堢矖鍙洖鍍忚繖浜涘矖浣嶁€濃€滀负浠€涔?Top1 姣斿叾浠栧矖浣嶆洿鍚堥€傗€濃€滈噸鍚堟妧鑳借鏄庝簡浠€涔堚€濃€滅己澶辨妧鑳界殑闅惧害鍜岃浆宀楁垚鏈浣曗€濃€滆矾寰勯噷鍝簺姝ラ鏄熀纭€銆佸摢浜涙槸瑙掕壊鍏抽敭銆佸摢浜涘彲鑳芥槸鍣０鈥濄€傝繖涓€姝ユ槸涓轰簡璁╄緭鍑烘洿鍍忓垎鏋愭姤鍛婏紝鑰屼笉鏄函琛ㄦ牸杞堪銆?
---

## 7. 鏈疆鏍蜂緥楠岃瘉缁撴灉

鏈疆鏈€缁堜繚鐣欑殑涓嶆槸鏃╂湡閭?10 鏉℃牱渚嬶紝鑰屾槸 3 鏉℃洿璐磋繎褰撳墠璧勬簮搴撹鐩栨柟鍚戠殑鏍蜂緥锛岃繍琛岃剼鏈负 `pipelines/report/run_resource_rich_career_reports.py`锛岀粨鏋滄枃浠朵繚瀛樺湪锛?
- `reports/resource_rich_career_reports_api_output.json`
- `reports/summary/job_resource_rich_career_reports_summary.md`

杩欎笁鏉℃牱渚嬪垎鍒亸鍚?`RAG / Agent`銆乣LLM Inference`銆乣Backend Python` 涓夌鏂瑰悜锛岀洰鐨勬槸璁╄矾寰勪腑鏈夋洿澶氭妧鑳借兘鎸傚埌宸叉湁瀛︿範璧勬簮銆傛渶缁堢粨鏋滄槸锛?
- `resource_rich_rag`锛歍op1 涓?`AI Agent Engineer`锛岃矾寰?24 姝ワ紝鍏朵腑 10 姝ュ甫璧勬簮锛?- `resource_rich_llm_inference`锛歍op1 涓?`LLM Inference Engineer`锛岃矾寰?21 姝ワ紝鍏朵腑 6 姝ュ甫璧勬簮锛?- `resource_rich_backend_python`锛歍op1 涓?`Backend Python Engineer`锛岃矾寰?18 姝ワ紝鍏朵腑 5 姝ュ甫璧勬簮銆?
杩欒鏄庡浘璋便€丟raphSAGE銆佽矾寰勭敓鎴愩€佹姤鍛婃帴鍙ｉ兘宸茬粡璺戦€氾紝浣嗗悓鏃朵篃鏆撮湶鍑鸿祫婧愯鐩栧苟涓嶅畬鏁淬€?
---

## 8. 鏈疆鍙戠幇鐨勯棶棰?
褰撳墠鏈€鏄庢樉鐨勯棶棰樻湁涓や釜銆傜涓€涓槸**璧勬簮瑕嗙洊涓嶈冻**锛氬緢澶氬矖浣嶈櫧鐒惰兘鎴愬姛鐢熸垚瀛︿範璺緞锛屼絾璺緞涓殑寰堝鎶€鑳藉湪 `learning_resources_v1.json` 閲屽苟娌℃湁瀵瑰簲璧勬簮锛屾墍浠ヤ細鍑虹幇閮ㄥ垎姝ラ `resources=[]`銆傝繖涓嶆槸璺緞澶辫触锛岃€屾槸璧勬簮搴撴湰韬鐩栬繕涓嶅銆?
绗簩涓槸**宀椾綅鎶€鑳界敾鍍忓櫔澹?*銆傛渶鍏稿瀷鐨勪緥瀛愭槸 `RAG Engineer` 璺緞閲屽嚭鐜颁簡 `C`銆乣Java`銆傝繖涓棶棰樺凡缁忓畾浣嶅埌鏁版嵁鍜屾帓搴忓眰锛氬畠浠洿鎺ユ潵鑷?`fine_grained_roles_v1.json` 鐨?`skill_freq`锛屽張琚?`role_top_skills()` 鏈烘鍦伴€夎繘宀椾綅 Top30锛屼笖鏈韩娌℃湁 prerequisites銆乣level` 鍙堜綆锛屾墍浠ュ湪鏈€缁堣矾寰勬帓搴忎腑琚帓鍒板墠闈€傛崲鍙ヨ瘽璇达紝杩欎釜闂鐨勬牴鍥犳槸宀椾綅鎶€鑳界敾鍍忚川閲忥紝鑰屼笉鏄?GraphSAGE 鎴?A* 绠楁硶鏈韩銆?
姝ゅ锛屽綋鍓嶅浘璋辫櫧鐒跺凡缁忔湁鏁堬紝浣嗗鏉傚害杩樻病鏈夐珮鍒扳€滄病鏈夊浘璋卞氨瀹屽叏鍋氫笉鍑烘潵鈥濈殑绋嬪害銆傚畠鏈川涓婁粛鐒舵洿鎺ヨ繎鈥滃矖浣嶆妧鑳界己鍙?+ 鎶€鑳藉厛淇浘 + GraphSAGE 杈呭姪鈥濈殑绯荤粺锛岃€屼笉鏄珮搴﹀鏉傜殑鑱屼笟鐭ヨ瘑鍥捐氨鎺ㄧ悊绯荤粺銆傝繖涓€鐐瑰湪鍚庣画濡傛灉瑕佺户缁彁鍗?D 妯″潡鏃讹紝闇€瑕佺户缁ˉ宀椾綅杩佺Щ鍏崇郴銆佹妧鑳芥浛浠ｅ叧绯诲拰鐢ㄦ埛琛屼负杈广€?
---

## 9. 褰撳墠淇濈暀鐨勬牳蹇冧骇鐗?
褰撳墠 D 妯″潡鏈€缁堜繚鐣欑殑鏍稿績浠ｇ爜鍜屼骇鐗╁涓嬶細

- `app/services/extractor.py`
- `app/services/career_catalog.py`
- `app/services/career_pathway_service.py`
- `app/services/graph_path_planner_v2.py`
- `app/services/report_generator.py`
- `pipelines/graph/build_career_graph_v2.py`
- `pipelines/graph/train_graphsage_v2.py`
- `pipelines/graph/export_graph_interactive_v2.py`
- `pipelines/graph/run_sample_rankings_v2.py`
- `pipelines/extract/diagnose_extractor_v1.py`
- `pipelines/report/run_resource_rich_career_reports.py`
- `models/graphsage_v2/model.pt`
- `models/graphsage_v2/embeddings.npy`
- `models/graphsage_v2/node_index.json`
- `reports/graph_build_summary_v2.json`
- `reports/graphsage_metrics_v2.json`
- `reports/full_career_graph_v2.html`
- `reports/resource_rich_career_reports_api_output.json`
- `reports/summary/job_resource_rich_career_reports_summary.md`

涓庝箣瀵瑰簲锛屽凡缁忓垹鎺夌殑鏃х増 D 鏂囦欢涓昏鍖呮嫭鏃╂湡 `graph_path_planner`銆佹棭鏈熸瀯鍥捐剼鏈€佹棭鏈?GraphSAGE 鑴氭湰銆丮ermaid 闈欐€佸浘瀵煎嚭鑴氭湰浠ュ強鏃х殑 10 鏉℃牱渚嬫姤鍛婅剼鏈紝鐩殑鏄妸鐩綍鏀舵暃鍒板綋鍓嶅敮涓€鏈夋晥鐨?`v2` 涓婚摼璺€?
---

## 10. 缁撹

鏈疆宸茬粡鎶婃ā鍧?D 浠庘€滀竴涓鎯斥€濇帹杩涙垚浜嗕竴濂楀畬鏁村彲杩愯鐨勭郴缁燂細绠€鍘嗗彲浠ヨ鎶藉彇涓烘妧鑳斤紝鎶€鑳藉彲浠ヨ繘鍏ョ粺涓€ `skill_id` 绌洪棿锛屽矖浣嶅彲浠ラ€氳繃 `JobBERT-v3 + pgvector` 鍋氱矖鍙洖锛屽浘璋卞彲浠ュ熀浜庡矖浣嶆妧鑳介噸瑕佸害銆佹妧鑳藉厛淇叧绯诲拰瀛︿範璧勬簮杩涜绮炬帓涓庤矾寰勭敓鎴愶紝GraphSAGE 鍙互涓哄浘鎼滅储鎻愪緵缁撴瀯琛ㄧず锛岃€屾渶缁堢粨鏋滆繕鍙互杩涗竴姝ラ€氳繃澶фā鍨嬬敓鎴愯亴涓氬垎鏋愭姤鍛娿€?
鐜伴樁娈佃繖濂楃郴缁熷凡缁忓叿澶囧彲杩愯銆佸彲瑙ｉ噴銆佸彲瑙嗗寲銆佸彲婕旂ず鐨勮亴涓氭帹鑽愪笌瀛︿範璺緞鑳藉姏銆傚悗缁鏋滅户缁凯浠ｏ紝浼樺厛绾ф渶楂樼殑鏂瑰悜浼氭槸锛氭竻娲楀矖浣嶆妧鑳界敾鍍忋€佽ˉ璧勬簮瑕嗙洊銆佹彁楂樿矾寰勬帓搴忕殑宀椾綅鐩稿叧鎬э紝浠ュ強璁╂姤鍛婃洿杩涗竴姝ュ噺灏戞ā鏉挎劅銆佸寮哄垎鏋愭€с€?
