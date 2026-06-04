"""
构建完整版 IT 技能标准词表 skill_vocab.json

每个技能条目:
  id        : 全队统一的 skill_id(小写连字符),A/B/D 共用
  name      : 标准显示名
  aliases   : 各种常见写法/缩写(用于归一化:任意写法 -> id/name)
  category  : 技能大类(用于分类/分层聚类辅助)
  hot       : 是否新兴/热门(招聘高频或新兴方向,辅助趋势加分)

产出:
  data/gold/skill_vocab.json
    - skills: 全部条目
    - alias_to_id: {别名(小写) -> id} 归一化查表
    - id_to_name: {id -> 标准名}
    - all_aliases: 所有别名(小写, 给词典匹配用)
    - by_category: {category -> [id...]}
运行(放到项目后): python -m pipelines.taxonomy.build_skill_vocab
"""

import json
import os

# ============================================================
# 技能定义区:(id, name, [aliases], category, hot)
# aliases 不必包含 name 本身和 id 本身,脚本会自动加入
# category 取值见 CATEGORIES
# ============================================================

# 语言
LANGUAGES = [
    ("python", "Python", [], True),
    ("java", "Java", ["jdk"], False),
    ("javascript", "JavaScript", ["js", "ecmascript"], False),
    ("typescript", "TypeScript", ["ts"], True),
    ("c", "C", ["c language"], False),
    ("cpp", "C++", ["cplusplus", "c plus plus"], False),
    ("csharp", "C#", ["c sharp", "csharp", "dotnet language"], False),
    ("go", "Go", ["golang"], True),
    ("rust", "Rust", [], True),
    ("ruby", "Ruby", [], False),
    ("php", "PHP", [], False),
    ("swift", "Swift", [], False),
    ("kotlin", "Kotlin", [], False),
    ("scala", "Scala", [], False),
    ("r", "R", ["r language"], False),
    ("matlab", "MATLAB", [], False),
    ("perl", "Perl", [], False),
    ("objective-c", "Objective-C", ["objective c", "objc"], False),
    ("dart", "Dart", [], False),
    ("shell", "Shell", ["bash", "shell scripting", "shell script"], False),
    ("powershell", "PowerShell", [], False),
    ("sql-lang", "SQL", ["structured query language"], False),  # SQL 作为语言/技能
    ("solidity", "Solidity", [], True),
    ("groovy", "Groovy", [], False),
    ("lua", "Lua", [], False),
    ("haskell", "Haskell", [], False),
    ("elixir", "Elixir", [], False),
    ("clojure", "Clojure", [], False),
]

# 前端
FRONTEND = [
    ("html", "HTML", ["html5"], False),
    ("css", "CSS", ["css3"], False),
    ("react", "React", ["react.js", "reactjs"], True),
    ("vue", "Vue.js", ["vue", "vuejs", "vue.js"], True),
    ("angular", "Angular", ["angularjs", "angular.js"], False),
    ("svelte", "Svelte", ["sveltekit"], True),
    ("nextjs", "Next.js", ["next.js", "nextjs"], True),
    ("nuxt", "Nuxt.js", ["nuxt", "nuxtjs"], False),
    ("redux", "Redux", [], False),
    ("jquery", "jQuery", [], False),
    ("tailwind", "Tailwind CSS", ["tailwindcss", "tailwind"], True),
    ("bootstrap", "Bootstrap", [], False),
    ("sass", "Sass", ["scss"], False),
    ("webpack", "Webpack", [], False),
    ("vite", "Vite", [], True),
    ("electron", "Electron", [], False),
    ("threejs", "Three.js", ["three.js", "threejs"], False),
    ("webgl", "WebGL", [], False),
]

# 后端框架
BACKEND = [
    ("nodejs", "Node.js", ["node", "node.js", "nodejs"], True),
    ("express", "Express.js", ["express", "expressjs"], False),
    ("nestjs", "NestJS", ["nest.js", "nestjs"], True),
    ("django", "Django", [], False),
    ("flask", "Flask", [], False),
    ("fastapi", "FastAPI", [], True),
    ("spring", "Spring", ["spring framework"], False),
    ("springboot", "Spring Boot", ["springboot", "spring-boot"], False),
    ("dotnet", ".NET", ["dotnet", ".net core", ".net framework", "asp.net", "asp.net core"], False),
    ("laravel", "Laravel", [], False),
    ("symfony", "Symfony", [], False),
    ("rails", "Ruby on Rails", ["rails", "ror", "ruby on rails"], False),
    ("gin", "Gin", [], False),
    ("hibernate", "Hibernate", [], False),
    ("grpc", "gRPC", [], True),
    ("graphql", "GraphQL", [], True),
    ("rest", "REST API", ["rest", "restful", "rest api", "restful api", "restful apis", "rest apis"], False),
]

