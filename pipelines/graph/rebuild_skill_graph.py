"""
rebuild_skill_graph.py
用 B 的技能 ID 重建完整先修关系图谱（275个技能），
输出 data/gold/skill_prerequisite_v2.json
"""
import json
from pathlib import Path

_REPO = Path(__file__).parents[2]
OUT = _REPO / "data" / "gold" / "skill_prerequisite_v2.json"

# B 词表：优先用仓库内 B 模块维护的版本，多路径兜底（保证任意机器可跑）
_B_VOCAB_CANDIDATES = [
    _REPO / "data" / "gold" / "skill_vocab.json",
    _REPO / "data" / "processed" / "skill_vocab.json",
    _REPO / "pipelines" / "extract" / "skill_vocab.json",
]

# ── 技能定义 ────────────────────────────────────────────────────────────────
# 格式：skill_id, skill_name, category, level(1-4), difficulty, hours_estimate, prerequisites[]
# level: 1=入门起点 2=初级 3=中级 4=高级
SKILLS = [
    # ═══ 编程语言 ════════════════════════════════════════════════════════════
    # 通用语言，无前置，自成起点
    ("python",        "Python",        "language", 1, "beginner",     40,  []),
    ("java",          "Java",          "language", 1, "beginner",     60,  []),
    ("javascript",    "JavaScript",    "language", 1, "beginner",     40,  []),
    ("c",             "C",             "language", 1, "beginner",     50,  []),
    ("go",            "Go",            "language", 1, "intermediate", 40,  []),
    ("rust",          "Rust",          "language", 1, "advanced",     60,  []),
    ("ruby",          "Ruby",          "language", 1, "beginner",     30,  []),
    ("php",           "PHP",           "language", 1, "beginner",     30,  []),
    ("swift",         "Swift",         "language", 1, "intermediate", 40,  []),
    ("kotlin",        "Kotlin",        "language", 1, "intermediate", 40,  []),
    ("r",             "R",             "language", 1, "beginner",     30,  []),
    ("matlab",        "MATLAB",        "language", 1, "beginner",     30,  []),
    ("perl",          "Perl",          "language", 1, "beginner",     20,  []),
    ("dart",          "Dart",          "language", 1, "beginner",     20,  []),
    ("lua",           "Lua",           "language", 1, "beginner",     15,  []),
    ("solidity",      "Solidity",      "language", 2, "intermediate", 40,  ["javascript"]),
    ("scala",         "Scala",         "language", 2, "intermediate", 50,  ["java"]),
    ("groovy",        "Groovy",        "language", 2, "beginner",     20,  ["java"]),
    ("cpp",           "C++",           "language", 2, "intermediate", 60,  ["c"]),
    ("csharp",        "C#",            "language", 2, "intermediate", 50,  ["java"]),
    ("typescript",    "TypeScript",    "language", 2, "beginner",     20,  ["javascript"]),
    ("objective-c",   "Objective-C",   "language", 2, "intermediate", 30,  ["c"]),
    ("shell",         "Shell",         "language", 2, "beginner",     15,  ["linux"]),
    ("powershell",    "PowerShell",    "language", 2, "beginner",     15,  ["linux"]),
    ("sql-lang",      "SQL",           "language", 1, "beginner",     20,  []),
    ("haskell",       "Haskell",       "language", 1, "advanced",     60,  []),
    ("elixir",        "Elixir",        "language", 1, "intermediate", 40,  []),
    ("clojure",       "Clojure",       "language", 1, "advanced",     50,  []),
    # ═══ 前端 ═══════════════════════════════════════════════════════════════
    ("html",          "HTML",          "frontend", 1, "beginner",     10,  []),
    ("css",           "CSS",           "frontend", 1, "beginner",     15,  ["html"]),
    ("tailwind",      "Tailwind CSS",  "frontend", 2, "beginner",     10,  ["css"]),
    ("bootstrap",     "Bootstrap",     "frontend", 2, "beginner",     10,  ["html", "css"]),
    ("sass",          "Sass",          "frontend", 2, "beginner",     10,  ["css"]),
    ("jquery",        "jQuery",        "frontend", 2, "beginner",     15,  ["javascript"]),
    ("webpack",       "Webpack",       "frontend", 2, "intermediate", 15,  ["javascript"]),
    ("vite",          "Vite",          "frontend", 2, "beginner",     10,  ["javascript"]),
    ("react",         "React",         "frontend", 3, "intermediate", 40,  ["javascript", "typescript"]),
    ("vue",           "Vue.js",        "frontend", 3, "intermediate", 35,  ["javascript", "typescript"]),
    ("angular",       "Angular",       "frontend", 3, "intermediate", 50,  ["typescript"]),
    ("svelte",        "Svelte",        "frontend", 3, "intermediate", 25,  ["javascript"]),
    ("redux",         "Redux",         "frontend", 3, "intermediate", 15,  ["react"]),
    ("nextjs",        "Next.js",       "frontend", 4, "intermediate", 30,  ["react"]),
    ("nuxt",          "Nuxt.js",       "frontend", 4, "intermediate", 25,  ["vue"]),
    ("electron",      "Electron",      "frontend", 3, "intermediate", 25,  ["javascript", "nodejs"]),
    ("threejs",       "Three.js",      "frontend", 3, "advanced",     30,  ["javascript"]),
    ("webgl",         "WebGL",         "frontend", 4, "advanced",     40,  ["javascript", "threejs"]),
    # ═══ 后端 ═══════════════════════════════════════════════════════════════
    ("nodejs",        "Node.js",       "backend",  2, "intermediate", 30,  ["javascript"]),
    ("express",       "Express.js",    "backend",  3, "beginner",     20,  ["nodejs"]),
    ("nestjs",        "NestJS",        "backend",  3, "intermediate", 30,  ["nodejs", "typescript"]),
    ("django",        "Django",        "backend",  2, "intermediate", 30,  ["python"]),
    ("flask",         "Flask",         "backend",  2, "beginner",     20,  ["python"]),
    ("fastapi",       "FastAPI",       "backend",  2, "intermediate", 20,  ["python"]),
    ("spring",        "Spring",        "backend",  2, "intermediate", 40,  ["java"]),
    ("springboot",    "Spring Boot",   "backend",  3, "intermediate", 40,  ["spring"]),
    ("dotnet",        ".NET",          "backend",  2, "intermediate", 40,  ["csharp"]),
    ("laravel",       "Laravel",       "backend",  2, "intermediate", 30,  ["php"]),
    ("symfony",       "Symfony",       "backend",  3, "intermediate", 30,  ["php"]),
    ("rails",         "Ruby on Rails", "backend",  2, "intermediate", 30,  ["ruby"]),
    ("gin",           "Gin",           "backend",  2, "intermediate", 20,  ["go"]),
    ("hibernate",     "Hibernate",     "backend",  3, "intermediate", 20,  ["spring"]),
    ("grpc",          "gRPC",          "backend",  3, "intermediate", 20,  ["python"]),
    ("graphql",       "GraphQL",       "backend",  3, "intermediate", 20,  ["nodejs"]),
    ("rest",          "REST API",      "backend",  2, "beginner",     15,  ["python"]),
    # ═══ 数据库 ══════════════════════════════════════════════════════════════
    ("mysql",         "MySQL",         "database", 2, "beginner",     20,  ["sql-lang"]),
    ("postgresql",    "PostgreSQL",    "database", 2, "beginner",     25,  ["sql-lang"]),
    ("oracle-db",     "Oracle DB",     "database", 2, "intermediate", 30,  ["sql-lang"]),
    ("sqlserver",     "SQL Server",    "database", 2, "beginner",     20,  ["sql-lang"]),
    ("sqlite",        "SQLite",        "database", 2, "beginner",     10,  ["sql-lang"]),
    ("mariadb",       "MariaDB",       "database", 2, "beginner",     15,  ["sql-lang"]),
    ("db2",           "DB2",           "database", 2, "intermediate", 25,  ["sql-lang"]),
    ("nosql",         "NoSQL",         "database", 2, "beginner",     10,  ["sql-lang"]),
    ("mongodb",       "MongoDB",       "database", 2, "beginner",     20,  ["nosql"]),
    ("redis",         "Redis",         "database", 2, "intermediate", 15,  ["sql-lang"]),
    ("cassandra",     "Cassandra",     "database", 3, "intermediate", 25,  ["nosql"]),
    ("elasticsearch", "Elasticsearch", "database", 3, "intermediate", 25,  ["nosql"]),
    ("dynamodb",      "DynamoDB",      "database", 3, "intermediate", 20,  ["nosql", "aws"]),
    ("neo4j",         "Neo4j",         "database", 3, "advanced",     30,  ["nosql"]),
    ("clickhouse",    "ClickHouse",    "database", 3, "intermediate", 25,  ["postgresql"]),
    ("couchbase",     "Couchbase",     "database", 3, "intermediate", 20,  ["nosql"]),
    ("influxdb",      "InfluxDB",      "database", 3, "intermediate", 20,  ["nosql"]),
    ("nosql",         "NoSQL概念",     "database", 2, "beginner",     10,  ["sql-lang"]),
    # ═══ 云计算 ══════════════════════════════════════════════════════════════
    ("linux",         "Linux",         "devops",   1, "beginner",     20,  []),
    ("git",           "Git",           "devops",   1, "beginner",     8,   []),
    ("cloud-computing","Cloud Computing","cloud",  2, "beginner",     15,  ["linux"]),
    ("aws",           "AWS",           "cloud",    3, "intermediate", 60,  ["linux", "docker"]),
    ("azure",         "Azure",         "cloud",    3, "intermediate", 50,  ["linux", "docker"]),
    ("gcp",           "Google Cloud",  "cloud",    3, "intermediate", 50,  ["linux", "docker"]),
    ("alicloud",      "Alibaba Cloud", "cloud",    3, "intermediate", 40,  ["linux", "docker"]),
    ("tencent-cloud", "Tencent Cloud", "cloud",    3, "intermediate", 40,  ["linux", "docker"]),
    ("cloudflare",    "Cloudflare",    "cloud",    3, "intermediate", 20,  ["linux"]),
    ("heroku",        "Heroku",        "cloud",    2, "beginner",     10,  ["git"]),
    ("digitalocean",  "DigitalOcean",  "cloud",    2, "beginner",     15,  ["linux"]),
    ("s3",            "Amazon S3",     "cloud",    3, "beginner",     10,  ["aws"]),
    ("ec2",           "Amazon EC2",    "cloud",    3, "intermediate", 15,  ["aws"]),
    ("lambda",        "AWS Lambda",    "cloud",    3, "intermediate", 20,  ["aws", "python"]),
    ("redshift",      "Amazon Redshift","cloud",   3, "intermediate", 20,  ["aws", "postgresql"]),
    ("aurora",        "Amazon Aurora", "cloud",    3, "intermediate", 20,  ["aws", "postgresql"]),
    ("edge-computing","Edge Computing","cloud",    4, "advanced",     30,  ["cloud-computing"]),
    # ═══ 大数据 ══════════════════════════════════════════════════════════════
    ("hadoop",        "Hadoop",        "bigdata",  2, "intermediate", 40,  ["linux", "java"]),
    ("spark",         "Apache Spark",  "bigdata",  3, "intermediate", 40,  ["python", "sql-lang"]),
    ("kafka",         "Apache Kafka",  "bigdata",  3, "intermediate", 25,  ["linux"]),
    ("flink",         "Apache Flink",  "bigdata",  3, "intermediate", 35,  ["spark"]),
    ("airflow",       "Apache Airflow","bigdata",  3, "intermediate", 25,  ["python"]),
    ("dbt",           "dbt",           "bigdata",  3, "intermediate", 20,  ["sql-lang", "python"]),
    ("hive",          "Hive",          "bigdata",  3, "intermediate", 25,  ["hadoop", "sql-lang"]),
    ("snowflake",     "Snowflake",     "bigdata",  3, "intermediate", 20,  ["sql-lang"]),
    ("databricks",    "Databricks",    "bigdata",  3, "intermediate", 25,  ["spark"]),
    ("etl",           "ETL",           "bigdata",  2, "intermediate", 20,  ["sql-lang", "python"]),
    ("bigquery",      "BigQuery",      "bigdata",  3, "intermediate", 20,  ["sql-lang", "gcp"]),
    ("rabbitmq",      "RabbitMQ",      "bigdata",  3, "intermediate", 15,  ["linux"]),
    ("dagster",       "Dagster",       "bigdata",  3, "intermediate", 20,  ["python", "airflow"]),
    ("data-warehouse","Data Warehouse","bigdata",  2, "intermediate", 20,  ["sql-lang"]),
    ("data-lake",     "Data Lake",     "bigdata",  3, "intermediate", 20,  ["spark"]),
    ("data-pipeline", "Data Pipeline", "bigdata",  3, "intermediate", 20,  ["python", "airflow"]),
    ("data-governance","Data Governance","bigdata",3, "intermediate", 20,  ["sql-lang"]),
    ("data-modeling", "Data Modeling", "bigdata",  2, "intermediate", 20,  ["sql-lang"]),
    ("data-quality",  "Data Quality",  "bigdata",  2, "intermediate", 15,  ["sql-lang", "python"]),
    ("dimensional-modeling","Dimensional Modeling","bigdata",3,"intermediate",25,["data-modeling"]),
    # ═══ 数据分析 ════════════════════════════════════════════════════════════
    ("pandas",        "Pandas",        "data_analysis", 2, "beginner",  20, ["python"]),
    ("numpy",         "NumPy",         "data_analysis", 2, "beginner",  15, ["python"]),
    ("tableau",       "Tableau",       "data_analysis", 2, "beginner",  20, ["sql-lang"]),
    ("powerbi",       "Power BI",      "data_analysis", 2, "beginner",  20, ["sql-lang"]),
    ("excel",         "Excel",         "data_analysis", 1, "beginner",  15, []),
    ("looker",        "Looker",        "data_analysis", 3, "intermediate",20,["sql-lang"]),
    ("data-analysis", "Data Analysis", "data_analysis", 2, "beginner",  20, ["python", "pandas"]),
    ("data-visualization","Data Visualization","data_analysis",3,"intermediate",20,["python","pandas"]),
    ("data-mining",   "Data Mining",   "data_analysis", 3, "intermediate",25,["python","machine-learning"]),
    ("statistics",    "Statistics",    "data_analysis", 2, "beginner",  30, ["python", "numpy"]),
    ("ab-testing",    "A/B Testing",   "data_analysis", 3, "intermediate",20,["statistics"]),
    ("business-intelligence","Business Intelligence","data_analysis",3,"intermediate",25,["sql-lang","tableau"]),
    ("dashboard",     "Dashboard",     "data_analysis", 2, "beginner",  15, ["sql-lang"]),
    ("data-cleaning", "Data Cleaning", "data_analysis", 2, "beginner",  15, ["python", "pandas"]),
    ("hypothesis-testing","Hypothesis Testing","data_analysis",3,"intermediate",20,["statistics"]),
    ("time-series",   "Time Series",   "data_analysis", 3, "intermediate",25,["statistics", "python"]),
    # ═══ AI / ML ═════════════════════════════════════════════════════════════
    ("numpy",         "NumPy",         "data_analysis", 2, "beginner",  15, ["python"]),   # already above
    ("pytorch",       "PyTorch",       "ai_ml",    2, "intermediate", 20, ["python", "numpy"]),
    ("tensorflow",    "TensorFlow",    "ai_ml",    2, "intermediate", 20, ["python", "numpy"]),
    ("keras",         "Keras",         "ai_ml",    2, "beginner",     15, ["tensorflow"]),
    ("scikit-learn",  "scikit-learn",  "ai_ml",    2, "intermediate", 20, ["python", "numpy"]),
    ("machine-learning","Machine Learning","ai_ml",3, "intermediate", 50, ["python", "statistics", "numpy"]),
    ("deep-learning", "Deep Learning", "ai_ml",    3, "intermediate", 40, ["machine-learning", "pytorch"]),
    ("nlp",           "NLP",           "ai_ml",    3, "intermediate", 35, ["python", "deep-learning"]),
    ("computer-vision","Computer Vision","ai_ml",  3, "intermediate", 40, ["deep-learning", "pytorch"]),
    ("reinforcement-learning","Reinforcement Learning","ai_ml",4,"advanced",50,["deep-learning"]),
    ("xgboost",       "XGBoost",       "ai_ml",    3, "intermediate", 15, ["machine-learning"]),
    ("data-science",  "Data Science",  "ai_ml",    2, "intermediate", 30, ["python", "statistics"]),
    ("jupyter",       "Jupyter",       "ai_ml",    1, "beginner",     5,  ["python"]),
    ("cuda",          "CUDA",          "ai_ml",    4, "advanced",     30, ["deep-learning", "pytorch"]),
    ("recommendation-system","Recommendation System","ai_ml",3,"intermediate",30,["machine-learning"]),
    ("feature-engineering","Feature Engineering","ai_ml",3,"intermediate",20,["python","machine-learning"]),
    ("model-deployment","Model Deployment","ai_ml",3,"intermediate",20,["python","docker","fastapi"]),
    ("cnn",           "CNN",           "ai_ml",    3, "intermediate", 20, ["deep-learning", "pytorch"]),
    ("rnn",           "RNN",           "ai_ml",    3, "intermediate", 20, ["deep-learning", "pytorch"]),
    ("crf",           "CRF",           "ai_ml",    4, "advanced",     20, ["nlp"]),
    ("gnn",           "Graph Neural Network","ai_ml",4,"advanced",   30, ["deep-learning", "pytorch"]),
    ("ner",           "NER",           "ai_ml",    3, "intermediate", 15, ["nlp"]),
    ("sentiment-analysis","Sentiment Analysis","ai_ml",3,"intermediate",15,["nlp"]),
    ("text-classification","Text Classification","ai_ml",3,"intermediate",15,["nlp"]),
    ("information-extraction","Information Extraction","ai_ml",4,"advanced",20,["nlp"]),
    ("supervised-learning","Supervised Learning","ai_ml",2,"intermediate",20,["machine-learning"]),
    ("unsupervised-learning","Unsupervised Learning","ai_ml",3,"intermediate",25,["machine-learning"]),
    ("model-evaluation","Model Evaluation","ai_ml",3,"intermediate",15,["machine-learning"]),
    # ═══ AI 新兴 ═════════════════════════════════════════════════════════════
    ("transformer",   "Transformer",   "ai_emerging",3,"intermediate",25,["deep-learning", "nlp"]),
    ("bert",          "BERT",          "ai_emerging",3,"intermediate",20,["transformer"]),
    ("embedding",     "Embedding",     "ai_emerging",3,"intermediate",15,["nlp"]),
    ("llm",           "LLM",           "ai_emerging",3,"intermediate",30,["transformer"]),
    ("gpt",           "GPT",           "ai_emerging",3,"intermediate",20,["llm"]),
    ("qwen",          "Qwen",          "ai_emerging",3,"intermediate",15,["llm"]),
    ("openai-api",    "OpenAI API",    "ai_emerging",3,"beginner",    15,["python", "llm"]),
    ("huggingface",   "Hugging Face",  "ai_emerging",3,"intermediate",20,["python", "transformer"]),
    ("prompt-engineering","Prompt Engineering","ai_emerging",3,"beginner",15,["llm"]),
    ("vector-database","Vector Database","ai_emerging",3,"intermediate",20,["embedding"]),
    ("pinecone",      "Pinecone",      "ai_emerging",3,"beginner",    10,["vector-database"]),
    ("milvus",        "Milvus",        "ai_emerging",3,"intermediate",15,["vector-database"]),
    ("weaviate",      "Weaviate",      "ai_emerging",3,"intermediate",15,["vector-database"]),
    ("chroma",        "Chroma",        "ai_emerging",3,"beginner",    10,["vector-database"]),
    ("faiss",         "FAISS",         "ai_emerging",3,"intermediate",15,["vector-database"]),
    ("langchain",     "LangChain",     "ai_emerging",3,"intermediate",25,["python", "llm"]),
    ("llamaindex",    "LlamaIndex",    "ai_emerging",3,"intermediate",20,["langchain"]),
    ("langgraph",     "LangGraph",     "ai_emerging",4,"intermediate",20,["langchain"]),
    ("rag",           "RAG",           "ai_emerging",4,"intermediate",25,["vector-database", "langchain"]),
    ("fine-tuning",   "Fine-tuning",   "ai_emerging",4,"advanced",   40,["llm", "pytorch"]),
    ("quantization",  "Quantization",  "ai_emerging",4,"advanced",   25,["fine-tuning"]),
    ("agent",         "AI Agent",      "ai_emerging",4,"intermediate",25,["langchain", "llm"]),
    ("multi-agent",   "Multi-Agent",   "ai_emerging",4,"intermediate",20,["agent"]),
    ("tool-calling",  "Tool Calling",  "ai_emerging",4,"intermediate",15,["agent"]),
    ("mcp",           "MCP",           "ai_emerging",4,"intermediate",15,["tool-calling"]),
    ("coze",          "Coze",          "ai_emerging",3,"beginner",    10,["agent"]),
    ("mlops",         "MLOps",         "ai_emerging",3,"intermediate",30,["machine-learning", "docker"]),
    ("multimodal",    "Multimodal",    "ai_emerging",4,"advanced",   25,["llm"]),
    ("diffusion",     "Diffusion Model","ai_emerging",4,"advanced",  30,["deep-learning"]),
    ("knowledge-graph","Knowledge Graph","ai_emerging",4,"advanced", 30,["embedding", "nlp"]),
    ("aigc",          "AIGC",          "ai_emerging",3,"intermediate",15,["llm"]),
    # ═══ DevOps ══════════════════════════════════════════════════════════════
    ("docker",        "Docker",        "devops",   2, "intermediate", 20, ["linux"]),
    ("kubernetes",    "Kubernetes",    "devops",   3, "intermediate", 35, ["docker"]),
    ("terraform",     "Terraform",     "devops",   3, "intermediate", 25, ["cloud-computing"]),
    ("ansible",       "Ansible",       "devops",   3, "intermediate", 20, ["linux"]),
    ("jenkins",       "Jenkins",       "devops",   3, "intermediate", 20, ["git", "docker"]),
    ("gitlab-ci",     "GitLab CI",     "devops",   3, "intermediate", 15, ["git", "docker"]),
    ("github-actions","GitHub Actions","devops",   2, "beginner",     15, ["git"]),
    ("cicd",          "CI/CD",         "devops",   3, "intermediate", 20, ["git", "docker"]),
    ("helm",          "Helm",          "devops",   3, "intermediate", 15, ["kubernetes"]),
    ("prometheus",    "Prometheus",    "devops",   3, "intermediate", 15, ["linux", "docker"]),
    ("grafana",       "Grafana",       "devops",   3, "intermediate", 15, ["prometheus"]),
    ("nginx",         "Nginx",         "devops",   2, "intermediate", 15, ["linux"]),
    ("devops",        "DevOps",        "devops",   3, "intermediate", 30, ["linux", "docker", "git"]),
    ("microservices", "Microservices", "devops",   4, "advanced",     30, ["docker", "system-design"]),
    ("serverless",    "Serverless",    "devops",   3, "intermediate", 20, ["cloud-computing"]),
    ("argocd",        "ArgoCD",        "devops",   4, "advanced",     20, ["kubernetes"]),
    ("cloudformation","CloudFormation","devops",   3, "intermediate", 20, ["aws"]),
    ("vagrant",       "Vagrant",       "devops",   2, "beginner",     10, ["linux"]),
    ("istio",         "Istio",         "devops",   4, "advanced",     25, ["kubernetes"]),
    ("caching",       "Caching",       "devops",   3, "intermediate", 15, ["redis"]),
    ("high-availability","High Availability","devops",4,"advanced",  25, ["system-design"]),
    ("load-balancing","Load Balancing","devops",   3, "intermediate", 20, ["linux", "system-design"]),
    ("message-queue", "Message Queue", "devops",   3, "intermediate", 15, ["kafka"]),
    ("capacity-planning","Capacity Planning","devops",4,"advanced",  20, ["system-design"]),
    ("performance-tuning","Performance Tuning","devops",4,"advanced",25,["system-design", "linux"]),
    ("sre",           "SRE",           "devops",   4, "advanced",     30, ["system-design", "linux"]),
    ("root-cause-analysis","Root Cause Analysis","devops",3,"intermediate",15,["linux"]),
    ("unix",          "Unix",          "devops",   1, "beginner",     10, []),
    # ═══ 测试 ════════════════════════════════════════════════════════════════
    ("selenium",      "Selenium",      "testing",  2, "beginner",     15, ["python"]),
    ("cypress",       "Cypress",       "testing",  2, "intermediate", 15, ["javascript"]),
    ("playwright",    "Playwright",    "testing",  2, "intermediate", 15, ["javascript"]),
    ("jest",          "Jest",          "testing",  2, "beginner",     10, ["javascript"]),
    ("pytest",        "pytest",        "testing",  2, "beginner",     10, ["python"]),
    ("junit",         "JUnit",         "testing",  2, "beginner",     10, ["java"]),
    ("appium",        "Appium",        "testing",  3, "intermediate", 20, ["python", "java"]),
    ("jmeter",        "JMeter",        "testing",  3, "intermediate", 15, ["java", "linux"]),
    ("postman",       "Postman",       "testing",  2, "beginner",     10, ["rest"]),
    ("qa-automation", "QA Automation", "testing",  3, "intermediate", 25, ["python", "selenium"]),
    ("unit-testing",  "Unit Testing",  "testing",  2, "beginner",     10, ["python"]),
    ("integration-testing","Integration Testing","testing",3,"intermediate",15,["unit-testing"]),
    ("load-testing",  "Load Testing",  "testing",  3, "intermediate", 15, ["jmeter"]),
    ("rest-api-testing","REST API Testing","testing",2,"beginner",   10, ["rest", "postman"]),
    # ═══ 移动开发 ════════════════════════════════════════════════════════════
    ("android",       "Android",       "mobile",   2, "intermediate", 40, ["kotlin"]),
    ("ios",           "iOS",           "mobile",   2, "intermediate", 40, ["swift"]),
    ("flutter",       "Flutter",       "mobile",   2, "intermediate", 35, ["dart"]),
    ("react-native",  "React Native",  "mobile",   3, "intermediate", 30, ["react"]),
    ("xamarin",       "Xamarin",       "mobile",   2, "intermediate", 30, ["csharp"]),
    ("jetpack-compose","Jetpack Compose","mobile",  3, "intermediate", 25, ["android"]),
    # ═══ 安全 ════════════════════════════════════════════════════════════════
    ("cybersecurity", "Cybersecurity", "security", 2, "intermediate", 30, ["linux"]),
    ("penetration-testing","Penetration Testing","security",3,"advanced",40,["cybersecurity", "linux"]),
    ("oauth",         "OAuth",         "security", 3, "intermediate", 15, ["rest", "python"]),
    ("jwt",           "JWT",           "security", 2, "beginner",     10, ["rest", "python"]),
    ("encryption",    "Encryption",    "security", 3, "intermediate", 20, ["cybersecurity"]),
    ("ssl-tls",       "SSL/TLS",       "security", 3, "intermediate", 15, ["cybersecurity"]),
    ("siem",          "SIEM",          "security", 3, "intermediate", 25, ["cybersecurity"]),
    ("owasp",         "OWASP",         "security", 3, "intermediate", 20, ["cybersecurity", "rest"]),
    ("zero-trust",    "Zero Trust",    "security", 3, "intermediate", 20, ["cybersecurity"]),
    ("compliance",    "Compliance",    "security", 3, "intermediate", 20, ["cybersecurity"]),
    ("cryptography",  "Cryptography",  "security", 3, "advanced",     30, ["cybersecurity"]),
    ("data-privacy",  "Data Privacy",  "security", 3, "intermediate", 15, ["cybersecurity"]),
    ("iam",           "IAM",           "security", 3, "intermediate", 20, ["cybersecurity", "cloud-computing"]),
    ("network-security","Network Security","security",3,"intermediate",25,["cybersecurity", "linux"]),
    ("vulnerability-assessment","Vulnerability Assessment","security",3,"advanced",30,["penetration-testing"]),
    ("incident-response","Incident Response","security",4,"advanced",25,["cybersecurity", "sre"]),
    # ═══ 方法论 ══════════════════════════════════════════════════════════════
    ("agile",         "Agile",         "methods",  1, "beginner",     10, []),
    ("scrum",         "Scrum",         "methods",  1, "beginner",     8,  ["agile"]),
    ("kanban",        "Kanban",        "methods",  1, "beginner",     5,  ["agile"]),
    ("jira",          "Jira",          "methods",  1, "beginner",     5,  []),
    ("confluence",    "Confluence",    "methods",  1, "beginner",     3,  []),
    ("websocket",     "WebSocket",     "methods",  3, "intermediate", 10, ["nodejs"]),
    ("json",          "JSON",          "methods",  1, "beginner",     3,  ["python"]),
    ("xml",           "XML",           "methods",  1, "beginner",     5,  ["python"]),
    ("oop",           "OOP",           "methods",  2, "beginner",     15, ["python"]),
    ("system-design", "System Design", "methods",  3, "intermediate", 40, ["python", "sql-lang", "docker"]),
    ("distributed-systems","Distributed Systems","methods",4,"advanced",40,["system-design"]),
    ("blockchain",    "Blockchain",    "methods",  3, "intermediate", 30, ["python"]),
    ("data-structures","Data Structures","methods",2,"intermediate",  30, ["python"]),
    ("algorithms",    "Algorithms",    "methods",  3, "intermediate", 40, ["data-structures"]),
    ("api-design",    "API Design",    "methods",  3, "intermediate", 20, ["rest", "python"]),
    ("design-patterns","Design Patterns","methods",3,"intermediate",  25, ["oop", "python"]),
    ("regex",         "Regular Expression","methods",2,"beginner",   10, ["python"]),
    ("web-scraping",  "Web Scraping",  "methods",  2, "intermediate", 15, ["python", "regex"]),
    ("gis",           "GIS",           "methods",  2, "intermediate", 30, ["python"]),
    ("iot",           "IoT",           "methods",  3, "intermediate", 30, ["linux", "python"]),
]