# 数据库
DATABASE = [
    ("mysql", "MySQL", [], False),
    ("postgresql", "PostgreSQL", ["postgres", "postgresql", "psql"], True),
    ("mongodb", "MongoDB", ["mongo"], False),
    ("redis", "Redis", [], False),
    ("oracle-db", "Oracle Database", ["oracle", "oracle db", "pl/sql", "plsql"], False),
    ("sqlserver", "SQL Server", ["mssql", "ms sql", "ms sql server", "microsoft sql server", "azure sql"], False),
    ("sqlite", "SQLite", [], False),
    ("cassandra", "Cassandra", [], False),
    ("elasticsearch", "Elasticsearch", ["elastic search", "elastic"], False),
    ("dynamodb", "DynamoDB", [], False),
    ("neo4j", "Neo4j", ["graph database"], False),
    ("clickhouse", "ClickHouse", [], True),
    ("mariadb", "MariaDB", [], False),
    ("couchbase", "Couchbase", [], False),
    ("influxdb", "InfluxDB", [], False),
    ("db2", "DB2", [], False),
    ("nosql", "NoSQL", [], False),
]

# 云
CLOUD = [
    ("aws", "AWS", ["amazon web services", "amazon aws", "aws cloud"], True),
    ("azure", "Microsoft Azure", ["azure"], True),
    ("gcp", "Google Cloud", ["google cloud platform", "gcp", "google cloud"], True),
    ("alicloud", "Alibaba Cloud", ["aliyun", "alibaba cloud"], False),
    ("cloudflare", "Cloudflare", [], False),
    ("heroku", "Heroku", [], False),
    ("digitalocean", "DigitalOcean", [], False),
    ("s3", "Amazon S3", ["s3"], False),
    ("ec2", "Amazon EC2", ["ec2"], False),
    ("lambda", "AWS Lambda", ["aws lambda"], False),
    ("redshift", "Amazon Redshift", ["redshift"], False),
    ("aurora", "Amazon Aurora", ["aurora"], False),
]

# 大数据 / 数据工程
BIGDATA = [
    ("spark", "Apache Spark", ["spark", "pyspark", "apache spark"], True),
    ("hadoop", "Hadoop", ["apache hadoop"], False),
    ("kafka", "Apache Kafka", ["kafka", "apache kafka"], True),
    ("flink", "Apache Flink", ["flink"], True),
    ("airflow", "Apache Airflow", ["airflow"], True),
    ("dbt", "dbt", [], True),
    ("hive", "Hive", ["apache hive"], False),
    ("snowflake", "Snowflake", [], True),
    ("databricks", "Databricks", [], True),
    ("etl", "ETL", [], False),
    ("bigquery", "BigQuery", ["big query"], True),
    ("rabbitmq", "RabbitMQ", [], False),
    ("dagster", "Dagster", [], True),
    ("data-warehouse", "Data Warehouse", ["data warehousing", "datawarehouse"], False),
    ("data-lake", "Data Lake", [], False),
    ("data-pipeline", "Data Pipeline", ["data pipelines"], False),
]

# 数据分析 / BI
DATA_ANALYSIS = [
    ("pandas", "Pandas", [], False),
    ("numpy", "NumPy", [], False),
    ("tableau", "Tableau", [], False),
    ("powerbi", "Power BI", ["powerbi", "power bi"], False),
    ("excel", "Excel", ["microsoft excel"], False),
    ("looker", "Looker", [], False),
    ("data-analysis", "Data Analysis", ["data analytics"], False),
    ("data-visualization", "Data Visualization", ["data viz"], False),
    ("data-mining", "Data Mining", [], False),
    ("statistics", "Statistics", ["statistical analysis"], False),
    ("ab-testing", "A/B Testing", ["a/b test", "ab test", "ab testing"], False),
]

# AI / 机器学习(经典)
AI_ML = [
    ("machine-learning", "Machine Learning", ["ml", "machine learning"], True),
    ("deep-learning", "Deep Learning", ["dl"], True),
    ("pytorch", "PyTorch", ["torch"], True),
    ("tensorflow", "TensorFlow", ["tf"], True),
    ("keras", "Keras", [], False),
    ("scikit-learn", "scikit-learn", ["sklearn", "scikit learn"], False),
    ("nlp", "NLP", ["natural language processing"], True),
    ("computer-vision", "Computer Vision", ["cv", "opencv"], True),
    ("reinforcement-learning", "Reinforcement Learning", ["rl"], False),
    ("xgboost", "XGBoost", [], False),
    ("data-science", "Data Science", [], True),
    ("jupyter", "Jupyter", ["jupyter notebook"], False),
    ("cuda", "CUDA", [], False),
    ("recommendation-system", "Recommendation System", ["recommender system", "recsys"], False),
    ("feature-engineering", "Feature Engineering", [], False),
    ("model-deployment", "Model Deployment", ["model serving"], False),
]

# AI 新兴 / RAG / Agent / LLM 生态 —— 支撑细粒度
AI_EMERGING = [
    ("llm", "LLM", ["large language model", "large language models", "llms"], True),
    ("rag", "RAG", ["retrieval augmented generation", "retrieval-augmented generation"], True),
    ("langchain", "LangChain", [], True),
    ("llamaindex", "LlamaIndex", ["llama index", "llama-index"], True),
    ("langgraph", "LangGraph", [], True),
    ("vector-database", "Vector Database", ["vector db", "vectordb", "vector databases"], True),
    ("pinecone", "Pinecone", [], True),
    ("milvus", "Milvus", [], True),
    ("weaviate", "Weaviate", [], True),
    ("chroma", "Chroma", ["chromadb"], True),
    ("faiss", "FAISS", [], True),
    ("embedding", "Embedding", ["embeddings", "text embedding"], True),
    ("prompt-engineering", "Prompt Engineering", ["prompt design"], True),
    ("fine-tuning", "Fine-tuning", ["finetuning", "fine tuning", "lora", "qlora"], True),
    ("agent", "AI Agent", ["ai agent", "ai agents", "agentic", "autonomous agent"], True),
    ("transformer", "Transformer", ["transformers"], True),
    ("bert", "BERT", [], False),
    ("gpt", "GPT", ["chatgpt", "gpt-4", "gpt4"], True),
    ("huggingface", "Hugging Face", ["huggingface", "hugging face"], True),
    ("openai-api", "OpenAI API", ["openai"], True),
    ("mlops", "MLOps", [], True),
    ("mcp", "MCP", ["model context protocol"], True),
    ("multimodal", "Multimodal", ["multi-modal"], True),
    ("diffusion", "Diffusion Model", ["stable diffusion", "diffusion models"], True),
    ("knowledge-graph", "Knowledge Graph", [], False),
]

# DevOps / 基础设施
DEVOPS = [
    ("docker", "Docker", ["containerization", "containers"], True),
    ("kubernetes", "Kubernetes", ["k8s"], True),
    ("terraform", "Terraform", [], True),
    ("ansible", "Ansible", [], False),
    ("jenkins", "Jenkins", [], False),
    ("gitlab-ci", "GitLab CI", ["gitlab ci"], False),
    ("github-actions", "GitHub Actions", [], True),
    ("cicd", "CI/CD", ["ci/cd", "continuous integration", "continuous deployment"], True),
    ("helm", "Helm", [], False),
    ("prometheus", "Prometheus", [], False),
    ("grafana", "Grafana", [], False),
    ("nginx", "Nginx", [], False),
    ("linux", "Linux", [], False),
    ("unix", "Unix", [], False),
    ("git", "Git", ["github", "gitlab", "bitbucket", "version control"], False),
    ("devops", "DevOps", [], True),
    ("microservices", "Microservices", ["microservice", "microservice architecture"], True),
    ("serverless", "Serverless", [], True),
    ("argocd", "ArgoCD", ["argo cd"], True),
    ("cloudformation", "CloudFormation", [], False),
    ("vagrant", "Vagrant", [], False),
    ("istio", "Istio", ["service mesh"], False),
]