def build():
    # 去重（同一 skill_id 可能在草稿中重复）
    seen = {}
    for entry in SKILLS:
        sid = entry[0]
        if sid not in seen:
            seen[sid] = entry

    skills_list = []
    for sid, name, cat, level, diff, hours, prereqs in seen.values():
        skills_list.append({
            "skill_id":      sid,
            "skill_name":    name,
            "category":      cat,
            "level":         level,
            "difficulty":    diff,
            "hours_estimate":hours,
            "hot":           False,   # 由 B 词表注入
            "prerequisites": prereqs,
        })

    # 从 B vocab 注入 hot 标记和别名（读仓库内文件，跨机器可移植）
    b_vocab_path = next((p for p in _B_VOCAB_CANDIDATES if p.exists()), None)
    if b_vocab_path is not None:
        with open(b_vocab_path, encoding="utf-8") as f:
            bv = json.load(f)
        b_hot  = {s["id"] for s in bv["skills"] if s.get("hot")}
        b_alias = {s["id"]: s.get("aliases", []) for s in bv["skills"]}
        for s in skills_list:
            if s["skill_id"] in b_hot:
                s["hot"] = True
            s["aliases"] = b_alias.get(s["skill_id"], [])

    # 验证先修ID是否都在图谱内
    all_ids = {s["skill_id"] for s in skills_list}
    errors = []
    for s in skills_list:
        for p in s["prerequisites"]:
            if p not in all_ids:
                errors.append(f"  {s['skill_id']} 的先修 {p} 不在图谱内")
    if errors:
        print("[WARN] 先修关系引用了不存在的节点：")
        for e in errors: print(e)

    output = {
        "version":     "v2",
        "description": "基于B模块技能词表(275个)重建的先修关系图谱，节点ID与B词表完全对齐",
        "total":       len(skills_list),
        "hot_count":   sum(1 for s in skills_list if s["hot"]),
        "skills":      skills_list,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] 输出: {OUT}")
    print(f"     技能总数: {len(skills_list)}")
    print(f"     热门技能: {sum(1 for s in skills_list if s['hot'])}")
    hot_no_prereq = [s['skill_id'] for s in skills_list if s['hot'] and not s['prerequisites']]
    print(f"     热门入门节点（无先修）: {hot_no_prereq}")


if __name__ == "__main__":
    build()