# 测试 / QA
TESTING = [
    ("selenium", "Selenium", [], False),
    ("cypress", "Cypress", [], True),
    ("playwright", "Playwright", [], True),
    ("jest", "Jest", [], False),
    ("pytest", "pytest", [], False),
    ("junit", "JUnit", [], False),
    ("appium", "Appium", [], False),
    ("jmeter", "JMeter", [], False),
    ("postman", "Postman", [], False),
    ("qa-automation", "QA Automation", ["test automation", "automation testing"], False),
    ("unit-testing", "Unit Testing", [], False),
]

# 移动
MOBILE = [
    ("android", "Android", [], False),
    ("ios", "iOS", [], False),
    ("flutter", "Flutter", [], True),
    ("react-native", "React Native", [], True),
    ("xamarin", "Xamarin", [], False),
    ("jetpack-compose", "Jetpack Compose", [], True),
]

# 安全
SECURITY = [
    ("cybersecurity", "Cybersecurity", ["cyber security", "information security", "infosec"], True),
    ("penetration-testing", "Penetration Testing", ["pentest", "pen testing"], False),
    ("oauth", "OAuth", [], False),
    ("jwt", "JWT", [], False),
    ("encryption", "Encryption", [], False),
    ("ssl-tls", "SSL/TLS", ["ssl", "tls"], False),
    ("siem", "SIEM", [], False),
    ("owasp", "OWASP", [], False),
    ("zero-trust", "Zero Trust", [], True),
]

# 方法 / 概念 / 工具
METHODS = [
    ("agile", "Agile", [], False),
    ("scrum", "Scrum", [], False),
    ("kanban", "Kanban", [], False),
    ("jira", "Jira", [], False),
    ("confluence", "Confluence", [], False),
    # 孤立 "API" 已移除:太泛、无区分度;具体 REST API/API Design 等保留。
    ("websocket", "WebSocket", ["websockets"], False),
    ("json", "JSON", [], False),
    ("xml", "XML", [], False),
    ("oop", "OOP", ["object oriented programming", "object-oriented"], False),
    ("system-design", "System Design", [], True),
    ("distributed-systems", "Distributed Systems", ["distributed system"], True),
    ("blockchain", "Blockchain", ["web3", "smart contract", "smart contracts"], True),
    ("data-structures", "Data Structures", ["data structures and algorithms", "dsa"], False),
    ("algorithms", "Algorithms", ["algorithm"], False),
]

# === A 模块(简历抽取)中文别名补充:ZH_ALIASES 挂已有条目,A_MODULE_SKILLS 为新建条目 ===
# 设计:不改动上面手工条目,统一在 build() 合并,便于回滚。
ZH_ALIASES = {
    "A/B Testing": ["a/b测试", "ab测试"],
    "AI Agent": ["智能体"],
    "Agile": ["敏捷开发"],
    "Algorithms": ["算法"],
    "Alibaba Cloud": ["阿里云"],
    "Blockchain": ["区块链", "智能合约"],
    "C": ["c语言"],
    "CI/CD": ["持续集成", "持续部署"],
    "Computer Vision": ["计算机视觉"],
    "Cybersecurity": ["信息安全"],
    "Data Analysis": ["数据分析"],
    "Data Lake": ["数据湖"],
    "Data Mining": ["数据挖掘"],
    "Data Structures": ["数据结构"],
    "Data Visualization": ["数据可视化"],
    "Data Warehouse": ["数据仓库", "数仓"],
    "Deep Learning": ["深度学习"],
    "Diffusion Model": ["扩散模型"],
    "Distributed Systems": ["分布式系统"],
    "Elasticsearch": ["es搜索"],
    "Embedding": ["向量嵌入"],
    "Excel": ["数据透视表"],
    "Feature Engineering": ["特征工程"],
    "Fine-tuning": ["微调"],
    "Go": ["go语言"],
    "Knowledge Graph": ["知识图谱"],
    "LLM": ["大语言模型", "大模型"],
    "Machine Learning": ["机器学习"],
    "Microservices": ["微服务"],
    "Model Deployment": ["模型部署", "模型服务"],
    "NLP": ["自然语言处理"],
    "NoSQL": ["非关系型数据库"],
    "OOP": ["面向对象"],
    "Penetration Testing": ["渗透测试"],
    "Prompt Engineering": ["提示词工程"],
    "R": ["r语言"],
    "RAG": ["检索增强生成"],
    "Recommendation System": ["推荐系统"],
    "Reinforcement Learning": ["强化学习"],
    "Shell": ["shell脚本"],
    "Statistics": ["统计", "统计建模"],
    "System Design": ["系统设计"],
    "Unit Testing": ["单元测试"],
    "Vector Database": ["向量数据库"],
    "Zero Trust": ["零信任"],
}

A_MODULE_SKILLS = [
    ("aigc", "AIGC", ["生成式人工智能", "generative ai"], "ai_emerging", True),
    ("cnn", "CNN", ["卷积神经网络", "convolutional neural network"], "ai_ml", False),
    ("rnn", "RNN", ["循环神经网络", "recurrent neural network"], "ai_ml", False),
    ("crf", "CRF", ["条件随机场", "conditional random field"], "ai_ml", False),
    ("gnn", "Graph Neural Network", ["图神经网络", "gnn"], "ai_ml", False),
    ("ner", "Named Entity Recognition", ["命名实体识别", "ner"], "ai_ml", False),
    ("sentiment-analysis", "Sentiment Analysis", ["情感分析"], "ai_ml", False),
    ("text-classification", "Text Classification", ["文本分类"], "ai_ml", False),
    ("information-extraction", "Information Extraction", ["信息抽取"], "ai_ml", False),
    ("supervised-learning", "Supervised Learning", ["监督学习"], "ai_ml", False),
    ("unsupervised-learning", "Unsupervised Learning", ["无监督学习"], "ai_ml", False),
    ("model-evaluation", "Model Evaluation", ["模型评估"], "ai_ml", False),
    ("quantization", "Quantization", ["量化", "模型量化"], "ai_emerging", False),
    ("multi-agent", "Multi-Agent System", ["多智能体", "multi-agent", "multi agent system"], "ai_emerging", True),
    ("tool-calling", "Tool Calling", ["工具调用", "function calling"], "ai_emerging", True),
    ("coze", "Coze", ["扣子"], "ai_emerging", True),
    ("qwen", "Qwen", ["通义千问", "tongyi"], "ai_emerging", True),
    ("business-intelligence", "Business Intelligence", ["商业智能", "bi"], "data_analysis", False),
    ("dashboard", "Dashboard", ["仪表盘", "数据看板"], "data_analysis", False),
    ("data-cleaning", "Data Cleaning", ["数据清洗"], "data_analysis", False),
    ("hypothesis-testing", "Hypothesis Testing", ["假设检验"], "data_analysis", False),
    ("time-series", "Time Series Analysis", ["时间序列分析", "时间序列"], "data_analysis", False),
    ("data-governance", "Data Governance", ["数据治理"], "bigdata", False),
    ("data-modeling", "Data Modeling", ["数据建模"], "bigdata", False),
    ("data-quality", "Data Quality", ["数据质量"], "bigdata", False),
    ("dimensional-modeling", "Dimensional Modeling", ["维度建模"], "bigdata", False),
    ("cloud-computing", "Cloud Computing", ["云计算"], "cloud", True),
    ("edge-computing", "Edge Computing", ["边缘计算"], "cloud", True),
    ("tencent-cloud", "Tencent Cloud", ["腾讯云", "tencent cloud"], "cloud", False),
    ("caching", "Caching", ["缓存"], "devops", False),
    ("high-availability", "High Availability", ["高可用", "ha"], "devops", False),
    ("load-balancing", "Load Balancing", ["负载均衡"], "devops", False),
    ("message-queue", "Message Queue", ["消息队列", "mq"], "devops", False),
    ("capacity-planning", "Capacity Planning", ["容量规划"], "devops", False),
    ("performance-tuning", "Performance Tuning", ["性能调优", "性能优化"], "devops", False),
    ("sre", "SRE", ["站点可靠性工程", "site reliability engineering"], "devops", True),
    ("root-cause-analysis", "Root Cause Analysis", ["根因分析", "rca"], "devops", False),
    ("compliance", "Compliance", ["合规"], "security", False),
    ("cryptography", "Cryptography", ["密码学"], "security", False),
    ("data-privacy", "Data Privacy", ["数据隐私"], "security", False),
    ("iam", "Identity and Access Management", ["身份认证", "iam"], "security", False),
    ("network-security", "Network Security", ["网络安全"], "security", False),
    ("vulnerability-assessment", "Vulnerability Assessment", ["漏洞评估"], "security", False),
    ("incident-response", "Incident Response", ["应急响应"], "security", False),
    ("api-design", "API Design", ["接口设计"], "methods", False),
    ("design-patterns", "Design Patterns", ["设计模式"], "methods", False),
    ("regex", "Regular Expression", ["正则表达式", "regex", "regexp"], "methods", False),
    ("web-scraping", "Web Scraping", ["爬虫", "网络爬虫", "web crawler", "crawler"], "methods", False),
    ("integration-testing", "Integration Testing", ["集成测试"], "testing", False),
    ("load-testing", "Load Testing", ["压力测试", "负载测试"], "testing", False),
    ("rest-api-testing", "REST API Testing", ["接口测试", "api testing"], "testing", False),
    ("gis", "GIS", ["地理信息系统"], "methods", False),
    ("iot", "IoT", ["物联网", "internet of things"], "methods", True),
]

ALL_GROUPS = {
    "language": LANGUAGES,
    "frontend": FRONTEND,
    "backend": BACKEND,
    "database": DATABASE,
    "cloud": CLOUD,
    "bigdata": BIGDATA,
    "data_analysis": DATA_ANALYSIS,
    "ai_ml": AI_ML,
    "ai_emerging": AI_EMERGING,
    "devops": DEVOPS,
    "testing": TESTING,
    "mobile": MOBILE,
    "security": SECURITY,
    "methods": METHODS,
}


def build():
    skills = []
    alias_to_id = {}
    id_to_name = {}
    by_category = {}
    all_aliases = set()
    seen_ids = set()
    conflicts = []

    # 把 A 模块新增条目按 category 并入(不改原始 ALL_GROUPS,便于回滚)
    merged_groups = {cat: list(group) for cat, group in ALL_GROUPS.items()}
    for sid, name, aliases, category, hot in A_MODULE_SKILLS:
        merged_groups.setdefault(category, []).append((sid, name, aliases, hot))

    for category, group in merged_groups.items():
        for sid, name, aliases, hot in group:
            if sid in seen_ids:
                conflicts.append(("dup_id", sid))
                continue
            seen_ids.add(sid)

            # 别名集合:name、id、显式 aliases,全部小写
            alias_set = set()
            alias_set.add(name.lower())
            alias_set.add(sid.lower().replace("-", " "))
            alias_set.add(sid.lower())
            for a in aliases:
                alias_set.add(a.lower())
            # A 模块中文别名(挂到已有条目)
            for a in ZH_ALIASES.get(name, []):
                alias_set.add(a.lower())

            entry = {
                "id": sid,
                "name": name,
                "category": category,
                "hot": hot,
                "aliases": sorted(alias_set),
            }
            skills.append(entry)
            id_to_name[sid] = name
            by_category.setdefault(category, []).append(sid)

            for a in alias_set:
                if a in alias_to_id and alias_to_id[a] != sid:
                    conflicts.append(("dup_alias", a, alias_to_id[a], sid))
                else:
                    alias_to_id[a] = sid
                all_aliases.add(a)

    out = {
        "version": "v1",
        "total": len(skills),
        "hot_count": sum(1 for s in skills if s["hot"]),
        "categories": list(ALL_GROUPS.keys()),
        "skills": skills,
        "alias_to_id": alias_to_id,
        "id_to_name": id_to_name,
        "by_category": by_category,
        "all_aliases": sorted(all_aliases),
    }
    return out, conflicts


if __name__ == "__main__":
    out, conflicts = build()
    os.makedirs("data/gold", exist_ok=True)
    path = "data/gold/skill_vocab.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"技能总数: {out['total']}")
    print(f"热门/新兴: {out['hot_count']}")
    print(f"别名总数: {len(out['all_aliases'])}")
    print(f"类别: {len(out['categories'])} -> {out['categories']}")
    print("\n各类别技能数:")
    for c, ids in out["by_category"].items():
        print(f"  {c:14s}: {len(ids)}")
    if conflicts:
        print(f"\n[警告] 冲突 {len(conflicts)} 处(需检查):")
        for c in conflicts[:20]:
            print(f"  {c}")
    else:
        print("\n无 id/别名冲突")
    print(f"\n已写出: {path}")